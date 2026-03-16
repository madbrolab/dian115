import math
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List

from app.schemas.message import ChannelCapabilityManager

from ..helper.tg_search import TgSearcher
from ..helper.nullbr import NullbrHelper
from .framework.callbacks import Action
from .framework.registry import view_registry
from .framework.views import BaseViewRenderer
from .session import Session
from ..utils.string import StringUtils
from ..core.config import configer

view_registry.clear()


class ViewRenderer(BaseViewRenderer):
    """
    视图渲染器
    """

    @staticmethod
    def __now_date() -> str:
        """
        返回当前时间的字符串表示。
        """
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def __get_paged_items_and_start_index(session: Session, page_size: int, data):
        """
        通用 - 获取当前页码的数据项。

        """
        session.view.total_pages = math.ceil(len(data) / page_size)

        if session.view.page >= session.view.total_pages > 0:
            session.view.page = session.view.total_pages - 1

        start_index = session.view.page * page_size
        paged_items = data[start_index : start_index + page_size]
        return paged_items, start_index

    @staticmethod
    def __get_page_size(session: Session) -> Tuple[int, int]:
        """
        通用 - 获取当前页面的大小，决定每页显示多少个下按钮。
        """
        max_buttons_per_row = ChannelCapabilityManager.get_max_buttons_per_row(
            session.message.channel
        )
        max_total_button_rows = ChannelCapabilityManager.get_max_button_rows(
            session.message.channel
        )

        # 决定本页要显示的下载器按钮行数
        if max_total_button_rows >= 4:
            button_rows = 2
        else:
            button_rows = 1

        page_size = button_rows * max_buttons_per_row
        return page_size, max_buttons_per_row

    def get_page_switch_buttons(self, session: Session) -> List[Dict[str, Any]]:
        """
        构建分页切换按钮。
        """
        page_nav = []
        if session.view.page > 0:
            page_nav.append(
                self._build_button(session, "◀️ 上一页", Action(command="page_prev"))
            )
        if session.view.page < session.view.total_pages - 1:
            page_nav.append(
                self._build_button(session, "▶️ 下一页", Action(command="page_next"))
            )
        return page_nav

    def get_navigation_buttons(
        self,
        session: Session,
        go_back: Optional[str] = None,
        refresh: bool = False,
        close: bool = False,
    ) -> list:
        """
        获取导航按钮，包含返回、刷新和关闭按钮。
        """
        nav_buttons = []
        if go_back:
            nav_buttons.append(self._build_common_go_back_button(session, view=go_back))
        if refresh:
            nav_buttons.append(self._build_common_refresh_button(session))
        if close:
            nav_buttons.append(self._build_common_close_button(session))
        return nav_buttons

    def get_search_data(self, session: Session):
        """
        获取搜索数据
        """
        nullbr_client = NullbrHelper()
        data = nullbr_client.get_media_list(session.business.search_keyword)
        session.business.search_info = {"data": data, "datatime": self.__now_date()}

    def get_resource_data(self, session: Session):
        """
        获取资源数据
        """
        resource_dict = session.business.resource_key_list[
            int(session.business.resource_key)
        ]

        nullbr_data = []
        if configer.get_config("nullbr_app_id") and configer.get_config(
            "nullbr_api_key"
        ):
            # Nullbr
            nullbr_client = NullbrHelper()
            nullbr_data = nullbr_client.search_resource(
                resource_dict.get("tmdb_id"),
                resource_dict.get("type"),
            )

        cs_data = []
        if configer.tg_search_channels:
            # TG Searcher
            searcher = TgSearcher()
            cs_data = searcher.search(
                key=resource_dict.get("name"), channels=configer.tg_search_channels
            )

        data = nullbr_data + cs_data

        # 记录到session，待渲染使用
        session.business.resource_info = {"data": data, "datatime": self.__now_date()}

    @view_registry.view(name="share_recieve_paths", code="srps")
    def render_share_recieve_paths(self, session: Session) -> Dict:
        """
        渲染分享目录选择器
        """
        title, buttons, text_lines = (
            "分享转存目录列表",
            [],
            ["请选择您要转存的目录：\n"],
        )

        # 获取频道能力，是否渲染按钮
        supports_buttons = ChannelCapabilityManager.supports_buttons(
            session.message.channel
        )
        # 最大行数，每行最大按钮数
        page_size, max_buttons_per_row = self.__get_page_size(session=session)
        # 当前页的数据，当前页的索引起点
        paged_items, start_index = self.__get_paged_items_and_start_index(
            session=session, page_size=page_size, data=configer.share_recieve_paths
        )

        button_row = []

        for i, path in enumerate(paged_items):
            original_index = configer.share_recieve_paths.index(path)

            text_lines.append(
                f"{StringUtils.to_emoji_number(start_index + i + 1)}. {path}"
            )

            # 支持按钮时，生成按钮
            if supports_buttons:
                button_row.append(
                    self._build_button(
                        session,
                        text=StringUtils.to_emoji_number(start_index + i + 1),
                        action=Action(command="share_recieve", value=original_index),
                    )
                )

                # 如果当前行已满，添加到按钮列表
                if len(button_row) == max_buttons_per_row:
                    buttons.append(button_row)
                    button_row = []

        if button_row:
            buttons.append(button_row)

        text_lines.append(
            f"\n页码: {session.view.page + 1} / {session.view.total_pages}"
        )
        text_lines.append(f"\n数据刷新时间：{self.__now_date()}")

        # 添加分页行
        if page_nav := self.get_page_switch_buttons(session):
            buttons.append(page_nav)

        text = "\n".join(text_lines)
        # 添加刷新与关闭行
        buttons.append(self.get_navigation_buttons(session, refresh=True, close=True))

        return {"title": title, "text": text, "buttons": buttons}

    @view_registry.view(name="offline_download_paths", code="odps")
    def render_offline_download_paths(self, session: Session) -> Dict:
        """
        渲染离线下载目录选择器
        """
        title, buttons, text_lines = (
            "离线下载目录列表",
            [],
            ["请选择您要下载到的目录：\n"],
        )

        # 获取频道能力，是否渲染按钮
        supports_buttons = ChannelCapabilityManager.supports_buttons(
            session.message.channel
        )
        # 最大行数，每行最大按钮数
        page_size, max_buttons_per_row = self.__get_page_size(session=session)
        # 当前页的数据，当前页的索引起点
        paged_items, start_index = self.__get_paged_items_and_start_index(
            session=session, page_size=page_size, data=configer.offline_download_paths
        )

        button_row = []

        for i, path in enumerate(paged_items):
            original_index = configer.offline_download_paths.index(path)

            text_lines.append(
                f"{StringUtils.to_emoji_number(start_index + i + 1)}. {path}"
            )

            # 支持按钮时，生成按钮
            if supports_buttons:
                button_row.append(
                    self._build_button(
                        session,
                        text=StringUtils.to_emoji_number(start_index + i + 1),
                        action=Action(command="offline_download", value=original_index),
                    )
                )

                # 如果当前行已满，添加到按钮列表
                if len(button_row) == max_buttons_per_row:
                    buttons.append(button_row)
                    button_row = []

        if button_row:
            buttons.append(button_row)

        text_lines.append(
            f"\n页码: {session.view.page + 1} / {session.view.total_pages}"
        )
        text_lines.append(f"\n数据刷新时间：{self.__now_date()}")

        # 添加分页行
        if page_nav := self.get_page_switch_buttons(session):
            buttons.append(page_nav)

        text = "\n".join(text_lines)
        # 添加刷新与关闭行
        buttons.append(self.get_navigation_buttons(session, refresh=True, close=True))

        return {"title": title, "text": text, "buttons": buttons}

    @view_registry.view(name="search_list", code="shl")
    def render_search_list(self, session: Session) -> Dict:
        """
        渲染搜索
        """
        title, buttons, text_lines = "搜索列表", [], ["请选择具体资源类型：\n"]

        if not session.business.search_info or session.view.refresh:
            self.get_search_data(session=session)
            session.view.refresh = False

        if not (search_info := session.business.search_info):
            text = "当前没有搜索结果。"
            buttons.append(
                self.get_navigation_buttons(session, refresh=True, close=True)
            )
            return {"title": title, "text": text, "buttons": buttons}

        else:
            search_data = search_info.get("data", [])
            # 获取频道能力，是否渲染按钮
            supports_buttons = ChannelCapabilityManager.supports_buttons(
                session.message.channel
            )
            # 最大行数，每行最大按钮数
            page_size, max_buttons_per_row = self.__get_page_size(session=session)
            # 当前页的数据，当前页的索引起点
            paged_items, start_index = self.__get_paged_items_and_start_index(
                session=session, page_size=page_size, data=search_data
            )

            button_row = []
            session.business.resource_key_list = []
            for i, data in enumerate(paged_items):
                d_title = (
                    StringUtils.replace_markdown_with_space(text=data.title)
                    if data.title
                    else "未知资源名"
                )

                text_lines.append(
                    f"{StringUtils.to_emoji_number(start_index + i + 1)}. {d_title} ({StringUtils.media_type_i18n(data.media_type)})"
                )

                # 支持按钮时，生成按钮
                if supports_buttons:
                    button_row.append(
                        self._build_button(
                            session,
                            text=StringUtils.to_emoji_number(start_index + i + 1),
                            action=Action(
                                command="resource",
                                view="resource_list",
                                value=i,
                            ),
                        )
                    )

                    session.business.resource_key_list.append(
                        {
                            "type": data.media_type,
                            "tmdb_id": data.tmdbid,
                            "name": data.title,
                        }
                    )

                    # 如果当前行已满，添加到按钮列表
                    if len(button_row) == max_buttons_per_row:
                        buttons.append(button_row)
                        button_row = []

            if button_row:
                buttons.append(button_row)

            text_lines.append(
                f"\n页码: {session.view.page + 1} / {session.view.total_pages}"
            )
            text_lines.append(
                f"\n数据刷新时间：{session.business.search_info.get('datatime', self.__now_date())}"
            )

            # 添加分页行
            if page_nav := self.get_page_switch_buttons(session):
                buttons.append(page_nav)

        text = "\n".join(text_lines)
        # 添加刷新与关闭行
        buttons.append(self.get_navigation_buttons(session, refresh=True, close=True))

        return {"title": title, "text": text, "buttons": buttons}

    @view_registry.view(name="resource_list", code="rsl")
    def render_resource_list(self, session: Session) -> Dict:
        """
        渲染资源
        """
        title, buttons, text_lines = "资源列表", [], ["请选择转存的资源：\n"]

        if not session.business.resource_info or session.view.refresh:
            self.get_resource_data(session=session)
            session.view.refresh = False

        if not (resource_info := session.business.resource_info):
            text = "当前没有搜索结果。"
            buttons.append(
                self.get_navigation_buttons(session, refresh=True, close=True)
            )
            return {"title": title, "text": text, "buttons": buttons}

        else:
            resource_data = resource_info.get("data", [])
            # 获取频道能力，是否渲染按钮
            supports_buttons = ChannelCapabilityManager.supports_buttons(
                session.message.channel
            )
            # 最大行数，每行最大按钮数
            page_size, max_buttons_per_row = self.__get_page_size(session=session)
            # 当前页的数据，当前页的索引起点
            paged_items, start_index = self.__get_paged_items_and_start_index(
                session=session, page_size=page_size, data=resource_data
            )

            button_row = []
            for i, data in enumerate(paged_items):
                original_index = resource_data.index(data)
                text_lines.append(
                    f"{StringUtils.to_emoji_number(start_index + i + 1)}. {data.get('taskname', '未知名称')}"
                )

                # 支持按钮时，生成按钮
                if supports_buttons:
                    button_row.append(
                        self._build_button(
                            session,
                            text=StringUtils.to_emoji_number(start_index + i + 1),
                            action=Action(command="subscribe", value=original_index),
                        )
                    )

                    # 如果当前行已满，添加到按钮列表
                    if len(button_row) == max_buttons_per_row:
                        buttons.append(button_row)
                        button_row = []

            if button_row:
                buttons.append(button_row)

            text_lines.append(
                f"\n页码: {session.view.page + 1} / {session.view.total_pages}"
            )
            text_lines.append(
                f"\n数据刷新时间：{session.business.resource_info.get('datatime', self.__now_date())}"
            )

            # 添加分页行
            if page_nav := self.get_page_switch_buttons(session):
                buttons.append(page_nav)

        text = "\n".join(text_lines)
        # 添加刷新与关闭行
        if configer.get_config("nullbr_app_id") and configer.get_config(
            "nullbr_api_key"
        ):
            buttons.append(
                self.get_navigation_buttons(
                    session, go_back="search_list", refresh=True, close=True
                )
            )
        else:
            buttons.append(
                self.get_navigation_buttons(session, refresh=True, close=True)
            )

        return {"title": title, "text": text, "buttons": buttons}

    @view_registry.view(name="subscribe_success", code="ss")
    def render_subscribe_success(self, _: Session) -> Dict:
        """
        渲染转存成功视图。
        """
        title = "✅ 转存成功"
        text = "您的转存请求已成功处理。"
        buttons = []
        return {"title": title, "text": text, "buttons": buttons}

    @view_registry.view(name="subscribe_fail", code="sf")
    def render_subscribe_fail(self, session: Session) -> Dict:
        """
        渲染转存失败视图。
        """
        title = "❌ 转存失败"
        text = "您的转存请求处理失败，请稍后重试。"
        buttons = [
            self.get_navigation_buttons(session, go_back="resource_list", close=True)
        ]
        return {"title": title, "text": text, "buttons": buttons}

    @view_registry.view(name="close", code="cl")
    def render_close(self, session: Session) -> Dict:
        """
        渲染转存失败视图。
        """
        title = "❌ 关闭页面"
        text = ""
        buttons = []
        return {"title": title, "text": text, "buttons": buttons}
