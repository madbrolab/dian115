from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from app.core.context import MediaInfo
from app.core.meta import MetaBase
from app.schemas import FileItem


@dataclass
class RelatedFile:
    """
    关联文件信息（字幕、音轨）
    """

    fileitem: FileItem
    target_path: Path
    file_type: str


@dataclass
class TransferTask:
    """
    整理任务
    """

    fileitem: FileItem
    target_path: Path
    mediainfo: MediaInfo
    meta: MetaBase
    transfer_type: str
    overwrite_mode: Optional[str] = None  # 覆盖模式: always, size, latest, never

    scrape: Optional[bool] = None  # 是否需要刮削
    need_notify: Optional[bool] = None  # 是否需要通知
    manual: Optional[bool] = None  # 是否手动整理
    background: Optional[bool] = None  # 是否后台运行
    username: Optional[str] = None  # 用户名
    downloader: Optional[str] = None  # 下载器
    download_hash: Optional[str] = None  # 下载记录hash

    related_files: List[RelatedFile] = field(default_factory=list)

    @property
    def all_files(self) -> List[tuple]:
        """
        返回所有需要处理的文件（主视频+关联文件）
        """
        files = [(self.fileitem, self.target_path)]
        for rf in self.related_files:
            files.append((rf.fileitem, rf.target_path))
        return files

    @property
    def target_dir(self) -> Path:
        """
        获取目标目录
        """
        return self.target_path.parent

    @property
    def target_name(self) -> str:
        """
        获取目标文件名
        """
        return self.target_path.name
