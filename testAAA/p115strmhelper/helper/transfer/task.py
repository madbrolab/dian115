from threading import Lock, Timer
from typing import List, Optional, Callable

from app.log import logger

from ...schemas.transfer import TransferTask


class TransferTaskManager:
    """
    整理任务队列管理器
    """

    def __init__(
        self,
        batch_delay: float = 10.0,
        batch_max_size: int = 100,
        batch_callback: Optional[Callable[[List[TransferTask]], None]] = None,
    ):
        """
        初始化任务管理器

        :param batch_delay: 批量等待时间（秒），默认 10.0 秒
        :param batch_max_size: 单批次最大任务数，默认 100
        :param batch_callback: 批量处理回调函数，接收任务列表作为参数
        """
        self.batch_delay = batch_delay
        self.batch_max_size = batch_max_size
        self.batch_callback = batch_callback

        # 待处理任务队列
        self._pending_tasks: List[TransferTask] = []

        # 线程锁，保护共享资源
        self._lock = Lock()

        # 延迟定时器
        self._timer: Optional[Timer] = None

        # 是否正在处理批量任务
        self._processing = False

        logger.info(
            f"【整理接管】初始化完成，批量延迟: {batch_delay} 秒，最大批次: {batch_max_size}"
        )

    def add_task(self, task: TransferTask) -> None:
        """
        添加任务到待处理队列

        :param task: 整理任务
        """
        should_trigger_immediately = False

        with self._lock:
            # 检查是否达到最大批次大小
            if len(self._pending_tasks) >= self.batch_max_size:
                logger.warn(
                    f"【整理接管】待处理队列已满（{self.batch_max_size}），"
                    f"立即触发批量处理"
                )
                should_trigger_immediately = True

            # 添加任务到队列
            self._pending_tasks.append(task)
            logger.debug(
                f"【整理接管】任务已加入队列: {task.fileitem.name} -> {task.target_path}，"
                f"当前队列大小: {len(self._pending_tasks)}"
            )

            # 如果达到最大批次大小，立即触发批量处理
            if should_trigger_immediately:
                # 取消现有定时器
                if self._timer is not None:
                    self._timer.cancel()
                    self._timer = None
            else:
                # 重置延迟定时器
                self._reset_timer()

        # 在锁外触发批量处理
        if should_trigger_immediately:
            self._trigger_batch_process()

    def _reset_timer(self) -> None:
        """
        重置延迟定时器
        每次新任务到达时调用，延迟 batch_delay 秒后触发批量处理
        """
        # 取消现有定时器
        if self._timer is not None:
            self._timer.cancel()

        # 创建新的定时器
        self._timer = Timer(
            interval=self.batch_delay, function=self._trigger_batch_process
        )
        self._timer.daemon = True
        self._timer.start()

        logger.debug(
            f"【整理接管】延迟定时器已重置，将在 {self.batch_delay} 秒后触发批量处理"
        )

    def _trigger_batch_process(self) -> None:
        """
        触发批量处理
        从待处理队列中取出所有任务，调用批量处理回调
        """
        with self._lock:
            # 如果正在处理，跳过
            if self._processing:
                logger.debug("【整理接管】批量处理正在进行中，跳过本次触发")
                return

            # 如果没有待处理任务，直接返回
            if not self._pending_tasks:
                logger.debug("【整理接管】没有待处理任务，跳过批量处理")
                return

            # 取出所有待处理任务
            tasks_to_process = self._pending_tasks.copy()
            self._pending_tasks.clear()

            # 取消定时器
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

            # 标记为正在处理
            self._processing = True

        # 在锁外执行批量处理，避免阻塞
        try:
            task_count = len(tasks_to_process)
            logger.info(f"【整理接管】开始批量处理 {task_count} 个任务")

            if self.batch_callback:
                self.batch_callback(tasks_to_process)
            else:
                logger.warn("【整理接管】未设置批量处理回调函数，任务将被丢弃")

            logger.info(f"【整理接管】批量处理完成，共处理 {task_count} 个任务")
        except Exception as e:
            logger.error(f"【整理接管】批量处理异常: {e}", exc_info=True)
        finally:
            # 重置处理标志
            with self._lock:
                self._processing = False

                # 检查是否还有待处理的任务，如果有则立即触发下一批处理
                if self._pending_tasks:
                    pending_count = len(self._pending_tasks)
                    logger.info(
                        f"【整理接管】批量处理完成后，队列中仍有 {pending_count} 个待处理任务，"
                        f"立即触发下一批处理"
                    )
                    should_trigger_next = True
                else:
                    should_trigger_next = False

            if should_trigger_next:
                self._trigger_batch_process()

    def flush(self) -> None:
        """
        立即处理所有待处理任务（不等待延迟）
        用于插件关闭或手动触发时
        """
        logger.info("【整理接管】手动触发批量处理（flush）")
        self._trigger_batch_process()

    def get_pending_count(self) -> int:
        """
        获取待处理任务数量

        :return: 待处理任务数量
        """
        with self._lock:
            return len(self._pending_tasks)

    def shutdown(self) -> None:
        """
        关闭任务管理器
        取消定时器并处理剩余任务
        """
        logger.info("【整理接管】正在关闭...")

        with self._lock:
            # 取消定时器
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

        # 处理剩余任务
        if self.get_pending_count() > 0:
            logger.info(
                f"【整理接管】关闭时仍有 {self.get_pending_count()} 个待处理任务，"
                f"立即处理"
            )
            self.flush()

        logger.info("【整理接管】已关闭")
