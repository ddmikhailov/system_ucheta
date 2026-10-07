"""Адреса интерфейса («/my-day», «/tasks», «/students»…) совпадают с адресами API. Обновление страницы
(F5), закладка и ссылка раньше показывали JSON «Нужна авторизация» вместо сайта."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import is_browser_navigation, register_spa


@pytest.fixture()
def client(tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>КАИТ-20</title>", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")

    app = FastAPI()

    @app.get("/students")
    def students_api():
        return {"detail": "Нужна авторизация"}

    @app.post("/students")
    def create_student():
        return {"created": True}

    @app.get("/my-day")
    def my_day_api():
        return {"api": "my-day"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    register_spa(app, static)
    return TestClient(app)


PAGE = {"Sec-Fetch-Dest": "document", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
FETCH = {"Sec-Fetch-Dest": "empty", "Accept": "*/*"}


@pytest.mark.parametrize("path", ["/students", "/my-day"])
def test_opening_the_address_in_the_browser_returns_the_page_not_json(client, path):
    response = client.get(path, headers=PAGE)
    assert "<title>КАИТ-20</title>" in response.text
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path, expected", [("/students", "Нужна авторизация"), ("/my-day", "my-day")])
def test_requests_from_the_app_still_reach_the_api(client, path, expected):
    assert expected in client.get(path, headers=FETCH).text


def test_old_browsers_without_fetch_metadata_are_recognised_by_accept(client):
    assert "<title>КАИТ-20</title>" in client.get("/students", headers={"Accept": "text/html"}).text
    assert "Нужна авторизация" in client.get("/students", headers={"Accept": "application/json"}).text


def test_only_get_and_head_are_taken_for_page_navigation(client):
    assert client.post("/students", headers=PAGE).json() == {"created": True}


@pytest.mark.parametrize("path", ["/health", "/assets/app.js"])
def test_server_only_paths_are_never_replaced_by_the_page(client, path):
    response = client.get(path, headers=PAGE)
    assert "<title>КАИТ-20</title>" not in response.text


def test_unknown_address_still_falls_back_to_the_page(client):
    assert "<title>КАИТ-20</title>" in client.get("/нет-такой-страницы", headers=FETCH).text


@pytest.mark.parametrize(
    "method, path, headers, expected",
    [
        ("GET", "/tasks", {"sec-fetch-dest": "document"}, True),
        ("GET", "/tasks", {"sec-fetch-dest": "empty", "accept": "text/html"}, False),
        ("GET", "/tasks", {"accept": "text/html"}, True),
        ("GET", "/tasks", {}, False),
        ("PUT", "/tasks", {"sec-fetch-dest": "document"}, False),
        ("GET", "/docs", {"sec-fetch-dest": "document"}, False),
    ],
)
def test_navigation_detection(method, path, headers, expected):
    assert is_browser_navigation(method, path, headers) is expected


@pytest.mark.parametrize("path", ["/.env", "/.git/HEAD", "/assets/missing.js.map", "/backup.sql"])
def test_missing_file_like_path_is_404_not_the_page(client, path):
    """Внешний аудит: /.env, /.git/HEAD отвечали 200 с главной страницей — сканеры принимали это за находку."""
    assert client.get(path).status_code == 404


def test_extensionless_spa_routes_still_return_the_page(client):
    assert "<title>КАИТ-20</title>" in client.get("/some/client/route").text
