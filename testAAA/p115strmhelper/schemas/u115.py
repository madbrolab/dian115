from typing import Optional

from pydantic import BaseModel, Field


class GetQRCodeParams(BaseModel):
    client_type: str = Field(default="alipaymini", description="客户端类型")


class QRCodeData(BaseModel):
    uid: str = Field(..., description="用户ID")
    time: str = Field(..., description="时间")
    sign: str = Field(..., description="签名")
    qrcode: str = Field(..., description="二维码")
    tips: str = Field(..., description="提示")
    client_type: str = Field(..., description="客户端类型")


class CheckQRCodeParams(BaseModel):
    uid: str = Field(..., description="用户ID")
    time: str = Field(..., description="时间")
    sign: str = Field(..., description="签名")
    client_type: str = Field(default="alipaymini", description="客户端类型")


class CheckQRCodeData(BaseModel):
    status: str = Field(..., description="状态")
    msg: str = Field(..., description="消息")
    cookie: Optional[str] = Field(default=None, description="Cookie")


class UserInfo(BaseModel):
    name: Optional[str] = Field(default=None, description="用户名")
    is_vip: Optional[bool] = Field(default=None, description="是否VIP")
    is_forever_vip: Optional[bool] = Field(default=None, description="是否永久VIP")
    vip_expire_date: Optional[str] = Field(default=None, description="VIP过期日期")
    avatar: Optional[str] = Field(default=None, description="头像")


class StorageInfo(BaseModel):
    total: Optional[str] = Field(default=None, description="总容量")
    used: Optional[str] = Field(default=None, description="已用容量")
    remaining: Optional[str] = Field(default=None, description="剩余容量")


class UserStorageStatusResponse(BaseModel):
    success: bool = Field(..., description="是否成功")
    error_message: Optional[str] = Field(default=None, description="错误消息")
    user_info: Optional[UserInfo] = Field(default=None, description="用户信息")
    storage_info: Optional[StorageInfo] = Field(default=None, description="存储信息")
