from django.shortcuts import render, redirect
from django.http import Http404, HttpResponse, JsonResponse, FileResponse, StreamingHttpResponse
from django.views.decorators.cache import cache_page
from django.conf import settings
from django.forms.models import model_to_dict
from django.urls.base import reverse
from django.core.exceptions import ValidationError
from django.db.models.functions import Length
from django.db.models import Case, When
from wsgiref.util import FileWrapper
from celery.result import AsyncResult
from dal import autocomplete, forward
from analysis.models import Analysis, Genes, Projects, AnalysisGenes
from analysis.forms import AnalysisForm
from analysis.tasks import submit_command
import time
import hashlib
import os
import re
import json
import string
import pandas as pd
import numpy as np
import math
from transect_web.settings import env

# also fetches root folder name of the GSEA curated/hallmark reports
# this is because these folders contains a number at the end
# that appears to be procedurally generated
def FetchGseaSummary(request, analysis_id):
    analysis =  Analysis.objects.filter(sha_hash=str(analysis_id))
    if analysis.exists() is False:
        raise Http404("Analysis Not Found")

    analysis = analysis.first()

    if analysis.percentile == 0:
        return JsonResponse({'error': f'{analysis_id} is not a DE analysis'}, status=500)

    gois = []
    for goi in analysis.genes_of_interest.all():
        gois.append(goi.name)

    GSEA_path = os.path.join(env('OUTPUT_DIR'), str(analysis_id), "GSEA")
    GSEA_summary = os.path.join(GSEA_path, "-".join(gois) + "_Strat_Vs_Curated.html")
    if os.path.exists(GSEA_path) is False or os.path.exists(GSEA_summary) is False:
        return JsonResponse({'error': f'{analysis_id} does not contain sufficient data '}, status=500)

    hallmark_report_root = ""
    curated_report_root = ""
    gsea_curated_plotly_data = ""

    # now lets fetch the reports
    for item in os.listdir(os.path.join(env('OUTPUT_DIR'), str(analysis_id), "GSEA")):
        if "Strat_Vs_Curated.GseaPreranked" in item:
            curated_report_root = item
        elif "Strat_Vs_Hallmark.GseaPreranked" in item:
            hallmark_report_root = item
        elif "Strat_Vs_Curated.json" in item:
            gsea_curated_data_file = os.path.join(env('OUTPUT_DIR'), str(analysis_id), "GSEA", item)
            with open(gsea_curated_data_file, "r") as f:
                gsea_curated_plotly_data = json.load(f)

    return JsonResponse({'error': "", "hallmark_report_root": hallmark_report_root, "curated_report_root": curated_report_root, "gsea_curated_plotly_data": gsea_curated_plotly_data}, status=200)

# needs to be changed to support better pagination
# current method will be too memory intensive as it loads everything
def provide_correlation_comparisons(request, analysis_id):
    analysis =  Analysis.objects.filter(sha_hash=str(analysis_id))
    if analysis.exists() is False:
        raise Http404("Analysis Not Found")
    if analysis.first().percentile != 0:
        return JsonResponse({'error': f'{analysis_id} is not a correlation analysis'}, status=500)

    # its better to put items that exist at the front of the table and then return an index indicating
    # the last item that has a plot
    # to enable this solution, we will prepend items that have a plot to the start of the table_items list
    # returning a list of genes with plots can potentially result in a searchtime of O(n^2)
    table_items = []
    last_plot_index = -1
    i = 0

    tsv_comp_file = os.path.join(env('OUTPUT_DIR'), str(analysis_id), "Corr_Analysis", analysis.first().genes_of_interest.all()[0].name + "_corr.tsv")
    correlation_records = pd.read_csv(tsv_comp_file, sep="\t")
    correlation_records = correlation_records.sort_values(by='logExp_Cor', ascending=False)

    cutoff = 0.7 if str(analysis.first().script) == "GDC" else 0.8

    for i in range(0, len(correlation_records)):
        if i == 1000:
            break

        curr_record = correlation_records.iloc[i]

        if curr_record["logExp_Cor"] > cutoff:
            last_plot_index += 1

        # ignore first column (i.e. GOI)
        record = curr_record[1:].tolist()
        table_items.append(record)

    return JsonResponse({'table_items': table_items, "last_plot_index": last_plot_index})

