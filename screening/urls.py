from django.urls import path
from . import views

urlpatterns = [
    # Run screening (POST only) for all apps on a job
    path("run/<int:job_id>/",              views.run_screening,            name="run_screening"),

    # Full screening dashboard for a job
    path("job/<int:job_id>/",              views.screening_dashboard,      name="screening_dashboard"),

    # Single application screening detail
    path("result/<int:application_id>/",   views.screening_result_detail,  name="screening_result_detail"),

    # FIX #15: candidate ranking for a job (was orphaned — no view or URL existed)
    path("job/<int:job_id>/ranking/",      views.ranking,                  name="ranking"),
]