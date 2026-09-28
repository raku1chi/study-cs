"""ドメイン層: ビジネスルールの中心。外側の層やインフラに依存してはいけない。"""
from .money import Money

__all__ = ["Money"]