def fetch_high_corr_gene_exprs(request, analysis_id, gene1_id, gene2_id):
    analysis =  Analysis.objects.filter(sha_hash=str(analysis_id))
    if analysis.exists() is False:
        raise Http404("Analysis Not Found")
    if analysis.first().percentile != 0:
        return JsonResponse({'error': f'{analysis_id} is not a correlation analysis'}, status=500)
    
    expr_file = os.path.join(env('OUTPUT_DIR'), str(analysis_id), "Corr_Analysis", analysis.first().genes_of_interest.all()[0].name + "_most_correlated_gene_exprs.tsv")

    expr_df_full = pd.read_csv(expr_file, sep="\t")
    expression_scores = {}

    expr_df = expr_df_full[['Names', gene1_id, gene2_id]]

    if gene1_id == gene2_id:
        expr_df = expr_df_full[['Names', gene1_id]]
    else:
        expr_df = expr_df_full[['Names', gene1_id, gene2_id]]

    # for some reason, pandas is killing most columns, specify how='row' to specify to only to kill the column
    # this is because certain columns mostly have nans, hence kill most rows
    # it is therefore better if we do this function on a column by column basis
    expr_df = expr_df.dropna(subset=expr_df.columns[1:], axis=0, how="any") # nan is not valid in JSON, will cause issues in javascript

    for column in expr_df.columns:
        column_values = list(expr_df[column])
        if column != "Names":
            column_values = [math.log2(x) for x in column_values]

        expression_scores[column] = column_values

    return JsonResponse(expression_scores)

def check_de_finished(request, analysis_id):
    analysis = Analysis.objects.filter(sha_hash=str(analysis_id)).first()

    if analysis is None:
        raise Http404("Analysis Not Found")
    
    if analysis.percentile == 0:
        return JsonResponse({'error': analysis_id + " is not a Differential Expression Analysis."}, status=500)

    # check to see if the GSEA folder exists, if so, then that signals the completion of the DE step
    if os.path.exists(os.path.join(env('OUTPUT_DIR'), str(analysis_id), "GSEA")) is False:
        if analysis.reason_for_failure != "":
            return JsonResponse({'error': 'Analysis Failed. ' + analysis.reason_for_failure}, status=500)
        else:
            return JsonResponse({'completed': False, 'error': ''}, status=200)
        
    return JsonResponse({'completed': True, 'error': ""}, status=200)

# the logic here is that both the DE and Correlation analysis will use this function
# however, the DE will use it to check if the entire analysis (GSEA inclucded) is fully finished,
# instead DE will use another function to check if the DE part has finished.
def check_fully_downloaded(request, analysis_id):
    analysis = Analysis.objects.filter(sha_hash=str(analysis_id)).first()

    if analysis is None:
        raise Http404("Analysis Not Found")

    if analysis.fully_downloaded is False and analysis.reason_for_failure == "":
        return JsonResponse({'completed': False, 'error': ''}, status=200)

    if analysis.reason_for_failure != "":
        return JsonResponse({'error': 'Analysis Failed. ' + analysis.reason_for_failure}, status=500)

    if os.path.exists(env('OUTPUT_DIR') + "/" + str(analysis_id) + ".zip") is False:
        raise Http404("Analysis Not Found")

    return JsonResponse({'completed': True, 'error': ""}, status=200)

# as an extension to this, it might be good to create a directory for all 3 types of scripts, GDC, etc, containing 

