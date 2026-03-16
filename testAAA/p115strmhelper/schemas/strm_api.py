from typing import Optional, List

from pydantic import BaseModel, Field


class StrmApiConfig(BaseModel):
    """
    API 调用生成 STRM 配置
    """

    local_path: Optional[str] = Field(default=None, description="本地路径")
    pan_path: Optional[str] = Field(default=None, description="网盘路径")


class StrmApiData(BaseModel):
    """
    API 调用生成 STRM 数据
    """

    id: Optional[int] = Field(default=None, description="文件ID")
    name: Optional[str] = Field(default=None, description="文件名")
    sha1: Optional[str] = Field(default=None, description="文件SHA1")
    size: Optional[int] = Field(default=None, description="文件大小")
    pick_code: Optional[str] = Field(default=None, description="文件pickcode")
    local_path: Optional[str] = Field(default=None, description="本地路径")
    pan_path: Optional[str] = Field(default=None, description="网盘路径")
    pan_media_path: Optional[str] = Field(default=None, description="网盘媒体库路径")
    media_server_refresh: Optional[bool] = Field(
        default=None, description="是否刷新媒体服务器"
    )
    scrape_metadata: Optional[bool] = Field(default=None, description="是否刮削元数据")
    auto_download_mediainfo: bool = Field(
        default=False, description="是否自动下载媒体元数据"
    )


class StrmApiResponseFail(StrmApiData):
    """
    生成失败 STRM 信息
    """

    code: int = Field(description="错误代码")
    reason: Optional[str] = Field(default=None, description="失败原因")


class StrmApiPayloadData(BaseModel):
    """
    API 调用生成 STRM 参数
    """

    data: List[StrmApiData] = Field(
        default_factory=list, description="STRM生成数据列表"
    )


class StrmApiPayloadByPathItem(BaseModel):
    """
    API 调用生成 STRM 路径组
    """

    local_path: Optional[str] = Field(default=None, description="本地路径")
    pan_media_path: str = Field(description="网盘媒体库路径")
    remove_strm_uuid: bool = Field(
        default=False, description="是否生成删除无效文件UUID缓存"
    )


class StrmApiPayloadByPathData(BaseModel):
    """
    API 调用生成 STRM 参数（by_path）
    """

    data: List[StrmApiPayloadByPathItem] = Field(
        default_factory=list, description="需要生成STRM的一组文件夹配置项"
    )
    media_server_refresh: Optional[bool] = Field(
        default=None, description="是否刷新媒体服务器"
    )
    scrape_metadata: Optional[bool] = Field(default=None, description="是否刮削元数据")
    auto_download_mediainfo: bool = Field(
        default=False, description="是否自动下载媒体元数据"
    )


class StrmApiResponseData(BaseModel):
    """
    API 返回生成 STRM 信息
    """

    success: List[StrmApiData] = Field(
        default_factory=list, description="成功生成的STRM列表"
    )
    fail: List[StrmApiResponseFail] = Field(
        default_factory=list, description="生成失败的STRM列表"
    )
    download_fail: List[str] = Field(
        default_factory=list, description="下载失败文件列表"
    )
    success_count: int = Field(default=0, description="成功数量")
    fail_count: int = Field(default=0, description="失败数量")
    download_success_count: int = Field(default=0, description="下载成功数量")
    download_fail_count: int = Field(default=0, description="下载失败数量")


class StrmApiResponseByPathItem(BaseModel):
    """
    API 调用生成 STRM 路径组
    """

    local_path: Optional[str] = Field(default=None, description="本地路径")
    pan_media_path: str = Field(description="网盘媒体库路径")
    remove_strm_uuid: Optional[str] = Field(
        default=None, description="删除无效文件的UUID缓存"
    )


class StrmApiResponseByPathData(StrmApiResponseData):
    """
    API 返回生成 STRM 信息（by_path）
    """

    paths_info: List[StrmApiResponseByPathItem] = Field(
        default_factory=list, description="生成STRM的文件夹数据项"
    )


class StrmApiPayloadRemoveItem(BaseModel):
    """
    清理无效 STRM 配置项
    """

    local_path: str = Field(description="本地路径")
    pan_media_path: str = Field(description="网盘媒体库路径")
    remove_strm_uuid: Optional[str] = Field(
        default=None, description="删除无效文件的UUID缓存"
    )
    remove_unless_meta: bool = Field(default=False, description="清理无效媒体元数据")
    remove_unless_parent: bool = Field(default=False, description="清理空文件夹")


class StrmApiPayloadRemoveData(BaseModel):
    """
    清理无效 STRM 参数
    """

    data: List[StrmApiPayloadRemoveItem] = Field(
        default_factory=list, description="删除配置项"
    )


class StrmApiResponseRemoveData(BaseModel):
    """
    清理无效 STRM 返回结果
    """

    remove_strm_count: int = Field(default=0, description="清理 STRM 文件个数")
    data: List[StrmApiPayloadRemoveItem] = Field(
        default_factory=list, description="删除配置项"
    )


class ManualTransferPayload(BaseModel):
    """
    手动整理参数
    """

    path: str = Field(description="网盘路径")


class StrmApiStatusCode:
    """
    API STRM 错误
    """

    # 成功
    Success: int = 10200
    # 未传有效参数
    MissPayload: int = 10400
    # 缺失必要参数，pick_code，id 或 pan_path 参数
    MissPcOrId: int = 10422
    # 文件扩展名不属于可整理媒体文件扩展名
    NotRmtMediaExt: int = 10600
    # 无法获取本地生成 STRM 路径
    GetLocalPathError: int = 10601
    # 无法获取网盘媒体库路径
    GetPanMediaPathError: int = 10602
    # STRM 文件生成失败
    CreateStrmError: int = 10911
