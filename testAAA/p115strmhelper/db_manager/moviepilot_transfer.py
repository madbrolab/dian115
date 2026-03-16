from typing import List

from jieba import cut as jieba_cut

from app.db import DbOper
from app.db.models.transferhistory import TransferHistory


class TransferHBOper(DbOper):
    """
    历史记录数据库操作扩展
    """

    def get_transfer_his_by_path_title(self, path: str) -> List[TransferHistory]:
        """
        通过路径查询转移记录
        所有匹配项

        :param path: 查询路径

        :return List: 数据列表
        """
        words = jieba_cut(path, HMM=False)
        title = "%".join(words)
        total = TransferHistory.count_by_title(self._db, title=title)
        result = TransferHistory.list_by_title(
            self._db, title=title, page=1, count=total
        )
        return result
