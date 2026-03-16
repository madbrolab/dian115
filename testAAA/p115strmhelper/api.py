from base64 import b64encode, b64decode
from io import BytesIO
from datetime import datetime
from dataclasses import asdict
from time import time, sleep
from typing import Dict, Optional
from pathlib import Path
from urllib.parse import quote, unquote

from p115center import P115Center
from qrcode import make as qr_make
from orjson import dumps, loads
from p115client import P115Client, check_response
from p115client.exception import P115DataError
from p115client.tool.fs_files import iter_fs_files
from fastapi import Body, Request, Response, Depends, status, Query
from fastapi.responses import JSONResponse

from .service import servicer
from .core.config import configer
from .schemas.donate import DEFAULT_DONATE_INFO as DONATE_INFO
from .core.cache import idpathcacher, DirectoryCache
from .core.aliyunpan import AliyunPanLogin
from .core.p115 import get_pid_by_path, get_pickcode_by_path
from .helper.life.test import MonitorLifeTest
from .helper.strm import ApiSyncStrmHelper
from .schemas.offline import (
    OfflineTasksPayload,
    AddOfflineTaskPayload,
    OfflineTasksData,
)
from .schemas.aliyun import (
    AliyunDriveQRCodeData,
    CheckAliyunDriveQRCodeParams,
    CheckAliyunDriveQRCodeData,
)
from .schemas.machineid import MachineID, MachineIDFeature
from .schemas.browse import BrowseDirParams, BrowseDirData, DirectoryItem
from .schemas.u115 import (
    QRCodeData,
    CheckQRCodeData,
    CheckQRCodeParams,
    GetQRCodeParams,
    UserInfo,
    UserStorageStatusResponse,
    StorageInfo,
)
from .schemas.plugin import (
    CheckLifeEventStatusPayload,
    LifeEventCheckData,
    LifeEventCheckSummary,
    PluginStatusData,
)
from .schemas.api import ApiResponse
from .schemas.share import ShareApiData, ShareResponseData, ShareSaveParent
from .schemas.strm_api import (
    StrmApiPayloadData,
    StrmApiPayloadByPathData,
    StrmApiPayloadRemoveData,
    ManualTransferPayload,
)
from .schemas.sync_del_history import DeleteSyncDelHistoryPayload
from .schemas.fuse import FuseMountPayload, FuseStatusData
from .utils.sentry import sentry_manager

from app.log import logger
from app.core.cache import cached, TTLCache
from app.helper.mediaserver import MediaServerHelper


