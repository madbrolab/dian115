from pathlib import Path
from typing import Optional, Any, Callable

from app.log import logger
from app.schemas import FileItem

try:
    from app.plugins.p115disk.p115_api import P115Api  # noqa: F401

    P115API_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    P115API_AVAILABLE = False
    P115Api = Any


from ..core.config import configer
from ..core.p115disk import P115DiskCore


class P115DiskPatcher:
    """
    P115Disk 上传增强补丁
    """

    _original_upload: Optional[Callable[..., Any]] = None
    _patched_class: Optional[Any] = None
    _active: bool = False

    @staticmethod
    def _patch_upload(
        self_instance: Any,
        target_dir: FileItem,
        local_path: Path,
        new_name: Optional[str] = None,
    ) -> Optional[FileItem]:
        """
        使用 P115DiskCore 上传
        """
        client = getattr(self_instance, "client", None)
        if not client:
            return None
        helper = P115DiskCore(client=client)
        logger.debug("【P115Disk】调用补丁接口上传")
        return helper.upload(
            target_dir=target_dir, local_path=local_path, new_name=new_name
        )

    @classmethod
    def enable(cls) -> None:
        """
        应用补丁
        """
        if not P115API_AVAILABLE:
            return
        if not configer.upload_module_enhancement:
            return
        if cls._active:
            return
        cls._original_upload = P115Api.upload
        P115Api.upload = cls._patch_upload
        cls._patched_class = P115Api
        cls._active = True
        logger.info("【P115Disk】上传接口补丁应用成功")

    @classmethod
    def disable(cls) -> None:
        """
        禁用补丁
        """
        if (
            not cls._active
            or cls._original_upload is None
            or cls._patched_class is None
        ):
            return
        cls._patched_class.upload = cls._original_upload
        cls._original_upload = None
        cls._patched_class = None
        cls._active = False
        logger.info("【P115Disk】上传接口恢复原始状态成功")
