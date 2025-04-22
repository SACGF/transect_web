from django.shortcuts import render, redirect, get_object_or_404
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
import logging
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

def view_manual(request):
    return render(request, 'analysis/TRANSECT_manual.html')

# also fetches root folder name of the GSEA curated/hallmark reports
# this is because these folders contains a number at the end
# that appears to be procedurally generated
def FetchGseaSummary(request, analysis_id):
    analysis = get_object_or_404(Analysis, sha_hash=str(analysis_id))

    if analysis.primary_analysis_type == "Correlation":
        return JsonResponse({'error': f'{analysis_id} is not a DE analysis'}, status=500)

    gois = list(analysis.genes_of_interest.all().values_list("name", flat=True))

    GSEA_path = os.path.join(env('OUTPUT_DIR'), str(analysis_id), "GSEA")

    rna_species = analysis.rna_species
    
    if rna_species == "mRNA":
        GSEA_summary = os.path.join(GSEA_path, "-".join(gois) + "_Strat_Vs_Curated.html")
        if os.path.exists(GSEA_path) is False or os.path.exists(GSEA_summary) is False:
            return JsonResponse({'error': f'{analysis_id} does not contain sufficient data '}, status=500)

    gsea_response = {}
    gsea_response["error"] = ""

    # now lets fetch the reports
    for item in os.listdir(os.path.join(env('OUTPUT_DIR'), str(analysis_id), "GSEA")):
        if rna_species == "mRNA":
            if "Strat_Vs_Curated.GseaPreranked" in item:
                gsea_response["curated_report_root"] = item
            elif "Strat_Vs_Hallmark.GseaPreranked" in item:
                gsea_response["hallmark_report_root"] = item
            elif "Strat_Vs_Curated.json" in item:
                gsea_curated_data_file = os.path.join(env('OUTPUT_DIR'), str(analysis_id), "GSEA", item)
                with open(gsea_curated_data_file, "r") as f:
                    gsea_plotly_data = json.load(f)
                    gsea_response["gsea_plotly_data"] = gsea_plotly_data
        elif rna_species == "miRNA":
            if "Strat_Vs_Inhouse-TargetScan.GseaPreranked" in item:
                gsea_response["inhouse_targetscan_report_root"] = item
            elif "Strat_Vs_Inhouse-TargetScan.json" in item:
                gsea_inhouse_data_file = os.path.join(env('OUTPUT_DIR'), str(analysis_id), "GSEA", item)
                with open(gsea_inhouse_data_file, "r") as f:
                    gsea_plotly_data = json.load(f)
                    gsea_response["gsea_plotly_data"] = gsea_plotly_data

    # better to check if nothing was found in the GSEA folder
    if rna_species == "miRNA" and len(gsea_response.keys()) == 1:
        return JsonResponse({'error': f'{analysis_id} does not contain sufficient data '}, status=500)

    return JsonResponse(gsea_response, status=200)

# needs to be changed to support better pagination
# current method will be too memory intensive as it loads everything
def provide_correlation_comparisons(request, analysis_id):
    analysis = get_object_or_404(Analysis, sha_hash=str(analysis_id))
    if analysis.primary_analysis_type != "Correlation":
        return JsonResponse({'error': f'{analysis_id} is not a correlation analysis'}, status=500)
    
    # its better to put items that exist at the front of the table and then return an index indicating
    # the last item that has a plot
    # to enable this solution, we will prepend items that have a plot to the start of the table_items list
    # returning a list of genes with plots can potentially result in a searchtime of O(n^2)
    table_items = []
    last_plot_index = -1
    i = 0

    tsv_comp_file = os.path.join(env('OUTPUT_DIR'), str(analysis_id), "Corr_Analysis", analysis.genes_of_interest.all()[0].name + "_corr.tsv")
    correlation_records = pd.read_csv(tsv_comp_file, sep="\t")
    correlation_records = correlation_records.sort_values(by='logExp_Cor', ascending=False)

    correlation_cutoff = 0.8

    MAX_CORR_RECORDS = 1000

    for i in range(0, len(correlation_records)):
        if i == MAX_CORR_RECORDS:
            break

        curr_record = correlation_records.iloc[i]

        if curr_record["logExp_Cor"] > correlation_cutoff:
            last_plot_index += 1

        # ignore first column (i.e. GOI)
        record = curr_record[1:].tolist()
        table_items.append(record)

    return JsonResponse({'table_items': table_items, "last_plot_index": last_plot_index})

