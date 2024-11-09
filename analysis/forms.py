from django import forms
from analysis.models import Analysis, Genes, Projects
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Case, When
from dal import autocomplete, forward
from django.core.exceptions import ValidationError

class AnalysisForm(forms.Form):
    def __init__(self, *args, **kwargs):
       super().__init__(*args, **kwargs)
       self.label_suffix = ""  # Removes : as label suffix

    def clean_gene_selected(self):
       order = self.data.getlist("gene_selected")
       cleaned = self.cleaned_data.get("gene_selected")
       preserved = Case(*[When(name=name, then=pos) for pos, name in enumerate(order)])
       return cleaned.filter(name__in=order).order_by(preserved)

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
                                                                          forward=("script_type", ),  
                                                                          # accessing script field as well, allowing us to filter based on that as well
                                                                          attrs={'data-placeholder': 'Projects ...',
                                                                                 'data-minimum-input-length': 1,
                                                                                 },
                                                                         )
                                   )

    # ModelMultipleChoiceField does not preserve the order of the elements
    gene_selected = forms.ModelMultipleChoiceField(queryset=Genes.objects.all(),
                                         required=True,
                                         widget=autocomplete.ModelSelect2Multiple(url='genes-autocomplete',
                                                             forward=("script_type", "use_mirna", ),  
                                                             attrs={'data-placeholder': 'Genes ...',
                                                                    'data-minimum-input-length': 2,
                                                                    'id': 'gene_selected', 
                                                                    'class': 'mt-3'
                                                                    }))

    composite_analysis_type = forms.ChoiceField(choices=[("Single", "Single"),
                                                         ("Additive", "Additive"),
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
                                                                                      "you cannot do a correlation analysis if you select either Ratio or Additive."
                                                                      }))

    do_correlation_analysis = forms.BooleanField(required=False,
                                                 label="Run correlation analysis (only valid with single analysis mode, will also ignore stratification threshold and any other optional parameter)",
                                                 widget=forms.CheckboxInput(attrs={'id': 'correlation_checkbox', 'class': "analysis-type-checkbox"}))
    
    percentile = forms.IntegerField(required=False,
                                   label="Percentile cutoff used as a threshold for low and high stratum membership. Must be integer between 2 - 25.",
                                   widget=forms.NumberInput(attrs={"id": "percentile_value", 
                                                                   'placeholder': "Type Percentile Here ...",
                                                                   'class': "form-control col-md-2",
                                                                   'min': 2, 'max': 25}))

    use_mirna = forms.BooleanField(required=False,
                                   label="Multimodal analysis (assess changes in mRNA given a miRNA query, at present can only be TCGA data)",
                                   widget=forms.CheckboxInput(attrs={'id': 'use_mirna_checkbox'}))
    
    switch_stratum = forms.BooleanField(required=False,
                               label="Switch comparison (compares low stratum to high stratum)",
                               widget=forms.CheckboxInput(attrs={'id': 'switch_stratum_checkbox'}))
    
    display_gsea = forms.BooleanField(required=False,
                     label="Run GSEA analysis (requires approx. 10-15 minutes to complete)",
                     widget=forms.CheckboxInput(attrs={'id': 'display_gsea_checkbox'}))