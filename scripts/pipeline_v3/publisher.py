from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        import fcntl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def publish_release(catalog_path: Path, status_path: Path, releases_dir: Path,
                    release_id: str, catalog: dict, status: dict) -> tuple[Path, Path]:
    release_dir = releases_dir / release_id
    if release_dir.exists():
        raise FileExistsError(f"release already exists: {release_id}")
    release_catalog = release_dir / "catalog.json"
    release_status = release_dir / "status.json"
    atomic_write_json(release_catalog, catalog)
    atomic_write_json(release_status, status)
    atomic_write_json(catalog_path, catalog)
    atomic_write_json(status_path, status)
    return release_catalog, release_status