def fetch_high_corr_gene_exprs(request, analysis_id, gene1_id, gene2_id):
    analysis = get_object_or_404(Analysis, sha_hash=str(analysis_id))
    if analysis.primary_analysis_type != "Correlation":
        return JsonResponse({'error': f'{analysis_id} is not a correlation analysis'}, status=500)
    
    expr_file = os.path.join(env('OUTPUT_DIR'), str(analysis_id), "Corr_Analysis", analysis.genes_of_interest.all()[0].name + "_most_correlated_gene_exprs.tsv")

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

def get_webgestalt_plots(request, analysis_id):
    analysis = get_object_or_404(Analysis, sha_hash=str(analysis_id))
    if analysis.primary_analysis_type == "Correlation":
        return JsonResponse({'error': analysis_id + " is not a Differential Expression Analysis."}, status=500)

    webgestalt_plots_to_display = []
    for webgestalt_plot in ["GO_UP_Reg", "GO_DOWN_Reg", "DS_UP_Reg", "DS_DOWN_Reg", "PW_UP_Reg", "PW_DOWN_Reg"]:
        if os.path.exists(os.path.join(env('OUTPUT_DIR'), str(analysis_id), "DE_Analysis", "WebGestalt", "Project_enrichDatabase" + webgestalt_plot, "Summary_enrichDatabase" + webgestalt_plot + ".html")):
            webgestalt_plots_to_display.append(webgestalt_plot)

    return JsonResponse({'webgestalt_plots_to_display': webgestalt_plots_to_display}, status=200)

def check_de_finished(request, analysis_id):
    analysis = get_object_or_404(Analysis, sha_hash=str(analysis_id))
    if analysis.primary_analysis_type == "Correlation":
        return JsonResponse({'error': analysis_id + " is not a Differential Expression Analysis."}, status=500)

    # check to see if the _no_gsea folder exists, if so, then that signals the completion of the DE step
    # potentially also check if the GSEA folder also doesn't exist, if it doesn't after the gsea
    # step is initiated, return "GSEA failed"
    if os.path.exists(os.path.join(env('OUTPUT_DIR'), str(analysis_id) + "_no_gsea.zip")) is False:
        if analysis.reason_for_failure != "":
            return JsonResponse({'error': 'Analysis Failed. ' + analysis.reason_for_failure}, status=500)
        else:
            return JsonResponse({'completed': False, 'error': ''}, status=200)
        
    return JsonResponse({'completed': True, 'error': ""}, status=200)

# the logic here is that both the DE and Correlation analysis will use this function
# however, the DE will use it to check if the entire analysis (GSEA inclucded) is fully finished,
# instead DE will use another function to check if the DE part has finished.
def check_fully_downloaded(request, analysis_id):
    analysis = get_object_or_404(Analysis, sha_hash=str(analysis_id))
    if analysis.fully_downloaded is False and analysis.reason_for_failure == "":
        return JsonResponse({'completed': False, 'error': ''}, status=200)

    if analysis.reason_for_failure != "":
        return JsonResponse({'error': 'Analysis Failed. ' + analysis.reason_for_failure}, status=500)

    if os.path.exists(env('OUTPUT_DIR') + "/" + str(analysis_id) + ".zip") is False:
        raise Http404("Analysis Not Found")

    return JsonResponse({'completed': True, 'error': ""}, status=200)

# as an extension to this, it might be good to create a directory for all 3 types of scripts, GDC, etc, containing 

def download(request, analysis_id):
    analysis = get_object_or_404(Analysis, sha_hash=str(analysis_id))
    
    display_gsea = request.GET.get('display_gsea')  # Defaults to 'false'
    display_gsea = display_gsea == "true"

    analysis_type = "Correlation" if analysis.primary_analysis_type == "Correlation" else "Differential Expression"
    download_filename = "correlation_" if analysis_type == "Correlation" else "de_"
    # make download filename have a combination of some of the parameters
    download_filename += "_".join([analysis.script.lower(), str(analysis.project).lower()]) + "_"

    gois = list(analysis.genes_of_interest.all().values_list("name", flat=True))

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
        script_type = self.forwarded.get('script_type')
        use_mirna = self.forwarded.get('use_mirna')

        if script_type == "GDC" and use_mirna is True: # safety check, though it should be impossible to check use_mirna if you have not selected GDC
            qs = Genes.objects.filter(name__istartswith="hsa-")
        else:
            qs = Genes.objects.exclude(name__istartswith="hsa-")

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
            # finally, if GDC, filter depending on whether miRNA selected or not

        return qs

