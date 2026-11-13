"""Stateless PT execution adapter for DIAN115 and MoviePilot V2/V3."""

import base64
import inspect
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

try:
    from app.sdk.plugin import _PluginBase
    from app.application.site.sites import SitesHelper
    from app.domain.context import TorrentInfo
    from app.application.rss import RssHelper
except ModuleNotFoundError:
    from app.plugins import _PluginBase
    from app.helper.sites import SitesHelper
    from app.core.context import TorrentInfo
    from app.helper.rss import RssHelper

from app.chain.download import DownloadChain
from app.chain.site import SiteChain
from app.chain.torrents import TorrentsChain
from app.modules.indexer import IndexerModule, SPIDER_PARSER_CLASSES
from app.modules.indexer.spider import mtorrent as mp_mtorrent
from app.schemas.types import MediaType


class _BoundMTorrent(mp_mtorrent.MTorrentSpider):
    """Extend request parameters while retaining the installed MP parser/auth."""

    def search_bound(self, payload, mtype):
        if not self._apikey:
            raise HTTPException(409, "请先在 MoviePilot 配置 M-Team API Key")
        params = self._MTorrentSpider__get_params(
            payload.get("keyword") or "", mtype, payload.get("page", 0))
        category = payload.get("category") or ""
        if category:
            params["categories"] = [part.strip() for part in category.split(",") if part.strip()]
        mode = payload.get("mteam_mode") or ""
        if mode:
            params["mode"] = mode
            if mode == "adult" and not category:
                params["categories"] = []
        start, end = payload.get("published_after"), payload.get("published_before")
        if start or end:
            try:
                zone = timezone(timedelta(hours=8))
                bounds = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in (start, end)]
                if any(value.tzinfo is None for value in bounds) or bounds[0] >= bounds[1]:
                    raise ValueError()
                params.update(uploadDateStart=bounds[0].astimezone(zone).strftime("%Y-%m-%d %H:%M:%S"),
                              uploadDateEnd=bounds[1].astimezone(zone).strftime("%Y-%m-%d %H:%M:%S"),
                              sortField="CREATED_DATE", sortDirection="DESC")
            except (ValueError, AttributeError, TypeError):
                raise HTTPException(400, "M-Team 发布时间窗口无效") from None
        response = mp_mtorrent.RequestUtils(
            headers={"Content-Type": "application/json", "User-Agent": self._ua,
                     "x-api-key": self._apikey}, proxies=self._proxy,
            referer=str(self._url or "") + "browse", timeout=self._timeout,
        ).post_res(url=self._searchurl, json=params)
        if response is None or response.status_code != 200:
            raise HTTPException(502, "M-Team 搜索请求失败")
        result = response.json()
        if str(result.get("code")) != "0" or not isinstance(result.get("data"), dict):
            raise HTTPException(502, "M-Team 返回业务错误，请检查 MoviePilot 的站点认证")
        rows = result["data"].get("data")
        if not isinstance(rows, list):
            raise HTTPException(502, "M-Team 资源响应无效")
        return self._MTorrentSpider__parse_result(rows), len(rows)


