from pathlib import Path
from typing import Optional, Callable, Any, Dict

from p115center import P115Center

from app import schemas
from app.log import logger
from app.modules.filemanager.storages.u115 import U115Pan

from ..core.u115_open import U115OpenHelper
from ..core.config import configer


class U115Patcher:
    """
    一个用于控制 U115Pan 猴子补丁的管理器。
    支持手动启用/禁用，也支持作为上下文管理器使用。
    """

    _original_method: Dict[str, Callable[..., Any]] = {
        "upload": None,
        "create_folder": None,
        "get_item": None,
        "get_folder": None,
        "rename": None,
    }
    _func_active: Dict[str, bool] = {
        "upload": False,
        "create_folder": False,
        "get_item": False,
        "get_folder": False,
        "rename": False,
    }
    log_map: Dict[str, str] = {
        "upload": "上传",
        "create_folder": "创建目录",
        "get_item": "获取文件信息",
        "get_folder": "获取目录信息",
        "rename": "重命名",
    }

    @staticmethod
    def _patch_upload(
        self_instance: U115Pan,
        target_dir: schemas.FileItem,
        local_path: Path,
        new_name: Optional[str] = None,
    ) -> Optional[schemas.FileItem]:
        """
        自定义 upload
        """
        helper = U115OpenHelper()
        logger.debug("【P115Open】调用补丁接口上传")
        return helper.upload(
            target_dir=target_dir, local_path=local_path, new_name=new_name
        )

    @staticmethod
    def _patch_create_folder(
        self_instance: U115Pan, parent_item: schemas.FileItem, name: str
    ) -> Optional[schemas.FileItem]:
        """
        自定义 create_folder
        """
        helper = U115OpenHelper()
        logger.debug("【P115Open】调用补丁接口创建目录")
        return helper.create_folder(parent_item=parent_item, name=name)

    @staticmethod
    def _patch_get_item(
        self_instance: U115Pan, path: Path
    ) -> Optional[schemas.FileItem]:
        """
        自定义 get_item
        """
        helper = U115OpenHelper()
        logger.debug("【P115Open】调用补丁接口获取文件信息")
        return helper.get_item(path=path)

    @staticmethod
    def _patch_get_folder(
        self_instance: U115Pan, path: Path
    ) -> Optional[schemas.FileItem]:
        """
        自定义 get_folder
        """
        helper = U115OpenHelper()
        logger.debug("【P115Open】调用补丁接口获取目录信息")
        return helper.get_folder(path=path)

    @staticmethod
    def _patch_rename(
        self_instance: U115Pan, fileitem: schemas.FileItem, name: str
    ) -> bool:
        """
        自定义 rename
        """
        helper = U115OpenHelper()
        logger.debug("【P115Open】调用补丁接口获取目录信息")
        return helper.rename(fileitem=fileitem, name=name)

    @classmethod
    def enable(cls):
        """
        启用猴子补丁
        """
        if configer.get_config("upload_module_enhancement"):
            if cls._func_active["upload"]:
                return

            if cls._original_method["upload"] is None:
                cls._original_method["upload"] = U115Pan.upload

            U115Pan.upload = cls._patch_upload
            cls._func_active["upload"] = True
            logger.info("【P115Open】上传接口补丁应用成功")

        try:
            client = P115Center(configer.get_config("MACHINE_ID"))
            resp = client.check_feature("transfer_module_enhancement")
            status = resp.get("enabled")
        except Exception:
            status = False

        if configer.transfer_module_enhancement and status:
            modules = ["create_folder", "get_item", "get_folder", "rename"]
            for module in modules:
                if cls._func_active.get(module):
                    continue

                original_method_name = module
                patch_method_name = f"_patch_{module}"

                original_method = getattr(U115Pan, original_method_name)
                patch_method = getattr(cls, patch_method_name)

                if cls._original_method.get(module) is None:
                    cls._original_method[module] = original_method

                setattr(U115Pan, original_method_name, patch_method)

                cls._func_active[module] = True
                logger.info(f"【P115Open】{cls.log_map[module]}接口补丁应用成功")

    @classmethod
    def disable(cls):
        """
        禁用猴子补丁
        """
        for key, status in cls._func_active.items():
            if status:
                if cls._original_method[key] is not None:
                    setattr(U115Pan, key, cls._original_method[key])

            cls._func_active[key] = False
            logger.info(f"【P115Open】{cls.log_map[key]}接口恢复原始状态成功")
