import re
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from app.log import logger
from app.core.config import settings
from app.utils.http import AsyncRequestUtils

from ...core.config import configer
from ...schemas.tg_search import ResourceItem
from ...utils.string import StringUtils
from ...utils.sentry import sentry_manager


@sentry_manager.capture_all_class_exceptions
class TgSearcher:
    """
    Telegream 搜索器

    模块思路参考：
      - https://github.com/JieWSOFT/MediaHelp/blob/main/backend/utils/tg_resource_sdk.py
        - LICENSE: https://github.com/JieWSOFT/MediaHelp/blob/main/LICENSE
      - https://github.com/Cp0204/quark-auto-save/blob/main/app/sdk/cloudsaver.py
        - LICENSE: https://github.com/Cp0204/quark-auto-save/blob/main/LICENSE
    """

    def __init__(self):
        proxies = (
            AsyncRequestUtils._convert_proxies_for_httpx(settings.PROXY)
            if settings.PROXY
            else None
        )
        self.session = httpx.Client(
            headers={"User-Agent": configer.get_user_agent(utype=1)},
            proxy=proxies,
            follow_redirects=True,
        )

    @staticmethod
    def extract_cloud_links(text: str) -> tuple[List[str], str]:
        """
        提取云盘链接
        """
        links: List[str] = []
        cloud_type = ""

        cloud_patterns = {
            "u115": r"(https?://(?:[a-zA-Z0-9-]+\.)*115[^/\s#]*\.[a-zA-Z]{2,}[^\s#]*)",
            "aliyun": r"(https?://(?:[a-zA-Z0-9-]+\.)?(?:alipan|aliyundrive)\.[a-zA-Z]{2,}[^\s#]*)",
        }

        for cloud_name, pattern in cloud_patterns.items():
            try:
                matches = re.findall(pattern, text)
                if matches:
                    links.extend(matches)
                    if not cloud_type:
                        cloud_type = cloud_name
            except Exception as e:
                logger.warn(f"【TGSearch】匹配 {cloud_name} 云盘链接时出错: {str(e)}")
                continue

        unique_links = list(set(links))
        return unique_links, cloud_type

    @staticmethod
    def _find_telegra_link_from_button(message_element) -> Optional[str]:
        """
        从消息的按钮中查找 telegra.ph 链接
        """
        try:
            button = message_element.select_one(
                ".tgme_widget_message_inline_button.url_button"
            )
            if button:
                href = button.get("href")
                if href and "telegra.ph" in href:
                    return href
        except Exception as e:
            logger.debug(f"【TGSearch】查找按钮链接时出错: {str(e)}")
        return None

    def _extract_links_from_telegra(self, telegra_url: str) -> tuple[List[str], str]:
        """
        从 telegra.ph 页面中提取115分享地址
        """
        try:
            response = self.session.get(telegra_url, timeout=30)
            response.raise_for_status()
            html = response.text

            cloud_links, cloud_type = self.extract_cloud_links(html)

            if cloud_links:
                logger.debug(
                    f"【TGSearch】从 telegra.ph 页面提取到 {len(cloud_links)} 个云盘链接"
                )

            return cloud_links, cloud_type
        except httpx.RequestError as e:
            logger.warning(
                f"【TGSearch】访问 telegra.ph 链接失败: {telegra_url}, 错误: {e}"
            )
            return [], ""
        except Exception as e:
            logger.warning(
                f"【TGSearch】解析 telegra.ph 页面时出错: {telegra_url}, 错误: {e}"
            )
            return [], ""

    def get_channel(self, url: str, channel_id: str) -> List[ResourceItem]:
        """
        搜索单个频道资源
        """
        try:
            response = self.session.get(url, timeout=60)
            response.raise_for_status()
            html = response.text
        except httpx.RequestError as e:
            logger.warn(f"【TGSearch】请求失败: {url}, 错误: {e}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        items: List[ResourceItem] = []

        for message in soup.select(".tgme_widget_message_wrap"):
            message_element = message.select_one(".tgme_widget_message")
            message_id = (
                message_element.get("data-post", "").split("/")[1]
                if message_element
                else None
            )

            text_element = message.select_one(".js-message_text")
            title = ""
            content = ""
            if not text_element:
                continue

            html_content = str(text_element)
            title_match = re.split("<br.*?>", html_content, 1)
            title = BeautifulSoup(title_match[0], "html.parser").get_text(
                " ", strip=True
            )

            if len(title_match) > 1:
                content_html = title_match[1]
                content = BeautifulSoup(content_html, "html.parser").get_text(
                    "\n", strip=True
                )

            time_element = message.select_one("time")
            pub_date = str(time_element.get("datetime")) if time_element else None

            photo_wrap = message.select_one(".tgme_widget_message_photo_wrap")
            image = None
            if photo_wrap and (style := photo_wrap.get("style")):
                if image_match := re.search(r"url\('(.+?)'\)", style):
                    image = image_match.group(1)

            tags: List[str] = []
            found_hrefs: List[str] = []
            for a in text_element.select("a"):
                href = a.get("href")
                text = a.get_text(strip=True)

                if href:
                    found_hrefs.append(href)

                if text and text.startswith("#"):
                    clean_tag = text.lstrip("#")
                    if clean_tag:
                        tags.append(clean_tag)

            all_links_text = " ".join(found_hrefs)
            cloud_links, cloud_type = self.extract_cloud_links(all_links_text)

            if not cloud_links:
                telegra_link = self._find_telegra_link_from_button(message)
                if telegra_link:
                    cloud_links, cloud_type = self._extract_links_from_telegra(
                        telegra_link
                    )

            if not cloud_links:
                continue

            item: ResourceItem = {
                "message_id": message_id,
                "title": title,
                "pub_date": pub_date,
                "content": content,
                "image": image,
                "cloud_links": cloud_links,
                "tags": tags,
                "cloud_type": cloud_type,
                "channel_id": channel_id,
            }
            items.append(item)

        return items

    def search(self, key: str, channels: List) -> List[dict]:
        """
        搜索资源
        """
        results: List[ResourceItem] = []
        for item in channels:
            channel_id = item.get("id")
            if not channel_id:
                continue
            url = StringUtils.encode_url_fully(f"https://t.me/s/{channel_id}?q={key}")
            results.extend(self.get_channel(url, channel_id))

        seen_links = set()
        clean_results = []

        pattern_title = r"(名称|标题)\s*[：:]\s*(.*)"
        pattern_content = r"(描述|简介)\s*[：:]\s*(.*)"

        for item in results:
            if not item.get("cloud_links"):
                continue

            main_link = None
            for link in item["cloud_links"]:
                if "115" in link:
                    main_link = link
            if not main_link:
                continue
            if main_link in seen_links:
                continue

            seen_links.add(main_link)

            title = item.get("title", "")
            if match := re.search(pattern_title, title, re.DOTALL):
                title = match.group(2)
            title = title.replace("&amp;", "&").strip()

            content = item.get("content", "")
            if "\n" in content:
                content_lines = []
                in_description = False
                for line in content.split("\n"):
                    if re.match(pattern_content, line):
                        in_description = True
                        content_lines.append(
                            re.sub(pattern_content, r"\2", line).strip()
                        )
                        continue
                    if re.match(r"(链接|标签)\s*[：:]", line):
                        in_description = False

                    if in_description:
                        content_lines.append(line.strip())

                if content_lines:
                    content = "\n".join(content_lines)

            clean_results.append(
                {
                    "shareurl": main_link,
                    "taskname": title,
                    "content": content.strip(),
                    "tags": item.get("tags", []),
                    "channel_id": item.get("channel_id", ""),
                }
            )

        logger.debug(f"【TGSearch】{key} 搜索到资源 {len(clean_results)} 条")

        return clean_results
