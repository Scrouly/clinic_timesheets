from django.urls import path

from . import views, views_cells, views_rows

urlpatterns = [
    path("schedules/", views.ScheduleListView.as_view(), name="schedules"),
    path("schedules/<int:pk>/", views.ScheduleDetailView.as_view(), name="schedule_detail"),
    path("schedules/<int:pk>/doctors/", views_rows.doctor_search, name="schedule_doctors"),
    path("schedules/<int:pk>/cells/", views_cells.cell_apply, name="cell_apply"),
    path("schedules/<int:pk>/rows/new/", views_rows.row_create, name="row_create"),
    path("schedules/<int:pk>/rows/<int:row>/edit/", views_rows.row_edit, name="row_edit"),
    path("schedules/<int:pk>/rows/<int:row>/remove/", views_rows.row_remove, name="row_remove"),
    path("schedules/<int:pk>/rows/<int:row>/move/", views_rows.row_move, name="row_move"),
    path("shifts/new/", views.ShiftCreateView.as_view(), name="shift_create"),
    path("shifts/<int:pk>/edit/", views.ShiftUpdateView.as_view(), name="shift_update"),
    path("shifts/<int:pk>/delete/", views.ShiftDeleteView.as_view(), name="shift_delete"),
    path("cabinets/", views.CabinetGridView.as_view(), name="cabinets"),
    path("cabinets/<int:year>/<int:month>/", views.CabinetGridView.as_view(), name="cabinets_month"),
]
