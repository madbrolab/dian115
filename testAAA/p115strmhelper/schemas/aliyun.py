from typing import Optional

from pydantic import BaseModel, Field


class AliyunDriveQRCodeData(BaseModel):
    qrcode: str = Field(..., description="二维码")
    t: str = Field(..., description="时间戳")
    ck: str = Field(..., description="校验值")


class CheckAliyunDriveQRCodeParams(BaseModel):
    t: str = Field(..., description="时间戳")
    ck: str = Field(..., description="校验值")


class CheckAliyunDriveQRCodeData(BaseModel):
    status: str = Field(..., description="状态")
    msg: str = Field(..., description="消息")
    token: Optional[str] = Field(default=None, description="Token")
