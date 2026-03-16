from pathlib import Path
from typing import Optional, Dict, List

from app.chain.media import MediaChain
from app.core.metainfo import MetaInfoPath
from app.helper.mediaserver import MediaServerHelper as MpMediaServerHelper
from app.log import logger
from app.schemas import ServiceInfo, RefreshMediaItem, MediaInfo

from ...utils.path import PathUtils


class MediaServerRefresh:
    """
    媒体服务器操作
    """

    def __init__(
        self,
        func_name: str,
        enabled: bool = False,
        mediaservers: Optional[List[str]] = None,
        mp_mediaserver: Optional[str] = None,
    ):
        self.func_name = func_name
        self.media_servers = mediaservers
        self.mp_mediaserver = mp_mediaserver
        self.enabled = enabled

    @property
    def service_infos(self) -> Optional[Dict[str, ServiceInfo]]:
        """
        媒体服务器服务信息

        :return: 媒体服务器服务信息
        """
        if not self.media_servers:
            logger.warning(f"{self.func_name}尚未配置媒体服务器，请检查配置")
            return None

        mediaserver_helper = MpMediaServerHelper()

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
                active_services[service_name] = service_info

        if not active_services:
            logger.warning(f"{self.func_name}没有已连接的媒体服务器，请检查配置")
            return None

        return active_services

    def refresh_mediaserver(
        self,
        file_path: Optional[str] = None,
        file_name: Optional[str] = None,
        mediainfo: Optional[MediaInfo] = None,
        refresh_all: bool = False,
    ) -> bool:
        """
        刷新媒体服务器

        :param file_path: 文件路径
        :param file_name: 文件名
        :param mediainfo: 媒体信息
        :param refresh_all: 是否刷新所有媒体服务器

        :return: 是否刷新成功
        """
        if not self.enabled:
            return True
        if not self.service_infos:
            return False
        logger.info(f"{self.func_name}{file_name} 开始刷新媒体服务器")
        if refresh_all:
            for name, service in self.service_infos.items():
                if hasattr(service.instance, "refresh_root_library"):
                    service.instance.refresh_root_library()
                else:
                    logger.warning(f"{self.func_name}{name} 不支持刷新")
            return True
        if self.mp_mediaserver:
            status, mediaserver_path, moviepilot_path = PathUtils.get_media_path(
                self.mp_mediaserver,
                file_path,
            )
            if status:
                logger.info(f"{self.func_name}{file_name} 刷新媒体服务器目录替换中...")
                file_path = file_path.replace(
                    moviepilot_path, mediaserver_path
                ).replace("\\", "/")
                logger.info(
                    f"{self.func_name}刷新媒体服务器目录替换: {moviepilot_path} --> {mediaserver_path}"
                )
                logger.info(f"{self.func_name}刷新媒体服务器目录: {file_path}")
        if not mediainfo:
            media_chain = MediaChain()
            meta = MetaInfoPath(path=Path(file_path))
            mediainfo = media_chain.recognize_media(meta=meta)
            if not mediainfo:
                logger.warning(f"{self.func_name}{file_name} 无法刷新媒体库")
                return False
        items = [
            RefreshMediaItem(
                title=mediainfo.title,
                year=mediainfo.year,
                type=mediainfo.type,
                category=mediainfo.category,
                target_path=Path(file_path),
            )
        ]
        for name, service in self.service_infos.items():
            if hasattr(service.instance, "refresh_library_by_items"):
                service.instance.refresh_library_by_items(items)
            else:
                logger.warning(f"{self.func_name}{file_name} {name} 不支持刷新")
        return True
