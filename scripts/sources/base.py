# scripts/sources/base.py
"""外部数据源基类。

设计要点：
- Source 只负责"采集 + 转换为 Product 列表"，不负责仲裁、不写盘。
- 每次返回的是 dict[provider_id, list[Product]]，便于 reconcile 按 provider 维度对齐。
- 单源失败应被 __init__.py 的 fetch_all_sources 捕获，不影响其他源。
"""
from abc import ABC, abstractmethod
from typing import Optional

from scripts.core.models import Product


class SourceResult:
    """单源采集结果。

    Attributes:
        source_id:     源标识，如 "litellm" / "openrouter"
        products:      {provider_id: [Product, ...]}
        error:         若整体失败，记录异常信息（不抛出）
        fetched_at:    ISO8601 时间戳
    """
    def __init__(self, source_id: str, products: dict = None,
                 error: Optional[str] = None, fetched_at: str = ""):
        self.source_id = source_id
        self.products = products or {}
        self.error = error
        self.fetched_at = fetched_at


class SourceBase(ABC):
    """外部数据源抽象基类。"""

    source_id: str = ""
    # 该源覆盖的 provider_id 列表（用于 reconcile 阶段判断"缺失"还是"未覆盖"）
    covers: list[str] = []

    @abstractmethod
    def fetch_all(self) -> dict[str, list[Product]]:
        """采集所有覆盖的厂商。

        Returns:
            {provider_id: [Product, ...]}
            若某 provider 采集失败，可省略该 key 或返回空 list。
        """
        raise NotImplementedError
