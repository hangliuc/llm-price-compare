from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class V3Config:
    runtime_dir: Path
    db_path: Path
    catalog_path: Path
    status_path: Path
    releases_dir: Path
    raw_dir: Path
    lock_path: Path
    models_dev_url: str
    fx_url: str = "https://api.frankfurter.dev/v1/latest?base=EUR"
    timeout_seconds: int = 45
    minimum_offer_count: int = 250
    minimum_plan_count: int = 30
    maximum_drop_ratio: float = 0.20

    @classmethod
    def from_env(cls) -> "V3Config":
        runtime = Path(os.environ.get("PPK_RUNTIME_DIR", "runtime/v3"))
        public = Path(os.environ.get("PPK_PUBLIC_DIR", "runtime/public"))
        return cls(
            runtime_dir=runtime,
            db_path=Path(os.environ.get("PPK_DB_PATH", runtime / "ppk.db")),
            catalog_path=Path(os.environ.get(
                "PPK_CATALOG_PATH", public / "catalog.json")),
            status_path=Path(os.environ.get(
                "PPK_STATUS_PATH", public / "status.json")),
            releases_dir=Path(os.environ.get(
                "PPK_RELEASES_DIR", runtime / "releases")),
            raw_dir=Path(os.environ.get("PPK_RAW_DIR", runtime / "raw")),
            lock_path=Path(os.environ.get(
                "PPK_LOCK_PATH", runtime / "pipeline.lock")),
            models_dev_url=os.environ.get(
                "PPK_MODELS_DEV_URL", "https://models.dev/api.json"),
            # Frankfurter is a public, ECB-backed daily reference-rate API.
            # This value is injectable for tests and operations.
            fx_url=os.environ.get(
                "PPK_FX_URL", "https://api.frankfurter.dev/v1/latest?base=EUR"),
            timeout_seconds=int(os.environ.get("PPK_HTTP_TIMEOUT", "45")),
            minimum_offer_count=int(os.environ.get(
                "PPK_MINIMUM_OFFER_COUNT", "250")),
            minimum_plan_count=int(os.environ.get(
                "PPK_MINIMUM_PLAN_COUNT", "30")),
            maximum_drop_ratio=float(os.environ.get(
                "PPK_MAXIMUM_DROP_RATIO", "0.20")),
        )
