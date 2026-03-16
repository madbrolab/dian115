from pathlib import Path
from platform import system, release
from typing import Dict, Any, Optional, List, Union, Literal

from orjson import loads, JSONDecodeError
from pydantic import (
    BaseModel,
    ValidationError,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    field_serializer,
)

from app.log import logger
from app.core.config import settings
from app.utils.system import SystemUtils
from app.db.systemconfig_oper import SystemConfigOper
from app.db.plugindata_oper import PluginDataOper

from ..version import VERSION
from ..core.aliyunpan import AliyunPanLogin
from ..schemas.cookie import U115Cookie
from ..schemas.share import ShareStrmConfig
from ..schemas.strm_api import StrmApiConfig
from ..utils.cron import CronUtils
from ..utils.machineid import MachineID
from ..utils.user_agent import UserAgentUtils


class PanTransferCloudDrive2Config(BaseModel):
    """
    交由 CloudDrive2 储存整理配置
    """

    enabled: bool = Field(default=False, description="交由 CloudDrive2 储存整理")
    prefix: str = Field(default="", description="CloudDrive2 储存挂载前缀")


class DirectoryUploadCloudDrive2Config(BaseModel):
    """
    目录上传交由 CloudDrive2 储存配置
    """

    enabled: bool = Field(default=False, description="交由 CloudDrive2 上传")
    prefix: str = Field(default="", description="CloudDrive2 储存挂载前缀")


