import re
from collections import defaultdict
from pathlib import Path
from time import time
from typing import List, Dict, Tuple, Optional, Set

from p115client import P115Client, check_response
from p115client.tool.edit import update_name

from app.chain.storage import StorageChain
from app.chain.transfer import TransferChain, task_lock
from app.core.config import settings
from app.core.event import eventmanager
from app.core.meta import MetaBase
from app.core.metainfo import MetaInfoPath
from app.db.transferhistory_oper import TransferHistoryOper
from app.helper.directory import DirectoryHelper
from app.log import logger
from app.schemas import FileItem, Notification, TransferInfo
from app.schemas import TransferTask as MPTransferTask
from app.schemas.types import EventType, MediaType, NotificationType
from app.utils.string import StringUtils

from ...core.config import configer
from ...schemas.transfer import TransferTask, RelatedFile
from .cache_updater import CacheUpdater


class TransferHandler:
    """
    115 整理执行器
    """

    def __init__(self, client: P115Client, storage_name: str = "115网盘Plus"):
        """
        初始化整理执行器

        :param client: 115 客户端实例
        :param storage_name: 存储名称
        """
        self.client = client
        self.storage_name = storage_name
        self.storage_chain = StorageChain()
        self.history_oper = TransferHistoryOper()

        self.cache_updater = CacheUpdater.create(
            client=client, storage_name=storage_name
        )

        logger.info(f"【整理接管】初始化整理执行器，存储: {storage_name}")

    @staticmethod
    def _is_subtitle_file(fileitem: FileItem) -> bool:
        """
        判断是否为字幕文件

        :param fileitem: 文件项
        :return: 是否为字幕文件
        """
        if not fileitem.extension:
            return False
        return f".{fileitem.extension.lower()}" in settings.RMT_SUBEXT

    @staticmethod
    def _is_audio_file(fileitem: FileItem) -> bool:
        """
        判断是否为音频文件

        :param fileitem: 文件项
        :return: 是否为音频文件
        """
        if not fileitem.extension:
            return False
        return f".{fileitem.extension.lower()}" in settings.RMT_AUDIOEXT

    @staticmethod
    def _create_mp_task(task: TransferTask) -> MPTransferTask:
        """
        创建 MoviePilot TransferTask 对象

        :param task: 插件任务对象

        :return: MoviePilot TransferTask 对象
        """
        return MPTransferTask(
            fileitem=task.fileitem,
            mediainfo=task.mediainfo,
            meta=task.meta,
        )

    @staticmethod
    def _group_tasks_by_media(
        tasks: List[TransferTask],
    ) -> Dict[Tuple, List[TransferTask]]:
        """
        按媒体分组任务

        :param tasks: 任务列表

        :return: 按媒体分组的任务字典，key 为 (media_id, season)
        """
        tasks_by_media: Dict[Tuple, List[TransferTask]] = defaultdict(list)
        for task in tasks:
            if task.mediainfo:
                key = (
                    task.mediainfo.tmdb_id or task.mediainfo.douban_id,
                    task.meta.begin_season,
                )
                tasks_by_media[key].append(task)
        return tasks_by_media

    def _remove_completed_jobs(
        self,
        tasks_by_media: Dict[Tuple, List[TransferTask]],
        task_action: str = "finish",
        check_method: str = "is_finished",
    ) -> int:
        """
        移除已完成的任务组

        :param tasks_by_media: 按媒体分组的任务字典
        :param task_action: 任务动作，'finish' 或 'fail'
        :param check_method: 检查方法，'is_finished' 或 'is_done'

        :return: 移除的任务组数量
        """
        chain = TransferChain()
        removed_count = 0

        for (media_id, season), group_tasks in tasks_by_media.items():
            try:
                # 使用第一个任务作为代表
                sample_task = group_tasks[0]
                mp_sample_task = self._create_mp_task(sample_task)

                # 确保所有任务都已标记（finish 或 fail）
                for task in group_tasks:
                    try:
                        mp_task = self._create_mp_task(task)
                        if task_action == "finish":
                            chain.jobview.finish_task(mp_task)
                        elif task_action == "fail":
                            chain.jobview.fail_task(mp_task)
                    except Exception as e:
                        action_name = "完成" if task_action == "finish" else "失败"
                        logger.debug(
                            f"【整理接管】标记任务{action_name}失败 (任务: {task.fileitem.name}): {e}"
                        )

                # 检查是否所有相关任务都完成了
                check_func = getattr(chain.jobview, check_method)
                if check_func(mp_sample_task):
                    # 移除整个媒体组任务
                    with task_lock:
                        chain.jobview.remove_job(mp_sample_task)
                    removed_count += 1
            except Exception as e:
                logger.debug(
                    f"【整理接管】移除任务组失败 (media_id={media_id}, season={season}): {e}",
                    exc_info=True,
                )

        return removed_count

    def _get_folder(self, path: Path) -> Optional[FileItem]:
        """
        获取目录，如目录不存在则创建

        :param path: 目录路径

        :return: 目录文件项，如果创建失败则返回None
        """
        folder_item = self.cache_updater._p115_api.get_item(path)
        if folder_item and folder_item.type == "dir":
            return folder_item

        try:
            resp = self.client.fs_makedirs_app(
                path.as_posix(), pid=0, **configer.get_ios_ua_app()
            )
            check_response(resp)
            logger.debug(f"【整理接管】get_folder 创建目录: {path} (ID: {resp['cid']})")
            modify_time = int(time())
            folder_item = FileItem(
                storage=self.storage_name,
                fileid=str(resp["cid"]),
                path=path.as_posix() + "/",
                name=path.name,
                basename=path.name,
                type="dir",
                modify_time=modify_time,
                pickcode=self.client.to_pickcode(resp["cid"]),
            )
            self.cache_updater.update_folder_cache(folder_item)
            return folder_item
        except Exception as e:
            logger.error(f"【整理接管】创建目录失败 ({path}): {e}", exc_info=True)
            return None

    def process_batch(self, tasks: List[TransferTask]) -> None:
        """
        批量处理整理任务

        :param tasks: 任务列表
        """
        if not tasks:
            logger.warn("【整理接管】任务列表为空，跳过处理")
            return

        logger.info(f"【整理接管】开始批量处理 {len(tasks)} 个任务")

        # 当前可继续处理的任务列表
        remaining_tasks = tasks.copy()
        # 失败的任务列表（用于最后批量记录）
        failed_tasks: List[Tuple[TransferTask, str]] = []

        try:
            # 发现关联文件
            try:
                self._discover_related_files(remaining_tasks)
            except Exception as e:
                error_msg = f"发现关联文件失败: {e}"
                logger.error(f"【整理接管】{error_msg}", exc_info=True)
                # 所有任务都失败
                failed_tasks.extend([(task, error_msg) for task in remaining_tasks])
                remaining_tasks = []
                # 阻断后续步骤
                self._batch_record_failures(failed_tasks)
                return

            # 批量创建目标目录
            if remaining_tasks:
                try:
                    failed_in_step, remaining_tasks = self._batch_create_directories(
                        remaining_tasks
                    )
                    failed_tasks.extend(failed_in_step)
                except Exception as e:
                    error_msg = f"批量创建目录失败: {e}"
                    logger.error(f"【整理接管】{error_msg}", exc_info=True)
                    # 所有剩余任务都失败
                    failed_tasks.extend([(task, error_msg) for task in remaining_tasks])
                    remaining_tasks = []
                    # 阻断后续步骤
                    self._batch_record_failures(failed_tasks)
                    return

            # 批量移动/复制文件
            if remaining_tasks:
                try:
                    failed_in_step, remaining_tasks = self._batch_move_or_copy(
                        remaining_tasks
                    )
                    failed_tasks.extend(failed_in_step)
                except Exception as e:
                    error_msg = f"批量移动/复制文件失败: {e}"
                    logger.error(f"【整理接管】{error_msg}", exc_info=True)
                    # 所有剩余任务都失败
                    failed_tasks.extend([(task, error_msg) for task in remaining_tasks])
                    remaining_tasks = []
                    # 阻断后续步骤
                    self._batch_record_failures(failed_tasks)
                    return

            # 批量重命名文件
            if remaining_tasks:
                try:
                    failed_in_step, remaining_tasks = self._batch_rename_files(
                        remaining_tasks
                    )
                    failed_tasks.extend(failed_in_step)
                except Exception as e:
                    error_msg = f"批量重命名文件失败: {e}"
                    logger.error(f"【整理接管】{error_msg}", exc_info=True)
                    # 所有剩余任务都失败
                    failed_tasks.extend([(task, error_msg) for task in remaining_tasks])
                    remaining_tasks = []
                    # 阻断后续步骤
                    self._batch_record_failures(failed_tasks)
                    return

            # 记录历史（只处理成功的任务）
            if remaining_tasks:
                try:
                    self._record_history(remaining_tasks)
                except Exception as e:
                    error_msg = f"记录历史失败: {e}"
                    logger.error(f"【整理接管】{error_msg}", exc_info=True)
                    # 所有剩余任务都失败
                    failed_tasks.extend([(task, error_msg) for task in remaining_tasks])
                    remaining_tasks = []

            # 批量记录所有失败的任务
            if failed_tasks:
                self._batch_record_failures(failed_tasks)

            success_count = len(remaining_tasks)
            fail_count = len(failed_tasks)
            logger.info(
                f"【整理接管】批量处理完成，成功: {success_count} 个，失败: {fail_count} 个"
            )

        except Exception as e:
            logger.error(f"【整理接管】批量处理异常: {e}", exc_info=True)
            # 所有剩余任务都失败
            error_msg = f"批量处理异常: {e}"
            failed_tasks.extend([(task, error_msg) for task in remaining_tasks])
            self._batch_record_failures(failed_tasks)

    def _discover_related_files(self, tasks: List[TransferTask]) -> None:
        """
        发现关联文件（字幕、音轨）

        :param tasks: 任务列表
        """
        logger.info("【整理接管】开始发现关联文件")

        # 按源目录分组任务
        tasks_by_dir: Dict[Path, List[TransferTask]] = defaultdict(list)
        for task in tasks:
            source_dir = Path(task.fileitem.path).parent
            tasks_by_dir[source_dir].append(task)

        # 对每个源目录，列出文件并匹配关联文件
        for source_dir, dir_tasks in tasks_by_dir.items():
            try:
                source_fileitem = FileItem(
                    storage=self.storage_name,
                    path=str(source_dir) + "/",
                    type="dir",
                )
                files = self.cache_updater._p115_api.list(source_fileitem)

                if not files:
                    logger.debug(
                        f"【整理接管】源目录 {source_dir} 为空，跳过关联文件发现"
                    )
                    continue

                # 为每个任务匹配关联文件
                for task in dir_tasks:
                    main_video_path = Path(task.fileitem.path)
                    main_video_metainfo = MetaInfoPath(main_video_path)

                    # 匹配字幕文件
                    TransferHandler._match_subtitle_files(
                        task, main_video_path, main_video_metainfo, files
                    )

                    # 匹配音轨文件
                    TransferHandler._match_audio_track_files(
                        task, main_video_path, files
                    )

            except Exception as e:
                logger.error(
                    f"【整理接管】发现关联文件失败 (目录: {source_dir}): {e}",
                    exc_info=True,
                )

        # 统计关联文件数量
        total_related = sum(len(task.related_files) for task in tasks)
        logger.info(f"【整理接管】关联文件发现完成，共发现 {total_related} 个关联文件")

    @staticmethod
    def _match_subtitle_files(
        task: TransferTask,
        main_video_path: Path,
        main_video_metainfo: MetaBase,
        files: List[FileItem],
    ) -> None:
        """
        匹配字幕文件

        :param task: 任务
        :param main_video_path: 主视频路径
        :param main_video_metainfo: 主视频元信息
        :param files: 目录文件列表
        """
        _zhcn_sub_re = (
            r"([.\[(\s](((zh[-_])?(cn|ch[si]|sg|sc))|zho?"
            r"|chinese|(cn|ch[si]|sg|zho?)[-_&]?(cn|ch[si]|sg|zho?|eng|jap|ja|jpn)"
            r"|eng[-_&]?(cn|ch[si]|sg|zho?)|(jap|ja|jpn)[-_&]?(cn|ch[si]|sg|zho?)"
            r"|简[体中]?)[.\])\s])"
            r"|([\u4e00-\u9fa5]{0,3}[中双][\u4e00-\u9fa5]{0,2}[字文语][\u4e00-\u9fa5]{0,3})"
            r"|简体|简中|JPSC|sc_jp"
            r"|(?<![a-z0-9])gb(?![a-z0-9])"
        )
        _zhtw_sub_re = (
            r"([.\[(\s](((zh[-_])?(hk|tw|cht|tc))"
            r"|cht[-_&]?(cht|eng|jap|ja|jpn)"
            r"|eng[-_&]?cht|(jap|ja|jpn)[-_&]?cht"
            r"|繁[体中]?)[.\])\s])"
            r"|繁体中[文字]|中[文字]繁体|繁体|JPTC|tc_jp"
            r"|(?<![a-z0-9])big5(?![a-z0-9])"
        )
        _ja_sub_re = (
            r"([.\[(\s](ja-jp|jap|ja|jpn"
            r"|(jap|ja|jpn)[-_&]?eng|eng[-_&]?(jap|ja|jpn))[.\])\s])"
            r"|日本語|日語"
        )
        _eng_sub_re = r"[.\[(\s]eng[.\])\s]"

        # 筛选字幕文件
        subtitle_files = [
            f
            for f in files
            if f.path != task.fileitem.path
            and f.type == "file"
            and f.extension
            and f".{f.extension.lower()}" in settings.RMT_SUBEXT
        ]

        if not subtitle_files:
            logger.debug(f"【整理接管】{main_video_path.parent} 目录下没有找到字幕文件")
            return

        logger.debug(f"【整理接管】字幕文件清单：{[f.name for f in subtitle_files]}")

        # 匹配字幕文件
        for sub_item in subtitle_files:
            # 识别字幕文件名（去除语言标识）
            sub_file_name = re.sub(
                _zhtw_sub_re,
                ".",
                re.sub(_zhcn_sub_re, ".", sub_item.name, flags=re.I),
                flags=re.I,
            )
            sub_file_name = re.sub(_eng_sub_re, ".", sub_file_name, flags=re.I)
            sub_metainfo = MetaInfoPath(Path(sub_item.path))

            # 匹配字幕文件名
            if (
                main_video_path.stem == Path(sub_file_name).stem
                or (
                    sub_metainfo.cn_name
                    and sub_metainfo.cn_name == main_video_metainfo.cn_name
                )
                or (
                    sub_metainfo.en_name
                    and sub_metainfo.en_name == main_video_metainfo.en_name
                )
            ):
                # 检查 part、season、episode 是否匹配
                if (
                    main_video_metainfo.part
                    and main_video_metainfo.part != sub_metainfo.part
                ):
                    continue
                if (
                    main_video_metainfo.season
                    and main_video_metainfo.season != sub_metainfo.season
                ):
                    continue
                if (
                    main_video_metainfo.episode
                    and main_video_metainfo.episode != sub_metainfo.episode
                ):
                    continue

                # 确定字幕语言类型
                new_file_type = ""
                if re.search(_zhcn_sub_re, sub_item.name, re.I):
                    new_file_type = ".chi.zh-cn"
                elif re.search(_zhtw_sub_re, sub_item.name, re.I):
                    new_file_type = ".zh-tw"
                elif re.search(_ja_sub_re, sub_item.name, re.I):
                    new_file_type = ".ja"
                elif re.search(_eng_sub_re, sub_item.name, re.I):
                    new_file_type = ".eng"

                # 生成字幕文件目标路径
                file_ext = f".{sub_item.extension}"
                new_sub_tag_dict = {
                    ".eng": ".英文",
                    ".chi.zh-cn": ".简体中文",
                    ".zh-tw": ".繁体中文",
                }
                new_sub_tag_list = [
                    (
                        (
                            ".default" + new_file_type
                            if (
                                (
                                    settings.DEFAULT_SUB == "zh-cn"
                                    and new_file_type == ".chi.zh-cn"
                                )
                                or (
                                    settings.DEFAULT_SUB == "zh-tw"
                                    and new_file_type == ".zh-tw"
                                )
                                or (
                                    settings.DEFAULT_SUB == "ja"
                                    and new_file_type == ".ja"
                                )
                                or (
                                    settings.DEFAULT_SUB == "eng"
                                    and new_file_type == ".eng"
                                )
                            )
                            else new_file_type
                        )
                        if t == 0
                        else f"{new_file_type}{new_sub_tag_dict.get(new_file_type, '')}({t})"
                    )
                    for t in range(6)
                ]

                # 尝试找到可用的目标文件名
                for new_sub_tag in new_sub_tag_list:
                    target_path = task.target_path.with_name(
                        task.target_path.stem + new_sub_tag + file_ext
                    )

                    # 添加到关联文件列表（只添加第一个匹配的）
                    related_file = RelatedFile(
                        fileitem=sub_item,
                        target_path=target_path,
                        file_type="subtitle",
                    )
                    task.related_files.append(related_file)

                    logger.debug(
                        f"【整理接管】发现字幕文件: {sub_item.name} -> {target_path.name}"
                    )
                    break

    @staticmethod
    def _match_audio_track_files(
        task: TransferTask,
        main_video_path: Path,
        files: List[FileItem],
    ) -> None:
        """
        匹配音轨文件

        :param task: 任务
        :param main_video_path: 主视频路径
        :param files: 目录文件列表
        """
        audio_track_files = [
            file
            for file in files
            if file.path != task.fileitem.path
            and Path(file.name).stem == main_video_path.stem
            and file.type == "file"
            and file.extension
            and f".{file.extension.lower()}" in settings.RMT_AUDIOEXT
        ]

        if not audio_track_files:
            logger.debug(
                f"【整理接管】{main_video_path.parent} 目录下没有找到匹配的音轨文件"
            )
            return

        logger.debug(f"【整理接管】音轨文件清单：{[f.name for f in audio_track_files]}")

        # 添加音轨文件
        for track_file in audio_track_files:
            track_ext = f".{track_file.extension}"
            target_path = task.target_path.with_name(task.target_path.stem + track_ext)

            related_file = RelatedFile(
                fileitem=track_file,
                target_path=target_path,
                file_type="audio_track",
            )
            task.related_files.append(related_file)

            logger.debug(
                f"【整理接管】发现音轨文件: {track_file.name} -> {target_path.name}"
            )

    def _batch_create_directories(
        self, tasks: List[TransferTask]
    ) -> Tuple[List[Tuple[TransferTask, str]], List[TransferTask]]:
        """
        批量创建目标目录

        :param tasks: 任务列表

        :return: (失败任务列表, 成功任务列表)
        """
        logger.info("【整理接管】开始批量创建目标目录")

        # 收集所有目标目录
        target_dirs: set[Path] = set()
        task_dirs_map: Dict[Path, List[TransferTask]] = defaultdict(list)
        for task in tasks:
            target_dir = task.target_dir
            target_dirs.add(target_dir)
            task_dirs_map[target_dir].append(task)
            # 关联文件的目标目录
            for related_file in task.related_files:
                related_dir = related_file.target_path.parent
                target_dirs.add(related_dir)
                task_dirs_map[related_dir].append(task)

        # 搜集子目录
        leaf_dirs: set[Path] = set()
        for target_dir in target_dirs:
            is_parent = any(
                target_dir != other_dir and target_dir in other_dir.parents
                for other_dir in target_dirs
            )
            if not is_parent:
                leaf_dirs.add(target_dir)

        # 批量创建子目录（自动递归）
        created_count = 0
        failed_dirs: set[Path] = set()
        for target_dir in leaf_dirs:
            try:
                folder_item = self._get_folder(target_dir)
                if folder_item:
                    created_count += 1
                else:
                    logger.warn(f"【整理接管】创建目录失败: {target_dir}")
                    failed_dirs.add(target_dir)

            except Exception as e:
                logger.error(
                    f"【整理接管】创建目录失败 ({target_dir}): {e}",
                    exc_info=True,
                )
                failed_dirs.add(target_dir)

        logger.info(f"【整理接管】目录创建完成，共创建 {created_count} 个目录")

        # 收集失败的任务（如果任务的目标目录创建失败，则任务失败）
        failed_tasks: List[Tuple[TransferTask, str]] = []
        success_tasks: List[TransferTask] = []

        for task in tasks:
            task_failed = False
            # 检查主目录
            if task.target_dir in failed_dirs:
                failed_tasks.append((task, f"创建目标目录失败: {task.target_dir}"))
                task_failed = True
            else:
                # 检查关联文件的目录
                for related_file in task.related_files:
                    related_dir = related_file.target_path.parent
                    if related_dir in failed_dirs:
                        failed_tasks.append(
                            (task, f"创建关联文件目录失败: {related_dir}")
                        )
                        task_failed = True
                        break

            if not task_failed:
                success_tasks.append(task)

        return failed_tasks, success_tasks

    def _batch_move_or_copy(
        self, tasks: List[TransferTask]
    ) -> Tuple[List[Tuple[TransferTask, str]], List[TransferTask]]:
        """
        批量移动/复制文件（按目标目录分组）

        :param tasks: 任务列表

        :return: (失败任务列表, 成功任务列表)
        """
        logger.info("【整理接管】开始批量移动/复制文件")

        # 跟踪每个任务的主文件处理状态（主文件失败则任务失败）
        task_main_file_status: Dict[str, bool] = {
            task.fileitem.path: False for task in tasks
        }
        # 跟踪每个任务的失败原因
        task_failures: Dict[str, str] = {}

        # 按目标目录和操作类型分组
        operations: Dict[
            Tuple[Path, str],
            List[Tuple[FileItem, str, TransferTask, bool, Optional[RelatedFile]]],
        ] = defaultdict(list)

        for task in tasks:
            target_dir = task.target_dir
            transfer_type = task.transfer_type

            # 主视频 (is_main=True, related_file=None)
            operations[(target_dir, transfer_type)].append(
                (task.fileitem, task.target_name, task, True, None)
            )

            # 关联文件 (is_main=False, related_file=related_file)
            for related_file in task.related_files:
                related_dir = related_file.target_path.parent
                operations[(related_dir, transfer_type)].append(
                    (
                        related_file.fileitem,
                        related_file.target_path.name,
                        task,
                        False,
                        related_file,
                    )
                )

        # 批量执行移动/复制
        for (target_dir, transfer_type), files in operations.items():
            try:
                # 获取目标目录的 fileid
                try:
                    folder_item = self._get_folder(target_dir)
                    if not folder_item or not folder_item.fileid:
                        logger.error(
                            f"【整理接管】无法获取或创建目标目录: {target_dir}"
                        )
                        affected_tasks = []
                        seen_tasks = set()
                        for _, _, task, _, _ in files:
                            task_id = (
                                task.fileitem.path if task and task.fileitem else None
                            )
                            if task_id and task_id not in seen_tasks:
                                affected_tasks.append(task)
                                seen_tasks.add(task_id)
                        for task in affected_tasks:
                            task_path = (
                                task.fileitem.path if task and task.fileitem else None
                            )
                            if task_path and task_path not in task_failures:
                                task_failures[task_path] = (
                                    f"无法获取或创建目标目录: {target_dir}"
                                )
                        continue
                    target_dir_id = int(folder_item.fileid)
                except Exception as e:
                    logger.error(
                        f"【整理接管】无法获取目标目录ID: {target_dir}, 错误: {e}"
                    )
                    affected_tasks = []
                    seen_tasks = set()
                    for _, _, task, _, _ in files:
                        task_id = task.fileitem.path if task and task.fileitem else None
                        if task_id and task_id not in seen_tasks:
                            affected_tasks.append(task)
                            seen_tasks.add(task_id)
                    for task in affected_tasks:
                        task_path = (
                            task.fileitem.path if task and task.fileitem else None
                        )
                        if task_path and task_path not in task_failures:
                            task_failures[task_path] = (
                                f"无法获取目标目录ID: {target_dir}, 错误: {e}"
                            )
                    continue

                # 批量检查目标文件是否已存在
                existing_files_map: Dict[str, FileItem] = {}
                try:
                    existing_files = self.cache_updater._p115_api.list(folder_item)
                    if existing_files:
                        # 创建文件名到 FileItem 的映射
                        for existing_file in existing_files:
                            if existing_file.type == "file":
                                existing_files_map[existing_file.name] = existing_file
                except Exception as list_error:
                    logger.warn(
                        f"【整理接管】批量列出目标目录文件失败 ({target_dir}): {list_error}，将跳过文件存在性检查"
                    )

                # 收集 文件 ID 和 文件信息 映射，并处理目标文件已存在的情况
                file_ids = []
                file_mapping: Dict[
                    int, Tuple[TransferTask, bool, str, Optional[RelatedFile]]
                ] = {}
                files_to_delete: List[FileItem] = []
                # 收集需要批量删除版本文件的任务（按目录分组）
                version_delete_tasks: Dict[Path, List[Tuple[Path, TransferTask]]] = (
                    defaultdict(list)
                )

                for fileitem, target_name, task, is_main, related_file in files:
                    if not fileitem.fileid:
                        logger.warn(f"【整理接管】文件缺少 fileid: {fileitem.path}")
                        # 如果是主文件缺少 fileid，标记任务失败
                        if is_main:
                            task_path = (
                                task.fileitem.path if task and task.fileitem else None
                            )
                            if task_path:
                                task_failures[task_path] = (
                                    f"文件缺少 fileid: {fileitem.path}"
                                )
                        continue

                    # 检查目标文件是否已存在
                    existing_item = existing_files_map.get(target_name)

                    # 判断是否为附加文件（字幕、音轨）
                    is_extra_file = False
                    if related_file:
                        # 关联文件（字幕、音轨）强制覆盖
                        is_extra_file = True
                    elif fileitem.extension:
                        # 检查文件扩展名是否为附加文件类型
                        file_ext = f".{fileitem.extension.lower()}"
                        is_extra_file = file_ext in (
                            settings.RMT_SUBEXT + settings.RMT_AUDIOEXT
                        )

                    if existing_item:
                        # 目标文件已存在
                        if is_extra_file:
                            # 附加文件强制覆盖
                            logger.info(
                                f"【整理接管】目标文件已存在，附加文件强制覆盖: {target_dir / target_name}"
                            )
                            files_to_delete.append(existing_item)
                            existing_files_map.pop(target_name, None)
                        else:
                            # 主视频文件，根据 overwrite_mode 决定是否覆盖
                            overwrite_mode = task.overwrite_mode or "never"
                            over_flag = False
                            should_skip = False

                            if overwrite_mode == "always":
                                # 总是覆盖同名文件
                                over_flag = True
                                logger.info(
                                    f"【整理接管】目标文件已存在，覆盖模式=always，将覆盖: {target_dir / target_name}"
                                )
                            elif overwrite_mode == "size":
                                # 存在时大覆盖小
                                source_size = fileitem.size or 0
                                target_size = existing_item.size or 0
                                if source_size > target_size:
                                    over_flag = True
                                    logger.info(
                                        f"【整理接管】目标文件已存在，覆盖模式=size，源文件更大 ({source_size} > {target_size})，将覆盖: {target_dir / target_name}"
                                    )
                                else:
                                    # 目标文件质量更好，跳过
                                    should_skip = True
                                    logger.info(
                                        f"【整理接管】目标文件已存在，覆盖模式=size，目标文件质量更好 ({target_size} >= {source_size})，跳过: {target_dir / target_name}"
                                    )
                            elif overwrite_mode == "latest":
                                # 仅保留最新版本
                                over_flag = True
                                logger.info(
                                    f"【整理接管】目标文件已存在，覆盖模式=latest，将覆盖: {target_dir / target_name}"
                                )
                            else:  # overwrite_mode == "never" or None
                                # 存在不覆盖
                                should_skip = True
                                logger.info(
                                    f"【整理接管】目标文件已存在，覆盖模式=never，跳过: {target_dir / target_name}"
                                )

                            if should_skip:
                                # 不覆盖，跳过此文件（文件已存在，视为成功）
                                if is_main:
                                    task.fileitem.fileid = existing_item.fileid
                                    # 文件已存在，视为成功
                                    task_path = (
                                        task.fileitem.path
                                        if task and task.fileitem
                                        else None
                                    )
                                    if task_path:
                                        task_main_file_status[task_path] = True
                                elif related_file:
                                    related_file.fileitem.fileid = existing_item.fileid
                                continue
                            elif over_flag:
                                # 覆盖模式，收集需要删除的文件
                                files_to_delete.append(existing_item)
                                # 从映射中移除，避免重复处理
                                existing_files_map.pop(target_name, None)
                    else:
                        # 目标文件不存在，但如果是 latest 模式，需要删除其他版本文件
                        if not is_extra_file and task.overwrite_mode == "latest":
                            # 收集到批量删除列表，循环外统一处理
                            version_delete_tasks[target_dir].append(
                                (target_dir / target_name, task)
                            )

                    file_id = int(fileitem.fileid)
                    file_ids.append(file_id)
                    file_mapping[file_id] = (task, is_main, target_name, related_file)

                # 批量删除已存在的文件
                if files_to_delete:
                    logger.info(
                        f"【整理接管】批量删除 {len(files_to_delete)} 个已存在的目标文件"
                    )
                    # 收集需要删除的文件 ID
                    delete_file_ids = []
                    delete_file_mapping: Dict[int, FileItem] = {}  # file_id -> FileItem
                    for existing_item in files_to_delete:
                        if existing_item.fileid:
                            file_id = int(existing_item.fileid)
                            delete_file_ids.append(file_id)
                            delete_file_mapping[file_id] = existing_item

                    if delete_file_ids:
                        try:
                            # 批量删除
                            resp = self.client.fs_delete(
                                delete_file_ids, **configer.get_ios_ua_app(app=False)
                            )
                            check_response(resp)
                            for file_id in delete_file_ids:
                                self.cache_updater.remove_cache(file_id)
                            logger.info(
                                f"【整理接管】批量删除成功: {len(delete_file_ids)} 个文件"
                            )
                        except Exception as batch_delete_error:
                            logger.error(
                                f"【整理接管】批量删除失败: {batch_delete_error}",
                                exc_info=True,
                            )
                            # 批量删除失败，从待处理列表中移除对应的文件
                            for file_id in delete_file_ids:
                                existing_item = delete_file_mapping.get(file_id)
                                if existing_item:
                                    # 找到对应的 file_id 并移除
                                    file_id_to_remove = None
                                    for fid, (
                                        t,
                                        is_m,
                                        t_name,
                                        rf,
                                    ) in file_mapping.items():
                                        if t_name == existing_item.name:
                                            file_id_to_remove = fid
                                            break
                                    if file_id_to_remove:
                                        file_ids.remove(file_id_to_remove)
                                        file_mapping.pop(file_id_to_remove, None)

                # 批量删除版本文件（latest 模式，目标文件不存在时）
                if version_delete_tasks:
                    self._batch_delete_version_files(version_delete_tasks)

                if not file_ids:
                    continue

                # 执行批量 移动 /复制
                if transfer_type == "move":
                    try:
                        resp = self.client.fs_move(
                            file_ids,
                            pid=target_dir_id,
                            **configer.get_ios_ua_app(app=False),
                        )
                        check_response(resp)
                        for file_id, (
                            task,
                            is_main,
                            target_name,
                            related_file,
                        ) in file_mapping.items():
                            try:
                                target_path = target_dir / target_name
                                new_fileitem = FileItem(
                                    storage=self.storage_name,
                                    path=str(target_path),
                                    name=target_name,
                                    fileid=str(file_id),
                                    type="file",
                                    size=task.fileitem.size
                                    if is_main
                                    else (
                                        related_file.fileitem.size
                                        if related_file
                                        else 0
                                    ),
                                    modify_time=task.fileitem.modify_time
                                    if is_main
                                    else (
                                        related_file.fileitem.modify_time
                                        if related_file
                                        else 0
                                    ),
                                    pickcode=task.fileitem.pickcode
                                    if is_main
                                    else (
                                        related_file.fileitem.pickcode
                                        if related_file
                                        else None
                                    ),
                                )
                                self.cache_updater.update_file_cache(new_fileitem)
                            except Exception as cache_error:
                                logger.debug(
                                    f"【整理接管】更新移动文件缓存失败 (file_id: {file_id}): {cache_error}"
                                )
                        logger.info(
                            f"【整理接管】批量移动 {len(file_ids)} 个文件到 {target_dir}"
                        )
                        # 标记所有文件移动成功
                        for file_id, (
                            task,
                            is_main,
                            target_name,
                            related_file,
                        ) in file_mapping.items():
                            if is_main:
                                task_path = (
                                    task.fileitem.path
                                    if task and task.fileitem
                                    else None
                                )
                                if task_path:
                                    task_main_file_status[task_path] = True
                    except Exception as batch_error:
                        logger.error(
                            f"【整理接管】批量移动失败: {batch_error}",
                            exc_info=True,
                        )
                        # 记录失败的主文件对应的任务
                        for file_id in file_ids:
                            task, is_main, target_name, related_file = file_mapping.get(
                                file_id, (None, False, "", None)
                            )
                            if task and is_main:
                                task_path = (
                                    task.fileitem.path
                                    if task and task.fileitem
                                    else None
                                )
                                if task_path:
                                    task_failures[task_path] = (
                                        f"批量移动失败: {target_name}"
                                    )
                elif transfer_type == "copy":
                    try:
                        resp = self.client.fs_copy(
                            file_ids,
                            pid=target_dir_id,
                            **configer.get_ios_ua_app(app=False),
                        )
                        check_response(resp)
                        logger.info(
                            f"【整理接管】批量复制 {len(file_ids)} 个文件到 {target_dir}"
                        )
                        self._update_file_ids_after_copy(target_dir, file_mapping)
                        for file_id, (
                            task,
                            is_main,
                            target_name,
                            related_file,
                        ) in file_mapping.items():
                            try:
                                actual_fileid = (
                                    task.fileitem.fileid
                                    if is_main
                                    else (
                                        related_file.fileitem.fileid
                                        if related_file
                                        else None
                                    )
                                )
                                if actual_fileid:
                                    target_path = target_dir / target_name
                                    new_fileitem = FileItem(
                                        storage=self.storage_name,
                                        path=str(target_path),
                                        name=target_name,
                                        fileid=actual_fileid,
                                        type="file",
                                        size=task.fileitem.size
                                        if is_main
                                        else (
                                            related_file.fileitem.size
                                            if related_file
                                            else 0
                                        ),
                                        modify_time=task.fileitem.modify_time
                                        if is_main
                                        else (
                                            related_file.fileitem.modify_time
                                            if related_file
                                            else 0
                                        ),
                                        pickcode=task.fileitem.pickcode
                                        if is_main
                                        else (
                                            related_file.fileitem.pickcode
                                            if related_file
                                            else None
                                        ),
                                    )
                                    self.cache_updater.update_file_cache(new_fileitem)
                                    # 标记主文件复制成功
                                    if is_main:
                                        task_path = (
                                            task.fileitem.path
                                            if task and task.fileitem
                                            else None
                                        )
                                        if task_path:
                                            task_main_file_status[task_path] = True
                            except Exception as cache_error:
                                logger.debug(
                                    f"【整理接管】更新复制文件缓存失败 (file_id: {file_id}): {cache_error}"
                                )
                    except Exception as batch_error:
                        logger.error(
                            f"【整理接管】批量复制失败: {batch_error}",
                            exc_info=True,
                        )
                        # 记录失败的主文件对应的任务
                        for file_id in file_ids:
                            task, is_main, target_name, related_file = file_mapping.get(
                                file_id, (None, False, "", None)
                            )
                            if task and is_main:
                                task_path = (
                                    task.fileitem.path
                                    if task and task.fileitem
                                    else None
                                )
                                if task_path:
                                    task_failures[task_path] = (
                                        f"批量复制失败: {target_name}"
                                    )

            except Exception as e:
                logger.error(
                    f"【整理接管】批量移动/复制失败 (目录: {target_dir}, 类型: {transfer_type}): {e}",
                    exc_info=True,
                )
                affected_tasks = []
                seen_tasks = set()
                for _, _, task, _, _ in files:
                    task_id = task.fileitem.path if task and task.fileitem else None
                    if task_id and task_id not in seen_tasks:
                        affected_tasks.append(task)
                        seen_tasks.add(task_id)

                for task in affected_tasks:
                    task_path = task.fileitem.path if task and task.fileitem else None
                    if task_path and task_path not in task_failures:
                        task_failures[task_path] = (
                            f"批量移动/复制失败 (目录: {target_dir}): {e}"
                        )

        # 收集失败和成功的任务
        failed_tasks: List[Tuple[TransferTask, str]] = []
        success_tasks: List[TransferTask] = []
        # 需要检查的任务（有 fileid 但状态未标记，可能是文件已存在被跳过但未正确标记）
        tasks_to_check: List[TransferTask] = []

        for task in tasks:
            task_path = task.fileitem.path if task and task.fileitem else None
            if task_path and task_path in task_failures:
                failed_tasks.append((task, task_failures[task_path]))
            elif task_path and task_main_file_status.get(task_path, False):
                success_tasks.append(task)
            else:
                # 主文件未处理或处理失败
                # 如果文件有 fileid，可能是已存在被跳过但未正确标记状态
                if task.fileitem.fileid:
                    tasks_to_check.append(task)
                else:
                    failed_tasks.append((task, "主文件移动/复制未完成"))

        # 批量检查需要确认的任务（避免逐个调用 API）
        if tasks_to_check:
            # 按目标目录分组，批量检查
            tasks_by_dir: Dict[Path, List[TransferTask]] = defaultdict(list)
            for task in tasks_to_check:
                tasks_by_dir[task.target_dir].append(task)

            for target_dir, dir_tasks in tasks_by_dir.items():
                try:
                    # 批量列出目标目录的文件
                    folder_item = self._get_folder(target_dir)
                    if folder_item:
                        existing_files = self.cache_updater._p115_api.list(folder_item)
                        if existing_files:
                            # 创建文件名到 FileItem 的映射
                            existing_files_map = {
                                f.name: f for f in existing_files if f.type == "file"
                            }
                            # 检查每个任务的文件是否存在
                            for task in dir_tasks:
                                if task.target_name in existing_files_map:
                                    # 文件已在目标位置，视为成功
                                    success_tasks.append(task)
                                else:
                                    failed_tasks.append((task, "主文件移动/复制未完成"))
                        else:
                            # 目录为空，所有任务都失败
                            for task in dir_tasks:
                                failed_tasks.append((task, "主文件移动/复制未完成"))
                    else:
                        # 无法获取目录，所有任务都失败
                        for task in dir_tasks:
                            failed_tasks.append((task, "主文件移动/复制未完成"))
                except Exception as e:
                    logger.warn(
                        f"【整理接管】批量检查文件存在性失败 (目录: {target_dir}): {e}"
                    )
                    # 检查失败，所有任务都标记为失败
                    for task in dir_tasks:
                        failed_tasks.append((task, "主文件移动/复制未完成"))

        logger.info(
            f"【整理接管】批量移动/复制完成，成功: {len(success_tasks)} 个，失败: {len(failed_tasks)} 个"
        )

        return failed_tasks, success_tasks

    def _batch_delete_version_files(
        self,
        version_delete_tasks: Dict[Path, List[Tuple[Path, TransferTask]]],
    ) -> None:
        """
        批量删除版本文件（latest 模式，目标文件不存在时）

        :param version_delete_tasks: 按目录分组的版本删除任务 {目录: [(目标路径, 任务), ...]}
        """
        for target_dir, tasks in version_delete_tasks.items():
            try:
                # 获取目标目录
                folder_item = self._get_folder(target_dir)
                if not folder_item:
                    logger.warn(f"【整理接管】无法获取目标目录: {target_dir}")
                    continue

                # 列出目录下所有文件
                files = self.cache_updater._p115_api.list(folder_item)
                if not files:
                    logger.debug(f"【整理接管】目录 {target_dir} 中没有文件")
                    continue

                # 收集需要删除的文件（按季集分组）
                files_to_delete_by_se: Dict[
                    Tuple[Optional[str], Optional[str]], List[FileItem]
                ] = defaultdict(list)

                # 收集所有目标文件的季集信息
                target_seasons_episodes: Set[Tuple[Optional[str], Optional[str]]] = (
                    set()
                )
                for target_path, _ in tasks:
                    meta = MetaInfoPath(target_path)
                    target_seasons_episodes.add((meta.season, meta.episode))

                if not target_seasons_episodes:
                    logger.debug(
                        f"【整理接管】目标文件无季集信息，跳过版本删除: {target_dir}"
                    )
                    continue

                logger.info(
                    f"【整理接管】覆盖模式=latest，正在删除目标目录中其它版本的文件: {target_dir}"
                )

                # 遍历目录中的文件，找出需要删除的版本文件
                for file in files:
                    if file.type != "file":
                        continue
                    if not file.extension:
                        continue
                    # 只处理媒体文件
                    file_ext = f".{file.extension.lower()}"
                    if file_ext not in settings.RMT_MEDIAEXT:
                        continue

                    # 识别文件中的季集信息
                    file_meta = MetaInfoPath(Path(file.path))
                    file_se: Tuple[Optional[str], Optional[str]] = (
                        file_meta.season,
                        file_meta.episode,
                    )

                    # 检查是否与任何目标文件的季集匹配
                    if file_se in target_seasons_episodes:
                        # 检查是否为目标文件本身（通过路径匹配）
                        is_target_file = False
                        for target_path, _ in tasks:
                            if Path(file.path) == target_path:
                                is_target_file = True
                                break

                        if not is_target_file:
                            files_to_delete_by_se[file_se].append(file)
                            logger.info(
                                f"【整理接管】发现同版本文件，将删除: {file.name}"
                            )

                # 批量删除所有收集到的版本文件
                all_files_to_delete = []
                for files_list in files_to_delete_by_se.values():
                    all_files_to_delete.extend(files_list)

                if not all_files_to_delete:
                    logger.debug(
                        f"【整理接管】目录 {target_dir} 中没有找到同版本的其他文件"
                    )
                    continue

                # 批量删除
                delete_file_ids = []
                for file in all_files_to_delete:
                    if file.fileid:
                        delete_file_ids.append(int(file.fileid))

                if delete_file_ids:
                    try:
                        resp = self.client.fs_delete(
                            delete_file_ids, **configer.get_ios_ua_app(app=False)
                        )
                        check_response(resp)
                        for file_id in delete_file_ids:
                            self.cache_updater.remove_cache(file_id)
                        logger.info(
                            f"【整理接管】批量删除版本文件成功: {len(delete_file_ids)} 个文件 (目录: {target_dir})"
                        )
                    except Exception as e:
                        logger.error(
                            f"【整理接管】批量删除版本文件失败: {e}", exc_info=True
                        )

            except Exception as e:
                logger.error(f"【整理接管】批量删除版本文件异常: {e}", exc_info=True)

    def _update_file_ids_after_copy(
        self,
        target_dir: Path,
        file_mapping: Dict[int, Tuple[TransferTask, bool, str, Optional[RelatedFile]]],
    ) -> None:
        """
        批量更新复制后的 文件 ID

        :param target_dir: 目标目录
        :param file_mapping: 文件ID到任务信息的映射
        """
        try:
            # 获取目标目录的文件列表
            target_dir_fileitem = FileItem(
                storage=self.storage_name,
                path=str(target_dir) + "/",
                type="dir",
            )
            files = self.cache_updater._p115_api.list(target_dir_fileitem)

            if not files:
                logger.warn(f"【整理接管】目标目录 {target_dir} 为空，无法更新文件ID")
                return

            # 创建文件名到文件项的映射
            file_map: Dict[str, FileItem] = {
                f.name: f for f in files if f.type == "file"
            }

            # 更新每个文件的任务信息
            for file_id, (
                task,
                is_main,
                target_name,
                related_file,
            ) in file_mapping.items():
                if target_name in file_map:
                    new_fileitem = file_map[target_name]
                    if new_fileitem.fileid:
                        if is_main:
                            # 更新主视频的 fileid
                            task.fileitem.fileid = new_fileitem.fileid
                            logger.debug(
                                f"【整理接管】更新主视频文件ID: {target_name} -> {new_fileitem.fileid}"
                            )
                        elif related_file:
                            # 更新关联文件的 fileid
                            related_file.fileitem.fileid = new_fileitem.fileid
                            logger.debug(
                                f"【整理接管】更新关联文件ID: {target_name} -> {new_fileitem.fileid}"
                            )
                else:
                    logger.warn(
                        f"【整理接管】未找到复制后的文件: {target_name} (目录: {target_dir})"
                    )

        except Exception as e:
            logger.error(
                f"【整理接管】批量更新文件ID失败 (目录: {target_dir}): {e}",
                exc_info=True,
            )

    def _update_single_file_id_after_copy(
        self,
        task: TransferTask,
        is_main: bool,
        target_path: Path,
        related_file: Optional[RelatedFile],
    ) -> None:
        """
        单个文件复制后更新 文件 ID

        :param task: 任务
        :param is_main: 是否为主视频
        :param target_path: 目标路径
        :param related_file: 关联文件（如果不是主视频）
        """
        try:
            file_item = self.cache_updater._p115_api.get_item(target_path)
            if file_item and file_item.fileid:
                if is_main:
                    task.fileitem.fileid = file_item.fileid
                    logger.debug(
                        f"【整理接管】更新主视频文件ID: {target_path.name} -> {file_item.fileid}"
                    )
                elif related_file:
                    related_file.fileitem.fileid = file_item.fileid
                    logger.debug(
                        f"【整理接管】更新关联文件ID: {target_path.name} -> {file_item.fileid}"
                    )
            else:
                logger.warn(f"【整理接管】未找到复制后的文件: {target_path}")
        except Exception as e:
            logger.warn(f"【整理接管】更新文件ID失败 ({target_path}): {e}")

    def _batch_rename_files(
        self, tasks: List[TransferTask]
    ) -> Tuple[List[Tuple[TransferTask, str]], List[TransferTask]]:
        """
        批量重命名文件

        :param tasks: 任务列表

        :return: (失败任务列表, 成功任务列表)
        """
        logger.info("【整理接管】开始批量重命名文件")

        # 收集需要重命名的文件（file_id, new_name, task, is_main）
        rename_items: List[Tuple[int, str, TransferTask, bool]] = []

        for task in tasks:
            # 检查主视频是否需要重命名
            source_name = Path(task.fileitem.path).name
            target_name = task.target_name
            if source_name != target_name and task.fileitem.fileid:
                rename_items.append(
                    (int(task.fileitem.fileid), target_name, task, True)
                )

            # 检查关联文件是否需要重命名
            for related_file in task.related_files:
                source_name = Path(related_file.fileitem.path).name
                target_name = related_file.target_path.name
                if source_name != target_name and related_file.fileitem.fileid:
                    rename_items.append(
                        (int(related_file.fileitem.fileid), target_name, task, False)
                    )

        if not rename_items:
            logger.info("【整理接管】没有需要重命名的文件")
            return [], tasks

        try:
            update_name(
                self.client,
                [(file_id, new_name) for file_id, new_name, _, _ in rename_items],
                **configer.get_ios_ua_app(app=False),
            )
            for file_id, new_name, _, _ in rename_items:
                self.cache_updater.update_rename_cache(file_id, new_name)
            logger.info(
                f"【整理接管】批量重命名完成，共重命名 {len(rename_items)} 个文件"
            )
        except Exception as e:
            logger.error(f"【整理接管】批量重命名失败: {e}", exc_info=True)
            # 批量重命名失败，所有任务都失败
            failed_tasks: List[Tuple[TransferTask, str]] = []
            for file_id, new_name, task, is_main in rename_items:
                if is_main:
                    task_path = task.fileitem.path if task and task.fileitem else None
                    if task_path:
                        failed_tasks.append((task, f"批量重命名失败: {new_name}"))

            return failed_tasks, []

        # 所有重命名都成功
        return [], tasks

    def _record_related_files_success_history(
        self, task: TransferTask
    ) -> tuple[int, dict]:
        """
        为关联文件（字幕、音轨）补充独立的成功历史记录。

        :param task: 整理任务

        :return tuple[int, dict]: (写入数量, 历史记录字典 {文件路径: history对象})
        """
        if not task.related_files:
            return 0, {}

        recorded = 0
        related_file_histories = {}
        for related_file in task.related_files:
            try:
                if (
                    not related_file
                    or not related_file.fileitem
                    or not related_file.fileitem.path
                    or not related_file.target_path
                ):
                    continue

                target_path = related_file.target_path

                # 构造目标文件项
                target_fileitem = FileItem(
                    storage=self.storage_name,
                    path=str(target_path),
                    name=target_path.name,
                    fileid=related_file.fileitem.fileid,
                    type="file",
                    size=related_file.fileitem.size,
                    modify_time=related_file.fileitem.modify_time,
                    pickcode=related_file.fileitem.pickcode,
                )

                # 构造目标目录项
                target_diritem = FileItem(
                    storage=self.storage_name,
                    path=str(target_path.parent) + "/",
                    name=target_path.parent.name,
                    type="dir",
                )

                # 构造 TransferInfo（不触发通知/刮削）
                transferinfo = TransferInfo(
                    success=True,
                    fileitem=related_file.fileitem,
                    target_item=target_fileitem,
                    target_diritem=target_diritem,
                    transfer_type=task.transfer_type,
                    file_list=[related_file.fileitem.path],
                    file_list_new=[target_fileitem.path],
                    need_scrape=False,
                    need_notify=False,
                )

                # 写入独立历史记录（每个关联文件一条）
                related_history = self.history_oper.add_success(
                    fileitem=related_file.fileitem,
                    mode=task.transfer_type,
                    meta=task.meta,
                    mediainfo=task.mediainfo,
                    transferinfo=transferinfo,
                    downloader=task.downloader,
                    download_hash=task.download_hash,
                )
                # 保存历史记录，用于后续事件发送
                if related_history:
                    related_file_histories[related_file.fileitem.path] = related_history
                recorded += 1
            except Exception as e:
                name = "unknown"
                try:
                    if related_file and related_file.fileitem:
                        name = related_file.fileitem.name
                except Exception:
                    pass
                logger.error(
                    f"【整理接管】写入关联文件历史失败 (file: {name}): {e}",
                    exc_info=True,
                )

        return recorded, related_file_histories

    def _record_history(self, tasks: List[TransferTask]) -> None:
        """
        记录转移历史

        :param tasks: 任务列表
        """
        logger.info("【整理接管】开始记录转移历史")

        # 跟踪成功处理的任务
        successfully_recorded_tasks: List[TransferTask] = []

        for task in tasks:
            try:
                # 构造目标文件项
                target_fileitem = FileItem(
                    storage=self.storage_name,
                    path=str(task.target_path),
                    name=task.target_name,
                    fileid=task.fileitem.fileid,
                    type="file",
                    size=task.fileitem.size,
                    modify_time=task.fileitem.modify_time,
                    pickcode=task.fileitem.pickcode,
                )

                # 构造目标目录项
                target_diritem = FileItem(
                    storage=self.storage_name,
                    path=str(task.target_dir) + "/",
                    name=task.target_dir.name,
                    type="dir",
                )

                # 构造 TransferInfo
                transferinfo = TransferInfo(
                    success=True,
                    fileitem=task.fileitem,
                    target_item=target_fileitem,
                    target_diritem=target_diritem,
                    transfer_type=task.transfer_type,
                    file_list=[task.fileitem.path],
                    file_list_new=[target_fileitem.path],
                    need_scrape=task.scrape or False,
                    need_notify=task.need_notify
                    if task.need_notify is not None
                    else True,
                )

                # 添加关联文件到文件列表
                for related_file in task.related_files:
                    transferinfo.file_list.append(related_file.fileitem.path)
                    transferinfo.file_list_new.append(str(related_file.target_path))

                # 记录成功历史
                history = self.history_oper.add_success(
                    fileitem=task.fileitem,
                    mode=task.transfer_type,
                    meta=task.meta,
                    mediainfo=task.mediainfo,
                    transferinfo=transferinfo,
                    downloader=task.downloader,
                    download_hash=task.download_hash,
                )

                # 关联文件（字幕/音轨）写入历史（每个关联文件独立一条）
                related_file_histories = {}
                try:
                    related_count, related_file_histories = (
                        self._record_related_files_success_history(task)
                    )
                    if related_count:
                        logger.debug(
                            f"【整理接管】已写入 {related_count} 个关联文件历史记录: {task.fileitem.name}"
                        )
                except Exception as e:
                    logger.debug(
                        f"【整理接管】写入关联文件历史异常 (任务: {task.fileitem.name}): {e}",
                        exc_info=True,
                    )

                # 标记任务完成
                try:
                    chain = TransferChain()
                    mp_task = self._create_mp_task(task)
                    chain.jobview.finish_task(mp_task)
                    logger.debug(f"【整理接管】标记任务完成: {task.fileitem.path}")
                except Exception as e:
                    logger.warn(f"【整理接管】标记任务完成失败: {e}", exc_info=True)

                # 发送整理完成事件
                eventmanager.send_event(
                    EventType.TransferComplete,
                    {
                        "fileitem": task.fileitem,
                        "meta": task.meta,
                        "mediainfo": task.mediainfo,
                        "transferinfo": transferinfo,
                        "downloader": task.downloader,
                        "download_hash": task.download_hash,
                        "transfer_history_id": history.id if history else None,
                    },
                )

                # 关联文件（字幕/音轨）发送对应的事件
                for related_file in task.related_files:
                    related_history = (
                        related_file_histories.get(related_file.fileitem.path)
                        if related_file_histories
                        else None
                    )
                    if related_file.file_type == "subtitle":
                        eventmanager.send_event(
                            EventType.SubtitleTransferComplete,
                            {
                                "fileitem": related_file.fileitem,
                                "meta": task.meta,
                                "mediainfo": task.mediainfo,
                                "transferinfo": TransferInfo(
                                    success=True,
                                    fileitem=related_file.fileitem,
                                    target_item=FileItem(
                                        storage=self.storage_name,
                                        path=str(related_file.target_path),
                                        name=related_file.target_path.name,
                                        fileid=related_file.fileitem.fileid,
                                        type="file",
                                        size=related_file.fileitem.size,
                                        modify_time=related_file.fileitem.modify_time,
                                        pickcode=related_file.fileitem.pickcode,
                                    ),
                                    target_diritem=transferinfo.target_diritem,
                                    transfer_type=task.transfer_type,
                                    file_list=[related_file.fileitem.path],
                                    file_list_new=[str(related_file.target_path)],
                                    need_scrape=False,
                                    need_notify=False,
                                ),
                                "downloader": task.downloader,
                                "download_hash": task.download_hash,
                                "transfer_history_id": related_history.id
                                if related_history
                                else None,
                            },
                        )
                    elif related_file.file_type == "audio_track":
                        eventmanager.send_event(
                            EventType.AudioTransferComplete,
                            {
                                "fileitem": related_file.fileitem,
                                "meta": task.meta,
                                "mediainfo": task.mediainfo,
                                "transferinfo": TransferInfo(
                                    success=True,
                                    fileitem=related_file.fileitem,
                                    target_item=FileItem(
                                        storage=self.storage_name,
                                        path=str(related_file.target_path),
                                        name=related_file.target_path.name,
                                        fileid=related_file.fileitem.fileid,
                                        type="file",
                                        size=related_file.fileitem.size,
                                        modify_time=related_file.fileitem.modify_time,
                                        pickcode=related_file.fileitem.pickcode,
                                    ),
                                    target_diritem=transferinfo.target_diritem,
                                    transfer_type=task.transfer_type,
                                    file_list=[related_file.fileitem.path],
                                    file_list_new=[str(related_file.target_path)],
                                    need_scrape=False,
                                    need_notify=False,
                                ),
                                "downloader": task.downloader,
                                "download_hash": task.download_hash,
                                "transfer_history_id": related_history.id
                                if related_history
                                else None,
                            },
                        )

                # 登记转移成功文件清单到 _success_target_files
                try:
                    chain = TransferChain()
                    with task_lock:
                        # 登记转移成功文件清单
                        target_dir_path = transferinfo.target_diritem.path
                        target_files = transferinfo.file_list_new
                        if chain._success_target_files.get(target_dir_path):
                            chain._success_target_files[target_dir_path].extend(
                                target_files
                            )
                        else:
                            chain._success_target_files[target_dir_path] = target_files
                except Exception as e:
                    logger.debug(
                        f"【整理接管】登记文件清单到 _success_target_files 失败: {e}"
                    )

                # 整理完成且有成功的任务时，执行 __do_finished 逻辑
                try:
                    chain = TransferChain()
                    mp_task = self._create_mp_task(task)
                    if chain.jobview.is_finished(mp_task):
                        with task_lock:
                            # 更新文件数量和大小
                            transferinfo.file_count = (
                                chain.jobview.count(
                                    task.mediainfo, task.meta.begin_season
                                )
                                or 1
                            )
                            transferinfo.total_size = (
                                chain.jobview.size(
                                    task.mediainfo, task.meta.begin_season
                                )
                                or task.fileitem.size
                                or 0
                            )

                            # 从 _success_target_files pop 文件清单
                            popped_files = chain._success_target_files.pop(
                                transferinfo.target_diritem.path, []
                            )
                            if popped_files:
                                transferinfo.file_list_new = popped_files

                            # 发送通知
                            if transferinfo.need_notify and (
                                task.background or not task.manual
                            ):
                                try:
                                    se_str = None
                                    if task.mediainfo.type == MediaType.TV:
                                        season_episodes = chain.jobview.season_episodes(
                                            task.mediainfo,
                                            task.meta.begin_season,
                                        )
                                        if season_episodes:
                                            se_str = f"{task.meta.season} {StringUtils.format_ep(season_episodes)}"
                                        else:
                                            se_str = f"{task.meta.season}"
                                    chain.send_transfer_message(
                                        meta=task.meta,
                                        mediainfo=task.mediainfo,
                                        transferinfo=transferinfo,
                                        season_episode=se_str,
                                        username=task.username,
                                    )
                                except Exception as e:
                                    logger.warn(
                                        f"【整理接管】发送通知失败: {e}",
                                        exc_info=True,
                                    )

                            # 发送刮削事件
                            if transferinfo.need_scrape:
                                try:
                                    eventmanager.send_event(
                                        EventType.MetadataScrape,
                                        {
                                            "meta": task.meta,
                                            "mediainfo": task.mediainfo,
                                            "fileitem": target_diritem,
                                            "file_list": transferinfo.file_list_new,
                                            "overwrite": False,
                                        },
                                    )
                                except Exception as e:
                                    logger.warn(
                                        f"【整理接管】发送刮削事件失败: {e}",
                                        exc_info=True,
                                    )
                except Exception as e:
                    logger.debug(f"【整理接管】执行完成逻辑失败: {e}", exc_info=True)

                logger.debug(
                    f"【整理接管】记录成功历史: {task.fileitem.name} -> {task.target_name}"
                )
                # 记录成功处理的任务
                successfully_recorded_tasks.append(task)

            except Exception as e:
                logger.error(
                    f"【整理接管】记录历史失败 (任务: {task.fileitem.name}): {e}",
                    exc_info=True,
                )
                self._record_fail(task, f"记录历史失败: {e}")

        # 所有任务处理完成后，统一批量删除空目录
        if successfully_recorded_tasks:
            self._batch_delete_empty_dirs(successfully_recorded_tasks)

        try:
            # 按媒体分组，每个媒体组只需要移除一次
            tasks_by_media = self._group_tasks_by_media(successfully_recorded_tasks)
            removed_count = self._remove_completed_jobs(
                tasks_by_media, task_action="finish", check_method="is_finished"
            )

            if removed_count > 0:
                logger.info(f"【整理接管】已移除 {removed_count} 个已完成的任务组")
        except Exception as e:
            logger.debug(f"【整理接管】移除任务失败: {e}", exc_info=True)

        logger.info("【整理接管】历史记录完成")

    def _batch_delete_empty_dirs(self, tasks: List[TransferTask]) -> None:
        """
        批量删除空目录

        :param tasks: 任务列表
        """
        try:
            chain = TransferChain()

            # 按媒体信息分组任务
            move_tasks = [task for task in tasks if task.transfer_type == "move"]
            if not move_tasks:
                logger.debug("【整理接管】没有移动模式的任务，跳过删除空目录")
                return

            tasks_by_media = self._group_tasks_by_media(move_tasks)

            if not tasks_by_media:
                logger.debug("【整理接管】没有有效的媒体任务，跳过删除空目录")
                return

            logger.info(
                f"【整理接管】开始批量删除空目录，共 {len(tasks_by_media)} 个媒体组"
            )

            # 收集所有需要删除的目录
            all_dir_items_to_delete: List[FileItem] = []
            checked_parent_dirs: Dict[str, List[FileItem]] = {}

            # 遍历每个媒体组
            for (media_id, season), group_tasks in tasks_by_media.items():
                # 使用第一个任务检查 is_success（同一组的所有任务应该有相同的 mediainfo）
                sample_task = group_tasks[0]
                mp_sample_task = MPTransferTask(
                    fileitem=sample_task.fileitem,
                    mediainfo=sample_task.mediainfo,
                    meta=sample_task.meta,
                )
                is_success = chain.jobview.is_success(mp_sample_task)
                logger.debug(
                    f"【整理接管】检查媒体组 (media_id={media_id}, season={season}) is_success={is_success}"
                )

                # 如果 is_success 为 False，检查任务状态详情
                if not is_success:
                    try:
                        # 使用 JobManager 的内部方法获取任务状态
                        __mediaid__ = chain.jobview._JobManager__get_media_id(
                            media=sample_task.mediainfo,
                            season=sample_task.meta.begin_season,
                        )
                        if __mediaid__ in chain.jobview._job_view:
                            job = chain.jobview._job_view[__mediaid__]
                            task_states = [
                                f"{t.fileitem.name if t.fileitem else 'None'}: {t.state}"
                                for t in job.tasks
                            ]
                            logger.warn(
                                f"【整理接管】任务状态详情 (media_id={media_id}, season={season}): {task_states}"
                            )
                        else:
                            logger.warn(
                                f"【整理接管】媒体组 (media_id={media_id}, season={season}) 不在 job_view 中，可能已被移除"
                            )
                            logger.info(
                                "【整理接管】任务不在 job_view 中，使用传入的任务列表删除空目录"
                            )
                            # 使用传入的 group_tasks 来收集需要删除的目录
                            for t in group_tasks:
                                if t.fileitem:
                                    parent_dir_item = (
                                        t.fileitem
                                        if t.fileitem.type == "dir"
                                        else self.cache_updater._p115_api.get_parent(
                                            t.fileitem
                                        )
                                    )
                                    if parent_dir_item and parent_dir_item.path:
                                        parent_dir_path = parent_dir_item.path
                                        if parent_dir_path not in checked_parent_dirs:
                                            collected_dirs = (
                                                self._collect_dirs_to_delete(t.fileitem)
                                            )
                                            checked_parent_dirs[parent_dir_path] = (
                                                collected_dirs
                                            )
                                            all_dir_items_to_delete.extend(
                                                collected_dirs
                                            )
                            continue
                    except Exception as e:
                        logger.debug(
                            f"【整理接管】获取任务状态详情失败: {e}", exc_info=True
                        )

                if not is_success:
                    logger.warn(
                        f"【整理接管】媒体组 (media_id={media_id}, season={season}) 未全部成功，跳过删除空目录"
                    )
                    continue

                # 获取所有成功的任务
                success_tasks = chain.jobview.success_tasks(
                    sample_task.mediainfo, sample_task.meta.begin_season
                )
                logger.debug(
                    f"【整理接管】媒体组 (media_id={media_id}, season={season}) 有 {len(success_tasks)} 个成功任务"
                )

                for t in success_tasks:
                    # 收集需要删除的空目录（避免重复检查）
                    if t.fileitem:
                        logger.debug(
                            f"【整理接管】处理任务文件: {t.fileitem.path} (type: {t.fileitem.type})"
                        )
                        # 获取源文件的父目录作为检查键
                        parent_dir_item = (
                            t.fileitem
                            if t.fileitem.type == "dir"
                            else self.cache_updater._p115_api.get_parent(t.fileitem)
                        )
                        if parent_dir_item and parent_dir_item.path:
                            parent_dir_path = parent_dir_item.path
                            logger.debug(f"【整理接管】检查父目录: {parent_dir_path}")
                            # 如果这个父目录已经检查过，直接使用之前的结果
                            if parent_dir_path in checked_parent_dirs:
                                cached_dirs = checked_parent_dirs[parent_dir_path]
                                logger.debug(
                                    f"【整理接管】使用缓存的目录列表: {len(cached_dirs)} 个目录"
                                )
                                all_dir_items_to_delete.extend(cached_dirs)
                            else:
                                # 首次检查，收集所有需要删除的目录
                                logger.debug(
                                    f"【整理接管】首次检查目录: {parent_dir_path}"
                                )
                                collected_dirs = self._collect_dirs_to_delete(
                                    t.fileitem
                                )
                                logger.debug(
                                    f"【整理接管】收集到 {len(collected_dirs)} 个需要删除的目录: {[d.path for d in collected_dirs]}"
                                )
                                # 缓存结果
                                checked_parent_dirs[parent_dir_path] = collected_dirs
                                all_dir_items_to_delete.extend(collected_dirs)
                        else:
                            logger.debug(
                                f"【整理接管】无法获取父目录 (fileitem: {t.fileitem.path})"
                            )
                    else:
                        logger.debug(f"【整理接管】任务没有 fileitem (task: {t})")

            # 去重（使用 fileid 作为唯一标识）
            unique_dir_items = {}
            for dir_item in all_dir_items_to_delete:
                if dir_item.fileid:
                    unique_dir_items[int(dir_item.fileid)] = dir_item

            logger.info(
                f"【整理接管】收集到 {len(unique_dir_items)} 个需要删除的空目录"
            )

            # 批量删除空目录
            if unique_dir_items:
                # 按路径深度排序
                sorted_dir_items = sorted(
                    unique_dir_items.items(),
                    key=lambda x: len(Path(x[1].path).parts),
                    reverse=True,
                )
                dir_paths = [
                    unique_dir_items[dir_id].path for dir_id, _ in sorted_dir_items
                ]
                logger.info(
                    f"【整理接管】准备删除 {len(sorted_dir_items)} 个空目录: {dir_paths[:5]}..."
                )

                # 批量删除所有空目录
                deleted_count = 0
                # 按目录树分组
                dir_trees: Dict[Path, List[Tuple[int, FileItem]]] = defaultdict(list)
                for dir_id, dir_item in sorted_dir_items:
                    dir_path = Path(dir_item.path)
                    tree_root = None
                    parent_dirs = []
                    for other_id, other_item in sorted_dir_items:
                        other_path = Path(other_item.path)
                        if (
                            dir_path.is_relative_to(other_path)
                            and dir_path != other_path
                        ):
                            parent_dirs.append((other_id, other_item, other_path))
                    for parent_id, parent_item, parent_path in parent_dirs:
                        is_subdir = False
                        for (
                            other_parent_id,
                            other_parent_item,
                            other_parent_path,
                        ) in parent_dirs:
                            if parent_id == other_parent_id:
                                continue
                            if (
                                parent_path.is_relative_to(other_parent_path)
                                and parent_path != other_parent_path
                            ):
                                is_subdir = True
                                break
                        if not is_subdir:
                            if tree_root is None or len(parent_path.parts) < len(
                                tree_root.parts
                            ):
                                tree_root = parent_path
                    if tree_root is None:
                        tree_root = dir_path
                    dir_trees[tree_root].append((dir_id, dir_item))

                dir_ids_to_delete = []
                for tree_root, dirs_in_tree in dir_trees.items():
                    max_depth_in_tree = max(
                        len(Path(dir_item.path).parts) for _, dir_item in dirs_in_tree
                    )
                    min_depth_dirs_in_tree = [
                        (dir_id, dir_item)
                        for dir_id, dir_item in dirs_in_tree
                        if len(Path(dir_item.path).parts) == max_depth_in_tree
                    ]
                    tree_exists = True
                    for dir_id, dir_item in min_depth_dirs_in_tree:
                        try:
                            current_dir = self.cache_updater._p115_api.get_item(
                                Path(dir_item.path)
                            )
                            if not current_dir:
                                # 该目录树的最小深度目录已被删除，说明整个目录树都被删除了
                                tree_exists = False
                                logger.debug(
                                    f"【整理接管】目录树 {tree_root} 的最小深度目录已被删除 ({dir_item.path})，跳过该目录树"
                                )
                                break
                        except Exception as e:
                            logger.debug(
                                f"【整理接管】检查目录树 {tree_root} 的最小深度目录状态失败 ({dir_item.path}): {e}"
                            )
                            tree_exists = False
                            break

                    if tree_exists:
                        # 该目录树存在，收集该目录树的所有目录 ID
                        dir_ids_to_delete.extend([dir_id for dir_id, _ in dirs_in_tree])
                    else:
                        logger.debug(
                            f"【整理接管】目录树 {tree_root} 已被删除，跳过 {len(dirs_in_tree)} 个目录"
                        )

                if not dir_ids_to_delete:
                    logger.debug("【整理接管】所有目录树都已删除，无需删除")
                else:
                    # 一次性批量删除所有空目录
                    try:
                        resp = self.client.fs_delete(
                            dir_ids_to_delete, **configer.get_ios_ua_app(app=False)
                        )
                        check_response(resp)
                        for dir_id in dir_ids_to_delete:
                            self.cache_updater.remove_cache(dir_id)
                        deleted_count = len(dir_ids_to_delete)
                        logger.info(
                            f"【整理接管】批量删除空目录成功: {deleted_count} 个目录"
                        )
                    except Exception as batch_delete_error:
                        logger.error(
                            f"【整理接管】批量删除空目录失败: {batch_delete_error}",
                            exc_info=True,
                        )

                logger.info(
                    f"【整理接管】删除空目录完成: {deleted_count}/{len(sorted_dir_items)} 个目录"
                )
            else:
                logger.debug("【整理接管】没有需要删除的空目录")

        except Exception as e:
            logger.debug(f"【整理接管】批量删除空目录失败: {e}", exc_info=True)

    def _collect_dirs_to_delete(self, fileitem: FileItem) -> List[FileItem]:
        """
        收集需要删除的空目录

        :param fileitem: 文件项

        :return: 需要删除的目录列表
        """
        dirs_to_delete: List[FileItem] = []
        media_exts = (
            settings.RMT_MEDIAEXT
            + settings.DOWNLOAD_TMPEXT
            + settings.RMT_SUBEXT
            + settings.RMT_AUDIOEXT
        )
        fileitem_path = Path(fileitem.path) if fileitem.path else Path("")

        # 检查路径深度（不能删除根目录或一级目录）
        if len(fileitem_path.parts) <= 2:
            logger.debug(f"【整理接管】{fileitem.path} 根目录或一级目录不允许删除")
            return dirs_to_delete

        # 如果是目录类型且是蓝光原盘，需要特殊处理
        if fileitem.type == "dir":
            if self.storage_chain.is_bluray_folder(fileitem):
                # 蓝光原盘目录，直接返回（需要删除整个目录）
                dirs_to_delete.append(fileitem)
                return dirs_to_delete

        # 检查和删除上级空目录
        dir_item = (
            fileitem
            if fileitem.type == "dir"
            else self.cache_updater._p115_api.get_parent(fileitem)
        )
        if not dir_item:
            logger.debug(f"【整理接管】{fileitem.path} 上级目录不存在")
            return dirs_to_delete

        # 查找操作文件项匹配的配置目录 (资源目录、媒体库目录)
        associated_dir = max(
            (
                Path(p)
                for d in DirectoryHelper().get_dirs()
                for p in (d.download_path, d.library_path)
                if p and fileitem_path.is_relative_to(Path(p))
            ),
            key=lambda path: len(path.parts),
            default=None,
        )

        # 递归检查父目录
        while dir_item and len(Path(dir_item.path).parts) > 2:
            dir_path = Path(dir_item.path)

            if associated_dir and associated_dir.is_relative_to(dir_path):
                logger.debug(
                    f"【整理接管】{dir_item.path} 位于资源或媒体库目录结构中，不删除"
                )
                break

            # 如果不在资源/媒体库目录结构中，检查是否有任何文件（包括子目录、nfo、jpg等）
            elif not associated_dir:
                try:
                    dir_files = self.cache_updater._p115_api.list(dir_item)
                    if dir_files:
                        logger.debug(
                            f"【整理接管】{dir_item.path} 不是空目录（有 {len(dir_files)} 个文件），不删除"
                        )
                        break
                except Exception as e:
                    logger.debug(
                        f"【整理接管】检查目录文件列表失败 ({dir_item.path}): {e}",
                        exc_info=True,
                    )
                    break

            # 检查：目录存在媒体文件，则不删除
            def __any_file(_item: FileItem):
                """
                递归处理
                """
                _items = self.cache_updater._p115_api.list(_item)
                if _items:
                    if not media_exts:
                        return True
                    for t in _items:
                        if (
                            t.type == "file"
                            and t.extension
                            and f".{t.extension.lower()}" in media_exts
                        ):
                            return True
                        elif t.type == "dir":
                            if __any_file(t):
                                return True
                return False

            try:
                has_media = __any_file(dir_item)
                if has_media is not False:
                    logger.debug(f"【整理接管】{dir_item.path} 存在媒体文件，不删除")
                    break
            except Exception as e:
                logger.debug(
                    f"【整理接管】检查媒体文件失败 ({dir_item.path}): {e}",
                    exc_info=True,
                )
                break

            # 所有检查通过，可以删除此目录
            logger.debug(f"【整理接管】收集到需要删除的空目录: {dir_item.path}")
            dirs_to_delete.append(dir_item)

            # 继续检查父目录
            dir_item = self.cache_updater._p115_api.get_parent(dir_item)

        return dirs_to_delete

    def _batch_record_failures(
        self, failed_tasks: List[Tuple[TransferTask, str]]
    ) -> None:
        """
        批量记录失败历史

        :param failed_tasks: 失败任务列表，每个元素为 (task, error_message)
        """
        if not failed_tasks:
            return

        logger.info(f"【整理接管】批量记录失败历史，共 {len(failed_tasks)} 个失败任务")

        # 先记录所有失败历史
        for task, message in failed_tasks:
            try:
                self._record_fail(task, message)
            except Exception as e:
                logger.error(
                    f"【整理接管】记录失败历史失败 (任务: {task.fileitem.name}): {e}",
                    exc_info=True,
                )

        # 按媒体分组，统一处理失败任务的移除
        try:
            # 提取任务列表（从 (task, message) 元组中提取）
            tasks = [task for task, _ in failed_tasks]
            # 按媒体分组，每个媒体组只需要移除一次
            tasks_by_media = self._group_tasks_by_media(tasks)
            removed_count = self._remove_completed_jobs(
                tasks_by_media, task_action="fail", check_method="is_done"
            )

            if removed_count > 0:
                logger.info(f"【整理接管】已移除 {removed_count} 个已完成的失败任务组")
        except Exception as e:
            logger.debug(f"【整理接管】移除失败任务失败: {e}", exc_info=True)

    def _record_fail(self, task: TransferTask, message: str) -> None:
        """
        记录失败历史并处理失败任务

        :param task: 任务
        :param message: 失败原因
        """
        try:
            # 构造 TransferInfo
            transferinfo = TransferInfo(
                success=False,
                fileitem=task.fileitem,
                transfer_type=task.transfer_type,
                message=message,
            )

            # 记录失败历史
            history = self.history_oper.add_fail(
                fileitem=task.fileitem,
                mode=task.transfer_type,
                meta=task.meta,
                mediainfo=task.mediainfo,
                transferinfo=transferinfo,
            )

            # 发送整理失败事件
            eventmanager.send_event(
                EventType.TransferFailed,
                {
                    "fileitem": task.fileitem,
                    "meta": task.meta,
                    "mediainfo": task.mediainfo,
                    "transferinfo": transferinfo,
                    "downloader": task.downloader,
                    "download_hash": task.download_hash,
                    "transfer_history_id": history.id if history else None,
                },
            )

            # 关联文件（字幕/音轨）记录历史并发送对应的失败事件
            for related_file in task.related_files:
                related_transferinfo = TransferInfo(
                    success=False,
                    fileitem=related_file.fileitem,
                    transfer_type=task.transfer_type,
                    message=message,
                )
                related_history = self.history_oper.add_fail(
                    fileitem=related_file.fileitem,
                    mode=task.transfer_type,
                    meta=task.meta,
                    mediainfo=task.mediainfo,
                    transferinfo=related_transferinfo,
                    downloader=task.downloader,
                    download_hash=task.download_hash,
                )
                if related_file.file_type == "subtitle":
                    eventmanager.send_event(
                        EventType.SubtitleTransferFailed,
                        {
                            "fileitem": related_file.fileitem,
                            "meta": task.meta,
                            "mediainfo": task.mediainfo,
                            "transferinfo": related_transferinfo,
                            "downloader": task.downloader,
                            "download_hash": task.download_hash,
                            "transfer_history_id": related_history.id
                            if related_history
                            else None,
                        },
                    )
                elif related_file.file_type == "audio_track":
                    eventmanager.send_event(
                        EventType.AudioTransferFailed,
                        {
                            "fileitem": related_file.fileitem,
                            "meta": task.meta,
                            "mediainfo": task.mediainfo,
                            "transferinfo": related_transferinfo,
                            "downloader": task.downloader,
                            "download_hash": task.download_hash,
                            "transfer_history_id": related_history.id
                            if related_history
                            else None,
                        },
                    )

            # 发送失败通知
            try:
                chain = TransferChain()
                chain.post_message(
                    Notification(
                        mtype=NotificationType.Manual,
                        title=f"{task.mediainfo.title_year} {task.meta.season_episode} 入库失败！",
                        text=f"原因：{message or '未知'}",
                        image=task.mediainfo.get_message_image()
                        if task.mediainfo
                        else None,
                        username=task.username,
                        link=settings.MP_DOMAIN("#/history"),
                    )
                )
            except Exception as e:
                logger.debug(f"【整理接管】发送失败通知失败: {e}", exc_info=True)

            # 标记任务失败
            try:
                chain = TransferChain()
                mp_task = self._create_mp_task(task)
                chain.jobview.fail_task(mp_task)
            except Exception as e:
                logger.debug(f"【整理接管】标记任务失败失败: {e}", exc_info=True)

            logger.debug(f"【整理接管】记录失败历史: {task.fileitem.name} - {message}")
        except Exception as e:
            logger.error(f"【整理接管】记录失败历史异常: {e}", exc_info=True)
