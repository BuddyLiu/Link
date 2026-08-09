"""
LINK 外部信息源集成模块
提供天气、新闻、日历等外部信息查询能力（含无 API Key 时降级）
"""

from .integration import ExternalIntegration, create_external_integration

__all__ = ["ExternalIntegration", "create_external_integration"]
