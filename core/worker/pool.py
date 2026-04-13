import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from core.exceptions import QueueError
from core.queue import get_queue_manager
from core.task import Task, TaskStatus
from core.worker.worker import Worker, WorkerConfig


logger = logging.getLogger("wzml.worker")


@dataclass
class WorkerPoolStats:
    total_workers: int = 0
    active_workers: int = 0
    queued_tasks: int = 0
    running_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0


class WorkerPool:
    def __init__(
        self,
        max_workers: int = 10,
        worker_config: WorkerConfig | None = None,
    ):
        self._max_workers = max_workers
        self._worker_config = worker_config or WorkerConfig()
        self._workers: list[Worker] = []
        self._worker_tasks: list[asyncio.Task] = []
        self._running = False
        self._stats = WorkerPoolStats()
        self._queue_manager = get_queue_manager()

    async def start(self) -> None:
        if self._running:
            logger.warning("Worker pool already running")
            return

        self._running = True
        logger.info(f"Starting worker pool with {self._max_workers} workers")

        for i in range(self._max_workers):
            worker = Worker(
                worker_id=f"worker_{i}",
                config=self._worker_config,
            )
            self._workers.append(worker)

        for worker in self._workers:
            task = asyncio.create_task(self._worker_loop(worker))
            self._worker_tasks.append(task)

        self._stats.total_workers = self._max_workers
        logger.info(f"Worker pool started with {self._max_workers} workers")

    async def stop(self, timeout: float = 30.0) -> None:
        if not self._running:
            return

        self._running = False
        logger.info("Stopping worker pool...")

        for task in self._worker_tasks:
            task.cancel()

        if self._worker_tasks:
            await asyncio.wait(
                self._worker_tasks,
                timeout=timeout,
            )

        self._worker_tasks.clear()
        self._workers.clear()
        logger.info("Worker pool stopped")

    async def _worker_loop(self, worker: Worker) -> None:
        logger.info(f"Worker {worker.worker_id} started")

        while self._running:
            try:
                task = await self._queue_manager.dequeue()

                if task is None:
                    await asyncio.sleep(1)
                    continue

                logger.info(f"Worker {worker.worker_id} executing task {task.id}")
                self._stats.running_tasks += 1
                self._stats.active_workers += 1

                try:
                    from core.executor import execute_task

                    success = await execute_task(task)

                    if success:
                        self._stats.completed_tasks += 1
                        await self._queue_manager.complete(task)
                    else:
                        self._stats.failed_tasks += 1
                        await self._queue_manager.fail(
                            task, task.error or "Unknown error"
                        )

                except Exception as e:
                    logger.error(f"Worker error: {e}")
                    self._stats.failed_tasks += 1
                    await self._queue_manager.fail(task, str(e))

                finally:
                    self._stats.running_tasks -= 1
                    self._stats.active_workers -= 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(1)

        logger.info(f"Worker {worker.worker_id} stopped")

    async def submit(self, task: Task) -> bool:
        return await self._queue_manager.enqueue(task)

    async def get_stats(self) -> WorkerPoolStats:
        queue_stats = await self._queue_manager.get_stats()
        self._stats.queued_tasks = queue_stats.pending
        self._stats.running_tasks = queue_stats.running
        return self._stats

    async def scale(self, max_workers: int) -> None:
        if max_workers < self._max_workers:
            self._max_workers = max_workers
            excess = len(self._workers) - max_workers
            for _ in range(excess):
                worker = self._workers.pop()
                worker.stop()
            logger.info(f"Worker pool scaled down to {max_workers}")

        elif max_workers > self._max_workers:
            old_count = self._max_workers
            self._max_workers = max_workers

            for i in range(old_count, max_workers):
                worker = Worker(
                    worker_id=f"worker_{i}",
                    config=self._worker_config,
                )
                self._workers.append(worker)
                task = asyncio.create_task(self._worker_loop(worker))
                self._worker_tasks.append(task)

            logger.info(f"Worker pool scaled up to {max_workers}")

        self._stats.total_workers = max_workers


_worker_pool: WorkerPool | None = None


def get_worker_pool() -> WorkerPool:
    global _worker_pool
    if _worker_pool is None:
        _worker_pool = WorkerPool()
    return _worker_pool


async def start_worker_pool(max_workers: int = 10) -> None:
    pool = get_worker_pool()
    await pool.start()


async def stop_worker_pool() -> None:
    if _worker_pool:
        await _worker_pool.stop()


async def submit_task(task: Task) -> bool:
    return await get_worker_pool().submit(task)
