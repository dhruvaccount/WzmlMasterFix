import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from core.exceptions import QueueFullError
from core.queue.priority_queue import PriorityQueue
from core.task import Task, TaskStatus, PRIORITY_ORDER


logger = logging.getLogger("wzml.queue")


@dataclass
class QueueStats:
    pending: int = 0
    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0


class QueueManager:
    def __init__(
        self,
        max_size: int = 100,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        self._queue = PriorityQueue(max_size)
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._running: dict[str, Task] = {}
        self._stats = QueueStats()

    async def enqueue(self, task: Task) -> bool:
        task.queue()

        if not await self._queue.put(task):
            task.status = TaskStatus.PENDING
            raise QueueFullError(self._queue._max_size)

        logger.info(f"Task {task.id} enqueued with priority {task.config.priority}")
        self._stats.queued += 1
        return True

    async def dequeue(self) -> Task | None:
        task = await self._queue.get()
        if task:
            task.start()
            self._running[task.id] = task
            self._stats.queued -= 1
            self._stats.running += 1
            logger.info(f"Task {task.id} dequeued")
        return task

    async def complete(self, task: Task) -> None:
        if task.id in self._running:
            del self._running[task.id]
        self._stats.running -= 1
        self._stats.completed += 1

    async def fail(self, task: Task, error: str) -> None:
        if task.id in self._running:
            del self._running[task.id]
        self._stats.running -= 1

        if task.can_retry:
            delay = min(self._base_delay * (2**task.retry_count), self._max_delay)
            logger.info(
                f"Task {task.id} failed, scheduling retry #{task.retry_count + 1} in {delay}s"
            )
            asyncio.create_task(self._schedule_retry(task, delay))
        else:
            task.fail(error)
            self._stats.failed += 1
            logger.error(f"Task {task.id} failed: {error}")

    async def _schedule_retry(self, task: Task, delay: float) -> None:
        await asyncio.sleep(delay)
        task.retry()
        await self.enqueue(task)

    async def cancel(self, task_id: str) -> bool:
        if await self._queue.remove(task_id):
            self._stats.queued -= 1
            return True

        if task_id in self._running:
            task = self._running[task_id]
            task.cancel()
            del self._running[task_id]
            self._stats.running -= 1
            return True

        return False

    async def get_stats(self) -> QueueStats:
        self._stats.pending = await self._queue.size()
        self._stats.running = len(self._running)
        return self._stats

    async def list_queued(self) -> list[Task]:
        return await self._queue.list_tasks()

    async def list_running(self) -> list[Task]:
        return list(self._running.values())


_queue_manager: QueueManager | None = None


def get_queue_manager() -> QueueManager:
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = QueueManager()
    return _queue_manager


async def enqueue_task(task: Task) -> bool:
    return await get_queue_manager().enqueue(task)


async def dequeue_task() -> Task | None:
    return await get_queue_manager().dequeue()


async def get_queue_stats() -> QueueStats:
    return await get_queue_manager().get_stats()
