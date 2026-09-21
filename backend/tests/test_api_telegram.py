def test_telegram_link_requires_bot_configured(client, curator_headers, monkeypatch):
    from app.api.routers import auth as auth_router

    monkeypatch.setattr(auth_router.settings, "telegram_bot_token", "")
    r = client.post("/auth/telegram/link", headers=curator_headers)
    assert r.status_code == 503


def test_telegram_link_flow(client, curator_headers, curator_user, db, monkeypatch):
    from app.api.routers import auth as auth_router
    from app.services.telegram_link_service import consume_link_token

    monkeypatch.setattr(auth_router.settings, "telegram_bot_token", "test-token")
    monkeypatch.setattr(auth_router.settings, "telegram_bot_username", "kait20_bot")

    r = client.get("/auth/me", headers=curator_headers)
    assert r.json()["telegram_linked"] is False

    r = client.post("/auth/telegram/link", headers=curator_headers)
    assert r.status_code == 200
    deep_link = r.json()["deep_link"]
    assert deep_link.startswith("https://t.me/kait20_bot?start=")
    token_value = deep_link.split("start=")[1]

    # Симулируем то, что делает обработчик /start в боте.
    consume_link_token(db, token_value, "42")

    r = client.get("/auth/me", headers=curator_headers)
    assert r.json()["telegram_linked"] is True

    r = client.post("/auth/telegram/unlink", headers=curator_headers)
    assert r.status_code == 200
    assert r.json()["telegram_linked"] is False

    db.refresh(curator_user)
    assert curator_user.telegram_chat_id is None


def test_telegram_link_requires_auth(client, seeded):
    r = client.post("/auth/telegram/link")
    assert r.status_code == 401
