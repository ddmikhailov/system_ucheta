"""Сборка PDF-документов для переноса платформы на рабочий сервер организации.

Результат — две книги в docs/deploy/:
  * kait20-instrukciya-administratoru.pdf — пошаговая инструкция для системного администратора;
  * kait20-zagruzka-dannyh-varianty.pdf   — анализ и варианты массовой загрузки контингента и кураторов.

Конфигурации в приложениях инструкции читаются из файлов docs/deploy (vhost Apache, служба systemd, резервная
копия), чтобы текст в PDF не расходился с тем, что реально проверялось.

Запуск (из корня репозитория, нужен reportlab из requirements.txt и шрифты DejaVu):
    python tools/build_deploy_pdf.py
"""
import datetime
import tomllib
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle,
)

REPO = Path(__file__).resolve().parent.parent
DEPLOY = REPO / "docs" / "deploy"
FONT_DIRS = [Path("/usr/share/fonts/truetype/dejavu"), Path("C:/Windows/Fonts")]

BRAND = colors.HexColor("#4a2c8a")
INK = colors.HexColor("#1c1b2e")
MUTED = colors.HexColor("#5b5a72")
CODE_BG = colors.HexColor("#f3f2f8")
LINE = colors.HexColor("#cfcde0")
WARN_BG = colors.HexColor("#fdf1e0")
OK_BG = colors.HexColor("#e8f5ec")


def register_fonts() -> None:
    names = {"DejaVuSans": "DejaVuSans.ttf", "DejaVuSans-Bold": "DejaVuSans-Bold.ttf", "DejaVuMono": "DejaVuSansMono.ttf"}
    for font, file in names.items():
        path = next((d / file for d in FONT_DIRS if (d / file).is_file()), None)
        if path is None:
            raise SystemExit(f"Не найден шрифт {file} (нужен DejaVu с кириллицей).")
        pdfmetrics.registerFont(TTFont(font, str(path)))
    pdfmetrics.registerFontFamily("DejaVuSans", normal="DejaVuSans", bold="DejaVuSans-Bold", italic="DejaVuSans", boldItalic="DejaVuSans-Bold")


def styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName="DejaVuSans", textColor=INK, alignment=TA_LEFT)
    return {
        "title": ParagraphStyle("title", fontSize=26, leading=32, fontName="DejaVuSans-Bold", textColor=BRAND, spaceAfter=10),
        "subtitle": ParagraphStyle("subtitle", fontSize=13, leading=18, textColor=MUTED, fontName="DejaVuSans", spaceAfter=6),
        "h1": ParagraphStyle("h1", fontSize=16, leading=21, fontName="DejaVuSans-Bold", textColor=BRAND, spaceBefore=14, spaceAfter=8, keepWithNext=1),
        "h2": ParagraphStyle("h2", fontSize=12, leading=16, fontName="DejaVuSans-Bold", textColor=INK, spaceBefore=10, spaceAfter=5, keepWithNext=1),
        "p": ParagraphStyle("p", fontSize=9.5, leading=14, spaceAfter=6, **base),
        "li": ParagraphStyle("li", fontSize=9.5, leading=14, leftIndent=14, bulletIndent=2, spaceAfter=3, **base),
        "cell": ParagraphStyle("cell", fontSize=8.6, leading=12, **base),
        "cellb": ParagraphStyle("cellb", fontSize=8.6, leading=12, fontName="DejaVuSans-Bold", textColor=INK),
        "head": ParagraphStyle("head", fontSize=8.6, leading=12, fontName="DejaVuSans-Bold", textColor=colors.white),
        "code": ParagraphStyle("code", fontSize=7.2, leading=9.8, fontName="DejaVuMono", textColor=INK),
        "note": ParagraphStyle("note", fontSize=9, leading=13, **base),
    }


S = {}


def P(text: str, style: str = "p") -> Paragraph:
    return Paragraph(text, S[style])


def bullets(items: list[str]) -> list[Paragraph]:
    return [Paragraph(item, S["li"], bulletText="•") for item in items]


def numbered(items: list[str]) -> list[Paragraph]:
    return [Paragraph(item, S["li"], bulletText=f"{i}.") for i, item in enumerate(items, start=1)]


TOO_LONG: list[str] = []
MAX_CODE_COLS = 104  # столько знаков моноширинного шрифта 7,2 pt помещается в рамку


def code(text: str) -> Table:
    for line in text.strip("\n").splitlines():
        if len(line) > MAX_CODE_COLS:
            TOO_LONG.append(f"{len(line)}: {line[:90]}")
    box = Table([[Preformatted(text.strip("\n"), S["code"])]], colWidths=[17 * cm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return box


def callout(text: str, kind: str = "warn") -> Table:
    bg = WARN_BG if kind == "warn" else OK_BG
    edge = colors.HexColor("#d98a1f") if kind == "warn" else colors.HexColor("#2e8b57")
    box = Table([[Paragraph(text, S["note"])]], colWidths=[17 * cm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg), ("LINEBEFORE", (0, 0), (0, -1), 3, edge),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return box


def table(rows: list[list[str]], widths: list[float], header: bool = True) -> Table:
    data = []
    for r, row in enumerate(rows):
        style = "head" if header and r == 0 else "cell"
        data.append([Paragraph(cell, S[style]) for cell in row])
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1 if header else 0)
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), BRAND))
        commands += [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#faf9fd")) for i in range(2, len(rows), 2)]
    t.setStyle(TableStyle(commands))
    return t


def build(path: Path, title: str, flow: list, version: str) -> None:
    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont("DejaVuSans", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(2 * cm, 1.2 * cm, f"Цифровой куратор · КАИТ №20 · версия {version} · {title}")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"стр. {doc.page}")
        canvas.setStrokeColor(LINE)
        canvas.line(2 * cm, 1.6 * cm, A4[0] - 2 * cm, 1.6 * cm)
        canvas.restoreState()

    doc = BaseDocTemplate(str(path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2.2 * cm,
                          title=title, author="Проект «Цифровой куратор»")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=decorate)])
    doc.build(flow)


