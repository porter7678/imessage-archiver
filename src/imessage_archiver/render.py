"""Generate browsable HTML from the JSON produced by extract.run()."""

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from . import config

# ---------------------------------------------------------------------------
# Shared CSS — embedded inline in every page so each file is self-contained.
# ---------------------------------------------------------------------------
_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: #fff;
    color: #000;
    font-size: 15px;
    line-height: 1.4;
}
a { color: #0b93f6; text-decoration: none; }
a:hover { text-decoration: underline; }

/* ---------- index ---------- */
.index-wrap { max-width: 720px; margin: 0 auto; padding: 24px 16px 48px; }
.index-wrap h1 { font-size: 1.4rem; margin-bottom: 16px; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; font-size: 0.8rem; color: #888; padding: 4px 8px; border-bottom: 1px solid #e0e0e0; }
td { padding: 8px 8px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }
td:last-child { white-space: nowrap; font-size: 0.85rem; color: #888; text-align: right; }
tr:hover td { background: #f9f9f9; }

/* ---------- conversation ---------- */
.conv-wrap { max-width: 720px; margin: 0 auto; padding: 0 16px 48px; }
.conv-header { position: sticky; top: 0; background: rgba(255,255,255,0.92);
    backdrop-filter: blur(6px); padding: 12px 0 10px; border-bottom: 1px solid #e0e0e0;
    margin-bottom: 12px; z-index: 10; }
.conv-header h1 { font-size: 1.1rem; }
.conv-header .sub { font-size: 0.8rem; color: #888; margin-top: 2px; }
.back { font-size: 0.85rem; display: block; margin-bottom: 6px; }

.day-sep { text-align: center; margin: 20px 0 8px; }
.day-sep span {
    display: inline-block; font-size: 0.75rem; color: #888;
    background: #f0f0f0; border-radius: 12px; padding: 2px 12px;
}

.msg-row { display: flex; margin-bottom: 2px; }
.msg-row.me { justify-content: flex-end; }
.msg-row.them { justify-content: flex-start; }

.sender-label {
    font-size: 0.72rem; color: #888; margin-left: 10px; margin-bottom: 2px;
}

.bubble-wrap { max-width: 72%; }
.bubble {
    display: inline-block; padding: 8px 12px; border-radius: 18px;
    word-break: break-word; white-space: pre-wrap;
}
.me .bubble { background: #0b93f6; color: #fff; border-bottom-right-radius: 4px; }
.them .bubble { background: #e5e5ea; color: #000; border-bottom-left-radius: 4px; }

.ts {
    font-size: 0.68rem; color: #aaa; margin-top: 3px;
    display: block;
}
.me .ts { text-align: right; margin-right: 4px; }
.them .ts { text-align: left; margin-left: 4px; }

/* media */
.att-img { display: block; max-width: 100%; border-radius: 12px; margin-top: 4px; }
.att-video { display: block; max-width: 100%; border-radius: 12px; margin-top: 4px; }
.att-audio { display: block; width: 100%; margin-top: 4px; }
.att-unavail { font-size: 0.8rem; font-style: italic; color: #aaa; }
"""

_URL_RE = re.compile(r"(https?://[^\s<\"']+)")


def _linkify(text: str) -> str:
    """Escape HTML then wrap bare URLs in <a> tags."""
    escaped = html.escape(text)
    return _URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener">\1</a>', escaped)


def _page(title: str, body: str) -> str:
    safe_title = html.escape(title)
    return (
        f'<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        f'<meta charset="utf-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{safe_title}</title>\n'
        f'<style>{_CSS}</style>\n'
        f'</head>\n<body>\n{body}\n</body>\n</html>\n'
    )


def _parse_ts(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _fmt_time(iso: str | None) -> str:
    dt = _parse_ts(iso)
    if dt is None:
        return ""
    return dt.strftime("%-I:%M %p")


def _fmt_date_sep(dt: datetime) -> str:
    return dt.strftime("%A, %B %-d, %Y")


def _group_by_day(messages: list[dict]):
    current_day = None
    batch: list[dict] = []
    for msg in messages:
        dt = _parse_ts(msg.get("timestamp"))
        day = dt.date() if dt else None
        if day != current_day:
            if batch:
                yield current_day, batch
            current_day = day
            batch = [msg]
        else:
            batch.append(msg)
    if batch:
        yield current_day, batch


def _render_attachment(att: dict, conv_folder: str) -> str:
    status = att.get("status")
    if status == "skipped":
        return ""
    transfer_name = html.escape(att.get("transfer_name") or "attachment")
    if status != "copied":
        return f'<span class="att-unavail">[attachment unavailable: {transfer_name}]</span>'

    rel_path = att.get("path", "")
    # path in JSON is relative from OUTPUT_ROOT, e.g. attachments/0001_Name/file.jpg
    # HTML file is at conversations/<folder>.html, so we need ../rel_path
    href = html.escape("../" + rel_path)
    mime = att.get("mime_type") or ""

    if mime.startswith("image/"):
        return f'<img class="att-img" src="{href}" alt="{transfer_name}" loading="lazy">'
    if mime.startswith("video/"):
        return f'<video class="att-video" controls preload="metadata" src="{href}"></video>'
    if mime.startswith("audio/"):
        return f'<audio class="att-audio" controls src="{href}"></audio>'
    return f'<a href="{href}">{transfer_name}</a>'


def _render_message(msg: dict, chat_style: str, stats: dict) -> str:
    is_me = msg.get("is_from_me", False)
    side = "me" if is_me else "them"
    sender_name = html.escape(msg.get("sender_name") or "")
    ts_str = _fmt_time(msg.get("timestamp"))

    parts: list[str] = []

    # Sender label — only for "them" in group chats
    if not is_me and chat_style == "group":
        parts.append(f'<div class="sender-label">{sender_name}</div>')

    # Text content
    text = msg.get("text") or ""
    text_html = _linkify(text).replace("\n", "<br>") if text else ""

    # Attachments
    att_html_parts: list[str] = []
    for att in msg.get("attachments") or []:
        att_html = _render_attachment(att, "")
        att_html_parts.append(att_html)
        mime = att.get("mime_type") or ""
        if att.get("status") == "copied":
            if mime.startswith("image/"):
                stats["inline_images"] += 1
            elif mime.startswith("video/"):
                stats["inline_videos"] += 1
            elif mime.startswith("audio/"):
                stats["inline_audio"] += 1
            else:
                stats["inline_other"] += 1
        else:
            stats["unavailable_attachments"] += 1

    bubble_inner = text_html
    if att_html_parts:
        if bubble_inner:
            bubble_inner += "<br>"
        bubble_inner += "".join(att_html_parts)

    if not bubble_inner:
        return ""

    ts_tag = f'<span class="ts">{html.escape(ts_str)}</span>' if ts_str else ""
    bubble = f'<div class="bubble">{bubble_inner}</div>'
    parts.append(f'<div class="bubble-wrap">{bubble}{ts_tag}</div>')

    inner = "\n".join(parts)
    return f'<div class="msg-row {side}">{inner}</div>\n'


def _render_conversation_html(conv: dict, stats: dict) -> str:
    title = conv.get("title") or "Conversation"
    style = conv.get("style") or "1-on-1"
    participants = conv.get("participants") or []
    messages = conv.get("messages") or []

    if style == "group":
        parts_str = ", ".join(p.get("name", p.get("handle", "?")) for p in participants)
        sub = html.escape(f"Group · {parts_str}")
    else:
        sub = html.escape(f"{len(messages)} messages")

    header = (
        f'<div class="conv-header">'
        f'<a class="back" href="../index.html">← All conversations</a>'
        f'<h1>{html.escape(title)}</h1>'
        f'<div class="sub">{sub}</div>'
        f'</div>'
    )

    body_parts: list[str] = [header, '<div class="conv-wrap">']

    for day, day_msgs in _group_by_day(messages):
        label = _fmt_date_sep(datetime.combine(day, datetime.min.time())) if day else "Unknown date"
        body_parts.append(
            f'<div class="day-sep"><span>{html.escape(label)}</span></div>\n'
        )
        for msg in day_msgs:
            msg_html = _render_message(msg, style, stats)
            if msg_html:
                body_parts.append(msg_html)

    body_parts.append("</div>")
    body = "\n".join(body_parts)
    return _page(title, body)


def _render_index_html(index_entries: list[dict]) -> str:
    sorted_entries = sorted(
        index_entries,
        key=lambda e: e.get("last_timestamp") or "",
        reverse=True,
    )

    rows: list[str] = []
    for entry in sorted_entries:
        title = html.escape(entry.get("title") or "Untitled")
        filename = entry.get("filename", "")
        html_file = filename.replace(".json", ".html")
        href = html.escape(f"conversations/{html_file}")
        style = entry.get("style") or "1-on-1"
        count = entry.get("message_count", 0)
        last_ts = entry.get("last_timestamp") or ""
        dt = _parse_ts(last_ts)
        date_str = dt.strftime("%b %-d, %Y") if dt else ""

        style_badge = " <small style='color:#888;font-size:0.75rem'>[group]</small>" if style == "group" else ""
        rows.append(
            f'<tr>'
            f'<td><a href="{href}">{title}</a>{style_badge}</td>'
            f'<td>{count:,} messages</td>'
            f'<td>{html.escape(date_str)}</td>'
            f'</tr>'
        )

    table = (
        '<table>\n'
        '<tr><th>Conversation</th><th>Messages</th><th>Last message</th></tr>\n'
        + "\n".join(rows)
        + '\n</table>'
    )
    body = (
        '<div class="index-wrap">\n'
        '<h1>iMessage Archive</h1>\n'
        + table
        + '\n</div>'
    )
    return _page("iMessage Archive", body)


def _load_conversations() -> list[dict]:
    with open(config.JSON_INDEX, encoding="utf-8") as f:
        index_entries: list[dict] = json.load(f)

    conversations = []
    for entry in index_entries:
        conv_file = config.JSON_CONVERSATIONS_DIR / entry["filename"]
        with open(conv_file, encoding="utf-8") as f:
            conversations.append(json.load(f))
    return conversations


def _write_readme(stats: dict, conv_count: int) -> None:
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    text = (
        f"iMessage Archive\n"
        f"================\n\n"
        f"This archive was generated by imessage-archiver on {now}.\n\n"
        f"Source device: {config.DEVICE_ID}\n"
        f"Conversations: {conv_count}\n"
        f"HTML pages:    {stats['pages_written']}\n\n"
        f"Structure:\n"
        f"  index.html              — list of all conversations\n"
        f"  conversations/          — one HTML page per conversation\n"
        f"  attachments/            — copied photos, videos, and other media\n"
        f"  json/                   — raw JSON export\n\n"
        f"Open index.html in any browser to browse the archive.\n"
    )
    config.README_PATH.write_text(text, encoding="utf-8")


def run() -> dict:
    """Render HTML pages from JSON. Returns render stats dict."""
    stats: dict = {
        "pages_written": 0,
        "inline_images": 0,
        "inline_videos": 0,
        "inline_audio": 0,
        "inline_other": 0,
        "unavailable_attachments": 0,
    }

    conversations = _load_conversations()
    config.HTML_CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

    for conv in conversations:
        filename = conv.get("filename", "")
        html_filename = filename.replace(".json", ".html")
        out_path = config.HTML_CONVERSATIONS_DIR / html_filename
        page_html = _render_conversation_html(conv, stats)
        out_path.write_text(page_html, encoding="utf-8")
        stats["pages_written"] += 1

    with open(config.JSON_INDEX, encoding="utf-8") as f:
        index_entries = json.load(f)

    index_html = _render_index_html(index_entries)
    config.HTML_INDEX.write_text(index_html, encoding="utf-8")

    _write_readme(stats, len(conversations))

    stats["largest_page"] = _find_largest_page()
    return stats


def _find_largest_page() -> Path | None:
    conv_dir = config.HTML_CONVERSATIONS_DIR
    if not conv_dir.exists():
        return None
    pages = sorted(conv_dir.glob("*.html"), key=lambda p: p.stat().st_size, reverse=True)
    return pages[0] if pages else None
