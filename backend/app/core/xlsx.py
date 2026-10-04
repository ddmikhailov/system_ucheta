"""Общие помощники для Excel-выгрузок и загрузок."""
import io
import zipfile

# xlsx — это zip. Файл ≤ 5 МБ может «распаковаться» в гигабайты (zip-бомба), а openpyxl
# разберёт всё в памяти. Настоящие файлы из шаблона занимают сотни КБ в распакованном виде.
MAX_ENTRIES = 200
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024


class UnsafeArchiveError(ValueError):
    pass


def check_zip_safety(content: bytes) -> None:
    """Отклоняет не-zip и архивы, распаковывающиеся сверх лимита. Заявленные в заголовке
    размеры можно подделать, поэтому дополнительно считаем реально распакованные байты —
    с остановкой на лимите, а не после распаковки целиком."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise UnsafeArchiveError("не xlsx-файл") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise UnsafeArchiveError("слишком много внутренних файлов")
        if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
            raise UnsafeArchiveError("файл слишком велик после распаковки")
        total = 0
        for info in infos:
            try:
                with archive.open(info) as stream:
                    while chunk := stream.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_UNCOMPRESSED_BYTES:
                            raise UnsafeArchiveError("файл слишком велик после распаковки")
            except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError) as exc:
                raise UnsafeArchiveError("повреждённый архив") from exc



def safe_cell(value):
    """openpyxl запишет строку, начинающуюся с =, +, - или @, как формулу — Excel её
    выполнит при открытии у того, кто скачал файл. Ответы по задачам, ФИО и прочие
    поля вводят люди, поэтому всё, что приходит из данных, пропускаем через эту функцию
    (экранирование апострофом, как рекомендует OWASP)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def append_row(ws, row) -> None:
    """Добавляет строку и сохраняет значения «как текст»: openpyxl принимает строку на «=»
    за формулу, а Excel выполнит её при открытии. Содержимое не меняется — в отличие от
    safe_cell, телефоны вида «+7…» остаются как есть (в xlsx текстовая ячейка не выполняется)."""
    ws.append(list(row))
    for cell in ws[ws.max_row]:
        if cell.data_type == "f":
            cell.data_type = "s"
