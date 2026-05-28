# iMessage Export — Claude Code Project Brief

## Goal

Extract **all** text conversations (SMS + iMessage, 1-on-1 and group) from a local iPhone backup into two deliverables:

1. **A browsable HTML archive** that looks roughly like the Messages app (bubbles, sender names, timestamps, embedded photos/videos/attachments).
2. **A raw JSON export** for future processing/scripting.

This is an archival/personal project. Accuracy and completeness matter more than speed.

---

## Environment

- **OS:** Windows 10 with WSL. Claude Code runs inside WSL.
- **Language:** Python (developer is comfortable with Python — write clean, readable Python, no need to over-explain basics).
- **Drive mapping:** The `D:` drive is accessible from WSL at `/mnt/d/`.
  - Backup source: `/mnt/d/MobileSync/Backup`
  - Output target: `/mnt/d/iMessageExport`
- Prefer the Python standard library where reasonable (`sqlite3`, `shutil`, `pathlib`, `hashlib`, `json`, `html`). Add third-party deps only if they earn their place — call out anything you install.

---

## Source data — what's in the backup and where

The backup is **unencrypted**, so files can be read/copied directly (no decryption step needed).

### Database files
- `sms.db` — SQLite, holds all messages. In the backup it's stored under a hashed filename:
  - Hash: `3d0d7e5fb2ce288813306e4d4636395e047a3d28`
  - Location: `Backup/<device-id>/3d/3d0d7e5fb2ce288813306e4d4636395e047a3d28`
  - (The first two hex chars `3d` are the subfolder.)
- `Manifest.db` — SQLite, at the root of the backup folder. Maps original on-device file paths → hashed backup filenames. Needed to locate attachment files.

> **Always copy these DBs to a scratch working dir before opening them** — don't open the originals in place.

### Key `sms.db` tables/columns
- `message` — `ROWID`, `guid`, `text`, `attributedBody`, `handle_id`, `is_from_me`, `date`, `date_read`, `service`, `associated_message_type`, `cache_has_attachments`
- `handle` — `ROWID`, `id` (phone number or email of the other party)
- `chat` — `ROWID`, `chat_identifier`, `display_name`, `style` (group vs 1-on-1)
- `chat_message_join` — links `chat.ROWID` ↔ `message.ROWID`
- `chat_handle_join` — links `chat.ROWID` ↔ `handle.ROWID` (group participants)
- `attachment` — `ROWID`, `filename`, `mime_type`, `transfer_name`
- `message_attachment_join` — links `message.ROWID` ↔ `attachment.ROWID`

---

## ⚠️ Known landmines — read before coding

These are the things that quietly break naive iMessage exporters. Handle them up front.

1. **Timestamp format.** Modern iOS stores `message.date` as **nanoseconds since 2001-01-01 00:00:00 UTC** (Mac/Cocoa absolute time epoch). Convert to Unix time with: `unix_seconds = (date / 1_000_000_000) + 978307200`. (Very old backups used seconds, not nanoseconds — detect by magnitude if you want to be safe, but this iPhone 15 backup will be nanoseconds.) Render timestamps in **local time**.

2. **`text` is often NULL — the message lives in `attributedBody`.** On recent iOS, many rows have `text = NULL` and the actual content serialized in the `attributedBody` BLOB (an `NSAttributedString` / Apple `typedstream`). You must extract text from `attributedBody` when `text` is empty, or you'll silently lose a large fraction of messages. A pragmatic approach: parse the typedstream blob to pull out the string payload (there are small pure-Python parsers for this, or you can extract the readable run between known typedstream markers). **Verify** that messages with NULL text but non-NULL attributedBody come through with real content before declaring done.

3. **Reactions/tapbacks — SKIP them.** Rows where `associated_message_type` is non-zero are tapbacks (Liked/Loved/Laughed/etc.) and edit/other associated messages. Filter these out so they don't appear as junk standalone messages.

4. **Attachment resolution (the hashed-filename dance).**
   - `attachment.filename` gives the original on-device path, e.g. `~/Library/SMS/Attachments/ab/12/...`.
   - The corresponding relative path in `Manifest.db` lives under the **`MediaDomain`** domain with `relativePath` like `Library/SMS/Attachments/ab/12/...`.
   - The hashed backup filename = `SHA1("MediaDomain-" + relativePath)` (40 hex chars), stored at `Backup/<device-id>/<first2chars>/<fullhash>`.
   - Prefer querying `Manifest.db`'s `Files` table (`fileID`, `domain`, `relativePath`) to look up the hash rather than recomputing — but the SHA1 formula is a good fallback/sanity check.
   - Copy attachments out into the output, renamed to something human-readable (use `attachment.transfer_name` for the original filename).

5. **Sent vs received:** `is_from_me` (1 = sent by me, 0 = received).

6. **Group vs 1-on-1:** use `chat.style` / participant count from `chat_handle_join`. Group chats may have a `display_name`; if not, build one from participant names.

---

## Contact name resolution

Phone numbers/emails in `handle.id` are raw. The developer will provide an exported **`.vcf` (vCard) file** of their contacts. Parse it to build a `{normalized_number_or_email → display_name}` map.

- Normalize phone numbers before matching (strip spaces, dashes, parens; handle `+1` country code vs not). A reasonable strategy: compare on the last 10 digits for US numbers.
- Fall back to the raw number/email when no contact match is found — never drop a conversation just because the name is unknown.
- **Ask the developer for the `.vcf` path** (or look in the project dir) before relying on it.

---

