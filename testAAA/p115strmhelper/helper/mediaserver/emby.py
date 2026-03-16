from pathlib import Path
from queue import Queue
from threading import Thread
from time import sleep
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import quote

from httpx import RequestError, post as httpx_post
from p115center import P115Center

from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.schemas import ServiceInfo
from app.utils.http import RequestUtils

from ...core.config import configer
from ...schemas.emby_mediainfo import EmbyMediainfoTask
from ...utils.path import PathUtils


class EmbyOperate:
    """
    Emby 媒体服务器操作类
    """

    def __init__(self, func_name: str):
        self.func_name = func_name
        self.mediaserver_helper = MediaServerHelper()

    def get_emby_info(self, name: str) -> Tuple[str, str, str]:
        """
        获取 Emby 服务器信息

        :param name: Emby Server Name

        :return: Emby 服务器信息
        """
        emby_server = self.mediaserver_helper.get_service(name=name, type_filter="emby")
        emby_user = emby_server.instance.get_user()
        emby_apikey = emby_server.config.config.get("apikey")
        emby_host = emby_server.config.config.get("host")
        if not emby_host:
            return "", "", ""
        if not emby_host.endswith("/"):
            emby_host += "/"
        if not emby_host.startswith("http"):
            emby_host = "http://" + emby_host  # noqa
        return emby_host, emby_user, emby_apikey

    def get_series_tmdb_id(self, name: str, series_id: str) -> Optional[str]:
        """
        获取剧集 TMDB ID

        :param name: Emby Server Name
        :param series_id: 剧集ID

        :return: TMDB ID
        """
        emby_host, emby_user, emby_apikey = self.get_emby_info(name)
        if not emby_host:
            return None

        req_url = (
            f"{emby_host}emby/Users/{emby_user}/Items/{series_id}?api_key={emby_apikey}"
        )
        try:
            with RequestUtils().get_res(req_url) as res:
                if res:
                    return res.json().get("ProviderIds", {}).get("Tmdb")
                else:
                    logger.warning(
                        f"{self.func_name}获取剧集 TMDB ID 失败，Emby 未返回有效响应 name={name!r} series_id={series_id!r}"
                    )
                    return None
        except Exception as e:
            logger.error(
                f"{self.func_name}获取剧集 TMDB ID 异常 name={name!r} series_id={series_id!r}: {e}",
            )
            return None

    def get_item_id_by_path(self, name: str, path: str) -> Optional[str]:
        """
        依据路径获取 Emby 项目 ID

        :param name: Emby Server Name
        :param path: 项目路径

        :return: 项目 ID
        """
        emby_host, _, emby_apikey = self.get_emby_info(name)
        if not emby_host:
            return None

        req_url = f"{emby_host}emby/Items"
        params = {
            "Path": path,
            "Recursive": "true",
            "Fields": "Path",
            "IncludeItemTypes": "Movie,Episode,Folder,Series",
            "api_key": emby_apikey,
        }
        try:
            with RequestUtils().get_res(url=req_url, params=params) as res:
                if res:
                    items = res.json().get("Items", [])
                    for item in items:
                        if item.get("Path") == path:
                            return item.get("Id")
                    logger.warning(
                        f"{self.func_name}无法获取项目 Id，未匹配到路径 name={name!r} path={path!r}"
                    )
                else:
                    logger.warning(
                        f"{self.func_name}获取项目 Id 失败，Emby 未返回有效响应 name={name!r} path={path!r}"
                    )
            return None
        except Exception as e:
            logger.error(
                f"{self.func_name}获取项目 Id 异常 name={name!r} path={path!r}: {e}",
            )
            return None

    def trigger_refresh_by_id(
        self,
        name: str,
        item_id: str,
        *,
        recursive: bool = True,
        metadata_refresh_mode: str = "FullRefresh",
        image_refresh_mode: str = "FullRefresh",
        replace_all_metadata: bool = False,
        replace_all_images: bool = False,
    ) -> bool:
        """
        触发指定 ID 的刷新任务

        :param name: Emby Server Name
        :param item_id: ID
        :param recursive: 是否递归刷新子项
        :param metadata_refresh_mode: 元数据刷新模式（如 Default、FullRefresh）
        :param image_refresh_mode: 图片刷新模式（如 Default、FullRefresh）
        :param replace_all_metadata: 是否替换全部元数据
        :param replace_all_images: 是否替换全部图片

        :return: 是否触发成功
        """
        emby_host, _, emby_apikey = self.get_emby_info(name)
        if not emby_host:
            return False

        req_url = f"{emby_host}emby/Items/{item_id}/Refresh"
        params = {
            "Recursive": str(recursive).lower(),
            "MetadataRefreshMode": metadata_refresh_mode,
            "ImageRefreshMode": image_refresh_mode,
            "ReplaceAllMetadata": str(replace_all_metadata).lower(),
            "ReplaceAllImages": str(replace_all_images).lower(),
            "api_key": emby_apikey,
        }
        try:
            with RequestUtils().post_res(url=req_url, params=params) as res:
                if res and res.status_code in {200, 204}:
                    return True
                else:
                    logger.warning(
                        f"{self.func_name}触发刷新任务失败，Emby 未返回有效响应 code={res.status_code!r} name={name!r} item_id={item_id!r}"
                    )
                    return False
        except Exception as e:
            logger.error(
                f"{self.func_name}触发刷新任务异常 name={name!r} item_id={item_id!r}: {e}",
            )
            return False

    def trigger_refresh_by_path(
        self,
        name: str,
        path: str,
        *,
        recursive: bool = True,
        metadata_refresh_mode: str = "FullRefresh",
        image_refresh_mode: str = "FullRefresh",
        replace_all_metadata: bool = False,
        replace_all_images: bool = False,
    ) -> bool:
        """
        依据路径触发刷新任务

        :param name: Emby Server Name
        :param path: 项目路径
        :param recursive: 是否递归刷新子项
        :param metadata_refresh_mode: 元数据刷新模式（如 Default、FullRefresh）
        :param image_refresh_mode: 图片刷新模式（如 Default、FullRefresh）
        :param replace_all_metadata: 是否替换全部元数据
        :param replace_all_images: 是否替换全部图片

        :return: 是否触发成功
        """
        path_obj = Path(path)
        for parent in path_obj.parents:
            if len(parent.parts) <= 1:
                break
            item_id = self.get_item_id_by_path(name, parent.as_posix())
            if not item_id:
                continue
            return self.trigger_refresh_by_id(
                name,
                item_id,
                recursive=recursive,
                metadata_refresh_mode=metadata_refresh_mode,
                image_refresh_mode=image_refresh_mode,
                replace_all_metadata=replace_all_metadata,
                replace_all_images=replace_all_images,
            )
        return False


