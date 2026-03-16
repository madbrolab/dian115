from typing import Literal, Set, List, Dict, Iterator

from . import DbOper
from .models.open_file import OpenFile
from .models.open_folder import OpenFolder


class OpenFileOper(DbOper):
    """
    Open 接口文件类数据库操作
    """

    def get_all_id(self, type: Literal["file", "folder"] = "file") -> Set[int]:
        """
        获取所有 ID

        :param type: 数据类型

        :return: ID 集合
        """
        if type == "file":
            return OpenFile.get_all_id(self._db)
        return OpenFolder.get_all_id(self._db)

    def upsert_batch(self, batch: List[Dict], type: Literal["file", "folder"] = "file"):
        """
        批量写入

        :param batch: 写入数据
        :param type: 数据类型
        """
        if type == "file":
            OpenFile.upsert_batch_by_list(self._db, batch)
        return OpenFolder.upsert_batch_by_list(self._db, batch)

    def get_parent_path_by_id(self, parent_id: int) -> str:
        """
        通过目录 ID 获取路径

        :param parent_id: 父目录 ID

        :return: 路径
        """
        return OpenFolder.get_by_id(self._db, parent_id).path

    def get_files_info_by_id(self, ids: Set[int]) -> Iterator[Dict]:
        """
        获取一组文件信息

        :param ids: 一组文件 ID

        :return: 迭代器，文件信息
        """
        for item in OpenFile.get_by_ids(self._db, ids):
            i = item.__dict__
            i.pop("_sa_instance_state", None)
            yield i
