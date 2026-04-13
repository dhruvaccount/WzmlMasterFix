class WZMLError(Exception):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


class TaskError(WZMLError):
    pass


class TaskNotFoundError(TaskError):
    def __init__(self, task_id: str):
        super().__init__(f"Task {task_id} not found", {"task_id": task_id})


class TaskNotPendingError(TaskError):
    def __init__(self, task_id: str, current_status: str, allowed_statuses: list[str]):
        super().__init__(
            f"Task {task_id} is {current_status}, expected one of {allowed_statuses}",
            {
                "task_id": task_id,
                "current_status": current_status,
                "allowed_statuses": allowed_statuses,
            },
        )


class TaskCancelledError(TaskError):
    def __init__(self, task_id: str):
        super().__init__(f"Task {task_id} has been cancelled", {"task_id": task_id})


class PipelineError(WZMLError):
    pass


class PipelineNotFoundError(PipelineError):
    def __init__(self, pipeline_id: str):
        super().__init__(
            f"Pipeline {pipeline_id} not found", {"pipeline_id": pipeline_id}
        )


class PipelineValidationError(PipelineError):
    def __init__(self, pipeline_id: str, errors: list[str]):
        super().__init__(
            f"Pipeline {pipeline_id} validation failed",
            {"pipeline_id": pipeline_id, "errors": errors},
        )


class PluginError(WZMLError):
    pass


class PluginNotFoundError(PluginError):
    def __init__(self, plugin_name: str):
        super().__init__(
            f"Plugin {plugin_name} not found", {"plugin_name": plugin_name}
        )


class PluginLoadError(PluginError):
    def __init__(self, plugin_name: str, reason: str):
        super().__init__(
            f"Plugin {plugin_name} failed to load: {reason}",
            {"plugin_name": plugin_name, "reason": reason},
        )


class PluginExecutionError(PluginError):
    def __init__(self, plugin_name: str, task_id: str, reason: str):
        super().__init__(
            f"Plugin {plugin_name} failed for task {task_id}: {reason}",
            {"plugin_name": plugin_name, "task_id": task_id, "reason": reason},
        )


class PluginValidationError(PluginError):
    def __init__(self, plugin_name: str, errors: list[str]):
        super().__init__(
            f"Plugin {plugin_name} validation failed",
            {"plugin_name": plugin_name, "errors": errors},
        )


class ExecutionError(WZMLError):
    pass


class ExecutionFailedError(ExecutionError):
    def __init__(self, task_id: str, stage: str, error: str):
        super().__init__(
            f"Task {task_id} failed at stage {stage}: {error}",
            {"task_id": task_id, "stage": stage, "error": error},
        )


class QueueError(WZMLError):
    pass


class QueueFullError(QueueError):
    def __init__(self, max_size: int):
        super().__init__(f"Queue is full (max: {max_size})", {"max_size": max_size})


class QueueWorkerError(QueueError):
    def __init__(self, worker_id: str, error: str):
        super().__init__(
            f"Worker {worker_id} failed: {error}",
            {"worker_id": worker_id, "error": error},
        )


class ConfigError(WZMLError):
    pass


class ConfigNotFoundError(ConfigError):
    def __init__(self, key: str):
        super().__init__(f"Configuration key {key} not found", {"key": key})


class ConfigValidationError(ConfigError):
    def __init__(self, key: str, errors: list[str]):
        super().__init__(
            f"Configuration {key} validation failed", {"key": key, "errors": errors}
        )


class StateError(WZMLError):
    pass


class StateNotFoundError(StateError):
    def __init__(self, task_id: str):
        super().__init__(f"State for task {task_id} not found", {"task_id": task_id})
