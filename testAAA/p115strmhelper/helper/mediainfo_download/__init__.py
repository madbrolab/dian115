from asyncio import Semaphore, gather, run as asyncio_run, sleep as asyncio_sleep
from base64 import b64decode
from itertools import batched
from pathlib import Path
from time import sleep as time_sleep
from typing import Dict, Generator, List, Optional, Set, Tuple
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from aiofiles import open as aio_open
from aiofiles.os import stat as aio_stat
from httpx import (
    AsyncClient,
    HTTPStatusError,
    LocalProtocolError,
    RequestError,
    stream as httpx_stream,
)
from orjson import loads
from p115center import P115Center
from p115pickcode import pickcode_to_id
from p115client import P115Client, check_response
from p115client.const import TYPE_TO_SUFFIXES
from p115client.util import reduce_image_url_layers
from p115client.tool.iterdir import (
    _iter_fs_files,
    iter_files,
    iter_files_with_path_skim,
)
from zstandard import ZstdCompressor, ZstdDecompressor

from app.log import logger

from ...core.config import configer
from ...core.cache import OofFastMiCache
from ...utils.url import Url
from ...utils.sentry import sentry_manager
from ...utils.exception import DownloadValidationFail


@sentry_manager.capture_all_class_exceptions
class MediaInfoDownloader:
    """
    媒体信息文件下载器
    """

    # 批处理文件数量
    batch_size = 200
    # 最大同时下载线程（cdn_url）
    max_workers = 4

    def __init__(self, cookie: str):
        self.cookie = cookie
        self.client = P115Client(cookie)

        self.oof_fast_mi_cacher = OofFastMiCache(
            configer.PLUGIN_TEMP_PATH / "oof_fast_mi"
        )
        self.p115_center = P115Center(
            license=configer.p115center_license,
            file_path=str(Path(__file__).resolve().parent.parent.parent / "api.py"),
        )
        self.zstd_compressor = ZstdCompressor()
        self.zstd_decompressor = ZstdDecompressor()

        base_headers = {
            "User-Agent": configer.get_user_agent(),
            "Cookie": self.cookie,
        }
        sanitized_headers = {}
        for key, value in base_headers.items():
            if value is None:
                continue
            if isinstance(value, bytes):
                final_value = value.decode("utf-8", errors="ignore")
            else:
                final_value = str(value)
            sanitized_headers[key] = final_value.strip()
        self.headers = sanitized_headers

        self.stop_all_flag = None

        self.mediainfo_count: int = 0
        self.mediainfo_fail_count: int = 0
        self.mediainfo_fail_dict: List = []

        logger.debug(f"【媒体信息文件下载】初始化请求头：{self.headers}")

    def __del__(self):
        self.oof_fast_mi_cacher.close()

    @staticmethod
    async def async_is_file_leq_1k(file_path: str | Path) -> bool:
        """
        判断文件是否小于等于 100B。

        如果文件不存在，返回 True。
        """
        try:
            stat_result = await aio_stat(file_path)
            return stat_result.st_size <= 100
        except FileNotFoundError:
            return True
        except Exception:
            return False

    def _oof_data_upload(self, upload_lst: List):
        """
        上传数据到服务器

        :param upload_lst: 上传列表
        """
        try:
            resp = self.p115_center.upload_mediainfo_data(upload_lst)
            logger.debug(
                f"【媒体信息文件下载】数据上传 OOF 服务器成功: {resp.model_dump()}"
            )
            self.oof_fast_mi_cacher.batch_set(upload_lst)
            logger.debug(f"【媒体信息文件下载】OOF 数据缓存本地成功: {len(upload_lst)}")
        except Exception as e:
            logger.warn(f"【媒体信息文件下载】获取 OOF 服务器数据失败: {e}")

    def get_download_url(self, pickcode: str) -> Optional[Url]:
        """
        获取下载链接
        """
        try:
            resp = self.client.download_url_app(
                pickcode, app="android", user_agent=configer.get_user_agent()
            )
            check_response(resp)
            data = resp["data"]
            data["file_name"] = unquote(urlsplit(data["url"]).path.rpartition("/")[-1])
        except Exception as e:
            logger.error(f"【媒体信息文件下载】{pickcode} 获取下载链接异常: {e}")
            return None
        return Url.of(data["url"], data)

    def save_oof_mediainfo_file(
        self, item_list: List | Tuple, json_data: Dict, key: str
    ) -> Generator:
        """
        将 OOF base64 数据解码后存入文件

        :param item_list: 待处理的列表
        :param json_data: 数据字典
        :param key: 数据类型（Cache ｜ Api）

        :return: 迭代器，返回未能处理的项目
        """
        for item in item_list:
            base64_data = json_data.get(item["sha1"])
            if base64_data:
                try:
                    file_path = Path(item["path"])
                    file_name = file_path.name
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    decompressed_data = self.zstd_decompressor.decompress(
                        b64decode(base64_data)
                    )
                    with open(file_path, "wb") as f:
                        f.write(decompressed_data)
                    logger.info(
                        f"【媒体信息文件下载】OOF {key} 保存 {file_name} 成功: {file_path}"
                    )
                    self.mediainfo_count += 1
                except Exception as e:
                    logger.error(
                        f"【媒体信息文件下载】处理 {item['path']} 时发生错误: {e}"
                    )
                    yield item
            else:
                yield item

    def save_mediainfo_file(
        self, file_path: Path, file_name: str, download_url: str
    ) -> bool:
        """
        保存媒体信息文件
        """
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with httpx_stream(
                "GET",
                download_url,
                timeout=30,
                headers=self.headers,
                follow_redirects=True,
            ) as response:
                response.raise_for_status()
                with open(file_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
        except Exception as e:
            logger.error(f"【媒体信息文件下载】保存 {file_name} 文件失败: {e}")
            return False
        logger.info(f"【媒体信息文件下载】保存 {file_name} 文件成功: {file_path}")
        return True

    async def async_save_mediainfo_file(
        self,
        client: AsyncClient,
        semaphore: Semaphore,
        file_path: Path,
        file_name: str,
        download_url: str,
        hide_cookies: bool = False,
        sha1: str | None = None,
    ) -> Optional[Tuple[str, Tuple[str, bytes, str]]]:
        """
        带验证和重试机制的异步下载

        :param client: HTTPX 客户端
        :param semaphore: 并发量
        :param file_path: 文件路径
        :param file_name：文件名称
        :param download_url: 下载地址
        :param hide_cookies: 是否使用 Cookie 下载，默认 False
        :param sha1: 文件 115 网盘 sha1，如果设置则会返回数据压缩信息
        """
        async with semaphore:
            max_retries = 3
            for attempt in range(max_retries):
                file_content_buffer = bytearray()
                try:
                    request_headers = self.headers.copy()
                    request_headers["Connection"] = "close"
                    if hide_cookies:
                        request_headers.pop("Cookie")

                    async with client.stream(
                        "GET", download_url, timeout=30, headers=request_headers
                    ) as response:
                        if response.status_code == 403:
                            self.stop_all_flag = True
                            response.raise_for_status()
                        response.raise_for_status()
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        async with aio_open(file_path, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                await f.write(chunk)
                                file_content_buffer.extend(chunk)

                    if await self.async_is_file_leq_1k(file_path):
                        raise DownloadValidationFail(
                            f"【媒体信息文件下载】文件 {file_name} 在下载后验证失败"
                        )

                    logger.info(
                        f"【媒体信息文件下载】保存 {file_name} 成功: {file_path}"
                    )
                    self.mediainfo_count += 1

                    if sha1:
                        return "files", (
                            sha1,
                            self.zstd_compressor.compress(file_content_buffer),
                            "application/octet-stream",
                        )
                    return None

                except DownloadValidationFail as e:
                    error_message = str(e)
                except LocalProtocolError as e:
                    error_message = f"协议错误 (LocalProtocolError): {e}"
                except HTTPStatusError as e:
                    if e.response.status_code == 403:
                        logger.error(
                            f"【下载失败】获取 {file_name} 时被拒绝 (403 Forbidden)，将不会重试。"
                        )
                        return None
                    error_message = f"HTTP错误 {e.response.status_code}"
                except RequestError as e:
                    error_message = f"网络请求错误 {type(e).__name__}"
                except Exception as e:
                    error_message = f"未知错误 {type(e).__name__}: {e}"

                logger.warning(
                    f"【媒体信息文件下载】保存 {file_name} 失败 (尝试 {attempt + 1}/{max_retries})，原因: {error_message}"
                )

                if attempt < max_retries - 1:
                    await asyncio_sleep(1)
                else:
                    self.mediainfo_fail_count += 1
                    self.mediainfo_fail_dict.append(file_path.as_posix())
                    logger.error(
                        f"【媒体信息文件下载】保存 {file_name} 在 {max_retries} 次尝试后最终失败"
                    )

    async def __async_download_batch_subtitle_image(
        self,
        data_map: Dict[str | int, str],
        item_list,
        value: str = "sha1",
        oof_upload: bool = False,
    ) -> Optional[List]:
        """
        为单个批次创建并并发执行所有下载任务
        """
        semaphore = Semaphore(256)
        async with AsyncClient(follow_redirects=True) as client:
            tasks = []
            for item in item_list:
                url = data_map.get(item[value])
                if url:
                    path = Path(item["path"])
                    task = self.async_save_mediainfo_file(
                        client,
                        semaphore,
                        path,
                        path.name,
                        url,
                        hide_cookies=bool(value == "sha1"),
                        sha1=item["sha1"] if oof_upload else None,
                    )
                    tasks.append(task)
            if tasks:
                result = await gather(*tasks)
                if oof_upload:
                    return list(filter(bool, result))
        return None

    async def __async_download_batch_share(
        self, item_list, value: str = "thumb", oof_upload: bool = False
    ) -> Optional[List]:
        """
        为单个批次分享创建并并发执行所有下载任务
        """
        semaphore = Semaphore(256)
        async with AsyncClient(follow_redirects=True) as client:
            tasks = []
            for item in item_list:
                path = Path(item["path"])
                task = self.async_save_mediainfo_file(
                    client,
                    semaphore,
                    path,
                    path.name,
                    item.get(value),
                    sha1=item["sha1"] if oof_upload else None,
                )
                tasks.append(task)
            if tasks:
                result = await gather(*tasks)
                if oof_upload:
                    return list(filter(bool, result))
        return None

    def batch_subtitle_downloader(self, downloads_list: List):
        """
        批量字幕文件下载

        .. caution::
            这个函数运行时，会把相关文件以 200 为一批，同一批次复制到同一个新建的目录，在批量获取链接后，自动把目录删除到回收站

        .. attention::
            目前 115 只支持：".srt"、".ass"、".ssa"
        """
        for item_list in batched(downloads_list, self.batch_size):
            resp = self.client.fs_mkdir(
                f"subtitle-{uuid4()}", **configer.get_ios_ua_app(app=False)
            )
            check_response(resp)
            if "cid" in resp:
                scid = resp["cid"]
            else:
                data = resp["data"]
                if "category_id" in data:
                    scid = data["category_id"]
                else:
                    scid = data["file_id"]
            try:
                resp = self.client.fs_copy(
                    [pickcode_to_id(item["pickcode"]) for item in item_list],
                    pid=scid,
                    **configer.get_ios_ua_app(app=False),
                )
                check_response(resp)
                attr = next(
                    _iter_fs_files(
                        client=self.client,
                        payload=scid,
                        page_size=1,
                        app="web",
                        **configer.get_ios_ua_app(app=False),
                    )
                )
                resp = self.client.fs_video_subtitle(
                    attr["pickcode"], **configer.get_ios_ua_app(app=False)
                )
                check_response(resp)
                subtitles = {
                    info["sha1"]: info["url"]
                    for info in resp["data"]["list"]
                    if info.get("file_id")
                }
                asyncio_run(
                    self.__async_download_batch_subtitle_image(subtitles, item_list)
                )
            except Exception as e:
                logger.error(f"【媒体信息文件下载】批处理字幕文件失败: {e}")
            finally:
                self.client.fs_delete(scid, **configer.get_ios_ua_app(app=False))

    def batch_share_subtitle_downloader(self, downloads_list: List):
        """
        批量转存字幕下载
        """
        for item_list in batched(downloads_list, 50):
            resp = self.client.fs_mkdir(
                f"subtitle-{uuid4()}", **configer.get_ios_ua_app(app=False)
            )
            check_response(resp)
            scid = resp["cid"]
            try:
                payload = {
                    "share_code": item_list[0]["share_code"],
                    "receive_code": item_list[0]["receive_code"],
                    "file_id": ",".join([str(file["file_id"]) for file in item_list]),
                    "cid": scid,
                    "is_check": 0,
                }
                resp = self.client.share_receive(
                    payload, **configer.get_ios_ua_app(app=False)
                )
                check_response(resp)
                # 休眠等待 115 全部转存完成
                time_sleep(8)
                attr = next(
                    _iter_fs_files(
                        client=self.client,
                        payload=scid,
                        page_size=1,
                        app="web",
                        **configer.get_ios_ua_app(app=False),
                    )
                )
                resp = self.client.fs_video_subtitle(
                    attr["pickcode"], **configer.get_ios_ua_app(app=False)
                )
                check_response(resp)
                subtitles = {
                    info["sha1"]: info["url"]
                    for info in resp["data"]["list"]
                    if info.get("file_id")
                }
                asyncio_run(
                    self.__async_download_batch_subtitle_image(subtitles, item_list)
                )
            except Exception as e:
                logger.error(f"【媒体信息文件下载】批处理字幕文件失败: {e}")
            finally:
                self.client.fs_delete(scid, **configer.get_ios_ua_app(app=False))

    def batch_image_downloader(self, downloads_list: List):
        """
        批量图片文件下载

        .. caution::
            这个函数运行时，会把相关文件以 200 为一批，同一批次复制到同一个新建的目录，在批量获取链接后，自动把目录删除到回收站
        """
        for item_list in batched(downloads_list, self.batch_size):
            resp = self.client.fs_mkdir(
                f"image-{uuid4()}", **configer.get_ios_ua_app(app=False)
            )
            check_response(resp)
            scid = resp["cid"]
            try:
                ids = [pickcode_to_id(item["pickcode"]) for item in item_list]
                resp = self.client.fs_copy(
                    ids,
                    pid=scid,
                    **configer.get_ios_ua_app(app=False),
                )
                check_response(resp)
                images: Dict = {}
                for attr in iter_files(
                    client=self.client,
                    cid=scid,
                    cooldown=1.5,
                    type=2,
                    **configer.get_ios_ua_app(app=False),
                ):
                    url = None
                    try:
                        url = reduce_image_url_layers(attr["thumb"])
                    except KeyError:
                        if attr.get("is_collect", False):
                            if attr["size"] < 1024 * 1024 * 115:
                                url = self.client.download_url(
                                    attr["pickcode"],
                                    use_web_api=True,
                                    user_agent=configer.get_user_agent(),
                                )
                        else:
                            url = self.client.download_url(
                                attr["pickcode"], user_agent=configer.get_user_agent()
                            )
                    if url:
                        images[attr["sha1"]] = url
                asyncio_run(
                    self.__async_download_batch_subtitle_image(images, item_list)
                )
            except Exception as e:
                logger.error(f"【媒体信息文件下载】批处理图片文件失败: {e}")
            finally:
                self.client.fs_delete(scid, **configer.get_ios_ua_app(app=False))

    def batch_oof_fast_mi_downloader(
        self, downloads_list: List, u115_share: bool = False
    ):
        """
        处理 OOF 数据库类文件下载

        1. 本地缓存读取
        2. 请求 OOF API 获取
        3. 115 cdn 下载（下载完成后自动上传+本地缓存）
        """
        for item_list in batched(downloads_list, self.batch_size):
            json = loads(
                self.oof_fast_mi_cacher.batch_get([item["sha1"] for item in item_list])
            )
            api_item_lst = list(self.save_oof_mediainfo_file(item_list, json, "Cache"))
            dl_lst: List = api_item_lst
            if not api_item_lst:
                continue
            try:
                resp = self.p115_center.download_mediainfo_data(
                    [item["sha1"] for item in api_item_lst]
                )
                json = {i["sha1"]: i["data"] for i in resp if i["data"]}
                dl_lst = list(self.save_oof_mediainfo_file(api_item_lst, json, "Api"))
                self.oof_fast_mi_cacher.batch_set(resp)
                logger.debug(
                    f"【媒体信息文件下载】OOF 数据本地缓存成功: {len(json.keys())}"
                )
            except Exception as e:
                logger.warn(f"【媒体信息文件下载】获取 OOF 服务器数据失败: {e}")
            if not dl_lst:
                continue
            if u115_share:
                self.batch_share_downloader(dl_lst, oof_upload=True)
            else:
                self.batch_downloader(dl_lst, oof_upload=True)

    def batch_share_downloader(self, downloads_list: List, oof_upload: bool = False):
        """
        批处理分享其它类型文件下载
        """
        upload_lst: List = []
        for item_list in batched(downloads_list, 50):
            sha1_to_path = {info["sha1"]: info["path"] for info in item_list}
            resp = self.client.fs_mkdir(
                f"receive_files-{uuid4()}",
                **configer.get_ios_ua_app(app=False),
            )
            check_response(resp)
            scid = resp["cid"]
            try:
                payload = {
                    "share_code": item_list[0]["share_code"],
                    "receive_code": item_list[0]["receive_code"],
                    "file_id": ",".join([str(file["file_id"]) for file in item_list]),
                    "cid": scid,
                    "is_check": 0,
                }
                resp = self.client.share_receive(
                    payload, **configer.get_ios_ua_app(app=False)
                )
                check_response(resp)
                # 休眠等待 115 全部转存完成
                time_sleep(8)
                file_info_lst = list(
                    iter_files_with_path_skim(
                        client=self.client,
                        cid=scid,
                        with_ancestors=False,
                        **configer.get_ios_ua_app(),
                    )
                )
                pcs = [i["pickcode"] for i in file_info_lst]
                resp = self.client.download_urls(
                    ",".join(pcs), user_agent=configer.get_user_agent()
                )
                for batch in batched(resp.items(), self.max_workers):
                    r_lst = asyncio_run(
                        self.__async_download_batch_share(
                            [
                                {
                                    "url": value.geturl(),
                                    "path": sha1_to_path.get(value["sha1"]),
                                    "sha1": value["sha1"],
                                }
                                for _, value in batch
                            ],
                            value="url",
                            oof_upload=oof_upload,
                        )
                    )
                    if oof_upload:
                        upload_lst.extend(r_lst)
                    time_sleep(1)
            except Exception as e:
                logger.error(f"【媒体信息文件下载】批处理下载文件失败: {e}")
            finally:
                self.client.fs_delete(scid, **configer.get_ios_ua_app(app=False))

        if oof_upload and upload_lst:
            self._oof_data_upload(upload_lst)

    def batch_downloader(self, downloads_list: List, oof_upload: bool = False):
        """
        批处理其它类型文件下载
        """
        for item in downloads_list:
            item["file_id"] = pickcode_to_id(item["pickcode"])
        upload_lst: List = []
        try:
            for item_list in batched(downloads_list, self.batch_size):
                pcs = [item["pickcode"] for item in item_list]
                resp = self.client.download_urls(
                    ",".join(pcs), user_agent=configer.get_user_agent()
                )
                data_map = {key: value.geturl() for key, value in resp.items()}
                for batch in batched(item_list, self.max_workers):
                    if self.stop_all_flag:
                        return
                    r_lst = asyncio_run(
                        self.__async_download_batch_subtitle_image(
                            data_map, batch, value="file_id", oof_upload=oof_upload
                        )
                    )
                    if oof_upload:
                        upload_lst.extend(r_lst)
                    time_sleep(1)
        except Exception as e:
            logger.error(f"【媒体信息文件下载】批处理下载文件失败: {e}")

        if oof_upload and upload_lst:
            self._oof_data_upload(upload_lst)

    def batch_auto_downloader(self, downloads_list: List):
        """
        根据列表自动批量下载
        """
        image_suffix: Set[str] = set(TYPE_TO_SUFFIXES[2])
        subtitle_suffix: Set[str] = {".srt", ".ass", ".ssa"}
        oof_fast_mi_suffix: Set[str] = {".nfo"}

        self.stop_all_flag = False
        self.mediainfo_count: int = 0
        self.mediainfo_fail_count: int = 0
        self.mediainfo_fail_dict: List = []

        image_list: List = []
        subtitle_list: List = []
        oof_fast_mi_list: List = []
        other_list: List = []

        subtitle_list_append = subtitle_list.append
        image_list_append = image_list.append
        oof_fast_mi_append = oof_fast_mi_list.append
        other_list_append = other_list.append

        for item in downloads_list:
            suffix = Path(item["path"]).suffix
            if suffix in subtitle_suffix:
                subtitle_list_append(item)
            elif suffix in image_suffix:
                image_list_append(item)
            elif suffix in oof_fast_mi_suffix:
                oof_fast_mi_append(item)
            else:
                other_list_append(item)

        if subtitle_list and not self.stop_all_flag:
            self.batch_subtitle_downloader(subtitle_list)
        if image_list and not self.stop_all_flag:
            self.batch_image_downloader(image_list)
        if oof_fast_mi_list and not self.stop_all_flag:
            self.batch_oof_fast_mi_downloader(oof_fast_mi_list, u115_share=False)
        if other_list and not self.stop_all_flag:
            self.batch_downloader(other_list)

        return self.mediainfo_count, self.mediainfo_fail_count, self.mediainfo_fail_dict

    def batch_auto_share_downloader(self, downloads_list: List):
        """
        根据列表自动批量分享下载
        """
        subtitle_suffix: Set[str] = {".srt", ".ass", ".ssa"}
        oof_fast_mi_suffix: Set[str] = {".nfo"}

        self.mediainfo_count: int = 0
        self.mediainfo_fail_count: int = 0
        self.mediainfo_fail_dict: List = []

        image_list: List = []
        subtitle_list: List = []
        oof_fast_mi_list: List = []
        other_list: List = []

        subtitle_list_append = subtitle_list.append
        image_list_append = image_list.append
        oof_fast_mi_append = oof_fast_mi_list.append
        other_list_append = other_list.append

        for item in downloads_list:
            suffix = Path(item["path"]).suffix
            if item.get("thumb"):
                image_list_append(item)
            elif suffix in subtitle_suffix:
                subtitle_list_append(item)
            elif suffix in oof_fast_mi_suffix:
                oof_fast_mi_append(item)
            else:
                other_list_append(item)

        if image_list:
            asyncio_run(self.__async_download_batch_share(image_list))
        if subtitle_list:
            self.batch_share_subtitle_downloader(subtitle_list)
        if oof_fast_mi_list:
            self.batch_oof_fast_mi_downloader(oof_fast_mi_list, u115_share=True)
        if other_list:
            self.batch_share_downloader(other_list)

        return self.mediainfo_count, self.mediainfo_fail_count, self.mediainfo_fail_dict
