"""Разовое заполнение «к какой паре пришла группа» (day_submissions.first_period)
по выгрузкам расписания занятий (xlsx, лист «Текущее расписание»).

Пара — первая пара дня, на которой у группы есть занятие (по любой подгруппе).
Обновляет только уже сданные дни; новых сдач не создаёт, отметки студентов не трогает.
По умолчанию заполняет только пустую пару; --overwrite заменяет и выбранную куратором.

Без --commit — пробный прогон: ничего не записывается, печатается отчёт.

    python -m scripts.import_first_period_schedule FILE_OR_DIR [...]            # пробный прогон
    python -m scripts.import_first_period_schedule FILE_OR_DIR [...] --commit   # запись
"""
import argparse
import datetime
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl

from app.db import base as db_base
from app.models import DaySubmission, StudyGroup

SHEET = "Текущее расписание"
HEADER_ROW = 3  # индекс строки с датами (нумерация с нуля)
FIRST_DATA_ROW = 8
GROUP_ROW = 5  # во второй форме: строка с кодами групп
LANDSCAPE_BLOCK = 4  # колонок на группу: подгруппа 1, 2, пустая, «Ауд.»
DISCIPLINE_COLUMNS = 3  # в блоке дня: подгруппа 1, подгруппа 2, затем «Ауд.» — её не считаем


def normalize_group_code(raw: str) -> str:
    """В поздних выгрузках к коду добавлен год набора («ИИ112-26») — в базе код без него."""
    return re.sub(r"-\d{2}$", "", str(raw).strip())


def _first_pair_portrait(rows) -> dict[tuple[str, datetime.date], int]:
    """Группы по строкам, дни по колонкам (лист «Текущее расписание»)."""
    days = []
    for col, value in enumerate(rows[HEADER_ROW]):
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", str(value or ""))
        if m:
            days.append((col, datetime.date(int(m[3]), int(m[2]), int(m[1]))))
    width = days[1][0] - days[0][0] if len(days) > 1 else DISCIPLINE_COLUMNS
    first: dict[tuple[str, datetime.date], int] = {}
    group = None
    for row in rows[FIRST_DATA_ROW:]:
        if row[0]:
            group = normalize_group_code(row[0])
        if not group or row[2] is None:
            continue
        pair = (int(row[2]) + 1) // 2  # урок 1–2 — первая пара, 3–4 — вторая…
        for col, day in days:
            if any(col + k < len(row) and row[col + k] not in (None, "") for k in range(min(DISCIPLINE_COLUMNS, width))):
                key = (group, day)
                first[key] = min(pair, first.get(key, pair))
    return first


def _first_pair_landscape(rows) -> dict[tuple[str, datetime.date], int]:
    """Дни по строкам, группы по колонкам (первый лист, коды групп в 6-й строке)."""
    starts = [
        (col, normalize_group_code(v)) for col, v in enumerate(rows[GROUP_ROW])
        if col >= 3 and v and str(v).strip() != "Группа:"
    ]
    width = starts[1][0] - starts[0][0] if len(starts) > 1 else LANDSCAPE_BLOCK
    first: dict[tuple[str, datetime.date], int] = {}
    day = None
    for row in rows[FIRST_DATA_ROW - 1:]:
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", str(row[0] or ""))
        if m:
            day = datetime.date(int(m[3]), int(m[2]), int(m[1]))
        if day is None or row[2] is None:
            continue
        pair = (int(row[2]) + 1) // 2
        for col, group in starts:
            if any(col + k < len(row) and row[col + k] not in (None, "") for k in range(min(DISCIPLINE_COLUMNS, width))):
                key = (group, day)
                first[key] = min(pair, first.get(key, pair))
    return first


def read_schedule(path: str) -> dict[tuple[str, datetime.date], int]:
    """(код группы, дата) -> первая пара дня, на которой есть занятие.
    Понимает обе формы выгрузки: «группы по строкам» и «группы по колонкам»."""
    wb = openpyxl.load_workbook(path, data_only=True)
    if SHEET in wb.sheetnames:
        return _first_pair_portrait(list(wb[SHEET].iter_rows(values_only=True)))
    return _first_pair_landscape(list(wb.worksheets[0].iter_rows(values_only=True)))


def collect_files(paths: list[str]) -> list[str]:
    files = []
    for p in paths:
        files += sorted(glob.glob(os.path.join(p, "*.xlsx"))) if os.path.isdir(p) else [p]
    return files


def load(db, paths: list[str], commit: bool, overwrite: bool = False) -> dict:
    schedule: dict[tuple[str, datetime.date], int] = {}
    parts, skipped = [], []
    for path in collect_files(paths):
        try:
            parts.append(read_schedule(path))
        except (KeyError, IndexError, ValueError, TypeError, openpyxl.utils.exceptions.InvalidFileException):
            skipped.append(os.path.basename(path))  # не расписание (другой xlsx в той же папке)
    # Выгрузки за разные периоды пересекаются; узкая (например, 3 дня внутри недели) —
    # это уточнение, поэтому применяем её последней.
    for part in sorted(parts, key=lambda x: -len({d for _, d in x})):
        schedule.update(part)
    report = {"updated": 0, "unchanged": 0, "kept_existing": 0, "not_submitted": 0, "groups_not_found": [], "skipped_files": skipped}
    groups = {g.code: g for g in db.query(StudyGroup)}
    missing = set()
    for (code, day), pair in sorted(schedule.items()):
        group = groups.get(code)
        if group is None:
            missing.add(code)
            continue
        sub = db.query(DaySubmission).filter(
            DaySubmission.study_group_id == group.id, DaySubmission.date == day
        ).one_or_none()
        if sub is None:
            report["not_submitted"] += 1
        elif sub.first_period == pair:
            report["unchanged"] += 1
        elif sub.first_period is not None and not overwrite:
            report["kept_existing"] += 1
        else:
            report["updated"] += 1
            sub.first_period = pair
    report["groups_not_found"] = sorted(missing)
    if commit:
        db.commit()
    else:
        db.rollback()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    db = db_base.SessionLocal()
    try:
        report = load(db, args.paths, args.commit, args.overwrite)
    finally:
        db.close()
    print("ЗАПИСЬ" if args.commit else "ПРОБНЫЙ ПРОГОН (ничего не записано)")
    for key, value in report.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
