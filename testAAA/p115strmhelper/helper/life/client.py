from shutil import rmtree
from collections import defaultdict
from threading import Timer, Event, Thread
from time import sleep, strftime, localtime, time
from typing import List, Set, Dict, Optional
from pathlib import Path
from itertools import batched, chain

from ...core.config import configer
from ...core.message import post_message
from ...core.scrape import media_scrape_metadata
from ...core.cache import idpathcacher, pantransfercacher, lifeeventcacher
from ...core.i18n import i18n
from ...core.p115 import get_pid_by_path, iter_life_behavior_once
from ...utils.path import PathUtils, PathRemoveUtils
from ...utils.sentry import sentry_manager
from ...utils.strm import StrmUrlGetter, StrmGenerater
from ...utils.automaton import AutomatonUtils
from ...utils.mediainfo_download import MediainfoDownloadMiddleware
from ...utils.http import check_iter_path_data
from ...utils.exception import FileItemKeyMiss
from ...db_manager.oper import FileDbHelper, LifeEventDbHelper
from ...helper.mediainfo_download import MediaInfoDownloader
from ...helper.mediasyncdel import MediaSyncDelHelper
from ...helper.mediaserver import MediaServerRefresh, emby_mediainfo_queue
from ...helper.life.queue import LifeTasksQueue

from p115client import P115Client, check_response
from p115client.exception import P115AuthenticationError
from p115client.tool.attr import get_path, normalize_attr
from p115client.tool.fs_files import iter_fs_files
from p115client.tool.iterdir import iter_files_with_path
from p115client.tool.life import life_show, BEHAVIOR_TYPE_TO_NAME

from app.schemas import NotificationType, FileItem
from app.log import logger
from app.core.config import settings
from app.chain.storage import StorageChain
from app.chain.transfer import TransferChain


