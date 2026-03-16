from typing import List, Dict

import httpx

from app.log import logger
from app.core.config import settings

from .framework.registry import command_registry, view_registry
from .framework.callbacks import Action
from .framework.handler import BaseActionHandler
from .session import Session
from ..core.config import configer
from ..core.message import post_message
from ..core.i18n import i18n
from ..service import servicer

command_registry.clear()


class ActionHandler(BaseActionHandler):
    """
    动作处理器
    处理用户的动作请求，并执行相应的业务逻辑
    """

    @command_registry.command(name="go_to", code="gt")
    def handle_go_to(self, session: Session, action: Action):
        """
        处理跳转到指定视图的操作
        """
        if action.view:
            if view_registry.get_by_name(action.view):
                session.go_to(action.view)
                if action.view == "search":
                    # 如果跳转到 start 视图，重置业务逻辑
                    session.business = session.business.__class__()
            else:
                raise ValueError(f"未知视图 '{action.view}'，跳转失败。")

    @command_registry.command(name="go_back", code="gb")
    def handle_go_back(self, session: Session, action: Action):
        """
        处理返回操作
        """
        if action.view:
            if view_registry.get_by_name(action.view):
                session.go_back(action.view)
                if action.view == "search":
                    # 如果返回到 start 视图，重置业务逻辑
                    session.business = session.business.__class__()
            else:
                logger.warning(f"未知视图 '{action.view}'，尝试返回失败。")
                raise ValueError(f"未知视图 '{action.view}'，返回失败。")

    @command_registry.command(name="page_next", code="pn")
    def handle_page_next(self, session: Session, _: Action):
        """
        处理下一页操作
        """
        session.page_next()

    @command_registry.command(name="page_prev", code="pp")
    def handle_page_prev(self, session: Session, _: Action):
        """
        处理上一页操作
        """
        session.page_prev()

    @command_registry.command(name="close", code="cl")
    def handle_closed(self, session: Session, _: Action):
        """
        处理关闭操作
        """
        session.view.name = "close"

    @command_registry.command(name="refresh", code="rf")
    def handle_refresh(self, session: Session, _: Action):
        """
        处理刷新操作
        """
        session.refresh_view()

    @command_registry.command(name="share_recieve_path", code="srp")
    def handle_share_recieve_path(self, session: Session, action: Action):
        """
        处理分享目录选择操作
        """
        session.business.share_recieve_path = None
        session.business.share_recieve_url = action.value

    @command_registry.command(name="share_recieve", code="dsr")
    def handle_share_recieve(self, session: Session, action: Action):
        """
        处理分享转存操作
        """
        try:
            if action.value is None:
                raise ValueError("value 不能为空。")
            # 索引号
            item_index = int(action.value)
            if 0 <= item_index < len(configer.share_recieve_paths):
                path = configer.share_recieve_paths[item_index]
                servicer.sharetransferhelper.add_share(
                    url=session.business.share_recieve_url,
                    channel=session.message.channel,
                    userid=session.message.userid,
                    pan_path=path,
                )
                session.view.name = "close"
            else:
                raise IndexError("索引超出范围。")
        except (ValueError, IndexError, TypeError) as e:
            logger.error(
                f"处理 share_recieve 失败: value={action.value}, error={e}",
                exc_info=True,
            )
            session.go_to("start")
            return [
                {"type": "error_message", "text": "处理分享转存时发生错误，请重试。"}
            ]
        return None

    @command_registry.command(name="offline_download_path", code="odp")
    def handle_offline_download_path(self, session: Session, action: Action):
        """
        处理离线下载目录选择操作
        """
        session.business.offline_download_path = None
        session.business.offline_download_url = action.value

    @command_registry.command(name="offline_download", code="dod")
    def handle_offline_download(self, session: Session, action: Action):
        """
        处理离线下载操作
        """
        try:
            if action.value is None:
                raise ValueError("value 不能为空。")
            # 索引号
            item_index = int(action.value)
            if 0 <= item_index < len(configer.offline_download_paths):
                path = configer.offline_download_paths[item_index]
                session.view.name = "close"
                # 选择目录为整理目录则进行网盘整理，否则只添加离线下载任务
                if (
                    path in configer.pan_transfer_paths
                    and configer.pan_transfer_enabled
                ):
                    status = servicer.offlinehelper.add_urls_to_transfer(
                        [session.business.offline_download_url]
                    )
                else:
                    status = servicer.offlinehelper.add_urls_to_path(
                        [session.business.offline_download_url], path
                    )
                if status:
                    post_message(
                        channel=session.message.channel,
                        title=i18n.translate("p115_add_offline_success"),
                        userid=session.message.userid,
                    )
                else:
                    post_message(
                        channel=session.message.channel,
                        title=i18n.translate("p115_add_offline_fail"),
                        userid=session.message.userid,
                    )
            else:
                raise IndexError("索引超出范围。")
        except (ValueError, IndexError, TypeError) as e:
            logger.error(
                f"处理 offline_download 失败: value={action.value}, error={e}",
                exc_info=True,
            )
            session.go_to("start")
            return [
                {"type": "error_message", "text": "处理离线下载时发生错误，请重试。"}
            ]
        return None

    @command_registry.command(name="search", code="sr")
    def handle_search(self, session: Session, action: Action):
        """
        处理搜索操作
        """
        if action.value is None:
            raise ValueError("搜索关键词不能为空。")
        search_keyword = action.value.strip()
        session.business.search_keyword = search_keyword

    @command_registry.command(name="resource", code="rs")
    def handle_resource(self, session: Session, action: Action):
        """
        处理资源操作
        """
        if action.value is None:
            raise ValueError("搜索关键词不能为空。")
        resource_key = action.value
        session.business.resource_key = resource_key
        if not configer.get_config("nullbr_app_id") or not configer.get_config(
            "nullbr_api_key"
        ):
            session.business.resource_key = 0
            session.business.resource_key_list = [
                {
                    "name": resource_key,
                }
            ]
        session.view.refresh = True
        session.go_to("resource_list")

    @command_registry.command(name="subscribe", code="sb")
    def handle_select_subscribe(
        self, session: Session, action: Action
    ) -> List[Dict] | None:
        """
        处理选中资源的操作
        """
        try:
            if action.value is None:
                raise ValueError("value 不能为空。")
            # 索引号
            item_index = int(action.value)
            # 全部搜索数据
            search_data = session.business.resource_info.get("data", [])

            if not search_data:
                raise ValueError("当前没有可用的资源。")
            if 0 <= item_index < len(search_data):
                data = search_data[item_index]
                resp = httpx.get(
                    f"{configer.get_config('moviepilot_address').rstrip('/')}/api/v1/plugin/P115StrmHelper/add_transfer_share?apikey={settings.API_TOKEN}&share_url={data.get('shareurl')}"
                )
                if resp.json().get("code") == 0:
                    session.go_to("subscribe_success")
                else:
                    session.go_to("subscribe_fail")
            else:
                raise IndexError("索引超出范围。")
        except (ValueError, IndexError, TypeError) as e:
            logger.error(
                f"处理 subscribe 失败: value={action.value}, error={e}", exc_info=True
            )
            session.go_to("start")
            return [{"type": "error_message", "text": "选择资源时发生错误，请重试。"}]
        return None
