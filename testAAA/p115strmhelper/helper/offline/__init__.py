import time
from typing import List
from pathlib import Path
from datetime import datetime, timezone

from p115center import P115Center, OfflineInfo
from p115client import P115Client
from p115client.tool.offline import offline_iter
from p115client.tool.attr import get_attr

from app.log import logger

from ...core.config import configer
from ...core.p115 import get_pid_by_path
from ...helper.life import MonitorLife
from ...schemas.offline import OfflineTaskItem
from ...utils.string import StringUtils
from ...utils.sentry import sentry_manager


@sentry_manager.capture_all_class_exceptions
class OfflineDownloadHelper:
    """
    离线下载
    """

    def __init__(self, client: P115Client, monitorlife: MonitorLife):
        self.client = client
        self.monitorlife = monitorlife
        self.transfer_list: List = []

        self.offline_list_cache = {"data": None, "timestamp": 0}

    @staticmethod
    def build_offline_urls_payload(urls, savepath=None, wp_path_id=None):
        """
        构建添加下载列表参数
        """
        payload = {}
        for i, url in enumerate(urls):
            payload[f"url[{i}]"] = url.strip()

        if savepath:
            payload["savepath"] = savepath
        if wp_path_id:
            payload["wp_path_id"] = wp_path_id

        return payload

    def __remove_transfer_list_by_hash(self, target_hash):
        """
        通过 hash 删除指定字典
        """
        i = 0
        while i < len(self.transfer_list):
            if self.transfer_list[i]["hash"] == target_hash:
                target_path = self.transfer_list[i]["path"]
                del self.transfer_list[i]
                return target_path
            i += 1
        return None

    def __exists_in_transfer_list(self, target_hash):
        """
        判断 hash 是否在 transfer_list 中
        """
        if any(d.get("hash") == target_hash for d in self.transfer_list):
            return True
        return False

    def __add_transfer_task(self, item):
        """
        添加整理任务
        """
        try:
            if not item[1].get("data", None):
                if item[1].get("count", None):
                    logger.error(
                        f"【离线下载】{item[0]} 下载失败，无法添加到网盘整理队列"
                    )
                    self.__remove_transfer_list_by_hash(item[0])
                else:
                    item[1]["count"] = 1
                    logger.warn(f"【离线下载】{item[0]} 下载任务二次检测")
                return
            parent_path = self.__remove_transfer_list_by_hash(item[0])
            logger.info(f"【离线下载】{item[0]} 下载完成，添加到网盘整理队列")
            data = get_attr(
                self.client,
                id=int(item[1].get("data").get("delete_file_id")),
                **configer.get_ios_ua_app(app=False),
            )
            event = {
                "file_id": int(data["id"]),
                "file_category": 0 if data["is_dir"] else 1,
                "parent_id": int(data["parent_id"]),
                "file_size": int(data["size"]),
                "pick_code": data["pickcode"],
                "update_time": data["user_utime"],
            }
            file_path = Path(parent_path) / str(item[1].get("data").get("name"))
            rmt_mediaext = [
                f".{ext.strip()}"
                for ext in configer.get_config("user_rmt_mediaext")
                .replace("，", ",")
                .split(",")
            ]
            # 直接传入网盘整理
            self.monitorlife.media_transfer(
                event=event,
                file_path=file_path,
                rmt_mediaext=rmt_mediaext,
            )
        except Exception as e:
            logger.error(f"【离线下载】{item[0]} 无法添加到网盘整理队列: {e}")

    def add_urls(self, url_list: List, cid: int):
        """
        添加一组任务
        """
        payload = self.build_offline_urls_payload(urls=url_list, wp_path_id=cid)
        return self.client.offline_add_urls(
            payload, **configer.get_ios_ua_app(app=False)
        )

    def get_tasks(self):
        """
        获取当前所有任务
        """
        return offline_iter(
            self.client, cooldown=2, type="web", **configer.get_ios_ua_app(app=False)
        )

    def get_tasks_status(self, info_hash: List):
        """
        获取一组任务的状态和信息
        """
        for item in self.get_tasks():
            item_hash = item.get("info_hash", None)
            if item_hash in info_hash:
                # 0 进行中、1 下载失败、2 下载成功、3 重试中
                if int(item.get("status", -1)) == 2:
                    yield [item_hash, {"status": True, "data": item}]
                elif int(item.get("status", -1)) == 1:
                    yield [item_hash, {"status": True, "data": ""}]
                else:
                    yield [item_hash, {"status": False, "data": item}]

    def add_urls_to_transfer(self, url_list: List) -> bool:
        """
        添加一组任务并进行网盘整理
        """
        try:
            # 寻找离线下载目录中可运行网盘整理的目录，如果无则调用 add_urls_to_path 函数
            parent_path = None
            for path in configer.pan_transfer_paths.split("\n"):
                if not path:
                    continue
                if path in configer.offline_download_paths:
                    parent_path = path
                break
            if not parent_path:
                return self.add_urls_to_path(
                    url_list, configer.offline_download_paths[0]
                )

            parent_id = get_pid_by_path(
                client=self.client,
                path=parent_path,
                mkdir=True,
                update_cache=True,
                by_cache=True,
            )
            logger.debug(f"【离线下载】获取到下载目录 {parent_path} ID：{parent_id}")

            resp = self.add_urls(url_list=url_list, cid=parent_id)
            if not resp.get("state", None):
                logger.error(f"【离线下载】下载任务添加失败: {url_list} {resp}")
                return False

            # 获取所有任务的 hash，添加到待整理列表中
            for item in resp.get("data", {}).get("result"):
                self.transfer_list.append(
                    {"hash": str(item.get("info_hash")), "path": str(parent_path)}
                )

            for url in url_list:
                self.post_offline_info(url)
            logger.debug(f"【离线下载】下载任务添加完成: {url_list}")
            return True
        except Exception as e:
            logger.error(f"【离线下载】未知错误：{e}")
            return False

    def add_urls_to_path(self, url_list: List, path: str) -> bool:
        """
        添加一组任务下载到指定路径
        """
        try:
            parent_id = get_pid_by_path(
                client=self.client,
                path=path,
                mkdir=True,
                update_cache=True,
                by_cache=True,
            )
            logger.debug(f"【离线下载】获取到下载目录 {path} ID：{parent_id}")

            resp = self.add_urls(url_list=url_list, cid=parent_id)
            if not resp.get("state", None):
                logger.error(f"【离线下载】下载任务添加失败: {url_list} {resp}")
                return False

            for url in url_list:
                self.post_offline_info(url)
            logger.debug(f"【离线下载】下载任务添加完成: {url_list}")
            return True
        except Exception as e:
            logger.error(f"【离线下载】未知错误：{e}")
            return False

    def pull_status_to_task(self):
        """
        等待下载完成运行指定任务
        """
        if not self.transfer_list:
            return
        # 获取待整理的 hash 列表
        hash_list = list(map(lambda x: x["hash"], self.transfer_list))
        for item in self.get_tasks_status(hash_list):
            # 判断是否是中止状态
            if item[1].get("status"):
                # 判断是否属于整理队列
                if self.__exists_in_transfer_list(item[0]):
                    self.__add_transfer_task(item)
        if self.transfer_list:
            logger.info(f"【离线下载】等待任务下载完成：{hash_list}")

    def get_cached_data(self):
        """
        获取缓存离线下载列表
        """
        status_mapping = {0: "下载中", 1: "下载失败", 2: "已完成", 3: "重试中"}

        now = time.time()
        if (
            self.offline_list_cache["data"] is None
            or (now - self.offline_list_cache["timestamp"]) > 120
        ):
            raw_tasks = self.get_tasks()
            formatted_tasks = []

            for task in raw_tasks:
                task_model = OfflineTaskItem(
                    info_hash=task.get("info_hash", ""),
                    name=task.get("name", ""),
                    size=task.get("size", 0),
                    size_text=StringUtils.format_size(task.get("size", 0)),
                    status=task.get("status", 0),
                    status_text=status_mapping.get(task.get("status", 4), "未知状态"),
                    percent=task.get("percentDone", 0.0),
                    add_time=task.get("add_time", 0),
                )
                formatted_tasks.append(task_model)

            self.offline_list_cache = {"data": formatted_tasks, "timestamp": now}

        return self.offline_list_cache["data"]

    @staticmethod
    def post_offline_info(url: str):
        """
        上传离线下载信息
        """
        if not configer.get_config("upload_offline_info"):
            return

        try:
            client = P115Center(configer.get_config("MACHINE_ID"))
            resp = client.upload_offline_info(
                OfflineInfo(
                    url=url,
                    postime=datetime.now(timezone.utc),
                )
            )
            logger.info(f"【离线下载】离线下载信息报告服务器成功: {resp.model_dump()}")
        except Exception as e:
            logger.debug(f"【离线下载】离线下载报告服务器失败: {e}")
