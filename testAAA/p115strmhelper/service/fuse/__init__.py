from subprocess import CalledProcessError, TimeoutExpired, run
from platform import system
from threading import Lock, Thread
from typing import Optional
from pathlib import Path

try:
    from os import getuid, getgid
except ImportError:

    def getuid() -> int:
        return 0

    def getgid() -> int:
        return 0


from p115client import P115Client

from ...core.config import configer
from ...helper.fuse import P115FuseOperations
from ...utils.sentry import sentry_manager

from app.log import logger


def _get_fuse_error_message(error_code: int) -> str:
    """
    根据错误代码获取 FUSE 错误信息

    :param error_code: 错误代码
    :return: 错误信息
    """
    error_messages = {
        1: "操作不允许 (EPERM) - 权限不足，可能需要 root 权限或 SYS_ADMIN 能力",
        2: "文件或目录不存在 (ENOENT) - 挂载点路径不存在",
        3: "没有这样的进程 (ESRCH) - 或无效的挂载选项",
        4: "系统调用被中断 (EINTR) - 挂载过程被中断",
        5: "输入/输出错误 (EIO) - I/O 操作失败",
        13: "权限被拒绝 (EACCES) - 挂载点权限不足",
        16: "设备或资源忙 (EBUSY) - 挂载点已被占用",
        20: "不是目录 (ENOTDIR) - 挂载点路径不是目录",
        22: "无效参数 (EINVAL) - 挂载参数无效或选项不支持",
        95: "操作不支持 (EOPNOTSUPP) - FUSE 未正确安装或内核不支持",
    }
    return error_messages.get(error_code, f"未知错误 (错误代码: {error_code})")


