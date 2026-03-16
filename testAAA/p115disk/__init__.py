from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional

from p115client import P115Client

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import ChainEventType
from app.helper.storage import StorageHelper
from app.schemas import StorageOperSelectionEventData, FileItem, StorageUsage

from .p115_api import P115Api


class P115Disk(_PluginBase):
    # 插件名称
    plugin_name = "115网盘储存"
    # 插件描述
    plugin_desc = "更快更强的115网盘存储模块。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Frontend/refs/heads/v2/src/assets/images/misc/u115.png"
    # 插件版本
    plugin_version = "0.2.7"
    # 插件作者
    plugin_author = "DDSRem"
    # 作者主页
    author_url = "https://github.com/DDSRem"
    # 插件配置项ID前缀
    plugin_config_prefix = "p115disk_"
    # 加载顺序
    plugin_order = 99
    # 可使用的用户级别
    auth_level = 1

    # 是否启用
    _enabled = False
    _client = None
    _disk_name = None
    _p115_api = None
    _cookie = None

    def __init__(self):
        """
        初始化
        """
        super().__init__()

        self._disk_name = "115网盘Plus"

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        if config:
            storage_helper = StorageHelper()
            storages = storage_helper.get_storagies()
            if not any(
                s.type == self._disk_name and s.name == self._disk_name
                for s in storages
            ):
                storage_helper.add_storage(
                    storage=self._disk_name, name=self._disk_name, conf={}
                )

            self._enabled = config.get("enabled")
            self._cookie = config.get("cookie")

            try:
                self._client = P115Client(cookies=self._cookie)
                self._p115_api = P115Api(client=self._client, disk_name=self._disk_name)
            except Exception as e:
                logger.error(f"115 网盘客户端创建失败: {e}")

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件API端点
        """
        return [
            {
                "path": "/clear_cache",
                "endpoint": self.clear_cache,
                "auth": "bear",
                "methods": ["POST"],
                "summary": "清理缓存",
                "description": "清理115网盘文件路径ID缓存和文件详情ID缓存",
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "cookie",
                                            "label": "115 Cookie",
                                            "hint": "Cookie 可以复用 115 网盘 STRM 助手的配置",
                                            "persistent-hint": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "warning",
                                            "variant": "tonal",
                                            "density": "compact",
                                            "class": "mt-2",
                                        },
                                        "content": [
                                            {
                                                "component": "div",
                                                "text": "重要提示：",
                                            },
                                            {
                                                "component": "div",
                                                "text": "• 下载模块和上传模块默认使用 MoviePilot 程序里面的 115 网盘存储模块，请务必在系统设置中配置好 115 网盘存储模块",
                                            },
                                            {
                                                "component": "div",
                                                "text": "• 其余接口（如浏览、删除、重命名等）为 Cookie 接口调用",
                                            },
                                            {
                                                "component": "div",
                                                "text": "• Cookie 可以复用 115 网盘 STRM 助手的配置，无需重复填写",
                                            },
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "cookie": "",
        }

    def get_page(self) -> List[dict]:
        """
        获取插件数据页面
        """
        return [
            {
                "component": "VCard",
                "props": {"variant": "outlined"},
                "content": [
                    {
                        "component": "VCardText",
                        "props": {"class": "pa-6 d-flex flex-column align-center"},
                        "content": [
                            {
                                "component": "VBtn",
                                "props": {
                                    "color": "primary",
                                    "variant": "elevated",
                                    "size": "large",
                                    "prepend-icon": "mdi-delete-sweep",
                                    "class": "mb-3",
                                },
                                "text": "清理缓存",
                                "events": {
                                    "click": {
                                        "api": "plugin/P115Disk/clear_cache",
                                        "method": "post",
                                    },
                                },
                            },
                            {
                                "component": "div",
                                "props": {"class": "text-caption text-medium-emphasis"},
                                "text": "清理115网盘文件路径ID缓存和文件详情ID缓存",
                            },
                        ],
                    },
                ],
            },
        ]

    def get_module(self) -> Dict[str, Any]:
        """
        获取插件模块声明，用于胁持系统模块实现
        """
        return {
            "list_files": self.list_files,
            "any_files": self.any_files,
            "download_file": self.download_file,
            "upload_file": self.upload_file,
            "delete_file": self.delete_file,
            "rename_file": self.rename_file,
            "get_file_item": self.get_file_item,
            "get_parent_item": self.get_parent_item,
            "snapshot_storage": self.snapshot_storage,
            "storage_usage": self.storage_usage,
            "support_transtype": self.support_transtype,
            "create_folder": self.create_folder,
            "exists": self.exists,
            "get_item": self.get_item,
        }

    @eventmanager.register(ChainEventType.StorageOperSelection)
    def storage_oper_selection(self, event: Event):
        """
        监听存储选择事件，返回当前类为操作对象
        """
        if not self._enabled:
            return
        event_data: StorageOperSelectionEventData = event.event_data
        if event_data.storage == self._disk_name:
            event_data.storage_oper = self._p115_api  # noqa

    def list_files(
        self, fileitem: FileItem, recursion: bool = False
    ) -> Optional[List[FileItem]]:
        """
        查询当前目录下所有目录和文件
        """

        if fileitem.storage != self._disk_name:
            return None

        if recursion:
            result = self._p115_api.iter_files(fileitem)
            if result is not None:
                return result

        def __get_files(_item: FileItem, _r: Optional[bool] = False):
            """
            递归处理
            """
            _items = self._p115_api.list(_item)
            if _items:
                if _r:
                    for t in _items:
                        if t.type == "dir":
                            __get_files(t, _r)
                        else:
                            result.append(t)
                else:
                    result.extend(_items)

        result = []
        __get_files(fileitem, recursion)

        return result

    def any_files(self, fileitem: FileItem, extensions: list = None) -> Optional[bool]:
        """
        查询当前目录下是否存在指定扩展名任意文件
        """
        if fileitem.storage != self._disk_name:
            return None

        def __any_file(_item: FileItem):
            """
            递归处理
            """
            _items = self._p115_api.list(_item)
            if _items:
                if not extensions:
                    return True
                for t in _items:
                    if (
                        t.type == "file"
                        and t.extension
                        and f".{t.extension.lower()}" in extensions
                    ):
                        return True
                    elif t.type == "dir":
                        if __any_file(t):
                            return True
            return False

        return __any_file(fileitem)

    def create_folder(self, fileitem: FileItem, name: str) -> Optional[FileItem]:
        """
        创建目录
        """
        if fileitem.storage != self._disk_name:
            return None

        return self._p115_api.create_folder(fileitem=fileitem, name=name)

    def download_file(self, fileitem: FileItem, path: Path = None) -> Optional[Path]:
        """
        下载文件

        :param fileitem: 文件项
        :param path: 本地保存路径
        """
        if fileitem.storage != self._disk_name:
            return None

        return self._p115_api.download(fileitem, path)

    def upload_file(
        self, fileitem: FileItem, path: Path, new_name: Optional[str] = None
    ) -> Optional[FileItem]:
        """
        上传文件
        :param fileitem: 保存目录项
        :param path: 本地文件路径
        :param new_name: 新文件名
        """
        if fileitem.storage != self._disk_name:
            return None

        return self._p115_api.upload(fileitem, path, new_name)

    def delete_file(self, fileitem: FileItem) -> Optional[bool]:
        """
        删除文件或目录
        """
        if fileitem.storage != self._disk_name:
            return None

        return self._p115_api.delete(fileitem)

    def rename_file(self, fileitem: FileItem, name: str) -> Optional[bool]:
        """
        重命名文件或目录
        """
        if fileitem.storage != self._disk_name:
            return None

        return self._p115_api.rename(fileitem, name)

    def exists(self, fileitem: FileItem) -> Optional[bool]:
        """
        判断文件或目录是否存在
        """
        if fileitem.storage != self._disk_name:
            return None

        return True if self.get_item(fileitem) else False

    def get_item(self, fileitem: FileItem) -> Optional[FileItem]:
        """
        查询目录或文件
        """
        if fileitem.storage != self._disk_name:
            return None

        return self.get_file_item(storage=fileitem.storage, path=Path(fileitem.path))

    def get_file_item(self, storage: str, path: Path) -> Optional[FileItem]:
        """
        根据路径获取文件项
        """
        if storage != self._disk_name:
            return None

        return self._p115_api.get_item(path)

    def get_parent_item(self, fileitem: FileItem) -> Optional[FileItem]:
        """
        获取上级目录项
        """
        if fileitem.storage != self._disk_name:
            return None

        return self._p115_api.get_parent(fileitem)

    def snapshot_storage(
        self,
        storage: str,
        path: Path,
        last_snapshot_time: float = None,
        max_depth: int = 5,
    ) -> Optional[Dict[str, Dict]]:
        """
        快照存储

        :param storage: 存储类型
        :param path: 路径
        :param last_snapshot_time: 上次快照时间，用于增量快照
        :param max_depth: 最大递归深度，避免过深遍历
        """
        if storage != self._disk_name:
            return None

        files_info = {}

        def __snapshot_file(_fileitm: FileItem, current_depth: int = 0):
            """
            递归获取文件信息
            """
            try:
                if _fileitm.type == "dir":
                    if current_depth >= max_depth:
                        return

                    if (
                        self.snapshot_check_folder_modtime  # noqa
                        and last_snapshot_time
                        and _fileitm.modify_time
                        and _fileitm.modify_time <= last_snapshot_time
                    ):
                        return

                    sub_files = self._p115_api.list(_fileitm)
                    for sub_file in sub_files:
                        __snapshot_file(sub_file, current_depth + 1)
                else:
                    if getattr(_fileitm, "modify_time", 0) > last_snapshot_time:
                        files_info[_fileitm.path] = {
                            "size": _fileitm.size or 0,
                            "modify_time": getattr(_fileitm, "modify_time", 0),
                            "type": _fileitm.type,
                        }

            except Exception as e:
                logger.debug(f"Snapshot error for {_fileitm.path}: {e}")

        fileitem = self._p115_api.get_item(path)
        if not fileitem:
            return {}

        __snapshot_file(fileitem)

        return files_info

    def storage_usage(self, storage: str) -> Optional[StorageUsage]:
        """
        存储使用情况
        """
        if storage != self._disk_name:
            return None

        return self._p115_api.usage()

    def support_transtype(self, storage: str) -> Optional[dict]:
        """
        获取支持的整理方式
        """
        if storage != self._disk_name:
            return None

        return {"move": "移动", "copy": "复制"}

    def clear_cache(self) -> Dict[str, Any]:
        """
        清理缓存

        :return: 清理结果
        """
        try:
            if not self._p115_api:
                return {
                    "code": 1,
                    "msg": "插件未启用或未初始化",
                }

            self._p115_api._id_cache.clear()
            self._p115_api._id_item_cache.clear()

            logger.info("【P115Disk】缓存清理成功")
            return {
                "code": 0,
                "msg": "缓存清理成功",
            }
        except Exception as e:
            logger.error(f"【P115Disk】缓存清理失败: {e}", exc_info=True)
            return {
                "code": 1,
                "msg": f"缓存清理失败: {str(e)}",
            }

    def stop_service(self):
        """
        退出插件
        """
        pass