def download(request, analysis_id):
    if Analysis.objects.filter(sha_hash=str(analysis_id)).exists() is False:
        raise Http404("Analysis Not Found")
    
    print("Should we show gsea?")
    display_gsea = request.GET.get('display_gsea')  # Defaults to 'false'
    display_gsea = True if display_gsea == "true" else False
    print(type(display_gsea))
    print(display_gsea)

    analysis = Analysis.objects.filter(sha_hash=str(analysis_id)).first()
    analysis_type = "Correlation" if analysis.percentile == 0 else "Differential Expression"
    download_filename = "correlation_" if analysis_type == "Correlation" else "de_"
    # make download filename have a combination of some of the parameters
    download_filename += "_".join([analysis.script.lower(), str(analysis.project).lower()]) + "_"

    gois = []
    for gene in analysis.genes_of_interest.all():
        gois.append(str(gene))

    if analysis.composite_analysis_type == "Single":
        download_filename += gois[0]
    elif analysis.composite_analysis_type == "Additive":
        download_filename += "+".join(gois)
    else:
        download_filename += "/".join(gois)

    download_filename += "_" + str(analysis.percentile) + "%_" + analysis.rna_species if analysis_type == "Differential Expression" else ""
    download_filename += ".zip"

    try:
        if analysis_type == "Differential Expression" and display_gsea is False:
            response = check_de_finished(request, analysis_id)
        else:
            response = check_fully_downloaded(request, analysis_id)
    except:
        raise Http404("Analysis Not Found")

    # should check database as well as if the file exists

    if analysis_type == "Differential Expression" and display_gsea is False:
        analysisOutDir = env('OUTPUT_DIR') + "/" + str(analysis_id) + "_no_gsea.zip"
    else:
        analysisOutDir = env('OUTPUT_DIR') + "/" + str(analysis_id) + ".zip"

    if os.path.exists(analysisOutDir) is False:
        return Http404({f'{analysis_type} Analysis Not Found'})

    # files could be very large, best to serve it in chunks
    def generate_file_chunks(file_path, chunk_size=8192):
        with open(file_path, 'rb') as file:
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    try:
        response = StreamingHttpResponse(generate_file_chunks(analysisOutDir), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename={download_filename}'
        response["Access-Control-Allow-Origin"] = env('WEBSERVER_PORT')
        return response
    except:
        return JsonResponse({'error': f'{analysis_type} Analysis Download Failed'}, status=500)

class GenesAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = Genes.objects.all()

        if self.q:
            qs = qs.filter(name__istartswith=self.q) # i at the start of contains indicates case insensitivity
            # good idea to sort by length of items, with shorter genes being brought up first
            qs = qs.annotate(gene_name_length=Length('name')).order_by('gene_name_length')

        return qs

class ProjectsAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = Projects.objects.all()

        script_type = self.forwarded.get('script_type')
        
        if script_type is None or script_type == "":
            return Projects.objects.none()

        if self.q:
            qs = qs.filter(name__istartswith=self.q)
            # since project names are more complex, we cannot simply filter by only GTEx or GDC
            qs = qs.filter(source=script_type)

        return qs

def display_settings_page(request):
    if request.method == 'POST':
        analysis_form = AnalysisForm(request.POST)

        # if not doing single gene analysis, automatically becomes de_analysis
        # and cannot do single analysis
        if analysis_form.is_valid():
            script_chosen = analysis_form.cleaned_data.get('script_type')
            analysis_script_path = env('GDC_SCRIPT') if script_chosen == "GDC" else \
                                  (env('GTEX_SCRIPT') if script_chosen == "GTEx" else env('RECOUNT_SCRIPT'))

            curr_proj_text = analysis_form.cleaned_data.get('project')
            
            try:
                project_obj = Projects.objects.filter(name=curr_proj_text).first()
                project_str = str(project_obj)
            except:
                raise Http404("Project " + curr_proj_text + " does not exist")

            # GTEx capitalises the first words only, anything after a "_" character is considered a separate word
            # It is different to RECOUNT3 which has the entire string capitalised

            if script_chosen == "GDC":
                project_str = "TCGA-" + project_str
            elif script_chosen == "GTEx":
                project_str = string.capwords(project_str.replace("_", " ")).replace(" ", "_")

            all_gois = analysis_form.cleaned_data.get('gene_selected')
            goi_name_list = []
            for i in range(0, len(all_gois)):
                goi_name_list.append(all_gois[i].name)

            curr_goi_composite_analysis_type = analysis_form.cleaned_data.get('composite_analysis_type')

            if analysis_form.cleaned_data.get('do_de_analysis') == True:
                curr_percentile = analysis_form.cleaned_data.get('percentile')
                curr_rna_species = "mRNA" if analysis_form.cleaned_data.get('use_mirna') is False else "miRNA"
                is_switch_stratum = analysis_form.cleaned_data.get('switch_stratum')
                display_gsea = analysis_form.cleaned_data.get('display_gsea')
            elif analysis_form.cleaned_data.get('do_correlation_analysis') == True:
                # only single genes can submit both types of analysis potentially
                # submit it in a list of commands to execute
                curr_goi_composite_analysis_type = "Single"
                curr_percentile = 0
                curr_rna_species = ""
                is_switch_stratum = False

            command_settings = {
                                    'script': script_chosen, 
                                    'project': project_obj, 
                                    'all_gois': goi_name_list, 
                                    'composite_analysis_type': curr_goi_composite_analysis_type,
                                    'percentile': curr_percentile, 
                                    'rna_species': curr_rna_species,
                                    'switch_stratum': is_switch_stratum,
                                }

            analysis_query = {}

            settings = str(command_settings.values())
            sha_hash = hashlib.sha1(settings.encode("utf-8")).hexdigest()
            filter_obj = Analysis.objects.filter(sha_hash=sha_hash)

            if filter_obj.exists() is True:
                if filter_obj.first().reason_for_failure != "":
                    analysis_form.add_error(None, filter_obj.first().reason_for_failure) # first attribute is field
                    return render(request, 'analysis/submission_page.html', {"analysis_form": analysis_form})
                else:
                    analysis = filter_obj.first()
                    analysis.times_accessed += 1
                    analysis.save()
            else:
                del command_settings['all_gois']
                newAnalysis = Analysis(**command_settings, sha_hash=sha_hash)
                newAnalysis.save()
                for index, goi_obj in enumerate(all_gois):
                    AnalysisGenes.objects.create(gene=goi_obj, analysis=newAnalysis, order=index)
                # cannot pass an object e.g. Project, Genes to the celery app
                # setting the task ID below to be equal to the sha_hash
                submit_command.apply_async((project_str, goi_name_list, curr_goi_composite_analysis_type, curr_percentile, curr_rna_species, is_switch_stratum, sha_hash, analysis_script_path, env('POST_ANALYSIS_SORT_SCRIPT')), queue="script_queue", task_id=sha_hash)

            analysis_query["analysis"] = str(sha_hash)
            # see if you can use context
            analysis_url = reverse('analysis-fetch', kwargs={key: value for (key, value) in analysis_query.items()})
            print(analysis_url)
            if analysis_form.cleaned_data.get('do_de_analysis') == True:
                analysis_url += "?display_gsea=" + str(display_gsea)
            print(analysis_url)
            return redirect(analysis_url)

    else:
        analysis_form = AnalysisForm()

    return render(request, 'analysis/submission_page.html', {"analysis_form": analysis_form})

def fetch(request, analysis):
    filter_obj = Analysis.objects.filter(sha_hash=analysis).first()

    gois = []
    for goi in filter_obj.genes_of_interest.all():
        gois.append(goi.name)

    analysis_info = {
                        'analysis': analysis, 
                        'gois': gois,
                        'script': filter_obj.script,
                        'project': filter_obj.project,
                        'percentile': filter_obj.percentile,
                        'rna_species': filter_obj.rna_species,
                        'is_switch_stratum': filter_obj.switch_stratum,
                        'analysis_type': "DE" if filter_obj.percentile > 0 else "Correlation", 
                        'composite_analysis_type': filter_obj.composite_analysis_type,
                        'expected_time': "1 minute for just the DE part" if filter_obj.percentile > 0 else "5 minutes"
                    }
    
    if filter_obj.percentile != 0:
        display_gsea = request.GET.get('display_gsea')  # Defaults to 'false'
        display_gsea = True if display_gsea == 'True' else False
        analysis_info['display_gsea'] = display_gsea

    return render(request, 'analysis/view_analysis.html', analysis_info)

def home(request):
    return render(request, 'analysis/TRANSECT.html')