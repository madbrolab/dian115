from re import match as re_match
from time import sleep
from copy import deepcopy
from dataclasses import asdict
from functools import wraps
from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional, Union

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import TransferInfo, FileItem
from app.schemas.types import EventType, MessageChannel
from apscheduler.triggers.cron import CronTrigger
from fastapi import Request

from .version import VERSION
from .api import Api
from .service import servicer
from .core.cache import pantransfercacher, lifeeventcacher
from .core.config import configer
from .core.i18n import i18n
from .core.message import post_message
from .db_manager import ct_db_manager
from .db_manager.init import init_db, migration_db, init_migration_scripts
from .db_manager.oper import FileDbHelper
from .mcp import MCPManager
from .patch.u115_open import U115Patcher
from .patch.p115disk_upload import P115DiskPatcher
from .interactive.framework.callbacks import decode_action, Action
from .interactive.framework.manager import BaseSessionManager
from .interactive.framework.schemas import TSession
from .interactive.handler import ActionHandler
from .interactive.session import Session
from .interactive.views import ViewRenderer
from .helper.strm import FullSyncStrmHelper, TransferStrmHelper
from .helper.share import U115_SHARE_URL_MATCH, ALIYUN_SHARE_URL_MATCH
from .helper.mediasyncdel import MediaSyncDelHelper
from .utils.path import PathUtils
from .utils.sentry import sentry_manager
from .utils.strm import StrmGenerater


# 实例化一个该插件专用的 SessionManager
session_manager = BaseSessionManager(session_class=Session)


