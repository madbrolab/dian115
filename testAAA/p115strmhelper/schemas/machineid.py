from typing import Optional

from pydantic import BaseModel, Field


class MachineID(BaseModel):
    """
    machine id 数据
    """

    machine_id: str = Field(..., description="机器ID")


class MachineIDFeature(BaseModel):
    """
    增强功能权限
    """

    machine_id: Optional[str] = Field(default=None, description="机器ID")
    feature_name: Optional[str] = Field(default=None, description="功能名称")
    enabled: bool = Field(default=False, description="是否启用")
