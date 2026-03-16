from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union


@dataclass
class EmbyMediainfoTask:
    """
    单条 Emby 媒体信息提取任务
    """

    func_name: str
    mp_mediaserver: Optional[str]
    mediaservers: Optional[List[str]]
    sha1: str
    path: Union[str, Path]
    size: Optional[int]
