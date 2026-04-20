from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

@router.websocket("/ws")
async def websocket_status(websocket: WebSocket):
    from core.events import event_bus
    import asyncio
    
    await websocket.accept()
    queue = asyncio.Queue()
    event_bus.subscribe(queue)
    try:
        while True:
            # wait for events to be pushed into the queue
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(queue)

@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    from core import get_task

    try:
        task = await get_task(task_id)
        return {
            "task_id": task.id,
            "status": task.status,
            "progress": {
                "stage": task.progress.stage,
                "plugin": task.progress.plugin,
                "percent": task.progress.progress,
                "speed": task.progress.speed,
                "eta": task.progress.eta,
            },
            "error": task.error,
            "retry_count": task.retry_count,
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/queue")
async def get_queue_status():
    from core.queue import get_queue_stats

    stats = await get_queue_stats()
    return {
        "pending": stats.pending,
        "running": stats.running,
        "completed": stats.completed,
        "failed": stats.failed,
    }


@router.get("/workers")
async def get_workers_status():
    from core.worker import get_worker_pool

    pool = get_worker_pool()
    try:
        stats = await pool.get_stats()
        return {
            "total_workers": stats.total_workers,
            "active_workers": stats.active_workers,
            "queued_tasks": stats.queued_tasks,
            "running_tasks": stats.running_tasks,
            "completed_tasks": stats.completed_tasks,
            "failed_tasks": stats.failed_tasks,
        }
    except Exception as e:
        return {"error": str(e)}
