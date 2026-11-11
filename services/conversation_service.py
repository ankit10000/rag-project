import uuid
from services.database import get_connection


def create_conversation(title: str = "New Conversation") -> str:

    conversation_id = uuid.uuid4()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, title)
            VALUES (%s, %s)
            """,
            (conversation_id, title)
        )

    return str(conversation_id)

def conversation_exists(conversation_id: str) -> bool:

    with get_connection() as conn:
        result = conn.execute(
            "SELECT 1 FROM conversations WHERE id = %s",
            (uuid.UUID(conversation_id),)
        ).fetchone()

    return result is not None

def save_message(
    conversation_id: str,
    role: str,
    content: str
):

    if role not in ("user", "assistant"):
        raise ValueError("Role must be user or assistant")

    if not content.strip():
        raise ValueError("Message content cannot be empty")

    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (uuid.UUID(conversation_id), role, content)
        ).fetchone()

    return row[0]


def mark_messages_excluded(
    conversation_id: str,
    message_ids: list[int]
) -> int:
    """
    Exclude messages from history, summarization and memory
    extraction. Scoped to this conversation only.
    Returns the number of messages marked.
    """

    ids = [int(i) for i in message_ids if i is not None]

    if not ids:
        return 0

    with get_connection() as conn:
        rows = conn.execute(
            """
            UPDATE messages
            SET context_excluded = true
            WHERE conversation_id = %s
              AND id = ANY(%s::bigint[])
            RETURNING id
            """,
            (uuid.UUID(conversation_id), ids)
        ).fetchall()

    return len(rows)


def get_paired_assistant_ids(
    conversation_id: str,
    message_ids: list[int]
) -> list[int]:
    """
    For each given user message, return the id of the assistant reply
    that immediately follows it in this conversation (if any).
    Replies often echo the fact the user stated.
    """

    paired = []

    with get_connection() as conn:
        for message_id in message_ids:
            if message_id is None:
                continue

            row = conn.execute(
                """
                SELECT id, role
                FROM messages
                WHERE conversation_id = %s
                  AND id > %s
                ORDER BY id ASC
                LIMIT 1
                """,
                (uuid.UUID(conversation_id), int(message_id))
            ).fetchone()

            origin = conn.execute(
                """
                SELECT role FROM messages
                WHERE conversation_id = %s AND id = %s
                """,
                (uuid.UUID(conversation_id), int(message_id))
            ).fetchone()

            if (
                row is not None
                and origin is not None
                and origin[0] == "user"
                and row[1] == "assistant"
            ):
                paired.append(row[0])

    return paired


def get_live_messages(
    conversation_id: str,
    limit: int = 40
) -> list[dict]:
    """Most recent non-excluded messages of this conversation."""

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content
            FROM messages
            WHERE conversation_id = %s
              AND NOT context_excluded
            ORDER BY id DESC
            LIMIT %s
            """,
            (uuid.UUID(conversation_id), limit)
        ).fetchall()

    rows.reverse()

    return [
        {"id": row[0], "role": row[1], "content": row[2]}
        for row in rows
    ]


def reset_conversation_summary(conversation_id: str):
    """
    Clear the summary and its checkpoint so it is rebuilt from the
    (non-excluded) messages by the normal summarization flow.
    """

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE conversations
            SET summary = '',
                summary_up_to_message_id = 0
            WHERE id = %s
            """,
            (uuid.UUID(conversation_id),)
        )


def get_conversation_history(
    conversation_id: str,
    limit: int = 16
) -> list[dict]:

    if limit <= 0:
        raise ValueError("Limit must be greater than zero")

    with get_connection() as conn:

        conversation = conn.execute(
            """
            SELECT summary_up_to_message_id
            FROM conversations
            WHERE id = %s
            """,
            (uuid.UUID(conversation_id),)
        ).fetchone()

        if conversation is None:
            raise ValueError("Conversation not found")

        checkpoint = conversation[0]

        rows = conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = %s
              AND id > %s
              AND NOT context_excluded
            ORDER BY id DESC
            LIMIT %s
            """,
            (uuid.UUID(conversation_id), checkpoint, limit)
        ).fetchall()

    rows.reverse()

    return [
        {"role": role, "content": content}
        for role, content in rows
    ]
