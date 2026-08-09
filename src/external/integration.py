"""
外部信息源集成模块

提供天气、新闻、日历查询能力，全部带超时 + 无 API Key 时自动降级：
- 天气：优先 OpenWeatherMap（需 key），降级 wttr.in（免费，无需 key）
- 新闻：优先 NewsAPI（需 key），降级 RSS 源解析（无需 key）
- 日历：Google Calendar（需凭据），未配置时返回清晰提示
"""

from typing import Dict, Any, Optional, List
import json
import time
from datetime import datetime


class ExternalIntegration:
    """外部信息源集成器"""

    def __init__(self, config: Dict[str, Any] = None, logger=None):
        self.logger = logger
        self.config = config or {}
        self._timeout = self.config.get("timeout", 8)

        # API keys（来自 settings 或环境变量）
        self.openweather_api_key = (
            self.config.get("openweathermap_api_key")
            or self._env("OPENWEATHERMAP_API_KEY")
        )
        self.newsapi_key = (
            self.config.get("newsapi_api_key")
            or self._env("NEWSAPI_API_KEY")
        )

    def _env(self, name: str) -> Optional[str]:
        import os
        return os.getenv(name)

    def _log(self, level: str, msg: str):
        if self.logger:
            getattr(self.logger, level, print)(msg)

    # ── 天气 ──

    def get_weather(self, city: str = None) -> Dict[str, Any]:
        """查询天气。优先 OpenWeatherMap，失败/无 key 降级 wttr.in。

        Returns:
            {"success": bool, "text": str, "source": str, ...}
        """
        city = city or self.config.get("default_city", "北京")
        if self.openweather_api_key:
            try:
                return self._weather_openweather(city)
            except Exception as e:
                self._log("warning", f"OpenWeatherMap 查询失败，降级 wttr.in: {e}")
        return self._weather_wttr(city)

    def _weather_openweather(self, city: str) -> Dict[str, Any]:
        import urllib.request, urllib.parse
        params = urllib.parse.urlencode({
            "q": city, "appid": self.openweather_api_key, "units": "metric", "lang": "zh_cn",
        })
        url = f"https://api.openweathermap.org/data/2.5/weather?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "LINK/1.0"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        main = data.get("main", {})
        weather = (data.get("weather") or [{}])[0]
        temp = main.get("temp")
        desc = weather.get("description", "未知")
        feels = main.get("feels_like")
        humidity = main.get("humidity")
        wind = (data.get("wind") or {}).get("speed")
        text = (f"🌤️ {city}当前天气：{desc}，{temp}°C"
                f"（体感{feels}°C），湿度{humidity}%，风速{wind}m/s。")
        return {"success": True, "text": text, "source": "openweathermap",
                "city": city, "temp": temp, "desc": desc}

    def _weather_wttr(self, city: str) -> Dict[str, Any]:
        import urllib.request, urllib.parse
        q = urllib.parse.quote(city)
        # wttr.in 支持中文城市名（用 format=j1 JSON）
        url = f"https://wttr.in/{q}?format=j1&lang=zh"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        current = (data.get("current_condition") or [{}])[0]
        temp = current.get("temp_C")
        desc = (current.get("lang_zh") or [{}])[0].get("value") or \
            (current.get("weatherDesc") or [{}])[0].get("value", "未知")
        humidity = current.get("humidity")
        wind = current.get("windspeedKmph")
        text = (f"🌤️ {city}当前天气：{desc}，{temp}°C，"
                f"湿度{humidity}%，风速{wind}km/h。")
        return {"success": True, "text": text, "source": "wttr.in",
                "city": city, "temp": temp, "desc": desc}

    # ── 新闻 ──

    def get_news(self, topic: str = None, limit: int = 5) -> Dict[str, Any]:
        """获取新闻。优先 NewsAPI，降级 RSS 解析。

        Returns:
            {"success": bool, "text": str, "source": str, "items": [...]}
        """
        topic = (topic or "").strip() or "综合"
        if self.newsapi_key:
            try:
                return self._news_newsapi(topic, limit)
            except Exception as e:
                self._log("warning", f"NewsAPI 查询失败，降级 RSS: {e}")
        return self._news_rss(topic, limit)

    def _news_newsapi(self, topic: str, limit: int) -> Dict[str, Any]:
        import urllib.request, urllib.parse
        params = urllib.parse.urlencode({
            "q": topic or "中国", "apiKey": self.newsapi_key,
            "pageSize": limit, "language": "zh",
        })
        url = f"https://newsapi.org/v2/everything?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "LINK/1.0"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        articles = data.get("articles") or []
        items = []
        for a in articles[:limit]:
            title = a.get("title", "")
            source = (a.get("source") or {}).get("name", "")
            if title:
                items.append({"title": title, "source": source})
        text = self._format_news(items, topic or "综合")
        return {"success": bool(items), "text": text, "source": "newsapi", "items": items}

    def _news_rss(self, topic: str, limit: int) -> Dict[str, Any]:
        """RSS 新闻源（无需 key），使用国内稳定可达的源"""
        import urllib.request, urllib.parse

        # 稳定中文 RSS 源（按优先级）
        sources = [
            ("ithome", "https://www.ithome.com/rss/", "IT之家"),
            ("36kr", "https://36kr.com/feed", "36氪"),
            ("sspai", "https://sspai.com/feed", "少数派"),
        ]

        last_err = None
        for name, url, label in sources:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                return self._parse_rss_titles(body, limit, name, label, topic)
            except Exception as e:
                last_err = e
                continue
        self._log("warning", f"所有新闻源均失败: {last_err}")
        return {"success": False, "text": "📰 新闻服务暂不可用（网络受限）。", "items": []}

    def _parse_rss_titles(self, xml: str, limit: int, source_name: str,
                          source_label: str, topic: str) -> Dict[str, Any]:
        import re
        titles = re.findall(r"<title>(.*?)</title>", xml, re.S)
        items = []
        # 跳过第 0 个（频道名）
        for t in titles[1:]:
            t = t.strip()
            if not t:
                continue
            # 有些源标题带频道前缀，去掉
            t = re.sub(r'^[^]]*?\s*[-|]\s*', '', t).strip()
            if len(t) <= 4:
                continue
            # 有具体 topic 时优先匹配包含该词的标题；普通源直接取前 limit 条
            if topic and topic not in ("综合",) and topic not in t:
                continue
            items.append({"title": t, "source": source_label})
            if len(items) >= limit:
                break
        text = self._format_news(items, topic)
        return {"success": bool(items), "text": text,
                "source": f"{source_name}_rss", "items": items}

    def _format_news(self, items: List[dict], topic: str) -> str:
        if not items:
            return f"📰 暂时没有找到关于「{topic}」的新闻。"
        lines = [f"📰 关于「{topic}」的最新新闻："]
        for i, it in enumerate(items[:5], 1):
            src = f"（{it['source']}）" if it.get("source") else ""
            lines.append(f"{i}. {it['title'][:80]}{src}")
        return "\n".join(lines)

    # ── 日历 ──

    def get_calendar_events(self, days: int = 7) -> Dict[str, Any]:
        """查询日历事件（Google Calendar）。

        Returns:
            {"success": bool, "text": str, "configured": bool, "items": [...]}
        """
        credentials_path = (
            self.config.get("google_calendar_credentials")
            or self._env("GOOGLE_CALENDAR_CREDENTIALS")
        )
        if not credentials_path:
            return {
                "success": False,
                "configured": False,
                "text": "📅 日历服务未配置（需要 Google Calendar 凭据）。"
                        "设置 GOOGLE_CALENDAR_CREDENTIALS 环境变量后可用。",
                "items": [],
            }
        try:
            return self._calendar_google(credentials_path, days)
        except Exception as e:
            return {"success": False, "configured": True,
                    "text": f"📅 日历查询失败: {e}", "items": []}

    def _calendar_google(self, credentials_path: str, days: int) -> Dict[str, Any]:
        # 可选依赖：google-api-python-client 未安装时给出提示
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            return {"success": False, "configured": True,
                    "text": "📅 需要安装 google-api-python-client 才能查询日历。",
                    "items": []}
        creds = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        service = build("calendar", "v3", credentials=creds)
        now = datetime.utcnow().isoformat() + "Z"
        later = datetime.utcnow().timestamp() + days * 86400
        end = datetime.utcfromtimestamp(later).isoformat() + "Z"
        events_result = service.events().list(
            calendarId="primary", timeMin=now, timeMax=end,
            maxResults=10, singleEvents=True, orderBy="startTime",
        ).execute()
        items = []
        for e in events_result.get("items", []):
            start = (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date", "")
            items.append({"title": e.get("summary", ""), "start": start[:16]})
        if not items:
            return {"success": True, "configured": True,
                    "text": f"📅 未来 {days} 天暂无日程安排。", "items": []}
        lines = [f"📅 未来 {days} 天的日程："]
        for i, it in enumerate(items, 1):
            lines.append(f"{i}. {it['start']} {it['title']}")
        return {"success": True, "configured": True, "text": "\n".join(lines), "items": items}

    # ── 统一查询 ──

    def query(self, intent: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """按意图统一查询外部信息"""
        params = params or {}
        if intent == "weather":
            return self.get_weather(params.get("city"))
        if intent == "news":
            return self.get_news(params.get("topic"), params.get("limit", 5))
        if intent == "calendar":
            return self.get_calendar_events(params.get("days", 7))
        return {"success": False, "text": f"未知查询类型: {intent}"}


def create_external_integration(config: Dict[str, Any] = None, logger=None) -> ExternalIntegration:
    """创建外部信息源集成器"""
    return ExternalIntegration(config or {}, logger=logger)
