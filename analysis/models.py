from django.db import models
import datetime

class Genes(models.Model):
    name = models.TextField(primary_key=True)

    def __str__(self):
        return self.name 

class Projects(models.Model):
    name = models.TextField()
    source = models.TextField() # study source, either TCGA or GTEx
    id = models.AutoField(primary_key=True)
    
    class Meta:
        unique_together = ('name', 'source')

    def __str__(self):
        return self.name
    

# TimestampedModel <- automatically adds created and modified
class Analysis(models.Model): # change name to analysis
    sha_hash = models.TextField(primary_key=True)
    script = models.TextField(default="GDC")
    project = models.ForeignKey(Projects, on_delete=models.CASCADE)
    genes_of_interest = models.ManyToManyField(Genes, through="AnalysisGenes")
    composite_analysis_type = models.TextField()
    percentile = models.PositiveIntegerField()
    rna_species = models.TextField()

    reason_for_failure = models.TextField(default="")
    fully_downloaded = models.BooleanField(default=False) # if this becomes None, then the download has failed
    times_accessed = models.PositiveIntegerField(default=0) # may be useful
    date_posted = models.DateTimeField(auto_now_add=True)  # auto_now_add automatically sets when the record was created
    last_accessed = models.DateTimeField(auto_now=True) 

    # read this: https://docs.djangoproject.com/en/5.0/ref/models/options/
    # also provides details on options, including unique_together
    #class Meta:
    #    # This ensures that there can only be 1 record that has the same values below
    #    # You could thus use get_or_create to retrieve exisitng/create new, and there will be guaranteed no dupes
    #    unique_together = ('script', 'project', 'genes_of_interest', 'composite_analysis_type', 'percentile', 'rna_species')

class AnalysisGenes(models.Model):
    gene = models.ForeignKey(Genes, on_delete=models.CASCADE)
    analysis = models.ForeignKey(Analysis, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order']