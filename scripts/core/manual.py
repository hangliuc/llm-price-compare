# scripts/core/manual.py
import os
from pathlib import Path
import yaml


def load_manual_providers(dir_path: str) -> list:
    """加载目录下所有 *.yaml 文件，返回 provider dict 列表。"""
    providers = []
    p = Path(dir_path)
    if not p.exists():
        return providers

    for f in sorted(p.glob("*.yaml")):
        with open(f, "r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
        if data and isinstance(data, dict) and "id" in data:
            providers.append(data)

    return providers