@sentry_manager.capture_all_class_exceptions
class Api:
    """
    插件 API
    """

    def __init__(self, client: Optional[P115Client]):
        self._client = client

        self.browse_dir_pan_api_cache = TTLCache(
            maxsize=1024, ttl=120, region="p115strmhelper_api_browse_dir_api"
        )
        self.browse_dir_pan_api_last = 0

    @staticmethod
    def get_config_api() -> Dict:
        """
        获取配置
        """
        config = configer.get_all_configs()

        mediaserver_helper = MediaServerHelper()
        config["mediaservers"] = [
            {"title": config.name, "value": config.name, "type": config.type}
            for config in mediaserver_helper.get_configs().values()
        ]

        return config

    @staticmethod
    def get_machine_id_api() -> MachineID:
        """
        获取 Machine ID
        """
        return MachineID(machine_id=configer.MACHINE_ID)

    @staticmethod
    def generate_media_redirect_config_api(
        mount_dir: str = Query(
            default="/emby/115", description="媒体服务器网盘挂载目录"
        ),
        moviepilot_address: str = Query(default="", description="MoviePilot 地址"),
        config_type: str = Query(
            default="emby2alist",
            description="配置类型：emby2alist | emby_reverse_proxy",
        ),
    ) -> ApiResponse:
        """
        生成 emby2Alist 或 Emby 302 反向代理配置

        :param mount_dir: 媒体服务器网盘挂载目录
        :param moviepilot_address: MoviePilot 地址
        :param config_type: 配置类型，emby2alist 或 emby_reverse_proxy

        :return: 生成的配置
        """
        try:
            if not moviepilot_address:
                moviepilot_address = configer.get_config("moviepilot_address") or ""

            if not moviepilot_address:
                moviepilot_address = "http://localhost:3000"

            base_url = moviepilot_address.rstrip("/")
            redirect_url = f"{base_url}/api/v1/plugin/P115StrmHelper/redirect_url"

            if config_type == "emby_reverse_proxy":
                generated_config = f"{mount_dir} => {redirect_url}"
            else:
                config_rules = [
                    f"  // 匹配 {mount_dir} 开头的路径，替换为新的 URL（保留后续路径）",
                    f'  [0, 1, "{mount_dir}", "{redirect_url}"],',
                ]
                generated_config = "\n".join(config_rules)

            return ApiResponse(
                code=0,
                msg="配置生成成功",
                data={
                    "generated_config": generated_config,
                    "mount_dir": mount_dir,
                    "moviepilot_address": moviepilot_address,
                    "redirect_url": redirect_url,
                    "config_type": config_type,
                },
            )
        except Exception as e:
            logger.error(f"生成 emby2Alist 配置失败: {e}", exc_info=True)
            return ApiResponse(code=-1, msg=f"生成配置失败: {str(e)}")

    @staticmethod
    def get_sync_del_history(
        page: int = Query(default=1, ge=1, description="页码，必须大于等于1"),
        limit: int = Query(default=20, description="每页数量，-1 表示获取所有"),
    ) -> ApiResponse:
        """
        获取同步删除历史记录

        :param page: 页码
        :param limit: 每页数量，-1 表示获取所有

        :return: 历史记录列表
        """
        historys = configer.get_plugin_data(key="sync_del_history") or []

        historys = sorted(historys, key=lambda x: x.get("del_time", ""), reverse=True)

        total = len(historys)

        if limit == -1:
            paginated_historys = historys
        else:
            start = (page - 1) * limit
            end = start + limit
            paginated_historys = historys[start:end]

        return ApiResponse(
            code=0,
            msg="获取成功",
            data={
                "total": total,
                "page": page,
                "limit": limit if limit != -1 else total,
                "items": paginated_historys,
            },
        )

    @staticmethod
    def delete_sync_del_history(payload: DeleteSyncDelHistoryPayload) -> ApiResponse:
        """
        删除同步删除历史记录

        :param payload: 删除请求体

        :return: 删除结果
        """
        historys = configer.get_plugin_data(key="sync_del_history") or []
        if not historys:
            return ApiResponse(code=1, msg="未找到历史记录")
        historys = [h for h in historys if h.get("unique") != payload.key]
        configer.save_plugin_data(key="sync_del_history", value=historys)
        return ApiResponse(code=0, msg="删除成功")

    @staticmethod
    def delete_all_sync_del_history() -> ApiResponse:
        """
        一键删除所有同步删除历史记录

        :return: 删除结果
        """
        historys = configer.get_plugin_data(key="sync_del_history") or []
        if not historys:
            return ApiResponse(code=1, msg="未找到历史记录")
        count = len(historys)
        configer.save_plugin_data(key="sync_del_history", value=[])
        return ApiResponse(code=0, msg=f"成功删除 {count} 条历史记录")

    @cached(
        region="p115strmhelper_api_get_user_storage_status", ttl=60 * 60, skip_none=True
    )
    def get_user_storage_status(self) -> UserStorageStatusResponse:
        """
        获取 115 用户基本信息和空间使用情况。
        """
        if not configer.get_config("cookies"):
            return UserStorageStatusResponse(
                success=False,
                error_message="115 Cookies 未配置，无法获取信息。",
                storage_info=None,
                user_info=None,
            )

        try:
            _temp_client = self._client
            if not _temp_client:
                try:
                    _temp_client = P115Client(configer.get_config("cookies"))
                    logger.info("【用户存储状态】P115Client 初始化成功")
                except Exception as e:
                    logger.error(f"【用户存储状态】P115Client 初始化失败: {e}")
                    return UserStorageStatusResponse(
                        success=False,
                        error_message=f"115客户端初始化失败: {e}",
                        storage_info=None,
                        user_info=None,
                    )

            # 获取用户信息
            user_info_resp = _temp_client.user_my_info()
            if user_info_resp.get("state"):
                data = user_info_resp.get("data", {})
                vip_data = data.get("vip", {})
                face_data = data.get("face", {})
                user_details_dict = {
                    "name": data.get("uname"),
                    "is_vip": vip_data.get("is_vip"),
                    "is_forever_vip": vip_data.get("is_forever"),
                    "vip_expire_date": vip_data.get("expire_str")
                    if not vip_data.get("is_forever")
                    else "永久",
                    "avatar": face_data.get("face_s"),
                }
                logger.info(
                    f"【用户存储状态】获取用户信息成功: {user_details_dict.get('name')}"
                )
            else:
                error_msg = (
                    user_info_resp.get("message", "获取用户信息失败")
                    if user_info_resp
                    else "获取用户信息响应为空"
                )
                logger.error(f"【用户存储状态】获取用户信息失败: {error_msg}")
                return UserStorageStatusResponse(
                    success=False,
                    error_message=f"获取115用户信息失败: {error_msg}",
                    storage_info=None,
                    user_info=None,
                )

            # 获取空间信息
            space_info_resp = _temp_client.fs_index_info(payload=0)
            if space_info_resp.get("state"):
                data = space_info_resp.get("data", {}).get("space_info", {})
                storage_details_dict = {
                    "total": data.get("all_total", {}).get("size_format"),
                    "used": data.get("all_use", {}).get("size_format"),
                    "remaining": data.get("all_remain", {}).get("size_format"),
                }
                logger.info(
                    f"【用户存储状态】获取空间信息成功: 总-{storage_details_dict.get('total')}"
                )
            else:
                error_msg = (
                    space_info_resp.get("error", "获取空间信息失败")
                    if space_info_resp
                    else "获取空间信息响应为空"
                )
                logger.error(f"【用户存储状态】获取空间信息失败: {error_msg}")
                return UserStorageStatusResponse(
                    success=False,
                    error_message=f"获取115空间信息失败: {error_msg}",
                    user_info=UserInfo.model_validate(user_details_dict),
                    storage_info=None,
                )

            return UserStorageStatusResponse(
                success=True,
                user_info=UserInfo.model_validate(user_details_dict),
                storage_info=StorageInfo.model_validate(storage_details_dict)
                if storage_details_dict
                else None,
            )

        except Exception as e:
            logger.error(f"【用户存储状态】获取信息时发生意外错误: {e}", exc_info=True)
            error_str_lower = str(e).lower()
            if (
                isinstance(e, P115DataError)
                and ("errno 61" in error_str_lower or "enodata" in error_str_lower)
                and "<!doctype html>" in error_str_lower
            ):
                specific_error_message = "获取115账户信息失败：Cookie无效或已过期，请在插件配置中重新扫码登录。"
            elif (
                "cookie" in error_str_lower
                or "登录" in error_str_lower
                or "登陆" in error_str_lower
            ):
                specific_error_message = (
                    f"获取115账户信息失败：{str(e)} 请检查Cookie或重新登录。"
                )
            else:
                specific_error_message = f"处理请求时发生错误: {str(e)}"

            return UserStorageStatusResponse(
                success=False,
                error_message=specific_error_message,
                storage_info=None,
                user_info=None,
            )

    def browse_dir_api(
        self, params: BrowseDirParams = Depends()
    ) -> ApiResponse[BrowseDirData]:
        """
        浏览目录
        """
        path = Path(params.path)
        is_local = params.is_local

        if is_local:
            try:
                if not path.exists():
                    return ApiResponse(code=1, msg=f"目录不存在: {path}")
                dirs = []
                files = []
                for item in path.iterdir():
                    if item.is_dir():
                        dirs.append(
                            {"name": item.name, "path": str(item), "is_dir": True}
                        )
                    else:
                        files.append(
                            {"name": item.name, "path": str(item), "is_dir": False}
                        )
                return ApiResponse(
                    data=BrowseDirData(
                        path=str(path), items=sorted(dirs, key=lambda x: x["name"])
                    )
                )
            except Exception as e:
                return ApiResponse(code=1, msg=f"浏览本地目录失败: {str(e)}")
        else:
            if not self._client or not configer.get_config("cookies"):
                return ApiResponse(code=1, msg="未配置cookie或客户端初始化失败")

            if time() - self.browse_dir_pan_api_last < 2:
                logger.debug("浏览网盘目录 API 限流，等待 2s 后继续")
                sleep(2)

            try:
                cached_result = self.browse_dir_pan_api_cache.get(key=path.as_posix())
                if cached_result:
                    return cached_result

                cid = get_pid_by_path(
                    client=self._client,
                    path=path,
                    mkdir=False,
                    update_cache=False,
                    by_cache=False,
                )
                if cid == -1:
                    return ApiResponse(code=1, msg=f"获取目录ID失败: {path}")

                items = []
                for batch in iter_fs_files(
                    self._client, cid, cooldown=2, **configer.get_ios_ua_app(app=False)
                ):
                    for item in batch.get("data", []):
                        if "fid" not in item:
                            full_path = f"{path.as_posix().rstrip('/')}/{item.get('n')}"
                            idpathcacher.add_cache(
                                id=int(item.get("cid")), directory=full_path
                            )
                            items.append(
                                DirectoryItem(
                                    name=item.get("n"), path=full_path, is_dir=True
                                )
                            )

                self.browse_dir_pan_api_last = time()

                response_data = ApiResponse(
                    data=BrowseDirData(
                        path=path.as_posix(), items=sorted(items, key=lambda x: x.name)
                    )
                )
                self.browse_dir_pan_api_cache.set(
                    key=path.as_posix(), value=response_data
                )
                return response_data
            except Exception as e:
                logger.error(f"浏览网盘目录 API 原始错误: {str(e)}")
                return ApiResponse(code=1, msg=f"浏览网盘目录失败: {str(e)}")

    @staticmethod
    def get_qrcode_api(params: GetQRCodeParams = Depends()) -> ApiResponse[QRCodeData]:
        """
        获取登录二维码
        """
        try:
            final_client_type = params.client_type
            allowed_types = [
                "web",
                "android",
                "115android",
                "ios",
                "115ios",
                "alipaymini",
                "wechatmini",
                "115ipad",
                "tv",
                "qandroid",
            ]
            if final_client_type not in allowed_types:
                final_client_type = "alipaymini"
            logger.info(f"【扫码登入】二维码API - 使用客户端类型: {final_client_type}")

            resp = P115Client.login_qrcode_token()
            check_response(resp)
            resp_info = resp.get("data", {})
            _uid = str(resp_info.get("uid", ""))
            _time = str(resp_info.get("time", ""))
            _sign = str(resp_info.get("sign", ""))
            resp = P115Client.login_qrcode(_uid)
            qrcode_base64 = b64encode(resp).decode("utf-8")

            return ApiResponse(
                data=QRCodeData(
                    uid=_uid,
                    time=_time,
                    sign=_sign,
                    qrcode=f"data:image/png;base64,{qrcode_base64}",
                    tips="请使用115客户端扫描二维码登录",
                    client_type=final_client_type,
                )
            )
        except Exception as e:
            error_msg = f"获取登录二维码出错: {str(e)}"
            logger.error(f"【扫码登入】获取二维码异常: {e}", exc_info=True)
            return ApiResponse(code=-1, msg=error_msg)

    def _check_qrcode_api_internal(
        self, uid: str, _time: str, sign: str, client_type: str
    ) -> ApiResponse[CheckQRCodeData]:
        """
        检查二维码状态并处理登录
        """
        try:
            if not uid:
                return ApiResponse(code=-1, msg="无效的二维码ID，参数uid不能为空")
            payload = {
                "uid": uid,
                "time": _time,
                "sign": sign,
            }
            resp = P115Client.login_qrcode_scan_status(payload)
            check_response(resp)
            status_code = resp.get("data").get("status")
        except Exception as e:
            error_msg = f"检查二维码状态异常: {str(e)}"
            logger.error(f"【扫码登入】检查二维码状态异常: {e}", exc_info=True)
            return ApiResponse(code=-1, msg=error_msg)

        if status_code == 0:
            return ApiResponse(data=CheckQRCodeData(status="waiting", msg="等待扫码"))
        if status_code == 1:
            return ApiResponse(
                data=CheckQRCodeData(status="scanned", msg="已扫码，等待确认")
            )
        if status_code == -1 or (
            status_code is None and resp.get("message") == "key invalid"
        ):
            return ApiResponse(code=-1, msg="二维码已过期")
        if status_code == -2:
            return ApiResponse(code=-1, msg="用户取消登录")

        if status_code == 2:
            try:
                resp = P115Client.login_qrcode_scan_result(uid, app=client_type)
                check_response(resp)
            except Exception as e:
                return ApiResponse(code=-1, msg=f"获取登录结果请求失败: {e}")

            if resp.get("state") and resp.get("data"):
                cookie_data = resp.get("data", {})
                cookie_string = ""
                if "cookie" in cookie_data and isinstance(cookie_data["cookie"], dict):
                    cookie_string = "; ".join(
                        [
                            f"{name}={value}"
                            for name, value in cookie_data["cookie"].items()
                            if name and value
                        ]
                    )

                if cookie_string:
                    _cookies = cookie_string.strip()
                    configer.update_config({"cookies": _cookies})
                    configer.update_plugin_config()
                    try:
                        self._client = P115Client(_cookies)
                        self.get_user_storage_status.cache_clear()
                        return ApiResponse(
                            data=CheckQRCodeData(
                                status="success", msg="登录成功", cookie=_cookies
                            )
                        )
                    except Exception as ce:
                        return ApiResponse(
                            code=-1,
                            msg=f"Cookie获取成功，但客户端初始化失败: {str(ce)}",
                        )
                else:
                    return ApiResponse(code=-1, msg="登录成功但未能正确解析Cookie")
            else:
                specific_error = resp.get("message", resp.get("error", "未知错误"))
                return ApiResponse(
                    code=-1, msg=f"获取登录会话数据失败: {specific_error}"
                )

        if status_code is None:
            return ApiResponse(data=CheckQRCodeData(status="waiting", msg="等待扫码"))

        return ApiResponse(code=-1, msg=f"未知的115业务状态码: {status_code}")

    def check_qrcode_api(
        self, params: CheckQRCodeParams = Depends()
    ) -> ApiResponse[CheckQRCodeData]:
        """
        检查二维码状态
        """
        return self._check_qrcode_api_internal(
            uid=params.uid,
            _time=params.time,
            sign=params.sign,
            client_type=params.client_type,
        )

    @staticmethod
    def get_aliyundrive_qrcode_api() -> ApiResponse[AliyunDriveQRCodeData]:
        """
        获取阿里云盘登入二维码
        """
        try:
            data = AliyunPanLogin.qr().get("content").get("data")
            if data:
                img = qr_make(data.get("codeContent"))
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                base64_string = b64encode(buffered.getvalue()).decode("utf-8")

                return ApiResponse(
                    data=AliyunDriveQRCodeData(
                        qrcode=f"data:image/png;base64,{base64_string}",
                        t=str(data.get("t", "")),
                        ck=str(data.get("ck", "")),
                    )
                )
            else:
                return ApiResponse(code=-1, msg="获取二维码失败，无有效数据")
        except Exception as e:
            return ApiResponse(code=-1, msg=f"获取二维码失败: {e}")

    @staticmethod
    def check_aliyundrive_qrcode_api(
        params: CheckAliyunDriveQRCodeParams = Depends(),
    ) -> ApiResponse[CheckAliyunDriveQRCodeData]:
        """
        轮询检查阿里云盘二维码的扫描和确认状态
        """
        try:
            data = AliyunPanLogin.ck(params.t, params.ck).get("content").get("data")
            _status = data["qrCodeStatus"]

            if _status == "CONFIRMED":
                h = data["bizExt"]
                c = loads(b64decode(h).decode("gbk"))
                refresh_token = c["pds_login_result"]["refreshToken"]
                if refresh_token:
                    configer.update_config({"aliyundrive_token": refresh_token})
                    configer.update_plugin_config()
                    return ApiResponse(
                        data=CheckAliyunDriveQRCodeData(
                            status="success", msg="登录成功", token=refresh_token
                        )
                    )
                return ApiResponse(code=-1, msg="登录成功但未能获取Token")
            elif _status == "EXPIRED":
                return ApiResponse(code=-1, msg="二维码无效或已过期")
            elif _status == "CANCELED":
                return ApiResponse(code=-1, msg="用户取消登录")
            elif _status == "SCANED":
                return ApiResponse(
                    data=CheckAliyunDriveQRCodeData(
                        status="scanned", msg="请在手机上确认"
                    )
                )
            else:  # WAITING
                return ApiResponse(
                    data=CheckAliyunDriveQRCodeData(status="waiting", msg="等待扫码")
                )
        except Exception as e:
            return ApiResponse(code=-1, msg=f"检查状态时出错: {e}")

    @staticmethod
    def _create_error_response(
        message: str, status_code: int = status.HTTP_400_BAD_REQUEST
    ) -> JSONResponse:
        """
        创建一个标准化的 JSON 错误响应
        """
        return JSONResponse(
            status_code=status_code, content={"code": -1, "msg": message, "data": None}
        )

    @staticmethod
    async def _redirect_url_impl(
        request: Request,
        pickcode: str = "",
        file_name: str = "",
        id: int = 0,
        share_code: str = "",
        receive_code: str = "",
    ) -> Response:
        """
        115 网盘 302 跳转实现
        """
        user_agent = request.headers.get("User-Agent") or b""
        logger.debug(f"【302跳转服务】获取到客户端UA: {user_agent}")

        if share_code:
            try:
                if not receive_code:
                    receive_code = await servicer.redirect.get_receive_code(share_code)
                elif len(receive_code) != 4:
                    return Api._create_error_response(
                        f"Bad receive_code: {receive_code}"
                    )
                if not id:
                    if file_name:
                        id = await servicer.redirect.share_get_id_for_name(
                            share_code,
                            receive_code,
                            file_name,
                        )
                if not id:
                    return Api._create_error_response(
                        f"Please specify id or name for share_code={share_code!r}"
                    )
                url = await servicer.redirect.get_share_downurl(
                    share_code, receive_code, id, user_agent
                )
                logger.info(f"【302跳转服务】获取 115 下载地址成功: {url}")
            except Exception as e:
                error_message = f"获取 115 分享下载地址失败: {e}"
                logger.error(f"【302跳转服务】{error_message}")
                return Api._create_error_response(
                    error_message, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            if not pickcode:
                logger.debug("【302跳转服务】Missing pickcode parameter")
                return Api._create_error_response("Missing pickcode parameter")

            if not (len(pickcode) == 17 and pickcode.isalnum()):
                logger.debug(f"【302跳转服务】Bad pickcode: {pickcode} {file_name}")
                return Api._create_error_response(
                    f"Bad pickcode: {pickcode} {file_name}"
                )

            try:
                if configer.get_config("link_redirect_mode") == "cookie":
                    url = await servicer.redirect.get_downurl_cookie(
                        pickcode.lower(), user_agent
                    )
                else:
                    url = await servicer.redirect.get_downurl_open(
                        pickcode.lower(), user_agent
                    )
                logger.info(
                    f"【302跳转服务】获取 115 下载地址成功: {url} {url['file_name']}"  # pylint: disable=E1126
                )
            except Exception as e:
                error_message = f"获取 115 下载地址失败: {e}"
                logger.error(f"【302跳转服务】{error_message}")
                return Api._create_error_response(
                    error_message, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        file_name = url["file_name"]
        try:
            file_name.encode("ascii")
            content_disposition = f'attachment; filename="{file_name}"'
        except UnicodeEncodeError:
            encoded_filename = quote(file_name, safe="")
            content_disposition = f"attachment; filename*=UTF-8''{encoded_filename}"

        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={
                "Location": url,
                "Content-Disposition": content_disposition,
            },
            media_type="application/json; charset=utf-8",
            content=dumps({"status": "redirecting", "url": url}),
        )

    @staticmethod
    async def redirect_url_get(
        request: Request,
        pickcode: str = "",
        file_name: str = "",
        id: int = 0,
        share_code: str = "",
        receive_code: str = "",
    ) -> Response:
        """
        115 网盘 302 跳转 (GET)
        """
        return await Api._redirect_url_impl(
            request, pickcode, file_name, id, share_code, receive_code
        )

    @staticmethod
    async def redirect_url_post(
        request: Request,
        pickcode: str = "",
        file_name: str = "",
        id: int = 0,
        share_code: str = "",
        receive_code: str = "",
    ) -> Response:
        """
        115 网盘 302 跳转 (POST)
        """
        return await Api._redirect_url_impl(
            request, pickcode, file_name, id, share_code, receive_code
        )

    @staticmethod
    async def redirect_url_head(
        request: Request,
        pickcode: str = "",
        file_name: str = "",
        id: int = 0,
        share_code: str = "",
        receive_code: str = "",
    ) -> Response:
        """
        115 网盘 302 跳转 (HEAD)
        """
        return await Api._redirect_url_impl(
            request, pickcode, file_name, id, share_code, receive_code
        )

    @staticmethod
    def _resolve_pickcode_from_args(
        args: str, pickcode: str
    ) -> tuple[Optional[str], Optional[Response]]:
        """
        从 args 解析 pick_code

        :param args: 参数，可能是 pick_code、路径或 id
        :param pickcode: 已有的 pick_code

        :return: (pick_code, error_response)，成功时返回 (pick_code, None)，失败时返回 (None, Response)
        """
        if args and not pickcode:
            if len(args) == 17 and args.isalnum():
                return args, None
            if "/" in args:
                try:
                    decoded_args = unquote(args)
                    if decoded_args.startswith("/") or "/" in decoded_args:
                        path_to_use = decoded_args
                    else:
                        path_to_use = args
                except Exception:
                    path_to_use = args
                if path_to_use and not path_to_use.startswith("/"):
                    path_to_use = "/" + path_to_use
                try:
                    resolved_pickcode = get_pickcode_by_path(
                        servicer.client,
                        path_to_use,
                        **configer.get_ios_ua_app(app=False),
                    )
                    if not resolved_pickcode:
                        logger.error(
                            f"【302跳转服务】无法通过路径获取 pickcode: {path_to_use}"
                        )
                        return None, Api._create_error_response(
                            f"无法通过路径获取 pickcode: {path_to_use}",
                            status_code=status.HTTP_404_NOT_FOUND,
                        )
                    return resolved_pickcode, None
                except Exception as e:
                    logger.error(f"【302跳转服务】获取 pickcode 失败: {e}")
                    return None, Api._create_error_response(
                        f"获取 pickcode 失败: {e}",
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
            else:
                try:
                    file_id = int(args)
                    resolved_pickcode = servicer.client.to_pickcode(file_id)
                    return resolved_pickcode, None
                except (ValueError, TypeError):
                    logger.error(f"【302跳转服务】无效的参数格式: {args}")
                    return None, Api._create_error_response(
                        f"无效的参数格式: {args}",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
        return pickcode, None

    @staticmethod
    async def redirect_url_get_path(
        request: Request,
        args: str = "",
        pickcode: str = "",
        file_name: str = "",
        id: int = 0,
        share_code: str = "",
        receive_code: str = "",
    ) -> Response:
        """
        115 网盘 302 跳转 (GET)
        """
        resolved_pickcode, error_response = Api._resolve_pickcode_from_args(
            args, pickcode
        )
        if error_response:
            return error_response
        return await Api._redirect_url_impl(
            request, resolved_pickcode, file_name, id, share_code, receive_code
        )

    @staticmethod
    async def redirect_url_post_path(
        request: Request,
        args: str = "",
        pickcode: str = "",
        file_name: str = "",
        id: int = 0,
        share_code: str = "",
        receive_code: str = "",
    ) -> Response:
        """
        115 网盘 302 跳转 (POST)
        """
        resolved_pickcode, error_response = Api._resolve_pickcode_from_args(
            args, pickcode
        )
        if error_response:
            return error_response
        return await Api._redirect_url_impl(
            request, resolved_pickcode, file_name, id, share_code, receive_code
        )

    @staticmethod
    async def redirect_url_head_path(
        request: Request,
        args: str = "",
        pickcode: str = "",
        file_name: str = "",
        id: int = 0,
        share_code: str = "",
        receive_code: str = "",
    ) -> Response:
        """
        115 网盘 302 跳转 (HEAD)
        """
        resolved_pickcode, error_response = Api._resolve_pickcode_from_args(
            args, pickcode
        )
        if error_response:
            return error_response
        return await Api._redirect_url_impl(
            request, resolved_pickcode, file_name, id, share_code, receive_code
        )

    @staticmethod
    def trigger_full_sync_api() -> ApiResponse:
        """
        触发全量同步
        """
        try:
            if not configer.get_config("enabled") or not configer.get_config("cookies"):
                return ApiResponse(code=1, msg="插件未启用或未配置cookie")
            servicer.start_full_sync()
            return ApiResponse(msg="全量同步任务已启动")
        except Exception as e:
            return ApiResponse(code=1, msg=f"启动全量同步任务失败: {str(e)}")

    @staticmethod
    def trigger_full_sync_db_api() -> ApiResponse:
        """
        触发全量同步数据库
        """
        try:
            if not configer.get_config("enabled") or not configer.get_config("cookies"):
                return ApiResponse(code=1, msg="插件未启用或未配置cookie")
            servicer.start_full_sync_db()
            return ApiResponse(msg="全量同步数据库任务已启动")
        except Exception as e:
            return ApiResponse(code=1, msg=f"启动全量同步数据库任务失败: {str(e)}")

    @staticmethod
    def trigger_share_sync_api() -> ApiResponse:
        """
        触发分享同步
        """
        try:
            if not configer.get_config("enabled") or not configer.get_config("cookies"):
                return ApiResponse(code=1, msg="插件未启用或未配置cookie")
            if not configer.share_strm_config:
                return ApiResponse(code=1, msg="分享同步未配置")
            servicer.start_share_sync()
            return ApiResponse(msg="分享同步任务已启动")
        except Exception as e:
            return ApiResponse(code=1, msg=f"启动分享同步任务失败: {str(e)}")

    @staticmethod
    def clear_id_path_cache_api() -> ApiResponse:
        """
        清理文件路径ID缓存
        """
        idpathcacher.clear()
        return ApiResponse(msg="文件路径ID缓存已清理")

    @staticmethod
    def clear_increment_skip_cache_api() -> ApiResponse:
        """
        清理增量同步跳过路径缓存
        """
        directory_cache = DirectoryCache(configer.PLUGIN_TEMP_PATH / "increment_skip")
        directory_cache.clear_group("increment_skip")
        return ApiResponse(msg="增量同步跳过路径缓存已清理")

    @staticmethod
    def get_status_api() -> ApiResponse[PluginStatusData]:
        """
        获取插件状态
        """
        return ApiResponse(
            data=PluginStatusData(
                enabled=configer.get_config("enabled"),
                has_client=bool(servicer.client),
                running=(
                    bool(servicer.scheduler.get_jobs()) if servicer.scheduler else False
                )
                or bool(
                    servicer.monitor_life_thread
                    and servicer.monitor_life_thread.is_alive()
                )
                or bool(servicer.service_observer),
            )
        )

    @staticmethod
    def add_transfer_share(share_url: str = "") -> ShareApiData:
        """
        添加分享转存整理
        """
        if not configer.share_recieve_paths:
            return ShareApiData(code=-1, msg="用户未配置转存目录")

        if not share_url:
            return ShareApiData(code=-1, msg="未传入分享链接")

        try:
            result = servicer.sharetransferhelper.add_share_115(
                share_url, notify=configer.notify
            )
        except Exception as e:
            return ShareApiData(code=-1, msg=str(e))

        if not result[0]:
            if result[1] == "解析分享链接失败":
                return ShareApiData(code=-1, msg="解析分享链接失败")
            else:
                return ShareApiData(code=-1, msg=result[2])
        else:
            return ShareApiData(
                code=0,
                msg="转存成功",
                data=ShareResponseData(
                    media_info=asdict(result[1]) if result[1] else None,
                    save_parent=ShareSaveParent(path=result[2], id=result[3]),
                ),
                timestamp=datetime.now(),
            )

    @staticmethod
    def offline_tasks_api(
        payload: OfflineTasksPayload,
    ) -> ApiResponse[OfflineTasksData]:
        """
        离线任务列表
        """
        page = payload.page
        limit = payload.limit

        all_tasks = servicer.offlinehelper.get_cached_data()
        total = len(all_tasks)

        if limit == -1:
            paginated_tasks = all_tasks
        else:
            start = (page - 1) * limit
            end = start + limit
            paginated_tasks = all_tasks[start:end]

        return ApiResponse(
            msg="获取离线任务成功",
            data=OfflineTasksData(total=total, tasks=paginated_tasks),
        )

    @staticmethod
    def add_offline_task_api(payload: AddOfflineTaskPayload) -> ApiResponse:
        """
        添加离线下载任务
        """
        links = payload.links
        path = payload.path

        if not path:
            status = servicer.offlinehelper.add_urls_to_transfer(links)
        else:
            status = servicer.offlinehelper.add_urls_to_path(links, path)

        if status:
            return ApiResponse(
                msg=f"{len(payload.links)} 个新任务已成功添加，正在后台处理。"
            )

        return ApiResponse(code=-1, msg="添加失败：请前往后台查看插件日志")

    @staticmethod
    def check_feature_api(name: str = "") -> MachineIDFeature:
        """
        判断是否有权限使用此增强功能
        """
        try:
            client = P115Center(configer.get_config("MACHINE_ID"))
            resp = client.check_feature(name)
            return MachineIDFeature(**resp)
        except Exception:
            return MachineIDFeature(
                machine_id=None,
                feature_name=name,
                enabled=False,
            )

    @staticmethod
    def get_authorization_status_api() -> ApiResponse:
        """
        获取机器授权状态
        """
        try:
            client = P115Center(configer.get_config("MACHINE_ID"))
            resp = client.get_authorization_status()
            if resp:
                return ApiResponse(code=0, msg="获取授权状态成功", data=resp)
            return ApiResponse(code=1, msg="获取授权状态失败")
        except Exception as e:
            return ApiResponse(code=-1, msg=f"获取授权状态失败: {str(e)}")

    @staticmethod
    def get_donate_info_api() -> ApiResponse:
        """
        获取捐赠信息（微信、支付宝二维码和红包口令）
        """
        try:
            return ApiResponse(code=0, msg="获取捐赠信息成功", data=DONATE_INFO)
        except Exception as e:
            return ApiResponse(code=-1, msg=f"获取捐赠信息失败: {str(e)}")

    @staticmethod
    def check_life_event_status_api(
        payload: Optional[CheckLifeEventStatusPayload] = Body(default=None),
    ) -> ApiResponse:
        """
        检查生活事件线程状态并测试拉取数据

        :param payload: 可选请求体，含 start_time 时执行“拉取指定时间内的全部数据”检查
        """
        debug_info = []
        success = True
        error_messages = []

        debug_info.append("=" * 60)
        debug_info.append("115生活事件故障检查报告")
        debug_info.append("=" * 60)
        debug_info.append("")

        debug_info.append("1. 插件基础状态")
        debug_info.append(f"   插件启用: {configer.get_config('enabled')}")
        cookies_configured = "是" if configer.get_config("cookies") else "否"
        debug_info.append(f"   Cookies配置: {cookies_configured}")
        debug_info.append("")

        debug_info.append("2. 生活事件配置")
        monitor_life_enabled = configer.get_config("monitor_life_enabled")
        monitor_life_paths = configer.get_config("monitor_life_paths")
        monitor_life_event_modes = configer.get_config("monitor_life_event_modes")
        debug_info.append(f"   启用状态: {monitor_life_enabled}")
        debug_info.append(
            f"   监控路径: {monitor_life_paths if monitor_life_paths else '未配置'}"
        )
        debug_info.append(
            f"   事件模式: {monitor_life_event_modes if monitor_life_event_modes else '未配置'}"
        )
        debug_info.append("")

        debug_info.append("3. 网盘整理配置")
        pan_transfer_enabled = configer.get_config("pan_transfer_enabled")
        pan_transfer_paths = configer.get_config("pan_transfer_paths")
        debug_info.append(f"   启用状态: {pan_transfer_enabled}")
        debug_info.append(
            f"   整理路径: {pan_transfer_paths if pan_transfer_paths else '未配置'}"
        )
        debug_info.append("")

        debug_info.append("4. 生活事件线程状态")
        monitor_life_thread = servicer.monitor_life_thread
        if monitor_life_thread:
            is_alive = monitor_life_thread.is_alive()
            debug_info.append("   线程存在: 是")
            debug_info.append(f"   线程运行: {is_alive}")
            debug_info.append(f"   线程名称: {monitor_life_thread.name}")
        else:
            debug_info.append("   线程存在: 否")
            debug_info.append("   线程运行: 否")
        debug_info.append("")

        debug_info.append("5. 115客户端状态")
        client = servicer.client
        if client:
            debug_info.append("   客户端初始化: 是")
            try:
                test_resp = client.user_my_info()
                if test_resp.get("state"):
                    debug_info.append("   客户端可用: 是")
                    user_info = test_resp.get("data", {})
                    debug_info.append(f"   用户名: {user_info.get('uname', '未知')}")
                else:
                    debug_info.append("   客户端可用: 否")
                    debug_info.append(
                        f"   错误信息: {test_resp.get('message', '未知错误')}"
                    )
                    success = False
                    error_messages.append("115客户端不可用")
            except Exception as e:
                debug_info.append("   客户端可用: 否")
                debug_info.append(f"   异常信息: {str(e)}")
                success = False
                error_messages.append(f"115客户端异常: {str(e)}")
        else:
            debug_info.append("   客户端初始化: 否")
            success = False
            error_messages.append("115客户端未初始化")
        debug_info.append("")

        debug_info.append("6. MonitorLife实例状态")
        monitorlife = servicer.monitorlife
        if monitorlife:
            debug_info.append("   实例存在: 是")
            client_associated = "是" if monitorlife._client else "否"
            debug_info.append(f"   客户端关联: {client_associated}")

            test_client = monitorlife._client if monitorlife._client else client
            if test_client:
                test_success, test_debug_info, test_error = (
                    MonitorLifeTest.test_life_event_status(test_client)
                )
                debug_info.extend(test_debug_info)
                if not test_success:
                    success = False
                    if test_error:
                        error_messages.append(test_error)
            else:
                debug_info.append("   生活事件检查: 跳过（客户端不存在）")
                success = False
        else:
            debug_info.append("   实例存在: 否")
            success = False
            error_messages.append("MonitorLife实例不存在")
        debug_info.append("")

        debug_info.append("7. 测试拉取生活事件数据")
        if monitorlife and monitorlife._client:
            pull_success, pull_debug_info, pull_errors = (
                MonitorLifeTest.test_life_event_pull(monitorlife._client)
            )
            debug_info.extend(pull_debug_info)
            if not pull_success:
                success = False
                error_messages.extend(pull_errors)
        elif monitorlife and client:
            pull_success, pull_debug_info, pull_errors = (
                MonitorLifeTest.test_life_event_pull(client)
            )
            debug_info.extend(pull_debug_info)
            if not pull_success:
                success = False
                error_messages.extend(pull_errors)
        else:
            debug_info.append("   拉取测试: 跳过（MonitorLife或客户端不存在）")
            success = False
        debug_info.append("")

        pull_client = (
            (monitorlife and monitorlife._client) or (monitorlife and client) or client
        )
        if payload and payload.start_time is not None:
            debug_info.append("8. 拉取指定时间内的全部数据")
            if pull_client:
                from_ts = int(payload.start_time)
                pull_ok, from_debug, from_errors = (
                    MonitorLifeTest.test_life_event_pull_from_time(pull_client, from_ts)
                )
                debug_info.extend(from_debug)
                if not pull_ok:
                    success = False
                    error_messages.extend(from_errors)
            else:
                debug_info.append("   跳过（客户端不存在）")
            debug_info.append("")
            config_step_num = "9"
        else:
            config_step_num = "8"

        debug_info.append(f"{config_step_num}. 配置完整性检查")
        should_run = bool(
            (monitor_life_enabled and monitor_life_paths and monitor_life_event_modes)
            or (pan_transfer_enabled and pan_transfer_paths)
        )
        debug_info.append(f"   应运行: {should_run}")
        if should_run:
            if not monitor_life_thread or not monitor_life_thread.is_alive():
                debug_info.append("   线程状态: 未运行（应运行但未运行，可能存在问题）")
                success = False
                error_messages.append("配置应运行但线程未运行")
            else:
                debug_info.append("   线程状态: 正常运行")
        else:
            debug_info.append("   线程状态: 未配置运行（配置未启用或配置不完整）")
        debug_info.append("")

        debug_info.append("=" * 60)
        debug_info.append("检查总结")
        debug_info.append("=" * 60)
        if success:
            debug_info.append("✓ 所有检查通过")
        else:
            debug_info.append("✗ 发现问题:")
            for msg in error_messages:
                debug_info.append(f"  - {msg}")
        debug_info.append("=" * 60)

        debug_text = "\n".join(debug_info)

        return ApiResponse(
            code=0 if success else 1,
            msg="检查完成" if success else "发现问题",
            data=LifeEventCheckData(
                success=success,
                error_messages=error_messages,
                debug_info=debug_text,
                summary=LifeEventCheckSummary(
                    plugin_enabled=configer.get_config("enabled"),
                    client_initialized=bool(client),
                    monitorlife_initialized=bool(monitorlife),
                    thread_running=bool(
                        monitor_life_thread and monitor_life_thread.is_alive()
                    ),
                    config_valid=should_run,
                ),
            ),
        )

    def api_strm_sync_creata(self, payload: StrmApiPayloadData) -> ApiResponse:
        """
        API 请求生成 STRM
        """
        strm_helper = ApiSyncStrmHelper(
            client=self._client, mediainfo_downloader=servicer.mediainfodownloader
        )
        code, msg, data = strm_helper.generate_strm_files(payload)
        return ApiResponse(code=code, msg=msg, data=data)

    def api_strm_sync_create_by_path(
        self, payload: StrmApiPayloadByPathData
    ) -> ApiResponse:
        """
        API 请求生成 STRM（by_path）
        """
        strm_helper = ApiSyncStrmHelper(
            client=self._client, mediainfo_downloader=servicer.mediainfodownloader
        )
        code, msg, data = strm_helper.generate_strm_paths(payload)
        return ApiResponse(code=code, msg=msg, data=data)

    def api_strm_sync_remove(self, payload: StrmApiPayloadRemoveData) -> ApiResponse:
        """
        API 请求删除无效 STRM 文件
        """
        strm_helper = ApiSyncStrmHelper(
            client=self._client, mediainfo_downloader=servicer.mediainfodownloader
        )
        code, msg, data = strm_helper.remove_unless_strm(payload)
        return ApiResponse(code=code, msg=msg, data=data)

    @staticmethod
    def manual_transfer_api(payload: ManualTransferPayload) -> ApiResponse:
        """
        手动触发网盘整理

        :param payload: 包含网盘路径的请求体
        """
        if not servicer.monitorlife:
            return ApiResponse(code=-1, msg="MonitorLife 实例未初始化", data=None)
        path = payload.path
        if not path or not isinstance(path, str) or not path.strip():
            return ApiResponse(code=-1, msg="无效的路径参数", data=None)
        path = path.strip()
        success = servicer.monitorlife.start_manual_transfer(path)
        if success:
            return ApiResponse(
                code=0, msg="整理任务已启动，正在后台执行", data={"path": path}
            )
        else:
            return ApiResponse(code=-1, msg="启动整理任务失败", data=None)

    @staticmethod
    def fuse_mount_api(payload: FuseMountPayload) -> ApiResponse:
        """
        FUSE 挂载

        :param payload: 挂载请求体
        """
        if not servicer.client:
            return ApiResponse(code=-1, msg="115客户端未初始化", data=None)

        mountpoint = payload.mountpoint.strip()
        if not mountpoint:
            return ApiResponse(code=-1, msg="挂载点路径不能为空", data=None)

        try:
            success = servicer.start_fuse(
                mountpoint=mountpoint,
                readdir_ttl=payload.readdir_ttl,
            )
            if success:
                return ApiResponse(
                    code=0,
                    msg="FUSE 文件系统挂载成功",
                    data={"mountpoint": mountpoint},
                )
            else:
                return ApiResponse(code=-1, msg="FUSE 文件系统挂载失败", data=None)
        except Exception as e:
            logger.error(f"【FUSE】挂载失败: {e}", exc_info=True)
            return ApiResponse(code=-1, msg=f"挂载失败: {str(e)}", data=None)

    @staticmethod
    def fuse_unmount_api() -> ApiResponse:
        """
        FUSE 卸载
        """
        try:
            servicer.stop_fuse()
            return ApiResponse(code=0, msg="FUSE 文件系统已卸载", data=None)
        except Exception as e:
            logger.error(f"【FUSE】卸载失败: {e}", exc_info=True)
            return ApiResponse(code=-1, msg=f"卸载失败: {str(e)}", data=None)

    @staticmethod
    def fuse_status_api() -> ApiResponse[FuseStatusData]:
        """
        获取 FUSE 状态
        """
        try:
            fuse_enabled = configer.fuse_enabled or False
            fuse_manager = servicer.fuse_manager
            mounted = bool(
                fuse_manager
                and fuse_manager.fuse_thread
                and fuse_manager.fuse_thread.is_alive()
                and fuse_manager.fuse_mountpoint
            )

            data = FuseStatusData(
                enabled=fuse_enabled,
                mounted=mounted,
                mountpoint=fuse_manager.fuse_mountpoint if mounted else None,
                readdir_ttl=configer.fuse_readdir_ttl or 60,
            )
            return ApiResponse(code=0, msg="获取状态成功", data=data)
        except Exception as e:
            logger.error(f"【FUSE】获取状态失败: {e}", exc_info=True)
            return ApiResponse(code=-1, msg=f"获取状态失败: {str(e)}", data=None)
