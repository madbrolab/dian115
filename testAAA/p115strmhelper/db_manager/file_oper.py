from typing import Dict, Optional, List
from pathlib import Path

from . import DbOper
from .models.folder import Folder
from .models.file import File
from ..utils.exception import PathNotInKey

from app.schemas import FileItem


class FileDbHelper(DbOper):
    """
    文件类数据库操作
    """

    @staticmethod
    def process_item(item: Dict) -> List[Dict]:
        """
        处理单个项目，分离文件夹和文件数据
        """
        if not item.get("path"):
            raise PathNotInKey("键中不包含 path 项")

        results = []
        ancestors = item.get("ancestors", [])

        # 处理祖先文件夹
        for i, ancestor in enumerate(ancestors[1:-1], start=1):
            path = "/" + "/".join(a["name"] for a in ancestors[1 : i + 1])
            results.append(
                {
                    "table": "folders",
                    "data": {
                        "id": ancestor["id"],
                        "parent_id": ancestor["parent_id"],
                        "name": ancestor["name"],
                        "path": path,
                    },
                }
            )

        # 处理文件本身
        results.append(
            {
                "table": "files",
                "data": {
                    "id": item["id"],
                    "parent_id": item["parent_id"],
                    "name": item["name"],
                    "sha1": item.get("sha1", ""),
                    "size": item.get("size", 0),
                    "pickcode": item.get("pickcode", item.get("pick_code", "")),
                    "ctime": item.get("ctime", 0),
                    "mtime": item.get("mtime", 0),
                    "path": item.get("path"),
                    "extra": str(item) if item else None,
                },
            }
        )

        return results

    @staticmethod
    def process_life_file_item(event, file_path: str) -> List[Dict]:
        """
        处理115生活事件文件 event
        """
        return [
            {
                "table": "files",
                "data": {
                    "id": event["file_id"],
                    "parent_id": event["parent_id"],
                    "name": event["file_name"],
                    "sha1": event.get("sha1", ""),
                    "size": event.get("file_size", 0),
                    "pickcode": event.get("pick_code", ""),
                    "ctime": event.get("create_time", 0),
                    "mtime": event.get("update_time", 0),
                    "path": str(file_path),
                    "extra": str(event),
                },
            }
        ]

    @staticmethod
    def process_life_dir_item(event, file_path: str) -> List[Dict]:
        """
        处理115生活事件文件夹 event
        """
        return [
            {
                "table": "folders",
                "data": {
                    "id": event["file_id"],
                    "parent_id": event["parent_id"],
                    "name": event["file_name"],
                    "path": str(file_path),
                },
            }
        ]

    @staticmethod
    def process_fs_files_item(item) -> List[Dict]:
        """
        处理115原始返回数据
        """
        if not item.get("path"):
            raise PathNotInKey("键中不包含 path 项")

        if "fid" not in item:
            return [
                {
                    "table": "folders",
                    "data": {
                        "id": int(item.get("cid")),
                        "parent_id": int(item.get("pid")),
                        "name": item.get("n"),
                        "path": item.get("path"),
                    },
                }
            ]
        else:
            return [
                {
                    "table": "files",
                    "data": {
                        "id": int(item.get("fid")),
                        "parent_id": int(item.get("cid")),
                        "name": item.get("n"),
                        "sha1": item.get("sha"),
                        "size": item.get("s"),
                        "pickcode": item.get("pc"),
                        "ctime": item.get("tp", 0),
                        "mtime": item.get("tu", 0),
                        "path": item.get("path"),
                        "extra": str(item),
                    },
                }
            ]

    @staticmethod
    def process_fileitem(fileitem: Optional[FileItem]) -> List[Dict]:
        """
        处理MP fileitem 类型数据
        """
        if not fileitem:
            return []
        if fileitem.type == "file":
            return [
                {
                    "table": "files",
                    "data": {
                        "id": int(fileitem.fileid),
                        "parent_id": int(fileitem.parent_fileid)
                        if fileitem.parent_fileid is not None
                        else -1,
                        "name": fileitem.name,
                        "sha1": "",
                        "size": fileitem.size if fileitem.size is not None else -1,
                        "pickcode": fileitem.pickcode,
                        "ctime": 0,
                        "mtime": int(fileitem.modify_time),
                        "path": str(Path(fileitem.path)),
                        "extra": "",
                    },
                }
            ]
        else:
            return [
                {
                    "table": "folders",
                    "data": {
                        "id": int(fileitem.fileid),
                        "parent_id": int(fileitem.parent_fileid)
                        if fileitem.parent_fileid is not None
                        else -1,
                        "name": fileitem.name,
                        "path": str(Path(fileitem.path)),
                    },
                }
            ]

    def upsert_batch(self, batch: List[Dict]):
        """
        批量写入或更新数据
        """
        files_data_map = {
            entry["data"]["id"]: entry["data"]
            for entry in batch
            if entry.get("table") == "files" and "id" in entry.get("data", {})
        }

        if files_data_map:
            files_data = list(files_data_map.values())
            self.upsert_batch_by_list("files", files_data)

        folders_data_map = {
            entry["data"]["id"]: entry["data"]
            for entry in batch
            if entry.get("table") == "folders" and "id" in entry.get("data", {})
        }

        if folders_data_map:
            folders_data = list(folders_data_map.values())
            self.upsert_batch_by_list("folders", folders_data)

        return True

    def upsert_batch_by_list(self, list_type: str, batch: List[Dict]):
        """
        通过列表批量写入或更新数据
        """
        if list_type == "files":
            File.upsert_batch_by_list(self._db, batch)
        else:
            Folder.upsert_batch_by_list(self._db, batch)
        return True

    def get_by_path(self, path: str) -> Optional[Dict]:
        """
        通过路径获取项目
        """
        file = File.get_by_path(self._db, path)
        if file:
            return {
                **file.__dict__,
                "type": "file",
                "_sa_instance_state": None,
            }
        folder = Folder.get_by_path(self._db, path)
        if folder:
            return {**folder.__dict__, "type": "folder", "_sa_instance_state": None}
        return None

    def get_by_id(self, id: int) -> Optional[Dict]:
        """
        通过ID获取项目
        """
        file = File.get_by_id(self._db, id)
        if file:
            return {
                **file.__dict__,
                "type": "file",
                "_sa_instance_state": None,
            }
        folder = Folder.get_by_id(self._db, id)
        if folder:
            return {**folder.__dict__, "type": "folder", "_sa_instance_state": None}
        return None

    def get_children(self, path: str) -> Dict:
        """
        获取路径下的所有子项
        """
        parent = Folder.get_by_path(self._db, path)
        if not parent:
            return {"files": [], "subfolders": []}
        parent_id = parent.id

        files = File.get_by_parent_id(self._db, parent_id)
        subfolders = Folder.get_by_parent_id(self._db, parent_id)

        def clean_record(record):
            d = record.__dict__
            d.pop("_sa_instance_state", None)
            d["type"] = "file" if isinstance(record, File) else "folder"
            return d

        return {
            "files": [clean_record(f) for f in files],
            "subfolders": [clean_record(sf) for sf in subfolders],
            "meta": {
                "parent_path": path,
                "parent_id": parent_id,
                "total_count": len(files) + len(subfolders),
            },
        }

    def remove_by_path_batch(self, path: str, only_file: bool = False):
        """
        通过路径批量删除
        """
        File.remove_by_path_batch(self._db, path)
        if not only_file:
            Folder.remove_by_path_batch(self._db, path)
        return True

    def remove_by_id_batch(self, id: int, only_file: bool = False):
        """
        通过文件夹 ID 批量删除
        """
        folder = Folder.get_by_id(self._db, id)
        if not folder:
            return True
        path = folder.path
        File.remove_by_path_batch(self._db, path)
        if not only_file:
            Folder.remove_by_path_batch(self._db, path)
        return True

    def remove_by_path(self, path_type: str, path: str):
        """
        删除指定路径的记录
        """
        if path_type == "file":
            File.delete_by_path(self._db, path)
        else:
            Folder.delete_by_path(self._db, path)

    def remove_by_id(self, id_type: str, id: int):
        """
        通过 ID 删除记录
        """
        if id_type == "file":
            File.delete_by_id(self._db, id)
        else:
            Folder.delete_by_id(self._db, id)

    def update_path_by_id(self, id: int, new_path: str) -> bool:
        """
        通过ID匹配数据并修改path
        """
        item = self.get_by_id(id)
        if not item:
            return False

        if item["type"] == "file":
            File.update_path(self._db, id, new_path)
        else:
            return False

        return True

    def update_name_by_id(self, id: int, new_name: str) -> bool:
        """
        通过ID匹配数据并修改name
        """
        item = self.get_by_id(id)
        if not item:
            return False

        if item["type"] == "file":
            File.update_name(self._db, id, new_name)
        else:
            return False

        return True

    def get_any_pickcode(self) -> Optional[str]:
        """
        从文件表中任意获取一条 pickcode 不为空的数据的 pickcode

        :return: pickcode
        """
        pickcode = File.get_any_pickcode(self._db)
        if pickcode:
            return pickcode

        return None
