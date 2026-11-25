"""Telegram alerts with a fake bot: connect, plant events, offline once, retries, /stop."""

import psycopg
import pytest

from app.services import notifications
from tests.test_accounts import csrf, login
from tests.test_site_connection import beat, enroll, kit
from tests.test_site_registration import WIND, admin, operator


class FakeBot(notifications.Telegram):
    def __init__(self):
        super().__init__("test-token")
        self.sent, self.updates, self.down, self.next_update = [], [], False, 1

    def call(self, method, http_timeout=15, **params):
        assert http_timeout > 0
        if method == "getMe":
            return {"username": "fedwind_test_bot"}
        if method == "getUpdates":
            ups = [u for u in self.updates if u["update_id"] >= params.get("offset", 0)]
            return ups
        if method == "sendMessage":
            if self.down:
                raise notifications.TelegramError("sendMessage: network")
            self.sent.append((params["chat_id"], params["text"]))
            return {"message_id": len(self.sent)}
        raise AssertionError(method)

    def press_start(self, chat_id, text, username="someone"):
        self.updates.append({"update_id": self.next_update, "message": {
            "text": text, "chat": {"id": chat_id, "type": "private"}, "from": {"username": username}}})
        self.next_update += 1

    def to(self, chat_id):
        return [t for c, t in self.sent if c == str(chat_id)]


@pytest.fixture
def bot(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(notifications, "client", lambda: fake)
    monkeypatch.setenv("SUPPORT_CHAT_ID", "team-chat")
    monkeypatch.setenv("FRONTEND_URL", "https://fedwind.example")
    return fake


def connect_telegram(client, token, bot, chat_id):
    r = client.post("/api/me/telegram/link", headers=csrf(token))
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith("https://t.me/fedwind_test_bot?start=")
    bot.press_start(chat_id, "/start " + url.split("start=")[1])
    notifications.tick(bot)
    assert client.get("/api/me/telegram").json()["linked"] is True
    assert any(t.startswith("Connected") for t in bot.to(chat_id))


def test_operator_and_admin_get_the_plant_journey(db_client, pg_url, bot):
    notifications.tick(bot)                                   # first round only sets the audit cursor
    t = admin(db_client)
    connect_telegram(db_client, t, bot, 999)
    op = operator(db_client)
    assert db_client.get("/api/me/telegram").json() == {
        "configured": True, "linked": False, "telegram_username": None, "linked_at": None,
        "bot_username": "fedwind_test_bot"}
    connect_telegram(db_client, op, bot, 111)
    site_id = db_client.post("/api/sites", json=WIND, headers=csrf(op)).json()["id"]
    db_client.cookies.clear()
    t = login(db_client, "admin@fedwind.kz")[1]
    notifications.tick(bot)
    for chat in ("999", "team-chat"):
        assert any("New plant waiting for approval: Zhanatas Wind" in m and "/admin/approvals" in m
                   for m in bot.to(chat))
    assert not any("New plant" in m for m in bot.to(111))     # operators don't get the admin queue

    db_client.post(f"/api/admin/sites/{site_id}/approve", json={}, headers=csrf(t))
    notifications.tick(bot)
    assert any(m.startswith("✅ Zhanatas Wind is approved") and f"/sites/{site_id}" in m for m in bot.to(111))

    db_client.cookies.clear()
    _, op = login(db_client, "op@plant.kz")
    key = enroll(db_client, kit(db_client, site_id, op)).json()["site_key"]
    beat(db_client, key)
    notifications.tick(bot)
    assert any(m.startswith("🟢 Zhanatas Wind is online") for m in bot.to(111))

    # No heartbeat for a while: one offline message to the operator, the admin and the team chat
    with psycopg.connect(pg_url) as conn:
        conn.execute("UPDATE site_credentials SET last_seen_at = now() - interval '10 minutes'")
    notifications.tick(bot)
    notifications.tick(bot)
    for chat in ("111", "999", "team-chat"):
        assert sum("is offline" in m for m in bot.to(chat)) == 1
    beat(db_client, key)
    notifications.tick(bot)
    assert any("is back online" in m for m in bot.to(111))

    # Suspension carries the reason
    db_client.cookies.clear()
    t = login(db_client, "admin@fedwind.kz")[1]
    db_client.post(f"/api/admin/sites/{site_id}/suspend", json={"note": "Maintenance"}, headers=csrf(t))
    notifications.tick(bot)
    assert any("suspended" in m and "“Maintenance”" in m for m in bot.to(111))


def test_retries_when_telegram_is_down_and_stop_disconnects(db_client, bot):
    notifications.tick(bot)
    op = operator(db_client)
    connect_telegram(db_client, op, bot, 111)
    bot.down = True
    db_client.post("/api/sites", json=WIND, headers=csrf(op))
    t = admin(db_client)
    connect_telegram_down = db_client.post("/api/me/telegram/link", headers=csrf(t))
    assert connect_telegram_down.status_code == 200
    notifications.tick(bot)                                   # queued, not sent
    assert not bot.to("team-chat")
    bot.down = False
    notifications.tick(bot)
    assert any("New plant" in m for m in bot.to("team-chat"))  # sent on the next round

    bot.press_start(111, "/stop")
    notifications.tick(bot)
    db_client.cookies.clear()
    login(db_client, "op@plant.kz")
    assert db_client.get("/api/me/telegram").json()["linked"] is False

    bot.press_start(222, "/start not-a-real-code")
    notifications.tick(bot)
    assert any("used or expired" in m for m in bot.to(222))


def test_without_a_bot_alerts_are_simply_off(db_client):
    op = operator(db_client)
    s = db_client.get("/api/me/telegram").json()
    assert s["configured"] is False and s["linked"] is False
    assert db_client.post("/api/me/telegram/link", headers=csrf(op)).status_code == 503
    assert notifications.start_background() is None
