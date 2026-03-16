from typing import Dict, List

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    select,
    delete,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ...db_manager import db_update, db_query, P115StrmHelperBase


class Folder(P115StrmHelperBase):
    """
    文件夹类
    """

    __tablename__ = "folders"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    path = Column(Text, nullable=False, unique=True)

    @staticmethod
    @db_query
    def get_by_path(db: Session, file_path: str):
        """
        通过路径获取（当路径不唯一报错 MultipleResultsFound）
        """
        return db.execute(
            select(Folder).where(Folder.path == file_path)
        ).scalar_one_or_none()

    @staticmethod
    @db_query
    def get_by_id(db: Session, file_id: int):
        """
        通过ID获取
        """
        return db.scalars(select(Folder).where(Folder.id == file_id)).first()

    @staticmethod
    @db_query
    def get_by_parent_id(db: Session, parent_id: int):
        """
        通过parent_id获取
        """
        return (
            db.execute(select(Folder).where(Folder.parent_id == parent_id))
            .scalars()
            .all()
        )

    @staticmethod
    @db_update
    def delete_by_path(db: Session, file_path: str):
        """
        通过路径删除（删除所有匹配值）
        """
        db.execute(delete(Folder).where(Folder.path == file_path))
        return True

    @staticmethod
    @db_update
    def delete_by_id(db: Session, file_id: int):
        """
        通过ID删除
        """
        db.execute(delete(Folder).where(Folder.id == file_id))
        return True

    @staticmethod
    @db_update
    def upsert_batch_by_list(db: Session, batch: List[Dict]):
        """
        通过列表批量写入或更新数据
        """
        stmt = sqlite_insert(Folder).prefix_with("OR REPLACE")
        db.execute(stmt, batch)
        return True

    @staticmethod
    @db_update
    def remove_by_path_batch(db: Session, path: str):
        """
        通过路径批量删除
        """
        db.execute(delete(Folder).where(Folder.path.startswith(path)))
        return True
