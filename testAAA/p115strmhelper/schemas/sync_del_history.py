from pydantic import BaseModel, Field


class DeleteSyncDelHistoryPayload(BaseModel):
    """
    删除同步删除历史记录请求体
    """
    key: str = Field(..., description="历史记录唯一标识")