@sentry_manager.capture_all_class_exceptions
class MonitorLife:
    """
    监控115生活事件

    {
        1: "upload_image_file",  上传图片 生成 STRM;写入数据库
        2: "upload_file",        上传文件/目录 生成 STRM;写入数据库
        3: "star_image",         标星图片 无操作
        4: "star_file",          标星文件/目录 无操作
        5: "move_image_file",    移动图片 生成 STRM;写入数据库
        6: "move_file",          移动文件/目录 生成 STRM;写入数据库
        7: "browse_image",       浏览图片 无操作
        8: "browse_video",       浏览视频 无操作
        9: "browse_audio",       浏览音频 无操作
        10: "browse_document",   浏览文档 无操作
        14: "receive_files",     接收文件 生成 STRM;写入数据库
        17: "new_folder",        创建新目录 写入数据库
        18: "copy_folder",       复制文件夹 生成 STRM;写入数据库
        19: "folder_label",      标签文件夹 无操作
        20: "folder_rename",     重命名文件夹 无操作
        22: "delete_file",       删除文件/文件夹 删除 STRM;移除数据库
    }

    注意: 目前没有重命名文件，复制文件的操作事件
    """

    def __init__(
        self,
        client: P115Client,
        mediainfodownloader: MediaInfoDownloader,
        stop_event: Optional[Event] = None,
    ):
        self._client = client
        self.mediainfodownloader = mediainfodownloader
        self.stop_event = stop_event

        self.tasks_queue = LifeTasksQueue()

        self._monitor_life_notification_timer = None
        self._monitor_life_notification_queue = defaultdict(
            lambda: {"strm_count": 0, "mediainfo_count": 0}
        )

        self.rmt_mediaext: List = []
        self.rmt_mediaext_set: Set = set()
        self.download_mediaext_set: Set = set()

        self.mdaw = AutomatonUtils.build_automaton(
            configer.mediainfo_download_whitelist
        )
        self.mdab = AutomatonUtils.build_automaton(
            configer.mediainfo_download_blacklist
        )

        self.mediaserver_helper = MediaServerRefresh(
            func_name="【监控生活事件】",
            enabled=configer.monitor_life_media_server_refresh_enabled,
            mp_mediaserver=configer.monitor_life_mp_mediaserver_paths,
            mediaservers=configer.monitor_life_mediaservers,
        )

    def _schedule_notification(self):
        """
        安排通知发送，如果一分钟内没有新事件则发送
        """
        if self._monitor_life_notification_timer:
            self._monitor_life_notification_timer.cancel()

        self._monitor_life_notification_timer = Timer(60.0, self._send_notification)
        self._monitor_life_notification_timer.start()

    def _send_notification(self):
        """
        发送合并后的通知
        """
        if "life" not in self._monitor_life_notification_queue:
            return

        counts = self._monitor_life_notification_queue["life"]
        if counts["strm_count"] == 0 and counts["mediainfo_count"] == 0:
            return

        text_parts = []
        if counts["strm_count"] > 0:
            text_parts.append(f"📄 生成STRM文件 {counts['strm_count']} 个")
        if counts["mediainfo_count"] > 0:
            text_parts.append(f"⬇️ 下载媒体文件 {counts['mediainfo_count']} 个")

        if text_parts and configer.get_config("notify"):
            post_message(
                mtype=NotificationType.Plugin,
                title=i18n.translate("life_sync_done_title"),
                text="\n" + "\n".join(text_parts),
            )

        # 重置计数器
        self._monitor_life_notification_queue["life"] = {
            "strm_count": 0,
            "mediainfo_count": 0,
        }

    def _get_path_by_cid(self, cid: int) -> Optional[Path]:
        """
        通过 cid 获取路径
        先从缓存获取，再从数据库获取，最后通过API获取
        """
        if int(cid) == 0:
            return Path("/")
        _databasehelper = FileDbHelper()
        dir_path = idpathcacher.get_dir_by_id(cid)
        if not dir_path:
            data = _databasehelper.get_by_id(id=cid)
            if data:
                dir_path = data.get("path", "")
                if dir_path:
                    logger.debug(f"获取 {cid} 路径（数据库）: {dir_path}")
                    idpathcacher.add_cache(id=cid, directory=str(dir_path))
                    return Path(dir_path)
            dir_path = get_path(
                client=self._client,
                attr=cid,
                root_id=None,
                **configer.get_ios_ua_app(app=False),
            )
            if not dir_path:
                logger.error(f"获取 {cid} 路径失败")
                return None
            if dir_path.startswith("根目录"):
                dir_path = dir_path[3:]
            idpathcacher.add_cache(id=cid, directory=str(dir_path))
            logger.debug(f"获取 {cid} 路径（API）: {dir_path}")
            return Path(dir_path)
        logger.debug(f"获取 {cid} 路径（缓存）: {dir_path}")
        return Path(dir_path)

    def media_transfer(self, event: Dict, file_path: Path, rmt_mediaext):
        """
        运行媒体文件整理
        :param event: 事件
        :param file_path: 文件路径
        :param rmt_mediaext: 媒体文件后缀名
        """
        org_file_path = file_path.as_posix()
        _databasehelper = FileDbHelper()
        transferchain = TransferChain()
        file_category = event["file_category"]
        file_id = event["file_id"]
        if file_category == 0:
            cache_top_path = False
            cache_file_id_list = []
            logger.info(f"【网盘整理】开始处理 {file_path} 文件夹中...")
            _databasehelper.remove_by_id_batch(int(event["file_id"]), False)
            # 文件夹情况，遍历文件夹，获取整理文件
            # 缓存顶层文件夹ID
            if str(event["file_id"]) not in pantransfercacher.delete_pan_transfer_list:
                pantransfercacher.delete_pan_transfer_list.append(str(event["file_id"]))
            for item in iter_files_with_path(
                self._client,
                cid=int(file_id),
                with_ancestors=True,
                cooldown=2,
                **configer.get_ios_ua_app(),
            ):
                try:
                    check_iter_path_data(item)
                except FileItemKeyMiss as e:
                    logger.warning(f"【网盘整理】数据拉取异常: {e}")
                    continue
                file_path = Path(item["path"])
                if not PathUtils.has_prefix(file_path, org_file_path):
                    continue
                # 缓存文件夹ID
                if (
                    str(item["parent_id"])
                    not in pantransfercacher.delete_pan_transfer_list
                ):
                    pantransfercacher.delete_pan_transfer_list.append(
                        str(item["parent_id"])
                    )
                if file_path.suffix.lower() in rmt_mediaext:
                    # 缓存文件ID
                    if (
                        str(item["id"])
                        not in pantransfercacher.creata_pan_transfer_list
                    ):
                        pantransfercacher.creata_pan_transfer_list.append(
                            str(item["id"])
                        )
                    # 判断此顶层目录MP是否能处理
                    if str(item["parent_id"]) != event["file_id"]:
                        cache_top_path = True
                    if str(item["id"]) not in cache_file_id_list:
                        cache_file_id_list.append(str(item["id"]))
                    fileitem = FileItem(
                        storage=configer.storage_module
                        if not configer.pan_transfer_clouddrive2_config.enabled
                        else "CloudDrive储存",
                        fileid=str(item["id"]),
                        parent_fileid=str(item["parent_id"]),
                        path=(
                            (
                                Path(configer.pan_transfer_clouddrive2_config.prefix)
                                / file_path.as_posix().lstrip("/")
                            ).as_posix()
                            if configer.pan_transfer_clouddrive2_config.enabled
                            else file_path.as_posix()
                        ),
                        type="file",
                        name=file_path.name,
                        basename=file_path.stem,
                        extension=file_path.suffix[1:].lower(),
                        size=item["size"],
                        pickcode=item["pickcode"],
                        modify_time=item["ctime"],
                    )
                    transferchain.do_transfer(fileitem=fileitem)
                    logger.info(f"【网盘整理】{file_path} 加入整理列队")
                if (
                    file_path.suffix.lower() in settings.RMT_AUDIOEXT
                    or file_path.suffix.lower() in settings.RMT_SUBEXT
                ):
                    # 如果是MP可处理的音轨或字幕文件，则缓存文件ID
                    if (
                        str(item["id"])
                        not in pantransfercacher.creata_pan_transfer_list
                    ):
                        pantransfercacher.creata_pan_transfer_list.append(
                            str(item["id"])
                        )

            # 顶层目录MP无法处理时添加到缓存字典中
            if cache_top_path and cache_file_id_list:
                if (
                    str(event["file_id"])
                    in pantransfercacher.top_delete_pan_transfer_list
                ):
                    # 如果存在相同ID的根目录则合并
                    cache_file_id_list = list(
                        dict.fromkeys(
                            chain(
                                cache_file_id_list,
                                pantransfercacher.top_delete_pan_transfer_list[
                                    str(event["file_id"])
                                ],
                            )
                        )
                    )
                    del pantransfercacher.top_delete_pan_transfer_list[
                        str(event["file_id"])
                    ]
                pantransfercacher.top_delete_pan_transfer_list[
                    str(event["file_id"])
                ] = cache_file_id_list
        else:
            # 文件情况，直接整理
            if file_path.suffix.lower() in rmt_mediaext:
                _databasehelper.remove_by_id("file", event["file_id"])
                # 缓存文件ID
                if (
                    str(event["file_id"])
                    not in pantransfercacher.creata_pan_transfer_list
                ):
                    pantransfercacher.creata_pan_transfer_list.append(
                        str(event["file_id"])
                    )
                fileitem = FileItem(
                    storage=configer.storage_module
                    if not configer.pan_transfer_clouddrive2_config.enabled
                    else "CloudDrive储存",
                    fileid=str(file_id),
                    parent_fileid=str(event["parent_id"]),
                    path=(
                        (
                            Path(configer.pan_transfer_clouddrive2_config.prefix)
                            / file_path.as_posix().lstrip("/")
                        ).as_posix()
                        if configer.pan_transfer_clouddrive2_config.enabled
                        else file_path.as_posix()
                    ),
                    type="file",
                    name=file_path.name,
                    basename=file_path.stem,
                    extension=file_path.suffix[1:].lower(),
                    size=event["file_size"],
                    pickcode=event["pick_code"],
                    modify_time=event["update_time"],
                )
                transferchain.do_transfer(fileitem=fileitem)
                logger.info(f"【网盘整理】{file_path} 加入整理列队")

    def creata_strm(self, event: Dict, file_path: Path):
        """
        创建 STRM 文件
        """
        _databasehelper = FileDbHelper()

        _get_url = StrmUrlGetter()

        org_file_path = file_path.as_posix()
        pickcode = event["pick_code"]
        file_category = event["file_category"]
        file_id = event["file_id"]
        status, target_dir, pan_media_dir = PathUtils.get_media_path(
            configer.get_config("monitor_life_paths"), file_path
        )
        if not status:
            return
        logger.debug("【监控生活事件】匹配到网盘文件夹路径: %s", str(pan_media_dir))

        if file_category == 0:
            # 文件夹情况，遍历文件夹
            mediainfo_count = 0
            strm_count = 0
            _databasehelper.upsert_batch(
                _databasehelper.process_life_dir_item(
                    event=event, file_path=file_path.as_posix()
                )
            )
            for batch in batched(
                iter_files_with_path(
                    self._client,
                    cid=int(file_id),
                    with_ancestors=True,
                    cooldown=2,
                    **configer.get_ios_ua_app(),
                ),
                7_000,
            ):
                processed = []
                for item in batch:
                    try:
                        check_iter_path_data(item)
                    except FileItemKeyMiss as e:
                        logger.warning(f"【监控生活事件】数据拉取异常: {e}")
                        continue
                    _process_item = _databasehelper.process_item(item)
                    if _process_item not in processed:
                        processed.extend(_process_item)
                    if item["is_dir"]:
                        continue
                    if "creata" in configer.get_config("monitor_life_event_modes"):  # pylint: disable=E1135
                        file_path = item["path"]
                        if not PathUtils.has_prefix(file_path, org_file_path):
                            continue
                        file_path = Path(target_dir) / Path(file_path).relative_to(
                            pan_media_dir
                        )
                        file_target_dir = file_path.parent
                        original_file_name = file_path.name
                        file_name = StrmGenerater.get_strm_filename(file_path)
                        new_file_path = file_target_dir / file_name

                        if configer.get_config(
                            "monitor_life_auto_download_mediainfo_enabled"
                        ):
                            if file_path.suffix.lower() in self.download_mediaext_set:
                                if not (
                                    result
                                    := MediainfoDownloadMiddleware.should_download(
                                        filename=original_file_name,
                                        blacklist_automaton=self.mdab,
                                        whitelist_automaton=self.mdaw,
                                    )
                                )[1]:
                                    logger.warning(
                                        "【监控生活事件】%s，跳过网盘路径: %s",
                                        result[0],
                                        item["path"],
                                    )
                                    continue

                                pickcode = item["pickcode"]
                                if not pickcode:
                                    logger.error(
                                        f"【监控生活事件】{original_file_name} 不存在 pickcode 值，无法下载该文件"
                                    )
                                    continue
                                download_url = (
                                    self.mediainfodownloader.get_download_url(
                                        pickcode=pickcode
                                    )
                                )

                                if not download_url:
                                    logger.error(
                                        f"【监控生活事件】{original_file_name} 下载链接获取失败，无法下载该文件"
                                    )
                                    continue

                                self.mediainfodownloader.save_mediainfo_file(
                                    file_path=Path(file_path),
                                    file_name=original_file_name,
                                    download_url=download_url,
                                )
                                mediainfo_count += 1
                                continue

                        if file_path.suffix.lower() not in self.rmt_mediaext_set:
                            logger.warn(
                                "【监控生活事件】跳过网盘路径: %s",
                                item["path"],
                            )
                            continue

                        if not (
                            result := StrmGenerater.should_generate_strm(
                                original_file_name, "life", item.get("size", None)
                            )
                        )[1]:
                            logger.warn(
                                f"【监控生活事件】{result[0]}，跳过网盘路径: {item['path']}"
                            )
                            continue

                        pickcode = item["pickcode"]
                        if not pickcode:
                            pickcode = item["pick_code"]

                        new_file_path.parent.mkdir(parents=True, exist_ok=True)

                        if not pickcode:
                            logger.error(
                                f"【监控生活事件】{original_file_name} 不存在 pickcode 值，无法生成 STRM 文件"
                            )
                            continue
                        if not (len(pickcode) == 17 and str(pickcode).isalnum()):
                            logger.error(
                                f"【监控生活事件】错误的 pickcode 值 {pickcode}，无法生成 STRM 文件"
                            )
                            continue

                        strm_url = _get_url.get_strm_url(
                            pickcode, original_file_name, item["path"]
                        )

                        with open(new_file_path, "w", encoding="utf-8") as file:
                            file.write(strm_url)
                        logger.info(
                            "【监控生活事件】生成 STRM 文件成功: %s",
                            str(new_file_path),
                        )
                        strm_count += 1
                        scrape_metadata = True
                        if configer.get_config("monitor_life_scrape_metadata_enabled"):
                            if configer.get_config(
                                "monitor_life_scrape_metadata_exclude_paths"
                            ):
                                if PathUtils.get_scrape_metadata_exclude_path(
                                    configer.get_config(
                                        "monitor_life_scrape_metadata_exclude_paths"
                                    ),
                                    str(new_file_path),
                                ):
                                    logger.debug(
                                        f"【监控生活事件】匹配到刮削排除目录，不进行刮削: {new_file_path}"
                                    )
                                    scrape_metadata = False
                            if scrape_metadata:
                                media_scrape_metadata(path=new_file_path)
                        # 刷新媒体服务器
                        self.mediaserver_helper.refresh_mediaserver(
                            file_path=str(new_file_path),
                            file_name=str(original_file_name),
                        )
                        if configer.monitor_life_emby_mediainfo_enabled and item.get(
                            "sha1"
                        ):
                            emby_mediainfo_queue.enqueue(
                                func_name="【监控生活事件】",
                                sha1=item["sha1"],
                                path=Path(new_file_path),
                                mp_mediaserver=configer.monitor_life_mp_mediaserver_paths,
                                mediaservers=configer.monitor_life_mediaservers,
                                size=item["size"],
                            )
                _databasehelper.upsert_batch(processed)
            if configer.get_config("notify"):
                if strm_count > 0 or mediainfo_count > 0:
                    self._monitor_life_notification_queue["life"]["strm_count"] += (
                        strm_count
                    )
                    self._monitor_life_notification_queue["life"][
                        "mediainfo_count"
                    ] += mediainfo_count
                    self._schedule_notification()
        else:
            file_path_string = file_path.as_posix()
            _databasehelper.upsert_batch(
                _databasehelper.process_life_file_item(
                    event=event, file_path=file_path_string
                )
            )
            if "creata" in configer.get_config("monitor_life_event_modes"):  # pylint: disable=E1135
                # 文件情况，直接生成
                file_path = Path(target_dir) / Path(file_path).relative_to(
                    pan_media_dir
                )
                file_target_dir = file_path.parent
                original_file_name = file_path.name
                file_name = StrmGenerater.get_strm_filename(file_path)
                new_file_path = file_target_dir / file_name

                if configer.get_config("monitor_life_auto_download_mediainfo_enabled"):
                    if file_path.suffix.lower() in self.download_mediaext_set:
                        if not (
                            result := MediainfoDownloadMiddleware.should_download(
                                filename=original_file_name,
                                blacklist_automaton=self.mdab,
                                whitelist_automaton=self.mdaw,
                            )
                        )[1]:
                            logger.warning(
                                "【监控生活事件】%s，跳过网盘路径: %s",
                                result[0],
                                str(file_path).replace(str(target_dir), "", 1),
                            )
                            return

                        if not pickcode:
                            logger.error(
                                f"【监控生活事件】{original_file_name} 不存在 pickcode 值，无法下载该文件"
                            )
                            return
                        download_url = self.mediainfodownloader.get_download_url(
                            pickcode=pickcode
                        )

                        if not download_url:
                            logger.error(
                                f"【监控生活事件】{original_file_name} 下载链接获取失败，无法下载该文件"
                            )
                            return

                        self.mediainfodownloader.save_mediainfo_file(
                            file_path=Path(file_path),
                            file_name=original_file_name,
                            download_url=download_url,
                        )
                        # 下载的元数据写入缓存，与整理事件对比
                        lifeeventcacher.create_strm_file_dict[str(event["file_id"])] = [
                            event["file_name"],
                            target_dir,
                            pan_media_dir,
                        ]
                        if configer.get_config("notify"):
                            self._monitor_life_notification_queue["life"][
                                "mediainfo_count"
                            ] += 1
                            self._schedule_notification()
                        return

                if file_path.suffix.lower() not in self.rmt_mediaext_set:
                    logger.warn(
                        "【监控生活事件】跳过网盘路径: %s",
                        str(file_path).replace(str(target_dir), "", 1),
                    )
                    return

                if not (
                    result := StrmGenerater.should_generate_strm(
                        original_file_name, "life", event.get("file_size", None)
                    )
                )[1]:
                    logger.warn(
                        f"【监控生活事件】{result[0]}，跳过网盘路径: {str(file_path).replace(str(target_dir), '', 1)}"
                    )
                    return

                new_file_path.parent.mkdir(parents=True, exist_ok=True)

                if not pickcode:
                    logger.error(
                        f"【监控生活事件】{original_file_name} 不存在 pickcode 值，无法生成 STRM 文件"
                    )
                    return
                if not (len(pickcode) == 17 and str(pickcode).isalnum()):
                    logger.error(
                        f"【监控生活事件】错误的 pickcode 值 {pickcode}，无法生成 STRM 文件"
                    )
                    return

                strm_url = _get_url.get_strm_url(
                    pickcode, original_file_name, file_path=file_path_string
                )

                with open(new_file_path, "w", encoding="utf-8") as file:
                    file.write(strm_url)
                logger.info(
                    "【监控生活事件】生成 STRM 文件成功: %s", str(new_file_path)
                )
                # 生成的STRM写入缓存，与整理事件对比
                lifeeventcacher.create_strm_file_dict[str(event["file_id"])] = [
                    event["file_name"],
                    target_dir,
                    pan_media_dir,
                ]
                if configer.get_config("notify"):
                    self._monitor_life_notification_queue["life"]["strm_count"] += 1
                    self._schedule_notification()
                scrape_metadata = True
                if configer.get_config("monitor_life_scrape_metadata_enabled"):
                    if configer.get_config(
                        "monitor_life_scrape_metadata_exclude_paths"
                    ):
                        if PathUtils.get_scrape_metadata_exclude_path(
                            configer.get_config(
                                "monitor_life_scrape_metadata_exclude_paths"
                            ),
                            str(new_file_path),
                        ):
                            logger.debug(
                                f"【监控生活事件】匹配到刮削排除目录，不进行刮削: {new_file_path}"
                            )
                            scrape_metadata = False
                    if scrape_metadata:
                        media_scrape_metadata(path=new_file_path)
                # 刷新媒体服务器
                self.mediaserver_helper.refresh_mediaserver(
                    file_path=new_file_path.as_posix(),
                    file_name=str(original_file_name),
                )
                if configer.monitor_life_emby_mediainfo_enabled and event.get("sha1"):
                    emby_mediainfo_queue.enqueue(
                        func_name="【监控生活事件】",
                        sha1=event["sha1"],
                        path=Path(new_file_path),
                        mp_mediaserver=configer.monitor_life_mp_mediaserver_paths,
                        mediaservers=configer.monitor_life_mediaservers,
                        size=event["file_size"],
                    )

    def remove_strm(self, event: Dict):
        """
        删除 STRM 文件
        """

        # def __get_file_path(
        #     file_name: str, file_size: str, file_id: str, file_category: int
        # ):
        #     """
        #     通过 还原文件/文件夹 再删除 获取文件路径
        #     """
        #     for item in self._client.recyclebin_list()["data"]:
        #         if (
        #             file_category == 0
        #             and str(item["file_name"]) == file_name
        #             and str(item["type"]) == "2"
        #         ) or (
        #             file_category != 0
        #             and str(item["file_name"]) == file_name
        #             and str(item["file_size"]) == file_size
        #         ):
        #             resp = self._client.recyclebin_revert(item["id"])
        #             if resp["state"]:
        #                 time.sleep(1)
        #                 path = get_path_to_cid(self._client, cid=int(item["cid"]))
        #                 time.sleep(1)
        #                 self._client.fs_delete(file_id)
        #                 return str(Path(path) / item["file_name"])
        #             else:
        #                 return None
        #     return None

        _databasehelper = FileDbHelper()

        file_path = None
        file_category = event["file_category"]
        file_item = _databasehelper.get_by_id(int(event["file_id"]))
        if file_item:
            file_path = file_item.get("path", "")
        if not file_path:
            logger.debug(
                f"【监控生活事件】{event['file_name']} 无法通过数据库获取路径，防止误删不处理"
            )
            return
        logger.debug(f"【监控生活事件】通过数据库获取路径：{file_path}")

        pan_file_path = file_path
        # 优先匹配待整理目录，如果删除的目录为待整理目录则不进行操作
        if configer.get_config("pan_transfer_enabled") and configer.get_config(
            "pan_transfer_paths"
        ):
            if PathUtils.get_run_transfer_path(
                paths=configer.get_config("pan_transfer_paths"),
                transfer_path=file_path,
            ):
                logger.debug(
                    f"【监控生活事件】{file_path} 为待整理目录下的路径，不做处理"
                )
                return

        # 匹配是否是媒体文件夹目录
        status, target_dir, pan_media_dir = PathUtils.get_media_path(
            configer.get_config("monitor_life_paths"), file_path
        )
        if not status:
            return
        logger.debug("【监控生活事件】匹配到网盘文件夹路径: %s", str(pan_media_dir))

        # 清理数据库此路径记录
        _databasehelper.remove_by_path(
            path_type="folder" if file_category == 0 else "file",
            path=str(pan_file_path),
        )

        # 检查文件是否还存在
        storagechain = StorageChain()
        fileitem = storagechain.get_file_item(
            storage=configer.storage_module, path=Path(file_path)
        )
        if fileitem:
            logger.warn(
                f"【监控生活事件】网盘 {file_path} 目录存在，跳过本地删除: {fileitem}"
            )
            # 这里如果路径存在则更新数据库信息
            _databasehelper.upsert_batch(
                _databasehelper.process_fileitem(fileitem=fileitem)
            )
            return

        file_path = Path(target_dir) / Path(file_path).relative_to(pan_media_dir)
        if file_path.suffix.lower() in self.rmt_mediaext_set:
            file_target_dir = file_path.parent
            file_name = StrmGenerater.get_strm_filename(file_path)
            file_path = file_target_dir / file_name
        logger.info(
            f"【监控生活事件】删除本地{'文件夹' if file_category == 0 else '文件'}: {file_path}"
        )
        try:
            if not Path(file_path).exists():
                logger.warn(f"【监控生活事件】本地 {file_path} 不存在，跳过删除")
                return
            if file_category == 0:
                # 删除目录
                rmtree(Path(file_path))
            else:
                # 删除文件
                Path(file_path).unlink(missing_ok=True)
                # 判断父目录是否需要删除
                PathRemoveUtils.remove_parent_dir(
                    file_path=Path(file_path),
                    mode=["strm"],
                    func_type="【监控生活事件】",
                )
            # 清理数据库所有路径
            _databasehelper.remove_by_path_batch(
                path=str(pan_file_path), only_file=False
            )
            logger.info(f"【监控生活事件】{file_path} 已删除")
            # 同步删除历史记录
            if configer.monitor_life_remove_mp_history:
                mediasyncdel = MediaSyncDelHelper()
                (
                    del_torrent_hashs,
                    stop_torrent_hashs,
                    error_cnt,
                    transfer_history,
                ) = mediasyncdel.remove_by_path(
                    path=pan_file_path,
                    del_source=configer.monitor_life_remove_mp_source,
                )
                if configer.get_config("notify") and transfer_history:
                    torrent_cnt_msg = ""
                    if del_torrent_hashs:
                        torrent_cnt_msg += (
                            i18n.translate(
                                "sync_del_torrent_count",
                                count=len(set(del_torrent_hashs)),
                            )
                            + "\n"
                        )
                    if stop_torrent_hashs:
                        stop_cnt = 0
                        # 排除已删除
                        for stop_hash in set(stop_torrent_hashs):
                            if stop_hash not in set(del_torrent_hashs):
                                stop_cnt += 1
                        if stop_cnt > 0:
                            torrent_cnt_msg += (
                                i18n.translate("sync_del_stop_count", count=stop_cnt)
                                + "\n"
                            )
                    if error_cnt:
                        torrent_cnt_msg += (
                            i18n.translate("sync_del_error_count", count=error_cnt)
                            + "\n"
                        )
                    del_type_text = (
                        i18n.translate("life_del_folder", path=pan_file_path)
                        if file_category == 0
                        else i18n.translate("life_del_file", path=pan_file_path)
                    )
                    post_message(
                        mtype=NotificationType.Plugin,
                        title=i18n.translate("life_sync_media_del_title"),
                        text=f"\n{del_type_text}\n"
                        f"{i18n.translate('sync_del_record_count', count=len(transfer_history) if transfer_history else 0)}\n"
                        f"{torrent_cnt_msg}"
                        f"时间 {strftime('%Y-%m-%d %H:%M:%S', localtime(time()))}\n",
                    )
        except Exception as e:
            logger.error(f"【监控生活事件】{file_path} 删除失败: {e}")

    def new_creata_path(self, event: Dict):
        """
        处理新出现的路径
        """
        # 1.获取绝对文件路径
        file_name = event["file_name"]
        dir_path = self._get_path_by_cid(int(event["parent_id"]))
        file_path = Path(dir_path) / file_name
        # 匹配逻辑 整理路径目录 > 生成STRM文件路径目录
        # 2.匹配是否为整理路径目录
        if configer.get_config("pan_transfer_enabled") and configer.get_config(
            "pan_transfer_paths"
        ):
            if PathUtils.get_run_transfer_path(
                paths=configer.get_config("pan_transfer_paths"),
                transfer_path=file_path,
            ):
                self.media_transfer(
                    event=event,
                    file_path=Path(file_path),
                    rmt_mediaext=self.rmt_mediaext,
                )
                return
        # 3.匹配是否为生成STRM文件路径目录
        if configer.get_config("monitor_life_enabled") and configer.get_config(
            "monitor_life_paths"
        ):
            if str(event["file_id"]) in pantransfercacher.creata_pan_transfer_list:
                # 检查是否命中缓存
                pantransfercacher.creata_pan_transfer_list.remove(str(event["file_id"]))
                if "transfer" in configer.get_config("monitor_life_event_modes"):  # pylint: disable=E1135
                    self.creata_strm(event=event, file_path=file_path)
            else:
                self.creata_strm(event=event, file_path=file_path)

    def _wait_for_transfer_complete(self):
        """
        等待 MoviePilot 整理任务完成
        """
        wait_start_time = None
        last_info_time = None

        while True:
            if not TransferChain().get_queue_tasks():
                break

            if wait_start_time is None:
                wait_start_time = time()
                last_info_time = wait_start_time

            wait_duration = time() - wait_start_time
            wait_duration_minutes = int(wait_duration // 60)

            if wait_duration >= 15 * 60:
                time_since_last_info = time() - last_info_time
                if time_since_last_info >= 60:
                    logger.info(
                        f"【监控生活事件】MoviePilot 整理运行中，已等待 {wait_duration_minutes} 分钟，"
                        "等待整理完成后继续监控生活事件..."
                    )
                    last_info_time = time()
            else:
                logger.debug(
                    "【监控生活事件】MoviePilot 整理运行中，等待整理完成后继续监控生活事件..."
                )

            if self.stop_event and self.stop_event.wait(timeout=20):
                return True

        return False

    def once_pull(self, from_time, from_id):
        """
        单次拉取
        """
        if self._wait_for_transfer_complete():
            return from_time, from_id

        events_batch: List = []
        for attempt in range(3, -1, -1):
            try:
                # 每次尝试先清空旧的值
                events_batch: List = []

                events_iterator = iter_life_behavior_once(
                    client=self._client,
                    from_time=from_time,
                    from_id=from_id,
                    cooldown=4,
                    **configer.get_ios_ua_app(),
                )

                try:
                    first_event = next(events_iterator)
                except P115AuthenticationError:
                    logger.error("【监控生活事件】登入失效，请重新扫码登入")
                    break
                except StopIteration:
                    # 迭代器为空，没有数据，属于正常情况
                    break

                if "update_time" not in first_event or "id" not in first_event:
                    break

                events_batch = [first_event]
                events_batch.extend(list(events_iterator))
                break
            except Exception as e:
                if attempt <= 0:
                    logger.error(f"【监控生活事件】拉取数据失败：{e}")
                    raise
                logger.warn(
                    f"【监控生活事件】拉取数据失败，剩余重试次数 {attempt} 次：{e}"
                )
                if self.stop_event and self.stop_event.wait(timeout=2):
                    return from_time, from_id

        if not events_batch:
            if self.stop_event and self.stop_event.wait(timeout=20):
                return from_time, from_id
            elif not self.stop_event:
                sleep(20)
            return from_time, from_id

        db_helper = LifeEventDbHelper()
        db_helper.upsert_batch_by_list(events_batch)

        return_from_time: int = from_time
        return_from_id: int = from_id
        wait_time = configer.monitor_life_event_wait_time
        if wait_time < 0:
            wait_time = 0
        process_time: int = int(time()) - wait_time
        process_item: bool = False
        for event in reversed(events_batch):
            self.rmt_mediaext = [
                f".{ext.strip()}"
                for ext in configer.get_config("user_rmt_mediaext")
                .replace("，", ",")
                .split(",")
            ]
            self.rmt_mediaext_set = set(self.rmt_mediaext)
            self.download_mediaext_set = {
                f".{ext.strip()}"
                for ext in configer.get_config("user_download_mediaext")
                .replace("，", ",")
                .split(",")
            }

            logger.debug(
                f"【监控生活事件】{BEHAVIOR_TYPE_TO_NAME.get(event['type'], '未知类型')}: {event}"
            )

            if (
                int(event["type"]) != 1
                and int(event["type"]) != 2
                and int(event["type"]) != 5
                and int(event["type"]) != 6
                and int(event["type"]) != 14
                and int(event["type"]) != 17
                and int(event["type"]) != 18
                and int(event["type"]) != 22
            ):
                continue

            if wait_time == 0:
                return_from_id = int(event["id"])
                return_from_time = int(event["update_time"])
            elif self.tasks_queue.exist(event):
                if not self.tasks_queue.time_done(process_time):
                    continue
                old_event = self.tasks_queue.pop()
                return_from_id = int(event["id"])
                return_from_time = int(event["update_time"])
                if old_event["file_name"] != event["file_name"]:
                    logger.info(
                        f"【监控生活事件】{event['id']} 文件名称改变：{old_event['file_name']} -> {event['file_name']}"
                    )
                process_item = True
            elif self.tasks_queue.inq(event) and self.tasks_queue.time_done(
                process_time
            ):
                logger.warning("【监控生活事件】生活事件等待队列出错，清空重新拉取...")
                self.tasks_queue.clear()
                break
            elif not self.tasks_queue.inq(event):
                self.tasks_queue.add(event)
                logger.info(
                    f"【监控生活事件】{BEHAVIOR_TYPE_TO_NAME.get(event['type'], '未知类型')} "
                    f"{event['id']} {event['file_name']} 加入等待队列"
                )
                continue
            else:
                continue

            if (
                int(event["type"]) == 1
                or int(event["type"]) == 2
                or int(event["type"]) == 5
                or int(event["type"]) == 6
                or int(event["type"]) == 14
                or int(event["type"]) == 18
            ):
                # 新路径事件处理
                self.new_creata_path(event=event)

            if int(event["type"]) == 22:
                # 删除文件/文件夹事件处理
                if str(event["file_id"]) in pantransfercacher.delete_pan_transfer_list:
                    # 检查是否命中删除文件夹缓存，命中则无需处理
                    pantransfercacher.delete_pan_transfer_list.remove(
                        str(event["file_id"])
                    )
                else:
                    if (
                        configer.get_config("monitor_life_enabled")
                        and configer.get_config("monitor_life_paths")
                        and "remove" in configer.get_config("monitor_life_event_modes")  # pylint: disable=E1135
                    ):
                        self.remove_strm(event=event)

            if int(event["type"]) == 17:
                # 对于创建文件夹事件直接写入数据库
                _databasehelper = FileDbHelper()
                file_name = event["file_name"]
                dir_path = self._get_path_by_cid(int(event["parent_id"]))
                file_path = Path(dir_path) / file_name
                # 待整理目录跳过处理
                if configer.pan_transfer_enabled and configer.pan_transfer_paths:
                    if PathUtils.get_run_transfer_path(
                        paths=configer.pan_transfer_paths,
                        transfer_path=file_path.as_posix(),
                    ):
                        continue
                # 未识别目录跳过处理
                if configer.pan_transfer_unrecognized_path:
                    if PathUtils.has_prefix(
                        file_path.as_posix(), configer.pan_transfer_unrecognized_path
                    ):
                        continue
                _databasehelper.upsert_batch(
                    _databasehelper.process_life_dir_item(
                        event=event, file_path=file_path
                    )
                )

        if not process_item:
            if self.stop_event and self.stop_event.wait(timeout=20):
                return return_from_time, return_from_id
            elif not self.stop_event:
                sleep(20)

        return return_from_time, return_from_id

    def once_transfer(self, path: str) -> None:
        """
        手动运行网盘整理

        :param path: 网盘路径
        """
        if not path or not isinstance(path, str):
            logger.error(f"【监控生活事件】无效的路径参数: {path}")
            return

        logger.info(f"【监控生活事件】开始手动运行网盘整理，路径: {path}")

        total_files = 0
        total_dirs = 0
        success_count = 0
        failed_count = 0
        skipped_count = 0
        failed_items = []

        try:
            self.rmt_mediaext = [
                f".{ext.strip()}"
                for ext in configer.user_rmt_mediaext.replace("，", ",").split(",")
            ]

            try:
                parent_id = get_pid_by_path(self._client, path, True, True, True)
                logger.info(
                    f"【监控生活事件】网盘媒体目录 ID 获取成功: {path} -> {parent_id}"
                )
            except Exception as e:
                logger.error(f"【监控生活事件】网盘媒体目录 ID 获取失败: {path} {e}")
                return

            logger.info(f"【监控生活事件】开始遍历目录: {path}")
            try:
                for batch_count, data in enumerate(
                    iter_fs_files(
                        self._client,
                        parent_id,
                        cooldown=2,
                        **configer.get_ios_ua_app(app=False),
                    ),
                    1,
                ):
                    if not data:
                        logger.debug(
                            f"【监控生活事件】第 {batch_count} 批数据为空，跳过"
                        )
                        continue
                    items = data.get("data", [])
                    if not items:
                        logger.debug(
                            f"【监控生活事件】第 {batch_count} 批数据中无文件项，跳过"
                        )
                        continue
                    logger.debug(
                        f"【监控生活事件】处理第 {batch_count} 批数据，包含 {len(items)} 个项目"
                    )
                    for item_index, item in enumerate(items, 1):
                        item_type = "未知"
                        item_name = "未知"
                        try:
                            item = normalize_attr(item)
                            item_name = item.get("name")
                            item_id = item.get("id")
                            item_type = "文件夹" if item.get("is_dir") else "文件"

                            if item.get("is_dir"):
                                total_dirs += 1
                            else:
                                total_files += 1

                            file_path = Path(path) / item_name

                            event = {
                                "file_category": 0 if item.get("is_dir") else 1,
                                "file_id": item.get("id"),
                                "parent_id": item.get("parent_id"),
                                "file_size": item.get("size", 0),
                                "pick_code": item.get("pickcode", ""),
                                "update_time": item.get("ctime", 0),
                                "file_name": item_name,
                            }

                            logger.debug(
                                f"【监控生活事件】处理 {item_type} [{batch_count}-{item_index}]: "
                                f"{item_name} (ID: {item_id})"
                            )
                            self.media_transfer(
                                event=event,
                                file_path=file_path,
                                rmt_mediaext=self.rmt_mediaext,
                            )
                            success_count += 1
                        except Exception as e:
                            failed_count += 1
                            error_msg = f"{item_type} {item_name} 处理异常: {type(e).__name__}: {e}"
                            failed_items.append(error_msg)
                            logger.error(f"【监控生活事件】{error_msg}")
                            continue
                    processed = success_count + failed_count + skipped_count
                    logger.info(
                        f"【监控生活事件】已处理 {processed} 个项目 "
                        f"(成功: {success_count}, 失败: {failed_count}, 跳过: {skipped_count})"
                    )
            except StopIteration:
                pass
            except Exception as e:
                logger.error(
                    f"【监控生活事件】遍历文件时发生错误: 错误类型: {type(e).__name__}, 错误: {e}"
                )
        except Exception as e:
            logger.error(
                f"【监控生活事件】网盘整理过程中发生未预期的错误: "
                f"错误类型: {type(e).__name__}, 错误: {e}",
            )
        finally:
            total_processed = total_files + total_dirs
            logger.info(
                f"【监控生活事件】手动网盘整理完成 - 路径: {path}\n"
                f"  总计: {total_processed} 个项目 (文件: {total_files}, 文件夹: {total_dirs})\n"
                f"  成功: {success_count} 个\n"
                f"  失败: {failed_count} 个\n"
                f"  跳过: {skipped_count} 个"
            )
            if failed_items:
                logger.warning(
                    f"【监控生活事件】失败项目详情 ({len(failed_items)} 个):\n"
                    + "\n".join(f"  - {item}" for item in failed_items[:10])
                    + (
                        f"\n  ... 还有 {len(failed_items) - 10} 个失败项目"
                        if len(failed_items) > 10
                        else ""
                    )
                )

    def check_status(self):
        """
        检查生活事件开启状态
        """
        try:
            resp = life_show(
                self._client, timeout=5, **configer.get_ios_ua_app(app=False)
            )
            check_response(resp)
            return True
        except Exception as e:
            logger.error(f"【监控生活事件】生活事件开启失败: {e}")
            return False

    def start_manual_transfer(self, path: str) -> bool:
        """
        启动后台手动整理任务

        :param path: 网盘路径
        :return: 是否成功启动任务
        """
        if not path or not isinstance(path, str) or not path.strip():
            logger.error(f"【监控生活事件】无效的路径参数: {path}")
            return False

        path = path.strip()

        def run_transfer():
            try:
                logger.info(f"【监控生活事件】开始执行手动整理任务: {path}")
                self.once_transfer(path)
                logger.info(f"【监控生活事件】手动整理任务完成: {path}")
            except Exception as e:
                logger.error(f"【监控生活事件】手动整理任务执行失败: {path}, 错误: {e}")

        transfer_thread = Thread(target=run_transfer, daemon=True)
        transfer_thread.start()
        logger.info(f"【监控生活事件】已启动手动整理任务线程: {path}")
        return True
