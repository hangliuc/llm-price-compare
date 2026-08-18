"""Deprecated compatibility entrypoint.

Scheduling, Git publishing and orchestration moved to ``scripts.pipeline``.
Use ``python3 -m scripts.pipeline.cli run`` for new automation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.pipeline.cli import main as pipeline_main


def main() -> int:
    return pipeline_main(["run"])


if __name__ == "__main__":
    raise SystemExit(main())
