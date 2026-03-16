from collections import deque
from itertools import batched
from pathlib import Path
from threading import Thread
from time import sleep
from typing import List, Dict, Optional, Tuple, Iterator, Any, Generator

from p115client import P115Client
from p115client.tool.export_dir import export_dir_parse_iter
from p115client.tool.iterdir import iterdir
from p115client.tool.fs_files import iter_fs_files
from sqlalchemy.orm.exc import MultipleResultsFound

from app.core.config import settings
from app.log import logger

from ...core.cache import idpathcacher, DirectoryCache
from ...core.config import configer
from ...core.scrape import media_scrape_metadata
from ...core.p115 import get_pid_by_path
from ...db_manager.oper import FileDbHelper
from ...helper.mediainfo_download import MediaInfoDownloader
from ...helper.mediaserver import MediaServerRefresh, emby_mediainfo_queue
from ...utils.exception import (
    CanNotFindPathToCid,
    ItertreeInternalError,
    PanDataNotInDb,
    PanPathNotFound,
)
from ...utils.path import PathUtils
from ...utils.sentry import sentry_manager
from ...utils.strm import StrmUrlGetter, StrmGenerater
from ...utils.tree import DirectoryTree
from ...utils.automaton import AutomatonUtils
from ...utils.mediainfo_download import MediainfoDownloadMiddleware


