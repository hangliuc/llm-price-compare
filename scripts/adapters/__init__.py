# scripts/adapters/__init__.py
from scripts.adapters.base import BaseAdapter
from scripts.adapters.openai import OpenAIAdapter
from scripts.adapters.anthropic import AnthropicAdapter
from scripts.adapters.deepseek import DeepSeekAdapter

# OpenCode / 智谱 / 火山引擎 改为 manual yaml 维护（页面结构不稳定或需登录），不再注册适配器
ADAPTERS: list[BaseAdapter] = [
    OpenAIAdapter(),
    AnthropicAdapter(),
    DeepSeekAdapter(),
]
