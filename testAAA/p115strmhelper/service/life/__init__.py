from threading import Event
from time import time

from ...core.config import configer
from ...core.i18n import i18n
from ...core.message import post_message
from ...helper.life import MonitorLife
from ...utils.exception import NotifyExceptionFormatter
from ...utils.sentry import sentry_manager

from app.log import logger
from app.schemas import NotificationType


@sentry_manager.capture_plugin_exceptions
def monitor_life_thread_worker(
    monitor_life: MonitorLife,
    stop_event: Event,
):
    """
    生活事件监控线程工作函数

    :param monitor_life: 已初始化的 MonitorLife 对象
    :param stop_event: threading.Event 对象，用于接收停止信号
    """
    try:
        monitor_life.stop_event = stop_event

        logger.info("【监控生活事件】生活事件状态检查中...")
        if not monitor_life.check_status():
            logger.error("【监控生活事件】生活事件状态检查失败，无法启动监控")
            return

        logger.info("【监控生活事件】生活事件监控启动中...")

        # 获取拉取模式
        pull_mode = configer.monitor_life_first_pull_mode
        # latest 模式，从当前时间开始拉取数据
        from_time = time()
        from_id = 0
        # all 模式，拉取所有数据
        if pull_mode == "all":
            from_time = 0
            from_id = 0
        # last 模式，从上次停止时间拉取后续数据
        elif pull_mode == "last":
            data = configer.get_plugin_data("monitor_life_strm_files")
            if data:
                from_time = data.get("from_time")
                from_id = data.get("from_id")

        while True:
            if stop_event.is_set():
                logger.info("【监控生活事件】收到停止信号，退出上传事件监控")
                configer.save_plugin_data(
                    "monitor_life_strm_files",
                    {"from_time": from_time, "from_id": from_id},
                )
                break

            try:
                from_time, from_id = monitor_life.once_pull(
                    from_time=from_time, from_id=from_id
                )
            except Exception as e:
                logger.error(f"【监控生活事件】生活事件监控运行失败: {e}")
                if stop_event.is_set():
                    logger.info("【监控生活事件】收到停止信号，退出监控")
                    return
                if configer.notify:
                    post_message(
                        mtype=NotificationType.Plugin,
                        title=i18n.translate("monitor_life_error_title"),
                        text=(
                            f"\n{i18n.translate('monitor_life_error_text', error=NotifyExceptionFormatter.format_exception_for_notify(e))}\n"
                        ),
                    )
                logger.info("【监控生活事件】30s 后尝试重新启动生活事件监控")
                if stop_event.wait(timeout=30):
                    logger.info("【监控生活事件】等待期间收到停止信号，退出监控")
                    return

        logger.info("【监控生活事件】已退出生活事件监控")
    except Exception as e:
        logger.error(f"【监控生活事件】线程运行异常: {e}")
        if configer.notify:
            post_message(
                mtype=NotificationType.Plugin,
                title=i18n.translate("monitor_life_exit_title"),
                text=(
                    f"\n{i18n.translate('monitor_life_exit_text', error=NotifyExceptionFormatter.format_exception_for_notify(e))}\n"
                ),
            )
        raise
