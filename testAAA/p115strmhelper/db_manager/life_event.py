from typing import List, Dict

from . import DbOper
from .models.life_event import LifeEvent


class LifeEventDbHelper(DbOper):
    """
    生活事件操作
    """

    def upsert_batch_by_list(self, batch: List[Dict]):
        """
        通过列表批量写入或更新数据
        """
        data = [
            {
                key: item[key]
                for key in [
                    "id",
                    "type",
                    "file_id",
                    "parent_id",
                    "file_name",
                    "file_category",
                    "file_type",
                    "file_size",
                    "sha1",
                    "pick_code",
                    "update_time",
                    "create_time",
                ]
            }
            for item in batch
        ]
        LifeEvent.upsert_batch_by_list(self._db, data)
