# Create your tasks here

import os
import subprocess
import shutil

from analysis.models import Analysis, Genes, Projects

from celery import shared_task

# if composite_analysis_type == "Single" and curr_percentile is not 0, this trigger de_analysis
@shared_task
def submit_command(project, gene, composite_analysis_type, percentile, rna_species, sha_hash, outdir, analysis_script_path):
    command = analysis_script_path + " -p " + project + " -g "
    all_gois = gene.split(",")
    
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
        command += " -t " + percentile
        command += " -s " + rna_species
        command += " -d "
    else:
        command += all_gois[0]
        command += " -c "

    out_path = os.path.join(outdir, sha_hash)
    os.mkdir(out_path)

    command += " -o " + out_path
    # run the command
    # if the command failed, delete its folder and associated database entry
    completed_process = subprocess.run(command, shell=True)
    if completed_process.returncode != 0:
        Analysis.objects.filter(sha_hash=sha_hash).first().delete()
        try:
            shutil.rmtree(path)
        except:
            pass
    else:
        analysis_obj = Analysis.objects.filter(sha_hash=sha_hash).first()
        analysis_obj.fully_downloaded = True
        analysis_obj.save()
        shutil.make_archive(out_path, 'zip', out_path) # finally zip the command

@shared_task
def add(x, y):
    print(x + y)
    time.sleep(10)
    return x + y