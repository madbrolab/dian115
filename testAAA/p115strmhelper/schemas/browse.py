from typing import List

from pydantic import BaseModel, Field


class BrowseDirParams(BaseModel):
    path: str = Field(default="/", description="目录路径")
    is_local: bool = Field(default=False, description="是否本地目录")


class DirectoryItem(BaseModel):
    name: str = Field(..., description="文件/目录名")
    path: str = Field(..., description="路径")
    is_dir: bool = Field(..., description="是否为目录")


class BrowseDirData(BaseModel):
    path: str = Field(..., description="当前路径")
    items: List[DirectoryItem] = Field(..., description="目录内容列表")
