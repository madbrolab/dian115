"""
分享 STRM 生成模块

本模块提供基于分享链接的 STRM 文件生成功能，存在数据服务器共享机制。

数据收集与共享机制
------------------
本模块在运行分享同步功能时，会自动启用数据服务器共享机制。此机制的设计目的和运作方式如下：

1. 数据收集范围
   - 仅收集分享链接中的文件基本信息（文件名、路径、大小、ID 等）
   - 不收集任何个人隐私信息、文件内容或访问凭证
   - 数据以匿名化、加密压缩的方式存储和传输

2. 数据收集的合理性
   - 降低风控风险：通过共享已知安全的分享数据，帮助规避平台风控机制
   - 提升生成效率：复用已处理的数据，减少重复的 API 调用和网络请求
   - 优化用户体验：加快 STRM 文件生成速度，减少等待时间
   - 数据最小化原则：仅收集生成 STRM 文件所必需的最少数据

3. 数据使用方式
   - 数据仅用于 STRM 文件生成流程
   - 数据存储在加密的服务器环境中
   - 数据可通过分享码和提取码进行访问，确保数据关联性

用户同意原则
-----------
使用本模块的分享同步功能即表示您同意以下条款：

1. 默认同意原则
   - 启用分享同步功能即视为您已阅读、理解并同意本数据收集与共享机制
   - 您可以通过禁用分享同步功能来停止数据收集和共享

2. 数据控制权
   - 您拥有对分享数据的完全控制权
   - 您可以随时停止使用本功能，已上传的数据将根据服务器策略进行处理

3. 隐私保护承诺
   - 我们承诺仅收集生成 STRM 文件所必需的数据
   - 不会收集、存储或传输任何个人敏感信息
   - 数据以加密方式传输和存储

4. 免责声明
   - 数据共享为可选功能，但分享同步功能的完整体验需要此功能支持
   - 如您不同意数据共享机制，请勿使用分享同步功能

注意事项
--------
- 本功能需要网络连接以访问数据服务器
- 首次运行时会尝试从服务器获取数据，如不存在则自动收集并上传
- 数据上传仅在成功处理所有文件且无异常时执行
"""

__all__ = ["ShareStrmHelper"]


from concurrent.futures import ThreadPoolExecutor, as_completed
from gzip import open as gzip_open
from itertools import batched
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import List, Dict, Set, Deque, Tuple, Optional, Iterable
from os import remove as os_remove
from os.path import exists as path_exists, getsize as path_getsize, join as path_join
from tempfile import gettempdir

from httpx import HTTPStatusError
from orjson import dumps, loads
from p115center import P115Center

from p115client.util import share_extract_payload

from app.chain.transfer import TransferChain
from app.log import logger
from app.schemas import FileItem

from ...core.config import configer
from ...core.p115 import ShareP115Client, iter_share_files_with_path
from ...core.scrape import media_scrape_metadata
from ...helper.mediainfo_download import MediaInfoDownloader
from ...helper.mediaserver import MediaServerRefresh
from ...schemas.share import ShareStrmConfig
from ...schemas.size import CompareMinSize
from ...utils.path import PathUtils
from ...utils.sentry import sentry_manager
from ...utils.strm import StrmUrlGetter, StrmGenerater


class ShareFilesDataCollector:
    """
    分享文件数据收集器
    """

    def __init__(self, data_iter: Iterable[Dict], temp_file: str):
        """
        :param data_iter: 文件数据迭代器
        :param temp_file: 临时文件路径
        """
        self.data_iter = data_iter
        self.temp_file = temp_file
        self.count = 0
        self._file_handle = None
        self._write_buffer = bytearray()
        self._buffer_size = 64 * 1024

    def __iter__(self):
        """
        迭代器接口，在迭代时同时写入数据
        """
        self._file_handle = gzip_open(self.temp_file, "wb")
        try:
            for record in self.data_iter:
                line_data = dumps(record) + b"\n"
                self._write_buffer.extend(line_data)

                if len(self._write_buffer) >= self._buffer_size:
                    self._file_handle.write(self._write_buffer)
                    self._write_buffer.clear()

                self.count += 1
                if self.count % 1000 == 0:
                    logger.debug(
                        f"【分享STRM生成】数据上传已收集 {self.count} 条数据..."
                    )
                yield record

            if self._write_buffer:
                self._file_handle.write(self._write_buffer)
                self._write_buffer.clear()
        finally:
            if self._file_handle:
                self._file_handle.close()
                self._file_handle = None

    def get_file_info(self) -> Tuple[str, int]:
        """
        获取临时文件信息

        :return: (文件路径, 数据条数)
        """
        return self.temp_file, self.count


