from datetime import datetime
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ShareSaveParent(BaseModel):
    """
    分享转存目录信息
    """

    path: str = Field(..., description="路径")
    id: int | str = Field(..., description="目录ID")


class ShareResponseData(BaseModel):
    """
    分享转存返回信息
    """

    media_info: Optional[Dict] = Field(default=None, description="媒体信息")
    save_parent: ShareSaveParent = Field(..., description="保存父目录")


class ShareApiData(BaseModel):
    """
    分享转存 API 返回数据
    """

    code: int = Field(default=0, description="响应码")
    msg: str = Field(default="success", description="响应消息")
    data: Optional[ShareResponseData] = Field(default=None, description="响应数据")
    timestamp: Optional[datetime] = Field(default=None, description="时间戳")


class ShareStrmConfig(BaseModel):
    """
    分享 STRM 生成配置
    """

    comment: Optional[str] = Field(default=None, description="备注")
    enabled: bool = Field(default=True, description="是否启用")
    share_link: Optional[str] = Field(default=None, description="分享链接")
    share_code: Optional[str] = Field(default=None, description="分享码")
    share_receive: Optional[str] = Field(default=None, description="分享密码")
    share_path: Optional[str] = Field(default=None, description="分享路径")
    local_path: Optional[str] = Field(default=None, description="本地路径")
    min_file_size: Optional[int] = Field(
        default=None, description="分享生成最小文件大小"
    )
    moviepilot_transfer: bool = Field(default=False, description="交由 MoviePilot 整理")
    auto_download_mediainfo: bool = Field(
        default=False, description="自动下载网盘元数据"
    )
    media_server_refresh: bool = Field(default=False, description="刷新媒体服务器")
    scrape_metadata: bool = Field(default=False, description="是否刮削元数据")
    speed_mode: Literal[0, 1, 2, 3] = Field(default=3, description="运行速度模式")

    @model_validator(mode="after")
    def enforce_moviepilot_constraints(self):
        """
        当 moviepilot_transfer 为 True 时，强制关闭其他相关选项
        """
        if self.moviepilot_transfer:
            self.auto_download_mediainfo = False
            self.media_server_refresh = False
            self.scrape_metadata = False
        return self
