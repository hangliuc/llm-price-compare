# scripts/adapters/__init__.py
from scripts.adapters.base import BaseAdapter
from scripts.adapters.openai import OpenAIAdapter
from scripts.adapters.anthropic import AnthropicAdapter
from scripts.adapters.deepseek import DeepSeekAdapter
from scripts.adapters.opencode import OpenCodeAdapter
from scripts.adapters.zhipu import ZhipuAdapter
from scripts.adapters.volcengine import VolcengineAdapter

ADAPTERS: list[BaseAdapter] = [
    OpenAIAdapter(),
    AnthropicAdapter(),
    DeepSeekAdapter(),
    OpenCodeAdapter(),
    ZhipuAdapter(),
    VolcengineAdapter(),
]
