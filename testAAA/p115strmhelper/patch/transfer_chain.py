from functools import wraps
from pathlib import Path
from threading import Lock
from typing import Optional, Tuple, Callable, TYPE_CHECKING

from app.log import logger

if TYPE_CHECKING:
    from ..helper.transfer import TransferTaskManager, TransferHandler


class TransferChainPatcher:
    """
    TransferChain 补丁管理器
    """

    _original_handle_transfer = None
    _enabled = False
    _task_manager: Optional["TransferTaskManager"] = None
    _handler: Optional["TransferHandler"] = None
    _storage_module: str = ""
    _lock = Lock()

    @classmethod
    def enable(
        cls,
        task_manager: "TransferTaskManager",
        handler: "TransferHandler",
        storage_module: str,
    ):
        """
        启用补丁

        :param task_manager: TransferTaskManager 实例
        :param handler: TransferHandler 实例
        :param storage_module: 存储模块名称
        """
        with cls._lock:
            if cls._enabled:
                logger.debug("【整理接管】补丁已启用，跳过")
                return

            try:
                from app.chain.transfer import TransferChain

                cls._task_manager = task_manager
                cls._handler = handler
                cls._storage_module = storage_module

                # 保存原方法
                cls._original_handle_transfer = (
                    TransferChain._TransferChain__handle_transfer
                )

                # 创建 patched 方法
                @wraps(cls._original_handle_transfer)
                def patched_handle_transfer(
                    self, task, callback: Optional[Callable] = None
                ) -> Optional[Tuple[bool, str]]:
                    return cls._patched_handle_transfer(self, task, callback)

                # 应用补丁
                TransferChain._TransferChain__handle_transfer = patched_handle_transfer
                cls._enabled = True
                logger.info("【整理接管】TransferChain 补丁已启用")

            except Exception as e:
                logger.error(f"【整理接管】启用补丁失败: {e}", exc_info=True)

    @classmethod
    def disable(cls):
        """
        禁用补丁
        """
        with cls._lock:
            if not cls._enabled:
                return

            try:
                from app.chain.transfer import TransferChain

                # 恢复原方法
                if cls._original_handle_transfer:
                    TransferChain._TransferChain__handle_transfer = (
                        cls._original_handle_transfer
                    )
                    cls._original_handle_transfer = None

                cls._task_manager = None
                cls._handler = None
                cls._storage_module = ""
                cls._enabled = False
                logger.info("【整理接管】TransferChain 补丁已禁用")

            except Exception as e:
                logger.error(f"【整理接管】禁用补丁失败: {e}", exc_info=True)

    @classmethod
    def _patched_handle_transfer(
        cls, chain_self, task, callback: Optional[Callable] = None
    ) -> Optional[Tuple[bool, str]]:
        """
        Patched 版本的 __handle_transfer
        """
        from app.chain.media import MediaChain
        from app.chain.tmdb import TmdbChain
        from app.core.config import settings
        from app.core.context import MediaInfo
        from app.db.transferhistory_oper import TransferHistoryOper
        from app.helper.directory import DirectoryHelper
        from app.schemas import Notification
        from app.schemas.types import MediaType, NotificationType

        from ..schemas.transfer import TransferTask as PluginTransferTask

        try:
            ########## 原始方法执行部分 ##########

            transferhis = TransferHistoryOper()
            mediainfo = task.mediainfo
            mediainfo_changed = False
            if not mediainfo:
                download_history = task.download_history
                # 下载用户
                if download_history:
                    task.username = download_history.username
                    # 识别媒体信息
                    if download_history.tmdbid or download_history.doubanid:
                        # 下载记录中已存在识别信息
                        mediainfo: Optional[MediaInfo] = chain_self.recognize_media(
                            mtype=MediaType(download_history.type),
                            tmdbid=download_history.tmdbid,
                            doubanid=download_history.doubanid,
                            episode_group=download_history.episode_group,
                        )
                        if mediainfo:
                            # 更新自定义媒体类别
                            if download_history.media_category:
                                mediainfo.category = download_history.media_category
                else:
                    # 识别媒体信息
                    mediainfo = MediaChain().recognize_by_meta(task.meta)

                # 更新媒体图片
                if mediainfo:
                    chain_self.obtain_images(mediainfo=mediainfo)

                if not mediainfo:
                    # 新增整理失败历史记录
                    his = transferhis.add_fail(
                        fileitem=task.fileitem,
                        mode=task.transfer_type,
                        meta=task.meta,
                        downloader=task.downloader,
                        download_hash=task.download_hash,
                    )
                    chain_self.post_message(
                        Notification(
                            mtype=NotificationType.Manual,
                            title=f"{task.fileitem.name} 未识别到媒体信息，无法入库！",
                            text=f"回复：```\n/redo {his.id} [tmdbid]|[类型]\n``` 手动识别整理。",
                            username=task.username,
                            link=settings.MP_DOMAIN("#/history"),
                        )
                    )
                    # 任务失败，直接移除task
                    chain_self.jobview.remove_task(task.fileitem)
                    return False, "未识别到媒体信息"

                mediainfo_changed = True

            # 如果未开启新增已入库媒体是否跟随TMDB信息变化则根据tmdbid查询之前的title
            if not settings.SCRAP_FOLLOW_TMDB:
                transfer_history = transferhis.get_by_type_tmdbid(
                    tmdbid=mediainfo.tmdb_id, mtype=mediainfo.type.value
                )
                if transfer_history and mediainfo.title != transfer_history.title:
                    mediainfo.title = transfer_history.title
                    mediainfo_changed = True

            if mediainfo_changed:
                # 更新任务信息
                task.mediainfo = mediainfo
                # 更新队列任务
                curr_task = chain_self.jobview.remove_task(task.fileitem)
                chain_self.jobview.add_task(
                    task, state=curr_task.state if curr_task else "waiting"
                )

            # 获取集数据
            if task.mediainfo.type == MediaType.TV and not task.episodes_info:
                # 判断注意season为0的情况
                season_num = task.mediainfo.season
                if season_num is None and task.meta.season_seq:
                    if task.meta.season_seq.isdigit():
                        season_num = int(task.meta.season_seq)
                # 默认值1
                if season_num is None:
                    season_num = 1
                task.episodes_info = TmdbChain().tmdb_episodes(
                    tmdbid=task.mediainfo.tmdb_id,
                    season=season_num,
                    episode_group=task.mediainfo.episode_group,
                )

            # 查询整理目标目录
            if not task.target_directory:
                if task.target_path:
                    # 指定目标路径，`手动整理`场景下使用，忽略源目录匹配，使用指定目录匹配
                    task.target_directory = DirectoryHelper().get_dir(
                        media=task.mediainfo,
                        dest_path=task.target_path,
                        target_storage=task.target_storage,
                    )
                else:
                    # 启用源目录匹配时，根据源目录匹配下载目录，否则按源目录同盘优先原则，如无源目录，则根据媒体信息获取目标目录
                    task.target_directory = DirectoryHelper().get_dir(
                        media=task.mediainfo,
                        storage=task.fileitem.storage,
                        src_path=Path(task.fileitem.path),
                        target_storage=task.target_storage,
                    )
            if not task.target_storage and task.target_directory:
                task.target_storage = task.target_directory.library_storage

            source_storage = task.fileitem.storage
            target_storage = task.target_storage

            ########## 原始方法执行结束 ##########

            # 如果是目录（蓝光原盘），回退到原方法处理
            if task.fileitem.type == "dir":
                logger.debug(
                    f"【整理接管】检测到目录类型任务（可能是蓝光原盘），回退到原方法: {task.fileitem.path}"
                )
                return cls._call_original_transfer_part(chain_self, task, callback)

            if (
                cls._should_intercept(source_storage, target_storage)
                and cls._task_manager is not None
            ):
                logger.debug(
                    f"【整理接管】检测到 115 → 115 整理任务: {task.fileitem.name}"
                )

                # 如果是字幕或音频文件，直接忽略
                if cls._is_subtitle_or_audio_file(task.fileitem):
                    logger.debug(
                        f"【整理接管】忽略字幕/音频文件（将跟随主文件一起处理）: {task.fileitem.name}"
                    )
                    chain_self.jobview.running_task(task)
                    chain_self.jobview.finish_task(task)
                    if chain_self.jobview.is_done(task):
                        chain_self.jobview.remove_job(task)
                    return True, "已由插件接管（字幕/音频文件，跟随主文件处理）"

                # 注意：这个验证在 transfer_media 中进行，但由于我们拦截了，需要在这里进行
                if task.mediainfo.type == MediaType.TV and task.fileitem.type == "file":
                    if task.meta.begin_episode is None:
                        logger.warn(
                            f"【整理接管】文件 {task.fileitem.path} 整理失败：未识别到文件集数"
                        )
                        transferhis.add_fail(
                            fileitem=task.fileitem,
                            mode=task.transfer_type,
                            meta=task.meta,
                            downloader=task.downloader,
                            download_hash=task.download_hash,
                        )
                        chain_self.jobview.remove_task(task.fileitem)
                        return False, "未识别到文件集数"

                    # 文件结束季为空
                    task.meta.end_season = None
                    # 文件总季数为1
                    if task.meta.total_season:
                        task.meta.total_season = 1
                    # 文件不可能超过2集
                    if task.meta.total_episode and task.meta.total_episode > 2:
                        task.meta.total_episode = 1
                        task.meta.end_episode = None

                # 计算目标路径
                target_path = cls._compute_target_path(task)
                if not target_path:
                    logger.error(f"【整理接管】计算目标路径失败: {task.fileitem.path}")
                    # 回退到原方法
                    return cls._call_original_transfer_part(chain_self, task, callback)

                # 确定整理方式
                transfer_type = task.transfer_type
                if not transfer_type and task.target_directory:
                    transfer_type = task.target_directory.transfer_type

                # 获取覆盖模式
                overwrite_mode = None
                if task.target_directory:
                    overwrite_mode = task.target_directory.overwrite_mode

                # 正在处理
                chain_self.jobview.running_task(task)

                # 创建插件的 TransferTask
                plugin_task = PluginTransferTask(
                    fileitem=task.fileitem,
                    target_path=target_path,
                    mediainfo=task.mediainfo,
                    meta=task.meta,
                    transfer_type=transfer_type or "move",
                    overwrite_mode=overwrite_mode,
                    scrape=task.scrape,
                    need_notify=True,
                    manual=task.manual,
                    background=task.background,
                    username=task.username,
                    downloader=task.downloader,
                    download_hash=task.download_hash,
                )

                # 加入批量队列
                cls._task_manager.add_task(plugin_task)

                logger.info(
                    f"【整理接管】任务已加入批量队列: {task.fileitem.name} -> {target_path}"
                )

                return True, "已由插件接管"

            # 非 115 -> 115 原方法整理
            return cls._call_original_transfer_part(chain_self, task, callback)

        except Exception as e:
            logger.error(
                f"【整理接管】Patched handle_transfer 异常: {e}", exc_info=True
            )
            try:
                return cls._call_original(chain_self, task, callback)
            except Exception as fallback_error:
                logger.error(f"【整理接管】回退到原方法也失败: {fallback_error}")
                return False, f"整理异常: {e}"

    @classmethod
    def _is_subtitle_or_audio_file(cls, fileitem) -> bool:
        """
        判断是否为字幕或音频文件

        :param fileitem: 文件项
        :return: 是否为字幕或音频文件
        """
        try:
            from app.core.config import settings

            if not fileitem.extension:
                return False
            ext = f".{fileitem.extension.lower()}"
            if ext in settings.RMT_SUBEXT or ext in settings.RMT_AUDIOEXT:
                return True
            return False
        except Exception as e:
            logger.debug(f"【整理接管】判断字幕/音频文件失败: {e}")
            return False

    @classmethod
    def _should_intercept(cls, source_storage: str, target_storage: str) -> bool:
        """
        判断是否应该拦截

        :param source_storage: 源存储
        :param target_storage: 目标存储
        :return: 是否应该拦截
        """
        return (
            cls._enabled
            and cls._storage_module
            and source_storage == cls._storage_module
            and target_storage == cls._storage_module
        )

    @classmethod
    def _compute_target_path(cls, task) -> Optional[Path]:
        """
        使用 MoviePilot 的逻辑计算目标路径

        :param task: MoviePilot 的 TransferTask
        :return: 目标路径，失败返回 None
        """
        from app.core.config import settings
        from app.modules.filemanager.transhandler import TransHandler
        from app.schemas.types import MediaType

        try:
            # 获取重命名格式
            if task.mediainfo.type == MediaType.TV:
                rename_format = settings.TV_RENAME_FORMAT
            else:
                rename_format = settings.MOVIE_RENAME_FORMAT

            # 创建 TransHandler 实例
            handler = TransHandler()

            # 计算目标目录
            target_dir = handler.get_dest_dir(
                mediainfo=task.mediainfo,
                target_dir=task.target_directory,
            )

            if not target_dir:
                logger.error("【整理接管】计算目标目录失败")
                return None

            # 获取文件扩展名
            file_ext = Path(task.fileitem.name).suffix

            # 获取命名字典
            naming_dict = handler.get_naming_dict(
                meta=task.meta,
                mediainfo=task.mediainfo,
                file_ext=file_ext,
                episodes_info=task.episodes_info,
            )

            # 计算重命名路径
            rename_path = handler.get_rename_path(
                template_string=rename_format,
                rename_dict=naming_dict,
                path=target_dir,
            )

            # 确保返回 Path 对象
            if rename_path:
                return (
                    Path(rename_path)
                    if not isinstance(rename_path, Path)
                    else rename_path
                )
            return None

        except Exception as e:
            logger.error(f"【整理接管】计算目标路径失败: {e}", exc_info=True)
            return None

    @classmethod
    def _call_original(
        cls, chain_self, task, callback: Optional[Callable]
    ) -> Optional[Tuple[bool, str]]:
        """
        调用原方法

        :param chain_self: TransferChain 实例
        :param task: 任务
        :param callback: 回调
        :return: 原方法的返回值
        """
        if cls._original_handle_transfer:
            return cls._original_handle_transfer(chain_self, task, callback)
        return None

    @classmethod
    def _call_original_transfer_part(
        cls, chain_self, task, callback: Optional[Callable]
    ) -> Optional[Tuple[bool, str]]:
        """
        调用原方法的 transfer 部分

        :param chain_self: TransferChain 实例
        :param task: 任务
        :param callback: 回调
        :return: 返回值
        """
        from app.core.event import eventmanager
        from app.schemas import StorageOperSelectionEventData, TransferInfo
        from app.schemas.types import ChainEventType

        try:
            # 正在处理
            chain_self.jobview.running_task(task)

            # 获取源存储操作对象
            source_oper = None
            source_event_data = StorageOperSelectionEventData(
                storage=task.fileitem.storage
            )
            source_event = eventmanager.send_event(
                ChainEventType.StorageOperSelection, source_event_data
            )
            if source_event and source_event.event_data:
                source_event_data = source_event.event_data
                if source_event_data.storage_oper:
                    source_oper = source_event_data.storage_oper

            # 获取目标存储操作对象
            target_oper = None
            target_event_data = StorageOperSelectionEventData(
                storage=task.target_storage
            )
            target_event = eventmanager.send_event(
                ChainEventType.StorageOperSelection, target_event_data
            )
            if target_event and target_event.event_data:
                target_event_data = target_event.event_data
                if target_event_data.storage_oper:
                    target_oper = target_event_data.storage_oper

            # 执行整理
            transferinfo: TransferInfo = chain_self.transfer(
                fileitem=task.fileitem,
                meta=task.meta,
                mediainfo=task.mediainfo,
                target_directory=task.target_directory,
                target_storage=task.target_storage,
                target_path=task.target_path,
                transfer_type=task.transfer_type,
                episodes_info=task.episodes_info,
                scrape=task.scrape,
                library_type_folder=task.library_type_folder,
                library_category_folder=task.library_category_folder,
                source_oper=source_oper,
                target_oper=target_oper,
            )

            if not transferinfo:
                logger.error("文件整理模块运行失败")
                return False, "文件整理模块运行失败"

            if callback:
                return callback(task, transferinfo)

            return transferinfo.success, transferinfo.message

        except Exception as e:
            logger.error(f"【整理接管】执行 transfer 失败: {e}", exc_info=True)
            return False, f"整理失败: {e}"

        finally:
            chain_self.jobview.try_remove_job(task)
