from pydantic import BaseModel, Field


class CompareMinSize(BaseModel):
    """
    文件大小最小值比较模型
    """

    min_size: int | None = Field(default=None, description="最小文件大小")
    file_size: int | None = Field(default=None, description="文件大小")
