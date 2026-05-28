import json
import sqlite3
from datetime import datetime, timezone
from . import config, contacts
from .attributed_body import extract_text

# Cocoa/Mac absolute time epoch: 2001-01-01 00:00:00 UTC
_COCOA_EPOCH_OFFSET = 978307200
# Values >= 10^12 are nanoseconds; below are already seconds (very old backups)
_NS_THRESHOLD = 10**12


def _cocoa_to_iso(date_val: int | None) -> str | None:
    if date_val is None:
        return None
    unix = (date_val / 1_000_000_000 + _COCOA_EPOCH_OFFSET
            if date_val >= _NS_THRESHOLD
            else date_val + _COCOA_EPOCH_OFFSET)
    return datetime.fromtimestamp(unix).astimezone().isoformat()


def run() -> dict:
    """Extract all conversations from sms.db. Returns stats dict for validate.py."""
    db_uri = f"file:{config.SCRATCH_SMS_DB}?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True)
    conn.row_factory = sqlite3.Row

    # --- Build participant map: chat_id → list of {handle, name} ---
    participants: dict[int, list[dict]] = {}
    for row in conn.execute(
        """
        SELECT chj.chat_id, h.id AS handle_id
        FROM chat_handle_join chj
        JOIN handle h ON h.ROWID = chj.handle_id
        ORDER BY chj.chat_id, h.ROWID
        """
    ):
        entry = {
            "handle": row["handle_id"],
            "name": contacts.resolve(row["handle_id"]) or row["handle_id"],
        }
        participants.setdefault(row["chat_id"], []).append(entry)

    # --- Pull all messages (no tapbacks/edits) ---
    rows = conn.execute(
        """
        SELECT
            m.ROWID        AS msg_id,
            m.guid,
            m.text,
            m.attributedBody,
            m.is_from_me,
            m.date,
            m.cache_has_attachments,
            m.item_type,
            m.service,
            h.id           AS handle_id,
            c.ROWID        AS chat_id,
            c.chat_identifier,
            c.display_name AS chat_display_name,
            c.style        AS chat_style
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        JOIN chat c ON c.ROWID = cmj.chat_id
        LEFT JOIN handle h ON h.ROWID = m.handle_id
        WHERE m.associated_message_type = 0
        ORDER BY c.ROWID, m.date ASC
        """
    ).fetchall()

    conn.close()

    # --- Group by chat ---
    chats_raw: dict[int, dict] = {}
    stats = {
        "total_messages": 0,
        "text_source_text": 0,
        "text_source_attributed": 0,
        "text_source_empty": 0,
        "empty_confirmed_blank": 0,   # attributedBody present but zero-length NSString
        "empty_both_null": 0,          # both text and attributedBody are NULL
        "unresolved_handles": set(),
    }

    for row in rows:
        chat_id = row["chat_id"]
        if chat_id not in chats_raw:
            parts = participants.get(chat_id, [])
            if row["chat_display_name"]:
                title = row["chat_display_name"]
            elif len(parts) == 1:
                title = parts[0]["name"]
            elif parts:
                title = ", ".join(p["name"] for p in parts)
            else:
                title = row["chat_identifier"] or f"chat_{chat_id}"

            chats_raw[chat_id] = {
                "chat_id": chat_id,
                "chat_identifier": row["chat_identifier"],
                "title": title,
                "style": "group" if row["chat_style"] == 43 else "1-on-1",
                "participants": parts,
                "messages": [],
            }

        # Resolve message text
        raw_text = row["text"]
        ab_blob = row["attributedBody"]
        if raw_text:
            text = raw_text
            source = "text"
        else:
            text, source = extract_text(ab_blob)

        stats["total_messages"] += 1
        if source == "text":
            stats["text_source_text"] += 1
        elif source == "attributed_body":
            stats["text_source_attributed"] += 1
        else:
            stats["text_source_empty"] += 1
            if ab_blob is not None:
                stats["empty_confirmed_blank"] += 1
            elif row["item_type"] == 0:
                stats["empty_both_null"] += 1

        # Sender
        if row["is_from_me"]:
            sender_name = "Me"
            sender_handle = "me"
        else:
            sender_handle = row["handle_id"] or ""
            sender_name = contacts.resolve(sender_handle) or sender_handle
            if sender_handle and not contacts.resolve(sender_handle):
                stats["unresolved_handles"].add(sender_handle)

        msg = {
            "timestamp": _cocoa_to_iso(row["date"]),
            "sender_name": sender_name,
            "sender_handle": sender_handle,
            "is_from_me": bool(row["is_from_me"]),
            "text": text,
            "text_source": source,
            "item_type": row["item_type"],
            "cache_has_attachments": bool(row["cache_has_attachments"]),
            "service": row["service"],
            "attachments": [],
        }
        chats_raw[chat_id]["messages"].append(msg)

    # Serialise — one file per conversation
    import re

    def _safe_filename(title: str) -> str:
        slug = re.sub(r"[^\w\s-]", "", title).strip()
        slug = re.sub(r"[\s]+", "_", slug)
        return slug[:60] or "untitled"

    conversations = list(chats_raw.values())
    config.JSON_CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

    index_entries = []
    for conv in conversations:
        messages_clean = [
            {k: v for k, v in m.items() if k != "text_source"}
            for m in conv["messages"]
        ]
        conv_out = {**conv, "messages": messages_clean}

        filename = f"{conv['chat_id']:04d}_{_safe_filename(conv['title'])}.json"
        conv_out["filename"] = filename
        path = config.JSON_CONVERSATIONS_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(conv_out, f, indent=2, ensure_ascii=False)

        last_ts = next(
            (m["timestamp"] for m in reversed(messages_clean) if m.get("timestamp")),
            None,
        )
        index_entries.append({
            "chat_id": conv["chat_id"],
            "title": conv["title"],
            "style": conv["style"],
            "participants": conv["participants"],
            "message_count": len(messages_clean),
            "last_timestamp": last_ts,
            "filename": filename,
        })

    with open(config.JSON_INDEX, "w", encoding="utf-8") as f:
        json.dump(index_entries, f, indent=2, ensure_ascii=False)

    stats["total_conversations"] = len(conversations)
    stats["conversations_raw"] = conversations  # kept in memory for validate.py
    return stats
