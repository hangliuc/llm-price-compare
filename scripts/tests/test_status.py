# scripts/tests/test_status.py
import json
import tempfile
import os
from pathlib import Path
from scripts.core.status import update_run_status, load_run_status


def test_update_run_status_writes_file():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "run_status.json")
        update_run_status(success=True, providers_summary={"openai": "ok"}, path=path)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["consecutive_failures"] == 0
        assert data["providers_summary"]["openai"] == "ok"
        assert "last_run_at" in data
        assert "last_success_at" in data


def test_update_run_status_increments_failures():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "run_status.json")
        # 首次失败
        update_run_status(success=False, providers_summary={"x": "failed"}, path=path)
        # 第二次失败
        update_run_status(success=False, providers_summary={"x": "failed"}, path=path)
        data = load_run_status(path)
        assert data["consecutive_failures"] == 2


def test_update_run_status_resets_on_success():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "run_status.json")
        update_run_status(success=False, providers_summary={}, path=path)
        update_run_status(success=True, providers_summary={}, path=path)
        data = load_run_status(path)
        assert data["consecutive_failures"] == 0
