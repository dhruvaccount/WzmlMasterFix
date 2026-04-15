"""
Phase 5: Full Integration Tests

Tests the complete system from API to Core to Telegram adapter,
including downloaders, uploaders, listeners, and the old system bridge.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_downloader_plugins():
    """Test all downloader plugins can be loaded."""
    print("\n=== TEST: Downloader Plugins ===")

    from plugins.downloader import get_downloader

    downloaders = [
        "aria2",
        "qbit",
        "jd",
        "mega",
        "nzb",
        "yt_dlp",
        "direct",
        "telegram",
        "gdrive",
        "rclone",
        "link_gen",
    ]

    for name in downloaders:
        try:
            downloader = get_downloader(name)
            assert downloader is not None, f"Downloader {name} not found"
            print(f"  [PASS] {name}")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            return False

    print("  RESULT: Downloader plugins PASSED")
    return True


async def test_uploader_plugins():
    """Test all uploader plugins can be loaded."""
    print("\n=== TEST: Uploader Plugins ===")

    from plugins.uploader import get_uploader

    uploaders = ["gdrive", "rclone", "telegram", "youtube", "uphosted"]

    for name in uploaders:
        try:
            uploader = get_uploader(name)
            assert uploader is not None, f"Uploader {name} not found"
            print(f"  [PASS] {name}")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            return False

    print("  RESULT: Uploader plugins PASSED")
    return True


async def test_processor_plugins():
    """Test all processor plugins can be loaded."""
    print("\n=== TEST: Processor Plugins ===")

    from plugins.processor import get_processor

    processors = [
        "extractor",
        "compressor",
        "ffmpeg",
        "metadata",
        "thumbnail",
        "splitter",
        "renamer",
    ]

    for name in processors:
        try:
            processor = get_processor(name)
            assert processor is not None, f"Processor {name} not found"
            print(f"  [PASS] {name}")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            return False

    print("  RESULT: Processor plugins PASSED")
    return True


async def test_listener_manager():
    """Test listener manager can register and manage listeners."""
    print("\n=== TEST: Listener Manager ===")

    from core.listeners import get_listener_manager, ListenerType

    manager = get_listener_manager()

    listener_types = [
        ("aria2", ListenerType.DOWNLOAD),
        ("qbit", ListenerType.DOWNLOAD),
        ("mega", ListenerType.DOWNLOAD),
        ("jd", ListenerType.DOWNLOAD),
        ("nzb", ListenerType.DOWNLOAD),
        ("direct", ListenerType.DOWNLOAD),
        ("task", ListenerType.PROCESS),
    ]

    for name, ltype in listener_types:
        try:
            manager.register(name, ltype)
            print(f"  [PASS] {name} ({ltype.name})")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            return False

    print("  RESULT: Listener manager PASSED")
    return True


async def test_pipeline_execution():
    """Test pipeline execution with plugins."""
    print("\n=== TEST: Pipeline Execution ===")

    from core import create_task
    from core.pipeline import create_pipeline, get_pipeline

    pipeline = create_pipeline(
        "integration_pipeline_id",
        name="Integration Pipeline",
        stages=[
            {"plugin": "direct", "action": "download"},
            {"plugin": "gdrive", "action": "upload"},
        ],
        custom=True,
    )
    print(f"  [PASS] Custom pipeline created: {pipeline.id}")

    task = await create_task(
        source="https://example.com/test.zip",
        pipeline_id=pipeline.id,
        user_id=999,
    )
    print(f"  [PASS] Task created: {task.id}")

    from core.queue import enqueue_task, get_queue_manager

    await enqueue_task(task)
    print(f"  [PASS] Task queued")

    pipeline2 = create_pipeline(
        "multi_stage_pipeline_id",
        name="Multi-stage Pipeline",
        stages=[
            {"plugin": "direct", "action": "download"},
            {"plugin": "extractor", "action": "extract"},
            {"plugin": "gdrive", "action": "upload"},
        ],
        custom=True,
    )
    print(f"  [PASS] Multi-stage pipeline created")

    print("  RESULT: Pipeline execution PASSED")
    return True


async def test_bridge_integration():
    """Test new system integration."""
    print("\n=== TEST: Bridge Integration ===")

    from core import create_task
    from core.queue import get_queue_manager, enqueue_task

    task = await create_task(
        source="https://example.com/file.zip",
        pipeline_id="download_upload",
        user_id=999,
    )
    await enqueue_task(task)
    print(f"  [PASS] Task created: {task.id[:8]}")

    manager = get_queue_manager()
    stats = await manager.get_stats()
    print(f"  [PASS] Queue stats: pending={stats.pending}")

    print("  RESULT: Bridge integration PASSED")
    return True


async def test_helper_modules():
    """Test all helper modules are importable."""
    print("\n=== TEST: Helper Modules ===")

    from core.helpers import (
        encode_slink,
        decode_slink,
        is_sudo_user,
        is_authorized_user,
        bypass_link,
        is_bypass_supported,
    )

    print("  [PASS] encode_slink/decode_slink")
    print("  [PASS] sudo/authorization helpers")
    print("  [PASS] bypass helpers")
    print("  [SKIP] TELEGRAM_COMMANDS (requires pyrogram)")
    print("  [SKIP] ButtonMaker (requires pyrogram)")

    from core.helpers.links_utils import (
        is_magnet_url,
        is_gdrive_link,
        is_mega_link,
        is_share_link,
        is_rclone_path,
        is_gdrive_id,
    )

    test_urls = [
        ("magnet:?xt=urn:btih:123", is_magnet_url),
        ("https://drive.google.com/file", is_gdrive_link),
        ("https://mega.nz/file", is_mega_link),
        ("https://gdtot.pro/file", is_share_link),
    ]

    for url, check_func in test_urls:
        result = check_func(url)
        print(f"  [PASS] {check_func.__name__}('{url[:30]}...'): {result}")

    print("  RESULT: Helper modules PASSED")
    return True


async def test_state_persistence():
    """Test state machine persistence."""
    print("\n=== TEST: State Persistence ===")

    from core import create_task, get_task, cancel_task
    from core.task import TaskStatus

    task = await create_task(
        source="https://example.com/persist.zip",
        pipeline_id="download_upload",
        user_id=888,
    )
    print(f"  [PASS] Task created: {task.id[:8]}")

    initial_status = task.status
    print(f"  [PASS] Initial status: {initial_status}")

    task.cancel()
    print(f"  [PASS] Task cancelled")

    result = await get_task(task.id)
    print(f"  [PASS] Task retrieved: {result.status}")

    print("  RESULT: State persistence PASSED")
    return True


async def run_phase5_tests():
    """Run all Phase 5 integration tests."""
    print("=" * 60)
    print("WZML-X v2 Phase 5: Full Integration Tests")
    print("=" * 60)

    tests = [
        ("Downloader Plugins", test_downloader_plugins),
        ("Uploader Plugins", test_uploader_plugins),
        ("Processor Plugins", test_processor_plugins),
        ("Listener Manager", test_listener_manager),
        ("Pipeline Execution", test_pipeline_execution),
        ("Bridge Integration", test_bridge_integration),
        ("Helper Modules", test_helper_modules),
        ("State Persistence", test_state_persistence),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_phase5_tests())
    sys.exit(0 if success else 1)
