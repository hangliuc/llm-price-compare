import json
import fcntl
import os
from pathlib import Path
import tempfile
from typing import Optional, Tuple


class PipelineLocked(RuntimeError):
    pass


class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            raise PipelineLocked("another pipeline run is active") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
        try:
            directory = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except (AttributeError, OSError):
            pass
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def publish(catalog_path: Path, status_path: Path, catalog: dict, status: dict,
            releases_dir: Optional[Path] = None) -> None:
    """Persist an immutable release, then atomically replace public pointers."""
    if releases_dir is not None:
        release_id = status["release_id"]
        release_path = releases_dir / release_id
        if release_path.exists():
            raise FileExistsError(f"release already exists: {release_id}")
        atomic_write_json(release_path / "catalog.json", catalog)
        atomic_write_json(release_path / "status.json", status)
    atomic_write_json(catalog_path, catalog)
    atomic_write_json(status_path, status)


def load_release(releases_dir: Path, release_id: str) -> Tuple[dict, dict]:
    release_path = releases_dir / release_id
    try:
        catalog = json.loads((release_path / "catalog.json").read_text(encoding="utf-8"))
        status = json.loads((release_path / "status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid release: {release_id}") from exc
    if catalog.get("release_id") != release_id or status.get("release_id") != release_id:
        raise ValueError(f"release identity mismatch: {release_id}")
    return catalog, status


def rollback(catalog_path: Path, status_path: Path, releases_dir: Path,
             release_id: str, rolled_back_at: str) -> dict:
    catalog, original_status = load_release(releases_dir, release_id)
    status = dict(original_status)
    status.update({
        "status": "healthy",
        "rolled_back_at": rolled_back_at,
        "rollback_target": release_id,
    })
    atomic_write_json(catalog_path, catalog)
    atomic_write_json(status_path, status)
    return status


__all__ = ["FileLock", "PipelineLocked", "atomic_write_json", "publish",
           "load_release", "rollback"]