def read(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8").rstrip("\n")


def project_version() -> str:
    return tomllib.loads((REPO / "backend" / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def cover(title: str, subtitle: str, version: str, lines: list[str]) -> list:
    today = datetime.date.today().strftime("%d.%m.%Y")
    out = [Spacer(1, 4.5 * cm), P("Цифровой куратор", "subtitle"), P(title, "title"), P(subtitle, "subtitle"), Spacer(1, 1 * cm)]
    out.append(table([["Версия платформы", version], ["Дата документа", today], *lines], [4.5, 12.5], header=False))
    out.append(PageBreak())
    return out


# ---------------------------------------------------------------------------------------------------------------
# Книга 1. Инструкция системному администратору
# ---------------------------------------------------------------------------------------------------------------

ENV_SERVER = """
# /opt/kait20/backend/.env   (владелец kait20, права 600)
ENVIRONMENT=production

DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=kait20
DB_PASSWORD=<пароль пользователя БД>
DB_NAME=kait20

# Случайная строка не короче 32 символов (команда генерации — в п. 4.6)
JWT_SECRET=<сгенерировать>
# Ключ шифрования особых полей досье (здоровье, соц. статус, учёт). Хранить ОТДЕЛЬНО от БД и не менять!
DOSSIER_ENCRYPTION_KEY=<сгенерировать или взять действующий — см. п. 3.3>

# Логин и ВРЕМЕННЫЙ пароль первого администратора; при первом входе платформа потребует сменить пароль
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<временный пароль>

# Перед приложением стоит ровно один прокси (Apache)
TRUSTED_PROXY_COUNT=1
NOTIFICATION_TIMEZONE=Europe/Moscow
# Пул соединений с БД (по умолчанию 10 + 20 запасных); должен укладываться в max_connections MySQL
# DB_POOL_SIZE=10
# DB_MAX_OVERFLOW=20
"""

SQL_CREATE = """
-- Выполнить от имени администратора MySQL (mysql -u root -p)
CREATE DATABASE kait20 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kait20'@'localhost'  IDENTIFIED BY '<пароль>';
CREATE USER 'kait20'@'127.0.0.1' IDENTIFIED BY '<пароль>';
GRANT ALL PRIVILEGES ON kait20.* TO 'kait20'@'localhost';
GRANT ALL PRIVILEGES ON kait20.* TO 'kait20'@'127.0.0.1';
FLUSH PRIVILEGES;
"""


def admin_guide(version: str) -> list:
    f: list = []
    f += cover(
        "Инструкция по развёртыванию на рабочем сервере", "для системного администратора организации", version,
        [["Целевая среда", "MySQL 8.1.0 · Python 3.14 · Apache 2.4 (обратный прокси) · без Docker и без дополнительных сервисов"],
         ["Версии ПО на сервере", "Не обновляются: Python 3.14 и MySQL 8.1.0 остаются как есть"],
         ["Что получает администратор", "Архив kait20-" + version + ".zip (+ файл .sha256) и этот документ"]],
    )

    f.append(P("Содержание", "h1"))
    f += numbered([
        "Как устроена платформа и что она требует", "Что нужно на сервере", "Что и как переносить",
        "Установка: шаг за шагом", "Эксплуатация: запуск, логи, резервные копии, обновление",
        "Безопасность и требования к окружению", "Первичная загрузка групп, студентов и кураторов",
        "Типичные проблемы и их решение", "Результаты проверки готовности",
        "Приложения: конфигурации (Apache, systemd, резервное копирование)",
    ])
    f.append(PageBreak())

    # 1 -----------------------------------------------------------------------------------------------------------
    f.append(P("1. Как устроена платформа", "h1"))
    f.append(P("Платформа — <b>одно приложение</b>: сервер Python (FastAPI) сам отдаёт и интерфейс (готовые файлы уже внутри архива), "
               "и данные (API). Никаких отдельных веб-серверов для статики, очередей, кэшей и планировщиков нет. "
               "Apache нужен только как точка входа по HTTPS и обратный прокси."))
    f.append(table([
        ["Звено", "Что делает", "Адрес"],
        ["Браузер пользователя", "Работает только с вашим доменом; сторонних сайтов, шрифтов и CDN платформа не использует", "https://&lt;домен&gt;/"],
        ["Apache 2.4", "HTTPS, перенаправление с http, обратный прокси на приложение", "порты 80 и 443"],
        ["Приложение kait20", "Python 3.14, один процесс (служба systemd), интерфейс + API", "127.0.0.1:8000 (только локально)"],
        ["MySQL 8.1.0", "Все данные; таблицы создаются и обновляются автоматически при запуске (миграции)", "127.0.0.1:3306"],
    ], [3.6, 9.4, 4.0]))
    f.append(Spacer(1, 6))
    f += bullets([
        "<b>Запускать нужно ровно один экземпляр приложения.</b> Счётчик неудачных попыток входа хранится в памяти процесса; "
        "несколько экземпляров считали бы его раздельно. Для нагрузки колледжа (около тысячи студентов и сотни кураторов) одного процесса достаточно.",
        "Планировщика заданий нет: напоминания и периодические задачи выполняются, когда кто-то открывает платформу. Отдельный cron для приложения не нужен "
        "(cron нужен только для резервных копий).",
        "Исходящий доступ в интернет приложению <b>не нужен</b> (Sentry по умолчанию выключен).",
        "Apache должен передавать в приложение <b>все</b> адреса без исключения (в том числе страницы интерфейса). Приложение само отличает "
        "открытие страницы в браузере от запроса данных по заголовкам браузера (Sec-Fetch-Dest / Accept), поэтому раздавать часть файлов из Apache "
        "или подменять ошибки прокси (ProxyErrorOverride) нельзя — страницы перестанут открываться по прямой ссылке или после обновления (F5).",
    ])

    # 2 -----------------------------------------------------------------------------------------------------------
    f.append(P("2. Что нужно на сервере", "h1"))
    f.append(table([
        ["Компонент", "Требование", "Комментарий"],
        ["Python", "<b>3.14.x</b> (уже установлен, не обновлять)", "Приложение не запустится на другой версии — это проверка на старте. Нужен модуль venv "
         "(в Debian/Ubuntu — пакет python3.14-venv, если его нет)."],
        ["MySQL", "<b>8.1.0</b> (уже установлен, не обновлять), кодировка utf8mb4", "Используются только стандартные возможности MySQL 8.0+. "
         "max_connections — не меньше 60 (пул приложения до 30 соединений + запас для резервного копирования и обслуживания)."],
        ["Apache", "2.4 с модулями <b>proxy, proxy_http, headers, ssl</b>", "Если модули не включены: a2enmod proxy proxy_http headers ssl (Debian/Ubuntu) "
         "либо LoadModule в httpd.conf (RHEL-семейство)."],
        ["Сертификат TLS", "для домена платформы", "Без HTTPS вход работать не будет (см. раздел 6)."],
        ["Шрифт DejaVu Sans", "пакет fonts-dejavu-core (или аналог)", "Нужен только для кириллицы в PDF-выгрузках."],
        ["Клиент MySQL", "mysql и mysqldump", "Для создания БД и резервных копий; обычно ставятся вместе с сервером."],
        ["Синхронизация времени", "chrony или systemd-timesyncd", "Платформа считает «сегодня», сроки сдачи и подачи питания по времени сервера."],
        ["Ресурсы", "1–2 vCPU, 2 ГБ ОЗУ, 5 ГБ диска", "Файлы приложения занимают около 4 МБ, виртуальное окружение — несколько сотен МБ; остальное — база и копии."],
    ], [3.0, 5.4, 8.6]))
    f.append(Spacer(1, 6))
    f.append(P("<b>Устанавливать дополнительно не нужно:</b> Node.js и npm (интерфейс уже собран), Docker, компилятор и заголовочные файлы "
               "(все Python-пакеты ставятся готовыми колёсами — проверено для Linux x86_64 и Python 3.14), mod_wsgi, Redis, RabbitMQ, "
               "Nginx. Подключения к внешним сервисам не используются."))

    # 3 -----------------------------------------------------------------------------------------------------------
    f.append(P("3. Что и как переносить", "h1"))
    f.append(P("3.1. Передаваемый комплект", "h2"))
    f.append(table([
        ["Что", "Откуда", "Куда"],
        ["Архив kait20-" + version + ".zip и kait20-" + version + ".zip.sha256", "готовит разработчик: python tools/build_release.py", "на сервер, в /tmp"],
        ["Этот документ", "—", "администратору"],
        ["Файлы vhost, службы и резервного копирования (приложения A–C)", "docs/deploy в репозитории или текст из приложений", "см. раздел 4"],
        ["Файлы с данными для загрузки (реестр контингента, список кураторов)", "передаются отдельно, НЕ через git и НЕ в составе архива", "/var/lib/kait20/import"],
    ], [7.0, 6.0, 4.0]))
    f.append(Spacer(1, 4))
    f.append(P("Внутри архива две папки: <b>backend</b> (приложение: код, готовый интерфейс в backend/static, миграции БД, скрипты загрузки данных, "
               "список зависимостей requirements.txt, шаблон настроек .env.example) и <b>frontend</b> (исходники интерфейса — на сервере не нужны, "
               "их можно не распаковывать). Тестов, файлов с реальными данными и секретов в архиве нет."))
    f.append(P("3.2. Что НЕ переносится", "h2"))
    f += bullets([
        "Файл .env разработки и любые пароли тестового окружения. Для рабочего сервера создаются <b>новые</b> секреты.",
        "Каталог .venv, node_modules, кэши — виртуальное окружение создаётся на самом сервере.",
        "Файлы с реальными ФИО в репозиторий не попадают (они в .gitignore) и передаются администратору отдельно защищённым каналом.",
    ])
    f.append(P("3.3. Данные: два сценария", "h2"))
    f.append(table([
        ["Сценарий", "Когда выбирать", "Что делать с ключами"],
        ["<b>А. Чистая установка</b> (рекомендуется)", "Рабочий сервер стартует с пустой базы; группы, студентов и кураторов загружают из файлов (раздел 7).",
         "Создать <b>новые</b> JWT_SECRET и DOSSIER_ENCRYPTION_KEY, сохранить ключ шифрования в сейфе отдельно от резервных копий БД."],
        ["<b>Б. Перенос действующей тестовой базы</b>", "На тестовой платформе уже заведены пользователи, отметки посещаемости, досье, которые нужно сохранить.",
         "DOSSIER_ENCRYPTION_KEY должен быть <b>тем же</b>, что на тестовой платформе, иначе особые поля досье не расшифровать. "
         "JWT_SECRET — новый (все сессии пользователей сбросятся, это нормально)."],
    ], [4.2, 7.0, 5.8]))
    f.append(Spacer(1, 4))
    f.append(P("Порядок для сценария Б: на источнике снять дамп "
               "<font name='DejaVuMono'>mysqldump --single-transaction --no-tablespaces --routines --triggers --default-character-set=utf8mb4 &lt;база&gt; | gzip &gt; kait20.sql.gz</font>, "
               "передать файл защищённым каналом, на сервере создать пустую БД (п. 4.3) и выполнить "
               "<font name='DejaVuMono'>zcat kait20.sql.gz | mysql kait20</font> <b>до первого запуска приложения</b>; затем запустить приложение — "
               "оно доведёт схему до актуальной версии автоматически. Сначала отработайте перенос на тестовой копии: версия MySQL на источнике может отличаться "
               "от 8.1.0."))
    f.append(callout("<b>Важно.</b> Ключ DOSSIER_ENCRYPTION_KEY нельзя терять и менять: без него сохранённые особые данные досье не прочитать, "
                     "а резервная копия БД без ключа для этих полей бесполезна. Храните ключ отдельно от копий базы.", "warn"))

    # 4 -----------------------------------------------------------------------------------------------------------
    f.append(PageBreak())
    f.append(P("4. Установка: шаг за шагом", "h1"))
    f.append(P("Команды приведены для Linux (Debian/Ubuntu); для RHEL-семейства отличаются только команды установки пакетов и пути конфигурации Apache. "
               "Здесь и далее <font name='DejaVuMono'>kurator.example.ru</font> — замените на реальный домен платформы."))
    f.append(P("4.1. Проверка версий (ничего не обновляя)", "h2"))
    f.append(code("""
python3.14 --version          # должно быть Python 3.14.x
mysql --version               # должно быть 8.1.0
apache2ctl -v                 # 2.4.x   (RHEL: httpd -v)
apache2ctl -M | grep -E 'proxy|headers|ssl'   # нужны: proxy, proxy_http, headers, ssl
"""))
    f.append(P("4.2. Пользователь и каталоги", "h2"))
    f.append(code("""
sudo useradd --system --home /opt/kait20 --shell /usr/sbin/nologin kait20
sudo mkdir -p /opt/kait20 /var/lib/kait20/import /var/backups/kait20
sudo chown kait20:kait20 /opt/kait20 /var/lib/kait20 /var/lib/kait20/import /var/backups/kait20
sudo chmod 700 /var/lib/kait20/import /var/backups/kait20
"""))
    f.append(P("4.3. База данных", "h2"))
    f.append(code(SQL_CREATE))
    f.append(P("Пароль в команды вставляется один раз и дальше хранится только в .env (п. 4.6) и в ~/.my.cnf пользователя kait20 (для резервных копий). "
               "Миграции при запуске создают и изменяют таблицы, поэтому пользователю приложения нужны права на всю БД kait20 (как выше)."))
    f.append(P("4.4. Распаковка и проверка целостности", "h2"))
    f.append(code("""
cd /tmp
sha256sum -c kait20-""" + version + """.zip.sha256              # должно быть: OK
sudo -u kait20 unzip -q kait20-""" + version + """.zip 'backend/*' -d /opt/kait20
ls /opt/kait20/backend         # app, alembic, scripts, static, requirements.txt, .env.example
"""))
    f.append(P("4.5. Виртуальное окружение и зависимости", "h2"))
    f.append(code("""
cd /opt/kait20/backend
sudo -u kait20 python3.14 -m venv .venv
sudo -u kait20 .venv/bin/pip install --require-hashes -r requirements.txt
"""))
    f.append(P("Ключ <font name='DejaVuMono'>--require-hashes</font> заставляет pip проверять подлинность каждого пакета по хэшу из requirements.txt. "
               "Сервер при установке обращается к индексу пакетов (pypi.org) — если прямого доступа в интернет нет, см. последнюю строку таблицы в разделе 8."))
    f.append(P("4.6. Настройки (.env)", "h2"))
    f.append(code("""
sudo -u kait20 cp /opt/kait20/backend/.env.example /opt/kait20/backend/.env
sudo chmod 600 /opt/kait20/backend/.env
# Генерация секретов (вывод вставить в .env; ключ шифрования — ещё и в сейф):
PY=/opt/kait20/backend/.venv/bin/python
$PY -c "import secrets; print(secrets.token_urlsafe(48))"
$PY -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""))
    f.append(P("Содержимое .env для рабочего сервера:"))
    f.append(code(ENV_SERVER))
    f.append(P("4.7. Пробный запуск вручную", "h2"))
    f.append(code("""
cd /opt/kait20/backend
sudo -u kait20 env HOST=127.0.0.1 .venv/bin/python -m scripts.entrypoint
# Ожидаемо: «База доступна» → «Миграции...» → «Справочники...» → «Запуск приложения...»
# В другом окне:   curl http://127.0.0.1:8000/health      →   {"status":"ok"}
# Остановить: Ctrl+C
"""))
    f.append(P("Скрипт запуска сам дожидается базы, применяет миграции, создаёт справочники и администратора и запускает приложение. "
               "Если JWT_SECRET слабый или версия Python не 3.14, он остановится с понятным сообщением."))
    f.append(P("4.8. Служба systemd", "h2"))
    f.append(P("Файл — в приложении B (docs/deploy/kait20.service). Установка:"))
    f.append(code("""
sudo cp kait20.service /etc/systemd/system/kait20.service
sudo systemctl daemon-reload
sudo systemctl enable --now kait20
sudo systemctl status kait20            # active (running)
journalctl -u kait20 -n 50 --no-pager   # журнал запуска
"""))
    f.append(P("4.9. Apache", "h2"))
    f.append(P("Файл — в приложении A (docs/deploy/kait20-apache.conf): впишите домен и пути к сертификату.", "p"))
    f.append(code("""
sudo cp kait20-apache.conf /etc/apache2/sites-available/kait20.conf
#   (RHEL-семейство: /etc/httpd/conf.d/kait20.conf)
sudo a2enmod proxy proxy_http headers ssl
sudo a2ensite kait20
sudo apache2ctl configtest              # должно быть: Syntax OK
sudo systemctl reload apache2
"""))
    f.append(P("4.10. Проверка после установки (чек-лист приёмки)", "h2"))
    f.append(table([
        ["№", "Проверка", "Ожидаемый результат"],
        ["1", "systemctl status kait20; journalctl -u kait20", "active (running), в журнале нет ошибок"],
        ["2", "curl http://127.0.0.1:8000/health на сервере", "{\"status\":\"ok\"}"],
        ["3", "Порт 8000 снаружи (с другого компьютера)", "НЕ отвечает (слушает только 127.0.0.1)"],
        ["4", "http://&lt;домен&gt;/ в браузере", "Перенаправление на https, открывается экран входа"],
        ["5", "Вход admin с временным паролем из .env", "Платформа просит задать новый пароль; после смены открывается рабочий экран"],
        ["6", "Обновить страницу (F5) на внутренней странице, например /admin", "Открывается интерфейс (не текст с JSON и не ошибка)"],
        ["7", "Админка → Витрины, любая выгрузка в Excel и PDF", "Файл скачивается, кириллица в PDF читается"],
        ["8", "Админка → Пользователи → профиль → «Выдать пароль»", "Временный пароль показывается"],
        ["9", "Остановить приложение (systemctl stop kait20) и открыть сайт", "Apache отвечает 503/502; после запуска всё работает без других действий"],
        ["10", "Перезагрузить сервер", "kait20, MySQL и Apache поднимаются сами; сайт открывается"],
    ], [0.9, 8.1, 8.0]))
    f.append(P("4.11. Первый вход", "h2"))
    f.append(P("Логин — значение ADMIN_USERNAME, пароль — ADMIN_PASSWORD из .env. Пароль <b>временный</b>: при первом входе платформа требует задать новый. "
               "После смены пароля строку ADMIN_PASSWORD из .env рекомендуется удалить (файл прочитан только при создании администратора)."))

    # 5 -----------------------------------------------------------------------------------------------------------
    f.append(PageBreak())
    f.append(P("5. Эксплуатация", "h1"))
    f.append(P("5.1. Ежедневное", "h2"))
    f.append(table([
        ["Задача", "Команда"],
        ["Состояние", "systemctl status kait20"],
        ["Журнал приложения (последние 100 строк / в реальном времени)", "journalctl -u kait20 -n 100 --no-pager   /   journalctl -u kait20 -f"],
        ["Перезапуск (после изменения .env)", "sudo systemctl restart kait20"],
        ["Журналы Apache", "/var/log/apache2/kait20-error.log и kait20-access.log (RHEL: /var/log/httpd)"],
        ["Проверка доступности (для мониторинга)", "GET https://&lt;домен&gt;/health → 200"],
    ], [7.0, 10.0]))
    f.append(P("5.2. Резервное копирование", "h2"))
    f.append(P("Скрипт — приложение C (docs/deploy/kait20-backup.sh). Делает сжатый дамп БД, проверяет, что архив читается и содержит таблицы, "
               "хранит 30 дней. Настройка:"))
    f.append(code("""
sudo cp kait20-backup.sh /opt/kait20/kait20-backup.sh && sudo chmod 755 /opt/kait20/kait20-backup.sh
# учётные данные для mysqldump (чтобы пароль не светился в списке процессов):
sudo -u kait20 sh -c 'printf "[client]\\nuser=kait20\\npassword=<пароль БД>\\n" > ~/.my.cnf'
sudo -u kait20 chmod 600 ~kait20/.my.cnf
# ежедневно в 02:30:
echo '30 2 * * * kait20 /opt/kait20/kait20-backup.sh >>/var/log/kait20-backup.log 2>&1' \\
  | sudo tee /etc/cron.d/kait20-backup
"""))
    f.append(callout("Копии БД нужно <b>выносить с этого сервера</b> (сетевая папка, ленточное хранилище, другой сервер): потеря диска уничтожит и базу, и копии. "
                     "Ключ DOSSIER_ENCRYPTION_KEY и файл .env копируются отдельно и хранятся в сейфе.", "warn"))
    f.append(P("5.3. Восстановление (проверить хотя бы один раз до ввода в эксплуатацию)", "h2"))
    f.append(code("""
sudo systemctl stop kait20
mysql -e "DROP DATABASE kait20; CREATE DATABASE kait20 \\
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
zcat /var/backups/kait20/kait20-<дата>.sql.gz | mysql kait20
sudo systemctl start kait20
"""))
    f.append(P("5.4. Обновление версии платформы", "h2"))
    f.append(code("""
# 1. резервная копия БД и копия текущей папки приложения
sudo -u kait20 /opt/kait20/kait20-backup.sh
sudo cp -a /opt/kait20/backend /opt/kait20/backend.prev
# 2. остановить, заменить код (сохранив .env и .venv), обновить зависимости, запустить
sudo systemctl stop kait20
cd /tmp && sha256sum -c kait20-<версия>.zip.sha256
sudo -u kait20 unzip -q kait20-<версия>.zip 'backend/*' -d /tmp/kait20-new
sudo rsync -a --exclude .env --exclude .venv /tmp/kait20-new/backend/ /opt/kait20/backend/
sudo chown -R kait20:kait20 /opt/kait20/backend
cd /opt/kait20/backend && sudo -u kait20 .venv/bin/pip install --require-hashes -r requirements.txt
sudo systemctl start kait20 && curl -s http://127.0.0.1:8000/health
"""))
    f.append(P("Миграции БД применяются при запуске автоматически. <b>Откат:</b> миграции работают только вперёд, поэтому откат — это возврат прежней папки "
               "(backend.prev) <u>вместе с восстановлением БД из копии, снятой перед обновлением</u> (п. 5.3)."))

    # 6 -----------------------------------------------------------------------------------------------------------
    f.append(P("6. Безопасность и требования к окружению", "h1"))
    f.append(P("Что уже сделано в приложении (проверено): сессия — HttpOnly-cookie с флагами Secure и SameSite=Strict; защита от подбора пароля — блокировка "
               "по связке «адрес + логин» (учётную запись мошенник заблокировать не может), для администраторов и руководителей лимит строже; "
               "заголовки HSTS, Content-Security-Policy (только свои ресурсы), X-Frame-Options; Swagger и схема API в рабочем режиме выключены; "
               "пароли хранятся в виде хэшей Argon2; особые данные досье шифруются; просмотр особых данных пишется в журнал."))
    f.append(P("<b>От администратора требуется:</b>", "p"))
    f += bullets([
        "<b>Только HTTPS.</b> Cookie сессии помечена Secure: по обычному http браузер её отбросит, и вход «не запомнится». "
        "Если на время запуска сертификата нет, в .env можно временно добавить <font name='DejaVuMono'>SESSION_COOKIE_SECURE=false</font> — "
        "с реальными данными так работать нельзя.",
        "Приложение слушает только 127.0.0.1 (так настроена служба); порт 8000 в файрволе наружу не открывать. MySQL — тоже только локально (bind-address=127.0.0.1), "
        "если сервер БД не вынесен отдельно.",
        "Права: .env — 600 (владелец kait20); ~/.my.cnf — 600; /var/lib/kait20/import и /var/backups/kait20 — 700.",
        "TRUSTED_PROXY_COUNT=1, если перед приложением ровно один Apache. Если между Apache и пользователями есть ещё балансировщик — значение 2; "
        "если приложение вдруг доступно напрямую без прокси — 0. Неверное значение ломает лимит попыток входа (все пользователи сольются в один адрес).",
        "Файлы с реальными ФИО (реестр, списки кураторов) после загрузки удалять с сервера (<font name='DejaVuMono'>shred -u</font> или стандартное безопасное удаление).",
        "Регулярные обновления ОС и Apache — как обычно; <b>Python 3.14 и MySQL 8.1.0 не обновлять</b> без согласования с разработчиком.",
    ])

    # 7 -----------------------------------------------------------------------------------------------------------
    f.append(P("7. Первичная загрузка групп, студентов и кураторов", "h1"))
    f.append(P("В платформе нет экрана массовой загрузки контингента; загрузка выполняется <b>командами на сервере</b> из файлов Excel и текста. "
               "Все команды по умолчанию работают в режиме проверки (ничего не пишут), запись включается ключом <font name='DejaVuMono'>--apply</font>; "
               "повторный запуск тех же данных ничего не меняет. Загрузка не требует обновления версии платформы и остановки сайта."))
    f.append(P("7.1. Форматы файлов", "h2"))
    f.append(table([
        ["Файл", "Формат", "Что обязательно"],
        ["registry.xlsx — реестр контингента", "Excel, первый лист; строка заголовка ищется по названиям колонок, остальные колонки (телефон, почта) игнорируются и в базу не попадают",
         "Колонки: <b>ФИО</b>; <b>Статус обучения</b> («Обучается» или «В академическом отпуске»); <b>Учебная группа</b> (например ИИ112-26 — хвост «-26» или «.8» отбрасывается); "
         "<b>Адрес площадки</b> (по нему определяется отделение; известные адреса зашиты в скрипт); <b>Курс обучения</b> («1 курс»)"],
        ["curators.tsv — кураторы", "Текст UTF-8, значения через табуляцию, одна строка = одна группа; один куратор может вести несколько групп",
         "ФИО ⇥ код группы ⇥ отделение. Куратор создаётся без пароля, логин — фамилия.инициал латиницей"],
    ], [4.0, 6.0, 7.0]))
    f.append(P("7.2. Порядок", "h2"))
    f.append(code("""
# файлы положить в /var/lib/kait20/import (владелец kait20, права 600)
sudo -u kait20 /opt/kait20/kait20-backup.sh        # 0. резервная копия — ОБЯЗАТЕЛЬНО
cd /opt/kait20/backend
RUN="sudo -u kait20 .venv/bin/python -m"
DATA=/var/lib/kait20/import
$RUN scripts.import_registry $DATA/registry.xlsx            # 1. реестр: проверка (ничего не пишет)
$RUN scripts.import_registry $DATA/registry.xlsx --apply    # 2. реестр: запись
$RUN scripts.import_curators $DATA/curators.tsv             # 3. кураторы: проверка
$RUN scripts.import_curators $DATA/curators.tsv --apply     # 4. кураторы: запись
$RUN scripts.hide_groups --apply                            # 5. скрыть группы со строчной «о» в коде
sudo shred -u $DATA/*                                       # 6. удалить файлы с ФИО
"""))
    f.append(callout("<b>Реестр удаляет.</b> Студенты, которых нет в файле реестра, <b>полностью удаляются</b> из базы вместе с отметками посещаемости, "
                     "периодами отсутствия и записями о группах; их ФИО в журнале аудита затираются необратимо. Поэтому: сначала резервная копия, потом "
                     "проверка (без --apply) и сверка отчёта с ожидаемыми цифрами, и только потом запись. Кураторов и их назначения реестр не трогает.", "warn"))
    f.append(P("После загрузки кураторов у них <b>нет паролей</b>: администратор платформы выдаёт временный пароль каждому "
               "(Админка → Пользователи → профиль → «Выдать пароль»); при первом входе куратор задаёт свой."))
    f.append(P("Варианты развития механизма загрузки (экран в платформе, единый шаблон Excel, выдача паролей списком) описаны в отдельном документе "
               "«Загрузка контингента и кураторов: анализ и варианты»."))

    # 8 -----------------------------------------------------------------------------------------------------------
    f.append(P("8. Типичные проблемы и их решение", "h1"))
    f.append(table([
        ["Симптом", "Причина", "Что сделать"],
        ["Приложение не запускается: «JWT_SECRET не задан или слишком короткий»", "Секрет пустой/предсказуемый", "Сгенерировать JWT_SECRET (п. 4.6), перезапустить"],
        ["«Требуется Python &gt;=3.14,&lt;3.15»", "venv создан другой версией Python", "Пересоздать venv командой python3.14 -m venv"],
        ["«DOSSIER_ENCRYPTION_KEY некорректен»", "Ключ испорчен при копировании", "Ключ Fernet — 44 символа, заканчивается на «=»; вставить без пробелов и кавычек"],
        ["Apache отвечает 502/503", "Служба kait20 не запущена или падает", "systemctl status kait20; journalctl -u kait20 -n 100"],
        ["Вход проходит, но сразу выбрасывает на экран входа", "Сайт открыт по http, а cookie помечена Secure", "Настроить HTTPS (раздел 6)"],
        ["Обновление страницы (F5) показывает текст «Нужна авторизация» или ошибку", "Apache подменяет ответы или не передаёт заголовки браузера", "Убрать ProxyErrorOverride и любые Rewrite/Alias, пропускающие часть адресов мимо прокси"],
        ["«Слишком много попыток входа» у всех сразу", "Неверный TRUSTED_PROXY_COUNT: приложение видит всех с одного адреса", "Поставить число прокси перед приложением (обычно 1)"],
        ["В логе «QueuePool limit … reached»", "Исчерпан пул соединений с БД", "Увеличить DB_POOL_SIZE/DB_MAX_OVERFLOW и max_connections MySQL, перезапустить"],
        ["В PDF вместо кириллицы квадраты", "Нет шрифта DejaVu Sans", "Установить fonts-dejavu-core, перезапустить службу"],
        ["Время «сегодня» отличается на несколько часов", "Часовой пояс/синхронизация", "Проверить NOTIFICATION_TIMEZONE и chrony; перезапустить"],
        ["pip install не может скачать пакеты", "Нет доступа к pypi.org", "Скачать колёса на компьютере с интернетом: pip download -r requirements.txt --only-binary=:all: --python-version 3.14 -d wheels, перенести папку и ставить с --no-index --find-links wheels --require-hashes"],
    ], [5.3, 5.2, 6.5]))

    # 9 -----------------------------------------------------------------------------------------------------------
    f.append(P("9. Результаты проверки готовности", "h1"))
    f.append(P("Перед подготовкой этого документа проведена проверка репозитория, конфигурации и сборки. Итог:"))
    f.append(table([
        ["Область", "Результат"],
        ["Сборка архива для сервера (tools/build_release.py)", "Найдено и исправлено: служебный комментарий в коде содержал название стороннего хостинга, из-за чего сборка архива останавливалась. После исправления архив собирается (344 файла, 2,4 МБ), без тестов, секретов и Docker-файлов."],
        ["Зависимости на Python 3.14", "Все 41 пакет из requirements.txt получены готовыми колёсами для Linux x86_64 / CPython 3.14: компилятор на сервере не нужен. Для другой архитектуры (например ARM) нужна отдельная проверка."],
        ["Работа за Apache", "Проверено на живом Apache 2.4 с TLS: проксирование, перенаправление http→https, открытие страниц по прямому адресу и обновление (F5), вход (cookie Secure + HttpOnly + SameSite=Strict), заголовки HSTS и CSP, выгрузки Excel. Приложены проверенные файлы конфигурации."],
        ["Вход по http без сертификата", "Раньше при ENVIRONMENT=production вход по http не работал вообще (браузер отбрасывал Secure-cookie). Добавлена настройка SESSION_COOKIE_SECURE (по умолчанию включено; временно можно выключить)."],
        ["Загрузка файлов больше 5 МБ", "Через Apache отказ приходил общей ошибкой 500 вместо понятного сообщения. Теперь размер проверяется в интерфейсе заранее."],
        ["Резервное копирование", "В скрипте добавлен --no-tablespaces: без него mysqldump на MySQL 8.0+ под обычным пользователем БД завершается ошибкой (нужна привилегия PROCESS)."],
        ["Скрипты загрузки контингента и кураторов", "Проверены на синтетических данных: пробный режим, запись, повторный запуск (идемпотентность). Ограничения описаны в разделе 7."],
        ["MySQL 8.1.0", "Автоматические тесты платформы в CI идут на MySQL 8.4 и на SQLite; на 8.1.0 они не запускались. В коде и миграциях используются только стандартные возможности MySQL 8.0+ (без JSON-колонок, функциональных индексов и специфичного синтаксиса 8.4), поэтому несовместимости не ожидается, но <b>первый запуск на тестовой копии БД обязателен</b> (п. 4.7)."],
        ["Не проверялось", "Установка на самом рабочем сервере и под systemd (шаблон службы составлен по документации, не запускался на реальной машине); Windows-сервер; ARM; нагрузочные испытания на реальном числе пользователей."],
    ], [5.0, 12.0]))

    # Приложения --------------------------------------------------------------------------------------------------
    f.append(PageBreak())
    f.append(P("Приложение A. Виртуальный хост Apache (docs/deploy/kait20-apache.conf)", "h1"))
    f.append(code(read("kait20-apache.conf")))
    f.append(PageBreak())
    f.append(P("Приложение B. Служба systemd (docs/deploy/kait20.service)", "h1"))
    f.append(code(read("kait20.service")))
    f.append(P("Приложение C. Резервное копирование (docs/deploy/kait20-backup.sh)", "h1"))
    f.append(code(read("kait20-backup.sh")))
    return f


# ---------------------------------------------------------------------------------------------------------------
# Книга 2. Загрузка данных: анализ и варианты
# ---------------------------------------------------------------------------------------------------------------

def data_loading_guide(version: str) -> list:
    f: list = []
    f += cover(
        "Загрузка контингента и кураторов", "анализ и варианты решения для рабочего сервера", version,
        [["Вопрос", "Как загружать группы, студентов и кураторов большими пачками на рабочем сервере — без выпуска новой версии платформы"],
         ["Статус", "Документ для принятия решения; реализация вариантов 2–3 не начата"]],
    )

    f.append(P("1. Постановка задачи", "h1"))
    f.append(P("На рабочем сервере платформа будет работать с настоящим контингентом колледжа (сегодня — около 1000 студентов, 44 группы, 6 отделений). "
               "Нужен способ <b>загружать и обновлять</b> эти данные большими пачками — при старте учебного года, при переводах между курсами, при появлении новых групп "
               "и смене кураторов — <b>не выпуская новую версию платформы</b> и не вручную по одной записи."))
    f.append(P("<b>Критерии, по которым сравниваются варианты:</b>", "p"))
    f += bullets([
        "не требует обновления кода платформы для каждой загрузки (данные — отдельно от версии);",
        "безопасность данных: реальные ФИО не попадают в git, файлы не лежат на сервере дольше нужного, действия остаются в журнале;",
        "защита от ошибок: предварительный просмотр («что изменится») до записи; повторная загрузка того же файла ничего не ломает;",
        "кто выполняет: системный администратор через консоль или сотрудник колледжа через сайт;",
        "трудоёмкость реализации и поддержки.",
    ])

    f.append(P("2. Что есть сейчас", "h1"))
    f.append(table([
        ["Инструмент", "Что делает", "Ограничения"],
        ["scripts.import_registry<br/>(реестр контингента, xlsx)", "Создаёт отделения, группы, студентов; переводит между группами; обновляет статус; проверка без --apply; повторный запуск безопасен",
         "Отделение определяется по адресу площадки из жёстко зашитого списка (6 адресов); дата зачисления новых студентов зашита (01.09.2026); "
         "<b>удаляет</b> студентов, которых нет в файле (необратимо); работает только из консоли сервера"],
        ["scripts.import_curators<br/>(список кураторов, tsv)", "Создаёт кураторов и назначает на группы; проверка без --apply; не трогает чужих кураторов",
         "Куратор создаётся <b>без пароля</b> — пароли выдаются по одному вручную; дата начала назначения зашита (01.09.2026); только консоль"],
        ["Загрузка досье из Excel<br/>(экран в платформе)", "Шаблон → файл → предпросмотр с ошибками → применить; работает из браузера",
         "Только дополнение досье (особые поля, представители), не группы и не кураторы; файл до 5 МБ"],
        ["Админка (по одной записи)", "Создание группы, студента, пользователя, назначения", "Для сотен записей непригодна"],
        ["Переменные IMPORT_*_ON_START", "Запуск импорта при старте службы", "Рассчитано на облачный хостинг; на своём сервере проще запускать команды напрямую"],
    ], [4.2, 6.2, 6.6]))

    f.append(P("3. Варианты", "h1"))

    f.append(P("Вариант 1. Оставить консольные скрипты и довести их (минимум работы)", "h2"))
    f.append(P("Администратор кладёт файлы в /var/lib/kait20/import и запускает команды (см. инструкцию, раздел 7). Что стоит доработать (0,5–1 день):"))
    f += bullets([
        "<b>Выдача паролей кураторам списком:</b> ключ --issue-passwords создаёт временные пароли и выгружает файл «ФИО, логин, пароль» для раздачи (сейчас пароли выдаются по одному в интерфейсе);",
        "<b>Предохранитель на удаление:</b> если реестр удалил бы больше заданной доли студентов (например 10%), загрузка останавливается без записи и просит явного подтверждения;",
        "<b>Перенос зашитых значений в настройки:</b> адреса площадок → отделения и даты начала учебного года читаются из файла настроек, а не из кода;",
        "<b>Отчёт в файл:</b> результат проверки сохраняется (создано / переведено / удалено / ошибки) — для сверки и архива.",
    ])
    f.append(table([["Плюсы", "Минусы"], ["Уже работает и проверено; ничего нового на сервере; нет риска для сайта", "Нужен доступ администратора к консоли при каждой загрузке; "
                                                                                                         "нет «красивого» предпросмотра; формат файла привязан к реестру колледжа"]], [8.5, 8.5]))

    f.append(P("Вариант 2. Экран «Импорт» в администрировании платформы", "h2"))
    f.append(P("Администратор платформы загружает файл прямо в браузере (по образцу уже существующей загрузки досье): шаблон → файл → "
               "<b>предпросмотр</b> («создастся 5 групп, 120 студентов, переведётся 14, выбудет 6, ошибок 2 — список») → «Применить». "
               "Каждая загрузка пишется в журнал аудита (кто, когда, сколько изменено). Оценка: 3–5 дней."))
    f += bullets([
        "Запись всегда после предпросмотра; повторная загрузка того же файла безопасна;",
        "вместо необратимого удаления отсутствующих студентов — перевод в статус «отчислен/выбыл» (удаление — отдельным осознанным действием администратора);",
        "после загрузки кураторов — выгрузка временных паролей одним файлом;",
        "файл не хранится на сервере (читается из запроса и сразу обрабатывается), поэтому остатков с ФИО не остаётся;",
        "доступно только роли «администратор»; лимит файла 5 МБ — с большим запасом (1000 студентов ≈ 100 КБ).",
    ])
    f.append(table([["Плюсы", "Минусы"], ["Не нужна консоль сервера и системный администратор; понятно сотруднику колледжа; есть журнал; предпросмотр защищает от ошибок",
                                          "Требует разработки и тестов; нужна аккуратная проверка прав (только админ)"]], [8.5, 8.5]))

    f.append(P("Вариант 3. Единый шаблон Excel (надстройка над вариантами 1 и 2) — рекомендуемая цель", "h2"))
    f.append(P("Вместо привязки к формату реестра колледжа вводится <b>собственный шаблон платформы</b> с тремя листами: «Группы» (код, курс, отделение, финансирование), "
               "«Студенты» (ФИО, группа, статус) и «Кураторы» (ФИО, группа, роль, дата начала). Шаблон скачивается из платформы <b>уже с текущими данными</b>: "
               "сотрудник правит таблицу (добавил строку — новый студент, поменял группу — перевод, поставил статус — выбытие) и загружает обратно. "
               "Одна и та же логика обслуживает и экран (вариант 2), и консольную команду (вариант 1). Оценка: 5–8 дней вместе с вариантом 2."))
    f.append(table([["Плюсы", "Минусы"], ["Не зависит от выгрузки реестра и адресов площадок; удобно обновлять частично (только кураторов или только одну группу); "
                                          "один формат на все случаи", "Самая большая по объёму работа; первичное сопоставление реестра колледжа с шаблоном — разовая подготовка файла"]], [8.5, 8.5]))

    f.append(P("Вариант 4. Загрузка клиентским скриптом через API (с компьютера администратора)", "h2"))
    f.append(P("Скрипт на компьютере администратора читает файл и вызывает уже существующие методы создания групп, студентов и пользователей. "
               "Серверный доступ не нужен, но: нужен токен администратора, загрузка идёт по одной записи (медленно, сотни запросов), логика сверки и отката "
               "оказывается на стороне клиента, нет пакетной транзакции. <b>Не рекомендуется</b> как постоянный механизм."))

    f.append(P("Вариант 5. Прямая загрузка в MySQL (LOAD DATA / mysqlimport + SQL-слияние)", "h2"))
    f.append(P("Файл CSV загружается в промежуточные таблицы и SQL-запросом вливается в рабочие. Максимально быстро для сотен тысяч строк, "
               "но обходит проверки приложения, журнал аудита и шифрование, требует знания схемы БД и не нужен при тысяче студентов. "
               "<b>Только как аварийная мера</b> силами администратора БД."))

    f.append(P("Вариант 6. Перенос действующей тестовой базы целиком (дамп → рабочий сервер)", "h2"))
    f.append(P("Разовая операция, а не механизм: сохраняет всё, что уже заведено на тестовой платформе (пользователей и пароли, группы, студентов, посещаемость, досье). "
               "Условия: тот же DOSSIER_ENCRYPTION_KEY; предварительная репетиция на тестовой копии (версия MySQL источника может отличаться от 8.1.0); дальше "
               "данные обновляются одним из вариантов 1–3. Подробности — в инструкции администратору, п. 3.3."))

    f.append(P("4. Сравнение", "h1"))
    f.append(table([
        ["Вариант", "Кто выполняет", "Предпросмотр", "Журнал", "Без новой версии", "Работа", "Рекомендация"],
        ["1. Скрипты + доработки", "сис. администратор", "режим проверки в консоли", "нет (текстовый отчёт)", "да", "0,5–1 день", "сразу, на старте"],
        ["2. Экран «Импорт»", "администратор платформы", "да, в браузере", "да", "да", "3–5 дней", "основной механизм"],
        ["3. Единый шаблон Excel", "администратор платформы / консоль", "да", "да", "да", "5–8 дней (с п. 2)", "цель"],
        ["4. API-скрипт клиента", "админ с токеном", "нет", "частично", "да", "1–2 дня", "нет"],
        ["5. Прямо в MySQL", "администратор БД", "нет", "нет", "да", "—", "только авария"],
        ["6. Дамп тестовой базы", "сис. администратор", "—", "—", "да", "разово", "если нужны данные тестирования"],
    ], [3.2, 2.8, 2.3, 2.1, 1.9, 2.1, 2.6]))

    f.append(P("5. Рекомендация и порядок работ", "h1"))
    f += numbered([
        "<b>К запуску на рабочем сервере:</b> вариант 1 с доработками (выдача паролей списком, предохранитель на удаление, настройки вместо зашитых значений). "
        "Этого достаточно, чтобы загрузить контингент и кураторов в день запуска без разработки интерфейса.",
        "<b>Если на тестовой платформе есть данные, которые нужно сохранить</b> — дополнительно вариант 6 (разовый перенос дампа), иначе чистая установка и загрузка из файлов.",
        "<b>Следом за запуском:</b> варианты 2+3 — экран «Импорт» и единый шаблон Excel. После этого плановые обновления (начало года, переводы, новые кураторы) "
        "делает сотрудник колледжа в браузере, без системного администратора и без выпуска версий.",
    ])
    f.append(P("6. Риски и что нужно решить", "h1"))
    f.append(table([
        ["Вопрос / риск", "Предложение"],
        ["Реестр колледжа — единственный источник правды о контингенте?", "Если да — вариант 3 строить на его колонках (ФИО, группа, статус, площадка, курс); если нет — отдельный шаблон платформы."],
        ["Что делать со студентами, которых нет в новой выгрузке?", "Не удалять сразу, а переводить в «выбыл» и предлагать удаление отдельным шагом (в скриптах сегодня — удаление)."],
        ["Кто вправе загружать данные?", "Только администратор платформы; каждая загрузка — в журнале аудита."],
        ["Персональные данные в файлах", "Файлы передаются защищённым каналом, не хранятся на сервере после загрузки, в git не попадают (уже закреплено в .gitignore)."],
        ["Пароли кураторов при массовой загрузке", "Временные пароли выгружаются одним файлом и выдаются под роспись; при первом входе куратор обязан сменить пароль."],
        ["Нужна ли загрузка посещаемости прошлых периодов?", "Если да — отдельная разовая задача (скрипт уже есть: import_attendance_xlsx), если нет — отметки начинаются с даты запуска."],
    ], [6.0, 11.0]))
    return f


def main() -> None:
    register_fonts()
    S.update(styles())
    version = project_version()
    build(DEPLOY / "kait20-instrukciya-administratoru.pdf", "Инструкция системному администратору", admin_guide(version), version)
    build(DEPLOY / "kait20-zagruzka-dannyh-varianty.pdf", "Загрузка данных: анализ и варианты", data_loading_guide(version), version)
    if TOO_LONG:
        raise SystemExit("Длинные строки кода (обрезаются в PDF):\n" + "\n".join(TOO_LONG))
    print("Готово:", *(p.name for p in sorted(DEPLOY.glob("*.pdf"))))


if __name__ == "__main__":
    main()
