import hashlib
import re
import shutil
import sqlite3
from pathlib import Path
from . import config

_HEIC_SUFFIXES = {".heic", ".heif"}


def _register_heif() -> bool:
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        return True
    except ImportError:
        return False


_HEIF_AVAILABLE = _register_heif()


def build_manifest_lookup() -> dict[str, str]:
    """Return {relativePath → fileID} for all MediaDomain entries in Manifest.db."""
    uri = f"file:{config.SCRATCH_MANIFEST_DB}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    lookup: dict[str, str] = {}
    for file_id, rel_path in conn.execute(
        "SELECT fileID, relativePath FROM Files WHERE domain='MediaDomain'"
    ):
        lookup[rel_path] = file_id
    conn.close()
    return lookup


def query_message_attachments(conn: sqlite3.Connection) -> dict[int, list]:
    """Return {message_rowid → [attachment rows]} for all messages that have attachments."""
    rows = conn.execute(
        """
        SELECT maj.message_id, a.ROWID, a.filename, a.mime_type, a.transfer_name, a.total_bytes
        FROM message_attachment_join maj
        JOIN attachment a ON a.ROWID = maj.attachment_id
        WHERE a.filename IS NOT NULL
        """
    ).fetchall()
    result: dict[int, list] = {}
    for row in rows:
        result.setdefault(row["message_id"], []).append(row)
    return result


def _resolve_relpath(filename: str) -> str | None:
    """Strip leading ~/ to get MediaDomain relative path, or None if not a media domain path."""
    if filename.startswith("~/"):
        return filename[2:]
    return None


def _sha1_fallback(relpath: str) -> str:
    return hashlib.sha1(("MediaDomain-" + relpath).encode()).hexdigest()


def _backup_path_for(file_id: str) -> Path:
    return config.DEVICE_DIR / file_id[:2] / file_id


def _copy_attachment(src: Path, dest: Path) -> tuple[bool, Path]:
    """Copy (or convert) src → dest. Returns (was_new_copy, actual_dest_path).

    HEIC/HEIF files are converted to JPEG so browsers can display them inline.
    The returned dest path may differ from the input (extension changed to .jpg).
    """
    is_heic = dest.suffix.lower() in _HEIC_SUFFIXES and _HEIF_AVAILABLE
    if is_heic:
        dest = dest.with_suffix(".jpg")

    if dest.exists() and dest.stat().st_size > 0:
        return False, dest

    dest.parent.mkdir(parents=True, exist_ok=True)

    if is_heic:
        from PIL import Image
        try:
            img = Image.open(src)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(dest, "JPEG", quality=88)
        except Exception as exc:
            print(f"  [warn] HEIC conversion failed for {dest.stem}: {exc} — copying as-is")
            dest = dest.with_suffix(".heic")
            shutil.copy2(src, dest)
    else:
        shutil.copy2(src, dest)

    return True, dest


def _sanitize_dest_name(transfer_name: str, rowid: int) -> str:
    safe = re.sub(r"[^\w\s.-]", "", transfer_name).strip()
    safe = re.sub(r"\s+", "_", safe) or f"attachment_{rowid}"
    return f"{rowid}_{safe}"


def process_attachment(att_row, conv_folder_name: str, manifest_lookup: dict, stats: dict) -> dict:
    """Resolve and copy one attachment. Updates stats counters in place. Returns JSON-ready dict."""
    rowid = att_row["ROWID"]
    filename = att_row["filename"] or ""
    mime_type = att_row["mime_type"]
    transfer_name = att_row["transfer_name"] or f"attachment_{rowid}"

    stats["total_attachments"] += 1

    if (mime_type or "").startswith("video/"):
        stats["skipped_video"] = stats.get("skipped_video", 0) + 1
        return {"path": None, "mime_type": mime_type, "transfer_name": transfer_name, "status": "skipped"}

    dest_name = _sanitize_dest_name(transfer_name, rowid)
    rel_path = f"attachments/{conv_folder_name}/{dest_name}"
    dest = config.OUTPUT_ATTACHMENTS_DIR / conv_folder_name / dest_name

    result: dict = {
        "path": rel_path,
        "mime_type": mime_type,
        "transfer_name": transfer_name,
        "status": None,
    }

    relpath = _resolve_relpath(filename)
    if relpath is None:
        stats["not_in_media_domain"] += 1
        result["status"] = "not_in_media_domain"
        return result

    file_id = manifest_lookup.get(relpath)
    if file_id is not None:
        backup_path = _backup_path_for(file_id)
        if not backup_path.exists():
            stats["missing_in_backup"] += 1
            stats["failed_mimes"][mime_type or "(null)"] = (
                stats["failed_mimes"].get(mime_type or "(null)", 0) + 1
            )
            result["status"] = "missing_in_backup"
            return result
    else:
        fallback_id = _sha1_fallback(relpath)
        backup_path = _backup_path_for(fallback_id)
        if backup_path.exists():
            stats["sha1_fallback"] += 1
        else:
            stats["missing_in_backup"] += 1
            stats["failed_mimes"][mime_type or "(null)"] = (
                stats["failed_mimes"].get(mime_type or "(null)", 0) + 1
            )
            result["status"] = "missing_in_backup"
            return result

    try:
        copied, actual_dest = _copy_attachment(backup_path, dest)
    except OSError as exc:
        stats["copy_errors"] += 1
        stats["failed_mimes"][mime_type or "(null)"] = (
            stats["failed_mimes"].get(mime_type or "(null)", 0) + 1
        )
        result["status"] = "copy_error"
        result["error"] = str(exc)
        return result

    # If HEIC was converted to JPEG, update path and mime_type in the result
    if actual_dest != dest:
        result["path"] = f"attachments/{conv_folder_name}/{actual_dest.name}"
        result["mime_type"] = "image/jpeg"

    if copied:
        stats["copied"] += 1
        stats["bytes_copied"] += att_row["total_bytes"] or 0
    else:
        stats["skipped_existing"] += 1

    result["status"] = "copied"
    return result
