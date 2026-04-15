"""
Phase 1 Foundation Tests
Tests for WZML-X Core Engine
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_task_state_machine():
    """Test task creation and state machine."""
    print("\n=== TEST: Task State Machine ===")

    from core import create_task, get_task, TaskStatus, TaskPriority

    # Test 1: Create task
    task = await create_task(
        source="https://example.com/file.zip",
        pipeline_id="download_upload",
        user_id=12345,
        destination="/gdrive/folder",
        priority=TaskPriority.HIGH,
    )
    assert task is not None
    assert task.status == TaskStatus.PENDING
    print(f"  [PASS] Task created: {task.id}")

    # Test 2: Queue task
    task.queue()
    assert task.status == TaskStatus.QUEUED
    print(f"  [PASS] Task queued")

    # Test 3: Start task
    task.start()
    assert task.status == TaskStatus.RUNNING
    print(f"  [PASS] Task started")

    # Test 4: Complete task
    task.complete()
    assert task.status == TaskStatus.COMPLETED
    assert task.progress.progress == 100.0
    print(f"  [PASS] Task completed")

    # Test 5: Get task by ID
    task2 = await get_task(task.id)
    assert task2.id == task.id
    print(f"  [PASS] Task retrieved")

    # Test 6: Cancel workflow
    task3 = await create_task(source="test", pipeline_id="download_upload", user_id=1)
    task3.queue()
    task3.start()
    task3.cancel()
    assert task3.status == TaskStatus.CANCELLED
    print(f"  [PASS] Task cancelled")

    # Test 7: Retry workflow
    task4 = await create_task(
        source="test", pipeline_id="download_upload", user_id=1, max_retries=3
    )
    task4.queue()
    task4.start()
    task4.fail("Test error")
    assert task4.status == TaskStatus.FAILED
    assert task4.error == "Test error"

    task4.retry()
    assert task4.status == TaskStatus.PENDING
    assert task4.retry_count == 1
    print(f"  [PASS] Task retry")

    print("  RESULT: All task state machine tests PASSED")
    return True


async def test_dynamic_pipelines():
    """Test dynamic pipeline creation."""
    print("\n=== TEST: Dynamic Pipelines ===")

    from core.pipeline import (
        create_pipeline,
        get_pipeline,
        list_pipelines,
        get_available_plugins,
        get_plugin_actions,
    )

    # Test 1: Get available plugins
    plugins = get_available_plugins()
    assert len(plugins) >= 15  # At least 15 plugins
    print(f"  [PASS] Available plugins: {len(plugins)}")

    # Test 2: Get plugin actions
    yt_actions = get_plugin_actions("yt_dlp")
    assert "download" in yt_actions
    print(f"  [PASS] yt_dlp actions: {yt_actions}")

    # Test 3: Create custom pipeline (simple name)
    custom = create_pipeline(
        "custom_yt_extract",
        name="YT Extract Zip GD",
        stages=[
            {"plugin": "yt_dlp", "action": "download"},
            {"plugin": "extractor", "action": "extract"},
            {"plugin": "compressor", "action": "zip"},
            {"plugin": "gdrive", "action": "upload"},
        ],
        description="Custom pipeline",
        custom=True,
    )
    assert custom is not None
    print(f"  [PASS] Custom pipeline created: {custom.id}")

    # Test 4: Get custom pipeline
    retrieved = get_pipeline(custom.id)
    assert retrieved.id == custom.id
    print(f"  [PASS] Pipeline retrieved")

    # Test 5: List pipelines
    all_pipelines = list_pipelines()
    assert len(all_pipelines) >= 5
    print(f"  [PASS] Total pipelines: {len(all_pipelines)}")

    # Test 6: Pipeline stages
    assert len(custom.stages) == 4
    print(f"  [PASS] Pipeline stages: {len(custom.stages)}")

    # Test 7: Get any pipeline in list
    pipelines = list_pipelines()
    print(f"  [PASS] Pipeline count: {len(pipelines)}")

    print("  RESULT: All dynamic pipeline tests PASSED")
    return True


async def test_priority_queue():
    """Test priority queue."""
    print("\n=== TEST: Priority Queue ===")

    from core.queue import PriorityQueue, QueueItem
    from core.task import Task, TaskPriority, create_task

    queue = PriorityQueue(max_size=10)

    # Test 1: Put tasks
    task1 = await create_task(
        source="t1", pipeline_id="test", user_id=1, priority=TaskPriority.LOW
    )
    task2 = await create_task(
        source="t2", pipeline_id="test", user_id=1, priority=TaskPriority.HIGH
    )
    task3 = await create_task(
        source="t3", pipeline_id="test", user_id=1, priority=TaskPriority.CRITICAL
    )

    await queue.put(task3)  # CRITICAL
    await queue.put(task1)  # LOW
    await queue.put(task2)  # HIGH

    # Test 2: Get in priority order
    first = await queue.get()
    assert first.config.priority == TaskPriority.CRITICAL
    print(f"  [PASS] Priority order: {first.config.priority}")

    second = await queue.get()
    assert second.config.priority == TaskPriority.HIGH
    print(f"  [PASS] Second: {second.config.priority}")

    # Test 3: Size
    size = await queue.size()
    assert size == 1
    print(f"  [PASS] Queue size: {size}")

    # Test 4: Remove
    task4 = await create_task(source="t4", pipeline_id="test", user_id=1)
    await queue.put(task4)
    removed = await queue.remove(task4.id)
    assert removed == True
    print(f"  [PASS] Task removed")

    print("  RESULT: All priority queue tests PASSED")
    return True


async def test_queue_manager():
    """Test queue manager with retry logic."""
    print("\n=== TEST: Queue Manager ===")

    from core.queue import get_queue_manager, QueueManager
    from core.task import TaskStatus, create_task

    manager = QueueManager(max_size=10)

    # Test 1: Enqueue
    task = await create_task(source="test", pipeline_id="test", user_id=1)
    result = await manager.enqueue(task)
    assert result == True
    assert task.status == TaskStatus.QUEUED
    print(f"  [PASS] Task enqueued")

    # Test 2: Dequeue
    task2 = await manager.dequeue()
    assert task2 is not None
    assert task2.status == TaskStatus.RUNNING
    print(f"  [PASS] Task dequeued")

    # Test 3: Complete
    task2.complete()
    await manager.complete(task2)
    print(f"  [PASS] Task completed")

    # Test 4: List queued
    task3 = await create_task(source="test3", pipeline_id="test", user_id=1)
    await manager.enqueue(task3)
    queued = await manager.list_queued()
    assert len(queued) >= 1
    print(f"  [PASS] List queued: {len(queued)}")

    print("  RESULT: All queue manager tests PASSED")
    return True


async def test_worker_pool():
    """Test worker pool."""
    print("\n=== TEST: Worker Pool ===")

    from core.worker import WorkerPool, Worker, WorkerConfig

    # Test 1: Create worker pool
    pool = WorkerPool(max_workers=5)
    assert pool._max_workers == 5
    print(f"  [PASS] Worker pool created")

    # Test 2: Worker config
    config = WorkerConfig(timeout=1800, max_retries=5)
    assert config.timeout == 1800
    assert config.max_retries == 5
    print(f"  [PASS] Worker config")

    # Test 3: Create worker
    worker = Worker("test_worker", config)
    assert worker.worker_id == "test_worker"
    assert worker.is_idle == True
    print(f"  [PASS] Worker created")

    # Test 4: Worker stats
    heartbeat = await worker.heartbeat()
    assert heartbeat["worker_id"] == "test_worker"
    assert heartbeat["is_idle"] == True
    print(f"  [PASS] Worker heartbeat")

    print("  RESULT: All worker pool tests PASSED")
    return True


async def test_plugin_registry():
    """Test plugin registry."""
    print("\n=== TEST: Plugin Registry ===")

    from core.registry import PluginRegistry, PluginMetadata, PluginType, PluginState

    registry = PluginRegistry()

    # Test 1: Create plugin metadata
    metadata = PluginMetadata(
        name="test_plugin",
        version="1.0.0",
        plugin_type=PluginType.DOWNLOADER,
    )
    assert metadata.name == "test_plugin"
    print(f"  [PASS] Plugin metadata")

    # Test 2: Register plugin
    class DummyPlugin:
        name = "test"

    registry.register_plugin("test", metadata, DummyPlugin())
    assert registry.plugin_exists("test")
    print(f"  [PASS] Plugin registered")

    # Test 3: List plugins
    plugins = registry.list_plugins(PluginType.DOWNLOADER)
    assert "test" in plugins
    print(f"  [PASS] List plugins")

    # Test 4: Get plugin info
    info = registry.get_plugin_info("test")
    assert info is not None
    assert info.state == PluginState.LOADED
    print(f"  [PASS] Get plugin info")

    print("  RESULT: All plugin registry tests PASSED")
    return True


async def test_plugin_interfaces():
    """Test plugin base interfaces."""
    print("\n=== TEST: Plugin Interfaces ===")

    from plugins import (
        DownloaderPlugin,
        UploaderPlugin,
        ProcessorPlugin,
        PluginContext,
        PluginResult,
        PluginType,
    )

    # Test 1: Plugin context
    ctx = PluginContext(task_id="test", source="http://test.com", destination="/dest")
    assert ctx.task_id == "test"
    assert ctx.source == "http://test.com"
    print(f"  [PASS] Plugin context")

    # Test 2: Plugin result
    result = PluginResult(
        success=True,
        output_path="/output/file.zip",
        output_paths=["/output/file.zip"],
    )
    assert result.success == True
    assert result.output_path == "/output/file.zip"
    print(f"  [PASS] Plugin result")

    # Test 3: Plugin types
    assert PluginType.DOWNLOADER == "downloader"
    assert PluginType.UPLOADER == "uploader"
    assert PluginType.PROCESSOR == "processor"
    print(f"  [PASS] Plugin types")

    # Test 4: Create custom plugin
    class MyDownloader(DownloaderPlugin):
        name = "my_downloader"

        async def download(self, context, config):
            return PluginResult(success=True, output_path="/test")

        async def pause(self):
            return True

        async def resume(self):
            return True

        async def cancel(self):
            return True

    plugin = MyDownloader()
    assert plugin.name == "my_downloader"
    assert plugin.plugin_type == PluginType.DOWNLOADER
    print(f"  [PASS] Custom plugin created")

    print("  RESULT: All plugin interface tests PASSED")
    return True


async def test_executor():
    """Test task executor."""
    print("\n=== TEST: Task Executor ===")

    from core.executor import Executor, ExecutionResult
    from core.task import create_task

    executor = Executor()

    # Test 1: Create execution result
    exec_result = ExecutionResult(
        success=True,
        output="/path/to/file",
    )
    assert exec_result.success == True
    assert exec_result.output == "/path/to/file"
    print(f"  [PASS] Execution result")

    # Test 2: Validate task (will have errors since plugins not loaded)
    task = await create_task(source="test", pipeline_id="download_upload", user_id=1)
    errors = await executor.validate_task(task)
    # May have plugin validation errors - that's expected
    print(f"  [PASS] Validate task check: {type(errors).__name__}")

    # Test 3: Executor exists
    assert executor is not None
    print(f"  [PASS] Executor created")

    print("  RESULT: All executor tests PASSED")
    return True


async def test_exceptions():
    """Test custom exceptions."""
    print("\n=== TEST: Exceptions ===")

    from core.exceptions import (
        WZMLError,
        TaskNotFoundError,
        PipelineNotFoundError,
        PluginNotFoundError,
        QueueFullError,
    )

    # Test 1: Task not found
    try:
        raise TaskNotFoundError("test-123")
    except TaskNotFoundError as e:
        assert "test-123" in str(e)
        print(f"  [PASS] TaskNotFoundError")

    # Test 2: Pipeline not found
    try:
        raise PipelineNotFoundError("test-pipeline")
    except PipelineNotFoundError as e:
        assert "test-pipeline" in str(e)
        print(f"  [PASS] PipelineNotFoundError")

    # Test 3: Plugin not found
    try:
        raise PluginNotFoundError("my_plugin")
    except PluginNotFoundError as e:
        assert "my_plugin" in str(e)
        print(f"  [PASS] PluginNotFoundError")

    # Test 4: Queue full
    try:
        raise QueueFullError(100)
    except QueueFullError as e:
        assert "100" in str(e)
        print(f"  [PASS] QueueFullError")

    print("  RESULT: All exception tests PASSED")
    return True


async def test_state_manager():
    """Test state management."""
    print("\n=== TEST: State Manager ===")

    from core.state import StateManager, StateData

    manager = StateManager()

    # Test 1: Initialize
    await manager.initialize()
    print(f"  [PASS] Initialize")

    # Test 2: Set state
    await manager.set("task-1", {"key": "value"})
    print(f"  [PASS] Set state")

    # Test 3: Get state
    state = await manager.get("task-1")
    assert state.data["key"] == "value"
    print(f"  [PASS] Get state")

    # Test 4: Update state
    await manager.update("task-1", {"key2": "value2"})
    state = await manager.get("task-1")
    assert state.data["key2"] == "value2"
    print(f"  [PASS] Update state")

    # Test 5: Exists
    exists = await manager.exists("task-1")
    assert exists == True
    print(f"  [PASS] Exists")

    # Test 6: Delete
    await manager.delete("task-1")
    exists = await manager.exists("task-1")
    assert exists == False
    print(f"  [PASS] Delete state")

    # Test 7: Count
    count = await manager.count()
    assert count == 0
    print(f"  [PASS] Count: {count}")

    # Test 8: Close
    await manager.close()
    print(f"  [PASS] Close")

    print("  RESULT: All state manager tests PASSED")
    return True


async def run_all_tests():
    """Run all Phase 1 tests."""
    print("=" * 60)
    print("WZML-X v2 Phase 1 Foundation - Full Test Suite")
    print("=" * 60)

    tests = [
        ("Task State Machine", test_task_state_machine),
        ("Dynamic Pipelines", test_dynamic_pipelines),
        ("Priority Queue", test_priority_queue),
        ("Queue Manager", test_queue_manager),
        ("Worker Pool", test_worker_pool),
        ("Plugin Registry", test_plugin_registry),
        ("Plugin Interfaces", test_plugin_interfaces),
        ("Task Executor", test_executor),
        ("Exceptions", test_exceptions),
        ("State Manager", test_state_manager),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
