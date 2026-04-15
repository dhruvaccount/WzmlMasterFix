"""
Phase 2 API Test Suite

Comprehensive tests for the API Layer
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_api_imports():
    """Test all API imports."""
    print("\n=== TEST: API Imports ===")

    from api.main import app

    assert app is not None
    print(f"  [PASS] API app created: {app.title}")

    from api.routes import tasks_router, status_router

    assert tasks_router is not None
    assert status_router is not None
    print("  [PASS] Routes imported")

    print("  RESULT: API imports PASSED")
    return True


async def test_extended_routes():
    """Test extended routes."""
    print("\n=== TEST: Extended Routes ===")

    from api.routes.tasks_extended import router

    assert router is not None

    routes = [r.path for r in router.routes]
    print(f"  [PASS] Extended routes: {len(routes)}")
    for r in routes[:5]:
        print(f"    - {r}")

    print("  RESULT: Extended routes PASSED")
    return True


async def test_task_creation():
    """Test task creation via API simulation."""
    print("\n=== TEST: Task Creation ===")

    from core import create_task
    from core.queue import enqueue_task

    # Create a task
    task = await create_task(
        source="https://example.com/file.zip",
        pipeline_id="download_upload",
        user_id=12345,
    )
    assert task is not None
    print(f"  [PASS] Task created: {task.id}")

    # Queue the task
    await enqueue_task(task)
    assert task.status.value == "queued"
    print(f"  [PASS] Task queued")

    # Get task
    from core import get_task

    retrieved = await get_task(task.id)
    assert retrieved.id == task.id
    print(f"  [PASS] Task retrieved")

    # Cancel task
    from core import cancel_task

    cancelled = await cancel_task(task.id)
    assert cancelled.status.value == "cancelled"
    print(f"  [PASS] Task cancelled")

    print("  RESULT: Task creation PASSED")
    return True


async def test_extended_api_functions():
    """Test extended API functions."""
    print("\n=== TEST: Extended API Functions ===")

    from core import create_task, get_tasks, TaskStatus
    from core.queue import enqueue_task, get_queue_manager

    # Create multiple tasks
    tasks = []
    for i in range(3):
        task = await create_task(
            source=f"https://example.com/file{i}.zip",
            pipeline_id="download_upload",
            user_id=100,
        )
        await enqueue_task(task)
        tasks.append(task)

    print(f"  [PASS] Created {len(tasks)} tasks")

    # List user tasks
    user_tasks = await get_tasks(user_id=100, limit=10)
    assert len(user_tasks) >= 3
    print(f"  [PASS] Listed user tasks: {len(user_tasks)}")

    # Queue stats
    manager = get_queue_manager()
    stats = await manager.get_stats()
    print(f"  [PASS] Queue stats: pending={stats.pending}")

    # List queued
    queued = await manager.list_queued()
    print(f"  [PASS] Queued tasks: {len(queued)}")

    print("  RESULT: Extended API functions PASSED")
    return True


async def test_pipeline_operations():
    """Test pipeline operations via API."""
    print("\n=== TEST: Pipeline Operations ===")

    from core.pipeline import create_pipeline, get_pipeline, get_available_plugins

    # Get available plugins
    plugins = get_available_plugins()
    print(f"  [PASS] Available plugins: {len(plugins)}")

    # Create custom pipeline
    custom = create_pipeline(
        "test_custom_pipeline_id",
        name="Test Custom Pipeline",
        stages=[
            {"plugin": "direct", "action": "download"},
            {"plugin": "gdrive", "action": "upload"},
        ],
        custom=True,
    )
    print(f"  [PASS] Custom pipeline: {custom.id}")

    # Get pipeline
    p = get_pipeline(custom.id)
    assert p.id == custom.id
    print(f"  [PASS] Pipeline retrieved")

    print("  RESULT: Pipeline operations PASSED")
    return True


async def test_client_adapter():
    """Test Telegram client adapter."""
    print("\n=== TEST: Client Adapter ===")

    try:
        from bots.clients.telegram import TelegramClient

        client = TelegramClient()
        assert client is not None
        print(f"  [PASS] TelegramClient exists")
    except ImportError as e:
        if "pyrogram" in str(e) or "pyrotgfork" in str(e):
            print(f"  [SKIP] Telegram library not installed")
            return True
        raise

    print("  RESULT: Client adapter PASSED")
    return True


async def run_api_tests():
    """Run all API tests."""
    print("=" * 60)
    print("WZML-X v2 Phase 2 API - Comprehensive Test Suite")
    print("=" * 60)

    tests = [
        ("API Imports", test_api_imports),
        ("Extended Routes", test_extended_routes),
        ("Task Creation", test_task_creation),
        ("Extended API Functions", test_extended_api_functions),
        ("Pipeline Operations", test_pipeline_operations),
        ("Client Adapter", test_client_adapter),
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
            import traceback

            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_api_tests())
    sys.exit(0 if success else 1)
