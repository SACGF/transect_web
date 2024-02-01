from django.db import models

class Genes(models.Model):
    name = models.TextField(primary_key=True)

    def __str__(self):
        return self.name 

class Projects(models.Model):
    name = models.TextField(primary_key=True)

    def __str__(self):
        return self.name

class Analysis(models.Model): # change name to analysis
    sha_hash = models.TextField(primary_key=True)
    project = models.ForeignKey(Projects, on_delete=models.CASCADE)
    gene = models.ForeignKey(Genes, on_delete=models.CASCADE)
    composite_analysis_type = models.CharField(max_length=100)
    percentile = models.PositiveIntegerField()
    rna_species = models.CharField(max_length=100)

    fully_downloaded = models.BooleanField(default=False)
    times_accessed = models.PositiveIntegerField(default=0) # may be useful
    # last_accessed
    date_posted = models.DateTimeField(auto_now_add=True)  # auto_now_add automatically sets when the record was created

    # read this: https://docs.djangoproject.com/en/5.0/ref/models/options/
    # also provides details on options, including unique_together
    class Meta:
        # This ensures that there can only be 1 record that has the same values below
        # You could thus use get_or_create to retrieve exisitng/create new, and there will be guaranteed no dupes
        unique_together = ('project', 'gene', 'composite_analysis_type', 'percentile', 'rna_species')
