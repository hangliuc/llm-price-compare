from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    output_path: Path
    status_path: Path
    db_path: Path
    manual_dir: Path
    lock_path: Path
    provider_min_ratio: float = 0.50
    dataset_min_ratio: float = 0.70
    min_providers: int = 3
    min_products: int = 20

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        output = Path(os.environ.get("PPK_OUTPUT_PATH", "data/prices.json"))
        runtime = Path(os.environ.get("PPK_RUNTIME_DIR", "runtime"))
        return cls(
            output_path=output,
            status_path=Path(os.environ.get("PPK_STATUS_PATH", "data/run_status.json")),
            db_path=Path(os.environ.get("PPK_DB_PATH", str(runtime / "prices.db"))),
            manual_dir=Path(os.environ.get("PPK_MANUAL_DIR", "data/manual")),
            lock_path=Path(os.environ.get("PPK_LOCK_PATH", str(runtime / "pipeline.lock"))),
            provider_min_ratio=float(os.environ.get("PPK_PROVIDER_MIN_RATIO", "0.50")),
            dataset_min_ratio=float(os.environ.get("PPK_DATASET_MIN_RATIO", "0.70")),
            min_providers=int(os.environ.get("PPK_MIN_PROVIDERS", "3")),
            min_products=int(os.environ.get("PPK_MIN_PRODUCTS", "20")),
        )

