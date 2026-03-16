from typing import List, Dict

from sqlalchemy import Column, Integer, String, BigInteger, select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ...db_manager import db_update, db_query, P115StrmHelperBase


class LifeEvent(P115StrmHelperBase):
    """
    生活事件表
    """

    __tablename__ = "life_event"

    id = Column(Integer, primary_key=True)
    type = Column(Integer, nullable=False, index=True)
    file_id = Column(Integer, nullable=False, index=True)
    parent_id = Column(Integer, nullable=False, index=True)
    file_name = Column(String(255), default="")
    file_category = Column(Integer, nullable=False)
    file_type = Column(Integer, nullable=False, index=True)
    file_size = Column(BigInteger, default=0)
    sha1 = Column(String(40), default="")
    pick_code = Column(String(50), default="")
    update_time = Column(BigInteger, default=0)
    create_time = Column(BigInteger, default=0)

    @staticmethod
    @db_update
    def upsert_batch_by_list(db: Session, batch: List[Dict]):
        """
        通过列表批量写入或更新数据
        """
        stmt = sqlite_insert(LifeEvent).prefix_with("OR REPLACE")
        db.execute(stmt, batch)
        return True

    @staticmethod
    @db_query
    def get_by_id(db: Session, file_id: int):
        """
        通过ID获取
        """
        return db.scalars(select(LifeEvent).where(LifeEvent.id == file_id)).first()

    @staticmethod
    @db_query
    def get_by_file_id(db: Session, file_id: int):
        """
        通过 file_id 获取
        """
        return db.scalars(select(LifeEvent).where(LifeEvent.file_id == file_id)).all()

    @staticmethod
    @db_query
    def get_by_type(db: Session, type_id: int):
        """
        通过 type 获取
        """
        return db.scalars(select(LifeEvent).where(LifeEvent.type == type_id)).all()
