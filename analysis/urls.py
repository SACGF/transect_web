from django.urls import path
from . import views

urlpatterns = [
    path('download', views.download, name='analysis-download'),
    path('home', views.display_settings_page, name='analysis-home'),
    path('fetch', views.fetch, name='analysis-fetch'),
    path('genes_autocomplete', views.GenesAutocomplete.as_view(), name='genes-autocomplete'),
    path('projects_autocomplete', views.ProjectsAutocomplete.as_view(), name='projects-autocomplete'),
    path('test', views.test, name='analysis-test')
]