class ShareOOPServerHelper:
    """
    分享 OOF 服务助手
    """

    @staticmethod
    def download_share_files_data(
        share_code: str, receive_code: str, temp_file: str
    ) -> bool:
        """
        从服务器下载分享文件数据

        :param share_code: 分享码
        :param receive_code: 提取码
        :param temp_file: 临时文件保存路径

        :return: 下载成功返回 True，失败返回 False
        """
        batch_id = f"{share_code}{receive_code}"
        logger.info(f"【分享STRM生成】尝试下载数据，batch_id: {batch_id}")

        try:
            client = P115Center()
            client.download_share_file_iter(batch_id, temp_file)
            logger.info(
                f"【分享STRM生成】数据下载成功，batch_id: {batch_id}, 文件大小: {path_getsize(temp_file) / 1024 / 1024:.2f} MB"
            )
            return True
        except HTTPStatusError as e:
            code = e.response.status_code if e.response else 500
            if code == 404:
                logger.debug(f"【分享STRM生成】数据不存在，batch_id: {batch_id}")
            else:
                logger.debug(
                    f"【分享STRM生成】下载数据失败，batch_id: {batch_id}, 状态码: {code}"
                )
            return False
        except Exception as e:
            logger.debug(f"【分享STRM生成】下载数据失败，batch_id: {batch_id}: {e}")
            return False

    @staticmethod
    def read_share_files_data_from_file(temp_file: str) -> Iterable[Dict]:
        """
        从下载的 gzip 文件中读取数据并返回迭代器

        :param temp_file: 临时文件路径

        :return: 数据迭代器
        """
        with gzip_open(temp_file, "rb") as f:
            for line in f:
                if line.strip():
                    try:
                        yield loads(line)
                    except Exception as e:
                        logger.warn(f"【分享STRM生成】解析数据行失败: {e}")
                        continue

    @staticmethod
    def upload_file(
        share_code: str,
        receive_code: str,
        temp_file: str,
    ) -> Optional[Dict]:
        """
        上传文件到服务器

        :param share_code: 分享码
        :param receive_code: 提取码
        :param temp_file: 临时文件路径

        :return: 上传结果响应数据，失败返回 None
        """
        batch_id = f"{share_code}{receive_code}"
        logger.info(f"【分享STRM生成】开始上传，batch_id: {batch_id}")

        try:
            client = P115Center(
                license=configer.p115center_license,
                file_path=str(Path(__file__).resolve().parent.parent.parent / "api.py"),
            )
            resp = client.upload_share_file_iter(batch_id, temp_file)
            logger.debug(f"【分享STRM生成】上传成功: {resp.model_dump()}")
        except Exception as e:
            logger.warn(f"【分享STRM生成】上传异常: {e}")
            return None
        finally:
            if path_exists(temp_file):
                try:
                    os_remove(temp_file)
                    logger.debug(f"【分享STRM生成】已清理临时文件: {temp_file}")
                except (OSError, TypeError, ValueError):
                    pass

    @staticmethod
    def upload_share_files_data(
        share_code: str, receive_code: str, temp_file: str
    ) -> Optional[Dict]:
        """
        上传分享文件数据到服务器

        :param share_code: 分享码
        :param receive_code: 提取码
        :param temp_file: 临时文件路径

        :return: 上传结果响应数据，失败返回 None
        """
        if not path_exists(temp_file) or path_getsize(temp_file) == 0:
            logger.warn("【分享STRM生成】临时文件不存在或为空，跳过上传")
            return None

        return ShareOOPServerHelper.upload_file(
            share_code=share_code,
            receive_code=receive_code,
            temp_file=temp_file,
        )