class EmbyMediaInfoOperate:
    """
    Emby 媒体信息操作类
    """

    def __init__(
        self,
        func_name: str,
        mediaservers: Optional[List[str]] = None,
        mp_mediaserver: Optional[str] = None,
    ):
        self.func_name = func_name
        self.media_servers = mediaservers
        self.mp_mediaserver = mp_mediaserver
        self.center = P115Center(
            license=configer.p115center_license,
            file_path=str(Path(__file__).resolve().parent.parent.parent / "api.py"),
        )
        self.emby_operate = EmbyOperate(func_name)

    @property
    def service_infos(self) -> Optional[Dict[str, ServiceInfo]]:
        """
        媒体服务器服务信息

        :return: 媒体服务器服务信息
        """
        if not self.media_servers:
            logger.warning(f"{self.func_name}尚未配置媒体服务器，请检查配置")
            return None

        mediaserver_helper = MediaServerHelper()

        services = mediaserver_helper.get_services(name_filters=self.media_servers)
        if not services:
            logger.warning(f"{self.func_name}获取媒体服务器实例失败，请检查配置")
            return None

        active_services = {}
        for service_name, service_info in services.items():
            if service_info.instance.is_inactive():
                logger.warning(
                    f"{self.func_name}媒体服务器 {service_name} 未连接，请检查配置"
                )
            else:
                if service_info.type == "emby":
                    active_services[service_name] = service_info

        if not active_services:
            logger.warning(f"{self.func_name}没有已连接的 Emby 媒体服务器，请检查配置")
            return None

        return active_services

    def _sync_media_info(
        self,
        host: str,
        api_key: str,
        media_data: Optional[Dict],
        service_name: str,
        need_upload: bool,
        file_path: Optional[str] = None,
        item_id: Optional[str] = None,
    ) -> Tuple[bool, bool, Optional[Dict]]:
        if file_path:
            path_encoded = quote(file_path, safe="")
            url = (
                f"{host}emby/Items/SyncMediaInfo?Path={path_encoded}&api_key={api_key}"
            )
        elif item_id:
            url = f"{host}emby/Items/SyncMediaInfo?Id={item_id}&api_key={api_key}"
        else:
            return False, need_upload, media_data
        try:
            res = httpx_post(
                url,
                json=media_data,
                headers={"Content-Type": "application/json"},
                timeout=60.0,
            )
            try:
                res_data = res.json()
            except Exception:
                res_data = []
            if res.status_code == 200 and res_data:
                logger.info(
                    f"{self.func_name}{service_name} 更新媒体信息成功: {file_path if file_path else item_id}"
                )
                if need_upload:
                    media_data = res_data
                elif media_data != res_data:
                    logger.warning(
                        f"{self.func_name}{service_name} 媒体信息不一致，重新上传服务器: {file_path if file_path else item_id}"
                    )
                    need_upload = True
                    media_data = res_data
                return True, need_upload, media_data
            else:
                logger.warning(
                    f"{self.func_name}{service_name} 更新媒体信息失败: [{res.status_code}] {res_data}"
                )
        except RequestError as e:
            logger.error(f"{self.func_name}{service_name} 更新媒体信息失败: {e}")
        return False, need_upload, media_data

    def get_mediainfo(self, sha1: str, path: Path, size: Optional[int] = None):
        """
        执行提取媒体信息，并上传服务器

        :param sha1: 媒体文件的 sha1 值
        :param path: 媒体路径
        :param size: 可选，当前文件大小（字节）
        """
        media_server = self.service_infos
        if not media_server:
            return

        media_data = None
        try:
            resp = self.center.download_emby_mediainfo_data([(sha1, size)])
            media_data = resp.get(sha1.upper(), None)
        except Exception as e:
            logger.error(f"{self.func_name}{path} 获取媒体信息失败: {e}")

        need_upload = True
        if media_data:
            need_upload = False

        file_path = path.as_posix()
        if self.mp_mediaserver:
            status, mediaserver_path, moviepilot_path = PathUtils.get_media_path(
                self.mp_mediaserver,
                path.as_posix(),
            )
            if not status:
                logger.error(
                    f"{self.func_name}{path} 无法确定媒体库路径，无法媒体信息提取"
                )
                return
            logger.info(f"{self.func_name}{path.name} 提取媒体信息目录替换中...")
            file_path = path.as_posix().replace(moviepilot_path, mediaserver_path)
            logger.info(
                f"{self.func_name}提取媒体信息目录替换: {moviepilot_path} --> {mediaserver_path}"
            )
            logger.info(f"{self.func_name}提取媒体信息目录: {file_path}")

        for service_name, service_info in media_server.items():
            host = service_info.config.config.get("host")
            api_key = service_info.config.config.get("apikey")
            if not host:
                continue
            if not host.endswith("/"):
                host += "/"
            if not host.startswith("http"):
                host = "http://" + host  # noqa
            status, need_upload, media_data = self._sync_media_info(
                host=host,
                api_key=api_key,
                media_data=media_data,
                service_name=service_name,
                need_upload=need_upload,
                file_path=file_path,
            )
            if not status:
                logger.info(
                    f"{self.func_name}尝试获取媒体 Id 提取媒体信息: {file_path}"
                )
                item_id = self.emby_operate.get_item_id_by_path(service_name, file_path)
                if not item_id:
                    sleep(10)
                    if self.emby_operate.trigger_refresh_by_path(
                        service_name, file_path
                    ):
                        for _ in range(3):
                            sleep(10)
                            item_id = self.emby_operate.get_item_id_by_path(
                                service_name, file_path
                            )
                            if item_id:
                                break
                if not item_id:
                    logger.error(
                        f"{self.func_name}无法获取媒体 Id 提取媒体信息: {file_path}"
                    )
                else:
                    status, need_upload, media_data = self._sync_media_info(
                        host=host,
                        api_key=api_key,
                        media_data=media_data,
                        service_name=service_name,
                        need_upload=need_upload,
                        item_id=item_id,
                    )
                    if not status:
                        logger.error(
                            f"{self.func_name}使用媒体 Id 提取媒体信息失败: [{item_id}] {file_path}"
                        )
        if need_upload and media_data:
            try:
                if self.center.upload_emby_mediainfo_data(sha1, media_data, size=size):
                    logger.info(
                        f"{self.func_name}上传媒体信息成功: [{sha1}]{file_path}"
                    )
                else:
                    logger.error(
                        f"{self.func_name}Emby 返回媒体信息异常，不进行上传: [{sha1}]{file_path}"
                    )
            except Exception as e:
                logger.warning(
                    f"{self.func_name}上传媒体信息失败: {sha1} {file_path} {e}"
                )


