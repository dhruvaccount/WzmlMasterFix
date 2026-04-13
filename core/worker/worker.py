import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime


logger = logging.getLogger("wzml.worker")


@dataclass
class WorkerConfig:
    timeout: int = 3600
    idle_timeout: int = 300
    max_retries: int = 3
    heartbeat_interval: int = 30


class Worker:
    def __init__(
        self,
        worker_id: str,
        config: WorkerConfig | None = None,
    ):
        self.worker_id = worker_id
        self.config = config or WorkerConfig()
        self._current_task = None
        self._running = False
        self._started_at = None
        self._completed_tasks = 0
        self._failed_tasks = 0

    def __repr__(self) -> str:
        return f"Worker({self.worker_id})"

    @property
    def is_idle(self) -> bool:
        return self._current_task is None

    @property
    def current_task(self):
        return self._current_task

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    @property
    def completed_tasks(self) -> int:
        return self._completed_tasks

    @property
    def failed_tasks(self) -> int:
        return self._failed_tasks

    async def execute(self, task) -> bool:
        if self._current_task is not None:
            raise RuntimeError("Worker already executing a task")

        self._current_task = task
        self._started_at = datetime.now()

        try:
            from core.executor import execute_task

            result = await asyncio.wait_for(
                execute_task(task),
                timeout=self.config.timeout,
            )

            if result:
                self._completed_tasks += 1
            else:
                self._failed_tasks += 1

            return result

        except asyncio.TimeoutError:
            logger.error(f"Task {task.id} timed out")
            self._failed_tasks += 1
            return False

        except Exception as e:
            logger.error(f"Task {task.id} failed: {e}")
            self._failed_tasks += 1
            return False

        finally:
            self._current_task = None

    async def heartbeat(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "is_idle": self.is_idle,
            "current_task": self._current_task.id if self._current_task else None,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "completed_tasks": self._completed_tasks,
            "failed_tasks": self._failed_tasks,
        }

    def stop(self) -> None:
        self._running = False


def create_worker(worker_id: str, config: WorkerConfig | None = None) -> Worker:
    return Worker(worker_id, config)
