from typing import Optional

from app.core.cache import TTLCache


class IdPathCache:
    """
    文件路径ID缓存
    """

    def __init__(self, maxsize=128):
        """
        初始化文件路径ID缓存

        :param maxsize: 缓存最大大小，默认128
        """
        self.id_to_dir = TTLCache(
            region="p115disk_id_path_cache_id_to_dir",
            maxsize=maxsize,
            ttl=60 * 30,
        )
        self.dir_to_id = TTLCache(
            region="p115disk_id_path_cache_dir_to_id",
            maxsize=maxsize,
            ttl=60 * 30,
        )

    def add_cache(self, id: int, directory: str):
        """
        添加缓存

        :param id: 文件 ID
        :param directory: 目录路径
        """
        old_directory = self.id_to_dir.get(str(id))
        if old_directory and old_directory != directory:
            self.dir_to_id.delete(key=old_directory)

        old_id = self.dir_to_id.get(directory)
        if old_id and old_id != str(id):
            self.id_to_dir.delete(key=old_id)

        self.id_to_dir.set(key=str(id), value=directory)
        self.dir_to_id.set(key=directory, value=str(id))

    def get_dir_by_id(self, id: int) -> Optional[str]:
        """
        通过 ID 获取路径

        :param id: 文件 ID
        :return: 目录路径，如果不存在则返回 None
        """
        return self.id_to_dir.get(str(id))

    def get_id_by_dir(self, directory: str) -> Optional[int]:
        """
        通过路径获取 ID

        :param directory: 目录路径
        :return: 文件 ID，如果不存在则返回 None
        """
        _id = self.dir_to_id.get(directory)
        if _id is None:
            return None
        try:
            return int(_id)
        except ValueError:
            return None

    def remove(self, id: Optional[int] = None, directory: Optional[str] = None):
        """
        通过 ID 或路径删除单条缓存

        :param id: 文件 ID
        :param directory: 目录路径
        :raises ValueError: 当 id 和 directory 都未提供时抛出
        """
        if id is not None:
            directory = self.id_to_dir.get(str(id))
            if directory:
                self.id_to_dir.delete(key=str(id))
                self.dir_to_id.delete(key=directory)
        elif directory is not None:
            _id = self.dir_to_id.get(directory)
            if _id:
                self.dir_to_id.delete(key=directory)
                self.id_to_dir.delete(key=_id)
        else:
            raise ValueError("id 和 directory 至少需要提供一个")

    def clear(self):
        """
        清空所有缓存
        """
        self.id_to_dir.clear()
        self.dir_to_id.clear()


class ItemIdCache:
    """
    文件详情ID缓存
    """

    def __init__(self, maxsize=128):
        """
        初始化文件详情ID缓存

        :param maxsize: 缓存最大大小，默认128
        """
        self.id_to_item = TTLCache(
            region="p115disk_item_id_cache",
            maxsize=maxsize,
            ttl=60 * 30,
        )

    def add_cache(self, id: int, item: dict):
        """
        添加缓存

        :param id: 文件 ID
        :param item: 文件详情
        """
        self.id_to_item.set(key=str(id), value=item)

    def get_item(self, id: int) -> Optional[dict]:
        """
        获取文件详情

        :param id: 文件 ID
        :return: 文件详情，如果不存在则返回 None
        """
        return self.id_to_item.get(str(id))

    def remove(self, id: int):
        """
        删除缓存

        :param id: 文件 ID
        """
        self.id_to_item.delete(key=str(id))

    def clear(self):
        """
        清空所有缓存
        """
        self.id_to_item.clear()