@sentry_manager.capture_plugin_exceptions
def fuse_thread_worker(
    fuse_operations: P115FuseOperations,
    mountpoint: str,
):
    """
    FUSE 文件系统线程工作函数

    :param fuse_operations: 已初始化的 P115FuseOperations 对象
    :param mountpoint: 挂载点路径
    """
    try:
        logger.info(f"【FUSE】正在挂载到: {mountpoint}")
        fuse_operations.run_forever(
            mountpoint=mountpoint,
            foreground=True,
            nothreads=False,
            allow_other=True,  # Docker 容器内非 root 挂载
            noauto_cache=True,
        )
        logger.info("【FUSE】FUSE 文件系统已卸载")
    except SystemExit:
        logger.info("【FUSE】收到退出信号")
    except RuntimeError as e:
        error_str = str(e)
        try:
            error_code = int(error_str)
            error_msg = _get_fuse_error_message(error_code)
            logger.error(f"【FUSE】挂载失败: {error_msg}")
        except ValueError:
            logger.error(f"【FUSE】运行失败: {e}", exc_info=True)
        raise
    except OSError as e:
        error_code = e.errno if hasattr(e, "errno") else None
        if error_code:
            error_msg = _get_fuse_error_message(error_code)
            logger.error(f"【FUSE】系统错误: {error_msg} (errno: {error_code})")
        else:
            logger.error(f"【FUSE】系统错误: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"【FUSE】运行失败: {e}", exc_info=True)
        raise


@sentry_manager.capture_all_class_exceptions
class FuseManager:
    """
    FUSE 文件系统管理器
    """

    def __init__(self, client: Optional[P115Client] = None):
        self.client = client
        self.fuse_thread: Optional[Thread] = None
        self.fuse_lock = Lock()
        self.fuse_operations: Optional[P115FuseOperations] = None
        self.fuse_mountpoint: Optional[str] = None

    def start_fuse(self, mountpoint: Optional[str] = None, readdir_ttl: float = 60):
        """
        启动 FUSE 文件系统

        :param mountpoint: 挂载点路径，如果为 None 则使用配置中的路径
        :param readdir_ttl: 目录读取缓存 TTL（秒）

        :return: 是否启动成功
        """
        with self.fuse_lock:
            return self._start_fuse_internal(mountpoint, readdir_ttl)

    def stop_fuse(self):
        """
        停止 FUSE 文件系统
        """
        with self.fuse_lock:
            self._stop_fuse_internal()

    def _start_fuse_internal(
        self, mountpoint: Optional[str] = None, readdir_ttl: float = 60
    ) -> bool:
        """
        启动 FUSE 文件系统线程
        """
        if not mountpoint:
            if not configer.fuse_enabled or not configer.fuse_mountpoint:
                return False
            mountpoint = configer.fuse_mountpoint

        if not self.client:
            logger.error("【FUSE】115客户端未初始化，无法启动 FUSE")
            return False

        if self.fuse_thread and self.fuse_thread.is_alive():
            logger.info("【FUSE】检测到已有线程在运行，停止旧线程中...")
            self._stop_fuse_internal()

        mountpoint_path = Path(mountpoint)
        if not mountpoint_path.exists():
            logger.error(f"【FUSE】挂载点路径不存在: {mountpoint}")
            return False
        if not mountpoint_path.is_dir():
            logger.error(f"【FUSE】挂载点路径不是目录: {mountpoint}")
            return False

        try:
            if system() == "Linux":
                result = run(
                    ["mountpoint", "-q", mountpoint],
                    capture_output=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    if self._is_fuse_mount(mountpoint):
                        logger.info(
                            f"【FUSE】检测到 FUSE 挂载点已被占用，先卸载: {mountpoint}"
                        )
                        try:
                            self._unmount_fuse(mountpoint)
                        except Exception as e:
                            logger.warning(
                                f"【FUSE】常规卸载失败，尝试懒卸载: {mountpoint} - {e}"
                            )
                            try:
                                self._unmount_fuse_lazy(mountpoint)
                            except Exception as e2:
                                logger.warning(
                                    f"【FUSE】懒卸载也失败，将尝试强制挂载（可能会覆盖现有挂载）: {mountpoint} - {e2}"
                                )
                    else:
                        logger.debug(
                            f"【FUSE】挂载点是其他类型的挂载（非FUSE），跳过卸载: {mountpoint}"
                        )
        except (TimeoutExpired, FileNotFoundError):
            pass

        try:
            uid = configer.fuse_uid
            gid = configer.fuse_gid
            if uid is None or gid is None:
                try:
                    current_uid = getuid()
                    current_gid = getgid()
                    uid = uid if uid is not None else current_uid
                    gid = gid if gid is not None else current_gid
                except (AttributeError, OSError):
                    uid = uid if uid is not None else 0
                    gid = gid if gid is not None else 0

            self.fuse_operations = P115FuseOperations(
                client=self.client,
                readdir_ttl=readdir_ttl or configer.fuse_readdir_ttl,
                uid=uid,
                gid=gid,
            )

            self.fuse_thread = Thread(
                target=fuse_thread_worker,
                args=(self.fuse_operations, mountpoint),
                name="P115StrmHelper-FUSE",
                daemon=True,
            )
            self.fuse_mountpoint = mountpoint
            self.fuse_thread.start()
            logger.info(f"【FUSE】FUSE 文件系统已启动，挂载点: {mountpoint}")
            return True
        except Exception as e:
            logger.error(f"【FUSE】启动失败: {e}", exc_info=True)
            return False

    def _stop_fuse_internal(self):
        """
        停止 FUSE 文件系统线程
        """
        if not self.fuse_thread or not self.fuse_thread.is_alive():
            self.fuse_thread = None
            self.fuse_operations = None
            self.fuse_mountpoint = None
            return

        logger.info("【FUSE】停止 FUSE 文件系统")

        if self.fuse_mountpoint:
            try:
                self._unmount_fuse(self.fuse_mountpoint)
            except Exception as e:
                logger.warning(
                    f"【FUSE】常规卸载失败，尝试懒卸载: {self.fuse_mountpoint} - {e}"
                )
                try:
                    self._unmount_fuse_lazy(self.fuse_mountpoint)
                except Exception as e2:
                    logger.warning(
                        f"【FUSE】懒卸载也失败: {self.fuse_mountpoint} - {e2}"
                    )

        self.fuse_thread.join(timeout=10)
        if self.fuse_thread.is_alive():
            logger.warning("【FUSE】线程未在预期时间内结束")
        else:
            logger.info("【FUSE】线程已正常退出")

        self.fuse_thread = None
        self.fuse_operations = None
        self.fuse_mountpoint = None

    @staticmethod
    def _is_fuse_mount(mountpoint: str) -> bool:
        """
        检查挂载点是否是 FUSE 类型的挂载

        :param mountpoint: 挂载点路径

        :return: 如果是 FUSE 挂载返回 True，否则返回 False
        """
        try:
            if system() == "Linux":
                result = run(
                    ["findmnt", "-n", "-o", "FSTYPE", mountpoint],
                    capture_output=True,
                    timeout=2,
                    text=True,
                )
                if result.returncode == 0:
                    fstype = result.stdout.strip()
                    return fstype.startswith("fuse") or fstype == "fuseblk"
            return False
        except (TimeoutExpired, FileNotFoundError):
            try:
                with open("/proc/mounts", "r") as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 3:
                            mount_path = parts[1]
                            fstype = parts[2]
                            if Path(mount_path).resolve() == Path(mountpoint).resolve():
                                return fstype.startswith("fuse") or fstype == "fuseblk"
            except (OSError, FileNotFoundError):
                pass
            return False

    @staticmethod
    def _unmount_fuse(mountpoint: str):
        """
        卸载 FUSE 文件系统

        :param mountpoint: 挂载点路径
        """
        sys_name = system()
        if sys_name == "Linux":
            cmd = ["fusermount", "-u", mountpoint]
        else:
            cmd = ["umount", mountpoint]

        try:
            run(cmd, check=True, timeout=5, capture_output=True)
            logger.info(f"【FUSE】成功卸载挂载点: {mountpoint}")
        except CalledProcessError as e:
            logger.error(f"【FUSE】卸载命令执行失败: {e}")
            raise
        except FileNotFoundError:
            logger.error("【FUSE】未找到卸载命令，请确保已安装 FUSE")
            raise

    @staticmethod
    def _unmount_fuse_lazy(mountpoint: str):
        """
        懒卸载 FUSE 文件系统

        :param mountpoint: 挂载点路径
        """
        sys_name = system()
        if sys_name == "Linux":
            cmd = ["fusermount", "-uz", mountpoint]
        else:
            cmd = ["umount", "-l", mountpoint]

        try:
            run(cmd, check=True, timeout=5, capture_output=True)
            logger.info(f"【FUSE】成功懒卸载挂载点: {mountpoint}")
        except CalledProcessError as e:
            logger.error(f"【FUSE】懒卸载命令执行失败: {e}")
            raise
        except FileNotFoundError:
            logger.error("【FUSE】未找到卸载命令，请确保已安装 FUSE")
            raise
