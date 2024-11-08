from django.db import models
from model_utils.models import TimeStampedModel
import datetime

class Genes(models.Model):
    name = models.TextField(primary_key=True)

    def __str__(self):
        return self.name 

class Projects(models.Model):
    name = models.TextField()
    source = models.TextField() # study source, either TCGA or GTEx
    id = models.TextField(primary_key=True)
    is_tcga = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Combine field1 and field2 to generate a unique id
        # this will make it easier to search for in DAL
        self.id = f"{self.name}_{self.source}"
        super(Projects, self).save(*args, **kwargs)
    
    class Meta:
        unique_together = ('name', 'source')

    def __str__(self):
        return self.name
    

# TimestampedModel <- automatically adds created and modified
class Analysis(TimeStampedModel):
    sha_hash = models.TextField(primary_key=True)
    primary_analysis_type = models.TextField(choices={
        "Correlation": "Correlation", 
        "DE": "Differential Expression"
        })
    script = models.TextField(default="GDC")
    project = models.ForeignKey(Projects, on_delete=models.CASCADE)
    genes_of_interest = models.ManyToManyField(Genes, through="AnalysisGenes")
    composite_analysis_type = models.TextField()
    percentile = models.PositiveIntegerField()
    rna_species = models.TextField()
    switch_stratum = models.BooleanField(default=False)

    reason_for_failure = models.TextField(default="")
    fully_downloaded = models.BooleanField(default=False) # if this becomes None, then the download has failed
    times_accessed = models.PositiveIntegerField(default=0) # may be useful

class AnalysisGenes(models.Model):
    gene = models.ForeignKey(Genes, on_delete=models.CASCADE)
    analysis = models.ForeignKey(Analysis, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order']