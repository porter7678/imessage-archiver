from pathlib import Path

BACKUP_ROOT = Path("/mnt/d/MobileSync/Backup")
DEVICE_ID = "00008120-00147460212A601E"
SMS_DB_HASH = "3d0d7e5fb2ce288813306e4d4636395e047a3d28"

DEVICE_DIR = BACKUP_ROOT / DEVICE_ID
SMS_DB_SRC = DEVICE_DIR / "3d" / SMS_DB_HASH
MANIFEST_DB_SRC = DEVICE_DIR / "Manifest.db"

REPO_ROOT = Path(__file__).parent.parent.parent
SCRATCH_DIR = REPO_ROOT / "data"
CONTACTS_VCF = REPO_ROOT / "porter_contacts.vcf"

OUTPUT_ROOT = Path("/mnt/d/iMessageExport")
JSON_DIR = OUTPUT_ROOT / "json"
JSON_INDEX = JSON_DIR / "index.json"
JSON_CONVERSATIONS_DIR = JSON_DIR / "conversations"

SCRATCH_SMS_DB = SCRATCH_DIR / "sms.db"
SCRATCH_MANIFEST_DB = SCRATCH_DIR / "Manifest.db"
