# scripts/adapters/base.py
from abc import ABC, abstractmethod
from scripts.core.models import Product, Provider
from scripts.core.validate import validate_product, ValidationError


class BaseAdapter(ABC):
    provider_id: str = ""
    provider_name: str = ""
    provider_name_en: str = ""
    region: str = ""
    website: str = ""
    pricing_url: str = ""

    @abstractmethod
    def fetch(self) -> list[Product]:
        """抓取并返回该厂商的所有 products。失败抛异常。"""
        raise NotImplementedError

    def validate(self, products: list[Product]) -> list[Product]:
        """通用校验。子类可覆盖加自检断言。"""
        for p in products:
            validate_product(p)
        return products

    def to_provider(self, products: list[Product]) -> Provider:
        return Provider(
            id=self.provider_id,
            name=self.provider_name,
            name_en=self.provider_name_en,
            region=self.region,
            website=self.website,
            pricing_url=self.pricing_url,
            products=products,
        )

    def assert_min_products(self, products: list[Product], minimum: int = 1):
        """适配器自检：抓到的产品数不能太少（防页面改版静默失效）。"""
        if len(products) < minimum:
            raise RuntimeError(
                f"{self.provider_id}: expected >={minimum} products, got {len(products)} "
                f"(page structure may have changed)"
            )
