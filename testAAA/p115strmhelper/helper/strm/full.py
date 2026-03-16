from collections import namedtuple
from concurrent.futures import as_completed, ThreadPoolExecutor
from itertools import batched
from pathlib import Path
from os import makedirs
from queue import Empty, Queue
from threading import Thread
from time import perf_counter, sleep
from typing import List, Dict, Optional, Set, Tuple

from orjson import dumps
from p115client import P115Client
from p115client.tool.iterdir import (
    iter_files_with_path,
    iter_files_with_path_skim,
)

from app.core.config import settings
from app.log import logger

from full_strm_sync import Processor, PackedResult
from full_strm_sync import __version__ as rust_core_version

from ...core.config import configer
from ...core.p115 import get_pid_by_path
from ...db_manager.oper import FileDbHelper
from ...helper.mediainfo_download import MediaInfoDownloader
from ...utils.automaton import AutomatonUtils
from ...utils.exception import (
    FileItemKeyMiss,
)
from ...utils.mediainfo_download import MediainfoDownloadMiddleware
from ...utils.path import PathUtils, PathRemoveUtils
from ...utils.sentry import sentry_manager
from ...utils.strm import StrmUrlGetter, StrmGenerater
from ...utils.tree import DirectoryTree
from ...utils.http import check_iter_path_data
from ...utils.base64 import CBase64
from ...utils.math import MathUtils
from ...helper.mediaserver import MediaServerRefresh


ProcessResult = namedtuple(
    "ProcessResult", ["status", "path", "message", "data", "path_entry"]
)


