__all__ = ["P115DiskCore"]

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter, sleep
from typing import Any, Optional

from cryptography.hazmat.primitives import hashes
from oss2 import StsAuth, Bucket, determine_part_size
from oss2.exceptions import ServerError
from oss2.models import PartInfo
from oss2.utils import b64encode_as_string, SizedFileAdapter
from p115center import P115Center, UploadInfo
from p115client import P115Client, check_response

from app.core.config import global_vars
from app.log import logger
from app.modules.filemanager.storages import transfer_process
from app.schemas import FileItem, NotificationType
from app.utils.string import StringUtils

from ..core.config import configer
from ..core.i18n import i18n
from ..core.message import post_message


class P115DiskCore:
    """
    模拟 P115Disk 插件接口
    """

    def __init__(self, client: P115Client):
        try:
            from app.plugins.p115disk.p115_api import P115Api  # noqa: F401

            P115_API_AVAILABLE = True
        except (ImportError, ModuleNotFoundError):
            P115_API_AVAILABLE = False
            P115Api = Any

        if P115_API_AVAILABLE:
            self._p115_api = P115Api(client=client, disk_name="115网盘Plus")

        self.p115_center = P115Center(configer.get_config("MACHINE_ID"))

    def upload(
        self,
        target_dir: FileItem,
        local_path: Path,
        new_name: Optional[str] = None,
    ) -> Optional[FileItem]:
        """
        上传文件到云盘

        :param target_dir: 上传目标目录项
        :param local_path: 本地文件路径
        :param new_name: 上传后的文件名，如果为None则使用本地文件名

        :return: 上传成功返回文件项，失败返回None
        """

        def read_range_hash(range_str: str) -> str:
            start, end = map(int, range_str.split("-"))
            with open(local_path, "rb") as f:
                f.seek(start)
                chunk = f.read(end - start + 1)
                sha1 = hashes.Hash(hashes.SHA1())
                sha1.update(chunk)
                return sha1.finalize().hex().upper()

        def encode_callback(cb: str) -> str:
            return b64encode_as_string(cb)

        def send_upload_info(
            file_sha1: Optional[str],
            first_sha1: Optional[str],
            second_auth: bool,
            second_sha1: Optional[str],
            file_size: Optional[str],
            file_name: Optional[str],
            upload_time: Optional[int],
        ):
            """
            发送上传信息
            """
            try:
                resp = self.p115_center.upload_info(
                    UploadInfo(
                        file_sha1=file_sha1,
                        first_sha1=first_sha1,
                        second_auth=second_auth,
                        second_sha1=second_sha1,
                        file_size=file_size,
                        file_name=file_name,
                        time=upload_time,
                        postime=datetime.now(timezone.utc),
                    )
                )
                logger.info(f"【P115Disk】上传信息报告服务器成功: {resp.model_dump()}")
            except Exception as e:
                logger.warn(f"【P115Disk】上传信息报告服务器失败: {e}")

        def send_upload_wait(target_name):
            """
            发送上传等待
            """
            if configer.notify and configer.upload_module_notify:
                post_message(
                    mtype=NotificationType.Plugin,
                    title=i18n.translate("upload_module_title"),
                    text=f"\n{i18n.translate('upload_wait_text', name=target_name)}\n",
                )

            try:
                self.p115_center.upload_wait()
            except Exception:
                pass

        def send_upload_result_notify(
            success: bool,
            target_name: str,
            file_size: int,
            elapsed_time: Optional[float] = None,
            error_msg: Optional[str] = None,
        ):
            """
            发送上传结果通知

            :param success: 是否成功
            :param target_name: 文件名
            :param file_size: 文件大小
            :param elapsed_time: 耗时（秒）
            :param error_msg: 错误信息
            """
            if not configer.notify or not configer.upload_open_result_notify:
                return

            if success:
                size_str = StringUtils.str_filesize(file_size)
                time_str = f"{elapsed_time:.1f}秒" if elapsed_time else "未知"
                post_message(
                    mtype=NotificationType.Plugin,
                    title=i18n.translate("upload_success_title"),
                    text=f"\n{i18n.translate('upload_success_text', name=target_name, size=size_str, time=time_str)}\n",
                )
            else:
                size_str = StringUtils.str_filesize(file_size)
                error_text = f"\n{i18n.translate('upload_fail_text', name=target_name, size=size_str)}\n"
                if error_msg:
                    error_text += (
                        f"{i18n.translate('upload_fail_error', error=error_msg)}\n"
                    )
                post_message(
                    mtype=NotificationType.Plugin,
                    title=i18n.translate("upload_fail_title"),
                    text=error_text,
                )

        if not local_path.exists():
            logger.error(f"【P115Disk】本地文件不存在: {local_path}")
            return None

        target_name = new_name or local_path.name
        target_path = Path(target_dir.path) / target_name

        # 获取目标目录ID
        target_pid = target_dir.fileid

        # 计算文件特征值
        file_size = local_path.stat().st_size
        file_sha1 = self._p115_api._calc_sha1(local_path)

        # 清理缓存
        cache_id = self._p115_api._id_cache.get_id_by_dir(target_path.as_posix())
        if cache_id:
            self._p115_api._id_cache.remove(id=cache_id)
            self._p115_api._id_item_cache.remove(id=cache_id)

        # 初始化进度条
        logger.info(f"【P115Disk】开始上传: {local_path} -> {target_path}")
        progress_callback = transfer_process(local_path.as_posix())

        try:
            wait_start_time = perf_counter()
            send_wait = False
            while True:
                start_time = perf_counter()
                # Step 1: 初始化上传
                init_resp = None
                init_max_retries = 3
                init_retry_delay = 2
                for init_attempt in range(init_max_retries):
                    try:
                        init_resp = self._p115_api.client.upload_file_init(
                            filename=target_name,
                            filesize=file_size,
                            filesha1=file_sha1,
                            pid=target_pid,
                            read_range_bytes_or_hash=read_range_hash,
                        )
                        check_response(init_resp)
                        break
                    except Exception as e:
                        if init_attempt < init_max_retries - 1:
                            logger.warn(
                                f"【P115Disk】初始化上传失败，"
                                f"第 {init_attempt + 1}/{init_max_retries} 次重试: {e}"
                            )
                            sleep(init_retry_delay)
                            init_retry_delay *= 2
                        else:
                            logger.error(f"【P115Disk】初始化上传重试用尽: {e}")
                            return None
                if init_resp is None:
                    return None

                logger.debug(f"【P115Disk】上传初始化结果: {init_resp}")

                if not init_resp.get("state"):
                    logger.error(
                        f"【P115Disk】初始化上传失败: {init_resp.get('error')}"
                    )
                    return None

                # 检查是否秒传成功
                if init_resp.get("reuse"):
                    logger.info(f"【P115Disk】{target_name} 秒传成功")
                    progress_callback(100)
                    end_time = perf_counter()
                    elapsed_time = end_time - start_time
                    send_upload_info(
                        file_sha1,
                        "",
                        True,
                        "",
                        str(file_size),
                        target_name,
                        int(elapsed_time),
                    )
                    send_upload_result_notify(
                        success=True,
                        target_name=target_name,
                        file_size=file_size,
                        elapsed_time=elapsed_time,
                    )
                    return self._p115_api.get_item(target_path)

                # 判断是等待秒传还是直接上传
                upload_module_skip_upload_wait_size = int(
                    configer.get_config("upload_module_skip_upload_wait_size") or 0
                )
                if (
                    upload_module_skip_upload_wait_size != 0
                    and file_size <= upload_module_skip_upload_wait_size
                ):
                    logger.info(
                        f"【P115Disk】文件大小 {file_size} 小于最低阈值，跳过等待流程: {target_name}"
                    )
                    break

                if perf_counter() - wait_start_time > int(
                    configer.get_config("upload_module_wait_timeout")
                ):
                    logger.warn(
                        f"【P115Disk】等待秒传超时，自动进行上传流程: {target_name}"
                    )
                    break

                upload_module_force_upload_wait_size = int(
                    configer.get_config("upload_module_force_upload_wait_size") or 0
                )
                if (
                    upload_module_force_upload_wait_size != 0
                    and file_size >= upload_module_force_upload_wait_size
                ):
                    logger.info(
                        f"【P115Disk】文件大小 {file_size} 大于最高阈值，强制等待流程: {target_name}"
                    )
                    sleep(int(configer.get_config("upload_module_wait_time")))
                else:
                    try:
                        resp = self.p115_center.user_speed_status()

                        if resp.status != "slow":
                            logger.warn(
                                f"【P115Disk】上传速度状态 {resp.status}，跳过秒传等待: {target_name}"
                            )
                            break

                        # 计算等待时间
                        default_wait_time = int(
                            configer.get_config("upload_module_wait_time")
                        )
                        sleep_time = default_wait_time
                        fastest_speed = resp.fastest_user_speed_mbps
                        user_speed = resp.user_average_speed_mbps
                        if fastest_speed and user_speed:
                            bs = user_speed * 0.2 + fastest_speed * 0.8
                            wt = file_size / (1024 * 1024) / bs
                            if wt > 10 * 60:
                                wt = wt / (wt // (10 * 60) + 1)
                            if wt <= default_wait_time // 2:
                                wt += default_wait_time // 2
                            sleep_time = int(wt)

                        logger.info(
                            f"【P115Disk】休眠 {sleep_time} 秒，等待秒传: {target_name}"
                        )
                        if not send_wait:
                            send_upload_wait(target_name)
                            send_wait = True
                        sleep(sleep_time)
                    except Exception as e:
                        logger.warn(f"【P115Disk】获取用户上传速度错误: {e}")
                        break

            if configer.upload_module_skip_slow_upload:
                skip_upload_size = configer.get_config(
                    "upload_module_skip_slow_upload_size"
                )
                if skip_upload_size and skip_upload_size > 0:
                    if file_size >= skip_upload_size:
                        logger.warn(
                            f"【P115Disk】{target_name} 无法秒传，文件大小 {file_size} 大于等于阈值 {skip_upload_size}，跳过上传"
                        )
                        send_upload_result_notify(
                            success=False,
                            target_name=target_name,
                            file_size=file_size,
                            error_msg=f"秒传失败，文件大小 {file_size} 大于等于阈值 {skip_upload_size}，已跳过上传",
                        )
                        return None
                    else:
                        logger.info(
                            f"【P115Disk】{target_name} 无法秒传，但文件大小 {file_size} 小于阈值 {skip_upload_size}，继续执行上传"
                        )
                else:
                    logger.warn(f"【P115Disk】{target_name} 无法秒传，跳过上传")
                    send_upload_result_notify(
                        success=False,
                        target_name=target_name,
                        file_size=file_size,
                        error_msg="秒传失败，已跳过上传",
                    )
                    return None

            # 获取上传信息
            bucket_name = init_resp.get("bucket")
            object_name = init_resp.get("object")
            callback_info = init_resp.get("callback")

            if not all([bucket_name, object_name, callback_info]):
                logger.error(f"【P115Disk】上传信息不完整: {init_resp}")
                return None

            # Step 2: 获取OSS上传凭证
            (
                endpoint,
                access_key_id,
                access_key_secret,
                security_token,
                token_expiration,
            ) = self._p115_api._get_oss_token()
            logger.info(
                f"【P115Disk】OSS Token 过期时间: {token_expiration.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

            # Step 3: OSS分片上传
            auth = StsAuth(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                security_token=security_token,
            )
            bucket = Bucket(auth, endpoint, bucket_name)  # noqa
            part_size = determine_part_size(file_size, preferred_size=10 * 1024 * 1024)

            logger.info(
                f"【P115Disk】开始分片上传，分片大小: {part_size // 1024 // 1024}MB"
            )

            # 初始化分片上传
            upload_id = bucket.init_multipart_upload(
                object_name, params={"encoding-type": "url", "sequential": ""}
            ).upload_id
            parts = []

            # 逐个上传分片并更新进度
            with open(local_path, "rb") as fileobj:
                part_number = 1
                offset = 0
                while offset < file_size:
                    # 检查是否取消上传
                    if global_vars.is_transfer_stopped(local_path.as_posix()):
                        logger.info(f"【P115Disk】{local_path} 上传已取消！")
                        bucket.abort_multipart_upload(object_name, upload_id)
                        return None

                    # 检查 token 是否即将过期（提前 5 分钟刷新）
                    if self._p115_api._is_token_expiring(
                        token_expiration, threshold_minutes=5
                    ):
                        logger.info("【P115Disk】Token 即将过期，正在刷新...")
                        try:
                            (
                                endpoint,
                                access_key_id,
                                access_key_secret,
                                security_token,
                                token_expiration,
                            ) = self._p115_api._get_oss_token()
                            # 重新创建认证和 bucket 对象
                            auth = StsAuth(
                                access_key_id=access_key_id,
                                access_key_secret=access_key_secret,
                                security_token=security_token,
                            )
                            bucket = Bucket(auth, endpoint, bucket_name)  # noqa
                            logger.info(
                                f"【P115Disk】Token 刷新成功，新的过期时间: "
                                f"{token_expiration.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                            )
                        except Exception as e:
                            logger.error(f"【P115Disk】刷新 Token 失败: {str(e)}")
                            bucket.abort_multipart_upload(object_name, upload_id)
                            return None

                    num_to_upload = min(part_size, file_size - offset)

                    # 上传分片，带重试机制处理 token 过期错误
                    max_retries = 2
                    for retry in range(max_retries):
                        try:
                            result = bucket.upload_part(
                                object_name,
                                upload_id,
                                part_number,
                                data=SizedFileAdapter(fileobj, num_to_upload),
                            )
                            parts.append(PartInfo(part_number, result.etag))
                            break  # 上传成功，跳出重试循环
                        except ServerError as e:
                            # 检查是否是 token 过期错误
                            error_code = getattr(e, "code", "")
                            if (
                                error_code
                                in ("InvalidAccessKeyId", "SecurityTokenExpired")
                                and retry < max_retries - 1
                            ):
                                logger.warn(
                                    f"【P115Disk】检测到 Token 过期错误 ({error_code})，"
                                    f"正在刷新并重试..."
                                )
                                # 刷新 token
                                (
                                    endpoint,
                                    access_key_id,
                                    access_key_secret,
                                    security_token,
                                    token_expiration,
                                ) = self._p115_api._get_oss_token()
                                auth = StsAuth(
                                    access_key_id=access_key_id,
                                    access_key_secret=access_key_secret,
                                    security_token=security_token,
                                )
                                bucket = Bucket(auth, endpoint, bucket_name)  # noqa
                                # 需要重新定位文件指针
                                fileobj.seek(offset)
                                continue
                            else:
                                # 其他错误或重试次数用尽，放弃上传
                                logger.error(f"【P115Disk】上传分片失败: {str(e)}")
                                bucket.abort_multipart_upload(object_name, upload_id)
                                raise

                    # 更新偏移和分片号
                    offset += num_to_upload
                    part_number += 1

                    # 实时更新进度
                    progress = (offset * 100) / file_size
                    progress_callback(progress)
                    logger.debug(f"【P115Disk】上传进度: {progress:.1f}%")

            # 完成上传
            progress_callback(100)

            # Step 4: 完成OSS上传并回调115服务器
            headers = {
                "X-oss-callback": encode_callback(callback_info["callback"]),
                "x-oss-callback-var": encode_callback(callback_info["callback_var"]),
                "x-oss-forbid-overwrite": "false",
            }

            result = bucket.complete_multipart_upload(
                object_name, upload_id, parts, headers=headers
            )

            if result.status == 200:
                logger.info(f"【P115Disk】{target_name} 上传成功")
                end_time = perf_counter()
                elapsed_time = end_time - start_time
                send_upload_result_notify(
                    success=True,
                    target_name=target_name,
                    file_size=file_size,
                    elapsed_time=elapsed_time,
                )
                end_time = perf_counter()
                elapsed_time = end_time - start_time
                send_upload_info(
                    file_sha1,
                    "",
                    False,
                    "",
                    str(file_size),
                    target_name,
                    int(elapsed_time),
                )
                return self._p115_api.get_item(target_path)
            else:
                logger.error(
                    f"【P115Disk】{target_name} 上传失败，状态码: {result.status}"
                )
                send_upload_result_notify(
                    success=False,
                    target_name=target_name,
                    file_size=file_size,
                    error_msg=f"错误码: {result.status}",
                )
                return None

        except Exception as e:
            logger.error(f"【P115Disk】上传失败: {local_path} - {str(e)}")
            send_upload_result_notify(
                success=False,
                target_name=target_name,
                file_size=file_size,
                error_msg=f"未知错误: {str(e)}",
            )
            return None
