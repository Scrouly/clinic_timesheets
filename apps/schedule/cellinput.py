"""Разбор текста ячейки графика: чистые функции без обращения к страницам и к базе.

Человек печатает в ячейку `8-14:40 301`, `отп` или `8-12 301; 14-18 302`. Здесь этот текст
превращается в список записей и обратно в каноническую запись. Все правила ввода живут в
этом модуле, клиент текст не разбирает.

parse_cell возвращает список ParsedEntry (пустой список: день очищается) либо CellError
с понятным сообщением по-русски. Исключений для ошибок ввода нет: ошибка это обычный результат.
"""
import re
from dataclasses import dataclass
from datetime import time

ENTRY_SEPARATORS = re.compile(r"[;+]")
# часы и необязательные минуты: «8», «8:30», «8.30», «830»; разделитель между концами: дефис или тире
TIME_RANGE = re.compile(
    r"^(\d{1,2})(?:[:.]?(\d{2}))?\s*[-\u2010-\u2015]\s*(\d{1,2})(?:[:.]?(\d{2}))?(?:\s+(.+))?$"
)
CABINET_NOISE = re.compile(r"[\s\-\u2010-\u2015_.]+")
HINT_EXAMPLE = "введите время, например 8-14"


@dataclass(frozen=True)
class ParsedEntry:
    """Одна запись ячейки: вид времени и, для рабочего, начало, конец и кабинет."""

    kind: object
    start: time | None = None
    end: time | None = None
    cabinet: object | None = None


@dataclass(frozen=True)
class CellError:
    message: str

    def __str__(self):
        return self.message


def _fold(text):
    """Название кабинета для сравнения: без регистра, пробелов, дефисов и точек."""
    return CABINET_NOISE.sub("", text.casefold())


def _to_time(hours, minutes):
    hour, minute = int(hours), int(minutes or 0)
    if hour > 23:
        return None
    if minute > 59:
        return None
    return time(hour, minute)


def _find_cabinet(text, cabinets):
    """Кабинет по названию: точное совпадение главнее начала названия. Возвращает (кабинет, ошибка)."""
    wanted = _fold(text.lstrip("·•").strip())
    if not wanted:
        return None, None
    exact = [c for c in cabinets if _fold(c.name) == wanted]
    if exact:
        return exact[0], None
    prefixed = [c for c in cabinets if _fold(c.name).startswith(wanted)]
    if len(prefixed) == 1:
        return prefixed[0], None
    if prefixed:
        names = " или ".join(c.name for c in prefixed[:5])
        return None, CellError(f"Какой кабинет «{text.strip()}»: {names}?")
    return None, CellError(f"Не нашёл кабинет «{text.strip()}»")


def _parse_segment(segment, cabinets, kinds, default_cabinet):
    text = segment.strip()
    folded = text.casefold()

    absence = next(
        (k for k in kinds if not k.is_working and folded in (k.short_label.casefold(), k.name.casefold())), None
    )
    if absence is not None:
        return ParsedEntry(kind=absence)

    match = TIME_RANGE.match(text)
    if match is None:
        return CellError(f"Не понял «{text}»: {HINT_EXAMPLE}")
    start_h, start_m, end_h, end_m, cabinet_text = match.groups()
    start, end = _to_time(start_h, start_m), _to_time(end_h, end_m)
    if start is None or end is None:
        return CellError(f"Не понял время в «{text}»: часы от 0 до 23, минуты от 0 до 59")
    if end <= start:
        return CellError(f"В «{text}» конец должен быть позже начала: смена не переходит через полночь")

    working = next((k for k in kinds if k.is_working), None)
    if working is None:
        return CellError("В справочнике нет вида времени «рабочее время»")

    cabinet = None
    if cabinet_text and cabinet_text.strip("·•").strip():
        cabinet, error = _find_cabinet(cabinet_text, cabinets)
        if error:
            return error
    else:
        cabinet = default_cabinet() if callable(default_cabinet) else default_cabinet
        if cabinet is None:
            return CellError(f"Укажите кабинет: «{text} 301»")
    return ParsedEntry(kind=working, start=start, end=end, cabinet=cabinet)


def parse_cell(raw, cabinets, kinds, default_cabinet=None):
    """Текст ячейки в список записей.

    cabinets, kinds: действующие кабинеты и виды времени. default_cabinet: кабинет для смены без
    кабинета в тексте (значение или функция без аргументов, её вызовут только при необходимости).
    """
    text = (raw or "").strip()
    if not text:
        return []
    entries = []
    for segment in ENTRY_SEPARATORS.split(text):
        if not segment.strip():
            continue  # «8-14;» и «8-14 ; ; 15-18»: лишние разделители не ошибка
        parsed = _parse_segment(segment, cabinets, kinds, default_cabinet)
        if isinstance(parsed, CellError):
            return parsed
        entries.append(parsed)
    return entries


def format_cell(entries):
    """Каноническая запись ячейки. parse_cell(format_cell(x)) возвращает те же записи.

    Принимает ParsedEntry или Shift: нужны атрибуты kind, start, end, cabinet.
    """
    parts = []
    for entry in sorted(entries, key=lambda e: (e.start or time.min, e.kind.short_label)):
        if entry.kind.is_working and entry.start and entry.end:
            cabinet = f" · {entry.cabinet.name}" if entry.cabinet else ""
            parts.append(f"{entry.start:%H:%M}–{entry.end:%H:%M}{cabinet}")
        else:
            parts.append(entry.kind.short_label)
    return "; ".join(parts)
