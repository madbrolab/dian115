from pathlib import Path
from collections import defaultdict
from re import search as re_search, IGNORECASE
from shutil import rmtree
from threading import Lock
from traceback import format_exc
from typing import Optional
from time import sleep

from p115client import P115Client

from app.chain.storage import StorageChain
from app.log import logger
from app.utils.system import SystemUtils
from app.schemas import FileItem

from ...core.config import configer
from ...helper.strm import MonitorStrmHelper


directory_upload_dict = defaultdict(Lock)


def process_file_change(client: P115Client, file_path: str, mon_path: str) -> None:
    """
    处理 watchfiles 产生的文件变更

    :param client: 115 客户端
    :param file_path: 事件文件路径
    :param mon_path: 监控目录
    """
    p = Path(file_path)
    if p.exists() and p.is_dir():
        return
    logger.debug(f"【目录上传】文件 创建: {file_path}")
    handle_file(client, file_path, mon_path)


def handle_file(client: P115Client, event_path: str, mon_path: str):
    """
    同步一个文件

    :param client: 115 客户端
    :param event_path: 事件文件路径
    :param mon_path: 监控目录
    """
    file_path = Path(event_path)
    storage_chain = StorageChain()
    try:
        if not file_path.exists():
            return
        # 全程加锁
        with directory_upload_dict[str(file_path.absolute())]:
            # 回收站隐藏文件不处理
            if (
                event_path.find("/@Recycle/") != -1
                or event_path.find("/#recycle/") != -1
                or event_path.find("/.") != -1
                or event_path.find("/@eaDir") != -1
            ):
                logger.debug(f"【目录上传】{event_path} 是回收站或隐藏的文件")
                return

            # 蓝光目录不处理
            if re_search(r"BDMV[/\\]STREAM", event_path, IGNORECASE):
                return

            # 先判断文件是否存在
            file_item = storage_chain.get_file_item(storage="local", path=file_path)
            if not file_item:
                logger.warn(f"【目录上传】{event_path} 未找到对应的文件")
                return

            delete = False
            dest_remote = ""
            dest_local = ""
            dest_strm = ""
            for item in configer.get_config("directory_upload_path"):
                if not item:
                    continue
                if mon_path == item.get("src", ""):
                    delete = item.get("delete", False)
                    dest_remote = item.get("dest_remote", "")
                    dest_local = item.get("dest_local", "")
                    dest_strm = item.get("dest_strm", "") or ""
                    break

            if file_path.suffix.lower() in [
                f".{ext.strip()}"
                for ext in configer.get_config("directory_upload_uploadext")
                .replace("，", ",")
                .split(",")
            ]:
                # 处理上传
                if not dest_remote:
                    logger.error(f"【目录上传】{file_path} 未找到对应的上传网盘目录")
                    return

                rel = Path(file_path).relative_to(mon_path)
                if configer.directory_upload_clouddrive2_config.enabled:
                    upload_storage = "CloudDrive储存"
                    target_file_path = (
                        Path(configer.directory_upload_clouddrive2_config.prefix)
                        / dest_remote.strip("/")
                        / rel
                    )
                else:
                    upload_storage = configer.storage_module
                    target_file_path = Path(dest_remote) / rel

                # 网盘目录创建流程
                def __find_dir(_fileitem: FileItem, _name: str) -> Optional[FileItem]:
                    """
                    查找下级目录中匹配名称的目录
                    """
                    for sub_folder in storage_chain.list_files(_fileitem):
                        if sub_folder.type != "dir":
                            continue
                        if sub_folder.name == _name:
                            return sub_folder
                    return None

                target_fileitem = storage_chain.get_file_item(
                    storage=upload_storage, path=target_file_path.parent
                )
                if not target_fileitem:
                    # 逐级查找和创建目录
                    target_fileitem = FileItem(storage=upload_storage, path="/")
                    for part in target_file_path.parent.parts[1:]:
                        dir_file = __find_dir(target_fileitem, part)
                        if dir_file:
                            target_fileitem = dir_file
                        else:
                            dir_file = storage_chain.create_folder(
                                target_fileitem, part
                            )
                            if not dir_file:
                                logger.error(
                                    f"【目录上传】创建目录 {target_fileitem.path}{part} 失败！"
                                )
                                return
                            target_fileitem = dir_file

                # 上传流程
                storage_chain.upload_file(target_fileitem, file_path, file_path.name)
                sleep(5)
                uploaded_file_item = storage_chain.get_file_item(
                    storage=upload_storage, path=target_file_path
                )
                if uploaded_file_item:
                    logger.info(
                        f"【目录上传】{file_path} 上传到网盘 {target_file_path} 成功 "
                    )
                    if dest_strm:
                        if upload_storage == "CloudDrive储存":
                            setattr(
                                uploaded_file_item,
                                "pickcode",
                                client.to_pickcode(int(uploaded_file_item.fileid)),
                            )
                        MonitorStrmHelper.generate_strm_after_upload(
                            uploaded_file_item=uploaded_file_item,
                            dest_strm=dest_strm,
                            mon_path=mon_path,
                            local_file_path=file_path,
                        )
                else:
                    logger.error(f"【目录上传】{file_path} 上传网盘失败")
                    return

            elif file_path.suffix.lower() in [
                f".{ext.strip()}"
                for ext in configer.get_config("directory_upload_copyext")
                .replace("，", ",")
                .split(",")
            ]:
                # 处理非上传文件
                if dest_local:
                    target_file_path = Path(dest_local) / Path(file_path).relative_to(
                        mon_path
                    )
                    # 创建本地目录
                    target_file_path.parent.mkdir(parents=True, exist_ok=True)
                    # 复制文件
                    status, msg = SystemUtils.copy(file_path, target_file_path)
                    if status == 0:
                        logger.info(
                            f"【目录上传】{file_path} 复制到 {target_file_path} 成功 "
                        )
                    else:
                        logger.error(f"【目录上传】{file_path} 复制失败: {msg}")
                        return
            else:
                # 未匹配后缀的文件直接跳过
                return

            # 处理源文件是否删除
            if delete:
                logger.info(f"【目录上传】删除源文件：{file_path}")
                file_path.unlink(missing_ok=True)
                for file_dir in file_path.parents:
                    if len(str(file_dir)) <= len(str(Path(mon_path))):
                        break
                    files = SystemUtils.list_files(file_dir)
                    if not files:
                        logger.warn(f"【目录上传】删除空目录：{file_dir}")
                        rmtree(file_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"【目录上传】目录监控发生错误：{str(e)} - {format_exc()}")
        return
