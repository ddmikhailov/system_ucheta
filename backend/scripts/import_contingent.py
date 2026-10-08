"""Загрузка контингента (группы, студенты, кураторы) из единого Excel-шаблона — консольный вариант экрана
«Админка → Импорт». Правила те же (см. app/services/contingent_import_service.py): ничего не удаляется,
пустая ячейка = «не менять», любая ошибка в файле блокирует запись целиком, повторный запуск безопасен.

    python -m scripts.import_contingent --template шаблон.xlsx            # скачать шаблон с текущими данными
    python -m scripts.import_contingent --template шаблон.xlsx --empty    # пустой шаблон
    python -m scripts.import_contingent файл.xlsx                         # проверка: что изменится (ничего не пишет)
    python -m scripts.import_contingent файл.xlsx --apply                 # записать
    ... --absent expel            # студентов из загруженных групп, которых нет в файле, отметить «отчислен»
    ... --replace-curators        # новый куратор вместо действующего (прежнее назначение закрывается)
    ... --create-departments      # завести отделения, которых ещё нет
    ... --confirm-large           # подтвердить массовое выбытие (слишком большая доля студентов группы)
    ... --issue-passwords пароли.csv   # временные пароли новым кураторам (только с --apply; CSV с правами 600)
    ... --enrolled-at 2026-09-01       # дата зачисления для новых студентов без даты (по умолчанию — сегодня)
    ... --report отчёт.txt             # сохранить результат в файл

Файл с ФИО держите вне репозитория и после загрузки удалите.
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import base as db_base
from app.services import contingent_import_service as svc
from scripts._report import write_credentials, write_report


def run(path: str, apply: bool, options: svc.Options, *, issue_passwords_file: str | None = None, report_file: str | None = None) -> svc.Report:
    with open(path, "rb") as f:
        content = f.read()
    parsed = svc.parse_workbook(content)
    db = db_base.SessionLocal()
    try:
        report = svc.process(db, parsed, options, None)
        if apply and not report.blocked:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    committed = apply and not report.blocked
    if committed and issue_passwords_file and report.credentials:
        write_credentials(issue_passwords_file, [(c.full_name, c.department, c.username, c.password) for c in report.credentials])

    print("Загружено." if committed else ("ЗАПИСЬ НЕ ВЫПОЛНЕНА." if apply else "Проверка (ничего не записано; добавьте --apply):"))
    for name, count in report.counts.items():
        print(f"  {name}: {count}")
    for c in report.changes[:svc.MAX_CHANGES_LISTED]:
        print(f"  [{c.sheet}] {c.action}: {c.label}" + (f" — {c.detail}" if c.detail else ""))
    for w in report.warnings:
        print(f"! {w}")
    for e in report.errors:
        print(f"ОШИБКА, лист «{e.sheet}», строка {e.row}: {e.message}")
    if report.needs_confirmation:
        print(f"ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ: {report.needs_confirmation} (--confirm-large)")
    notes = [f"[{c.sheet}] {c.action}: {c.label} {c.detail}".strip() for c in report.changes]
    notes += [f"! {w}" for w in report.warnings] + [f"ОШИБКА {e.sheet}:{e.row} {e.message}" for e in report.errors]
    write_report(report_file, "Загрузка контингента", committed, report.counts, notes)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", help="заполненный шаблон (.xlsx)")
    parser.add_argument("--template", metavar="ФАЙЛ.xlsx", help="сохранить шаблон (с текущими данными) и выйти")
    parser.add_argument("--empty", action="store_true", help="шаблон без данных")
    parser.add_argument("--apply", action="store_true", help="записать изменения в базу")
    parser.add_argument("--absent", choices=["keep", "expel"], default="keep")
    parser.add_argument("--replace-curators", action="store_true")
    parser.add_argument("--create-departments", action="store_true")
    parser.add_argument("--confirm-large", action="store_true")
    parser.add_argument("--issue-passwords", metavar="ФАЙЛ.csv")
    parser.add_argument("--enrolled-at", type=datetime.date.fromisoformat)
    parser.add_argument("--report", metavar="ФАЙЛ.txt")
    args = parser.parse_args()

    if args.template:
        db = db_base.SessionLocal()
        try:
            content = svc.build_template(db, with_data=not args.empty)
        finally:
            db.close()
        with open(args.template, "wb") as f:
            f.write(content)
        print(f"Шаблон сохранён: {args.template}")
        return
    if not args.path:
        parser.error("укажите файл или --template")
    if args.issue_passwords and not args.apply:
        parser.error("--issue-passwords работает только вместе с --apply")
    options = svc.Options(
        absent_students=args.absent, replace_curators=args.replace_curators, create_departments=args.create_departments,
        confirm_large=args.confirm_large, issue_passwords=bool(args.issue_passwords), default_enrolled_at=args.enrolled_at,
    )
    try:
        report = run(args.path, args.apply, options, issue_passwords_file=args.issue_passwords, report_file=args.report)
    except (svc.ImportFileError, RuntimeError, OSError) as exc:
        sys.exit(f"Ошибка: {exc}")
    if report.blocked:
        sys.exit(1)


if __name__ == "__main__":
    main()