## Deliverables / output structure

Target: `/mnt/d/iMessageExport/` (i.e. `D:\iMessageExport`)

Suggested layout (adjust if you have a better idea — explain if you deviate):

```
D:\iMessageExport\
├── index.html                  # landing page: list of all conversations, linked
├── conversations\
│   ├── <Name or chat id>.html  # one browsable HTML page per conversation
│   └── ...
├── attachments\
│   └── <per-conversation folders of copied media>
├── json\
│   └── messages.json           # full structured export (see below)
└── README.txt                  # short note on what this is + how it was generated
```

### HTML requirements
- Conversation list / index linking to each thread, ideally with last-message date and participant name.
- Per-conversation pages styled like a chat: sender name, message bubbles aligned by sender (me vs them), timestamps.
- **Attachments embedded inline**: images and video shown in the page (`<img>`, `<video>`); other file types shown as a link to the copied file.
- Keep it self-contained and openable directly in a browser (relative links to the `attachments` folder are fine).
- Doesn't need to be fancy — clean and readable beats pixel-perfect.

### JSON requirements
- Structured for easy future scripting. Suggested shape: a list of conversations, each with participants and an ordered list of messages; each message with `timestamp` (ISO 8601 local), `sender` (resolved name + raw handle), `is_from_me`, `text`, and `attachments` (list of relative paths + mime types).
- For JSON, attachments are **referenced by relative path** (pointing at the copied files in `attachments\`), since embedding binary in JSON isn't useful.

---

## Milestones

Work through these in order. **Stop and surface a validation report at the end of each milestone before proceeding.** The developer will confirm before you continue.

---

### Milestone 1 — Data extraction → JSON

This is the highest-risk phase. Everything downstream depends on the data being correct here.

**Tasks:**
1. Set up a scratch working dir inside the repo (`data/`); copy `sms.db` and `Manifest.db` from the backup into it.
2. Build the contact name map by parsing the `.vcf` file.
3. Query `sms.db`: join `message`, `handle`, `chat`, `chat_message_join`, `chat_handle_join`. Filter out reactions (`associated_message_type != 0`).
4. Resolve message text — `text` column first, fall back to `attributedBody` BLOB. For `attributedBody` parsing, **find and adapt an existing pure-Python typedstream/NSAttributedString parser** rather than writing one from scratch — this is well-trodden ground and a known fiddly format.
5. Convert timestamps (nanoseconds since 2001-01-01 → local time ISO 8601).
6. Emit `json/messages.json` with the full conversation/message structure.

**At the end of Milestone 1, output a validation report to the terminal:**
- Total conversations found
- Total messages found
- Count of messages where text came from `text` column vs `attributedBody`
- Count of messages where both were NULL/empty (flag these — they may be attachment-only, which is fine, or a parsing gap)
- Count of unresolved handles (no contact name match)
- Sample: print the first 3 messages from 2 different conversations so the developer can sanity-check names, timestamps, and content

**Do not proceed to Milestone 2 until the developer confirms the JSON looks correct.**

---

### Milestone 2 — Attachment resolution

**Tasks:**
1. Build a lookup from `Manifest.db`'s `Files` table (`fileID`, `domain`, `relativePath`) keyed on the attachment's original on-device path.
2. For each attachment in `message_attachment_join` / `attachment` table, resolve the hashed backup file and copy it into `attachments/<conversation-name>/` with a human-readable filename (use `attachment.transfer_name`).
3. Update `messages.json` so each message's `attachments` array contains the relative path to the copied file and its `mime_type`.

**At the end of Milestone 2, output a validation report:**
- Total attachments found in `sms.db`
- Count successfully resolved and copied
- Count not found in backup (missing files — flag but don't fail)
- List any mime types that weren't resolved (helps catch lookup bugs)

**Do not proceed to Milestone 3 until the developer confirms attachments look right** (i.e. spot-checks that known photos are present and named sensibly).

---

### Milestone 3 — HTML generation

With validated JSON and attachments, this phase is low-risk — purely a rendering concern.

**Tasks:**
1. Generate `conversations/<name>.html` for each conversation: chat-bubble layout, sender name, local timestamps, sent/received alignment.
2. Embed attachments inline: `<img>` for images, `<video>` for video, linked file for everything else.
3. Generate `index.html`: list of all conversations with participant names and last-message date, linked to their respective pages.
4. Generate `README.txt` with a short note (what this archive is, when it was generated, source device).

**Style guidance:** clean and readable beats pixel-perfect. Doesn't need to look exactly like Messages — just be usable.

**Milestone 3 validation checklist:**
- [ ] `index.html` opens in a browser and links to every conversation
- [ ] Spot-checked conversation shows correct names, sent/received alignment, readable timestamps
- [ ] Messages that came from `attributedBody` have real text content (not blank bubbles)
- [ ] Photos/videos appear inline; other attachments are clickable links
- [ ] No tapback/reaction messages appear
- [ ] Group chats show participant names

---

## General notes

- Write all scripts so they can be **re-run idempotently** (safe to wipe the output dir and regenerate from scratch).
- Prefer the Python standard library where reasonable. Add third-party deps only if they meaningfully earn their place — flag anything you install.
- For `attributedBody` parsing specifically: look for an existing battle-tested snippet rather than writing your own typedstream parser from scratch.

---

## Notes / open items for the developer to confirm

- Path to the exported `.vcf` contacts file.
- Confirm the `<device-id>` subfolder name inside `Backup\` (there should be exactly one folder with a long hex/GUID name).