class Dian115Bridge(_PluginBase):
    plugin_name = "DIAN115 PT 连接"
    plugin_desc = "提供站点搜索与取种；种子解析、筛选、下载及订阅由 DIAN115 管理。"
    plugin_icon = ""
    plugin_version = "1.1.0"
    plugin_author = "DIAN115"
    author_url = ""
    plugin_config_prefix = "dian115bridge_"
    plugin_order = 90
    auth_level = 1

    _limit = 5 * 1024 * 1024

    def init_plugin(self, config=None):
        self._enabled = bool((config or {}).get("enabled", False))

    def get_state(self):
        return getattr(self, "_enabled", False)

    def get_form(self):
        return [{
            "component": "VSwitch",
            "props": {"model": "enabled", "label": "启用 DIAN115 PT 连接"},
        }, {
            "component": "VAlert",
            "props": {"type": "info", "variant": "tonal", "text":
                      "使用 MoviePilot 自身 API 密钥认证。连接器不创建订阅、不轮询下载进度；"
                      "站点凭据保留在 MoviePilot，下载器由 DIAN115 直接连接。"},
        }], {"enabled": False}

    def get_page(self):
        return []

    @staticmethod
    def get_command():
        return []

    def stop_service(self):
        pass

    def get_api(self):
        return [{
            "path": "/" + name, "endpoint": getattr(self, name),
            "methods": ["POST"], "auth": "apikey",
            "summary": "DIAN115 PT " + name,
        } for name in ("capabilities", "search", "torrent", "rss", "rss_url", "userdata")]

    def _require_enabled(self):
        if not self.get_state():
            raise HTTPException(409, "DIAN115 PT 连接尚未启用")

    @staticmethod
    def _ok(data):
        return {"success": True, "data": data}

    def capabilities(self, payload: dict):
        self._require_enabled()
        return self._ok({"protocol": 1, "operations": [
            "search", "torrent", "rss", "rss_url", "userdata", "mteam_window",
        ]})

    def _site(self, payload):
        self._require_enabled()
        wanted = payload.get("site_id")
        if not isinstance(wanted, int) or isinstance(wanted, bool) or wanted <= 0:
            raise HTTPException(400, "站点编号无效")
        matches = [dict(site) for site in SitesHelper().get_indexers()
                   if site.get("id") == wanted and site.get("is_active", True)]
        if len(matches) != 1:
            raise HTTPException(409, "指定的 MoviePilot 站点不存在、停用或存在歧义")
        return matches[0]

    @staticmethod
    def _torrents(torrents):
        result = []
        for torrent in torrents or []:
            row = torrent.to_dict()
            for key in ("site_cookie", "site_ua", "site_proxy", "site_downloader"):
                row.pop(key, None)
            for key in ("pubdate", "freedate"):
                value = row.get(key)
                if value:
                    try:
                        row[key] = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().isoformat()
                    except ValueError:
                        pass
            # Enclosures may still contain tracker ticket recipes. DIAN115
            # seals the complete resource before caching or returning it.
            result.append(row)
        return result

    def search(self, payload: dict):
        site = self._site(payload)
        page = payload.get("page", 0)
        if not isinstance(page, int) or isinstance(page, bool) or page < 0 or page > 10000:
            raise HTTPException(400, "页码无效")
        mode = payload.get("mteam_mode") or ""
        if mode not in ("", "normal", "adult"):
            raise HTTPException(400, "M-Team 模式无效")
        mtype = {"movie": MediaType.MOVIE, "tv": MediaType.TV}.get(payload.get("media_type"))
        indexer = IndexerModule()
        started = time.monotonic()
        try:
            keyword = payload.get("keyword") or ""
            if not indexer._IndexerModule__search_check(site, keyword):
                raise HTTPException(409, "MoviePilot 站点限流或不支持当前关键词")
            keyword = indexer._IndexerModule__clear_search_text(keyword)
            parser = site.get("parser")
            if parser == "mTorrent":
                rows, raw_count = _BoundMTorrent(site).search_bound({**payload, "keyword": keyword}, mtype)
                failed = False
            else:
                if mode or payload.get("published_after") or payload.get("published_before"):
                    raise HTTPException(400, "该搜索参数仅支持 M-Team")
                spider_class = SPIDER_PARSER_CLASSES.get(parser)
                if spider_class:
                    spider = spider_class(site)
                    accepted = inspect.signature(spider.search).parameters
                    category = payload.get("category") or None
                    if category and "cat" not in accepted:
                        raise HTTPException(409, "当前 MoviePilot 解析器不支持显式分类，请升级解析器或清除该条件")
                    values = {"keyword": keyword, "mtype": mtype, "cat": category, "page": page}
                    failed, rows = spider.search(**{key: value for key, value in values.items() if key in accepted})
                else:
                    failed, rows = indexer._IndexerModule__spider_search(
                        indexer=site, search_word=keyword, mtype=mtype,
                        cat=payload.get("category") or None, page=page)
                raw_count = len(rows)
            indexer._IndexerModule__indexer_statistic(site, error_flag=failed, seconds=int(time.monotonic() - started))
            if failed:
                raise HTTPException(502, "MoviePilot 站点请求或解析失败，请检查该站连接")
            torrents = indexer._IndexerModule__parse_result(site, rows, int(time.monotonic() - started))
            size = indexer.get_search_page_size(site, keyword=keyword)
            return self._ok({"torrents": self._torrents(torrents), "page_size": size or 0, "raw_count": raw_count})
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, "MoviePilot 站点搜索失败") from None

    def torrent(self, payload: dict):
        site = self._site(payload)
        row = dict(payload.get("torrent") or {})
        if row.get("site") != site.get("id"):
            raise HTTPException(400, "资源与指定站点不一致")
        row.update(site_cookie=site.get("cookie"), site_ua=site.get("ua"),
                   site_proxy=site.get("proxy"), site_name=site.get("name"))
        try:
            torrent = TorrentInfo()
            torrent.from_dict(row)
            content, _, _ = DownloadChain().download_torrent(torrent)
            if isinstance(content, str):
                content = content.encode()
            if not content or len(content) > self._limit:
                raise HTTPException(502, "种子为空或超过连接器容量")
            return self._ok({"content": base64.b64encode(content).decode()})
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, "MoviePilot 取种失败") from None

    def rss_url(self, payload: dict):
        site = self._site(payload)
        try:
            url, error = RssHelper().get_rss_link(
                url=site.get("url") or site.get("domain"), cookie=site.get("cookie"),
                ua=site.get("ua"), proxy=bool(site.get("proxy")), timeout=site.get("timeout") or 30)
            if not url:
                raise HTTPException(502, "MoviePilot 未找到 RSS 地址，请手动配置")
            return self._ok({"url": url})
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, "MoviePilot RSS 自动发现失败") from None

    def rss(self, payload: dict):
        site = self._site(payload)
        if not site.get("rss"):
            raise HTTPException(409, "请先在 MoviePilot 配置该站 RSS 地址")
        try:
            torrents = TorrentsChain().rss(site["domain"])
            if not torrents:
                raise HTTPException(502, "MoviePilot RSS 未返回资源，请检查 RSS 地址")
            return self._ok({"torrents": self._torrents(torrents)})
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, "MoviePilot RSS 读取失败") from None

    def userdata(self, payload: dict):
        site = self._site(payload)
        try:
            stats = SiteChain().refresh_userdata(site)
            if stats is None:
                raise HTTPException(502, "MoviePilot 未返回账号统计")
            data = stats.model_dump()
            result = {key: value for key, value in data.items() if key in {
                "username", "user_level", "join_at", "bonus", "upload", "download",
                "ratio", "seeding", "leeching", "seeding_size", "leeching_size",
                "seeding_info", "message_unread", "message_unread_contents", "err_msg",
            }}
            result["tracker_user_id"] = str(data.get("userid") or "")
            return self._ok(result)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, "MoviePilot 账号统计读取失败") from None
