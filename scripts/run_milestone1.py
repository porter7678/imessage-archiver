import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from imessage_archiver import copy_dbs, extract, validate

print("=== Milestone 1: Data extraction → JSON ===\n")

print("Step 1: Copying databases to scratch dir...")
copy_dbs.run()

print("\nStep 2: Extracting messages...")
stats = extract.run()
print(f"  Done — {stats['total_conversations']} conversations, {stats['total_messages']} messages")

validate.run(stats)
