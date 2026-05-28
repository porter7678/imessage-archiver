import shutil
from . import config


def _needs_copy(src, dst) -> bool:
    if not dst.exists():
        return True
    return src.stat().st_mtime > dst.stat().st_mtime


def run():
    config.SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    for src, dst in [
        (config.SMS_DB_SRC, config.SCRATCH_SMS_DB),
        (config.MANIFEST_DB_SRC, config.SCRATCH_MANIFEST_DB),
    ]:
        if _needs_copy(src, dst):
            print(f"Copying {src.name} ({src.stat().st_size // 1_048_576} MB)...")
            shutil.copy2(src, dst)
            print(f"  → {dst}")
        else:
            print(f"  {dst.name} already up to date, skipping copy")
