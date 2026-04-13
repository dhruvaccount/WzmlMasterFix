from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter()


class FileRecord(BaseModel):
    id: str
    name: str
    path: str
    size: int
    mime_type: str
    user_id: int
    task_id: Optional[str] = None
    created_at: datetime
    url: Optional[str] = None


async def get_db():
    from db import get_database

    return get_database()


@router.get("")
async def list_files(
    user_id: int | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    db = await get_db()

    if user_id is not None:
        files = await db.find("files", {"user_id": user_id})
    else:
        files = await db.find_all("files")

    files.sort(key=lambda f: f.get("created_at", datetime.min), reverse=True)

    return {
        "data": files[offset : offset + limit],
        "meta": {"count": len(files), "limit": limit, "offset": offset},
    }


@router.get("/{file_id}")
async def get_file(file_id: str):
    db = await get_db()
    file = await db.find_one("files", {"id": file_id})

    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    return {"data": file}


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    db = await get_db()
    file = await db.find_one("files", {"id": file_id})

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    await db.delete_one("files", {"id": file_id})
    return {"data": file, "message": "File deleted"}


@router.post("")
async def add_file(
    name: str,
    path: str,
    size: int,
    mime_type: str,
    user_id: int,
    task_id: str = None,
    url: str = None,
):
    import uuid

    db = await get_db()

    file_id = f"file_{uuid.uuid4().hex[:12]}"
    record = {
        "id": file_id,
        "name": name,
        "path": path,
        "size": size,
        "mime_type": mime_type,
        "user_id": user_id,
        "task_id": task_id,
        "created_at": datetime.now(),
        "url": url,
    }

    await db.insert_one("files", record)

    return {"data": record, "message": "File registered"}
