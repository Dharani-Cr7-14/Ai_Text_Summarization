from django.urls import path

from . import views


urlpatterns = [
    path("", views.index, name="index"),
    path("summarize/", views.summarize_view, name="summarize"),
    path("api/summarize/", views.summarize_api, name="api_summarize"),
    path("download-summary/", views.download_summary, name="download_summary"),
]