def display_settings_page(request):
    if request.method == 'POST':
        analysis_form = AnalysisForm(request.POST)

        # if not doing single gene analysis, automatically becomes de_analysis
        # and cannot do single analysis
        if analysis_form.is_valid():
            script_chosen = analysis_form.cleaned_data.get('script_type')

            curr_proj_text = analysis_form.cleaned_data.get('project')
            
            try:
                project_obj = Projects.objects.filter(name=curr_proj_text, source=script_chosen).first()
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
            goi_name_list = [g.name for g in all_gois]

            curr_goi_composite_analysis_type = analysis_form.cleaned_data.get('composite_analysis_type')

            primary_analysis_type = "Correlation" if analysis_form.cleaned_data.get('do_correlation_analysis') is True else "DE"

            if primary_analysis_type == "DE":
                curr_percentile = analysis_form.cleaned_data.get('percentile')
                curr_rna_species = "mRNA" if analysis_form.cleaned_data.get('use_mirna') is False else "miRNA"
                is_switch_stratum = analysis_form.cleaned_data.get('switch_stratum')
                display_gsea = analysis_form.cleaned_data.get('display_gsea')
            elif primary_analysis_type == "Correlation":
                # only single genes can submit both types of analysis potentially
                # submit it in a list of commands to execute
                curr_goi_composite_analysis_type = "Single"
                curr_percentile = 0
                curr_rna_species = ""
                is_switch_stratum = False

            command_settings = {
                                    'primary_analysis_type': primary_analysis_type,
                                    'script': script_chosen, 
                                    'project': project_obj, 
                                    'all_gois': goi_name_list, 
                                    'composite_analysis_type': curr_goi_composite_analysis_type,
                                    'percentile': curr_percentile, 
                                    'rna_species': curr_rna_species,
                                    'switch_stratum': is_switch_stratum,
                                }

            settings = str(command_settings.values())
            sha_hash = hashlib.sha1(settings.encode("utf-8")).hexdigest()

            del command_settings['all_gois']
            newAnalysis, created = Analysis.objects.get_or_create(sha_hash=sha_hash, defaults=command_settings)

            if not created:
                if newAnalysis.reason_for_failure != "":
                    # when re-rendering the gene_selected field, the page appears to rearrange
                    # the gene positions to be alphabetical (not sure why), 
                    # as a simple fix, delete the gois 
                    post_data = request.POST.copy()
                    post_data.setlist('gene_selected', [])  # Clear selected options
                    analysis_form = AnalysisForm(post_data)  # Re-create the form with modified data

                    # doing the above will add the "This Field is Required" error, since it will be empty,
                    # need to delete it
                    # also put my custom error after because the error above will overwrite it
                    del analysis_form.errors['gene_selected']
                    analysis_form.add_error(None, newAnalysis.reason_for_failure) # first attribute is field
                    return render(request, 'analysis/submission_page.html', {"analysis_form": analysis_form})
                else:
                    newAnalysis.times_accessed += 1
                    newAnalysis.save()
            else:
                newAnalysis.save()
                for index, goi_obj in enumerate(all_gois):
                    AnalysisGenes.objects.create(gene=goi_obj, analysis=newAnalysis, order=index)
                print(type(sha_hash))
                submit_command.apply_async((sha_hash,), queue="script_queue", task_id=sha_hash)

            analysis_query = {}
            analysis_query["analysis"] = str(sha_hash)
            analysis_url = reverse('analysis-fetch', kwargs=analysis_query)
            if primary_analysis_type == "DE":
                analysis_url += "?display_gsea=" + str(display_gsea)
            return redirect(analysis_url)

    else:
        analysis_form = AnalysisForm()

    return render(request, 'analysis/submission_page.html', {"analysis_form": analysis_form})

def fetch(request, analysis):
    filter_obj = get_object_or_404(Analysis, sha_hash=str(analysis))

    logger = logging.getLogger("django")
    logger.info("Fetching analysis: " + analysis)
    
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
                        'analysis_type': filter_obj.primary_analysis_type, 
                        'composite_analysis_type': filter_obj.composite_analysis_type,
                        'expected_time': "3 minutes for just the DE part" if filter_obj.primary_analysis_type == "DE" else "5 minutes"
                    }
    
    if filter_obj.primary_analysis_type != "Correlation":
        display_gsea = request.GET.get('display_gsea')  # Defaults to 'false'
        display_gsea = True if display_gsea == 'True' else False
        analysis_info['display_gsea'] = display_gsea

    return render(request, 'analysis/view_analysis.html', analysis_info)

def home(request):
    return render(request, 'analysis/TRANSECT.html')