class ConfigManager(BaseModel):
    """
    插件配置管理器
    """

    @staticmethod
    def _get_default_plugin_config_path() -> Path:
        """
        返回默认的插件配置目录路径
        """
        return settings.PLUGIN_DATA_PATH / "p115strmhelper"

    @staticmethod
    def _get_default_plugin_db_path() -> Path:
        """
        返回默认的插件数据库文件路径
        """
        return (
            ConfigManager._get_default_plugin_config_path() / "p115strmhelper_file.db"
        )

    @staticmethod
    def _get_default_plugin_database_script_location() -> Path:
        """
        返回默认的插件数据库结构目录路径
        """
        return settings.ROOT_PATH / "app" / "plugins" / "p115strmhelper" / "database"

    @staticmethod
    def _get_default_plugin_temp_path() -> Path:
        """
        返回默认的插件临时目录路径
        """
        return ConfigManager._get_default_plugin_config_path() / "temp"

    model_config = ConfigDict(
        extra="ignore",
        arbitrary_types_allowed=True,
        validate_assignment=True,
    )

    @field_validator(
        "cron_full_sync_strm", "increment_sync_cron", "cron_clear", mode="before"
    )
    @classmethod
    def _validate_and_fix_cron(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        status, msg = CronUtils.validate_cron_expression(v)
        if status:
            return v
        logger.warning(msg)
        fixed = CronUtils.fix_cron_expression(v)
        if CronUtils.is_valid_cron(fixed):
            logger.info(f"自动修复 cron: '{v}' -> '{fixed}'")
            return fixed
        logger.error(
            f"无法修复无效的 cron: '{v}'，恢复默认值 '{CronUtils.get_default_cron()}'"
        )
        return CronUtils.get_default_cron()

    @field_validator("share_strm_config", mode="before")
    @classmethod
    def _validate_share_strm_config(cls, v: Any) -> List[ShareStrmConfig]:
        """
        验证并转换 share_strm_config
        """
        if v is None:
            return []
        if isinstance(v, list):
            return [
                ShareStrmConfig.model_validate(item) if isinstance(item, dict) else item
                for item in v
            ]
        return []

    @field_validator("api_strm_config", mode="before")
    @classmethod
    def _validate_api_strm_config(cls, v: Any) -> List[StrmApiConfig]:
        """
        验证并转换 api_strm_config
        """
        if v is None:
            return []
        if isinstance(v, list):
            return [
                StrmApiConfig.model_validate(item) if isinstance(item, dict) else item
                for item in v
            ]
        return []

    @model_validator(mode="before")
    @classmethod
    def _validate_cron_fields_before(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        cron_fields = ["cron_full_sync_strm", "increment_sync_cron", "cron_clear"]
        for field in cron_fields:
            val = data.get(field)
            if not val:
                continue
            status, msg = CronUtils.validate_cron_expression(val)
            if status:
                continue
            logger.warning(msg)
            fixed = CronUtils.fix_cron_expression(val)
            if CronUtils.is_valid_cron(fixed):
                data[field] = fixed
                logger.info(f"自动修复 {field}: '{val}' -> '{fixed}'")
            else:
                logger.error(
                    f"无法修复无效的 {field}: '{val}'，恢复默认值 '{CronUtils.get_default_cron()}'"
                )
                data[field] = CronUtils.get_default_cron()
        return data

    PLUSIN_NAME: str = Field(
        default="P115StrmHelper", min_length=1, description="插件名称"
    )
    DB_WAL_ENABLE: bool = Field(default=True, description="是否开启数据库WAL模式")
    PLUGIN_CONFIG_PATH: Path = Field(
        default_factory=lambda: ConfigManager._get_default_plugin_config_path(),
        description="插件配置目录",
    )
    PLUGIN_DB_PATH: Path = Field(
        default_factory=lambda: ConfigManager._get_default_plugin_db_path(),
        description="插件数据库目录",
    )
    PLUGIN_DATABASE_SCRIPT_LOCATION: Path = Field(
        default_factory=lambda: (
            ConfigManager._get_default_plugin_database_script_location()
        ),
        description="插件数据库表目录",
    )
    PLUGIN_DATABASE_VERSION_LOCATIONS: List[str] = Field(
        default_factory=lambda: [
            str(ConfigManager._get_default_plugin_config_path() / "database/versions")
        ],
        description="插件数据库版本目录列表",
    )
    PLUGIN_TEMP_PATH: Path = Field(
        default_factory=lambda: ConfigManager._get_default_plugin_temp_path(),
        description="插件临时目录",
    )

    language: str = Field(default="zh_CN", min_length=1, description="插件语言")

    enabled: bool = Field(default=False, description="插件总开关")
    notify: bool = Field(default=False, description="通知开关")
    strm_url_format: str = Field(
        default="pickcode", min_length=1, description="生成 STRM URL 格式"
    )
    link_redirect_mode: str = Field(
        default="cookie", min_length=1, description="302 跳转方式"
    )
    cookies: Optional[str] = Field(default=None, description="115 Cookie")
    aliyundrive_token: Optional[str] = Field(default=None, description="阿里云盘 Token")
    password: Optional[str] = Field(default=None, description="115 安全码")
    moviepilot_address: Optional[str] = Field(
        default=None, min_length=1, description="MoviePilot 地址"
    )
    user_rmt_mediaext: str = Field(
        default="mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v",
        min_length=1,
        description="可识别媒体后缀",
    )
    user_download_mediaext: str = Field(
        default="srt,ssa,ass", min_length=1, description="可识别下载后缀"
    )

    transfer_monitor_enabled: bool = Field(
        default=False, description="整理事件监控开关"
    )
    transfer_monitor_scrape_metadata_enabled: bool = Field(
        default=False, description="刮削 STRM 开关"
    )
    transfer_monitor_scrape_metadata_exclude_paths: Optional[str] = Field(
        default=None, description="刮削排除目录"
    )
    transfer_monitor_paths: Optional[str] = Field(default=None, description="监控目录")
    transfer_mp_mediaserver_paths: Optional[str] = Field(
        default=None, description="MP-媒体库 目录转换"
    )
    transfer_monitor_mediaservers: Optional[List[str]] = Field(
        default=None, description="刷新媒体服务器"
    )
    transfer_monitor_media_server_refresh_enabled: bool = Field(
        default=False, description="刷新媒体服务器开关"
    )
    transfer_monitor_emby_mediainfo_enabled: bool = Field(
        default=False, description="EMBY 媒体信息提取开关"
    )
    transfer_monitor_clouddrive2_enabled: bool = Field(
        default=False, description="监控MP整理开启CloudDrive2储存监控"
    )

    full_sync_overwrite_mode: str = Field(
        default="never", min_length=1, description="全量同步覆盖模式"
    )
    full_sync_remove_unless_strm: bool = Field(
        default=False, description="清理无效 STRM 文件"
    )
    full_sync_remove_unless_dir: bool = Field(
        default=False, description="清理无效 STRM 目录（即无 STRM 文件的目录）"
    )
    full_sync_remove_unless_file: bool = Field(
        default=False, description="清理无效 STRM 文件关联的媒体信息文件"
    )
    full_sync_remove_unless_max_threshold: int = Field(
        default=10, ge=0, description="清理无效 STRM 最大删除阈值"
    )
    full_sync_remove_unless_stable_threshold: int = Field(
        default=5, ge=0, description="清理无效 STRM 稳定阈值"
    )
    timing_full_sync_strm: bool = Field(default=False, description="定期全量同步开关")
    full_sync_auto_download_mediainfo_enabled: bool = Field(
        default=False, description="下载媒体信息文件开关"
    )
    cron_full_sync_strm: Optional[str] = Field(
        default="0 */12 * * *", description="定期全量同步周期"
    )
    full_sync_min_file_size: Optional[int] = Field(
        default=None, ge=0, description="全量生成最小文件大小"
    )
    full_sync_media_server_refresh_enabled: bool = Field(
        default=False, description="全量同步刷新媒体服务器开关"
    )
    full_sync_mediaservers: Optional[List[str]] = Field(
        default=None, description="全量同步刷新媒体服务器列表"
    )
    full_sync_strm_paths: Optional[str] = Field(
        default=None,
        description="全量同步路径，每行格式为 本地目录#网盘目录，行尾可加 #0 表示该目录不参与全量同步",
    )
    full_sync_strm_log: bool = Field(default=True, description="全量生成输出详细日志")
    full_sync_batch_num: Union[int, str] = Field(
        default=5_000, description="全量同步单次批处理量"
    )
    full_sync_process_num: Union[int, str] = Field(
        default=128, description="全量同步文件处理线程数"
    )
    full_sync_iter_function: str = Field(
        default="iter_files_with_path_skim",
        min_length=1,
        description="全量同步使用的函数",
    )
    full_sync_process_rust: bool = Field(
        default=False, description="全量同步处理数据使用 rust 模块"
    )

    increment_sync_strm_enabled: bool = Field(default=False, description="增量同步开关")
    increment_sync_auto_download_mediainfo_enabled: bool = Field(
        default=False, description="下载媒体信息文件开关"
    )
    increment_sync_cron: Optional[str] = Field(
        default="0 */2 * * *", description="运行周期"
    )
    increment_sync_strm_paths: Optional[str] = Field(
        default=None, description="增量同步目录"
    )
    increment_sync_mp_mediaserver_paths: Optional[str] = Field(
        default=None, description="MP-媒体库 目录转换"
    )
    increment_sync_scrape_metadata_enabled: bool = Field(
        default=False, description="刮削 STRM 开关"
    )
    increment_sync_scrape_metadata_exclude_paths: Optional[str] = Field(
        default=None, description="刮削排除目录"
    )
    increment_sync_media_server_refresh_enabled: bool = Field(
        default=False, description="刷新媒体服务器开关"
    )
    increment_sync_mediaservers: Optional[List[str]] = Field(
        default=None, description="刷新媒体服务器"
    )
    increment_sync_emby_mediainfo_enabled: bool = Field(
        default=False, description="Emby 媒体信息提取开关"
    )
    increment_sync_min_file_size: Optional[int] = Field(
        default=None, ge=0, description="增量生成最小文件大小"
    )
    increment_sync_second_level_dir_scan: bool = Field(
        default=False, description="扫描二级目录生成目录树（二级目录最大限100文件夹）"
    )

    monitor_life_enabled: bool = Field(default=False, description="监控生活事件开关")
    monitor_life_auto_download_mediainfo_enabled: bool = Field(
        default=False, description="下载媒体信息文件开关"
    )
    monitor_life_paths: Optional[str] = Field(
        default=None, description="生活事件监控目录"
    )
    monitor_life_mp_mediaserver_paths: Optional[str] = Field(
        default=None, description="MP-媒体库 目录转换"
    )
    monitor_life_media_server_refresh_enabled: bool = Field(
        default=False, description="刷新媒体服务器开关"
    )
    monitor_life_mediaservers: Optional[List[str]] = Field(
        default=None, description="刷新媒体服务器"
    )
    monitor_life_emby_mediainfo_enabled: bool = Field(
        default=False, description="Emby 媒体信息提取开关"
    )
    monitor_life_event_modes: Optional[List[str]] = Field(
        default=None, description="监控事件类型"
    )
    monitor_life_scrape_metadata_enabled: bool = Field(
        default=False, description="刮削 STRM 开关"
    )
    monitor_life_scrape_metadata_exclude_paths: Optional[str] = Field(
        default=None, description="刮削排除目录"
    )
    monitor_life_remove_mp_history: bool = Field(
        default=False, description="同步删除本地STRM时是否删除MP整理记录"
    )
    monitor_life_remove_mp_source: bool = Field(
        default=False, description="同上方情况时是否删除源文件"
    )
    monitor_life_min_file_size: Optional[int] = Field(
        default=None, ge=0, description="生活事件生成最小文件大小"
    )
    monitor_life_first_pull_mode: str = Field(
        default="latest", min_length=1, description="生活事件启动拉取模式"
    )
    monitor_life_event_wait_time: int = Field(
        default=0, ge=0, description="生活事件事件等待时间"
    )

    share_strm_config: List[ShareStrmConfig] = Field(
        default_factory=list, description="分享 STRM 生成配置"
    )
    share_strm_mediaservers: Optional[List[str]] = Field(
        default=None, description="刷新媒体服务器"
    )
    share_strm_mp_mediaserver_paths: Optional[str] = Field(
        default=None, description="MP-媒体库 目录转换"
    )

    api_strm_config: List[StrmApiConfig] = Field(
        default_factory=list, description="API STRM 生成配置"
    )
    api_strm_mediaservers: Optional[List[str]] = Field(
        default=None, description="刷新媒体服务器"
    )
    api_strm_mp_mediaserver_paths: Optional[str] = Field(
        default=None, description="MP-媒体库 目录转换"
    )
    api_strm_scrape_metadata_enabled: bool = Field(
        default=False, description="刮削 STRM 开关"
    )
    api_strm_media_server_refresh_enabled: bool = Field(
        default=False, description="刷新媒体服务器开关"
    )

    clear_recyclebin_enabled: bool = Field(default=False, description="清理回收站开关")
    clear_receive_path_enabled: bool = Field(
        default=False, description="清理 最近接收 目录开关"
    )
    cron_clear: Optional[str] = Field(default="0 */7 * * *", description="清理周期")

    pan_transfer_enabled: bool = Field(default=False, description="网盘整理开关")
    pan_transfer_clouddrive2_config: PanTransferCloudDrive2Config = Field(
        default_factory=PanTransferCloudDrive2Config,
        description="网盘整理交由CloudDrive2储存整理",
    )
    pan_transfer_paths: Optional[str] = Field(default=None, description="网盘整理目录")
    pan_transfer_unrecognized_path: Optional[str] = Field(
        default=None, description="网盘整理未识别目录"
    )
    share_recieve_paths: Optional[List] = Field(
        default_factory=list, description="分享转存目录"
    )
    offline_download_paths: Optional[List] = Field(
        default_factory=list, description="离线下载目录"
    )

    fuse_enabled: bool = Field(default=False, description="FUSE 文件系统开关")
    fuse_mountpoint: Optional[str] = Field(default=None, description="FUSE 挂载点路径")
    fuse_readdir_ttl: float = Field(
        default=60, ge=0, description="FUSE 目录读取缓存 TTL（秒）"
    )
    fuse_uid: Optional[int] = Field(
        default=None, ge=0, description="FUSE 挂载文件所有者 UID（默认使用当前用户）"
    )
    fuse_gid: Optional[int] = Field(
        default=None, ge=0, description="FUSE 挂载文件所有者 GID（默认使用当前用户）"
    )
    fuse_strm_takeover_enabled: bool = Field(
        default=False, description="是否接管 STRM 文件生成内容（FUSE 挂载模式）"
    )
    fuse_strm_mount_dir: Optional[str] = Field(
        default=None, description="媒体服务器网盘挂载目录（FUSE 挂载模式）"
    )
    fuse_strm_takeover_rules: Optional[List] = Field(
        default_factory=list,
        description="STRM 接管规则（FUSE 挂载模式）",
    )

    directory_upload_enabled: bool = Field(
        default=False, description="监控目录上传开关"
    )
    directory_upload_mode: str = Field(
        default="compatibility", min_length=1, description="监控目录模式"
    )
    directory_upload_uploadext: str = Field(
        default="mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v",
        min_length=1,
        description="可上传文件后缀",
    )
    directory_upload_copyext: str = Field(
        default="srt,ssa,ass", min_length=1, description="可本地操作文件后缀"
    )
    directory_upload_path: Optional[List[Dict]] = Field(
        default=None, description="监控目录信息"
    )
    directory_upload_clouddrive2_config: DirectoryUploadCloudDrive2Config = Field(
        default_factory=DirectoryUploadCloudDrive2Config,
        description="目录上传交由CloudDrive2储存",
    )

    tg_search_channels: Optional[List[Dict]] = Field(
        default=None, description="TG 搜索频道"
    )
    nullbr_app_id: Optional[str] = Field(
        default=None, min_length=1, description="Nullbr APP ID"
    )
    nullbr_api_key: Optional[str] = Field(
        default=None, min_length=1, description="Nullbr API KEY"
    )

    same_playback: bool = Field(default=False, description="多端播放同一个文件")

    error_info_upload: bool = Field(default=True, description="上传错误信息")
    upload_module_enhancement: bool = Field(default=False, description="115 上传增强")
    upload_module_skip_slow_upload: bool = Field(
        default=False, description="115 上传秒传失败时跳过上传返回失败"
    )
    upload_module_notify: bool = Field(default=True, description="115 上传增强开启通知")
    upload_open_result_notify: bool = Field(
        default=False, description="115 上传结果通知"
    )
    upload_module_wait_time: int = Field(
        default=5 * 60, ge=0, description="115 上传增强休眠等待时间"
    )
    upload_module_wait_timeout: int = Field(
        default=60 * 60, ge=0, description="115 上传增强最长等待时间"
    )
    upload_module_skip_upload_wait_size: Optional[int] = Field(
        default=None, ge=0, description="115 上传增强跳过等待秒传的文件大小阈值"
    )
    upload_module_force_upload_wait_size: Optional[int] = Field(
        default=None, ge=0, description="115 上传增强强制等待秒传的文件大小阈值"
    )
    upload_module_skip_slow_upload_size: Optional[int] = Field(
        default=None,
        ge=0,
        description="115 上传秒传失败后跳过上传的文件大小阈值（大于此值的文件将跳过上传）",
    )
    upload_share_info: bool = Field(default=True, description="上传分享链接")
    upload_offline_info: bool = Field(default=True, description="上传离线下载链接")
    transfer_module_enhancement: bool = Field(default=False, description="115 整理增强")
    pan_transfer_takeover: bool = Field(
        default=False,
        description="接管网盘整理（启用后将接管 115 → 115 的整理任务进行批量处理，需要存储模块为 '115网盘Plus'）",
    )
    storage_module: Literal["u115", "115网盘Plus"] = Field(
        default="u115", description="存储模块选择"
    )

    strm_url_template_enabled: bool = Field(
        default=False, description="STRM URL 自定义模板是否启用"
    )
    strm_url_template: Optional[str] = Field(
        default=None, description="STRM URL 基础模板"
    )
    strm_url_template_custom: Optional[str] = Field(
        default=None, description="STRM URL 扩展名特定模板，格式：ext1,ext2 => template"
    )
    strm_filename_template_enabled: bool = Field(
        default=False, description="STRM 文件名自定义模板是否启用"
    )
    strm_filename_template: Optional[str] = Field(
        default=None, description="STRM 文件名基础模板"
    )
    strm_filename_template_custom: Optional[str] = Field(
        default=None,
        description="STRM 文件名扩展名特定模板，格式：ext1,ext2 => template",
    )
    strm_generate_blacklist: Optional[List] = Field(
        default=None, description="STRM 文件生成黑名单"
    )
    mediainfo_download_whitelist: Optional[List] = Field(
        default=None, description="媒体信息文件下载白名单"
    )
    mediainfo_download_blacklist: Optional[List] = Field(
        default=None, description="媒体信息文件下载黑名单"
    )
    strm_url_encode: bool = Field(default=False, description="STRM URL 文件名称编码")

    sync_del_enabled: bool = Field(default=False, description="同步删除开关")
    sync_del_notify: bool = Field(default=True, description="同步删除通知开关")
    sync_del_source: bool = Field(default=False, description="同步删除源文件")
    sync_del_p115_library_path: Optional[str] = Field(
        default=None, description="115网盘媒体库路径映射"
    )
    sync_del_p115_force_delete_files: bool = Field(
        default=False, description="115网盘强制删除文件"
    )
    sync_del_remove_versions: bool = Field(default=False, description="开启多版本删除")
    sync_del_mediaservers: Optional[List[str]] = Field(
        default=None, description="同步删除媒体服务器"
    )

    @field_serializer(
        "PLUGIN_CONFIG_PATH",
        "PLUGIN_DB_PATH",
        "PLUGIN_DATABASE_SCRIPT_LOCATION",
        "PLUGIN_TEMP_PATH",
    )
    def _serialize_paths(self, v: Path) -> str:
        return str(v)

    @property
    def p115center_license(self) -> str:
        """
        返回 p115center 许可证
        """
        return "cef0d1d912faea680dd04cd3c6921db386f460b43ff5b46e19ce463a11a33e4a"

    @property
    def PLUGIN_ALIGO_PATH(self) -> Path:
        """
        返回 aligo 配置的动态路径
        """
        return self.PLUGIN_CONFIG_PATH / "aligo"

    @property
    def MACHINE_ID(self) -> str:
        """
        获取或生成机器ID
        """
        return MachineID.get_or_generate_machine_id(
            self.PLUGIN_CONFIG_PATH / "machine_id.txt"
        )

    @property
    def USER_AGENT(self) -> str:
        """
        全局用户代理字符串
        """
        return self.get_user_agent()

    @property
    def cookies_dict(self) -> Dict[str, str]:
        """
        获取 cookie dict
        """
        cookie = U115Cookie.from_string(self.cookies)
        return cookie.to_dict()

    def _update_aliyun_token(self):
        """
        从文件动态获取最新的阿里云盘Token
        """
        token = AliyunPanLogin.get_token(self.PLUGIN_ALIGO_PATH / "aligo.json")
        if token:
            self.aliyundrive_token = token

    def load_from_dict(self, config_dict: Dict[str, Any]) -> bool:
        """
        从字典加载配置
        """
        try:
            for key, value in config_dict.items():
                if hasattr(self, key):
                    setattr(self, key, value)
            self._update_aliyun_token()
            return True
        except ValidationError as e:
            logger.error(f"【配置管理器】配置验证失败: {e}")
            return False

    def load_from_json(self, json_str: str) -> bool:
        """
        从JSON字符串加载配置
        """
        try:
            return self.load_from_dict(loads(json_str))
        except JSONDecodeError:
            logger.error("【配置管理器】无效的JSON格式")
            return False

    def get_config(self, key: str) -> Optional[Any]:
        """
        获取单个配置值
        """
        if key in ["PLUGIN_ALIGO_PATH", "MACHINE_ID"]:
            return getattr(self, key)
        if key == "aliyundrive_token":
            self._update_aliyun_token()
        return getattr(self, key, None)

    def get_all_configs(self) -> Dict[str, Any]:
        """
        获取所有配置
        """
        self._update_aliyun_token()
        return self.model_dump(mode="json")

    def update_config(self, updates: Dict[str, Any]) -> bool:
        """
        更新一个或多个配置项
        """
        try:
            filename_template_keys = [
                "strm_filename_template_enabled",
                "strm_filename_template",
                "strm_filename_template_custom",
            ]
            need_reset_filename_template = any(
                key in updates for key in filename_template_keys
            )

            current_data = self.model_dump(mode="json")
            current_data.update(updates)
            validated = self.model_validate(current_data)
            for key in updates.keys():
                if hasattr(validated, key):
                    setattr(self, key, getattr(validated, key))

            if "aliyundrive_token" in updates:
                if not updates.get("aliyundrive_token"):
                    (self.PLUGIN_ALIGO_PATH / "aligo.json").unlink(missing_ok=True)
            else:
                self._update_aliyun_token()

            if need_reset_filename_template:
                from ..utils.strm import StrmGenerater

                StrmGenerater._reset_filename_template_resolver()

            return True
        except ValidationError as e:
            logger.error(f"【配置管理器】配置更新失败: {e.json()}")
            return False

    def update_plugin_config(self) -> Optional[bool]:
        """
        将当前配置状态保存到数据库
        """
        systemconfig = SystemConfigOper()
        plugin_id = self.PLUSIN_NAME
        return systemconfig.set(f"plugin.{plugin_id}", self.model_dump(mode="json"))

    def get_user_agent(self, utype: int = -1) -> str:
        """
        根据类型获取指定的User-Agent
        """
        user_agents = {
            1: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            2: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            3: settings.USER_AGENT,
            4: "Mozilla/5.0 (Linux; Android 11; Redmi Note 8 Pro Build/RP1A.200720.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/89.0.4389.72 MQQBrowser/6.2 TBS/045913 Mobile Safari/537.36 V1_AND_SQ_8.8.68_2538_YYB_D A_8086800 QQ/8.8.68.7265 NetType/WIFI WebP/0.3.0 Pixel/1080 StatusBarHeight/76 SimpleUISwitch/1 QQTheme/2971 InMagicWin/0 StudyMode/0 CurrentMode/1 CurrentFontScale/1.0 GlobalDensityScale/0.9818182 AppId/537112567 Edg/98.0.4758.102",
            5: UserAgentUtils.generate_u115_ios(),
        }
        if utype in user_agents:
            return user_agents[utype]
        return (
            f"{self.PLUSIN_NAME}/{VERSION} "
            f"({system()} {release()}; "
            f"{SystemUtils.cpu_arch() if hasattr(SystemUtils, 'cpu_arch') and callable(SystemUtils.cpu_arch) else 'UnknownArch'})"
        )

    def get_ios_ua_app(self, app: bool = True) -> Dict[str, Any]:
        """
        获取 IOS 设备的 header（UA）和 APP
        """
        kwargs: Dict[str, Any] = {
            "headers": {"user-agent": self.get_user_agent(5)},
        }
        if app:
            kwargs["app"] = "ios"
        return kwargs

    def save_plugin_data(self, key: str, value: Any, plugin_id: Optional[str] = None):
        """
        保存插件数据
        :param key: 数据key
        :param value: 数据值
        :param plugin_id: plugin_id
        """
        if not plugin_id:
            plugin_id = self.PLUSIN_NAME
        plugindata = PluginDataOper()
        plugindata.save(plugin_id, key, value)

    def get_plugin_data(
        self, key: Optional[str] = None, plugin_id: Optional[str] = None
    ) -> Any:
        """
        获取插件数据
        :param key: 数据key
        :param plugin_id: plugin_id
        """
        if not plugin_id:
            plugin_id = self.PLUSIN_NAME
        plugindata = PluginDataOper()
        return plugindata.get_data(plugin_id, key)

    def del_plugin_data(self, key: str, plugin_id: Optional[str] = None) -> Any:
        """
        删除插件数据
        :param key: 数据key
        :param plugin_id: plugin_id
        """
        if not plugin_id:
            plugin_id = self.PLUSIN_NAME
        plugindata = PluginDataOper()
        return plugindata.del_data(plugin_id, key)


configer = ConfigManager()
