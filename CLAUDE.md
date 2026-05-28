# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Python tool that extracts all iMessage/SMS conversations from a local (unencrypted) iPhone backup and produces:
- A browsable HTML archive (chat-bubble UI, embedded media)
- A raw `messages.json` export

Full specification is in `SPEC.md`. Work through it milestone by milestone; **stop for developer confirmation at the end of each milestone before proceeding.**

## Paths

| Resource | Path |
|---|---|
| Backup source | `/mnt/d/MobileSync/Backup` |
| Output target | `/mnt/d/iMessageExport/` |
| Scratch working dir (copies of DBs) | `data/` inside this repo |
| Contacts vCard | `porter_contacts.vcf` (already in repo root) |

`sms.db` lives at `Backup/<device-id>/3d/3d0d7e5fb2ce288813306e4d4636395e047a3d28`. Always copy DBs to `data/` before opening — never open originals in place.

## Setup

Use `uv` for dependency management. Prefer stdlib (`sqlite3`, `shutil`, `pathlib`, `hashlib`, `json`, `html`). Add third-party packages only when they meaningfully earn their place; flag each one added.

```bash
uv run python <script.py>
```

## Critical implementation details

These are the silent failure modes that break naive iMessage exporters:

1. **Timestamps are nanoseconds since 2001-01-01 UTC** (Cocoa epoch). Convert: `unix_seconds = (date / 1_000_000_000) + 978307200`. Render in local time.

2. **`text` is often NULL — fall back to `attributedBody`**. Many rows on recent iOS have `text = NULL` with content in the `attributedBody` BLOB (NSAttributedString / Apple typedstream). Use an existing pure-Python typedstream parser rather than writing one from scratch. Validate that attributedBody messages come through with real content.

3. **Filter out tapbacks/reactions**: skip rows where `message.associated_message_type != 0`.

4. **Attachment resolution dance**:
   - `attachment.filename` = original on-device path (e.g. `~/Library/SMS/Attachments/ab/12/...`)
   - Look up in `Manifest.db` `Files` table (domain=`MediaDomain`, relativePath = path without `~/`)
   - Hashed backup filename = `SHA1("MediaDomain-" + relativePath)` — prefer Manifest.db lookup, use SHA1 as fallback
   - Copy to output as `attachments/<conversation-name>/<transfer_name>`

5. **Contact normalization**: match `handle.id` (phone/email) against the `.vcf` by last 10 digits for US numbers. Fall back to raw number, never drop conversations.

## Output structure

```
/mnt/d/iMessageExport/
├── index.html
├── conversations/<Name or chat id>.html
├── attachments/<per-conversation folders>
├── json/messages.json
└── README.txt
```

Scripts must be **idempotent** (safe to wipe output and regenerate from scratch).

## Milestone gate

SPEC.md defines three milestones with specific validation reports. Do not advance past a milestone without the developer's explicit confirmation. Each milestone ends with a terminal validation report (counts, samples, error flags).
