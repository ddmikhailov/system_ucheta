import datetime

import pytest

from app.core.time import utcnow
from app.services.telegram_link_service import (
    ChatAlreadyLinked,
    LinkTokenInvalid,
    build_deep_link,
    consume_link_token,
    create_link_token,
    unlink_telegram,
)


def test_create_and_consume_link_token(imported, db, curator_user):
    token = create_link_token(db, curator_user)
    assert token.user_id == curator_user.id
    assert token.is_usable is True

    link = build_deep_link(token.token)
    assert token.token in link

    user = consume_link_token(db, token.token, "555")
    assert user.id == curator_user.id
    assert user.telegram_chat_id == "555"
    assert user.telegram_linked_at is not None

    db.refresh(token)
    assert token.used_at is not None
    assert token.is_usable is False


def test_consume_link_token_twice_fails(imported, db, curator_user):
    token = create_link_token(db, curator_user)
    consume_link_token(db, token.token, "555")
    with pytest.raises(LinkTokenInvalid):
        consume_link_token(db, token.token, "666")


def test_consume_expired_token_fails(imported, db, curator_user):
    token = create_link_token(db, curator_user)
    token.expires_at = utcnow() - datetime.timedelta(minutes=1)
    db.commit()
    with pytest.raises(LinkTokenInvalid):
        consume_link_token(db, token.token, "555")


def test_consume_unknown_token_fails(imported, db):
    with pytest.raises(LinkTokenInvalid):
        consume_link_token(db, "does-not-exist", "555")


def test_chat_already_linked_to_another_user(imported, db, curator_user, db_second_curator):
    token1 = create_link_token(db, curator_user)
    consume_link_token(db, token1.token, "777")

    token2 = create_link_token(db, db_second_curator)
    with pytest.raises(ChatAlreadyLinked):
        consume_link_token(db, token2.token, "777")


def test_relinking_same_chat_to_same_user_is_allowed(imported, db, curator_user):
    token1 = create_link_token(db, curator_user)
    consume_link_token(db, token1.token, "777")

    token2 = create_link_token(db, curator_user)
    user = consume_link_token(db, token2.token, "777")
    assert user.telegram_chat_id == "777"


def test_unlink_clears_chat_id(imported, db, curator_user):
    token = create_link_token(db, curator_user)
    consume_link_token(db, token.token, "555")
    assert curator_user.telegram_chat_id == "555"

    unlink_telegram(db, curator_user)
    db.refresh(curator_user)
    assert curator_user.telegram_chat_id is None
    assert curator_user.telegram_linked_at is None
