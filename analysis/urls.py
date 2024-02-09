from django.urls import path
from . import views

urlpatterns = [
    path('fetch_gois/<analysis_id>', views.fetch_gois, name='fetch-gois'),
    path('check_analysis_type/<analysis_id>', views.check_analysis_type, name='analysis-check-type'),
    path('download/<analysis_id>', views.download, name='analysis-download'),
    path('home', views.display_settings_page, name='analysis-home'),
    path('fetch/<analysis>', views.fetch, name='analysis-fetch'),
    path('fetch/<analysis>/<analysis2>', views.fetch2, name='analysis-fetch2'),
    path('genes_autocomplete', views.GenesAutocomplete.as_view(), name='genes-autocomplete'),
    path('projects_autocomplete', views.ProjectsAutocomplete.as_view(), name='projects-autocomplete'),
]

