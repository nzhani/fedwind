import os
from typing import Any, Dict

import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID")


def _require_bot_token() -> str:
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is missing in .env")
    return BOT_TOKEN


def _require_support_chat_id() -> str:
    if not SUPPORT_CHAT_ID:
        raise ValueError("SUPPORT_CHAT_ID is missing in .env")
    return SUPPORT_CHAT_ID


def _api_url(method: str) -> str:
    token = _require_bot_token()
    return f"https://api.telegram.org/bot{token}/{method}"


def send_telegram_message(text: str) -> Dict[str, Any]:
    chat_id = _require_support_chat_id()

    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    response = requests.post(_api_url("sendMessage"), json=payload, timeout=15)
    response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {data}")

    return data


def set_telegram_webhook(webhook_url: str) -> Dict[str, Any]:
    payload = {"url": webhook_url}

    response = requests.post(_api_url("setWebhook"), json=payload, timeout=15)
    response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram setWebhook failed: {data}")

    return data


def get_telegram_webhook_info() -> Dict[str, Any]:
    response = requests.get(_api_url("getWebhookInfo"), timeout=15)
    response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram getWebhookInfo failed: {data}")

    return data


def delete_telegram_webhook() -> Dict[str, Any]:
    response = requests.post(_api_url("deleteWebhook"), timeout=15)
    response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram deleteWebhook failed: {data}")

    return data