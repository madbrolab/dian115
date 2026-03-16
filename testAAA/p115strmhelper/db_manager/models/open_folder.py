from typing import Set, List, Dict

from sqlalchemy import Column, Integer, String, Text, select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ...db_manager import P115StrmHelperBase, db_query, db_update


class OpenFolder(P115StrmHelperBase):
    """
    Open 文件夹类
    """

    __tablename__ = "open_folders"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, nullable=False)
    name = Column(String(255), default="")
    path = Column(Text, unique=True)

    @staticmethod
    @db_query
    def get_all_id(db: Session) -> Set[int]:
        """
        获取所有 ID

        :return: ID 集合
        """
        stmt = select(OpenFolder.id)
        return set(db.scalars(stmt).all())

    @staticmethod
    @db_update
    def upsert_batch_by_list(db: Session, batch: List[Dict]):
        """
        通过列表批量写入或更新数据
        """
        stmt = sqlite_insert(OpenFolder).prefix_with("OR REPLACE")
        db.execute(stmt, batch)

    @staticmethod
    @db_query
    def get_by_id(db: Session, folder_id: int):
        """
        通过ID获取
        """
        return db.scalars(select(OpenFolder).where(OpenFolder.id == folder_id)).first()
