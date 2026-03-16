from pathlib import Path
from typing import Optional, TYPE_CHECKING, Any

from app.log import logger
from app.schemas import FileItem

if TYPE_CHECKING:
    from ....p115disk.p115_api import P115Api
else:
    P115Api = Any

try:
    from app.plugins.p115disk.p115_api import P115Api  # noqa

    P115_API_AVAILABLE = True
except (ImportError, Exception):
    P115_API_AVAILABLE = False


class CacheUpdater:
    """
    115 网盘缓存更新器
    """

    def __init__(self, p115_api: Optional["P115Api"] = None):
        """
        初始化缓存更新器

        :param p115_api: P115Api 实例
        """
        self._p115_api = p115_api

    @classmethod
    def create(cls, client, storage_name: str = "115网盘Plus") -> "CacheUpdater":
        """
        创建缓存更新器实例

        :param client: 115 客户端实例
        :param storage_name: 存储名称
        :return: CacheUpdater 实例
        """
        p115_api = None
        if P115_API_AVAILABLE:
            try:
                p115_api = P115Api(client=client, disk_name=storage_name)
            except Exception as e:
                logger.warn(f"【整理接管】无法创建 P115Api 实例，缓存更新将跳过: {e}")

        return cls(p115_api=p115_api)

    def update_folder_cache(self, folder_item: FileItem) -> None:
        """
        更新目录缓存

        :param folder_item: 目录文件项
        """
        if not self._p115_api or not folder_item or not folder_item.fileid:
            return
        try:
            if hasattr(self._p115_api, "_id_cache"):
                self._p115_api._id_cache.add_cache(
                    id=int(folder_item.fileid),
                    directory=folder_item.path.rstrip("/"),
                )
            if hasattr(self._p115_api, "_id_item_cache"):
                self._p115_api._id_item_cache.add_cache(
                    id=int(folder_item.fileid),
                    item={
                        "path": folder_item.path.rstrip("/"),
                        "id": folder_item.fileid,
                        "size": None,
                        "modify_time": folder_item.modify_time or 0,
                        "pickcode": folder_item.pickcode or "",
                        "is_dir": True,
                    },
                )
        except Exception as e:
            logger.debug(f"【整理接管】更新目录缓存失败: {e}")

    def update_file_cache(self, file_item: FileItem) -> None:
        """
        更新文件缓存

        :param file_item: 文件项
        """
        if not self._p115_api or not file_item or not file_item.fileid:
            return
        try:
            if hasattr(self._p115_api, "_id_cache"):
                self._p115_api._id_cache.add_cache(
                    id=int(file_item.fileid),
                    directory=file_item.path,
                )
            if hasattr(self._p115_api, "_id_item_cache"):
                self._p115_api._id_item_cache.add_cache(
                    id=int(file_item.fileid),
                    item={
                        "path": file_item.path,
                        "id": file_item.fileid,
                        "size": file_item.size or 0,
                        "modify_time": file_item.modify_time or 0,
                        "pickcode": file_item.pickcode or "",
                        "is_dir": False,
                    },
                )
        except Exception as e:
            logger.debug(f"【整理接管】更新文件缓存失败: {e}")

    def remove_cache(self, file_id: int) -> None:
        """
        删除缓存

        :param file_id: 文件ID
        """
        if not self._p115_api:
            return
        try:
            if hasattr(self._p115_api, "_id_cache"):
                self._p115_api._id_cache.remove(id=file_id)
            if hasattr(self._p115_api, "_id_item_cache"):
                self._p115_api._id_item_cache.remove(file_id)
        except Exception as e:
            logger.debug(f"【整理接管】删除缓存失败: {e}")

    def update_rename_cache(self, file_id: int, new_name: str) -> None:
        """
        更新重命名后的缓存

        :param file_id: 文件ID
        :param new_name: 新文件名
        """
        if not self._p115_api:
            return
        try:
            if hasattr(self._p115_api, "_id_cache"):
                old_path = self._p115_api._id_cache.get_dir_by_id(file_id)
                if old_path:
                    self._p115_api._id_cache.remove(id=file_id)
                    new_path = Path(old_path).parent / new_name
                    self._p115_api._id_cache.add_cache(
                        id=file_id,
                        directory=str(new_path),
                    )
            if hasattr(self._p115_api, "_id_item_cache"):
                old_item = self._p115_api._id_item_cache.get_item(file_id)
                if old_item:
                    new_path = Path(old_item["path"]).parent / new_name
                    self._p115_api._id_item_cache.add_cache(
                        id=file_id,
                        item={
                            "path": str(new_path),
                            "id": old_item["id"],
                            "size": old_item["size"],
                            "modify_time": old_item["modify_time"],
                            "pickcode": old_item["pickcode"],
                            "is_dir": old_item["is_dir"],
                        },
                    )
        except Exception as e:
            logger.debug(f"【整理接管】更新重命名缓存失败 (file_id: {file_id}): {e}")
