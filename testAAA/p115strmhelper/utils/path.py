__all__ = ["PathUtils", "PathRemoveUtils"]


from pathlib import Path
from typing import Tuple, Optional, List
from shutil import rmtree

from app.log import logger
from app.utils.system import SystemUtils


class PathUtils:
    """
    路径匹配
    """

    @staticmethod
    def has_prefix(full_path, prefix_path) -> bool:
        """
        判断路径是否包含
        :param full_path: 完整路径
        :param prefix_path: 匹配路径
        """
        full = Path(full_path).parts
        prefix = Path(prefix_path).parts

        if len(prefix) > len(full):
            return False

        return full[: len(prefix)] == prefix

    @staticmethod
    def get_run_transfer_path(paths, transfer_path) -> bool:
        """
        判断路径是否为整理路径
        """
        transfer_paths = paths.split("\n")
        for path in transfer_paths:
            if not path:
                continue
            if PathUtils.has_prefix(transfer_path, path):
                return True
        return False

    @staticmethod
    def get_scrape_metadata_exclude_path(paths, scrape_path) -> bool:
        """
        检查目录是否在排除目录内
        """
        exclude_path = paths.split("\n")
        for path in exclude_path:
            if not path:
                continue
            if PathUtils.has_prefix(scrape_path, path):
                return True
        return False

    @staticmethod
    def get_media_path(paths, media_path) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        获取媒体目录路径
        """
        media_paths = paths.split("\n")
        for path in media_paths:
            if not path:
                continue
            parts = path.split("#", 2)
            if PathUtils.has_prefix(media_path, parts[1]):
                return True, parts[0], parts[1]
        return False, None, None

    @staticmethod
    def get_p115_strm_path(paths, media_path) -> Tuple[bool, Optional[str]]:
        """
        匹配全量目录，自动生成新的 paths
        """
        media_paths = paths.split("\n")
        for path in media_paths:
            if not path:
                continue
            parts = path.split("#", 2)
            if PathUtils.has_prefix(media_path, parts[1]):
                local_path = Path(parts[0]) / Path(media_path).relative_to(parts[1])
                final_paths = f"{local_path}#{media_path}"
                return True, final_paths
        return False, None

    @staticmethod
    def get_p115_media_path(
        media_path: str, p115_library_path: str
    ) -> Tuple[bool, Optional[List[str]]]:
        """
        获取 115 网盘媒体目录路径

        :param media_path: 媒体路径
        :param p115_library_path: 115 网盘媒体库路径映射（格式：媒体服务器STRM路径#MoviePilot路径# 115 网盘路径）
        :return: (是否匹配, 路径部分列表)
        """
        if not p115_library_path:
            return False, None
        media_paths = p115_library_path.split("\n")
        for path in media_paths:
            if not path:
                continue
            parts = path.split("#", 2)
            if PathUtils.has_prefix(media_path, parts[0]):
                return True, parts
        return False, None


class PathRemoveUtils:
    """
    目录删除工具
    """

    @staticmethod
    def remove_parent_dir(
        file_path: Path, mode: str | list = "all", func_type: str = None
    ):
        """
        删除父目录

        :param file_path: 文件夹路径
        :param mode: 删除模式，支持全部匹配和文件后缀匹配
        :param func_type: 日志输出函数名称
        """
        # 删除空目录
        # 判断当前媒体父路径下是否有媒体文件，如有则无需遍历父级
        if mode == "all":
            func_bool = any(file_path.parent.iterdir())
        else:
            func_bool = SystemUtils.exits_files(
                directory=file_path.parent, extensions=mode
            )
        if not func_bool:
            # 判断父目录是否为空, 为空则删除
            i = 0
            for parent_path in file_path.parents:
                i += 1
                if i > 3:
                    break
                if str(parent_path.parent) != str(file_path.root):
                    # 父目录非根目录，才删除父目录
                    if mode == "all":
                        func_bool = any(parent_path.iterdir())
                    else:
                        func_bool = SystemUtils.exits_files(
                            directory=parent_path, extensions=mode
                        )
                    if not func_bool:
                        # 当前路径下没有媒体文件则删除
                        rmtree(parent_path)
                        logger.warn(f"{func_type}本地空目录 {parent_path} 已删除")

    @staticmethod
    def clean_related_files(file_path: Path, func_type: str = None):
        """
        根据一个文件的路径，清理同一文件夹下文件名包含此文件名的其他文件。

        对于 .strm 后缀文件进行保护，不做删除操作

        :param file_path: 基准文件路径
        :param func_type: 日志输出函数名称
        """
        directory = file_path.parent
        file_stem = file_path.stem
        for item_to_check in directory.iterdir():
            if (
                item_to_check.is_file()
                and item_to_check != file_path
                and file_stem in item_to_check.stem
                and item_to_check.suffix.lower() != ".strm"
            ):
                logger.warn(f"{func_type}删除文件 {item_to_check}")
                item_to_check.unlink(missing_ok=True)
