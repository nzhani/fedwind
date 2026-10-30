"""
Feedback Router
===============
Stores website feedback/questions, supports answering them,
exposes public answered questions for the website,
and processes Telegram webhook replies.

Storage now uses SQLite instead of JSONL.
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.feedback_db import (
    create_conversation_with_user_message,
    create_developer_answer,
    create_user_follow_up_message,
    delete_conversation,
    get_conversation_entries,
    get_user_message_target_by_telegram_message_id,
    get_conversation_messages,
    get_public_answers,
    get_first_user_message,
    set_message_telegram_id,
)
from app.services.telegram_service import (
    SUPPORT_CHAT_ID,
    delete_telegram_webhook,
    get_telegram_webhook_info,
    send_telegram_message,
    set_telegram_webhook,
)

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


class FeedbackCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000, description="Feedback/question text")
    name: Optional[str] = Field(None, max_length=100, description="Optional name")
    context: Optional[str] = Field(None, max_length=200, description="Context (e.g. dashboard)")


class FeedbackEntry(BaseModel):
    id: str
    message: str
    name: Optional[str] = None
    context: Optional[str] = None
    created_at: str
    status: str = "pending"
    answer_text: Optional[str] = None
    answered_at: Optional[str] = None
    answered_by: Optional[str] = None
    is_public: bool = False
    telegram_message_id: Optional[int] = None


class FeedbackResponse(BaseModel):
    success: bool
    message: str
    entry: FeedbackEntry


class FeedbackListResponse(BaseModel):
    entries: list[FeedbackEntry]
    total: int


class AnswerFeedbackRequest(BaseModel):
    answer_text: str = Field(..., min_length=1, max_length=10000)
    answered_by: Optional[str] = Field(default="Developer", max_length=100)
    is_public: bool = True


class FollowUpRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    name: Optional[str] = Field(None, max_length=100)
    context: Optional[str] = Field(None, max_length=200)
    reply_to_message_id: Optional[str] = None


class ConversationMessageItem(BaseModel):
    id: str
    conversation_id: str
    sender_type: str
    sender_name: Optional[str] = None
    message_text: str
    context: Optional[str] = None
    created_at: str
    is_public: bool = False
    telegram_message_id: Optional[int] = None
    reply_to_message_id: Optional[str] = None


class ConversationMessagesResponse(BaseModel):
    conversation_id: str
    entries: list[ConversationMessageItem]
    total: int


class PublicAnswerItem(BaseModel):
    id: str
    question: str
    answer_text: Optional[str] = None
    created_at: str
    answered_at: Optional[str] = None
    asked_by: str


class PublicAnswersResponse(BaseModel):
    entries: list[PublicAnswerItem]
    total: int


class TelegramWebhookSetupRequest(BaseModel):
    public_base_url: str = Field(..., min_length=1, description="Public HTTPS base URL, without trailing slash")


def _build_telegram_question_text(entry: FeedbackEntry) -> str:
    return (
        f"📩 New Website Question\n\n"
        f"🆔 Conversation ID: {entry.id}\n"
        f"👤 Name: {entry.name or 'Anonymous'}\n"
        f"🕒 Created At: {entry.created_at}\n"
        f"📌 Status: {entry.status}\n\n"
        f"❓ Question:\n{entry.message}\n\n"
        f"Reply to this message with:\n"
        f"ANSWER: your answer here"
    )


def _build_telegram_follow_up_text(
    conversation_id: str,
    message: str,
    name: Optional[str],
    created_at: str,
) -> str:
    return (
        f"🔁 Website Follow-up\n\n"
        f"🆔 Conversation ID: {conversation_id}\n"
        f"👤 Name: {name or 'Anonymous'}\n"
        f"🕒 Created At: {created_at}\n\n"
        f"💬 Follow-up:\n{message}\n\n"
        f"Reply to this message with:\n"
        f"ANSWER: your answer here"
    )


def _extract_sender_name(message_from: dict) -> str:
    username = (message_from.get("username") or "").strip()
    first_name = (message_from.get("first_name") or "").strip()
    last_name = (message_from.get("last_name") or "").strip()

    if username:
        return f"@{username}"

    full_name = f"{first_name} {last_name}".strip()
    return full_name or "Developer"


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(feedback: FeedbackCreate):
    created = create_conversation_with_user_message(
        message_text=feedback.message.strip(),
        sender_name=feedback.name.strip() if feedback.name else None,
        context=feedback.context.strip() if feedback.context else None,
    )

    entry = FeedbackEntry(
        id=created["conversation_id"],
        message=feedback.message.strip(),
        name=feedback.name.strip() if feedback.name else None,
        context=feedback.context.strip() if feedback.context else None,
        created_at=created["created_at"],
        status="pending",
        answer_text=None,
        answered_at=None,
        answered_by=None,
        is_public=False,
        telegram_message_id=None,
    )

    try:
        telegram_response = send_telegram_message(_build_telegram_question_text(entry))
        message_id = telegram_response.get("result", {}).get("message_id")
        if isinstance(message_id, int):
            entry.telegram_message_id = message_id
            set_message_telegram_id(created["message_id"], message_id)
    except Exception as e:
        print(f"Failed to send feedback to Telegram: {e}")

    return FeedbackResponse(
        success=True,
        message="Thank you! Your message has been sent.",
        entry=entry,
    )


@router.get("", response_model=FeedbackListResponse)
async def list_feedback():
    rows = get_conversation_entries()

    entries = [
        FeedbackEntry(
            id=row["id"],
            message=row["message"],
            name=row["name"],
            context=row["context"],
            created_at=row["created_at"],
            status=row["status"],
            answer_text=row["answer_text"],
            answered_at=row["answered_at"],
            answered_by=row["answered_by"],
            is_public=row["is_public"],
            telegram_message_id=row["telegram_message_id"],
        )
        for row in rows
    ]

    return FeedbackListResponse(entries=entries, total=len(entries))


@router.get("/{feedback_id}/messages", response_model=ConversationMessagesResponse)
async def get_feedback_messages(feedback_id: str):
    try:
        rows = get_conversation_messages(feedback_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Feedback not found")

    entries = [
        ConversationMessageItem(
            id=row["id"],
            conversation_id=row["conversation_id"],
            sender_type=row["sender_type"],
            sender_name=row["sender_name"],
            message_text=row["message_text"],
            context=row["context"],
            created_at=row["created_at"],
            is_public=row["is_public"],
            telegram_message_id=row["telegram_message_id"],
            reply_to_message_id=row["reply_to_message_id"],
        )
        for row in rows
    ]

    return ConversationMessagesResponse(
        conversation_id=feedback_id,
        entries=entries,
        total=len(entries),
    )


@router.post("/{feedback_id}/follow-up", response_model=FeedbackResponse)
async def create_feedback_follow_up(feedback_id: str, payload: FollowUpRequest):
    try:
        created = create_user_follow_up_message(
            conversation_id=feedback_id,
            message_text=payload.message.strip(),
            sender_name=payload.name.strip() if payload.name else None,
            context=payload.context.strip() if payload.context else None,
            reply_to_message_id=payload.reply_to_message_id,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Feedback not found")

    telegram_message_id = None

    try:
        telegram_response = send_telegram_message(
            _build_telegram_follow_up_text(
                conversation_id=feedback_id,
                message=payload.message.strip(),
                name=payload.name.strip() if payload.name else None,
                created_at=created["created_at"],
            )
        )
        message_id = telegram_response.get("result", {}).get("message_id")
        if isinstance(message_id, int):
            telegram_message_id = message_id
            set_message_telegram_id(created["message_id"], message_id)
    except Exception as e:
        print(f"Failed to send follow-up to Telegram: {e}")

    return FeedbackResponse(
        success=True,
        message="Follow-up sent successfully.",
        entry=FeedbackEntry(
            id=feedback_id,
            message=payload.message.strip(),
            name=payload.name.strip() if payload.name else None,
            context=payload.context.strip() if payload.context else None,
            created_at=created["created_at"],
            status="pending",
            answer_text=None,
            answered_at=None,
            answered_by=None,
            is_public=False,
            telegram_message_id=telegram_message_id,
        ),
    )


@router.patch("/{feedback_id}/answer", response_model=FeedbackResponse)
async def answer_feedback(feedback_id: str, payload: AnswerFeedbackRequest):
    rows = get_conversation_entries()
    target = next((row for row in rows if row["id"] == feedback_id), None)

    if not target:
        raise HTTPException(status_code=404, detail="Feedback not found")

    first_user_message = get_first_user_message(feedback_id)
    if not first_user_message:
        raise HTTPException(status_code=404, detail="Main question not found")

    created = create_developer_answer(
        conversation_id=feedback_id,
        answer_text=payload.answer_text,
        answered_by=payload.answered_by or "Developer",
        is_public=payload.is_public,
        reply_to_message_id=first_user_message["id"],
    )

    entry = FeedbackEntry(
        id=feedback_id,
        message=target["message"],
        name=target["name"],
        context=target["context"],
        created_at=target["created_at"],
        status="answered",
        answer_text=payload.answer_text.strip(),
        answered_at=created["answered_at"],
        answered_by=payload.answered_by or "Developer",
        is_public=payload.is_public,
        telegram_message_id=target["telegram_message_id"],
    )

    return FeedbackResponse(
        success=True,
        message="Feedback answered successfully.",
        entry=entry,
    )


@router.get("/public-answers", response_model=PublicAnswersResponse)
async def list_public_answers():
    rows = get_public_answers()

    public_entries = [
        PublicAnswerItem(
            id=row["id"],
            question=row["question"],
            answer_text=row["answer_text"],
            created_at=row["created_at"],
            answered_at=row["answered_at"],
            asked_by=row["asked_by"],
        )
        for row in rows
    ]

    return PublicAnswersResponse(entries=public_entries, total=len(public_entries))


@router.post("/telegram/set-webhook")
async def setup_telegram_webhook(payload: TelegramWebhookSetupRequest):
    base_url = payload.public_base_url.strip().rstrip("/")
    webhook_url = f"{base_url}/api/feedback/telegram/webhook"

    result = set_telegram_webhook(webhook_url)

    return {
        "success": True,
        "message": "Telegram webhook set successfully.",
        "webhook_url": webhook_url,
        "telegram_response": result,
    }


@router.get("/telegram/webhook-info")
async def telegram_webhook_info():
    result = get_telegram_webhook_info()
    return {
        "success": True,
        "telegram_response": result,
    }


@router.post("/telegram/delete-webhook")
async def remove_telegram_webhook():
    result = delete_telegram_webhook()
    return {
        "success": True,
        "message": "Telegram webhook deleted successfully.",
        "telegram_response": result,
    }


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    update: Any = await request.json()

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True, "ignored": "No message in update"}

    chat = message.get("chat") or {}
    incoming_chat_id = str(chat.get("id"))

    if SUPPORT_CHAT_ID and incoming_chat_id != str(SUPPORT_CHAT_ID):
        return {"ok": True, "ignored": "Message came from another chat"}

    text = (message.get("text") or "").strip()
    if not text:
        return {"ok": True, "ignored": "No text message"}

    reply_to_message = message.get("reply_to_message")
    if not reply_to_message:
        return {"ok": True, "ignored": "Not a reply"}

    if ":" not in text:
        return {"ok": True, "ignored": "No ANSWER: prefix"}

    prefix, body = text.split(":", 1)
    if prefix.strip().lower() != "answer":
        return {"ok": True, "ignored": "Message is not public answer format"}

    answer_text = body.strip()
    if not answer_text:
        return {"ok": True, "ignored": "Answer text is empty"}

    replied_message_id = reply_to_message.get("message_id")
    if not isinstance(replied_message_id, int):
        return {"ok": True, "ignored": "Replied message_id missing"}

    target = get_user_message_target_by_telegram_message_id(replied_message_id)

    if not target:
        return {"ok": True, "ignored": "No matching feedback entry"}

    answered_by = _extract_sender_name(message.get("from") or {})

    create_developer_answer(
        conversation_id=target["conversation_id"],
        answer_text=answer_text,
        answered_by=answered_by,
        is_public=True,
        reply_to_message_id=target["message_id"],
    )

    return {
        "ok": True,
        "message": "Answer saved successfully.",
        "feedback_id": target["conversation_id"],
        "reply_to_message_id": target["message_id"],
    }


@router.delete("/{feedback_id}")
async def delete_feedback(feedback_id: str):
    deleted = delete_conversation(feedback_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Feedback not found")

    return {"success": True, "message": "Feedback deleted"}