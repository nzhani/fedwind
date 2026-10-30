import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from psycopg import connect
from psycopg.rows import dict_row

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")


def get_connection():
    return connect(DATABASE_URL, row_factory=dict_row, connect_timeout=3)

print("Using PostgreSQL via DATABASE_URL")

@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def generate_id() -> str:
    return str(uuid.uuid4())[:8]


def utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def init_feedback_db() -> None:
    with db_cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                sender_type TEXT NOT NULL,
                sender_name TEXT,
                message_text TEXT NOT NULL,
                context TEXT,
                created_at TEXT NOT NULL,
                is_public BOOLEAN NOT NULL DEFAULT FALSE,
                telegram_message_id INTEGER,
                reply_to_message_id TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
            ON messages(conversation_id)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_created_at
            ON messages(created_at)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_telegram_message_id
            ON messages(telegram_message_id)
            """
        )


def conversation_exists(conversation_id: str) -> bool:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM conversations
            WHERE id = %s
            """,
            (conversation_id,),
        )
        return cursor.fetchone() is not None


def create_conversation_with_user_message(
    message_text: str,
    sender_name: Optional[str] = None,
    context: Optional[str] = None,
) -> dict:
    conversation_id = generate_id()
    message_id = generate_id()
    now = utc_now()

    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO conversations (id, created_at, updated_at, status)
            VALUES (%s, %s, %s, %s)
            """,
            (conversation_id, now, now, "pending"),
        )

        cursor.execute(
            """
            INSERT INTO messages (
                id,
                conversation_id,
                sender_type,
                sender_name,
                message_text,
                context,
                created_at,
                is_public,
                telegram_message_id,
                reply_to_message_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                message_id,
                conversation_id,
                "user",
                sender_name,
                message_text,
                context,
                now,
                False,
                None,
                None,
            ),
        )

    return {
        "conversation_id": conversation_id,
        "message_id": message_id,
        "created_at": now,
    }


def create_user_follow_up_message(
    conversation_id: str,
    message_text: str,
    sender_name: Optional[str] = None,
    context: Optional[str] = None,
    reply_to_message_id: Optional[str] = None,
) -> dict:
    if not conversation_exists(conversation_id):
        raise ValueError("Conversation not found")

    message_id = generate_id()
    now = utc_now()

    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO messages (
                id,
                conversation_id,
                sender_type,
                sender_name,
                message_text,
                context,
                created_at,
                is_public,
                telegram_message_id,
                reply_to_message_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                message_id,
                conversation_id,
                "user",
                sender_name,
                message_text,
                context,
                now,
                False,
                None,
                reply_to_message_id,
            ),
        )

        cursor.execute(
            """
            UPDATE conversations
            SET updated_at = %s, status = %s
            WHERE id = %s
            """,
            (now, "pending", conversation_id),
        )

    return {
        "conversation_id": conversation_id,
        "message_id": message_id,
        "created_at": now,
    }


def set_message_telegram_id(message_id: str, telegram_message_id: int) -> None:
    with db_cursor() as cursor:
        cursor.execute(
            """
            UPDATE messages
            SET telegram_message_id = %s
            WHERE id = %s
            """,
            (telegram_message_id, message_id),
        )


def get_first_user_message(conversation_id: str):
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM messages
            WHERE conversation_id = %s
              AND sender_type = 'user'
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (conversation_id,),
        )
        return cursor.fetchone()


