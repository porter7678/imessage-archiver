# imessage-archiver

Extracts all iMessage/SMS conversations from a local (unencrypted) iPhone backup and produces:

- A browsable HTML archive with a chat-bubble UI and embedded media
- A raw `messages.json` export for scripting

## Requirements

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/)
- An unencrypted local iPhone backup (iTunes/Finder backup on Windows, accessible at `/mnt/d/MobileSync/Backup` from WSL)

## Setup

```bash
uv sync
```

## Usage

```bash
uv run python scripts/archive.py
```

Output is written to `/mnt/d/iMessageExport/`. Open `index.html` in any browser.

## Output structure

```
/mnt/d/iMessageExport/
├── index.html                  # landing page: all conversations, linked
├── conversations/
│   └── <Name>.html             # one page per conversation
├── attachments/
│   └── <per-conversation folders>
├── json/
│   ├── index.json
│   └── conversations/          # one JSON file per conversation
└── README.txt
```

## Configuration

Paths and device ID are in `src/imessage_archiver/config.py`. Update `DEVICE_ID` and `BACKUP_ROOT` if your backup location differs.

## Re-running

The script is idempotent — safe to wipe the output directory and regenerate from scratch. Attachment copies are skipped if the file already exists and the size matches.

## Notes

- Tapbacks and reactions are filtered out.
- Message text falls back from the `text` column to `attributedBody` (Apple typedstream) automatically.
- Timestamps are rendered in local time (converted from Cocoa nanoseconds since 2001-01-01).
- Phone numbers are matched against `porter_contacts.vcf` by last 10 digits; unmatched handles fall back to the raw number.
