from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator

from core.exceptions import StateNotFoundError
from core.task import Task, TaskStatus


@dataclass
class StateData:
    task_id: str
    data: dict = field(default_factory=dict)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class StateManager:
    _storage: dict[str, StateData] = field(default_factory=dict, repr=False)

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get(self, task_id: str) -> StateData:
        state = self._storage.get(task_id)
        if not state:
            raise StateNotFoundError(task_id)
        return state

    async def set(self, task_id: str, data: dict) -> None:
        self._storage[task_id] = StateData(
            task_id=task_id, data=data, updated_at=datetime.now()
        )

    async def update(self, task_id: str, data: dict) -> None:
        existing = self._storage.get(task_id)
        if existing:
            existing.data.update(data)
            existing.updated_at = datetime.now()
        else:
            await self.set(task_id, data)

    async def delete(self, task_id: str) -> None:
        if task_id in self._storage:
            del self._storage[task_id]

    async def exists(self, task_id: str) -> bool:
        return task_id in self._storage

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        user_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> AsyncIterator[str]:
        task_ids = list(self._storage.keys())
        task_ids.sort(key=lambda t: self._storage[t].updated_at, reverse=True)

        count = 0
        for task_id in task_ids:
            if offset > 0:
                offset -= 1
                continue
            if count >= limit:
                break
            count += 1
            yield task_id

    async def clear(self) -> None:
        self._storage.clear()

    async def count(self) -> int:
        return len(self._storage)


_state_manager: StateManager | None = None


def get_state_manager() -> StateManager:
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


async def initialize_state() -> None:
    manager = get_state_manager()
    await manager.initialize()


async def close_state() -> None:
    if _state_manager:
        await _state_manager.close()
