from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class V2Config:
    runtime_dir: Path
    db_path: Path
    catalog_path: Path
    status_path: Path
    manual_dir: Path
    alias_path: Path
    lock_path: Path
    run_status_path: Optional[Path] = None
    releases_dir: Optional[Path] = None
    evidence_dir: Optional[Path] = None
    evidence_retention_days: int = 90

    @classmethod
    def from_env(cls) -> "V2Config":
        runtime = Path(os.environ.get("PPK_V2_RUNTIME_DIR", "runtime/v2"))
        public = runtime / "public" / "v2"
        return cls(
            runtime_dir=runtime,
            db_path=Path(os.environ.get("PPK_V2_DB_PATH", runtime / "prices-v2.db")),
            catalog_path=Path(os.environ.get("PPK_V2_CATALOG_PATH", public / "catalog.json")),
            status_path=Path(os.environ.get("PPK_V2_STATUS_PATH", public / "status.json")),
            run_status_path=Path(os.environ.get(
                "PPK_V2_RUN_STATUS_PATH", runtime / "public" / "run_status.json")),
            releases_dir=Path(os.environ.get(
                "PPK_V2_RELEASES_DIR", runtime / "releases")),
            evidence_dir=Path(os.environ.get(
                "PPK_V2_EVIDENCE_DIR", runtime / "raw")),
            evidence_retention_days=int(os.environ.get(
                "PPK_V2_EVIDENCE_RETENTION_DAYS", "90")),
            manual_dir=Path(os.environ.get("PPK_V2_MANUAL_DIR", "data/manual")),
            alias_path=Path(os.environ.get(
                "PPK_V2_ALIAS_PATH", "data/identity/model_aliases.yaml")),
            lock_path=Path(os.environ.get("PPK_V2_LOCK_PATH", runtime / "pipeline.lock")),
        )