def get_conversation_entries() -> list[dict]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, created_at, updated_at, status
            FROM conversations
            ORDER BY updated_at DESC
            """
        )
        conversations = cursor.fetchall()

    results = []

    for conversation in conversations:
        conversation_id = conversation["id"]
        first_user_message = get_first_user_message(conversation_id)

        if not first_user_message:
            continue

        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM messages
                WHERE conversation_id = %s
                  AND sender_type = 'developer'
                  AND reply_to_message_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (conversation_id, first_user_message["id"]),
            )
            main_developer_answer = cursor.fetchone()

        results.append(
            {
                "id": conversation_id,
                "message": first_user_message["message_text"],
                "name": first_user_message["sender_name"],
                "context": first_user_message["context"],
                "created_at": first_user_message["created_at"],
                "status": "answered" if main_developer_answer else conversation["status"],
                "answer_text": main_developer_answer["message_text"] if main_developer_answer else None,
                "answered_at": main_developer_answer["created_at"] if main_developer_answer else None,
                "answered_by": main_developer_answer["sender_name"] if main_developer_answer else None,
                "is_public": bool(main_developer_answer["is_public"]) if main_developer_answer else False,
                "telegram_message_id": first_user_message["telegram_message_id"],
            }
        )

    return results


def get_conversation_messages(conversation_id: str) -> list[dict]:
    if not conversation_exists(conversation_id):
        raise ValueError("Conversation not found")

    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                conversation_id,
                sender_type,
                sender_name,
                message_text,
                context,
                created_at,
                is_public,
                telegram_message_id,
                reply_to_message_id
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        )
        rows = cursor.fetchall()

    return [
        {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "sender_type": row["sender_type"],
            "sender_name": row["sender_name"],
            "message_text": row["message_text"],
            "context": row["context"],
            "created_at": row["created_at"],
            "is_public": bool(row["is_public"]),
            "telegram_message_id": row["telegram_message_id"],
            "reply_to_message_id": row["reply_to_message_id"],
        }
        for row in rows
    ]


def create_developer_answer(
    conversation_id: str,
    answer_text: str,
    answered_by: Optional[str] = None,
    is_public: bool = True,
    reply_to_message_id: Optional[str] = None,
) -> dict:
    message_id = generate_id()
    now = utc_now()

    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM conversations
            WHERE id = %s
            """,
            (conversation_id,),
        )
        conversation = cursor.fetchone()

        if not conversation:
            raise ValueError("Conversation not found")

        cursor.execute(
            """
            INSERT INTO messages (
                id,
                conversation_id,
                sender_type,
                sender_name,
                message_text,
                context,
                created_at,
                is_public,
                telegram_message_id,
                reply_to_message_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                message_id,
                conversation_id,
                "developer",
                answered_by or "Developer",
                answer_text,
                None,
                now,
                is_public,
                None,
                reply_to_message_id,
            ),
        )

        cursor.execute(
            """
            UPDATE conversations
            SET updated_at = %s, status = %s
            WHERE id = %s
            """,
            (now, "answered", conversation_id),
        )

    return {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "answered_at": now,
    }


def get_user_message_target_by_telegram_message_id(telegram_message_id: int) -> Optional[dict]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, conversation_id
            FROM messages
            WHERE sender_type = 'user'
              AND telegram_message_id = %s
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (telegram_message_id,),
        )
        row = cursor.fetchone()

    if not row:
        return None

    return {
        "message_id": row["id"],
        "conversation_id": row["conversation_id"],
    }


def get_public_answers() -> list[dict]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC
            """
        )
        conversations = cursor.fetchall()

    results = []

    for conversation in conversations:
        conversation_id = conversation["id"]
        first_user_message = get_first_user_message(conversation_id)

        if not first_user_message:
            continue

        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM messages
                WHERE conversation_id = %s
                  AND sender_type = 'developer'
                  AND is_public = TRUE
                  AND reply_to_message_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (conversation_id, first_user_message["id"]),
            )
            main_public_answer = cursor.fetchone()

        results.append(
            {
                "id": conversation_id,
                "question": first_user_message["message_text"],
                "answer_text": main_public_answer["message_text"] if main_public_answer else None,
                "created_at": first_user_message["created_at"],
                "answered_at": main_public_answer["created_at"] if main_public_answer else None,
                "asked_by": first_user_message["sender_name"] or "Anonymous",
            }
        )

    results.sort(
        key=lambda x: x["answered_at"] or x["created_at"],
        reverse=True,
    )
    return results


def delete_conversation(conversation_id: str) -> bool:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM conversations
            WHERE id = %s
            """,
            (conversation_id,),
        )
        exists = cursor.fetchone()

        if not exists:
            return False

        cursor.execute(
            """
            DELETE FROM messages
            WHERE conversation_id = %s
            """,
            (conversation_id,),
        )

        cursor.execute(
            """
            DELETE FROM conversations
            WHERE id = %s
            """,
            (conversation_id,),
        )

    return True