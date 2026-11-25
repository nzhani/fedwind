"""
Telegram alerts for the signed-in user (app/services/notifications.py).

  GET    /api/me/telegram        connected? (and whether the server has a bot at all)
  POST   /api/me/telegram/link   a t.me link with a one-time code (15 min)
  DELETE /api/me/telegram        disconnect
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_user
from app.db import DatabaseUnavailable
from app.services import notifications
from app.services.accounts import User

router = APIRouter()


def _call(fn, *args):
    try:
        return fn(*args)
    except DatabaseUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except LookupError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except notifications.TelegramError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Telegram: {e}")


@router.get("/api/me/telegram", summary="Telegram alerts: status")
def telegram_status(user: User = Depends(require_user)):
    return _call(notifications.status, user.id)


@router.post("/api/me/telegram/link", summary="Telegram alerts: a one-time link to connect")
def telegram_link(user: User = Depends(require_user)):
    return _call(notifications.start_link, user.id)


@router.delete("/api/me/telegram", summary="Telegram alerts: disconnect")
def telegram_unlink(user: User = Depends(require_user)):
    _call(notifications.unlink, user.id)
    return {"linked": False}
