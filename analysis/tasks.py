# Create your tasks here

import logging
import os
import subprocess
import shutil
import time
from datetime import timedelta

from analysis.models import Analysis, Genes, Projects
from django.utils import timezone
from transect_web.settings import env

import celery
from celery import shared_task
#from worker import app

def delete_folder(out_path):
    try:
        shutil.rmtree(out_path)
    except:
        pass

def delete_file(file_to_delete):
    try:
        os.remove(file_to_delete)
    except:
        pass

# if composite_analysis_type == "Single" and curr_percentile is not 0, this trigger de_analysis
@shared_task
def submit_command(sha_hash):
    print("Received command")
    selected_analysis = Analysis.objects.filter(sha_hash=sha_hash).first()

    print(selected_analysis.project.source)

    project = selected_analysis.project.name
    if selected_analysis.project.source == "GDC":
        project = "TCGA-" + selected_analysis.project.name

    percentile = selected_analysis.percentile
    rna_species = selected_analysis.rna_species
    is_switch_stratum = selected_analysis.switch_stratum
    composite_analysis_type = selected_analysis.composite_analysis_type
    analysis_script_path = env('GDC_SCRIPT') if selected_analysis.script == "GDC" else \
                      (env('GTEX_SCRIPT') if selected_analysis.script == "GTEx" else env('RECOUNT_SCRIPT'))
    
    all_gois = list(selected_analysis.genes_of_interest.all().values_list("name", flat=True))
    command = analysis_script_path + " -p " + project + " -g "
    # INSPECT! Change gene.split(",") to just gene
    
    # adding different settings based on whether de or correlation, 
    # if correlation, set percentile input and rna_species_to_analyse
    # adjusted also the analysis script to accomodate this
    if selected_analysis.primary_analysis_type == "DE":
        to_add = ""
        if composite_analysis_type == "Single":
            to_add = all_gois[0]
        elif composite_analysis_type == "Additive":
            to_add = "+".join(all_gois)
        elif composite_analysis_type == "Ratio":
            to_add = "%".join(all_gois)
        
        command += to_add
        command += " -e"
        command += " -t " + str(percentile)
        command += " -s " + rna_species
        if is_switch_stratum:
            command += " -S"
        command += " -d"
    else:
        command += all_gois[0]
        command += " -c"

    out_path = os.path.join(env('OUTPUT_DIR'), sha_hash)

    # just a sanity check, to see if path already exists
    # better to just delete and start again it in case there are problems with the old version
    # also delete the zip file
    # under normal circumstances, this is unecessary because this script only gets triggered 
    # when the analysis is not detected in the database
    delete_folder(out_path)
    delete_file(out_path + ".zip")

    os.mkdir(out_path)

    command += " -o " + out_path
    # run the command
    # if the command failed, delete its folder and associated database entry

    logging.info("Executing command: " + command)
    analysis_process = subprocess.Popen(command.split(" "), stderr=subprocess.PIPE)
    stdout, stderr = analysis_process.communicate()

    if analysis_process.returncode != 0:
        logging.error("Command failed with the error code " + str(analysis_process.returncode) + ": " + command)
        logging.error(stderr.decode('utf-8'))
        analysis = Analysis.objects.filter(sha_hash=sha_hash).first()
        analysis.reason_for_failure = "The analysis failed as the submitted command failed."
        if analysis_process.returncode == 2:
            analysis.reason_for_failure = "Insufficient observations in this dataset."
        analysis.save()
        delete_folder(out_path)
        delete_file(out_path + ".zip")
        # if the command failed because there was insufficient data,
        # return that message, otherwise return "analysis failed as 
        # the submitted command failed"
    else:
        logging.info("Command finished successfully: " + command)

        # repositioned this as it makes sense to have this here after everything is complete
        analysis_obj = Analysis.objects.filter(sha_hash=sha_hash).first()
        analysis_obj.fully_downloaded = True
        analysis_obj.save()

# removes analysis (and their folders) that have existed for more than 1 day
# in addition, removes databases without an output directory, vice-versa
# should I add a case that takes into account whether a Analysis object is currently being used
# I plan on executing this everyday at 3am, where it would reasonably be assumed that no one is
# accessing the website (perhaps I can add a render when someone navigates to home, to inform them that this is the case)
# I should also block this function from occurring if there are still active jobs
@shared_task(queue='script_queue')
def clean_database_and_analysis():
    # removes items that were last accessed more than 24 hours ago
    for analysis in Analysis.objects.all():
        time_threshold = timezone.now() - timedelta(hours=24)
        # no need to delete folders individually as we have a signal that handles that
        Analysis.objects.filter(modified__lt=time_threshold).delete()

    # remove databases without an output directory, vice-versa
    # if a database lacks an associated .zip or general output directory then delete it
    # technically I can combine this with the above but I feel like this method is cleaner
    for analysis in Analysis.objects.all():
        out_path = os.path.join(env('OUTPUT_DIR'), analysis.sha_hash)
        if os.path.exists(out_path) is False or os.path.exists(out_path + ".zip") is False:
            logging.info("Removing Analysis: " + analysis.sha_hash + " because it is either missing an output directory or is not inside the Analysis database.")
            analysis.delete()

    # now lets go through the files/folders themselves to see if there are any discrepencies
    # this method works as a "first come first serve" method
    # e.g. if the first item we got was the directory and there was a discrepency, it will
    # delete its corresponding zip file as well and ignore it  
    for item in os.listdir(env('OUTPUT_DIR')):
        sha_hash = item.split(".zip")[0]
        zip_path = os.path.join(env('OUTPUT_DIR'), sha_hash + ".zip")
        gsea_zip_path = delete_file(unzipped_path + "_no_gsea.zip")
        unzipped_path = os.path.join(env('OUTPUT_DIR'), sha_hash)
        
        # simple "catch-all" method without having to write extensive conditional checks
        if Analysis.objects.filter(sha_hash=sha_hash).exists() is False or os.path.exists(zip_path) is False or os.path.exists(unzipped_path) is False or os.path.exists(gsea_zip_path) is False:
            logging.info("Removing Analysis: " + sha_hash + " because it is either missing an output directory/zip file or is not inside the Analysis database.")
            Analysis.objects.filter(sha_hash=sha_hash).delete()
            delete_folder(unzipped_path)
            delete_file(zip_path)
            delete_file(gsea_zip_path)

@celery.signals.task_failure.connect(sender=submit_command)
def task_failure_handler(sender=None, headers=None, body=None, **kwargs):
    if exception := kwargs.get("exception"):
        sha_hash = str(kwargs.get("args")[5])
        analysis = Analysis.objects.filter(sha_hash=sha_hash).first()
        analysis.reason_for_failure = "Unknown Error"
        out_path = os.path.join(env('OUTPUT_DIR'), sha_hash)
        analysis.save()
        delete_folder(out_path)
        delete_file(out_path + ".zip")
        delete_file(out_path + "_no_gsea.zip")
