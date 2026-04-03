from django.urls import path
from . import views

urlpatterns = [
    # Candidate
    path("apply/<int:job_id>/", views.apply_job, name="apply_job"),
    path("already-applied/<int:job_id>/", views.already_applied, name="already_applied"),
    path("withdraw/<int:application_id>/",views.withdraw_application, name="withdraw_application"),
    
    path("my/",views.application_list,name="application_list"),
    path("my/old/", views.old_application_list, name="old_application_list"),

    # Company
    path("job/<int:job_id>/applicants/",views.view_applicants, name="view_applicants"),
    path("<int:application_id>/",views.application_detail,name="application_detail"),
    path("<int:application_id>/status/",views.update_application_status,name="update_application_status"),

    # Resume manager
    path("resumes/",views.resume_manager, name="resume_manager"),
    path("resumes/<int:resume_id>/delete/", views.delete_resume, name="delete_resume"),
    path("resumes/<int:resume_id>/default/",views.set_default_resume, name="set_default_resume"),
]