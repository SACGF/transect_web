from django.shortcuts import render, redirect
from django.http import Http404, HttpResponse, JsonResponse, FileResponse, StreamingHttpResponse
from django.views.decorators.cache import cache_page
from django.conf import settings
from django.forms.models import model_to_dict
from django.urls.base import reverse
from django.core.exceptions import ValidationError
from django.db.models.functions import Length
from wsgiref.util import FileWrapper
from celery.result import AsyncResult
from dal import autocomplete, forward
from analysis.models import Analysis, Genes, Projects
from analysis.forms import AnalysisForm
from analysis.tasks import submit_command
import time
import hashlib
import os
import string
from sRT_backend.settings import env

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
    GSEA_summary = os.path.join(GSEA_path, "-".join(gois) + "_Strat_Vs_Curated.csv")
    if os.path.exists(GSEA_path) is False or os.path.exists(GSEA_summary) is False:
        return JsonResponse({'error': f'{analysis_id} does not contain sufficient data '}, status=500)

    x = []
    y = []
    with open(GSEA_summary, "r") as f:
        next(f)
        for line in f:
            curr = line.strip().split(",")
            y.append(curr[0])
            x.append(float(curr[4]))

    hallmark_report_root = ""
    curated_report_root = ""

    # now lets fetch the reports
    for item in os.listdir(os.path.join(env('OUTPUT_DIR'), str(analysis_id), "GSEA")):
        if "Strat_Vs_Curated.GseaPreranked" in item:
            curated_report_root = item
        elif "Strat_Vs_Hallmark.GseaPreranked" in item:
            hallmark_report_root = item

    return JsonResponse({'error': "", "x": x, "y": y, "hallmark_report_root": hallmark_report_root, "curated_report_root": curated_report_root}, status=200)

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

    # pushing items with a plot at the front
    # plot should be sorted by record 5 (logExp_FDR)
    # either way, add only the items with a plot first
    # checking if path exists will negate the need for us to check a certain
    # value which may present design problems in the future
    tsv_comp_file = os.path.join(env('OUTPUT_DIR'), str(analysis_id), "Corr_Analysis", analysis.first().genes_of_interest.all()[0].name + "_corr.tsv")

    with open(tsv_comp_file, "r") as f:
        next(f)
        for line in f:
            if i == 1000:
                break

            record = line.replace("\"", "").strip().split("\t")
            if os.path.exists(os.path.join(env('OUTPUT_DIR'), str(analysis_id), "Corr_Analysis", "plots", record[0] + "_" + record[1] + ".png")) is True:
                last_plot_index += 1
                table_items.append(record[1:])
                i += 1
    
    with open(tsv_comp_file, "r") as f:
        next(f)
        for line in f:
            if i == 1000:
                break

            record = line.replace("\"", "").strip().split("\t")
            if os.path.exists(os.path.join(env('OUTPUT_DIR'), str(analysis_id), "Corr_Analysis", "plots", record[0] + "_" + record[1] + ".png")) is False:
                table_items.append(record[1:])
                i += 1

    return JsonResponse({'table_items': table_items, "last_plot_index": last_plot_index})

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
        response = check_fully_downloaded(request, analysis_id)
    except:
        raise Http404("Analysis Not Found")

    # should check database as well as if the file exists

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

            if script_type == "GDC" or script_type == "GTEx":
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
                project_obj = Projects.objects.filter(pk=curr_proj_text).first()
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
                curr_rna_species = analysis_form.cleaned_data.get('rna_species')
            elif analysis_form.cleaned_data.get('do_correlation_analysis') == True:
                # only single genes can submit both types of analysis potentially
                # submit it in a list of commands to execute
                curr_goi_composite_analysis_type = "Single"
                curr_percentile = 0
                curr_rna_species = ""

            command_settings = {
                                    'script': script_chosen, 
                                    'project': project_obj, 
                                    'all_gois': goi_name_list, 
                                    'composite_analysis_type': curr_goi_composite_analysis_type,
                                    'percentile': curr_percentile, 
                                    'rna_species': curr_rna_species
                                }

            analysis_query = {}

            settings = str(command_settings.values())
            sha_hash = hashlib.sha1(settings.encode("utf-8")).hexdigest()
            filter_obj = Analysis.objects.filter(sha_hash=sha_hash)

            if filter_obj.exists() is True and filter_obj.first().fully_downloaded == True:
                analysis = filter_obj.first()
                analysis.times_accessed += 1
                analysis.save()
            else:
                # cannot pass an object e.g. Project, Genes to the celery app
                if filter_obj.exists() is False:
                    del command_settings['all_gois']
                    newAnalysis = Analysis(**command_settings, sha_hash=sha_hash)
                    newAnalysis.save()
                    newAnalysis.genes_of_interest.set(all_gois)
                    newAnalysis.save()
                else:
                    analysis_form.add_error(None, filter_obj.first().reason_for_failure) # first attribute is field
                    return render(request, 'analysis/submission_page.html', {"analysis_form": analysis_form})

                # setting the task ID below to be equal to the sha_hash
                submit_command.apply_async((project_str, goi_name_list, curr_goi_composite_analysis_type, curr_percentile, curr_rna_species, sha_hash, analysis_script_path), queue="script_queue", task_id=sha_hash)
            
            analysis_query["analysis"] = str(sha_hash)
            analysis_url = reverse('analysis-fetch', kwargs={key: value for (key, value) in analysis_query.items()})
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
                        'analysis_type': "DE" if filter_obj.percentile > 0 else "Correlation", 
                        'composite_analysis_type': filter_obj.composite_analysis_type
                    }

    return render(request, 'analysis/view_analysis.html', analysis_info)