class EmbyMediainfoQueue:
    """
    Emby 媒体信息提取全局队列
    """

    _SENTINEL = object()

    def __init__(self) -> None:
        self._queue: Optional[Queue] = None
        self._worker_thread: Optional[Thread] = None

    def _worker(self) -> None:
        """
        队列 worker
        """
        if self._queue is None:
            return
        while True:
            try:
                task = self._queue.get()
            except Exception as e:
                logger.error(
                    f"【Emby 媒体信息队列】worker 取任务异常: {e}", exc_info=True
                )
                continue
            if task is self._SENTINEL:
                if self._queue is not None:
                    self._queue.task_done()
                break
            try:
                path = task.path if isinstance(task.path, Path) else Path(task.path)
                helper = EmbyMediaInfoOperate(
                    func_name=task.func_name,
                    mp_mediaserver=task.mp_mediaserver,
                    mediaservers=task.mediaservers,
                )
                helper.get_mediainfo(task.sha1, path, size=task.size)
            except Exception as e:
                logger.error(
                    f"{task.func_name} Emby 媒体信息提取失败: {e}",
                    exc_info=True,
                )
            finally:
                if self._queue is not None:
                    self._queue.task_done()

    def start(self) -> None:
        """
        启动 Emby 媒体信息提取队列 worker 线程
        """
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return
        self._queue = Queue(maxsize=4096)
        self._worker_thread = Thread(
            target=self._worker,
            name="P115StrmHelper-EmbyMediainfoQueue",
            daemon=False,
        )
        self._worker_thread.start()
        logger.debug("【Emby 媒体信息队列】worker 已启动")

    def stop(self) -> None:
        """
        停止 Emby 媒体信息提取队列 worker 线程
        """
        if (
            self._queue is None
            or self._worker_thread is None
            or not self._worker_thread.is_alive()
        ):
            return
        try:
            self._queue.put(self._SENTINEL)
            self._worker_thread.join(timeout=30)
            if self._worker_thread.is_alive():
                logger.warning("【Emby 媒体信息队列】worker 未在 30 秒内退出")
        except Exception as e:
            logger.error(f"【Emby 媒体信息队列】停止 worker 异常: {e}", exc_info=True)
        finally:
            self._worker_thread = None
            self._queue = None

    def enqueue(
        self,
        func_name: str,
        sha1: str,
        path: Union[str, Path],
        mp_mediaserver: Optional[str] = None,
        mediaservers: Optional[List[str]] = None,
        size: Optional[int] = None,
    ) -> None:
        """
        将一条 Emby 媒体信息提取任务加入全局队列

        :param func_name: 调用方标识，用于日志
        :param sha1: 媒体文件 sha1
        :param path: 媒体路径
        :param mp_mediaserver: MoviePilot 媒体服务器路径配置，可选
        :param mediaservers: 媒体服务器名称列表，可选
        :param size: 文件大小（字节），可选
        """
        if self._queue is None:
            logger.warning(
                "【Emby 媒体信息队列】队列未初始化，请先启动 worker，跳过入队"
            )
            return
        try:
            self._queue.put(
                EmbyMediainfoTask(
                    func_name=func_name,
                    mp_mediaserver=mp_mediaserver,
                    mediaservers=mediaservers,
                    sha1=sha1,
                    path=path,
                    size=size,
                )
            )
        except Exception as e:
            logger.error(f"【Emby 媒体信息队列】入队失败: {e}", exc_info=True)


emby_mediainfo_queue = EmbyMediainfoQueue()
