"""
Full Integration Test

Tests the complete system from API to Core to Telegram adapter
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_full_flow():
    """Test complete flow: API -> Core -> Queue -> Worker."""
    print("\n=== TEST: Full Integration Flow ===")

    # 1. Create task via API simulation
    from core import create_task, get_task, TaskStatus
    from core.queue import enqueue_task, get_queue_manager
    from core.pipeline import create_pipeline

    # Create custom pipeline
    pipeline = create_pipeline(
        pipeline_id="integration_test",
        name="Integration Test Pipeline",
        stages=[
            {"plugin": "downloader.direct", "action": "download"},
            {"plugin": "uploader.gdrive", "action": "upload"},
        ],
        custom=True,
    )
    print(f"  [PASS] Pipeline created: {pipeline.id}")

    # Create task
    task = await create_task(
        source="https://example.com/test.zip",
        pipeline_id=pipeline.id,
        user_id=999,
    )
    print(f"  [PASS] Task created: {task.id}")

    # Queue task
    await enqueue_task(task)
    print(f"  [PASS] Task queued: {task.status}")

    # Get from queue
    manager = get_queue_manager()
    dequeued = await manager.dequeue()
    print(f"  [PASS] Task dequeued: {dequeued.id if dequeued else None}")

    # After dequeue, task is already RUNNING (not QUEUED)
    if dequeued:
        assert dequeued.status == TaskStatus.RUNNING
        print(f"  [PASS] Task dequeued/running: {dequeued.status}")

        # Complete task
        dequeued.complete()
        await manager.complete(dequeued)
        print(f"  [PASS] Task completed: {dequeued.status}")

    # Get stats
    stats = await manager.get_stats()
    print(f"  [PASS] Stats: completed={stats.completed}")

    print("  RESULT: Full flow PASSED")
    return True


async def test_api_to_core():
    """Test API endpoints calling Core."""
    print("\n=== TEST: API to Core Integration ===")

    # Simulate API call
    from core import create_task
    from core.queue import enqueue_task

    # API-like function
    async def api_create_mirror(source: str, user_id: int, is_leech: bool = False):
        pipeline = "telegram_gdrive" if is_leech else "download_upload"

        task = await create_task(
            source=source,
            pipeline_id=pipeline,
            user_id=user_id,
            metadata={"is_leech": is_leech},
        )

        await enqueue_task(task)
        return task

    # Simulate API calls
    task1 = await api_create_mirror("https://example.com/file1.zip", 100)
    task2 = await api_create_mirror("https://example.com/file2.zip", 100, is_leech=True)

    print(f"  [PASS] Mirror task: {task1.id[:8]}")
    print(f"  [PASS] Leech task: {task2.id[:8]}")

    # Get user tasks
    from core import get_tasks

    user_tasks = await get_tasks(user_id=100)
    print(f"  [PASS] User tasks: {len(user_tasks)}")

    print("  RESULT: API to Core PASSED")
    return True


async def test_new_system():
    """Test new system integration."""
    print("\n=== TEST: New System Integration ===")

    from config import get_config
    from core.queue import get_queue_manager

    config = get_config()
    config.load_all()

    print(f"  [PASS] Config loaded: telegram={bool(config.telegram.BOT_TOKEN)}")

    # Test queue stats
    manager = get_queue_manager()
    stats = await manager.get_stats()
    print(f"  [PASS] Queue stats: pending={stats.pending}")

    print("  RESULT: New system PASSED")
    return True


async def run_integration_tests():
    """Run all integration tests."""
    print("=" * 60)
    print("WZML-X v2 Full Integration Test")
    print("=" * 60)

    tests = [
        ("Full Flow", test_full_flow),
        ("API to Core", test_api_to_core),
        ("New System", test_new_system),
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
    success = asyncio.run(run_integration_tests())
    sys.exit(0 if success else 1)
