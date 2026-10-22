from django.urls import path

from . import views

urlpatterns = [
    path("schedules/", views.ScheduleListView.as_view(), name="schedules"),
    path("schedules/<int:pk>/", views.ScheduleDetailView.as_view(), name="schedule_detail"),
    path("shifts/new/", views.ShiftCreateView.as_view(), name="shift_create"),
    path("shifts/<int:pk>/edit/", views.ShiftUpdateView.as_view(), name="shift_update"),
    path("shifts/<int:pk>/delete/", views.ShiftDeleteView.as_view(), name="shift_delete"),
    path("cabinets/", views.CabinetGridView.as_view(), name="cabinets"),
    path("cabinets/<int:year>/<int:month>/", views.CabinetGridView.as_view(), name="cabinets_month"),
]
