from django.urls import path
from . import views

urlpatterns = [
    # Public
    path("",                     views.job_list,          name="job_list"),
    path("<int:job_id>/",        views.job_detail,        name="job_detail"),

    # Company management
    path("create/",              views.create_job,        name="create_job"),
    path("<int:job_id>/edit/",   views.edit_job,          name="edit_job"),
    path("<int:job_id>/delete/", views.delete_job,        name="delete_job"),
    path("<int:job_id>/toggle/", views.toggle_job_status, name="toggle_job_status"),
    path("manage/",              views.company_job_list,  name="company_job_list"),
    path('old/',                    views.old_jobs,             name='old_jobs'),
    path('to-shortlist/',           views.to_shortlist,          name='to_shortlist'),
    path('<int:job_id>/send-email/', views.send_shortlist_email,  name='send_shortlist_email'),
]