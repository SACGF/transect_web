from django.urls import path
from . import views

urlpatterns = [
    path('fetch_gois/<analysis_id>', views.fetch_gois, name='fetch-gois'),
    path('check_analysis_type/<analysis_id>', views.check_analysis_type, name='analysis-check-type'),
    path('provide_correlation_comparisons/<analysis_id>', views.provide_correlation_comparisons, name='provide-correlation-comparisons'),
    path('download/<analysis_id>', views.download, name='analysis-download'),
    path('check_fully_downloaded/<analysis_id>', views.check_fully_downloaded, name='check-fully-downloaded'),
    path('home', views.display_settings_page, name='analysis-home'),
    path('fetch/<analysis>', views.fetch, name='analysis-fetch'),
    path('genes_autocomplete', views.GenesAutocomplete.as_view(), name='genes-autocomplete'),
    path('projects_autocomplete', views.ProjectsAutocomplete.as_view(), name='projects-autocomplete'),
]

