import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from core.exceptions import (
    ExecutionFailedError,
    PluginExecutionError,
    PluginNotFoundError,
    PipelineNotFoundError,
)
from core.pipeline import Pipeline, PipelineStage, get_pipeline, ErrorPolicy
from core.registry import get_registry
from core.task import Task, TaskStatus, update_task_progress
from core.events import event_bus


logger = logging.getLogger("wzml.executor")


@dataclass
class ExecutionContext:
    task: Task
    stage_index: int
    stage: PipelineStage
    previous_output: Any = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ExecutionResult:
    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)


class Executor:
    def __init__(self):
        self.registry = get_registry()

    async def execute(self, task: Task) -> bool:
        logger.info(f"Starting task {task.id} with pipeline {task.config.pipeline_id}")

        pipeline = get_pipeline(task.config.pipeline_id)

        previous_output = None
        for stage_index, stage in enumerate(pipeline.stages):
            task.current_stage = stage_index

            await update_task_progress(
                task.id,
                stage=f"stage_{stage_index}",
                plugin=stage.plugin,
                progress=0.0,
            )

            try:
                result = await self._execute_stage(
                    task, stage_index, stage, previous_output
                )
            except Exception as e:
                logger.error(f"Stage {stage_index} failed: {e}")
                task.fail(str(e))
                return False

            if not result.success:
                if stage.on_error == ErrorPolicy.CONTINUE:
                    logger.warning(
                        f"Stage {stage_index} failed, continuing: {result.error}"
                    )
                    continue
                elif stage.on_error == ErrorPolicy.RETRY:
                    logger.warning(f"Stage {stage_index} failed with retry policy")
                    task.fail(result.error or "Retry failed")
                    return False
                else:
                    task.fail(result.error or "Stage failed")
                    return False

            # Carry over the output to the next stage
            if (
                result.output
                and hasattr(result.output, "output_path")
                and result.output.output_path
            ):
                previous_output = result.output.output_path

        task.complete()
        logger.info(f"Task {task.id} completed successfully")
        return True

    async def _execute_stage(
        self,
        task: Task,
        stage_index: int,
        stage: PipelineStage,
        previous_output: str = None,
    ) -> ExecutionResult:
        plugin_name = stage.plugin
        action = stage.action

        try:
            plugin = self.registry.get_plugin(plugin_name)
        except PluginNotFoundError:
            return ExecutionResult(
                success=False,
                error=f"Plugin {plugin_name} not found",
            )

        from plugins.base import PluginContext

        context = ExecutionContext(
            task=task,
            stage_index=stage_index,
            stage=stage,
        )

        plugin_context = PluginContext(
            task_id=task.id,
            source=previous_output if previous_output else task.config.source,
            destination=task.config.destination,
            config=task.config.options,
            metadata=task.config.metadata,
        )

        action_method = None
        if hasattr(plugin, action):
            action_method = getattr(plugin, action)

        if not action_method or not callable(action_method):
            return ExecutionResult(
                success=False,
                error=f"Plugin {plugin_name} has no action '{action}'",
            )

        try:
            result = await action_method(plugin_context, stage.config.__dict__)

            t = await update_task_progress(
                task.id,
                stage=stage.name or f"stage_{stage_index}",
                plugin=plugin_name,
                progress=100.0,
            )
            await event_bus.publish("task_progress", t.to_dict())

            return ExecutionResult(
                success=True,
                output=result,
                metadata=context.metadata,
            )

        except PluginExecutionError as e:
            logger.error(f"Plugin execution error: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
            )

    async def validate_task(self, task: Task) -> list[str]:
        errors = []

        try:
            pipeline = get_pipeline(task.config.pipeline_id)
        except PipelineNotFoundError as e:
            errors.append(str(e))
            return errors

        pipeline_errors = pipeline.validate()
        errors.extend(pipeline_errors)

        for stage in pipeline.stages:
            if not self.registry.plugin_exists(stage.plugin):
                errors.append(f"Plugin {stage.plugin} not found")

        return errors


_executor: Executor | None = None


def get_executor() -> Executor:
    global _executor
    if _executor is None:
        _executor = Executor()
    return _executor


async def execute_task(task: Task) -> bool:
    executor = get_executor()
    return await executor.execute(task)


async def validate_task(task: Task) -> list[str]:
    executor = get_executor()
    return await executor.validate_task(task)
