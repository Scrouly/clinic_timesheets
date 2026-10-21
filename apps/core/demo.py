"""Образец сетки графика на выдуманных данных.

Нужен, чтобы согласовать внешний вид с заведующими и кадровиком до того,
как появятся настоящие модели графиков. Никаких обращений к базе здесь нет.
"""
import calendar
from datetime import date, time

WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")

# (ФИО, должность, ставка, кабинет, начало, конец, рабочие дни недели)
DEMO_STAFF = (
    ("Орлов А.П.", "врач-хирург", 1.0, "301", time(8, 0), time(14, 30), (0, 1, 2, 3, 4)),
    ("Соколова Е.В.", "врач-эндокринолог", 0.75, "115", time(9, 0), time(14, 0), (0, 2, 4)),
    ("Мартынов И.Д.", "врач-невролог", 1.0, "117", time(8, 0), time(14, 30), (0, 1, 2, 3, 4)),
    ("Лаптева О.Н.", "врач-кардиолог", 0.25, "117", time(13, 0), time(17, 0), (1, 3)),
    ("Белов Р.С.", "врач-уролог", 0.5, "201", time(15, 0), time(20, 0), (0, 1, 2)),
    ("Зайцева Н.К.", "врач-акушер-гинеколог", 0.5, "201", time(14, 0), time(19, 0), (2, 3, 4)),
)

def _hours(start, end):
    return round((end.hour * 60 + end.minute - start.hour * 60 - start.minute) / 60, 2)


def build_demo_grid(year, month):
    last_day = calendar.monthrange(year, month)[1]
    days = []
    for number in range(1, last_day + 1):
        weekday = date(year, month, number).weekday()
        days.append({"number": number, "weekday": WEEKDAYS[weekday], "is_weekend": weekday >= 5})

    rows = []
    for name, position, rate, cabinet, start, end, week in DEMO_STAFF:
        cells, worked_days, worked_hours = [], 0, 0.0
        for day in days:
            weekday = date(year, month, day["number"]).weekday()
            cell = {"kind": "off", "weekend": day["is_weekend"]}
            if weekday in week:
                hours = _hours(start, end)
                cell = {
                    "kind": "shift",
                    "weekend": day["is_weekend"],
                    "time": f"{start:%H:%M}–{end:%H:%M}",
                    "cabinet": cabinet,
                    "hours": hours,
                }
                worked_days += 1
                worked_hours += hours
            cells.append(cell)
        rows.append(
            {
                "name": name,
                "position": f"{position} ({str(rate).replace('.', ',')} ст.)",
                "cells": cells,
                "worked_days": worked_days,
                "worked_hours": round(worked_hours, 2),
                # В образце норма задана условно: у большинства строк она сходится с планом,
                # у одной выше нормы, чтобы были видны оба вида расхождений.
                "norm": round(worked_hours - (4.0 if len(rows) == 3 else 0.0), 2),
            }
        )

    _mark_examples(rows, days)
    for row in rows:
        row["delta"] = round(row["worked_hours"] - row["norm"], 2)
    return {"days": days, "rows": rows}


def _mark_examples(rows, days):
    """Показывает, как выглядят отпуск, накладка и правка. Примеры стоят в начале месяца,
    чтобы были видны без прокрутки."""
    first_workday = next(i for i, d in enumerate(days) if not d["is_weekend"])

    # отпуск у второго врача: пять календарных дней подряд
    for index in range(first_workday, min(first_workday + 5, len(days))):
        cell = rows[1]["cells"][index]
        if cell["kind"] == "shift":
            rows[1]["worked_days"] -= 1
            rows[1]["worked_hours"] = round(rows[1]["worked_hours"] - cell["hours"], 2)
        rows[1]["cells"][index] = {"kind": "vacation", "weekend": days[index]["is_weekend"], "text": "ОТП"}

    # накладка: первая среда, когда оба врача работают в кабинете 201
    clash_day = next((i for i, d in enumerate(days) if d["weekday"] == "ср" and i >= first_workday), None)
    if clash_day is not None:
        for row_index in (4, 5):
            cell = rows[row_index]["cells"][clash_day]
            if cell["kind"] == "shift":
                cell["state"] = "error"
                cell["note"] = "Кабинет 201 занят в это время другим врачом"

    # правка после отправки: ближайший четверг после накладки
    after = clash_day if clash_day is not None else first_workday
    edited_day = next((i for i, d in enumerate(days) if d["weekday"] == "чт" and i > after), None)
    if edited_day is not None and rows[0]["cells"][edited_day]["kind"] == "shift":
        rows[0]["cells"][edited_day]["state"] = "changed"
        rows[0]["cells"][edited_day]["note"] = "Время смены изменено"
