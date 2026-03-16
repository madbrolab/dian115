__all__ = ["DirectoryTree"]

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable, Generator, Union, List

from app.core.config import settings
from app.helper.redis import RedisHelper


class DirectoryTreeStorage(ABC):
    """
    目录树存储策略的抽象基类
    """

    @abstractmethod
    def add_paths(self, paths: Iterable[str], append: bool = False):
        """
        从一个迭代器添加多个路径
        """
        pass

    @abstractmethod
    def compare_trees(
        self, other_storage: "DirectoryTreeStorage"
    ) -> Generator[str, None, None]:
        """
        比较两个树，返回 self 中存在而 other 中不存在的路径
        """
        pass

    @abstractmethod
    def compare_trees_lines(
        self, other_storage: "DirectoryTreeStorage"
    ) -> Generator[int, None, None]:
        """
        比较两个树，返回差异路径在 self 中的行号
        """
        pass

    @abstractmethod
    def get_path_by_line_number(self, line_number: int) -> Union[str, None]:
        """
        根据行号获取路径
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """
        返回树中的有效条目总数
        """
        pass

    @abstractmethod
    def clear(self):
        """
        清理目录树
        """
        pass


class TxtFileStorage(DirectoryTreeStorage):
    """
    使用 TXT 文件作为后端的存储策略
    """

    def __init__(self, file_path: Union[str, Path]):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def add_paths(self, paths: Iterable[str], append: bool = False):
        mode = "a" if append else "w"
        buffer_size = 1048576
        with open(self.file_path, mode, encoding="utf-8", buffering=buffer_size) as f:
            f.writelines(f"{path}\n" for path in paths)

    def compare_trees(
        self, other_storage: "DirectoryTreeStorage"
    ) -> Generator[str, None, None]:
        if not isinstance(other_storage, TxtFileStorage):
            raise TypeError("TxtFileStorage 只能与同类型的树进行比较")

        try:
            with open(other_storage.file_path, "r", encoding="utf-8") as f2:
                tree2_set = set(line.strip() for line in f2)
        except FileNotFoundError:
            tree2_set = set()

        with open(self.file_path, "r", encoding="utf-8") as f1:
            for line in f1:
                file_path = line.strip()
                if file_path not in tree2_set:
                    yield file_path

    def compare_trees_lines(
        self, other_storage: "DirectoryTreeStorage"
    ) -> Generator[int, None, None]:
        if not isinstance(other_storage, TxtFileStorage):
            raise TypeError("TxtFileStorage 只能与同类型的树进行比较")

        try:
            with open(other_storage.file_path, "r", encoding="utf-8") as f2:
                tree2_set = set(line.strip() for line in f2)
        except FileNotFoundError:
            tree2_set = set()

        with open(self.file_path, "r", encoding="utf-8") as f1:
            for line_num, line in enumerate(f1, start=1):
                file_path = line.strip()
                if file_path not in tree2_set:
                    yield line_num

    def get_path_by_line_number(self, line_number: int) -> Union[str, None]:
        if line_number <= 0:
            return None
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if i == line_number:
                        return line.strip()
        except FileNotFoundError:
            return None
        return None

    def count(self) -> int:
        count = 0
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        count += 1
        except FileNotFoundError:
            return 0
        return count

    def clear(self):
        if self.file_path.exists():
            self.file_path.unlink()


class RedisStorage(DirectoryTreeStorage):
    """
    使用 Redis 作为后端的存储策略
    """

    def __init__(self, tree_name: str):
        self.tree_name = tree_name

        self.redis_helper = RedisHelper()
        self.redis_helper._connect()  # noqa
        self.client = self.redis_helper.client

        self._set_key = f"dirtree:set:{tree_name}"
        self._list_key = f"dirtree:list:{tree_name}"

    def add_paths(self, paths: Iterable[str], append: bool = False):
        pipe = self.client.pipeline()

        if not append:
            pipe.delete(self._set_key, self._list_key)

        chunk_size, path_chunk = 5000, []
        for path in paths:
            if path:
                path_chunk.append(path)
            if len(path_chunk) >= chunk_size:
                pipe.sadd(self._set_key, *path_chunk)
                pipe.rpush(self._list_key, *path_chunk)
                path_chunk = []

        if path_chunk:
            pipe.sadd(self._set_key, *path_chunk)
            pipe.rpush(self._list_key, *path_chunk)

        pipe.execute()

    def compare_trees(
        self, other_storage: "DirectoryTreeStorage"
    ) -> Generator[str, None, None]:
        if not isinstance(other_storage, RedisStorage):
            raise TypeError("RedisStorage 只能与同类型的树进行高性能比较")

        diff_bytes = self.client.sdiff(self._set_key, other_storage._set_key)
        for b_path in diff_bytes:
            yield b_path.decode("utf-8")

    def compare_trees_lines(
        self, other_storage: "DirectoryTreeStorage"
    ) -> Generator[int, None, None]:
        if not isinstance(other_storage, RedisStorage):
            raise TypeError("RedisStorage 只能与同类型的树进行高性能比较")

        chunk_size, line_num = 5000, 0
        while True:
            paths_chunk_bytes = self.client.lrange(
                self._list_key, line_num, line_num + chunk_size - 1
            )
            if not paths_chunk_bytes:
                break

            for path_bytes in paths_chunk_bytes:
                line_num += 1
                if not self.client.sismember(other_storage._set_key, path_bytes):
                    yield line_num

    def get_path_by_line_number(self, line_number: int) -> Union[str, None]:
        if line_number <= 0:
            return None
        path_bytes = self.client.lindex(self._list_key, line_number - 1)
        return path_bytes.decode("utf-8") if path_bytes else None

    def count(self) -> int:
        return self.client.scard(self._set_key)

    def clear(self):
        self.client.delete(self._set_key, self._list_key)


class DirectoryTree:
    """
    目录树操作的高级接口，支持 TXT 和 Redis 后端
    """

    def __init__(self, file_path: Path):
        """
        初始化目录树实例。
        """
        if settings.CACHE_BACKEND_TYPE == "redis":
            self._storage: DirectoryTreeStorage = RedisStorage(file_path.stem)
        else:
            self._storage: DirectoryTreeStorage = TxtFileStorage(file_path)

    def scan_directory_to_tree(
        self, root_path, append=False, extensions=None, use_posix=True
    ):
        """
        扫描本地目录生成目录树，可过滤后缀
        """
        root = Path(root_path).resolve()
        if extensions:
            extensions = {f".{ext.lower().lstrip('.')}" for ext in extensions}

        def path_generator():
            for path in root.rglob("*"):
                if path.is_file() and (
                    extensions is None or path.suffix.lower() in extensions
                ):
                    yield path.as_posix() if use_posix else str(path)

        self._storage.add_paths(path_generator(), append=append)

    def generate_tree_from_list(self, file_list: List[str], append=False):
        """
        从文件列表生成目录树
        """
        self._storage.add_paths(file_list, append=append)

    def compare_trees(self, other_tree: "DirectoryTree") -> Generator[str, None, None]:
        """
        比较两个目录树，找出本树有而另一颗树没有的文件
        """
        yield from self._storage.compare_trees(other_tree._storage)

    def compare_trees_lines(
        self, other_tree: "DirectoryTree"
    ) -> Generator[int, None, None]:
        """
        比较两个目录树，返回差异文件在本树中的行号
        """
        yield from self._storage.compare_trees_lines(other_tree._storage)

    def get_path_by_line_number(self, line_number: int) -> Union[str, None]:
        """
        通过行号获取路径
        """
        return self._storage.get_path_by_line_number(line_number)

    def count(self) -> int:
        """
        获取此目录树中的有效条目总数
        """
        return self._storage.count()

    def compare_entry_counts(self, other_tree: "DirectoryTree") -> int:
        """
        对比两个目录树的有效条目总数。

        :param other_tree: 要比较的另一个 DirectoryTree 实例
        :return: int 两个树条目数量的差值绝对值
        """
        return abs(self.count() - other_tree.count())

    def clear(self):
        """
        清除此目录树的所有内容。
        - 对于 TXT 后端，会清空文件
        - 对于 Redis 后端，会删除相关的键
        """
        self._storage.clear()