class FullSyncStrmHelper:
    """
    全量生成 STRM 文件
    """

    def __init__(
        self,
        client: P115Client,
        mediainfodownloader: MediaInfoDownloader,
    ):
        self.rmt_mediaext_set = {
            f".{ext.strip()}"
            for ext in configer.user_rmt_mediaext.replace("，", ",").split(",")
        }
        self.download_mediaext_set = {
            f".{ext.strip()}"
            for ext in configer.user_download_mediaext.replace("，", ",").split(",")
        }
        self.auto_download_mediainfo = (
            configer.full_sync_auto_download_mediainfo_enabled
        )
        self.client = client
        self.mediainfodownloader = mediainfodownloader
        self.total_count = 0
        self.elapsed_time = 0
        self.total_db_write_count = 0
        self.strm_count = 0
        self.mediainfo_count = 0
        self.strm_fail_count = 0
        self.mediainfo_fail_count = 0
        self.remove_unless_strm_count = 0
        self.strm_fail_dict: Dict[str, str] = {}
        self.mediainfo_fail_dict: List = []
        self.pan_transfer_enabled = configer.pan_transfer_enabled
        self.pan_transfer_paths = configer.pan_transfer_paths
        self.overwrite_mode = configer.full_sync_overwrite_mode
        self.remove_unless_strm = configer.full_sync_remove_unless_strm
        self.databasehelper = FileDbHelper()
        self.download_mediainfo_list = []

        self.mediaserver_helper = MediaServerRefresh(
            func_name="【全量STRM生成】",
            enabled=configer.full_sync_media_server_refresh_enabled,
            mediaservers=configer.full_sync_mediaservers,
        )

        self.strmurlgetter = StrmUrlGetter()
        self.sgab = AutomatonUtils.build_automaton(configer.strm_generate_blacklist)
        self.mdaw = AutomatonUtils.build_automaton(
            configer.mediainfo_download_whitelist
        )
        self.mdab = AutomatonUtils.build_automaton(
            configer.mediainfo_download_blacklist
        )

        self.write_queue = Queue(maxsize=4096)
        self.result_queue = Queue()

        self.local_tree_path = configer.PLUGIN_TEMP_PATH / "local_tree.txt"
        self.pan_tree_path = configer.PLUGIN_TEMP_PATH / "pan_tree.txt"
        self.local_tree = DirectoryTree(self.local_tree_path)
        self.pan_tree = DirectoryTree(self.pan_tree_path)

        if configer.full_sync_strm_log:
            self.__base_logger = self.__base_has_logger
        else:
            self.__base_logger = self.__base_no_logger

    def __del__(self):
        self._clean_tree()

    def _clean_tree(self):
        """
        清理目录树文件
        """
        self.local_tree.clear()
        self.pan_tree.clear()

    @staticmethod
    def __base_no_logger(level, msg, *args):
        """
        空白日志输出器
        """
        pass

    @staticmethod
    def __base_has_logger(level, msg, *args):
        """
        由配置控制的日志输出器
        """
        log_method = getattr(logger, level)
        log_method(msg, *args)

    def __get_remove_unless_strm(self, path_base64: str) -> Dict:
        """
        获取删除信息

        :param path_base64: 路径 base64 信息

        :return: 数据字典
        """
        data: dict = configer.get_plugin_data("full_remove_unless_strm")
        if data:
            return data.get(path_base64, {})
        return {}

    def __save_remove_unless_strm(self, path_base64: str, value: Dict):
        """
        保存删除信息

        :param path_base64: 路径 base64 信息
        :param value: 保存字典
        """
        data: Dict | None = configer.get_plugin_data("full_remove_unless_strm")
        if data:
            data[path_base64] = value
        else:
            data = {path_base64: value}
        configer.save_plugin_data("full_remove_unless_strm", data)

    def __remove_unless_strm_local(self, target_dir: str) -> Thread:
        """
        清理无效 STRM 本地扫描

        :param target_dir: 扫描路径

        :return: 扫描进程
        """
        self._clean_tree()

        def background_task(_target_dir):
            """
            后台运行任务
            """
            logger.info(f"【全量STRM生成】开始扫描本地媒体库文件: {_target_dir}")
            try:
                self.local_tree.scan_directory_to_tree(
                    root_path=_target_dir,
                    append=False,
                    extensions=[".strm"],
                )
                logger.info(f"【全量STRM生成】扫描本地媒体库文件完成: {_target_dir}")
            except Exception as e:
                logger.error(
                    f"【全量STRM生成】扫描本地媒体库文件 {_target_dir} 错误: {e}"
                )

        local_tree_task_thread = Thread(
            target=background_task,
            args=(target_dir,),
        )
        local_tree_task_thread.start()

        return local_tree_task_thread

    def __process_db_item(
        self, batch, seen_folder_ids: Set[str], seen_file_ids: Set[str]
    ) -> Tuple[Set[str], Set[str]]:
        """
        处理写入数据库的内容
        """
        files_list: List = []
        folders_list: List = []

        for item in batch:
            ancestors = item.get("ancestors", [])
            path_parts = []
            for ancestor in ancestors[1:-1]:
                path_parts.append(ancestor["name"])
                path = "/" + "/".join(path_parts)
                ancestor_id = str(ancestor["id"])
                if ancestor_id not in seen_folder_ids:
                    folders_list.append(
                        {
                            "id": ancestor["id"],
                            "parent_id": ancestor["parent_id"],
                            "name": ancestor["name"],
                            "path": path,
                        }
                    )
                    seen_folder_ids.add(ancestor_id)
            file_id = str(item["id"])
            if file_id not in seen_file_ids:
                files_list.append(
                    {
                        "id": item["id"],
                        "parent_id": item["parent_id"],
                        "name": item["name"],
                        "sha1": item.get("sha1", ""),
                        "size": item.get("size", 0),
                        "pickcode": item.get("pickcode", item.get("pick_code", "")),
                        "ctime": item.get("ctime", 0),
                        "mtime": item.get("mtime", 0),
                        "path": item.get("path", ""),
                        "extra": dumps(item).decode("utf-8") if item else None,
                    }
                )
                seen_file_ids.add(file_id)

        if files_list:
            self.databasehelper.upsert_batch_by_list("files", files_list)
        if folders_list:
            self.databasehelper.upsert_batch_by_list("folders", folders_list)

        return seen_folder_ids, seen_file_ids

    def __io_writer_worker(self):
        """
        写入 STRM 文件操作
        """
        buffer_size = 64

        while True:
            tasks: List[Tuple[Path, str, str]] = []
            task_done_handled = False
            try:
                first_task = self.write_queue.get()
                if first_task is None:
                    self.result_queue.put(None)
                    self.write_queue.task_done()
                    break
                tasks.append(first_task)

                while len(tasks) < buffer_size:
                    try:
                        extra_task = self.write_queue.get_nowait()
                        if extra_task is None:
                            self.__flush_write_buffer(tasks)
                            for _ in tasks:
                                self.write_queue.task_done()
                            self.result_queue.put(None)
                            self.write_queue.task_done()
                            task_done_handled = True
                            return
                        tasks.append(extra_task)
                    except Empty:
                        break
                self.__flush_write_buffer(tasks)
            finally:
                if not task_done_handled:
                    for _ in tasks:
                        self.write_queue.task_done()

    def __flush_write_buffer(self, tasks: List[Tuple[Path, str, str]]):
        """
        批量处理写入任务
        """
        for new_file_path, strm_url, original_file_name in tasks:
            try:
                with open(new_file_path, "w", encoding="utf-8") as file:
                    file.write(strm_url)

                self.result_queue.put(
                    ProcessResult(
                        status="success",
                        path=str(new_file_path),
                        message=None,
                        data=None,
                        path_entry=None,
                    )
                )
            except FileNotFoundError:
                try:
                    makedirs(new_file_path.parent, exist_ok=True)
                    with open(new_file_path, "w", encoding="utf-8") as file:
                        file.write(strm_url)

                    self.result_queue.put(
                        ProcessResult(
                            status="success",
                            path=str(new_file_path),
                            message=None,
                            data=None,
                            path_entry=None,
                        )
                    )
                except Exception as e:
                    sentry_manager.sentry_hub.capture_exception(e)
                    logger.error(
                        "【全量STRM生成】写入 STRM 文件失败: %s  %s",
                        str(new_file_path),
                        e,
                    )
                    self.result_queue.put(
                        ProcessResult(
                            status="fail",
                            path=str(new_file_path),
                            message=str(e),
                            data=None,
                            path_entry=None,
                        )
                    )
            except Exception as e:
                sentry_manager.sentry_hub.capture_exception(e)
                logger.error(
                    "【全量STRM生成】写入 STRM 文件失败: %s  %s",
                    str(new_file_path),
                    e,
                )
                self.result_queue.put(
                    ProcessResult(
                        status="fail",
                        path=str(new_file_path),
                        message=str(e),
                        data=None,
                        path_entry=None,
                    )
                )

    def __process_single_item(
        self, item: Dict, target_dir: Path, pan_media_dir: str
    ) -> Optional[ProcessResult]:
        """
        处理单个项目
        """
        path_entry = None
        try:
            # 判断是否有信息缺失
            check_iter_path_data(item)
            # 判断是否为文件夹
            if item["is_dir"]:
                return None
            item_path = item["path"]
            # 全量拉数据时可能混入无关路径
            if not PathUtils.has_prefix(item_path, pan_media_dir):
                return None
            file_path = target_dir / Path(item_path).relative_to(pan_media_dir)
            file_target_dir = file_path.parent
            original_file_name = file_path.name
            file_name = StrmGenerater.get_strm_filename(file_path)
            new_file_path = file_target_dir / file_name
        except FileItemKeyMiss as e:
            logger.error(
                "【全量STRM生成】生成 STRM 文件失败: %s  %s",
                str(item),
                e,
            )
            return ProcessResult(
                status="fail",
                path=str(item),
                message=str(e),
                data=None,
                path_entry=None,
            )
        except Exception as e:
            sentry_manager.sentry_hub.capture_exception(e)
            logger.error(
                "【全量STRM生成】生成 STRM 文件失败: %s  %s",
                str(item),
                e,
            )
            return ProcessResult(
                status="fail",
                path=str(item),
                message=str(e),
                data=None,
                path_entry=None,
            )

        try:
            if self.pan_transfer_enabled and self.pan_transfer_paths:
                if PathUtils.get_run_transfer_path(
                    paths=self.pan_transfer_paths,
                    transfer_path=item_path,
                ):
                    logger.debug(
                        "【全量STRM生成】%s 为待整理目录下的路径，不做处理",
                        item_path,
                    )
                    return None

            if self.auto_download_mediainfo:
                if file_path.suffix.lower() in self.download_mediaext_set:
                    if file_path.exists():
                        if self.overwrite_mode == "never":
                            self.__base_logger(
                                "warn",
                                "【全量STRM生成】%s 已存在，覆盖模式 %s，跳过此路径",
                                new_file_path,
                                self.overwrite_mode,
                            )
                            return ProcessResult(
                                status="skip",
                                path=None,
                                message=None,
                                data=None,
                                path_entry=path_entry,
                            )
                        else:
                            self.__base_logger(
                                "warn",
                                "【全量STRM生成】%s 已存在，覆盖模式 %s",
                                new_file_path,
                                self.overwrite_mode,
                            )

                    if not (
                        result := MediainfoDownloadMiddleware.should_download(
                            filename=file_path.name,
                            blacklist_automaton=self.mdab,
                            whitelist_automaton=self.mdaw,
                        )
                    )[1]:
                        self.__base_logger(
                            "warn",
                            "【全量STRM生成】%s，跳过网盘路径: %s",
                            result[0],
                            item_path,
                        )
                        return ProcessResult(
                            status="skip",
                            path=None,
                            message=None,
                            data=None,
                            path_entry=path_entry,
                        )

                    pickcode = item.get("pickcode", item.get("pick_code", None))
                    if not pickcode:
                        logger.error(
                            f"【全量STRM生成】{original_file_name} 不存在 pickcode 值，无法下载该文件"
                        )
                        return ProcessResult(
                            status="fail",
                            path=original_file_name,
                            message="不存在 pickcode 值，无法下载",
                            data=None,
                            path_entry=None,
                        )

                    download_info = {
                        "type": "local",
                        "pickcode": pickcode,
                        "path": file_path,
                        "sha1": item["sha1"],
                    }
                    return ProcessResult(
                        status="download",
                        path=None,
                        message=None,
                        data=download_info,
                        path_entry=None,
                    )

            if file_path.suffix.lower() not in self.rmt_mediaext_set:
                self.__base_logger(
                    "warn",
                    "【全量STRM生成】跳过网盘路径: %s",
                    item_path,
                )
                return ProcessResult(
                    status="skip",
                    path=None,
                    message=None,
                    data=None,
                    path_entry=path_entry,
                )

            if not (
                result := StrmGenerater.should_generate_strm(
                    filename=original_file_name,
                    mode="full",
                    filesize=item.get("size", None),
                    blacklist_automaton=self.sgab,
                )
            )[1]:
                self.__base_logger(
                    "warn",
                    "【全量STRM生成】%s，跳过网盘路径: %s",
                    result[0],
                    item_path,
                )
                return ProcessResult(
                    status="skip",
                    path=None,
                    message=None,
                    data=None,
                    path_entry=path_entry,
                )

            if self.remove_unless_strm:
                path_entry = str(new_file_path)

            if new_file_path.exists():
                if self.overwrite_mode == "never":
                    self.__base_logger(
                        "warn",
                        f"【全量STRM生成】{new_file_path} 已存在，覆盖模式 {self.overwrite_mode}，跳过此路径",
                    )
                    return ProcessResult(
                        status="skip",
                        path=None,
                        message=None,
                        data=None,
                        path_entry=path_entry,
                    )
                else:
                    self.__base_logger(
                        "warn",
                        f"【全量STRM生成】{new_file_path} 已存在，覆盖模式 {self.overwrite_mode}",
                    )

            pickcode = item.get("pickcode", item.get("pick_code", ""))

            if not pickcode:
                logger.error(
                    f"【全量STRM生成】{original_file_name} 不存在 pickcode 值，无法生成 STRM 文件"
                )
                return ProcessResult(
                    status="fail",
                    path=str(new_file_path),
                    message="不存在 pickcode 值",
                    data=None,
                    path_entry=path_entry,
                )
            if not (len(pickcode) == 17 and str(pickcode).isalnum()):
                logger.error(
                    f"【全量STRM生成】错误的 pickcode 值 {pickcode}，无法生成 STRM 文件"
                )
                return ProcessResult(
                    status="fail",
                    path=str(new_file_path),
                    message=f"错误的 pickcode 值 {pickcode}",
                    data=None,
                    path_entry=path_entry,
                )

            strm_url = self.strmurlgetter.get_strm_url(
                pickcode, original_file_name, item.get("path")
            )
            self.write_queue.put((new_file_path, strm_url, original_file_name))

            return ProcessResult(
                status="submitted",
                path=None,
                message=None,
                data=None,
                path_entry=path_entry,
            )
        except Exception as e:
            sentry_manager.sentry_hub.capture_exception(e)
            logger.error(
                "【全量STRM生成】生成 STRM 文件失败: %s  %s",
                str(new_file_path),
                e,
            )
            return ProcessResult(
                status="fail",
                path=item_path,
                message=str(e),
                data=None,
                path_entry=path_entry,
            )

    def generate_database(self, full_sync_strm_paths):
        """
        全量更新数据库
        """
        media_paths = full_sync_strm_paths.split("\n")
        for path in media_paths:
            if not path:
                continue
            parts = path.split("#", 2)
            if len(parts) >= 3 and str(parts[2]).strip() == "0":
                continue
            pan_media_dir = parts[1]

            try:
                parent_id = get_pid_by_path(
                    self.client, pan_media_dir, True, False, False
                )
                logger.info(
                    f"【全量STRM生成】网盘媒体目录 ID 获取成功: {pan_media_dir} {parent_id}"
                )
            except Exception as e:
                sentry_manager.sentry_hub.capture_exception(e)
                logger.error(
                    f"【全量STRM生成】网盘媒体目录 ID 获取失败: {pan_media_dir} {e}"
                )
                return False

            try:
                if (
                    configer.get_config("full_sync_iter_function")
                    == "iter_files_with_path_skim"
                ):
                    iter_func = iter_files_with_path_skim
                    iter_kwargs = {
                        "cid": parent_id,
                        "with_ancestors": True,
                        **configer.get_ios_ua_app(),
                    }
                else:
                    iter_func = iter_files_with_path
                    iter_kwargs = {
                        "cid": parent_id,
                        "with_ancestors": True,
                        "cooldown": 1.5,
                        **configer.get_ios_ua_app(),
                    }
                logger.debug(
                    f"【全量STRM生成】迭代函数 {iter_func}; 参数 {iter_kwargs}"
                )
                start_time = perf_counter()
                seen_folder_ids: Set[str] = set()
                seen_file_ids: Set[str] = set()
                for batch in batched(
                    iter_func(self.client, **iter_kwargs),
                    int(configer.get_config("full_sync_batch_num")),
                ):
                    seen_folder_ids, seen_file_ids = self.__process_db_item(
                        batch,
                        seen_folder_ids,
                        seen_file_ids,
                    )
                end_time = perf_counter()
                self.elapsed_time += end_time - start_time
                self.total_db_write_count += len(seen_file_ids) + len(seen_folder_ids)
            except Exception as e:
                sentry_manager.sentry_hub.capture_exception(e)
                logger.error(
                    f"【全量STRM生成】全量更新数据库失败: {pan_media_dir} {e}",
                    exc_info=True,
                )
                return False

        logger.info(
            f"【全量STRM生成】全量更新数据库完成，时间 {self.elapsed_time:.6f} 秒，数据库写入量 {self.total_db_write_count} 条"
        )

    def generate_strm_files(self, full_sync_strm_paths):
        """
        生成 STRM 文件
        """
        rust = configer.full_sync_process_rust
        media_paths = full_sync_strm_paths.split("\n")

        num_io_workers = 8
        io_threads = []
        for _ in range(num_io_workers):
            thread = Thread(target=self.__io_writer_worker)
            thread.daemon = True
            thread.start()
            io_threads.append(thread)

        def result_collector():
            finished_workers = 0
            while finished_workers < num_io_workers:
                try:
                    result = self.result_queue.get()
                    if result is None:
                        finished_workers += 1
                        continue
                    if result.status == "success":
                        self.strm_count += 1
                    elif result.status == "fail":
                        self.strm_fail_count += 1
                        self.strm_fail_dict[result.path] = result.message
                finally:
                    self.result_queue.task_done()

        collector_thread = Thread(target=result_collector)
        collector_thread.daemon = True
        collector_thread.start()

        with ThreadPoolExecutor(
            max_workers=int(configer.full_sync_process_num)
        ) as executor:
            for path in media_paths:
                if not path:
                    continue
                parts = path.split("#", 2)
                if len(parts) >= 3 and str(parts[2]).strip() == "0":
                    continue
                path_base64 = CBase64.encode(str(path).encode("utf-8"))
                pan_media_dir = parts[1]
                target_dir = parts[0]

                if self.remove_unless_strm:
                    local_tree_task_thread = self.__remove_unless_strm_local(target_dir)

                if rust:
                    config_for_rust = {
                        "pan_transfer_enabled": self.pan_transfer_enabled,
                        "pan_transfer_paths": self.pan_transfer_paths.split("\n")
                        if self.pan_transfer_paths
                        else [],
                        "auto_download_mediainfo": self.auto_download_mediainfo,
                        "rmt_mediaext_set": list(self.rmt_mediaext_set),
                        "download_mediaext_set": list(self.download_mediaext_set),
                        "strm_generate_blacklist": configer.strm_generate_blacklist
                        or [],
                        "mediainfo_download_whitelist": configer.mediainfo_download_whitelist
                        or [],
                        "mediainfo_download_blacklist": configer.mediainfo_download_blacklist
                        or [],
                        "full_sync_min_file_size": configer.full_sync_min_file_size
                        or 0,
                        "pan_media_dir": pan_media_dir,
                    }
                    config_json = dumps(config_for_rust).decode("utf-8")

                    try:
                        processor = Processor(config_json)
                    except Exception as e:
                        logger.error(f"【全量STRM生成】初始化 Rust 核心失败: {e}")
                        return False

                    logger.info(
                        f"【全量STRM生成】Full Sync STRM Rust Core Version：v{rust_core_version}"
                    )

                try:
                    parent_id = get_pid_by_path(
                        self.client, pan_media_dir, True, False, False
                    )
                    logger.info(
                        f"【全量STRM生成】网盘媒体目录 ID 获取成功: {pan_media_dir} {parent_id}"
                    )
                except Exception as e:
                    sentry_manager.sentry_hub.capture_exception(e)
                    logger.error(
                        f"【全量STRM生成】网盘媒体目录 ID 获取失败: {pan_media_dir} {e}"
                    )
                    return False

                try:
                    if (
                        configer.get_config("full_sync_iter_function")
                        == "iter_files_with_path_skim"
                    ):
                        iter_func = iter_files_with_path_skim
                        iter_kwargs = {
                            "cid": parent_id,
                            "with_ancestors": True,
                            **configer.get_ios_ua_app(),
                        }
                    else:
                        iter_func = iter_files_with_path
                        iter_kwargs = {
                            "cid": parent_id,
                            "with_ancestors": True,
                            "cooldown": 1.5,
                            **configer.get_ios_ua_app(),
                        }
                    logger.debug(
                        f"【全量STRM生成】迭代函数 {iter_func}; 参数 {iter_kwargs}"
                    )
                    start_time = perf_counter()
                    seen_folder_ids: Set[str] = set()
                    seen_file_ids: Set[str] = set()
                    for batch in batched(
                        iter_func(self.client, **iter_kwargs),
                        int(configer.get_config("full_sync_batch_num")),
                    ):
                        path_list: List = []

                        db_task_future = executor.submit(
                            self.__process_db_item,
                            batch,
                            seen_folder_ids,
                            seen_file_ids,
                        )

                        if rust:
                            input_batch = [
                                {
                                    "name": item.get("name"),
                                    "path": item.get("path"),
                                    "is_dir": item.get("is_dir"),
                                    "size": item.get("size"),
                                    "pickcode": item.get(
                                        "pickcode", item.get("pick_code")
                                    ),
                                    "sha1": item.get("sha1"),
                                }
                                for item in batch
                                if item.get("name") and item.get("path")
                            ]

                            self.total_count += len(input_batch)

                            batch_json = dumps(input_batch).decode("utf-8")
                            results: PackedResult = processor.process_batch(batch_json)

                            for fail_info in results.fail_results:
                                self.strm_fail_count += 1
                                self.strm_fail_dict[fail_info.path_in_pan] = (
                                    fail_info.reason
                                )

                            for download_info in results.download_results:
                                local_path = target_dir / Path(
                                    download_info.path_in_pan
                                ).relative_to(pan_media_dir)
                                if (
                                    local_path.exists()
                                    and self.overwrite_mode == "never"
                                ):
                                    self.__base_logger(
                                        "warn",
                                        f"【全量STRM生成】媒体文件 {local_path} 已存在，覆盖模式为 'never'，跳过下载。",
                                    )
                                    continue
                                self.download_mediainfo_list.append(
                                    {
                                        "type": "local",
                                        "pickcode": download_info.pickcode,
                                        "path": local_path,
                                        "sha1": download_info.sha1,
                                    }
                                )

                            for strm_info in results.strm_results:
                                local_path = target_dir / Path(
                                    strm_info.path_in_pan
                                ).relative_to(pan_media_dir)
                                new_file_path = local_path.with_name(
                                    StrmGenerater.get_strm_filename(local_path)
                                )
                                if self.remove_unless_strm:
                                    path_list.append(str(new_file_path))
                                if new_file_path.exists():
                                    if self.overwrite_mode == "never":
                                        self.__base_logger(
                                            "warn",
                                            f"【全量STRM生成】STRM 文件 {new_file_path} 已存在，覆盖模式为 'never'，跳过生成。",
                                        )
                                        continue
                                    self.__base_logger(
                                        "warn",
                                        f"【全量STRM生成】{new_file_path} 已存在，将进行覆盖。",
                                    )
                                strm_url = self.strmurlgetter.get_strm_url(
                                    strm_info.pickcode,
                                    strm_info.original_file_name,
                                    strm_info.path_in_pan,
                                )
                                self.write_queue.put(
                                    (
                                        new_file_path,
                                        strm_url,
                                        strm_info.original_file_name,
                                    )
                                )

                            if configer.full_sync_strm_log:
                                for skip_info in results.skip_results:
                                    if not skip_info.reason:
                                        continue
                                    self.__base_logger(
                                        "warn", "【全量STRM生成】" + skip_info.reason
                                    )
                        else:
                            target_dir_path = Path(target_dir)

                            future_to_item = {
                                executor.submit(
                                    self.__process_single_item,
                                    item,
                                    target_dir_path,
                                    pan_media_dir,
                                ): item
                                for item in batch
                            }

                            self.total_count += len(future_to_item)

                            for future in as_completed(future_to_item):
                                item = future_to_item[future]
                                try:
                                    result = future.result()
                                    if not result:
                                        continue

                                    if result.status == "fail":
                                        self.strm_fail_count += 1
                                        self.strm_fail_dict[result.path] = (
                                            result.message
                                        )
                                    elif result.status == "download":
                                        self.download_mediainfo_list.append(result.data)

                                    if result.path_entry:
                                        path_list.append(result.path_entry)

                                except Exception as e:
                                    sentry_manager.sentry_hub.capture_exception(e)
                                    logger.error(
                                        f"【全量STRM生成】并发处理出错: {item} - {str(e)}"
                                    )

                        try:
                            seen_folder_ids, seen_file_ids = db_task_future.result()
                        except Exception as e:
                            sentry_manager.sentry_hub.capture_exception(e)
                            logger.error(
                                f"【全量STRM生成】数据库处理并发处理出错: {str(e)}"
                            )

                        if self.remove_unless_strm:
                            self.pan_tree.generate_tree_from_list(
                                path_list, append=True
                            )

                    end_time = perf_counter()
                    self.elapsed_time += end_time - start_time
                    self.total_db_write_count += len(seen_file_ids) + len(
                        seen_folder_ids
                    )

                    self.write_queue.join()
                    self.result_queue.join()
                except Exception as e:
                    sentry_manager.sentry_hub.capture_exception(e)
                    logger.error(
                        f"【全量STRM生成】全量生成 STRM 文件失败: {pan_media_dir} {e}",
                        exc_info=True,
                    )
                    return False

                if self.remove_unless_strm:
                    while local_tree_task_thread.is_alive():  # noqa
                        logger.info("【全量STRM生成】扫描本地媒体库运行中...")
                        sleep(10)
                    if (
                        not self.strm_fail_dict
                        and (
                            settings.CACHE_BACKEND_TYPE == "redis"
                            or self.local_tree_path.exists()
                        )
                        and self.local_tree.count() != 0
                    ):
                        try:
                            counts = self.__get_remove_unless_strm(path_base64).get(
                                "counts", []
                            )
                            local_tree_count = self.local_tree.count()
                            remove_count = self.local_tree.compare_entry_counts(
                                self.pan_tree
                            )
                            rp = (remove_count / local_tree_count) * 100
                            if rp > configer.full_sync_remove_unless_max_threshold:
                                # 在阈值范围外，进行数据稳定性测试
                                logger.warn(
                                    f"【全量STRM生成】本次将删除文件个数为 {remove_count}，超过安全阈值 {configer.full_sync_remove_unless_max_threshold}% 不进行删除操作"
                                )

                                counts.append(remove_count)
                                if len(counts) < 3:
                                    logger.info(
                                        f"【全量STRM生成】删除数据稳定性检查，已收集 {len(counts)}/3 个数据点 {counts}"
                                    )
                                    self.__save_remove_unless_strm(
                                        path_base64, {"counts": counts}
                                    )
                                    continue

                                if MathUtils.is_stable_cv(
                                    counts,
                                    configer.full_sync_remove_unless_stable_threshold
                                    / 100,
                                ):
                                    logger.info(
                                        f"【全量STRM生成】删除数据稳定性检查通过: {counts}"
                                    )
                                    self.__save_remove_unless_strm(
                                        path_base64, {"counts": []}
                                    )
                                else:
                                    logger.warn(
                                        f"【全量STRM生成】删除数据稳定性检查失败，重置计数器: {counts}"
                                    )
                                    self.__save_remove_unless_strm(
                                        path_base64, {"counts": [remove_count]}
                                    )
                                    continue
                            else:
                                # 在阈值内，且存在计数，则清空
                                if len(counts) > 0:
                                    self.__save_remove_unless_strm(
                                        path_base64, {"counts": []}
                                    )

                            for remove_path in self.local_tree.compare_trees(
                                self.pan_tree
                            ):
                                logger.info(
                                    f"【全量STRM生成】清理无效 STRM 文件: {remove_path}"
                                )
                                Path(remove_path).unlink(missing_ok=True)
                                if configer.full_sync_remove_unless_file:
                                    PathRemoveUtils.clean_related_files(
                                        file_path=Path(remove_path),
                                        func_type="【全量STRM生成】",
                                    )
                                if configer.full_sync_remove_unless_dir:
                                    PathRemoveUtils.remove_parent_dir(
                                        file_path=Path(remove_path),
                                        mode=["strm"],
                                        func_type="【全量STRM生成】",
                                    )
                                self.remove_unless_strm_count += 1
                        except Exception as e:
                            sentry_manager.sentry_hub.capture_exception(e)
                            logger.error(f"【全量STRM生成】清理无效 STRM 文件失败: {e}")
                    else:
                        logger.warn(
                            "【全量STRM生成】存在生成失败的 STRM 文件或扫描本地文件出错，跳过清理无效 STRM 文件"
                        )

        logger.info("【全量STRM生成】所有文件处理任务已提交，等待文件写入完成...")
        self.write_queue.join()
        for _ in range(num_io_workers):
            self.write_queue.put(None)
        for thread in io_threads:
            thread.join()
        self.result_queue.join()
        collector_thread.join()

        self.mediainfo_count, self.mediainfo_fail_count, self.mediainfo_fail_dict = (
            self.mediainfodownloader.batch_auto_downloader(
                downloads_list=self.download_mediainfo_list
            )
        )

        if self.mediaserver_helper.enabled:
            logger.info(
                "【全量STRM生成】开始刷新整个媒体库，此操作会刷新所有媒体服务器"
            )
            self.mediaserver_helper.refresh_mediaserver(refresh_all=True)

        self.result_print()

        logger.debug(
            f"【全量STRM生成】时间 {self.elapsed_time:.6f} 秒，总迭代文件数量 {self.total_count} 个，数据库写入量 {self.total_db_write_count} 条"
        )

        return True

    def result_print(self):
        """
        输出结果信息
        """
        if self.strm_fail_dict:
            for path, error in self.strm_fail_dict.items():
                logger.warn(f"【全量STRM生成】{path} 生成错误原因: {error}")
        if self.mediainfo_fail_dict:
            for path in self.mediainfo_fail_dict:
                logger.warn(f"【全量STRM生成】{path} 下载错误")
        logger.info(
            f"【全量STRM生成】全量生成 STRM 文件完成，总共生成 {self.strm_count} 个 STRM 文件，下载 {self.mediainfo_count} 个媒体数据文件"
        )
        if self.strm_fail_count != 0 or self.mediainfo_fail_count != 0:
            logger.warn(
                f"【全量STRM生成】{self.strm_fail_count} 个 STRM 文件生成失败，{self.mediainfo_fail_count} 个媒体数据文件下载失败"
            )
        if self.remove_unless_strm_count != 0:
            logger.warn(
                f"【全量STRM生成】清理 {self.remove_unless_strm_count} 个失效 STRM 文件"
            )

    def get_generate_total(self):
        """
        输出总共生成文件个数
        """
        return (
            self.strm_count,
            self.mediainfo_count,
            self.strm_fail_count,
            self.mediainfo_fail_count,
            self.remove_unless_strm_count,
        )
