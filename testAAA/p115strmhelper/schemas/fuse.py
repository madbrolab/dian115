from typing import Optional

from pydantic import BaseModel, Field


class FuseMountPayload(BaseModel):
    """
    FUSE 挂载请求体
    """

    mountpoint: str = Field(..., description="挂载点路径")
    readdir_ttl: float = Field(default=60, ge=0, description="目录读取缓存 TTL（秒）")


class FuseStatusData(BaseModel):
    """
    FUSE 状态数据
    """

    enabled: bool = Field(..., description="是否启用")
    mounted: bool = Field(..., description="是否已挂载")
    mountpoint: Optional[str] = Field(default=None, description="挂载点路径")
    readdir_ttl: float = Field(default=60, description="目录读取缓存 TTL（秒）")
