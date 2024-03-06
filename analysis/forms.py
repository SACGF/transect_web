from django import forms
from analysis.models import Analysis, Genes, Projects
from django.core.validators import MaxValueValidator, MinValueValidator
from dal import autocomplete, forward

class AnalysisForm(forms.Form):
    def __init__(self, *args, **kwargs):
       super().__init__(*args, **kwargs)
       self.label_suffix = ""  # Removes : as label suffix

    class Meta:
       model = Analysis
       fields = ['script', 'project', 'genes_of_interest', 'composite_analysis_type', 'percentile', 'rna_species']

    script_type = forms.ChoiceField(choices=[('', ' -- select an option -- '), 
                                                           ("GDC", "GDC"), 
                                                           ("GTEx", "GTEx"),
                                                           ("RECOUNT3", "RECOUNT3")],
                                                    required=True,
                                                    widget=forms.Select(
                                                           attrs={'id': 'script_choice', 
                                                                  'class': "form-select mt-3", 
                                                                  'empty_label': " -- select an option -- ",
                                                                  'data-toggle': "popover",
                                                                  'data-placement': "top", 
                                                                  'data-trigger': "hover",
                                                                  'data-content': "Choose the analysis script" 
                                                                  }))

    project = forms.ModelChoiceField(queryset=Projects.objects.all(),
                                         required=True,
                                         widget=autocomplete.ModelSelect2(url='projects-autocomplete',
                                                                          forward=(forward.Const("GDC", 'script_typez'), ),  
                                                                          # accessing script field as well, allowing us to filter based on that as well
                                                                          attrs={'data-placeholder': 'Projects ...',
                                                                                 'data-minimum-input-length': 1.,
                                                                                 "id": "project_choice",
                                                                                 },
                                                                         )
                                   )

    gene_selected = forms.ModelMultipleChoiceField(queryset=Genes.objects.all(),
                                         required=True,
                                         widget=autocomplete.ModelSelect2Multiple(url='genes-autocomplete',
                                                             attrs={'data-placeholder': 'Genes ...',
                                                                    'data-minimum-input-length': 3,
                                                                    'id': 'gene_selected', 
                                                                    'class': 'mt-3'
                                                                    }))

    composite_analysis_type = forms.ChoiceField(choices=[("Single", "Single"),
                                                         ("Multi", "Multi"),
                                                         ("Ratio", "Ratio")],
                                                        initial= "Single",
                                                        widget=forms.Select(
                                                               attrs={'id': 'composite_analysis_choice', 
                                                                      'class': "form-select mt-3", 
                                                                      # 'empty_label': " -- select an option -- ",
                                                                      'data-toggle': "popover",
                                                                      'data-placement': "top", 
                                                                      'data-trigger': "hover",
                                                                      'data-content': "Choose if you want to do a single-analysis on a gene " + \
                                                                                      "or a mutli/ratio analysis on a group of genes. Note that " + \
                                                                                      "you cannot do a correlation analysis if you select either Ratio or Multi."
                                                                      }))

    do_correlation_analysis = forms.BooleanField(required=False,
                                                 label="Correlation Analysis",
                                                 widget=forms.CheckboxInput(attrs={'id': 'correlation_checkbox', 'class': "validate-checkbox"}))
    
    do_de_analysis = forms.BooleanField(required=False,
                                          label="Differential Expression Analysis",
                                          widget=forms.CheckboxInput(attrs={'id': 'de_checkbox', 'class': "validate-checkbox"}))

    percentile = forms.IntegerField(required=False,
                                   label="This program will compare the expressions of " + \
                                         "samples with a gene expression less than the percentile with the expression " + \
                                         "of samples greater than 100 - percentile.",
                                   widget=forms.NumberInput(attrs={"id": "percentile_value", 
                                                                   'placeholder': "Type Percentile Here ...",
                                                                   'class': "form-control col-md-2",
                                                                   'min': 2, 'max': 25}))

    rna_species = forms.ChoiceField(required=False,
                                   choices=[('', ' -- select an option -- '), 
                                             ("mRNA", "mRNA"), 
                                             ("miRNA", "miRNA")], 
                                    widget=forms.Select(attrs={'id': 'rna_species_choices', 
                                                               'class': "form-select", 
                                                               'empty_label': " -- select an option -- "}))