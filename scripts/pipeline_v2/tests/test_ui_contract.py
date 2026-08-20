from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_ui_reads_v2_catalog_and_adapts_at_boundary():
    source = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'const DATA_PATHS = ["../data/v2/catalog.json"]' in source
    assert 'DATA_PATHS.push("../runtime/v2/public/v2/catalog.json")' in source
    assert "function catalogV2ToViewData(catalog)" in source
    assert "for (const path of DATA_PATHS)" in source


def test_production_web_mount_exposes_v2_public_directory():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "./runtime/public:/usr/share/nginx/html/data:ro" in compose
    assert "PPK_V2_CATALOG_PATH=/app/public/v2/catalog.json" in compose
