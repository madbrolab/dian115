from pathlib import Path
from time import sleep
from typing import Tuple, List, Optional, Dict
from uuid import uuid4

from p115client import P115Client
from p115client.tool import iter_files_with_path_skim
from p115pickcode import to_id

from ...core.u115_open import U115OpenHelper
from ...core.p115 import get_pid_by_path
from ...core.config import configer
from ...core.scrape import media_scrape_metadata
from ...helper.mediainfo_download import MediaInfoDownloader
from ...helper.mediaserver import MediaServerRefresh
from ...schemas.strm_api import (
    StrmApiPayloadData,
    StrmApiPayloadByPathData,
    StrmApiPayloadRemoveData,
    StrmApiPayloadRemoveItem,
    StrmApiResponseData,
    StrmApiResponseByPathItem,
    StrmApiResponseByPathData,
    StrmApiResponseFail,
    StrmApiResponseRemoveData,
    StrmApiData,
    StrmApiStatusCode,
)
from ...utils.tree import DirectoryTree
from ...utils.strm import StrmUrlGetter, StrmGenerater
from ...utils.path import PathUtils, PathRemoveUtils
from ...utils.sentry import sentry_manager

from app.log import logger


class ApiSyncStrmHelper:
    """
    API 调用生成 STRM
    """

    cooldown: int | float = 1

    def __init__(self, client: P115Client, mediainfo_downloader: MediaInfoDownloader):
        self.client = client
        self.open_client = U115OpenHelper()
        self.mediainfo_downloader = mediainfo_downloader

        self.strm_url_getter = StrmUrlGetter()

        self.rmt_mediaext = {
            f".{ext.strip()}"
            for ext in configer.user_rmt_mediaext.replace("，", ",").split(",")
        }
        self.download_mediaext_set = {
            f".{ext.strip()}"
            for ext in configer.user_download_mediaext.replace("，", ",").split(",")
        }

    def generate_strm_files(
        self, payload: StrmApiPayloadData
    ) -> Tuple[int, str, StrmApiResponseData]:
        """
        生成 STRM 文件
        """
        if not payload.data:
            return StrmApiStatusCode.MissPayload, "未传有效参数", StrmApiResponseData()

        success_strm_count = 0
        fail_strm_count = 0

        success_data: List[StrmApiData] = []
        fail_data: List[StrmApiResponseFail] = []

        download_list: List[Dict] = []

        for item in payload.data:
            if not item.pick_code and not item.id and not item.pan_path:
                fail_data.append(
                    StrmApiResponseFail(
                        **item.model_dump(),
                        code=StrmApiStatusCode.MissPcOrId,
                        reason="缺失必要参数，pick_code，id 或 pan_path 参数",
                    )
                )
                fail_strm_count += 1
                continue

            file_id = None
            pick_code = None
            if item.id or item.pick_code:
                file_id = item.id if item.id else to_id(item.pick_code)
                pick_code = (
                    item.pick_code
                    if item.pick_code
                    else self.client.to_pickcode(item.id)
                )
            name = item.name
            pan_path = item.pan_path
            sha1 = item.sha1
            size = item.size
            local_path = item.local_path
            pan_media_path = item.pan_media_path

            if not pan_path or not sha1 or not size or not file_id:
                try:
                    if file_id:
                        file_info = self.open_client.get_item_info(file_id)
                    else:
                        file_info = self.open_client.get_item_info(pan_path)
                    if not file_info:
                        fail_data.append(
                            StrmApiResponseFail(
                                **item.model_dump(),
                                code=StrmApiStatusCode.GetPanMediaPathError,
                                reason="无法获取文件信息",
                            )
                        )
                        fail_strm_count += 1
                        continue
                    file_id = file_info.get("file_id")
                    pick_code = file_info.get("pick_code")
                    pan_path = file_info.get("path")
                    sha1 = file_info.get("sha1")
                    size = file_info.get("size_byte")
                    sleep(self.cooldown)
                except Exception as e:
                    logger.error(f"【API_STRM生成】获取文件信息失败: {e}")
                    fail_data.append(
                        StrmApiResponseFail(
                            **item.model_dump(),
                            code=StrmApiStatusCode.GetPanMediaPathError,
                            reason=f"获取文件信息失败: {e}",
                        )
                    )
                    fail_strm_count += 1
                    continue

            if not pan_path:
                fail_data.append(
                    StrmApiResponseFail(
                        **item.model_dump(),
                        code=StrmApiStatusCode.GetPanMediaPathError,
                        reason="无法获取文件路径",
                    )
                )
                fail_strm_count += 1
                continue

            if not name:
                name = Path(pan_path).name

            if not local_path:
                for paths in configer.api_strm_config:
                    if PathUtils.has_prefix(pan_path, paths.pan_path):
                        local_path = paths.local_path
                        pan_media_path = paths.pan_path
                        break
                if not local_path:
                    fail_data.append(
                        StrmApiResponseFail(
                            **item.model_dump(),
                            code=StrmApiStatusCode.GetLocalPathError,
                            reason="无法获取本地生成 STRM 路径",
                        )
                    )
                    fail_strm_count += 1
                    continue

            if not pan_media_path:
                for paths in configer.api_strm_config:
                    if local_path == paths.local_path:
                        pan_media_path = paths.pan_path
                        break
                if not pan_media_path:
                    fail_data.append(
                        StrmApiResponseFail(
                            **item.model_dump(),
                            code=StrmApiStatusCode.GetPanMediaPathError,
                            reason="无法获取网盘媒体库路径",
                        )
                    )
                    fail_strm_count += 1
                    continue

            if item.scrape_metadata is None:
                scrape_metadata = configer.api_strm_scrape_metadata_enabled
            else:
                scrape_metadata = item.scrape_metadata

            if item.media_server_refresh is None:
                media_server_refresh = configer.api_strm_media_server_refresh_enabled
            else:
                media_server_refresh = item.media_server_refresh

            auto_download_mediainfo = item.auto_download_mediainfo

            local_path_obj = Path(local_path)
            pan_path_obj = Path(pan_path)
            try:
                file_path = local_path_obj / pan_path_obj.relative_to(pan_media_path)
            except ValueError as e:
                logger.error(
                    f"【API_STRM生成】路径计算失败: pan_path={pan_path}, pan_media_path={pan_media_path}, {e}"
                )
                fail_data.append(
                    StrmApiResponseFail(
                        **item.model_dump(),
                        code=StrmApiStatusCode.GetPanMediaPathError,
                        reason="路径计算失败: pan_media_path 不是 pan_path 的前缀",
                    )
                )
                fail_strm_count += 1
                continue
            new_file_path = file_path.parent / StrmGenerater.get_strm_filename(
                file_path
            )

            if (
                pan_path_obj.suffix.lower() in self.download_mediaext_set
                and auto_download_mediainfo
            ):
                download_list.append(
                    {
                        "type": "local",
                        "pickcode": pick_code,
                        "path": file_path.as_posix(),
                        "sha1": sha1,
                    }
                )
                continue

            if pan_path_obj.suffix.lower() not in self.rmt_mediaext:
                fail_data.append(
                    StrmApiResponseFail(
                        **item.model_dump(),
                        code=StrmApiStatusCode.NotRmtMediaExt,
                        reason="文件扩展名不属于可整理媒体文件扩展名",
                    )
                )
                fail_strm_count += 1
                continue

            strm_api_data = StrmApiData(
                name=name,
                sha1=sha1,
                size=size,
                pick_code=pick_code,
                pan_path=pan_path,
                id=file_id,
                local_path=local_path,
                pan_media_path=pan_media_path,
                scrape_metadata=scrape_metadata,
                media_server_refresh=media_server_refresh,
                auto_download_mediainfo=auto_download_mediainfo,
            )

            strm_url = self.strm_url_getter.get_strm_url(pick_code, name, pan_path)
            try:
                new_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(new_file_path, "w", encoding="utf-8") as file:
                    file.write(strm_url)
            except Exception as e:
                sentry_manager.sentry_hub.capture_exception(e)
                fail_data.append(
                    StrmApiResponseFail(
                        **strm_api_data.model_dump(),
                        code=StrmApiStatusCode.CreateStrmError,
                        reason=f"STRM 文件生成失败: {e}",
                    )
                )
                fail_strm_count += 1
                logger.error(
                    f"【API_STRM生成】{new_file_path.as_posix()} 文件生成失败: {e}"
                )
                continue

            logger.info(f"【API_STRM生成】{new_file_path.as_posix()} 文件生成成功")
            success_data.append(strm_api_data)
            success_strm_count += 1

            if scrape_metadata:
                logger.info(f"【API_STRM生成】{new_file_path.as_posix()} 开始刮削...")
                media_scrape_metadata(new_file_path.as_posix())

            if media_server_refresh:
                media_refresh_helper = MediaServerRefresh(
                    func_name="【API_STRM生成】",
                    enabled=media_server_refresh,
                    mp_mediaserver=configer.api_strm_mp_mediaserver_paths,
                    mediaservers=configer.api_strm_mediaservers,
                )
                media_refresh_helper.refresh_mediaserver(
                    file_path=new_file_path.as_posix(), file_name=new_file_path.name
                )

        mediainfo_count = 0
        mediainfo_fail_count = 0
        mediainfo_fail_dict: List[str] = []
        if download_list:
            logger.info(
                f"【API_STRM生成】开始批量下载媒体信息文件，共 {len(download_list)} 个文件"
            )
            mediainfo_count, mediainfo_fail_count, mediainfo_fail_dict = (
                self.mediainfo_downloader.batch_auto_downloader(
                    downloads_list=download_list,
                )
            )
            logger.info(
                f"【API_STRM生成】媒体信息文件下载完成，成功: {mediainfo_count}, 失败: {mediainfo_fail_count}"
            )

        return (
            StrmApiStatusCode.Success,
            "生成完成",
            StrmApiResponseData(
                success=success_data,
                fail=fail_data,
                download_fail=mediainfo_fail_dict,
                success_count=success_strm_count,
                fail_count=fail_strm_count,
                download_success_count=mediainfo_count,
                download_fail_count=mediainfo_fail_count,
            ),
        )

    def generate_strm_paths(
        self, payload: StrmApiPayloadByPathData
    ) -> Tuple[int, str, StrmApiResponseByPathData]:
        """
        根据文件夹列表生成 STRM 文件
        """
        if not payload.data:
            return (
                StrmApiStatusCode.MissPayload,
                "未传有效参数",
                StrmApiResponseByPathData(),
            )

        success_strm_count = 0
        fail_strm_count = 0
        download_success_count = 0
        download_fail_count = 0

        success_data: List[StrmApiData] = []
        fail_data: List[StrmApiResponseFail] = []
        download_fail: List[str] = []
        paths_info: List[StrmApiResponseByPathItem] = []

        for path in payload.data:
            try:
                parent_id = get_pid_by_path(
                    self.client, path.pan_media_path, True, False, False
                )
                logger.info(
                    f"【API_STRM生成】网盘媒体目录 ID 获取成功: {path.pan_media_path} {parent_id}"
                )
            except Exception as e:
                sentry_manager.sentry_hub.capture_exception(e)
                logger.error(
                    f"【API_STRM生成】网盘媒体目录 ID 获取失败: {path.pan_media_path} {e}"
                )
                continue

            path_payload = {}
            if path.local_path:
                path_payload = {
                    "pan_media_path": path.pan_media_path,
                    "local_path": path.local_path,
                }

            file_list: List[StrmApiData] = []
            uuid: Optional[str] = None

            if path.remove_strm_uuid:
                uuid = str(uuid4())
                pan_tree = DirectoryTree(
                    configer.PLUGIN_TEMP_PATH / f"{uuid}_pan_tree.txt"
                )

            for item in iter_files_with_path_skim(
                self.client,
                cid=parent_id,
                with_ancestors=True,
                **configer.get_ios_ua_app(),
            ):
                try:
                    file_list.append(
                        StrmApiData(
                            id=item["id"],
                            pick_code=item["pickcode"],
                            name=item["name"],
                            sha1=item["sha1"],
                            size=item["size"],
                            pan_path=item["path"],
                            media_server_refresh=payload.media_server_refresh,
                            scrape_metadata=payload.scrape_metadata,
                            auto_download_mediainfo=payload.auto_download_mediainfo,
                            **path_payload,
                        )
                    )
                except ValueError:
                    logger.error(f"【API_STRM生成】文件信息缺失: {item}")
                    continue

            logger.info(
                f"【API_STRM生成】提取 {len(file_list)} 个文件数据，开始生成 STRM ..."
            )

            result = self.generate_strm_files(
                StrmApiPayloadData(
                    data=file_list,
                )
            )

            success_strm_count += result[2].success_count
            fail_strm_count += result[2].fail_count
            download_success_count += result[2].download_success_count
            download_fail_count += result[2].download_fail_count

            success_data.extend(result[2].success)
            fail_data.extend(result[2].fail)
            download_fail.extend(result[2].download_fail)

            if path.remove_strm_uuid:
                lst: List[str] = []
                for item in result[2].success:
                    try:
                        file_path = Path(item.local_path) / Path(
                            item.pan_path
                        ).relative_to(item.pan_media_path)
                        new_file_path = (
                            file_path.parent
                            / StrmGenerater.get_strm_filename(file_path)
                        )
                        lst.append(new_file_path.as_posix())
                    except ValueError:
                        continue
                pan_tree.generate_tree_from_list(lst)  # noqa

            paths_info.append(
                StrmApiResponseByPathItem(
                    local_path=path.local_path,
                    pan_media_path=path.pan_media_path,
                    remove_strm_uuid=uuid,
                )
            )

        return (
            StrmApiStatusCode.Success,
            "生成完成",
            StrmApiResponseByPathData(
                success=success_data,
                fail=fail_data,
                download_fail=download_fail,
                success_count=success_strm_count,
                fail_count=fail_strm_count,
                download_success_count=download_success_count,
                download_fail_count=download_fail_count,
                paths_info=paths_info,
            ),
        )

    def remove_unless_strm(
        self, payload: StrmApiPayloadRemoveData
    ) -> Tuple[int, str, StrmApiResponseRemoveData]:
        """
        删除无效 STRM 文件
        """

        if not payload.data:
            return (
                StrmApiStatusCode.MissPayload,
                "未传有效参数",
                StrmApiResponseRemoveData(),
            )

        remove_strm_count = 0
        config_data: List[StrmApiPayloadRemoveItem] = []

        for item in payload.data:
            if not item.remove_strm_uuid:
                uuid = str(uuid4())
                pan_tree = DirectoryTree(
                    configer.PLUGIN_TEMP_PATH / f"{uuid}_pan_tree.txt"
                )
                lst: List[str] = []
                try:
                    parent_id = get_pid_by_path(
                        self.client, item.pan_media_path, True, False, False
                    )
                    logger.info(
                        f"【API_STRM生成】网盘媒体目录 ID 获取成功: {item.pan_media_path} {parent_id}"
                    )
                except Exception as e:
                    sentry_manager.sentry_hub.capture_exception(e)
                    logger.error(
                        f"【API_STRM生成】网盘媒体目录 ID 获取失败: {item.pan_media_path} {e}"
                    )
                    continue
                for i in iter_files_with_path_skim(
                    self.client,
                    cid=parent_id,
                    with_ancestors=True,
                    **configer.get_ios_ua_app(),
                ):
                    try:
                        path = Path(i["path"])
                        if path.suffix.lower() in self.rmt_mediaext:
                            file_path = Path(item.local_path) / path.relative_to(
                                item.pan_media_path
                            )
                            new_file_path = (
                                file_path.parent
                                / StrmGenerater.get_strm_filename(file_path)
                            )
                            lst.append(new_file_path.as_posix())
                    except ValueError:
                        logger.error(f"【API_STRM生成】文件信息缺失: {i}")
                        continue
                pan_tree.generate_tree_from_list(lst)
                logger.info(f"【API_STRM生成】生成网盘目录树完成 {item.pan_media_path}")
            else:
                uuid = item.remove_strm_uuid
                pan_tree = DirectoryTree(
                    configer.PLUGIN_TEMP_PATH / f"{uuid}_pan_tree.txt"
                )
                logger.info(f"【API_STRM生成】使用缓存网盘目录树 {item.pan_media_path}")

            try:
                local_tree = DirectoryTree(
                    configer.PLUGIN_TEMP_PATH / f"{uuid}_local_tree.txt"
                )
                local_tree.scan_directory_to_tree(
                    root_path=item.local_path,
                    append=False,
                    extensions=[".strm"],
                )

                logger.info(f"【API_STRM生成】生成本地目录树完成 {item.local_path}")

                for remove_path in local_tree.compare_trees(pan_tree):
                    logger.info(f"【API_STRM生成】清理无效 STRM 文件: {remove_path}")
                    Path(remove_path).unlink(missing_ok=True)
                    if item.remove_unless_meta:
                        PathRemoveUtils.clean_related_files(
                            file_path=Path(remove_path),
                            func_type="【API_STRM生成】",
                        )
                    if item.remove_unless_parent:
                        PathRemoveUtils.remove_parent_dir(
                            file_path=Path(remove_path),
                            mode=["strm"],
                            func_type="【API_STRM生成】",
                        )
                    remove_strm_count += 1

                config_data.append(
                    StrmApiPayloadRemoveItem(
                        **item.model_dump(exclude={"remove_strm_uuid"}),
                        remove_strm_uuid=uuid,
                    )
                )

                pan_tree.clear()
                local_tree.clear()
            except Exception as e:
                sentry_manager.sentry_hub.capture_exception(e)
                logger.error(
                    f"【API_STRM生成】清理无效 STRM 文件失败: {item.pan_media_path} -> {item.local_path} {e}"
                )
                try:
                    pan_tree.clear()
                except Exception:
                    pass
                try:
                    if local_tree:  # noqa
                        local_tree.clear()  # noqa
                except Exception:
                    pass
                continue

        logger.info(
            f"【API_STRM生成】清理无效 STRM 文件完成，本次清理 {remove_strm_count} 个"
        )

        return (
            StrmApiStatusCode.Success,
            "清理完成",
            StrmApiResponseRemoveData(
                remove_strm_count=remove_strm_count, data=config_data
            ),
        )
