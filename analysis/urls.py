from django.urls import path
from . import views

urlpatterns = [
    path('home', views.home, name='analysis-home'),
    path('provide_correlation_comparisons/<analysis_id>', views.provide_correlation_comparisons, name='provide-correlation-comparisons'),
    path('download/<analysis_id>', views.download, name='analysis-download'),
    path('check_fully_downloaded/<analysis_id>', views.check_fully_downloaded, name='check-fully-downloaded'),
    path('check_de_finished/<analysis_id>', views.check_de_finished, name='check-de-finished'),
    path('submit', views.display_settings_page, name='analysis-submit'),
    path('fetch/<analysis>', views.fetch, name='analysis-fetch'),
    path('genes_autocomplete', views.GenesAutocomplete.as_view(), name='genes-autocomplete'),
    path('projects_autocomplete', views.ProjectsAutocomplete.as_view(), name='projects-autocomplete'),
    path('fetch_gsea_summary/<analysis_id>', views.FetchGseaSummary, name='fetch-gsea-summary'),
    path('fetch_high_corr_gene_exprs/<analysis_id>/<gene1_id>/<gene2_id>', views.fetch_high_corr_gene_exprs, name='fetch-high-corr-gene-exprs'),
]

