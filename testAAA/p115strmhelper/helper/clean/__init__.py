from time import sleep
from typing import List

from p115client import P115Client, check_response
from p115client.tool.fs_files import iter_fs_files

from app.log import logger

from ...core.config import configer
from ...utils.sentry import sentry_manager


class Cleaner:
    """
    清理类
    """

    def __init__(self, client: P115Client):
        self.client = client

    def clear_recyclebin(self):
        """
        清空回收站
        """
        try:
            logger.info("【回收站清理】开始清理回收站")
            payload = {"password": configer.get_config("password")}
            resp = self.client.recyclebin_clean(
                payload, **configer.get_ios_ua_app(app=False)
            )
            check_response(resp)
            logger.info("【回收站清理】回收站已清空")
        except Exception as e:
            sentry_manager.sentry_hub.capture_exception(e)
            logger.error(f"【回收站清理】清理回收站运行失败: {e}")
            return

    def clear_receive_path(self):
        """
        清空最近接收
        """
        try:
            logger.info("【最近接收清理】开始清理最近接收")
            parent_id = int(
                self.client.fs_sys_dir(0, **configer.get_ios_ua_app())["cid"]
            )
            if parent_id == -1:
                logger.info("【最近接收清理】最近接收目录为空，无需清理")
                return
            logger.info(f"【最近接收清理】最近接收目录 ID 获取成功: {parent_id}")
            sleep(2)
            id_list: List = []
            for batch in iter_fs_files(
                self.client, parent_id, cooldown=2, **configer.get_ios_ua_app(app=False)
            ):
                for item in batch.get("data", []):
                    if not item:
                        continue
                    if "fid" not in item:
                        id_list.append(item.get("cid"))
                    else:
                        id_list.append(item.get("fid"))
            if not id_list:
                logger.info("【最近接收清理】最近接收目录为空，无需清理")
                return
            batch_size = 45000
            total_files = len(id_list)
            logger.info(f"【最近接收清理】清理文件总数：{total_files}")
            sleep(2)
            if total_files > batch_size:
                logger.info(f"【最近接收清理】文件数量超过 {batch_size}，将分批删除")
                for i in range(0, total_files, batch_size):
                    batch_ids = id_list[i : i + batch_size]
                    logger.info(
                        f"【最近接收清理】正在删除第 {i // batch_size + 1} 批，数量：{len(batch_ids)}"
                    )
                    self.client.fs_delete(
                        batch_ids, **configer.get_ios_ua_app(app=False)
                    )
                    sleep(2)
            else:
                self.client.fs_delete(id_list, **configer.get_ios_ua_app(app=False))
            logger.info("【最近接收清理】最近接收已清空")
        except Exception as e:
            sentry_manager.sentry_hub.capture_exception(e)
            logger.error(f"【最近接收清理】清理最近接收运行失败: {e}")
            return
