"""Общие помощники консольных загрузок: файл-отчёт и файл с временными паролями."""
import csv
import datetime
import os


def write_report(path: str | None, title: str, apply: bool, stats: dict[str, int], notes: list[str] | None = None) -> None:
    """Результат запуска — в текстовый файл (для сверки и архива). Без пути ничего не делает."""
    if not path:
        return
    lines = [f"{title} — {datetime.datetime.now():%d.%m.%Y %H:%M}", "режим: " + ("ЗАПИСЬ" if apply else "проверка, в базу ничего не записано"), ""]
    lines += [f"{name}: {count}" for name, count in stats.items()] or ["изменений нет"]
    if notes:
        lines += ["", *notes]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_credentials(path: str, rows: list[tuple[str, str, str, str]]) -> None:
    """Временные пароли — в CSV (UTF-8 с BOM и «;», чтобы Excel открыл кириллицу). Файл создаётся с правами 600:
    пароли действуют до первого входа, но лежать на диске дольше нужного им не стоит."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["ФИО", "Отделение", "Логин", "Временный пароль"])
        writer.writerows(rows)
