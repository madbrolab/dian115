from threading import Event as ThreadEvent, Thread

from pydantic import BaseModel, ConfigDict, Field


class ObserverInfo(BaseModel):
    """
    目录上传 watchfiles 监控项
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread: Thread = Field(..., description="watchfiles 监控线程")
    stop_event: ThreadEvent = Field(..., description="停止监控用的 Event")
    mon_path: str = Field(..., description="监控目录路径")