class IncrementSyncStrmHelper:
    """
    增量同步 STRM 文件
    """

    def __init__(self, client: P115Client, mediainfodownloader: MediaInfoDownloader):
        self.client = client
        self.mediainfodownloader = mediainfodownloader
        self.rmt_mediaext = [
            f".{ext.strip()}"
            for ext in configer.get_config("user_rmt_mediaext")
            .replace("，", ",")
            .split(",")
        ]
        self.download_mediaext = [
            f".{ext.strip()}"
            for ext in configer.get_config("user_download_mediaext")
            .replace("，", ",")
            .split(",")
        ]
        self.auto_download_mediainfo = configer.get_config(
            "increment_sync_auto_download_mediainfo_enabled"
        )
        self.mp_mediaserver_paths = configer.get_config(
            "increment_sync_mp_mediaserver_paths"
        )
        self.scrape_metadata_enabled = configer.get_config(
            "increment_sync_scrape_metadata_enabled"
        )
        self.scrape_metadata_exclude_paths = configer.get_config(
            "increment_sync_scrape_metadata_exclude_paths"
        )
        self.media_server_refresh_enabled = configer.get_config(
            "increment_sync_media_server_refresh_enabled"
        )
        self.mediaservers = configer.increment_sync_mediaservers
        self.emby_mediainfo_enabled = configer.increment_sync_emby_mediainfo_enabled
        self.strm_count = 0
        self.mediainfo_count = 0
        self.strm_fail_count = 0
        self.mediainfo_fail_count = 0
        self.api_count = 0
        self.strm_fail_dict: Dict[str, str] = {}
        self.mediainfo_fail_dict: List = []
        self.pan_transfer_enabled = configer.pan_transfer_enabled
        self.pan_transfer_paths = configer.pan_transfer_paths
        self.databasehelper = FileDbHelper()
        self.directory_cache = DirectoryCache(
            configer.PLUGIN_TEMP_PATH / "increment_skip"
        )
        self.directory_cache_group_name = "increment_skip"
        self.download_mediainfo_list = []

        self.mdaw = AutomatonUtils.build_automaton(
            configer.mediainfo_download_whitelist
        )
        self.mdab = AutomatonUtils.build_automaton(
            configer.mediainfo_download_blacklist
        )

        self.strmurlgetter = StrmUrlGetter()
        self.mediaserver_helper = MediaServerRefresh(
            func_name="【增量STRM生成】",
            enabled=self.media_server_refresh_enabled,
            mp_mediaserver=self.mp_mediaserver_paths,
            mediaservers=self.mediaservers,
        )

        self.local_tree_path = (
            configer.get_config("PLUGIN_TEMP_PATH") / "increment_local_tree.txt"
        )
        self.pan_tree_path = (
            configer.get_config("PLUGIN_TEMP_PATH") / "increment_pan_tree.txt"
        )
        self.pan_to_local_tree_path = (
            configer.get_config("PLUGIN_TEMP_PATH") / "increment_pan_to_local_tree.txt"
        )
        self.local_tree = DirectoryTree(self.local_tree_path)
        self.pan_tree = DirectoryTree(self.pan_tree_path)
        self.pan_to_local_tree = DirectoryTree(self.pan_to_local_tree_path)

    def __del__(self):
        self.directory_cache.close()
        self.local_tree.clear()
        self.pan_tree.clear()
        self.pan_to_local_tree.clear()

    def __itertree(
        self, pan_path: str, local_path: str
    ) -> Generator[tuple[str, str], Any, None]:
        """
        迭代目录树

        :param pan_path: 网盘路径
        :param local_path: 本地路径

        :return Iterator: 网盘路径迭代器
        """
        relative_path = None

        cid = get_pid_by_path(self.client, pan_path, True, False, False)
        if cid == -1:
            raise PanPathNotFound(f"网盘路径不存在: {pan_path}")
        self.api_count += 4

        items_iterator = export_dir_parse_iter(
            client=self.client,
            export_file_ids=cid,
            delete=True,
            **configer.get_ios_ua_app(app=False),
        )
        try:
            next(items_iterator)
            relative_path = next(items_iterator)
        except StopIteration:
            return

        def process_file_item(item_str: str):
            item_path = Path(pan_path) / Path(item_str).relative_to(relative_path)
            relative_item_path = item_path.relative_to(pan_path)
            local_item_path = Path(local_path) / relative_item_path

            if item_path.suffix.lower() in self.rmt_mediaext:
                strm_filename = StrmGenerater.get_strm_filename(local_item_path)
                yield (
                    (local_item_path.parent / strm_filename).as_posix(),
                    item_path.as_posix(),
                )
            elif (
                item_path.suffix.lower() in self.download_mediaext
                and self.auto_download_mediainfo
            ):
                yield (
                    local_item_path.as_posix(),
                    item_path.as_posix(),
                )

        previous_item = None
        for current_item in items_iterator:
            if previous_item is not None:
                if not current_item.startswith(previous_item + "/"):
                    yield from process_file_item(previous_item)
            previous_item = current_item
        if previous_item is not None:
            yield from process_file_item(previous_item)

    def __iterdir(self, cid: int, path: str) -> Iterator:
        """
        迭代网盘目录

        :param cid: 网盘目录 ID
        :param path: 网盘路径

        :return Iterator: 网盘文件(夹)信息迭代器
        """
        logger.debug(f"【增量STRM生成】迭代网盘目录: {cid} {path}")
        for batch in iter_fs_files(
            self.client, cid, cooldown=2, **configer.get_ios_ua_app(app=False)
        ):
            self.api_count += 1
            for item in batch.get("data", []):
                item["path"] = path + "/" + item.get("n")
                yield item

    def __get_cid_by_path(self, path: str) -> Optional[int]:
        """
        通过路径获取 cid
        先从缓存获取，再从数据库获取

        :param path: 网盘目录

        :return int: 网盘目录 ID
        """
        cid = idpathcacher.get_id_by_dir(path)
        if not cid:
            # 这里如果有多条重复数据就不进行删除文件夹操作了，说明数据库重复过多，直接放弃
            data = self.databasehelper.get_by_path(path=path)
            if data:
                cid = data.get("id", "")
                if cid:
                    logger.debug(f"【增量STRM生成】获取 {path} cid（数据库）: {cid}")
                    idpathcacher.add_cache(id=int(cid), directory=path)
                    return int(cid)
            return None
        logger.debug(f"【增量STRM生成】获取 {path} cid（缓存）: {cid}")
        return int(cid)

    def __get_size(self, path: str) -> Optional[int]:
        """
        通过数据库获取文件大小

        :param path: 网盘路径

        :return int: 文件大小
        """
        data = self.databasehelper.get_by_path(path=path)
        if data:
            size = data.get("size", 0)
            if size and size > 0:
                return size
        return None

    def __get_pickcode_sha1(self, path: str) -> Tuple[str, str]:
        """
        通过路径获取 pick_code, sha1

        :param path: 文件网盘路径

        :return pick_code, sha1: 返回此文件的 pick_code 和 sha1
        """
        last_path = None
        processed = []
        while True:
            # 这里如果有多条重复数据直接删除文件重复信息，然后迭代重新获取
            try:
                file_item = self.databasehelper.get_by_path(path=path)
            except MultipleResultsFound:
                self.databasehelper.remove_by_path_batch(path=path, only_file=True)
                file_item = None
            if file_item:
                return file_item.get("pickcode"), file_item.get("sha1")
            file_path = Path(path)
            temp_path = None
            cid = None
            for part in file_path.parents:
                cid = self.__get_cid_by_path(part.as_posix())
                if cid:
                    temp_path = part
                    break
            if not temp_path:
                raise PanDataNotInDb(f"数据库无数据，无法找到路径 {path} 对应的 cid")
            if last_path and last_path == temp_path:
                logger.debug(f"文件夹遍历错误：{last_path} {processed}")
                raise CanNotFindPathToCid(
                    f"文件夹遍历错误，无法找到路径 {path} 对应的 cid"
                )
            if not cid:
                raise CanNotFindPathToCid(f"无法找到路径 {path} 的 cid")
            for batch in batched(
                self.__iterdir(cid=cid, path=temp_path.as_posix()), 5_000
            ):
                processed: List = []
                for item in batch:
                    processed.extend(self.databasehelper.process_fs_files_item(item))
                self.databasehelper.upsert_batch(processed)
            last_path = temp_path
            sleep(2)

    def __generate_local_tree(self, target_dir: str):
        """
        生成本地目录树

        :param target_dir: 本地目录
        """
        self.local_tree.clear()

        def background_task(_target_dir):
            """
            后台运行任务
            """
            logger.info(f"【增量STRM生成】开始扫描本地媒体库文件: {_target_dir}")
            try:
                self.local_tree.scan_directory_to_tree(
                    root_path=_target_dir,
                    append=False,
                    use_posix=True,
                    extensions=[".strm"]
                    if not self.auto_download_mediainfo
                    else [".strm"] + self.download_mediaext,
                )
                logger.info(f"【增量STRM生成】扫描本地媒体库文件完成: {_target_dir}")
            except Exception as e:
                sentry_manager.sentry_hub.capture_exception(e)
                logger.error(
                    f"【增量STRM生成】扫描本地媒体库文件 {_target_dir} 错误: {e}"
                )

        local_tree_task_thread = Thread(
            target=background_task,
            args=(target_dir,),
        )
        local_tree_task_thread.start()

        return local_tree_task_thread

    @staticmethod
    def __wait_generate_local_tree(thread):
        """
        等待生成本地目录树运行完成

        :param thread: 本地目录树线程
        """
        while thread.is_alive():
            logger.info("【增量STRM生成】扫描本地媒体库运行中...")
            sleep(10)

    def __generate_pan_tree(self, pan_media_dir: str, target_dir: str):
        """
        生成网盘目录树

        :param pan_media_dir: 网盘目录
        :param target_dir: 本地目录

        :raise: ItertreeInternalError: 网盘目录树生成失败
        """
        last_error: Optional[Exception] = None
        for i in range(1, 4):
            self.pan_tree.clear()
            self.pan_to_local_tree.clear()

            logger.info(f"【增量STRM生成】开始生成网盘目录树: {pan_media_dir}")

            try:
                for path1, path2 in self.__itertree(
                    pan_path=pan_media_dir, local_path=target_dir
                ):
                    self.pan_to_local_tree.generate_tree_from_list([path1], append=True)
                    self.pan_tree.generate_tree_from_list([path2], append=True)

                logger.info(f"【增量STRM生成】网盘目录树生成完成: {pan_media_dir}")
                return
            except Exception as e:
                last_error = e
                sentry_manager.sentry_hub.capture_exception(e)
                if "Broken pipe" in str(e):
                    logger.warning(
                        f"【增量STRM生成】网盘目录树生成 {pan_media_dir} 错误: {e}，第 {i} 次自动重试..."
                    )
                    sleep(30 + 2**i)
                else:
                    logger.error(
                        f"【增量STRM生成】网盘目录树生成 {pan_media_dir} 错误: {e}"
                    )
                    raise ItertreeInternalError(
                        f"网盘目录树生成失败: {pan_media_dir}"
                    ) from e
        if last_error is not None:
            raise ItertreeInternalError(
                f"网盘目录树生成失败: {pan_media_dir}"
            ) from last_error

    def __handle_addition_path(self, pan_path: str, local_path: str):
        """
        处理新增路径

        :param pan_path: 网盘路径
        :param local_path: 本地路径
        """
        pan_path_obj = Path(pan_path)
        new_file_path = Path(local_path)

        try:
            if self.directory_cache.is_in_cache(
                self.directory_cache_group_name, pan_path
            ):
                return

            if self.pan_transfer_enabled and self.pan_transfer_paths:
                if PathUtils.get_run_transfer_path(
                    paths=self.pan_transfer_paths,
                    transfer_path=pan_path,
                ):
                    logger.debug(
                        f"【增量STRM生成】{pan_path} 为待整理目录下的路径，不做处理"
                    )
                    return

            if self.auto_download_mediainfo:
                if pan_path_obj.suffix.lower() in self.download_mediaext:
                    if not (
                        result := MediainfoDownloadMiddleware.should_download(
                            filename=pan_path_obj.name,
                            blacklist_automaton=self.mdab,
                            whitelist_automaton=self.mdaw,
                        )
                    )[1]:
                        logger.warning(
                            "【增量STRM生成】%s，跳过网盘路径: %s",
                            result[0],
                            pan_path,
                        )
                        self.directory_cache.add_to_group(
                            self.directory_cache_group_name, pan_path
                        )
                        return

                    pickcode, sha1 = self.__get_pickcode_sha1(pan_path)
                    if not pickcode:
                        logger.error(
                            f"【增量STRM生成】{pan_path_obj.name} 不存在 pickcode 值，无法下载该文件"
                        )
                        return
                    self.download_mediainfo_list.append(
                        {
                            "type": "local",
                            "pickcode": pickcode,
                            "path": local_path,
                            "sha1": sha1,
                        }
                    )
                    return

            if pan_path_obj.suffix.lower() not in self.rmt_mediaext:
                logger.warn(f"【增量STRM生成】跳过网盘路径: {pan_path}")
                self.directory_cache.add_to_group(
                    self.directory_cache_group_name, pan_path
                )
                return

            if not (
                result := StrmGenerater.should_generate_strm(
                    pan_path_obj.name, "increment", self.__get_size(pan_path)
                )
            )[1]:
                logger.warn(f"【增量STRM生成】{result[0]}，跳过网盘路径: {pan_path}")
                self.directory_cache.add_to_group(
                    self.directory_cache_group_name, pan_path
                )
                return

            pickcode, sha1 = self.__get_pickcode_sha1(pan_path)

            if not (
                result := StrmGenerater.not_min_limit(
                    "increment", self.__get_size(pan_path)
                )
            )[1]:
                logger.warn(f"【增量STRM生成】{result[0]}，跳过网盘路径: {pan_path}")
                self.directory_cache.add_to_group(
                    self.directory_cache_group_name, pan_path
                )
                return

            new_file_path.parent.mkdir(parents=True, exist_ok=True)

            if not pickcode:
                self.strm_fail_count += 1
                self.strm_fail_dict[str(new_file_path)] = "不存在 pickcode 值"
                logger.error(
                    f"【增量STRM生成】{pan_path_obj.name} 不存在 pickcode 值，无法生成 STRM 文件"
                )
                return
            if not (len(pickcode) == 17 and str(pickcode).isalnum()):
                self.strm_fail_count += 1
                self.strm_fail_dict[str(new_file_path)] = (
                    f"错误的 pickcode 值 {pickcode}"
                )
                logger.error(
                    f"【增量STRM生成】错误的 pickcode 值 {pickcode}，无法生成 STRM 文件"
                )
                return

            strm_url = self.strmurlgetter.get_strm_url(
                pickcode, pan_path_obj.name, pan_path
            )

            with open(new_file_path, "w", encoding="utf-8") as file:
                file.write(strm_url)
            self.strm_count += 1
            logger.info(
                "【增量STRM生成】生成 STRM 文件成功: %s",
                str(new_file_path),
            )
        except Exception as e:
            sentry_manager.sentry_hub.capture_exception(e)
            logger.error(
                "【增量STRM生成】生成 STRM 文件失败: %s  %s",
                str(new_file_path),
                e,
            )
            self.strm_fail_count += 1
            self.strm_fail_dict[str(new_file_path)] = str(e)
            return
        if self.scrape_metadata_enabled:
            scrape_metadata = True
            if self.scrape_metadata_exclude_paths:
                if PathUtils.get_scrape_metadata_exclude_path(
                    self.scrape_metadata_exclude_paths,
                    local_path,
                ):
                    logger.debug(
                        f"【增量STRM生成】匹配到刮削排除目录，不进行刮削: {local_path}"
                    )
                    scrape_metadata = False
            if scrape_metadata:
                media_scrape_metadata(
                    path=local_path,
                )
        self.mediaserver_helper.refresh_mediaserver(
            file_path=local_path,
            file_name=new_file_path.name,
        )

        if self.emby_mediainfo_enabled and sha1:
            emby_mediainfo_queue.enqueue(
                func_name="【增量STRM生成】",
                sha1=sha1,
                path=Path(local_path),
                mp_mediaserver=self.mp_mediaserver_paths,
                mediaservers=self.mediaservers,
                size=self.__get_size(pan_path),
            )

    def __scan_second_level_directory(self, path: str) -> List[str]:
        """
        扫描二级目录

        :param path: 路径

        :return: 目录名称列表
        """
        self.api_count += 2
        name_list: List[str] = []
        cid = get_pid_by_path(self.client, path, True, False, False)
        if cid == -1:
            raise PanPathNotFound(f"网盘路径不存在: {path}")
        for item in iterdir(
            client=self.client, cid=cid, cooldown=2, **configer.get_ios_ua_app()
        ):
            if not item["is_dir"]:
                raise OSError("二级目录不能存在文件")
            name_list.append(item["name"])
            if len(name_list) > 100:
                raise OSError("超出二级目录扫描上限")
        return name_list

    def generate_strm_files(self, sync_strm_paths):
        """
        生成 STRM 文件

        :param sync_strm_paths: 同步 STRM 路径
        """
        media_paths = sync_strm_paths.split("\n")
        if configer.increment_sync_second_level_dir_scan:
            try:
                lst: List[str] = []
                for path in media_paths:
                    if not path or not path.strip():
                        continue
                    parts = path.strip().split("#", 1)
                    target_dir = Path(parts[0].strip()).as_posix()
                    pan_media_dir = Path(parts[1].strip()).as_posix()
                    for n in self.__scan_second_level_directory(pan_media_dir):
                        pt_str = f"{target_dir}/{n}#{pan_media_dir}/{n}"
                        lst.append(pt_str)
                        logger.info(f"【增量STRM生成】扫描到目录: {pt_str}")
                queue: deque[Tuple[str, int]] = deque((path.strip(), 0) for path in lst)
            except Exception as e:
                logger.error(f"【增量STRM生成】构建目录列表出错: {e}")
                return
        else:
            queue: deque[Tuple[str, int]] = deque(
                (path.strip(), 0) for path in media_paths if path and path.strip()
            )
        while queue:
            path, retry_count = queue.popleft()
            if retry_count > 2:
                continue
            parts = path.split("#", 1)
            target_dir = parts[0].strip()
            pan_media_dir = parts[1].strip()

            if pan_media_dir == "/" or target_dir == "/":
                logger.error(
                    f"【增量STRM生成】网盘目录或本地生成目录不能为根目录: {path}"
                )
                continue

            pan_media_dir = pan_media_dir.rstrip("/")
            target_dir = target_dir.rstrip("/")

            try:
                # 生成本地目录树文件
                local_tree_task_thread = self.__generate_local_tree(
                    target_dir=target_dir
                )

                # 生成网盘目录树文件
                self.__generate_pan_tree(
                    pan_media_dir=pan_media_dir, target_dir=target_dir
                )

                # 等待生成本地目录树运行完成
                self.__wait_generate_local_tree(local_tree_task_thread)

                if (
                    not self.pan_to_local_tree_path.exists()
                    or not self.local_tree_path.exists()
                ) and settings.CACHE_BACKEND_TYPE != "redis":
                    logger.error(f"【增量STRM生成】{path} 目录树生成错误")
                else:
                    # 生成或者下载文件
                    for line in self.pan_to_local_tree.compare_trees_lines(
                        self.local_tree
                    ):
                        pan_path_str = self.pan_tree.get_path_by_line_number(line)
                        local_path_str = self.pan_to_local_tree.get_path_by_line_number(
                            line
                        )
                        if pan_path_str and local_path_str:
                            self.__handle_addition_path(
                                pan_path=pan_path_str,
                                local_path=local_path_str,
                            )
            except ItertreeInternalError as e:
                if retry_count < 2:
                    queue.append((path, retry_count + 1))
                    logger.warning(
                        f"【增量STRM生成】目录同步错误，已加入队尾重试（剩余重试次数 {2 - retry_count}）: {path}，错误: {e}"
                    )
                else:
                    logger.error(
                        f"【增量STRM生成】目录同步错误，已达重试上限: {path}，错误: {e}"
                    )
            except Exception as e:
                sentry_manager.sentry_hub.capture_exception(e)
                logger.error(f"【增量STRM生成】增量同步 STRM 文件失败: {e}")
                return

            wait_seconds = 20 + 10 * retry_count
            sleep(wait_seconds)

        # 下载媒体信息文件
        self.mediainfo_count, self.mediainfo_fail_count, self.mediainfo_fail_dict = (
            self.mediainfodownloader.batch_auto_downloader(
                downloads_list=self.download_mediainfo_list
            )
        )

        # 日志输出
        if self.strm_fail_dict:
            for path, error in self.strm_fail_dict.items():
                logger.warn(f"【增量STRM生成】{path} 生成错误原因: {error}")
        if self.mediainfo_fail_dict:
            for path in self.mediainfo_fail_dict:
                logger.warn(f"【增量STRM生成】{path} 下载错误")
        logger.info(
            f"【增量STRM生成】增量生成 STRM 文件完成，总共生成 {self.strm_count} 个 STRM 文件，下载 {self.mediainfo_count} 个媒体数据文件"
        )
        if self.strm_fail_count != 0 or self.mediainfo_fail_count != 0:
            logger.warn(
                f"【增量STRM生成】{self.strm_fail_count} 个 STRM 文件生成失败，{self.mediainfo_fail_count} 个媒体数据文件下载失败"
            )
        logger.info(f"【增量STRM生成】API 请求次数 {self.api_count} 次")

    def get_generate_total(self):
        """
        输出总共生成文件个数
        """
        return (
            self.strm_count,
            self.mediainfo_count,
            self.strm_fail_count,
            self.mediainfo_fail_count,
        )
