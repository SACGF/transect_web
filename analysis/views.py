from django.shortcuts import render, redirect
from django.http import Http404, HttpResponse, JsonResponse, FileResponse, StreamingHttpResponse
from django.views.decorators.cache import cache_page
from django.conf import settings
from django.forms.models import model_to_dict
from django.urls.base import reverse
from wsgiref.util import FileWrapper
from dal import autocomplete
from analysis.models import Analysis, Genes, Projects
from analysis.forms import AnalysisForm
from analysis.tasks import add, submit_command
import time
import hashlib
import os
import subprocess

# as an extension to this, it might be good to create a directory for all 3 types of scripts, GDC, etc, containing 

OUTPUT_DIR = "/home/yasir/Desktop/newProj4/outs"
ANALYSIS_SCRIPT_PATH = "/home/yasir/Desktop/newProj4/sRT_new/sRT/bin/GDC_scripts/GDC_TCGA_analyse_GOI.sh"
WEBSERVER_PORT = "http://localhost:8000"

def download(request):
    global OUTPUT_DIR
    global WEBSERVER_PORT

    print("Radio")

    query = request.GET.dict()
    if Analysis.objects.filter(sha_hash=str(query["analysis_id"])).exists() is False:
        raise Http404("Analysis Not Found")

    analysis = Analysis.objects.filter(sha_hash=str(query["analysis_id"])).first()
    analysis_type = "Correlation" if analysis.percentile == 0 else "Differential Expression"
    download_filename = "correlation_analysis.zip" if analysis_type == "Correlation" else "differential_expression_analysis.zip"

    print(analysis.fully_downloaded)

    try:
        while analysis.fully_downloaded is False:
            analysis = Analysis.objects.filter(sha_hash=str(query["analysis_id"])).first()
            print("Deadlock")
            time.sleep(5)
    except:
        return JsonResponse({'error': f'{analysis_type} Analysis Failed'}, status=500)

    if os.path.exists(OUTPUT_DIR + "/" + str(query["analysis_id"]) + ".zip") is False:
        raise Http404("Analysis Not Found")

    print("Something")

    # should check database as well as if the file exists

    analysisOutDir = OUTPUT_DIR + "/" + str(query["analysis_id"]) + ".zip"
    if os.path.exists(analysisOutDir) is False:
        return JsonResponse({'error': f'{analysis_type} Analysis Not Found'}, status=404)

    print("Beginning Download")

    # files could be very large, best to serve it in chunks
    def generate_file_chunks(file_path, chunk_size=8192):
        with open(file_path, 'rb') as file:
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    print("Almost Done")

    try:
        response = StreamingHttpResponse(generate_file_chunks(analysisOutDir), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename={download_filename}'
        response["Access-Control-Allow-Origin"] = WEBSERVER_PORT
        return response
    except:
        return JsonResponse({'error': f'{analysis_type} Analysis Download Failed'}, status=500)

class GenesAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = Genes.objects.all()

        if self.q:
            qs = qs.filter(name__istartswith=self.q)

        return qs

class ProjectsAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = Projects.objects.all()

        print(qs)

        if self.q:
            qs = qs.filter(name__istartswith=self.q)

        return qs

def display_settings_page(request):
    print(request.method)
    if request.method == 'POST':
        print("Hello")
        analysis_form = AnalysisForm(request.POST)

        # if not doing single gene analysis, automatically becomes de_analysis
        # and cannot do single analysis
        if analysis_form.is_valid():
            curr_proj_text = analysis_form.cleaned_data.get('project')
            gene_selected_text = analysis_form.cleaned_data.get('gene_selected_1')
            
            try:
                project_obj = Projects.objects.filter(pk=curr_proj_text).first()
            except:
                raise Http404("Project " + curr_proj_text + " does not exist")

            try:
                curr_goi = Genes.objects.filter(pk=gene_selected_text).first()
            except:
                raise Http404("Gene " + gene_selected_text + " does not exist")

            curr_goi_composite_analysis_type = analysis_form.cleaned_data.get('composite_analysis_type')
            commands_to_process = [] # list of dicts

            if analysis_form.cleaned_data.get('do_de_analysis') == True:
                curr_percentile = analysis_form.cleaned_data.get('percentile')
                curr_rna_species = analysis_form.cleaned_data.get('rna_species')
                commands_to_process.append({'project': project_obj, 'gene': curr_goi, 
                                           'composite_analysis_type': curr_goi_composite_analysis_type,
                                           'percentile': curr_percentile, 'rna_species': curr_rna_species})

            # only single genes can submit both types of analysis potentially
            # submit it in a list of commands to execute
            if analysis_form.cleaned_data.get('do_correlation_analysis') == True:
                curr_goi_composite_analysis_type = "Single"
                curr_percentile = 0
                curr_rna_species = ""
                commands_to_process.append({'project': project_obj, 'gene': curr_goi, 
                           'composite_analysis_type': curr_goi_composite_analysis_type,
                           'percentile': curr_percentile, 'rna_species': curr_rna_species})

            analysis_query = ""

            for command_settings in commands_to_process:
                print(command_settings)
                print(Analysis.objects.all())
                filter_obj = Analysis.objects.filter(**command_settings)
                settings = str(command_settings.values())
                sha_hash = hashlib.sha1(settings.encode("utf-8")).hexdigest()
                
                if filter_obj.exists() is True:
                    analysis = filter_obj.first()
                    analysis.times_accessed += 1
                    analysis.save()
                else:
                    print("OBJ Does not Exist")
                    newAnalysis = Analysis(**command_settings, sha_hash=sha_hash)
                    newAnalysis.save()
                    # submit_command.apply_async((**command_settings, sha_hash=sha_hash, outdir=OUTPUT_DIR, analysis_script_path=ANALYSIS_SCRIPT_PATH), queue="script_queue")
                    # print(submit_command.backend)
                    # cannot pass an object e.g. Project, Genes to the celery app
                    submit_command.apply_async((str(project_obj), str(curr_goi), curr_goi_composite_analysis_type, curr_percentile, curr_rna_species, sha_hash, OUTPUT_DIR, ANALYSIS_SCRIPT_PATH), queue="script_queue")
                
                if analysis_query == "":
                    analysis_query = "?analysis=" + str(sha_hash)
                else:
                    analysis_query += "&analysis=" + str(sha_hash)
            
            #return redirect(reverse('analysis-fetch'), kwargs=analysis_query)
            print(analysis_query)
            return redirect(reverse('analysis-fetch') + analysis_query)

    else:
        analysis_form = AnalysisForm()
        return render(request, 'analysis/submission_page.html', {"analysis_form": analysis_form})

#def fetch(request, analysis, analysis2 = None):
def fetch(request):
    query = request.GET.dict()
    analysis_ids = {'analysis': query["analysis"]}
    if "analysis2" in query.keys():
        analysis_ids['analysis2'] = query["analysis2"]
    return render(request, 'analysis/view_analysis.html', analysis_ids)

def test(requests):
    add.delay(2, 2)
    return HttpResponse("Here's the text of the web page.")