class ShareStrmHelper:
    """
    根据分享生成STRM
    """

    def __init__(self, mediainfodownloader: MediaInfoDownloader):
        self.rmt_mediaext: Set[str] = {
            f".{ext.strip()}"
            for ext in configer.user_rmt_mediaext.replace("，", ",").split(",")
        }
        self.download_mediaext: Set[str] = {
            f".{ext.strip()}"
            for ext in configer.user_download_mediaext.replace("，", ",").split(",")
        }

        self.share_client = ShareP115Client(configer.cookies)
        self.mediainfodownloader = mediainfodownloader

        self.elapsed_time = 0

        self.total_count = 0
        self.strm_count = 0
        self.mediainfo_count = 0

        self.strm_fail_count = 0
        self.strm_fail_dict: Dict[str, str] = {}
        self.mediainfo_fail_count = 0
        self.mediainfo_fail_dict: List = []

        self.download_mediainfo_list = []

        self.scrape_refresh_queue = Deque()
        self.mp_transfer_queue = Deque()

        self.lock = Lock()

        self.strmurlgetter = StrmUrlGetter()

    @staticmethod
    def get_share_code(config: ShareStrmConfig) -> ShareStrmConfig:
        """
        解析分享配置，获取分享码和提取码
        """
        if config.share_link:
            data = share_extract_payload(config.share_link)
            share_code = data["share_code"]
            receive_code = data["receive_code"]
            logger.info(
                f"【分享STRM生成】解析分享链接 share_code={share_code} receive_code={receive_code}"
            )
        else:
            if not config.share_code or not config.share_receive:
                return config
            share_code = config.share_code
            receive_code = config.share_receive
        config.share_code = share_code
        config.share_receive = receive_code
        return config

    def scrape_refresh_media(self, config: ShareStrmConfig) -> None:
        """
        刮削媒体 & 刷新媒体服务器

        :param config: 分享 STRM 生成配置
        """
        media_server_refresh = MediaServerRefresh(
            func_name="【分享STRM生成】",
            enabled=config.media_server_refresh,
            mp_mediaserver=configer.share_strm_mp_mediaserver_paths,
            mediaservers=configer.share_strm_mediaservers,
        )

        def _refresh_media_server(file_path: Path) -> None:
            media_server_refresh.refresh_mediaserver(
                file_path=file_path.as_posix(), file_name=file_path.name
            )

        def _scrape_media_data(file_path: Path) -> None:
            logger.info(f"【分享STRM生成】{file_path.as_posix()} 开始刮削...")
            media_scrape_metadata(file_path.as_posix())

        def _scrape_and_refresh(file_path: Path) -> None:
            logger.info(f"【分享STRM生成】{file_path.as_posix()} 开始刮削...")
            _scrape_media_data(file_path)
            _refresh_media_server(file_path)

        if config.scrape_metadata and config.media_server_refresh:
            func = _scrape_and_refresh
        elif config.scrape_metadata:
            func = _scrape_media_data
        elif config.media_server_refresh:
            func = _refresh_media_server
        else:
            return

        while len(self.scrape_refresh_queue) != 0:
            path = self.scrape_refresh_queue.popleft()
            func(Path(path))

    def mp_transfer(self) -> None:
        """
        交由 MoviePilot 整理文件
        """
        transfer_chain = TransferChain()
        while len(self.mp_transfer_queue) != 0:
            path = Path(self.mp_transfer_queue.popleft())
            transfer_chain.do_transfer(
                fileitem=FileItem(
                    storage="local",
                    type="file",
                    path=path.as_posix(),
                    name=path.name,
                    basename=path.stem,
                    extension=path.suffix[1:].lower(),
                    size=path.stat().st_size,
                    modify_time=path.stat().st_mtime,
                )
            )

    def __process_single_item(
        self,
        item: Dict,
        config: ShareStrmConfig,
    ) -> None:
        """
        处理单个 STRM 文件

        :param item: 网盘文件信息
        :param config: 分享 STRM 生成配置
        """
        file_path = item["path"]

        if not PathUtils.has_prefix(file_path, config.share_path):
            logger.debug(
                "【分享STRM生成】此文件不在用户设置分享目录下，跳过分享路径: %s",
                str(file_path).replace(config.local_path, "", 1),
            )
            return

        share_path_obj = Path(config.share_path)
        local_path_obj = Path(config.local_path)
        item_path_obj = Path(file_path)

        file_path = local_path_obj / item_path_obj.relative_to(share_path_obj)
        file_target_dir = file_path.parent
        original_file_name = file_path.name
        file_name = StrmGenerater.get_strm_filename(file_path)
        new_file_path = file_target_dir / file_name

        try:
            if config.auto_download_mediainfo:
                if file_path.suffix.lower() in self.download_mediaext:
                    with self.lock:
                        self.download_mediainfo_list.append(
                            {
                                "type": "share",
                                "share_code": config.share_code,
                                "receive_code": config.share_receive,
                                "file_id": item["id"],
                                "path": file_path,
                                "thumb": item.get("thumb", None),
                                "sha1": item["sha1"],
                            }
                        )
                    return

            if file_path.suffix.lower() not in self.rmt_mediaext:
                logger.warn(
                    "【分享STRM生成】文件后缀不匹配，跳过分享路径: %s",
                    str(file_path).replace(config.local_path, "", 1),
                )
                return

            if not (
                result := StrmGenerater.should_generate_strm(
                    original_file_name,
                    mode="share",
                    filesize=CompareMinSize(
                        min_size=config.min_file_size, file_size=item["size"]
                    ),
                )
            )[1]:
                logger.warn(
                    f"【分享STRM生成】{result[0]}，跳过分享路径: {str(file_path).replace(config.local_path, '', 1)}"
                )
                return

            if not item["id"]:
                logger.error(
                    f"【分享STRM生成】{original_file_name} 不存在 id 值，无法生成 STRM 文件"
                )
                self.strm_fail_dict[str(new_file_path)] = "不存在 id 值"
                self.strm_fail_count += 1
                return

            new_file_path.parent.mkdir(parents=True, exist_ok=True)

            strm_url = self.strmurlgetter.get_share_strm_url(
                config.share_code,
                config.share_receive,
                item["id"],
                item["name"],
                item["path"],
            )

            new_file_path.write_text(strm_url, encoding="utf-8")
            self.strm_count += 1
            logger.info("【分享STRM生成】生成 STRM 文件成功: %s", str(new_file_path))

            if config.moviepilot_transfer:
                self.mp_transfer_queue.append(new_file_path)

            if config.media_server_refresh or config.scrape_metadata:
                self.scrape_refresh_queue.append(new_file_path)
        except Exception as e:
            sentry_manager.sentry_hub.capture_exception(e)
            logger.error(
                "【分享STRM生成】生成 STRM 文件失败: %s  %s",
                str(new_file_path),
                e,
            )
            self.strm_fail_count += 1
            self.strm_fail_dict[str(new_file_path)] = str(e)
            return

    def generate_strm_files(self) -> None:
        """
        获取分享文件，生成 STRM
        """
        if not configer.share_strm_config:
            return

        for config in configer.share_strm_config:
            comment_info = f" ({config.comment})" if config.comment else ""

            if not config.enabled:
                logger.info(f"【分享STRM生成】跳过未启用的配置{comment_info}: {config}")
                continue

            config = ShareStrmHelper.get_share_code(config)

            if not config.share_code or not config.share_receive:
                logger.error(
                    f"【分享STRM生成】缺失分享码或提取码{comment_info}: {config}"
                )
                continue

            logger.info(
                f"【分享STRM生成】开始处理分享配置{comment_info}: share_code={config.share_code}, share_path={config.share_path}, local_path={config.local_path}"
            )
            start_time = perf_counter()

            # 迭代器选择
            data_collector = None
            batch_id = f"{config.share_code}{config.share_receive}"
            temp_file = path_join(gettempdir(), f"share_data_{batch_id}.json.gz")
            download_success = ShareOOPServerHelper.download_share_files_data(
                share_code=config.share_code,
                receive_code=config.share_receive,
                temp_file=temp_file,
            )
            if download_success:
                logger.info(f"【分享STRM生成】使用下载的数据生成 STRM{comment_info}")
                data_iter = ShareOOPServerHelper.read_share_files_data_from_file(
                    temp_file
                )
            else:
                logger.info(f"【分享STRM生成】数据不存在，开始收集数据{comment_info}")
                data_iter = iter_share_files_with_path(
                    client=self.share_client,
                    share_code=config.share_code,
                    receive_code=config.share_receive,
                    cid=0,
                    speed_mode=config.speed_mode,
                    **configer.get_ios_ua_app(),
                )
                data_collector = ShareFilesDataCollector(data_iter, temp_file)
                data_iter = data_collector

            has_exception = False
            try:
                with ThreadPoolExecutor(max_workers=128) as executor:
                    for batch in batched(data_iter, 1_000):
                        self.total_count += len(batch)
                        future_to_item = {
                            executor.submit(
                                self.__process_single_item,
                                item=item,
                                config=config,
                            ): item
                            for item in batch
                        }

                        for future in as_completed(future_to_item):
                            item = future_to_item[future]
                            try:
                                future.result()
                            except Exception as e:
                                has_exception = True
                                sentry_manager.sentry_hub.capture_exception(e)
                                logger.error(
                                    f"【分享STRM生成】并发处理出错: {item} - {str(e)}"
                                )
            except Exception as e:
                has_exception = True
                sentry_manager.sentry_hub.capture_exception(e)
                logger.error(f"【分享STRM生成】处理分享文件时出错{comment_info}: {e}")

            end_time = perf_counter()
            self.elapsed_time += end_time - start_time

            # 数据上传服务器
            def cleanup_temp_file(file_path: str) -> None:
                if path_exists(file_path):
                    try:
                        os_remove(file_path)
                        logger.debug(f"【分享STRM生成】已清理临时文件: {file_path}")
                    except (OSError, TypeError, ValueError):
                        pass

            if has_exception:
                logger.warn(
                    f"【分享STRM生成】处理过程中出现异常，跳过数据上传{comment_info}: share_code={config.share_code}"
                )
                cleanup_temp_file(temp_file)
            elif download_success:
                file_size_mb = path_getsize(temp_file) / 1024 / 1024
                logger.info(
                    f"【分享STRM生成】使用下载数据完成，文件大小: {file_size_mb:.2f} MB{comment_info}"
                )
                cleanup_temp_file(temp_file)
            else:
                file_path, data_count = data_collector.get_file_info()
                if data_count > 0:
                    file_size_mb = path_getsize(file_path) / 1024 / 1024
                    logger.info(
                        f"【分享STRM生成】共收集 {data_count} 条数据，文件大小: {file_size_mb:.2f} MB"
                    )
                    upload_result = ShareOOPServerHelper.upload_share_files_data(
                        share_code=config.share_code,
                        receive_code=config.share_receive,
                        temp_file=file_path,
                    )
                    if upload_result:
                        logger.info(
                            f"【分享STRM生成】数据上传成功{comment_info}: share_code={config.share_code}"
                        )
                    else:
                        logger.warn(
                            f"【分享STRM生成】数据上传失败{comment_info}: share_code={config.share_code}"
                        )
                else:
                    logger.debug(
                        f"【分享STRM生成】未收集到数据，跳过上传{comment_info}: share_code={config.share_code}"
                    )
                    cleanup_temp_file(file_path)

            self.scrape_refresh_media(config)

            if config.moviepilot_transfer:
                self.mp_transfer()

        self.mediainfo_count, self.mediainfo_fail_count, self.mediainfo_fail_dict = (
            self.mediainfodownloader.batch_auto_share_downloader(
                downloads_list=self.download_mediainfo_list
            )
        )

    def get_generate_total(self) -> Tuple[int, int, int, int]:
        """
        输出总共生成文件个数
        """
        if self.strm_fail_dict:
            for path, error in self.strm_fail_dict.items():
                logger.warn(f"【分享STRM生成】{path} 生成错误原因: {error}")

        if self.mediainfo_fail_dict:
            for path in self.mediainfo_fail_dict:
                logger.warn(f"【分享STRM生成】{path} 下载错误")

        logger.info(
            f"【分享STRM生成】分享生成 STRM 文件完成，总共生成 {self.strm_count} 个 STRM 文件，下载 {self.mediainfo_count} 个媒体数据文件"
        )

        if self.strm_fail_count != 0 or self.mediainfo_fail_count != 0:
            logger.warn(
                f"【分享STRM生成】{self.strm_fail_count} 个 STRM 文件生成失败，{self.mediainfo_fail_count} 个媒体数据文件下载失败"
            )

        logger.debug(
            f"【全量STRM生成】时间 {self.elapsed_time:.6f} 秒，总迭代文件数量 {self.total_count}"
        )

        return (
            self.strm_count,
            self.mediainfo_count,
            self.strm_fail_count,
            self.mediainfo_fail_count,
        )
