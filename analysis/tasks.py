# Create your tasks here

import os
import subprocess
import shutil

from analysis.models import Analysis, Genes, Projects
from django.utils import timezone
from sRT_backend.settings import env

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
def submit_command(project, all_gois, composite_analysis_type, percentile, rna_species, sha_hash, analysis_script_path):
    print("Hello submit command")
    command = analysis_script_path + " -p " + project + " -g "
    # INSPECT! Change gene.split(",") to just gene
    
    # adding different settings based on whether de or correlation, 
    # if correlation, set percentile input and rna_species_to_analyse
    # adjusted also the analysis script to accomodate this
    if percentile != 0:
        to_add = ""
        if composite_analysis_type == "Single":
            to_add = all_gois[0]
        elif composite_analysis_type == "Multi":
            to_add = "+".join(all_gois)
        elif composite_analysis_type == "Ratio":
            to_add = "%".join(all_gois)
        
        command += to_add
        print(command)
        command += " -t " + str(percentile)
        print("Hello tasks")
        command += " -s " + rna_species
        command += " -d "
    else:
        command += all_gois[0]
        command += " -c "

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

    completed_process = subprocess.run(command, shell=True)

    print("TASK CHECKPOINT")
    print(completed_process.returncode)

    if completed_process.returncode != 0:
        print("TF CHECKPOINT 1")
        analysis = Analysis.objects.filter(sha_hash=sha_hash).first()
        analysis.reason_for_failure = "The analysis failed as the submitted command failed."
        if completed_process.returncode == 2:
            analysis.reason_for_failure = "Insufficient observations in this dataset."
        analysis.save()
        delete_folder(out_path)
        delete_file(out_path + ".zip")
        print("TF CHECKPOINT 2")
        # if the command failed because there was insufficient data,
        # return that message, otherwise return "analysis failed as 
        # the submitted command failed"
    else:
        analysis_obj = Analysis.objects.filter(sha_hash=sha_hash).first()
        analysis_obj.fully_downloaded = True
        analysis_obj.save()
        shutil.make_archive(out_path, 'zip', out_path) # finally zip the command

# removes analysis (and their folders) that have existed for more than 1 day
# in addition, removes databases without an output directory, vice-versa
# should I add a case that takes into account whether a Analysis object is currently being used
# I plan on executing this everyday at 3am, where it would reasonably be assumed that no one is
# accessing the website (perhaps I can add a render when someone navigates to home, to inform them that this is the case)
# I should also block this function from occurring if there are still active jobs
@shared_task(queue='script_queue')
def clean_database_and_analysis():
    print("\n\n")
    print("PERFORMING DATABASE CLEANUP")
    print("\n\n")
    # removes items that were last accessed more than 24 hours ago
    for analysis in Analysis.objects.all():
        #analysis.last_accessed timezone.localtime()
        difference = timezone.localtime() - analysis.last_accessed.astimezone(timezone.get_current_timezone())
        if difference.days > 1: # dates are more than 24 hours apart from each other, can use difference.minutes, etc
        #if difference.seconds > 600:
            out_path = os.path.join(env('OUTPUT_DIR'), analysis.sha_hash)
            analysis.delete()
            delete_folder(out_path)
            delete_file(out_path + ".zip")

    # remove databases without an output directory, vice-versa
    # if a database lacks an associated .zip or general output directory then delete it
    # technically I can combine this with the above but I feel like this method is cleaner
    for analysis in Analysis.objects.all():
        out_path = os.path.join(env('OUTPUT_DIR'), analysis.sha_hash)
        if os.path.exists(out_path) is False or os.path.exists(out_path + ".zip") is False:
            analysis.delete()
            delete_folder(out_path)
            delete_file(out_path + ".zip")

    # now lets go through the files/folders themselves to see if there are any discrepencies
    # this method works as a "first come first serve" method
    # e.g. if the first item we got was the directory and there was a discrepency, it will
    # delete its corresponding zip file as well and ignore it  
    for item in os.listdir(env('OUTPUT_DIR')):
        sha_hash = item.split(".zip")[0]
        zip_path = os.path.join(env('OUTPUT_DIR'), sha_hash + ".zip")
        unzipped_path = os.path.join(env('OUTPUT_DIR'), sha_hash)
        
        # simple "catch-all" method without having to write extensive conditional checks
        if Analysis.objects.filter(sha_hash=sha_hash).exists() is False \
           or os.path.exists(zip_path) is False \
           or os.path.exists(unzipped_path) is False:
            if Analysis.objects.filter(sha_hash=sha_hash).exists():
                Analysis.objects.filter(sha_hash=sha_hash).first().delete()
            delete_folder(unzipped_path)
            delete_file(zip_path)

@celery.signals.task_failure.connect(sender=submit_command)
def task_failure_handler(sender=None, headers=None, body=None, **kwargs):
    if exception := kwargs.get("exception"):
        print("Command Failed: ", kwargs.get("args"))
        sha_hash = str(kwargs.get("args")[5])
        analysis = Analysis.objects.filter(sha_hash=sha_hash).first()
        analysis.fully_downloaded = None
        analysis.reason_for_failure = "Unknown Error"
        out_path = os.path.join(env('OUTPUT_DIR'), sha_hash)
        delete_folder(out_path)
        delete_file(out_path + ".zip")
