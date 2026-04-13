import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from heapq import heappop, heappush
from typing import Any

from core.task import Task, TaskPriority, PRIORITY_ORDER


@dataclass
class QueueItem:
    priority: int
    task: Task
    added_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0

    def __lt__(self, other: "QueueItem") -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.added_at < other.added_at


class PriorityQueue:
    def __init__(self, max_size: int = 0):
        self._heap: list[QueueItem] = []
        self._max_size = max_size
        self._lock = asyncio.Lock()

    async def put(self, task: Task) -> bool:
        async with self._lock:
            if self._max_size > 0 and len(self._heap) >= self._max_size:
                return False

            priority = PRIORITY_ORDER.get(task.config.priority, 2)

            item = QueueItem(priority=priority, task=task)
            heappush(self._heap, item)
            return True

    async def get(self) -> Task | None:
        async with self._lock:
            if not self._heap:
                return None
            item = heappop(self._heap)
            return item.task

    async def get_nowait(self) -> Task:
        async with self._lock:
            if not self._heap:
                raise QueueEmpty()
            item = heappop(self._heap)
            return item.task

    async def peek(self) -> Task | None:
        async with self._lock:
            if not self._heap:
                return None
            return self._heap[0].task

    async def remove(self, task_id: str) -> bool:
        async with self._lock:
            for i, item in enumerate(self._heap):
                if item.task.id == task_id:
                    del self._heap[i]
                    self._heap = self._heap[:]
                    return True
            return False

    async def size(self) -> int:
        async with self._lock:
            return len(self._heap)

    async def is_empty(self) -> bool:
        async with self._lock:
            return len(self._heap) == 0

    async def is_full(self) -> bool:
        async with self._lock:
            return self._max_size > 0 and len(self._heap) >= self._max_size

    async def clear(self) -> None:
        async with self._lock:
            self._heap.clear()

    async def list_tasks(self) -> list[Task]:
        async with self._lock:
            return [item.task for item in sorted(self._heap)]


class QueueEmpty(Exception):
    pass
