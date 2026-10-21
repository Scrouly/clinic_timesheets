from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("schedules/", views.SECTIONS["schedules"], name="schedules"),
    path("summary/", views.SECTIONS["summary"], name="summary"),
    path("cabinets/", views.SECTIONS["cabinets"], name="cabinets"),
    path("reports/", views.SECTIONS["reports"], name="reports"),
    path("reference/", views.SECTIONS["reference"], name="reference"),
    path("demo/grid/", views.DemoGridView.as_view(), name="demo_grid"),
]
