from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from core.events import event_bus
from core.exceptions import (
    TaskNotFoundError,
    TaskNotPendingError,
    TaskError,
)


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


PRIORITY_ORDER: dict[TaskPriority, int] = {
    TaskPriority.CRITICAL: 0,
    TaskPriority.HIGH: 1,
    TaskPriority.NORMAL: 2,
    TaskPriority.LOW: 3,
}


@dataclass
class TaskConfig:
    source: str
    destination: str
    pipeline_id: str
    user_id: int
    priority: TaskPriority = TaskPriority.NORMAL
    metadata: dict = field(default_factory=dict)
    max_retries: int = 3
    timeout: int = 3600
    options: dict = field(default_factory=dict)


@dataclass
class TaskProgress:
    stage: str = ""
    plugin: str = ""
    progress: float = 0.0
    speed: float = 0.0
    eta: int = 0
    downloaded: int = 0
    uploaded: int = 0
    total: int = 0


@dataclass
class Task:
    id: str
    config: TaskConfig
    status: TaskStatus = TaskStatus.PENDING
    progress: TaskProgress = field(default_factory=TaskProgress)
    current_stage: int = 0
    error: str | None = None
    retry_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.config.source,
            "destination": self.config.destination,
            "pipeline_id": self.config.pipeline_id,
            "user_id": self.config.user_id,
            "status": self.status,
            "priority": self.config.priority,
            "progress": {
                "stage": self.progress.stage,
                "plugin": self.progress.plugin,
                "progress": self.progress.progress,
                "speed": self.progress.speed,
                "eta": self.progress.eta,
                "downloaded": self.progress.downloaded,
                "uploaded": self.progress.uploaded,
                "total": self.progress.total,
            },
            "current_stage": self.current_stage,
            "error": self.error,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
        }

    @property
    def is_active(self) -> bool:
        return self.status in (
            TaskStatus.PENDING,
            TaskStatus.QUEUED,
            TaskStatus.RUNNING,
        )

    @property
    def can_retry(self) -> bool:
        return (
            self.status in (TaskStatus.FAILED, TaskStatus.CANCELLED)
            and self.retry_count < self.config.max_retries
        )

    @property
    def can_cancel(self) -> bool:
        return self.is_active

    def queue(self) -> None:
        if self.status != TaskStatus.PENDING:
            raise TaskNotPendingError(self.id, self.status, [TaskStatus.PENDING])
        self.status = TaskStatus.QUEUED
        self.queued_at = datetime.now()
        import asyncio
        asyncio.create_task(event_bus.publish("task_queued", self.to_dict()))

    def start(self) -> None:
        if self.status != TaskStatus.QUEUED:
            raise TaskNotPendingError(self.id, self.status, [TaskStatus.QUEUED])
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()
        import asyncio
        asyncio.create_task(event_bus.publish("task_started", self.to_dict()))

    def complete(self) -> None:
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now()
        self.progress.stage = "completed"
        self.progress.progress = 100.0
        import asyncio
        asyncio.create_task(event_bus.publish("task_completed", self.to_dict()))

    def fail(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()
        self.progress.stage = "failed"
        import asyncio
        asyncio.create_task(event_bus.publish("task_failed", self.to_dict()))

    def cancel(self) -> None:
        if not self.can_cancel:
            raise TaskError(f"Cannot cancel task in {self.status} state")
        self.status = TaskStatus.CANCELLED
        self.completed_at = datetime.now()
        self.progress.stage = "cancelled"

    def retry(self) -> None:
        if not self.can_retry:
            raise TaskError(
                f"Cannot retry: status={self.status}, retries={self.retry_count}/{self.config.max_retries}"
            )
        self.retry_count += 1
        self.status = TaskStatus.PENDING
        self.error = None
        self.current_stage = 0
        self.progress = TaskProgress()


_task_store: dict[str, Task] = {}
_mongodb_enabled = False


def enable_mongodb():
    global _mongodb_enabled
    _mongodb_enabled = True


def is_mongodb_enabled() -> bool:
    return _mongodb_enabled


def generate_task_id() -> str:
    import uuid

    return f"task_{uuid.uuid4().hex[:12]}"


async def create_task(
    source: str,
    pipeline_id: str,
    user_id: int,
    destination: str = "",
    priority: TaskPriority = TaskPriority.NORMAL,
    metadata: dict | None = None,
    max_retries: int = 3,
    timeout: int = 3600,
    options: dict | None = None,
) -> Task:
    task_id = generate_task_id()

    config = TaskConfig(
        source=source,
        destination=destination or "",
        pipeline_id=pipeline_id,
        user_id=user_id,
        priority=priority,
        metadata=metadata or {},
        max_retries=max_retries,
        timeout=timeout,
        options=options or {},
    )

    task = Task(id=task_id, config=config)
    _task_store[task_id] = task

    if _mongodb_enabled:
        try:
            from core.mongodb import get_mongodb_client

            mongo = get_mongodb_client()
            if mongo.is_connected:
                await mongo.save_task(task_id, task.to_dict())
        except Exception:
            pass

    return task


async def get_task(task_id: str) -> Task:
    task = _task_store.get(task_id)
    if not task:
        if _mongodb_enabled:
            try:
                from db.mongodb import get_mongodb_client

                mongo = get_mongodb_client()
                doc = await mongo.get_task(task_id)
                if doc:
                    task = _task_store.get(task_id)
            except Exception:
                pass
        if not task:
            raise TaskNotFoundError(task_id)
    return task


async def get_tasks(
    user_id: int | None = None,
    status: TaskStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Task]:
    tasks = list(_task_store.values())

    if user_id is not None:
        tasks = [t for t in tasks if t.config.user_id == user_id]

    if status is not None:
        tasks = [t for t in tasks if t.status == status]

    tasks.sort(key=lambda t: t.created_at, reverse=True)

    return tasks[offset : offset + limit]


async def cancel_task(task_id: str) -> Task:
    task = await get_task(task_id)
    task.cancel()
    return task


async def retry_task(task_id: str) -> Task:
    task = await get_task(task_id)
    task.retry()
    return task


async def update_task_progress(
    task_id: str,
    stage: str,
    plugin: str,
    progress: float,
    speed: float = 0.0,
    eta: int = 0,
    downloaded: int = 0,
    uploaded: int = 0,
    total: int = 0,
) -> Task:
    task = await get_task(task_id)
    task.progress.stage = stage
    task.progress.plugin = plugin
    task.progress.progress = progress
    task.progress.speed = speed
    task.progress.eta = eta
    task.progress.downloaded = downloaded
    task.progress.uploaded = uploaded
    task.progress.total = total
    
    import asyncio
    asyncio.create_task(event_bus.publish("task_progress", task.to_dict()))
    
    return task
