import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from imessage_archiver import copy_dbs, extract, validate

print("=== Milestone 2: Attachment resolution ===\n")

print("Step 1: Copying databases to scratch dir...")
copy_dbs.run()

print("\nStep 2: Extracting messages and resolving attachments...")
stats = extract.run()
print(f"  Done — {stats['total_conversations']} conversations, {stats['total_messages']} messages")
print(f"  Attachments: {stats['copied']} copied, {stats['skipped_existing']} skipped, "
      f"{stats['missing_in_backup']} missing, {stats['not_in_media_domain']} temp files")

validate.run_milestone2(stats)
