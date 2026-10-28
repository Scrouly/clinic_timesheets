"""Состав строк графика: поиск врача, добавление, правка, удаление и перестановка строк.

Все адреса проверяют право редактирования отделения графика. Ответы устроены так же, как у смен:
запрос с заголовком X-Requested-With: fetch получает фрагмент формы или JSON, обычный запрос страницу.
"""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import rows
from .forms import RowCreateForm, RowEditForm, RowRemoveForm
from .models import Assignment, Doctor, Schedule, ScheduleRow
from .views import is_fetch, period_title

SEARCH_LIMIT = 20


def editable_schedule(request, pk):
    schedule = get_object_or_404(Schedule.objects.select_related("department"), pk=pk)
    if not request.user.editable_departments().filter(pk=schedule.department_id).exists():
        raise PermissionDenied
    return schedule


def wants_json(request):
    return is_fetch(request) and request.headers.get("Accept", "").startswith("application/json")


def rate_text(rate):
    return format(rate.normalize(), "f")


def errors_json(form):
    return {name: [str(e) for e in errs] for name, errs in form.errors.items() if name != "__all__"} | {
        "__all__": [str(e) for e in form.non_field_errors()]
    }


def back_to_schedule(schedule):
    return redirect("schedule_detail", pk=schedule.pk)


@require_GET
def doctor_search(request, pk):
    """Сотрудники для выбора в графике: по фамилии, имени, отчеству или табельному номеру."""
    schedule = editable_schedule(request, pk)
    words = request.GET.get("q", "").casefold().split()
    found = []
    for doctor in Doctor.objects.all():  # сравнение без учёта регистра в Python: работает одинаково на любой базе
        haystack = f"{doctor.last_name} {doctor.first_name} {doctor.patronymic} {doctor.tab_number or ''}".casefold()
        if all(word in haystack for word in words):
            found.append(doctor)
        if len(found) == SEARCH_LIMIT:
            break

    assignments = {}
    for assignment in Assignment.objects.filter(doctor__in=found).order_by("-is_active", "-pk"):
        assignments.setdefault(assignment.doctor_id, []).append(assignment)
    present = {}
    for doctor_id, specialty_id in ScheduleRow.objects.filter(
        schedule=schedule, assignment__doctor__in=found
    ).values_list("assignment__doctor_id", "assignment__specialty_id"):
        present.setdefault(doctor_id, []).append(specialty_id)

    results = []
    for doctor in found:
        own = [a for a in assignments.get(doctor.pk, []) if a.department_id == schedule.department_id]
        other = assignments.get(doctor.pk, [])
        suggestion = own[0] if own else (other[0] if other else None)
        results.append(
            {
                "id": doctor.pk,
                "name": doctor.full_name,
                "short": doctor.short_name,
                "tab_number": doctor.tab_number or "",
                "specialty": suggestion.specialty_id if suggestion else None,
                "rate": rate_text(suggestion.rate) if own else "1",
                "in_schedule": present.get(doctor.pk, []),
            }
        )
    return JsonResponse({"results": results})


def render_form(request, schedule, form, *, title, action, template_context=None):
    """Форма строки: фрагмент для боковой панели или полная страница."""
    context = {
        "form": form,
        "schedule": schedule,
        "title": title,
        "action": action,
        "panel": is_fetch(request),
        "period": period_title(schedule.year, schedule.month),
    }
    context.update(template_context or {})
    template = "schedule/_row_form_body.html" if is_fetch(request) else "schedule/row_form.html"
    return render(request, template, context)


def finish(request, schedule, message, **extra):
    """Успех: JSON для запроса из панели, иначе сообщение и возврат на график."""
    if is_fetch(request):
        messages.success(request, message)
        return JsonResponse({"ok": True, "next": reverse("schedule_detail", args=[schedule.pk]), **extra})
    messages.success(request, message)
    return back_to_schedule(schedule)


@require_http_methods(["GET", "POST"])
def row_create(request, pk):
    schedule = editable_schedule(request, pk)
    action = reverse("row_create", args=[schedule.pk])
    if request.method == "POST":
        form = RowCreateForm(request.POST, schedule=schedule)
        if form.is_valid():
            row = form.save()
            if row is not None:
                return finish(
                    request, schedule, f"{row.assignment.doctor.short_name} добавлен в график.", row=row.pk
                )
        if wants_json(request):
            return JsonResponse({"ok": False, "errors": errors_json(form)}, status=400)
    else:
        form = RowCreateForm(schedule=schedule, initial={"position": request.GET.get("position") or None})
    return render_form(
        request, schedule, form,
        title="Добавить врача в график",
        action=action,
        template_context={"submit": "Добавить", "catalog_note": True},
    )


def _row(schedule, row_pk):
    return get_object_or_404(
        ScheduleRow.objects.select_related("assignment__doctor", "assignment__specialty"),
        pk=row_pk,
        schedule=schedule,
    )


@require_http_methods(["GET", "POST"])
def row_edit(request, pk, row):
    schedule = editable_schedule(request, pk)
    row = _row(schedule, row)
    action = reverse("row_edit", args=[schedule.pk, row.pk])
    form = RowEditForm(request.POST if request.method == "POST" else None, row=row)
    if request.method == "POST" and form.is_valid() and form.save() is not None:
        return finish(request, schedule, f"Ставка и профессия обновлены: {row.assignment.doctor.short_name}.")
    return render_form(
        request, schedule, form,
        title=f"Ставка и профессия: {row.assignment.doctor.short_name}",
        action=action,
        template_context={"submit": "Сохранить", "row": row},
    )


@require_http_methods(["GET", "POST"])
def row_remove(request, pk, row):
    schedule = editable_schedule(request, pk)
    row = _row(schedule, row)
    action = reverse("row_remove", args=[schedule.pk, row.pk])
    form = RowRemoveForm(request.POST if request.method == "POST" else None, row=row)
    name = row.assignment.doctor.short_name
    if request.method == "POST" and form.is_valid():
        removed = form.save()
        if removed is not None:
            tail = f" Удалено смен: {removed}." if removed else ""
            return finish(request, schedule, f"{name} убран из графика.{tail}")
    return render_form(
        request, schedule, form,
        title="Убрать из графика",
        action=action,
        template_context={
            "submit": "Убрать из графика",
            "danger": True,
            "row": row,
            "shift_count": form.shift_count,
            "name": name,
        },
    )


@require_POST
def row_move(request, pk, row):
    schedule = editable_schedule(request, pk)
    row = _row(schedule, row)
    position = request.POST.get("position")
    try:
        rows.move_row(
            row,
            direction=request.POST.get("direction"),
            position=int(position) if position not in (None, "") else None,
        )
    except (rows.RowError, ValueError) as error:
        message = getattr(error, "message", "Не понял, куда переместить строку.")
        if is_fetch(request):
            return JsonResponse({"ok": False, "errors": {"__all__": [message]}}, status=400)
        messages.error(request, message)
        return back_to_schedule(schedule)
    if is_fetch(request):
        return JsonResponse({"ok": True})
    return back_to_schedule(schedule)
