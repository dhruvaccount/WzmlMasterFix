from fastapi import APIRouter, Body, HTTPException, Query, status
from pydantic import BaseModel

from core import TaskStatus, create_task, get_task, get_tasks, cancel_task, retry_task


router = APIRouter()


class MirrorRequest(BaseModel):
    source: str
    user_id: int
    pipeline_id: str = "download_upload"
    destination: str = ""
    priority: str = "normal"
    is_leech: bool = False
    is_qbit: bool = False
    mirror_mode: str = ""
    multi: bool = False
    link: str = ""
    options: dict = {}


class BulkLinksRequest(BaseModel):
    links: list[str]
    user_id: int
    pipeline_id: str = "download_upload"


@router.post("/mirror", tags=["Mirror"])
async def create_mirror_task(
    source: str,
    user_id: int,
    destination: str = "",
    is_leech: bool = False,
    is_qbit: bool = False,
    mirror_mode: str = "",
    metadata: dict | None = None,
):
    if is_qbit:
        pipeline_id = "torrent_gdrive"
    elif is_leech:
        pipeline_id = "telegram_gdrive"
    else:
        pipeline_id = "download_upload"

    task = await create_task(
        source=source,
        pipeline_id=pipeline_id,
        user_id=user_id,
        destination=destination,
        metadata=metadata or {},
    )

    from core.queue import enqueue_task

    await enqueue_task(task)

    return {
        "data": task.to_dict(),
        "message": f"{'Leech' if is_leech else 'Mirror'} task created",
    }


@router.post("/bulk", tags=["Mirror"])
async def create_bulk_tasks(request: BulkLinksRequest):
    tasks = []
    for link in request.links:
        task = await create_task(
            source=link,
            pipeline_id=request.pipeline_id,
            user_id=request.user_id,
        )
        tasks.append(task.to_dict())

    return {
        "data": tasks,
        "count": len(tasks),
        "message": f"Created {len(tasks)} tasks",
    }


@router.post("/clone", tags=["GDrive"])
async def clone_task(
    source_id: str,
    user_id: int,
    destination: str = "",
):
    task = await create_task(
        source=source_id,
        pipeline_id="gdrive_clone",
        user_id=user_id,
        destination=destination or "root",
    )

    from core.queue import enqueue_task

    await enqueue_task(task)

    return {"data": task.to_dict(), "message": "Clone task created"}


@router.post("/ytdlp", tags=["YouTube"])
async def create_ytdlp_task(
    url: str,
    user_id: int,
    quality: str = "best",
    format: str = "mp4",
    thumbnail: bool = True,
):
    task = await create_task(
        source=url,
        pipeline_id="yt_telegram",
        user_id=user_id,
        metadata={
            "quality": quality,
            "format": format,
            "thumbnail": thumbnail,
        },
    )

    from core.queue import enqueue_task

    await enqueue_task(task)

    return {"data": task.to_dict(), "message": "YouTube task created"}


@router.post("/rss", tags=["RSS"])
async def create_rss_task(
    feed_url: str,
    user_id: int,
    pipeline_id: str = "rss_gdrive",
):
    task = await create_task(
        source=feed_url,
        pipeline_id=pipeline_id,
        user_id=user_id,
        metadata={"rss": True},
    )

    return {"data": task.to_dict(), "message": "RSS task created"}


@router.post("/uphoster", tags=["Uphoster"])
async def create_uphoster_task(
    file_path: str,
    user_id: int,
    service: str = "gofile",
):
    task = await create_task(
        source=file_path,
        pipeline_id=f"uphosted_{service}",
        user_id=user_id,
    )

    return {"data": task.to_dict(), "message": f"Upload to {service} created"}


@router.get("/status/active", tags=["Status"])
async def get_active_tasks(
    user_id: int | None = None,
):
    tasks = await get_tasks(
        user_id=user_id,
        status=None,
        limit=100,
    )

    active = [t for t in tasks if t.status in [TaskStatus.QUEUED, TaskStatus.RUNNING]]

    return {
        "data": [t.to_dict() for t in active],
        "count": len(active),
    }


@router.get("/status/user/{user_id}", tags=["Status"])
async def get_user_tasks(
    user_id: int,
    limit: int = 50,
):
    tasks = await get_tasks(
        user_id=user_id,
        limit=limit,
    )

    return {
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks),
    }


@router.get("/status/all", tags=["Status"])
async def get_all_tasks(
    limit: int = 100,
    offset: int = 0,
):
    tasks = await get_tasks(limit=limit, offset=offset)

    return {
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks),
        "limit": limit,
        "offset": offset,
    }


@router.post("/{task_id}/cancel", tags=["Control"])
async def cancel_task_v2(task_id: str):
    return await cancel_task_endpoint(task_id)


@router.post("/{task_id}/force_start", tags=["Control"])
async def force_start_task(task_id: str):
    task = await get_task(task_id)
    if task.status == TaskStatus.QUEUED:
        task.start()
    return {"data": task.to_dict(), "message": "Task force started"}


@router.post("/{task_id}/pause", tags=["Control"])
async def pause_task(task_id: str):
    return {"error": "Not implemented"}


@router.post("/{task_id}/resume", tags=["Control"])
async def resume_task(task_id: str):
    return {"error": "Not implemented"}


@router.get("/queue/stats", tags=["Queue"])
async def get_queue_stats():
    from core.queue import get_queue_manager

    manager = get_queue_manager()
    stats = await manager.get_stats()

    return {
        "pending": stats.pending,
        "running": stats.running,
        "completed": stats.completed,
        "failed": stats.failed,
    }


@router.get("/queue/pending", tags=["Queue"])
async def get_pending_tasks():
    from core.queue import get_queue_manager

    manager = get_queue_manager()
    tasks = await manager.list_queued()

    return {"data": [t.to_dict() for t in tasks]}


async def cancel_task_endpoint(task_id: str):
    try:
        task = await cancel_task(task_id)
        return {
            "data": task.to_dict(),
            "message": "Task cancelled successfully",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
