# scripts/sources/spike_litellm.py
"""Spike: 实测 LiteLLM model_prices_and_context_window.json 对项目 12 家厂商的覆盖率。

用法：
    python3 scripts/sources/spike_litellm.py
"""
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

_LITELLM_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

# 项目 12 家厂商 -> LiteLLM litellm_provider 字段的候选映射
# LiteLLM 的 litellm_provider 字段值需人工对照，先列候选，跑一次后再修正
_PROVIDER_MAP = {
    "openai": ["openai"],
    "anthropic": ["anthropic"],
    "google": ["vertex_ai-language-models", "vertex_ai-vision-models", "gemini", "vertex_ai"],
    "aws": ["bedrock", "sagemaker", "amazon"],
    "deepseek": ["deepseek"],
    "moonshot": ["moonshot"],
    "qwen": ["dashscope", "qwen", "alibaba"],
    "opencode": [],  # 待人工确认
    "volcengine": ["volcengine", "doubao", "ark"],
    "zhipu": ["zhipu", "glm"],
    "minimax": ["minimax"],
    "xiaomi": ["xiaomi", "mimo"],
}


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    print(f"Fetching {_LITELLM_URL} ...")
    data = fetch_json(_LITELLM_URL)

    # LiteLLM JSON 顶层有 "sample_spec" 等元字段，模型条目是 dict 且含 litellm_provider
    model_entries = {
        k: v for k, v in data.items()
        if isinstance(v, dict) and "litellm_provider" in v
    }
    print(f"总模型条目数: {len(model_entries)}\n")

    # 按 litellm_provider 分组
    by_provider = defaultdict(list)
    for model_id, entry in model_entries.items():
        p = entry.get("litellm_provider", "unknown")
        by_provider[p].append(model_id)

    print("=== LiteLLM 所有 litellm_provider 值（按模型数排序）===")
    for p, models in sorted(by_provider.items(), key=lambda x: -len(x[1])):
        print(f"  {p:50s} {len(models):4d} models")
    print()

    print("=== 项目 12 家厂商覆盖率 ===")
    total_covered = 0
    for pid, candidates in _PROVIDER_MAP.items():
        matched = []
        for c in candidates:
            if c in by_provider:
                matched.append((c, len(by_provider[c])))
        if matched:
            total_covered += 1
            counts = ", ".join(f"{c}={n}" for c, n in matched)
            print(f"  {pid:12s} ✅  {counts}")
            # 打印前 3 个模型示例
            for c, _ in matched[:1]:
                samples = by_provider[c][:3]
                print(f"               示例: {samples}")
        else:
            print(f"  {pid:12s} ❌  无候选或未匹配")

    print(f"\n覆盖率: {total_covered}/12 = {total_covered/12*100:.0f}%")

    # 检查 per_token 价格字段完整性
    print("\n=== per_token 价格字段完整性（仅检查前 5 个模型）===")
    for pid, candidates in _PROVIDER_MAP.items():
        if not candidates:
            continue
        for c in candidates:
            if c not in by_provider:
                continue
            for model_id in by_provider[c][:2]:
                entry = model_entries[model_id]
                prices = {
                    "input_cost_per_token": entry.get("input_cost_per_token"),
                    "output_cost_per_token": entry.get("output_cost_per_token"),
                    "cache_read_input_token_cost": entry.get("cache_read_input_token_cost"),
                    "max_tokens": entry.get("max_tokens"),
                    "max_input_tokens": entry.get("max_input_tokens"),
                }
                print(f"  {pid:10s} {model_id:50s} {prices}")
            break  # 每个 provider 只看前 2 个

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
