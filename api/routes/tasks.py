from fastapi import APIRouter, HTTPException, Query, status

from core import TaskStatus, create_task, get_task, get_tasks, cancel_task, retry_task


router = APIRouter()


@router.post("")
async def create_task_endpoint(
    source: str,
    pipeline_id: str,
    user_id: int,
    destination: str = "",
    priority: str = "normal",
    metadata: dict | None = None,
):
    try:
        task = await create_task(
            source=source,
            pipeline_id=pipeline_id,
            user_id=user_id,
            destination=destination,
            priority=priority,
            metadata=metadata,
        )

        return {
            "data": task.to_dict(),
            "message": "Task created successfully",
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("")
async def list_tasks(
    user_id: int | None = Query(None, description="Filter by user ID"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    task_status = TaskStatus(status) if status else None

    tasks = await get_tasks(
        user_id=user_id,
        status=task_status,
        limit=limit,
        offset=offset,
    )

    return {
        "data": [t.to_dict() for t in tasks],
        "meta": {
            "count": len(tasks),
            "limit": limit,
            "offset": offset,
        },
    }


@router.get("/{task_id}")
async def get_task_endpoint(task_id: str):
    try:
        task = await get_task(task_id)
        return {"data": task.to_dict()}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete("/{task_id}")
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


@router.post("/{task_id}/retry")
async def retry_task_endpoint(task_id: str):
    try:
        task = await retry_task(task_id)
        return {
            "data": task.to_dict(),
            "message": "Task queued for retry",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
