from typing import Set, List, Dict

from sqlalchemy import Column, Integer, String, BigInteger, Text, select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ...db_manager import P115StrmHelperBase, db_query, db_update


class OpenFile(P115StrmHelperBase):
    """
    Open 文件类
    """

    __tablename__ = "open_files"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, nullable=False)
    name = Column(String(255), default="")
    sha1 = Column(String(40), default="")
    size = Column(BigInteger, default=0)
    pick_code = Column(String(50), default="")
    ico = Column(String(40), default="")
    ctime = Column(BigInteger, default=0)
    mtime = Column(BigInteger, default=0)
    utime = Column(BigInteger, default=0)
    file_type = Column(BigInteger, default=0)
    type = Column(BigInteger, default=0)
    path = Column(Text, unique=True)
    local_path = Column(Text, default="")

    @staticmethod
    @db_query
    def get_all_id(db: Session) -> Set[int]:
        """
        获取所有 ID

        :return: ID 集合
        """
        stmt = select(OpenFile.id)
        return set(db.scalars(stmt).all())

    @staticmethod
    @db_update
    def upsert_batch_by_list(db: Session, batch: List[Dict]):
        """
        通过列表批量写入或更新数据
        """
        stmt = sqlite_insert(OpenFile).prefix_with("OR REPLACE")
        db.execute(stmt, batch)

    @staticmethod
    @db_query
    def get_by_ids(db: Session, ids: Set[int]) -> List["OpenFile"] | None:
        """
        通过一组 ID 获取一组文件信息
        """
        if not ids:
            return []
        stmt = select(OpenFile).where(OpenFile.id.in_(ids))
        return list(db.scalars(stmt).all())
