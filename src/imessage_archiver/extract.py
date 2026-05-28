import json
import re
import sqlite3
from datetime import datetime, timezone
from . import attachments as att_mod
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


def _safe_filename(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title).strip()
    slug = re.sub(r"[\s]+", "_", slug)
    return slug[:60] or "untitled"


def run() -> dict:
    """Extract all conversations from sms.db with attachment resolution. Returns stats dict."""
    db_uri = f"file:{config.SCRATCH_SMS_DB}?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True)
    conn.row_factory = sqlite3.Row

    # --- Build attachment lookups ---
    print("  Building Manifest.db lookup...")
    manifest_lookup = att_mod.build_manifest_lookup()
    print(f"  Loaded {len(manifest_lookup)} Manifest entries")
    attachments_by_msg = att_mod.query_message_attachments(conn)
    print(f"  Found attachments for {len(attachments_by_msg)} messages")

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
    stats: dict = {
        "total_messages": 0,
        "text_source_text": 0,
        "text_source_attributed": 0,
        "text_source_empty": 0,
        "empty_confirmed_blank": 0,
        "empty_both_null": 0,
        "unresolved_handles": set(),
        # attachment stats (populated by attachments.process_attachment)
        "total_attachments": 0,
        "copied": 0,
        "skipped_existing": 0,
        "missing_in_backup": 0,
        "not_in_media_domain": 0,
        "sha1_fallback": 0,
        "copy_errors": 0,
        "bytes_copied": 0,
        "failed_mimes": {},
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

            folder_name = f"{chat_id:04d}_{_safe_filename(title)}"
            chats_raw[chat_id] = {
                "chat_id": chat_id,
                "chat_identifier": row["chat_identifier"],
                "title": title,
                "style": "group" if row["chat_style"] == 43 else "1-on-1",
                "participants": parts,
                "folder_name": folder_name,
                "messages": [],
            }

        folder_name = chats_raw[chat_id]["folder_name"]

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

        # Resolve attachments for this message
        msg_attachments = []
        for att_row in attachments_by_msg.get(row["msg_id"], []):
            att_dict = att_mod.process_attachment(att_row, folder_name, manifest_lookup, stats)
            msg_attachments.append(att_dict)

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
            "attachments": msg_attachments,
        }
        chats_raw[chat_id]["messages"].append(msg)

    # Serialise — one file per conversation
    conversations = list(chats_raw.values())
    config.JSON_CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

    index_entries = []
    for conv in conversations:
        messages_clean = [
            {k: v for k, v in m.items() if k != "text_source"}
            for m in conv["messages"]
        ]
        filename = f"{conv['folder_name']}.json"
        conv_out = {
            k: v for k, v in conv.items() if k != "folder_name"
        }
        conv_out["messages"] = messages_clean
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