@sentry_manager.capture_all_class_exceptions
class P115StrmHelper(_PluginBase):
    # 插件名称
    plugin_name = "115网盘STRM助手"
    # 插件描述
    plugin_desc = "115网盘STRM生成一条龙服务"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Frontend/refs/heads/v2/src/assets/images/misc/u115.png"
    # 插件版本
    plugin_version = VERSION
    # 插件作者
    plugin_author = "DDSRem"
    # 作者主页
    author_url = "https://github.com/DDSRem"
    # 插件配置项ID前缀
    plugin_config_prefix = "p115strmhelper_"
    # 加载顺序
    plugin_order = 99
    # 可使用的用户级别
    auth_level = 1

    api = None
    mcp_manager = None

    @staticmethod
    def logs_oper(oper_name: str):
        """
        数据库操作汇报装饰器
        - 捕获异常并记录日志
        - 5秒内合并多条消息，避免频繁发送通知
        """

        def decorator(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                level, text = "success", f"{oper_name} 成功"
                try:
                    result = func(self, *args, **kwargs)
                    return result
                except Exception as e:
                    logger.error(f"{oper_name} 失败：{str(e)}", exc_info=True)
                    level, text = "error", f"{oper_name} 失败：{str(e)}"
                    return False
                finally:
                    if hasattr(self, "add_message"):
                        self.add_message(title=oper_name, text=text, level=level)

            return wrapper

        return decorator

    def __init__(self, config: dict = None):
        """
        初始化
        """
        super().__init__()

        # 初始化配置项
        configer.load_from_dict(config or {})

        if not Path(configer.PLUGIN_TEMP_PATH).exists():
            Path(configer.PLUGIN_TEMP_PATH).mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        self.init_database()

        # 实例化处理器和渲染器
        self.action_handler = ActionHandler()
        self.view_renderer = ViewRenderer()

        # 初始化通知语言
        i18n.load_translations()

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        self.api = Api(client=None)

        if config:
            configer.update_config(config)
            configer.update_plugin_config()
            i18n.load_translations()
            sentry_manager.reload_config()

        # 停止现有任务
        self.stop_service()

        if configer.enabled:
            self.init_database()

            if servicer.init_service():
                self.api = Api(client=servicer.client)

            U115Patcher().enable()
            P115DiskPatcher().enable()

            # 目录上传监控服务
            servicer.start_directory_upload()

            servicer.start_monitor_life()

        try:
            self.mcp_manager = MCPManager(api=self.api, servicer=servicer)
        except Exception as e:
            logger.warning(f"MCP 初始化跳过: {e}")
            self.mcp_manager = None

    @logs_oper("初始化数据库")
    def init_database(self) -> bool:
        """
        初始化数据库
        """
        if not Path(configer.PLUGIN_CONFIG_PATH).exists():
            Path(configer.PLUGIN_CONFIG_PATH).mkdir(parents=True, exist_ok=True)
        if not ct_db_manager.is_initialized():
            # 初始化数据库会话
            ct_db_manager.init_database(db_path=configer.PLUGIN_DB_PATH)
            # 表单补全
            init_db(
                engine=ct_db_manager.Engine,
            )
            # 初始化 迁移脚本
            if init_migration_scripts():
                # 更新数据库
                migration_db(
                    db_path=configer.PLUGIN_DB_PATH,
                    script_location=configer.PLUGIN_DATABASE_SCRIPT_LOCATION,
                    version_locations=configer.PLUGIN_DATABASE_VERSION_LOCATIONS,
                )
            else:
                raise Exception("初始化迁移脚本失败")
        return True

    def get_state(self) -> bool:
        """
        插件状态
        """
        return configer.enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return [
            {
                "cmd": "/p115_full_sync",
                "event": EventType.PluginAction,
                "desc": "全量同步115网盘文件",
                "category": "",
                "data": {"action": "p115_full_sync"},
            },
            {
                "cmd": "/p115_inc_sync",
                "event": EventType.PluginAction,
                "desc": "增量同步115网盘文件",
                "category": "",
                "data": {"action": "p115_inc_sync"},
            },
            {
                "cmd": "/p115_add_share",
                "event": EventType.PluginAction,
                "desc": "转存分享到待整理目录",
                "category": "",
                "data": {"action": "p115_add_share"},
            },
            {
                "cmd": "/ol",
                "event": EventType.PluginAction,
                "desc": "添加离线下载任务",
                "category": "",
                "data": {"action": "p115_add_offline"},
            },
            {
                "cmd": "/p115_strm",
                "event": EventType.PluginAction,
                "desc": "全量生成指定网盘目录STRM",
                "category": "",
                "data": {"action": "p115_strm"},
            },
            {
                "cmd": "/sh",
                "event": EventType.PluginAction,
                "desc": "搜索指定资源",
                "category": "",
                "data": {"action": "p115_search"},
            },
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取 API 接口
        """
        apis = [
            {
                "path": "/redirect_url",
                "endpoint": self.api.redirect_url_get,
                "methods": ["GET"],
                "summary": "302跳转",
                "description": "115网盘302跳转",
                "allow_anonymous": True,
            },
            {
                "path": "/redirect_url",
                "endpoint": self.api.redirect_url_post,
                "methods": ["POST"],
                "summary": "302跳转",
                "description": "115网盘302跳转",
                "allow_anonymous": True,
            },
            {
                "path": "/redirect_url",
                "endpoint": self.api.redirect_url_head,
                "methods": ["HEAD"],
                "summary": "302跳转",
                "description": "115网盘302跳转",
                "allow_anonymous": True,
            },
            {
                "path": "/redirect_url/{args:path}",
                "endpoint": self.api.redirect_url_get_path,
                "methods": ["GET"],
                "summary": "302跳转",
                "description": "115网盘302跳转",
                "allow_anonymous": True,
            },
            {
                "path": "/redirect_url/{args:path}",
                "endpoint": self.api.redirect_url_post_path,
                "methods": ["POST"],
                "summary": "302跳转",
                "description": "115网盘302跳转",
                "allow_anonymous": True,
            },
            {
                "path": "/redirect_url/{args:path}",
                "endpoint": self.api.redirect_url_head_path,
                "methods": ["HEAD"],
                "summary": "302跳转",
                "description": "115网盘302跳转",
                "allow_anonymous": True,
            },
            {
                "path": "/api_strm_sync_creata",
                "endpoint": self.api.api_strm_sync_creata,
                "methods": ["POST"],
                "summary": "API 请求生成 STRM",
                "description": "API 请求生成 STRM",
            },
            {
                "path": "/api_strm_sync_create_by_path",
                "endpoint": self.api.api_strm_sync_create_by_path,
                "methods": ["POST"],
                "summary": "API 请求生成 STRM（通过一组文件夹路径）",
                "description": "API 请求生成 STRM（通过一组文件夹路径）",
            },
            {
                "path": "/api_strm_sync_remove",
                "endpoint": self.api.api_strm_sync_remove,
                "methods": ["POST"],
                "summary": "API 请求删除无效 STRM 文件",
                "description": "API 请求删除无效 STRM 文件",
            },
            {
                "path": "/add_transfer_share",
                "endpoint": self.api.add_transfer_share,
                "methods": ["GET"],
                "summary": "添加分享转存整理",
            },
            {
                "path": "/user_storage_status",
                "endpoint": self.api.get_user_storage_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取115用户基本信息和空间状态",
            },
            {
                "path": "/get_config",
                "endpoint": self.api.get_config_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取配置",
            },
            {
                "path": "/get_machine_id",
                "endpoint": self.api.get_machine_id_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取 Machine ID",
            },
            {
                "path": "/generate_emby2alist_config",
                "endpoint": self.api.generate_media_redirect_config_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "生成媒体重定向配置（emby2Alist / Emby 302 反向代理）",
            },
            {
                "path": "/save_config",
                "endpoint": self._save_config_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存配置",
            },
            {
                "path": "/get_status",
                "endpoint": self.api.get_status_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取状态",
            },
            {
                "path": "/full_sync",
                "endpoint": self.api.trigger_full_sync_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "执行全量同步",
            },
            {
                "path": "/full_sync_db",
                "endpoint": self.api.trigger_full_sync_db_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "执行全量同步",
            },
            {
                "path": "/share_sync",
                "endpoint": self.api.trigger_share_sync_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "执行分享同步",
            },
            {
                "path": "/clear_id_path_cache",
                "endpoint": self.api.clear_id_path_cache_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "清理文件路径ID缓存",
            },
            {
                "path": "/clear_increment_skip_cache",
                "endpoint": self.api.clear_increment_skip_cache_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "清理增量同步跳过路径缓存",
            },
            {
                "path": "/browse_dir",
                "endpoint": self.api.browse_dir_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "浏览目录",
            },
            {
                "path": "/get_qrcode",
                "endpoint": self.api.get_qrcode_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取登录二维码",
            },
            {
                "path": "/check_qrcode",
                "endpoint": self.api.check_qrcode_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "检查二维码状态",
            },
            {
                "path": "/get_aliyundrive_qrcode",
                "endpoint": self.api.get_aliyundrive_qrcode_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取阿里云盘登录二维码",
            },
            {
                "path": "/check_aliyundrive_qrcode",
                "endpoint": self.api.check_aliyundrive_qrcode_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "检查阿里云盘二维码状态",
            },
            {
                "path": "/offline_tasks",
                "endpoint": self.api.offline_tasks_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "离线任务列表",
            },
            {
                "path": "/add_offline_task",
                "endpoint": self.api.add_offline_task_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "添加离线下载任务",
            },
            {
                "path": "/check_feature",
                "endpoint": self.api.check_feature_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "判断是否有权限使用此增强功能",
            },
            {
                "path": "/get_authorization_status",
                "endpoint": self.api.get_authorization_status_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取机器授权状态",
            },
            {
                "path": "/get_donate_info",
                "endpoint": self.api.get_donate_info_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取捐赠信息",
            },
            {
                "path": "/check_life_event_status",
                "endpoint": self.api.check_life_event_status_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "检查115生活事件线程状态并测试拉取数据",
            },
            {
                "path": "/manual_transfer",
                "endpoint": self.api.manual_transfer_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "手动触发网盘整理",
            },
            {
                "path": "/get_sync_del_history",
                "endpoint": self.api.get_sync_del_history,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取同步删除历史记录",
            },
            {
                "path": "/delete_sync_del_history",
                "endpoint": self.api.delete_sync_del_history,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "删除同步删除历史记录",
            },
            {
                "path": "/delete_all_sync_del_history",
                "endpoint": self.api.delete_all_sync_del_history,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "一键删除所有同步删除历史记录",
            },
            {
                "path": "/fuse_mount",
                "endpoint": self.api.fuse_mount_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "挂载 FUSE 文件系统",
            },
            {
                "path": "/fuse_unmount",
                "endpoint": self.api.fuse_unmount_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "卸载 FUSE 文件系统",
            },
            {
                "path": "/fuse_status",
                "endpoint": self.api.fuse_status_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取 FUSE 状态",
            },
        ]
        if getattr(self, "mcp_manager", None) is not None:
            apis.extend(
                [
                    {
                        "path": "/mcp/sse",
                        "endpoint": self.mcp_manager.handle_sse,
                        "methods": ["GET"],
                        "summary": "MCP SSE 端点",
                    },
                    {
                        "path": "/mcp/messages",
                        "endpoint": self.mcp_manager.handle_messages,
                        "methods": ["POST"],
                        "summary": "MCP 消息端点",
                    },
                ]
            )
        if servicer.webdav_core:
            apis.extend(
                [
                    {
                        "path": "/webdav",
                        "endpoint": servicer.webdav_core.propfind,
                        "methods": ["PROPFIND"],
                        "summary": "Webdav PROPFIND",
                        "description": "Webdav PROPFIND",
                        "allow_anonymous": True,
                    },
                    {
                        "path": "/webdav/{path:path}",
                        "endpoint": servicer.webdav_core.propfind,
                        "methods": ["PROPFIND"],
                        "summary": "Webdav PROPFIND",
                        "description": "Webdav PROPFIND",
                        "allow_anonymous": True,
                    },
                    {
                        "path": "/webdav",
                        "endpoint": servicer.webdav_core.get,
                        "methods": ["GET"],
                        "summary": "Webdav GET",
                        "description": "Webdav GET",
                        "allow_anonymous": True,
                    },
                    {
                        "path": "/webdav/{path:path}",
                        "endpoint": servicer.webdav_core.get,
                        "methods": ["GET"],
                        "summary": "Webdav GET",
                        "description": "Webdav GET",
                        "allow_anonymous": True,
                    },
                    {
                        "path": "/webdav",
                        "endpoint": servicer.webdav_core.options,
                        "methods": ["OPTIONS"],
                        "summary": "Webdav OPTIONS",
                        "description": "Webdav OPTIONS",
                        "allow_anonymous": True,
                    },
                    {
                        "path": "/webdav/{path:path}",
                        "endpoint": servicer.webdav_core.options,
                        "methods": ["OPTIONS"],
                        "summary": "Webdav OPTIONS",
                        "description": "Webdav OPTIONS",
                        "allow_anonymous": True,
                    },
                ]
            )
        return apis

    def get_service(self) -> List[Dict[str, str | Dict[Any, Any] | Any]] | None:
        """
        注册插件公共服务
        """
        cron_service = [
            {
                "id": "P115StrmHelper_offline_status",
                "name": "监控115网盘离线下载进度",
                "trigger": CronTrigger.from_crontab("*/2 * * * *"),
                "func": servicer.offline_status,
                "kwargs": {},
            }
        ]
        if (
            configer.monitor_life_enabled
            and configer.monitor_life_paths
            and configer.monitor_life_event_modes
        ) or (configer.pan_transfer_enabled and configer.pan_transfer_paths):
            cron_service.append(
                {
                    "id": "P115StrmHelper_monitor_life_guard",
                    "name": "115生活事件线程守护",
                    "trigger": CronTrigger.from_crontab("* * * * *"),
                    "func": servicer.check_monitor_life_guard,
                    "kwargs": {},
                }
            )
        if (
            configer.cron_full_sync_strm
            and configer.timing_full_sync_strm
            and configer.full_sync_strm_paths
        ):
            cron_service.append(
                {
                    "id": "P115StrmHelper_full_sync_strm_files",
                    "name": "定期全量同步115媒体库",
                    "trigger": CronTrigger.from_crontab(configer.cron_full_sync_strm),
                    "func": servicer.full_sync_strm_files,
                    "kwargs": {},
                }
            )
        if configer.cron_clear and (
            configer.clear_recyclebin_enabled or configer.clear_receive_path_enabled
        ):
            cron_service.append(
                {
                    "id": "P115StrmHelper_main_cleaner",
                    "name": "定期清理115空间",
                    "trigger": CronTrigger.from_crontab(configer.cron_clear),
                    "func": servicer.main_cleaner,
                    "kwargs": {},
                }
            )
        if (
            configer.increment_sync_strm_enabled
            and configer.increment_sync_strm_paths
            and configer.increment_sync_cron
        ):
            cron_service.append(
                {
                    "id": "P115StrmHelper_increment_sync_strm",
                    "name": "115网盘定期增量同步",
                    "trigger": CronTrigger.from_crontab(configer.increment_sync_cron),
                    "func": servicer.increment_sync_strm_files,
                    "kwargs": {},
                }
            )
        if cron_service:
            return cron_service

    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        """
        返回插件使用的前端渲染模式
        :return: 前端渲染模式，前端文件目录
        """
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """
        为Vue组件模式返回初始配置数据。
        Vue模式下，第一个参数返回None，第二个参数返回初始配置数据。
        """
        return None, self.api.get_config_api()

    def get_page(self) -> Optional[List[dict]]:
        """
        Vue模式不使用Vuetify页面定义
        """
        return None

    @eventmanager.register(EventType.TransferComplete)
    def delete_top_pan_transfer_path(self, event: Event):
        """
        处理网盘整理MP无法删除的顶层目录
        """

        if not configer.pan_transfer_enabled or not configer.pan_transfer_paths:
            return

        if not pantransfercacher.top_delete_pan_transfer_list:
            return

        item = event.event_data
        if not item:
            return

        item_transfer = item.get("transferinfo")
        if isinstance(item_transfer, dict):
            item_transfer = TransferInfo(**item_transfer)
        dest_fileitem: FileItem = item_transfer.target_item
        src_fileitem: FileItem = item.get("fileitem")

        if item_transfer.transfer_type != "move":
            return

        if (
            dest_fileitem.storage != configer.storage_module
            or src_fileitem.storage != configer.storage_module
        ):
            return

        if not PathUtils.get_run_transfer_path(
            paths=configer.pan_transfer_paths,
            transfer_path=src_fileitem.path,
        ):
            return

        remove_id = ""
        # 遍历删除字典
        for key, item_list in pantransfercacher.top_delete_pan_transfer_list.items():
            # 只有目前处理完成的这个文件ID在处理列表中，才表明匹配到了该删除的顶层目录
            if str(dest_fileitem.fileid) in item_list:
                # 从列表中删除这个ID
                pantransfercacher.top_delete_pan_transfer_list[key] = [
                    item for item in item_list if item != str(dest_fileitem.fileid)
                ]
                # 记录需删除的顶层目录
                remove_id = key
                break

        if remove_id:
            # 只有需删除的顶层目录下面的文件全部整理完成才进行删除操作
            if not pantransfercacher.top_delete_pan_transfer_list.get(remove_id):
                del pantransfercacher.top_delete_pan_transfer_list[remove_id]
                resp = servicer.client.fs_delete(int(remove_id))
                if resp["state"]:
                    logger.info(f"【网盘整理】删除 {remove_id} 文件夹成功")
                else:
                    logger.error(f"【网盘整理】删除 {remove_id} 文件夹失败: {resp}")

        return

    @eventmanager.register(
        [
            EventType.TransferComplete,
            EventType.AudioTransferComplete,
            EventType.SubtitleTransferComplete,
        ]
    )
    def generate_strm(self, event: Event):
        """
        监控目录整理生成 STRM 文件
        """
        if (
            not configer.enabled
            or not configer.transfer_monitor_enabled
            or not configer.transfer_monitor_paths
            or not configer.moviepilot_address
        ):
            return

        item = event.event_data
        if not item:
            return
        event_type = event.event_type
        if not event_type:
            return

        strm_helper = TransferStrmHelper()
        strm_helper.do_generate(
            client=servicer.client,
            item=item,
            event_type=event_type,
            mediainfodownloader=servicer.mediainfodownloader,
        )

    @eventmanager.register(EventType.PluginAction)
    def p115_full_sync(self, event: Event):
        """
        远程全量同步
        """
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "p115_full_sync":
            return
        post_message(
            channel=event.event_data.get("channel"),
            title=i18n.translate("start_full_sync"),
            userid=event.event_data.get("user"),
        )
        servicer.full_sync_strm_files()

    @eventmanager.register(EventType.PluginAction)
    def p115_inc_sync(self, event: Event):
        """
        远程增量同步
        """
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "p115_inc_sync":
            return
        post_message(
            channel=event.event_data.get("channel"),
            title=i18n.translate("start_inc_sync"),
            userid=event.event_data.get("user"),
        )
        servicer.increment_sync_strm_files(send_msg=True)

    @eventmanager.register(EventType.PluginAction)
    def p115_strm(self, event: Event):
        """
        全量生成指定网盘目录STRM
        """
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "p115_strm":
            return
        args = event_data.get("arg_str")
        if not args:
            logger.error(f"【全量STRM生成】缺少参数：{event_data}")
            post_message(
                channel=event.event_data.get("channel"),
                title=i18n.translate("p115_strm_parameter_error"),
                userid=event.event_data.get("user"),
            )
            return
        if (
            not configer.full_sync_strm_paths
            or not configer.moviepilot_address
            or not configer.user_download_mediaext
        ):
            post_message(
                channel=event.event_data.get("channel"),
                title=i18n.translate("p115_strm_full_sync_config_error"),
                userid=event.event_data.get("user"),
            )
            return

        status, paths = PathUtils.get_p115_strm_path(
            paths=configer.full_sync_strm_paths, media_path=args
        )
        if not status:
            post_message(
                channel=event.event_data.get("channel"),
                title=f"{args} {i18n.translate('p115_strm_match_path_error')}",
                userid=event.event_data.get("user"),
            )
            return
        strm_helper = FullSyncStrmHelper(
            client=servicer.client,
            mediainfodownloader=servicer.mediainfodownloader,
        )
        post_message(
            channel=event.event_data.get("channel"),
            title=i18n.translate("p115_strm_start_sync", paths=args),
            userid=event.event_data.get("user"),
        )
        strm_helper.generate_strm_files(
            full_sync_strm_paths=paths,
        )
        (
            strm_count,
            mediainfo_count,
            strm_fail_count,
            mediainfo_fail_count,
            remove_unless_strm_count,
        ) = strm_helper.get_generate_total()
        text = f"""
📂 网盘路径：{args}
📄 生成STRM文件 {strm_count} 个
⬇️ 下载媒体文件 {mediainfo_count} 个
❌ 生成STRM失败 {strm_fail_count} 个
🚫 下载媒体失败 {mediainfo_fail_count} 个
"""
        if remove_unless_strm_count != 0:
            text += f"🗑️ 清理无效STRM文件 {remove_unless_strm_count} 个"
        post_message(
            channel=event.event_data.get("channel"),
            userid=event.event_data.get("user"),
            title=i18n.translate("full_sync_done_title"),
            text=text,
        )

    @eventmanager.register(EventType.PluginAction)
    def p115_search(self, event: Event):
        """
        处理搜索请求
        """
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "p115_search":
            return

        if not configer.tg_search_channels:
            post_message(
                channel=event.event_data.get("channel"),
                title=i18n.translate("p115_search_config_error"),
                userid=event.event_data.get("user"),
            )
            return

        args = event_data.get("arg_str")
        if not args:
            logger.error(f"【搜索】缺少参数：{event_data}")
            post_message(
                channel=event.event_data.get("channel"),
                title=i18n.translate("p115_search_parameter_error"),
                userid=event.event_data.get("user"),
            )
            return

        try:
            session = session_manager.get_or_create(
                event_data, plugin_id=self.__class__.__name__
            )

            search_keyword = args.strip()

            if configer.nullbr_app_id and configer.nullbr_api_key:
                command = "search"
                view = "search_list"
            else:
                command = "resource"
                view = "resource_list"

            action = Action(command=command, view=view, value=search_keyword)

            immediate_messages = self.action_handler.process(session, action)
            # 报错，截断后续运行
            if immediate_messages:
                for msg in immediate_messages:
                    self.__send_message(session, text=msg.get("text"), title="错误")
                return

            # 设置页面
            session.go_to(view)
            self._render_and_send(session)
        except Exception as e:
            logger.error(f"处理 search 命令失败: {e}", exc_info=True)

    @eventmanager.register(EventType.MessageAction)
    def message_action(self, event: Event):
        """
        处理按钮点击回调
        """
        try:
            event_data = event.event_data
            callback_text = event_data.get("text", "")

            # 1. 解码 Action callback_text = c:xxx|w:xxx|v|xxx
            session_id, action = decode_action(callback_text=callback_text)
            if not session_id or not action:
                # 如果解码失败或不属于本插件，则忽略
                return

            # 2. 获取会话
            session = session_manager.get(session_id)
            if not session:
                context = {
                    "channel": event_data.get("channel"),
                    "source": event_data.get("source"),
                    "userid": event_data.get("userid") or event_data.get("user"),
                    "original_message_id": event_data.get("original_message_id"),
                    "original_chat_id": event_data.get("original_chat_id"),
                }
                self.post_message(
                    **context,
                    title="⚠️ 会话已过期",
                    text="操作已超时。\n请重新发起 `/sh` 命令。",
                )
                return

            # 3. 更新会话上下文
            session.update_message_context(event_data)

            # 4. 委托给 ActionHandler 处理业务逻辑
            immediate_messages = self.action_handler.process(session, action)
            if immediate_messages:
                for msg in immediate_messages:
                    self.__send_message(session, text=msg.get("text"), title="错误")
                    return

            # 5. 渲染新视图并发送
            self._render_and_send(session)
        except Exception as e:
            logger.debug(f"出错了：{e}", exc_info=True)

    def _render_and_send(self, session: TSession):
        """
        根据 Session 的当前状态，渲染视图并发送/编辑消息。
        """
        # 1. 委托给 ViewRenderer 生成界面数据
        render_data = self.view_renderer.render(session)

        # 2. 发送或编辑消息
        self.__send_message(session, render_data=render_data)

        # 3. 处理会话结束逻辑
        if session.view.name in ["subscribe_success", "close"]:
            # 深复制会话的删除消息数据
            delete_message_data = deepcopy(session.get_delete_message_data())
            session_manager.end(session.session_id)
            # 等待一段时间让用户看到最后一条消息
            sleep(5)
            self.__delete_message(**delete_message_data)

    def __send_message(
        self, session: TSession, render_data: Optional[dict] = None, **kwargs
    ):
        """
        统一的消息发送接口。
        """
        context = asdict(session.message)
        if render_data:
            context.update(render_data)
        context.update(kwargs)
        # 将 user key改名成 userid，规避传入值只是user
        userid = context.get("user")
        if userid:
            context["userid"] = userid
            # 删除多余的 user 键
            context.pop("user", None)
        self.post_message(**context)

    def __delete_message(
        self,
        channel: MessageChannel,
        source: str,
        message_id: Union[str, int],
        chat_id: Optional[Union[str, int]] = None,
    ) -> bool:
        """
        删除会话中的原始消息。
        """
        # 兼容旧版本无删除方法
        if hasattr(self.chain, "delete_message"):
            return self.chain.delete_message(
                channel=channel, source=source, message_id=message_id, chat_id=chat_id
            )
        return False

    @eventmanager.register(EventType.UserMessage)
    def user_add_share(self, event: Event):
        """
        远程分享转存
        """
        if not configer.enabled:
            return
        text = event.event_data.get("text")
        userid = event.event_data.get("userid")
        channel = event.event_data.get("channel")
        if not text:
            return
        if not text.startswith("http"):
            return
        if not bool(re_match(U115_SHARE_URL_MATCH, text)) and not bool(
            re_match(ALIYUN_SHARE_URL_MATCH, text)
        ):
            return

        if len(configer.share_recieve_paths) <= 1:
            servicer.sharetransferhelper.add_share(
                url=text,
                channel=channel,
                userid=userid,
            )
            return

        try:
            session = session_manager.get_or_create(
                event.event_data, plugin_id=self.__class__.__name__
            )

            action = Action(
                command="share_recieve_path", view="share_recieve_paths", value=text
            )

            immediate_messages = self.action_handler.process(session, action)
            # 报错，截断后续运行
            if immediate_messages:
                for msg in immediate_messages:
                    self.__send_message(session, text=msg.get("text"), title="错误")
                return

            # 设置页面
            session.go_to("share_recieve_paths")
            self._render_and_send(session)
        except Exception as e:
            logger.error(f"处理分享转存命令失败: {e}")

    @eventmanager.register(EventType.PluginAction)
    def p115_add_share(self, event: Event):
        """
        远程分享转存
        """
        args = None
        if event:
            event_data = event.event_data
            if not event_data or event_data.get("action") != "p115_add_share":
                return
            args = event_data.get("arg_str")
            if not args:
                logger.error(f"【分享转存】缺少参数：{event_data}")
                post_message(
                    channel=event.event_data.get("channel"),
                    title=i18n.translate("p115_add_share_parameter_error"),
                    userid=event.event_data.get("user"),
                )
                return

        if len(configer.share_recieve_paths) <= 1:
            servicer.sharetransferhelper.add_share(
                url=args,
                channel=event.event_data.get("channel"),
                userid=event.event_data.get("user"),
            )
            return

        try:
            session = session_manager.get_or_create(
                event.event_data, plugin_id=self.__class__.__name__
            )

            action = Action(
                command="share_recieve_path", view="share_recieve_paths", value=args
            )

            immediate_messages = self.action_handler.process(session, action)
            # 报错，截断后续运行
            if immediate_messages:
                for msg in immediate_messages:
                    self.__send_message(session, text=msg.get("text"), title="错误")
                return

            # 设置页面
            session.go_to("share_recieve_paths")
            self._render_and_send(session)
        except Exception as e:
            logger.error(f"处理分享转存命令失败: {e}")

    @eventmanager.register(EventType.PluginAction)
    def p115_add_offline(self, event: Event):
        """
        添加离线下载任务
        """
        args = None
        if event:
            event_data = event.event_data
            if not event_data or event_data.get("action") != "p115_add_offline":
                return
            args = event_data.get("arg_str")
            if not args:
                logger.error(f"【离线下载】缺少参数：{event_data}")
                post_message(
                    channel=event.event_data.get("channel"),
                    title=i18n.translate("p115_add_offline_parameter_error"),
                    userid=event.event_data.get("user"),
                )
                return

        if len(configer.offline_download_paths) <= 1:
            if servicer.offlinehelper.add_urls_to_transfer([str(args)]):
                post_message(
                    channel=event.event_data.get("channel"),
                    title=i18n.translate("p115_add_offline_success"),
                    userid=event.event_data.get("user"),
                )
            else:
                post_message(
                    channel=event.event_data.get("channel"),
                    title=i18n.translate("p115_add_offline_fail"),
                    userid=event.event_data.get("user"),
                )
            return

        try:
            session = session_manager.get_or_create(
                event.event_data, plugin_id=self.__class__.__name__
            )

            action = Action(
                command="offline_download_path",
                view="offline_download_paths",
                value=args,
            )

            immediate_messages = self.action_handler.process(session, action)
            # 报错，截断后续运行
            if immediate_messages:
                for msg in immediate_messages:
                    self.__send_message(session, text=msg.get("text"), title="错误")
                return

            # 设置页面
            session.go_to("offline_download_paths")
            self._render_and_send(session)
        except Exception as e:
            logger.error(f"处理离线下载命令失败: {e}")

    @eventmanager.register(
        [
            EventType.TransferComplete,
            EventType.AudioTransferComplete,
            EventType.SubtitleTransferComplete,
        ]
    )
    def fix_monitor_life_strm(self, event: Event):
        """
        监控整理事件
        处理115生活事件生成MP整理STRM文件名称错误
        """

        def file_rename(fileitem: FileItem, refresh: bool = False):
            """
            重命名
            """
            if not fileitem:
                return
            target_path = Path(fileitem.path).parent
            file_item = lifeeventcacher.create_strm_file_dict.get(
                str(fileitem.fileid), None
            )
            if not file_item:
                return
            if fileitem.name != file_item[0]:
                # 文件名称不一致，表明网盘文件被重命名，需要将本地文件重命名
                target_path_obj = Path(target_path / fileitem.name).relative_to(
                    file_item[2]
                )
                target_file_path = (
                    Path(file_item[1])
                    / target_path_obj.parent
                    / StrmGenerater.get_strm_filename(target_path_obj)
                )
                life_path_obj = Path(target_path / file_item[0]).relative_to(
                    file_item[2]
                )
                life_path = (
                    Path(file_item[1])
                    / life_path_obj.parent
                    / StrmGenerater.get_strm_filename(life_path_obj)
                )
                # 如果重命名后的文件存在，先删除再重命名
                try:
                    if target_file_path.exists():
                        target_file_path.unlink(missing_ok=True)
                    life_path.rename(target_file_path)
                    _databasehelper.update_path_by_id(
                        id=int(fileitem.fileid),
                        new_path=Path(target_path / fileitem.name).as_posix(),
                    )
                    _databasehelper.update_name_by_id(
                        id=int(fileitem.fileid),
                        new_name=str(fileitem.name),
                    )
                    lifeeventcacher.create_strm_file_dict.pop(
                        str(fileitem.fileid), None
                    )
                    logger.info(
                        f"【监控生活事件】修正文件名称: {life_path} --> {target_file_path}"
                    )
                    if refresh:
                        servicer.monitorlife.mediaserver_helper.refresh_mediaserver(
                            file_path=Path(target_file_path).as_posix(),
                            file_name=str(target_file_path.name),
                        )
                    return
                except Exception as e:
                    logger.error(f"【监控生活事件】修正文件名称失败: {e}")

        # 生活事件已开启
        if (
            not configer.monitor_life_enabled
            or not configer.monitor_life_paths
            or not configer.monitor_life_event_modes
        ):
            return

        # 生活事件在运行
        if not bool(
            servicer.monitor_life_thread and servicer.monitor_life_thread.is_alive()
        ):
            return

        item = event.event_data
        if not item:
            return
        event_type = event.event_type
        if not event_type:
            return

        # 整理信息
        item_transfer = item.get("transferinfo")
        if isinstance(item_transfer, dict):
            item_transfer = TransferInfo(**item_transfer)
        # 目的地文件 fileitem
        dest_fileitem: FileItem = item_transfer.target_item

        _databasehelper = FileDbHelper()

        # 音轨和字幕文件名称更改无需刷新媒体服务器
        media_refresh = True
        if (
            event_type == EventType.AudioTransferComplete
            or event_type == EventType.SubtitleTransferComplete
        ):
            media_refresh = False

        file_rename(fileitem=dest_fileitem, refresh=media_refresh)

    @eventmanager.register(EventType.WebhookMessage)
    def sync_del_by_webhook(self, event: Event):
        """
        通过Webhook事件同步删除媒体
        """
        if not configer.sync_del_enabled:
            return

        if not event or not event.event_data:
            return

        mediasyncdel_helper = MediaSyncDelHelper()
        mediasyncdel_helper.sync_del_by_webhook(
            event_data=event.event_data,
            enabled=configer.sync_del_enabled,
            notify=configer.sync_del_notify,
            del_source=configer.sync_del_source,
            p115_library_path=configer.sync_del_p115_library_path,
            p115_force_delete_files=configer.sync_del_p115_force_delete_files,
        )

    @eventmanager.register(EventType.DownloadFileDeleted)
    def download_file_del_sync(self, event: Event):
        """
        下载文件删除处理事件
        """
        if not configer.sync_del_enabled:
            return

        if not event:
            return

        mediasyncdel_helper = MediaSyncDelHelper()
        mediasyncdel_helper.download_file_del_sync(event)

    def stop_service(self):
        """
        退出插件
        """
        servicer.stop()
        ct_db_manager.close_database()
        U115Patcher().disable()
        P115DiskPatcher().disable()

    async def _save_config_api(self, request: Request) -> Dict:
        """
        异步保存配置
        """
        try:
            data = await request.json()
            if not configer.update_config(data):
                return {"code": 1, "msg": "保存失败，请查看详细日志"}

            # 持久化存储配置
            configer.update_plugin_config()

            i18n.load_translations()

            sentry_manager.reload_config()

            # 重新初始化插件
            self.init_plugin(config=self.get_config())

            return {"code": 0, "msg": "保存成功"}
        except Exception as e:
            return {"code": 1, "msg": f"保存失败: {str(e)}"}