def get_conversation_summary(conversation_id: str) -> str:

    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT summary
            FROM conversations
            WHERE id = %s
            """,
            (uuid.UUID(conversation_id),)
        ).fetchone()

    if result is None:
        raise ValueError("Conversation not found")

    return result[0] or ""


def update_conversation_summary(
    conversation_id: str,
    summary: str
):

    with get_connection() as conn:
        result = conn.execute(
            """
            UPDATE conversations
            SET summary = %s
            WHERE id = %s
            RETURNING id
            """,
            (summary, uuid.UUID(conversation_id))
        ).fetchone()

    if result is None:
        raise ValueError("Conversation not found")

def get_message_count(conversation_id: str) -> int:

    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT COUNT(*)
            FROM messages
            WHERE conversation_id = %s
            """,
            (uuid.UUID(conversation_id),)
        ).fetchone()

    return result[0]
def get_old_messages(
    conversation_id: str,
    keep_recent: int = 6
) -> list[dict]:

    if keep_recent < 1:
        raise ValueError("keep_recent must be at least 1")

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content
            FROM messages
            WHERE conversation_id = %s
            ORDER BY id ASC
            """,
            (uuid.UUID(conversation_id),)
        ).fetchall()

    old_rows = rows[:-keep_recent] if len(rows) > keep_recent else []

    return [
        {
            "id": row[0],
            "role": row[1],
            "content": row[2]
        }
        for row in old_rows
    ]

def get_messages_to_summarize(
    conversation_id: str,
    keep_recent: int = 6
) -> tuple[str, list[dict]]:

    if keep_recent < 1:
        raise ValueError("keep_recent must be at least 1")

    with get_connection() as conn:
        conversation = conn.execute(
            """
            SELECT summary, summary_up_to_message_id
            FROM conversations
            WHERE id = %s
            """,
            (uuid.UUID(conversation_id),)
        ).fetchone()

        if conversation is None:
            raise ValueError("Conversation not found")

        summary, checkpoint = conversation

        rows = conn.execute(
            """
            WITH recent_messages AS (
                SELECT id
                FROM messages
                WHERE conversation_id = %s
                  AND NOT context_excluded
                ORDER BY id DESC
                LIMIT %s
            )
            SELECT id, role, content
            FROM messages
            WHERE conversation_id = %s
              AND id > %s
              AND NOT context_excluded
              AND id NOT IN (SELECT id FROM recent_messages)
            ORDER BY id ASC
            """,
            (
                uuid.UUID(conversation_id),
                keep_recent,
                uuid.UUID(conversation_id),
                checkpoint
            )
        ).fetchall()

    messages = [
        {"id": row[0], "role": row[1], "content": row[2]}
        for row in rows
    ]

    return summary or "", messages


def update_conversation_memory(
    conversation_id: str,
    summary: str,
    last_message_id: int
):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE conversations
            SET summary = %s,
                summary_up_to_message_id = %s
            WHERE id = %s
            """,
            (
                summary,
                last_message_id,
                uuid.UUID(conversation_id)
            )
        )
def get_messages_for_memory_extraction(
    conversation_id: str,
    limit: int = 10
) -> list[dict]:
    """Fetch new messages not yet processed for memory extraction."""

    if limit <= 0:
        raise ValueError("limit must be greater than zero.")

    conversation_uuid = uuid.UUID(conversation_id)

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT memory_extraction_up_to_message_id
            FROM conversations
            WHERE id = %s
            """,
            (conversation_uuid,)
        ).fetchone()

        if row is None:
            raise ValueError("Conversation not found.")

        checkpoint = row[0]

        rows = conn.execute(
            """
            SELECT id, role, content
            FROM messages
            WHERE conversation_id = %s
              AND id > %s
              AND NOT context_excluded
            ORDER BY id ASC
            LIMIT %s
            """,
            (conversation_uuid, checkpoint, limit)
        ).fetchall()

    return [
        {
            "id": row[0],
            "role": row[1],
            "content": row[2]
        }
        for row in rows
    ]


def update_memory_extraction_checkpoint(
    conversation_id: str,
    last_message_id: int
):
    """Mark messages as processed for memory extraction."""

    conversation_uuid = uuid.UUID(conversation_id)

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE conversations
            SET memory_extraction_up_to_message_id = %s
            WHERE id = %s
            """,
            (last_message_id, conversation_uuid)
        )