from fastapi import APIRouter, BackgroundTasks, HTTPException, Body
from pydantic import BaseModel
from typing import Optional, Callable
import asyncio

router = APIRouter()

_webhook_store: dict[str, dict] = {}
_webhook_callbacks: dict[str, Callable] = {}


class WebhookConfig(BaseModel):
    url: str
    events: list[str] = ["complete", "error", "progress"]
    secret: Optional[str] = None
    enabled: bool = True


class WebhookResponse(BaseModel):
    task_id: str
    event: str
    data: dict
    timestamp: str


@router.post("/task/{task_id}")
async def register_task_webhook(
    task_id: str,
    webhook: WebhookConfig,
):
    _webhook_store[task_id] = {
        "url": webhook.url,
        "events": webhook.events,
        "secret": webhook.secret,
        "enabled": webhook.enabled,
        "created_at": str(asyncio.get_event_loop().time()),
    }
    return {
        "message": "Webhook registered",
        "task_id": task_id,
        "url": webhook.url,
    }


@router.delete("/task/{task_id}")
async def delete_task_webhook(task_id: str):
    if task_id in _webhook_store:
        del _webhook_store[task_id]
        return {"message": "Webhook deleted", "task_id": task_id}
    raise HTTPException(status_code=404, detail="Webhook not found")


@router.get("/task/{task_id}")
async def get_task_webhook(task_id: str):
    webhook = _webhook_store.get(task_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"data": webhook}


@router.get("")
async def list_webhooks():
    return {"data": _webhook_store, "count": len(_webhook_store)}


@router.post("/trigger")
async def trigger_webhook(
    task_id: str,
    event: str,
    data: dict = Body(...),
):
    webhook = _webhook_store.get(task_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if not webhook.get("enabled"):
        return {"message": "Webhook disabled"}

    if event not in webhook.get("events", []):
        return {"message": "Event not subscribed"}

    import httpx
    from datetime import datetime

    payload = {
        "task_id": task_id,
        "event": event,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    }

    headers = {}
    if webhook.get("secret"):
        headers["X-Webhook-Secret"] = webhook["secret"]

    try:
        async with httpx.AsyncClient() as client:
            await client.post(webhook["url"], json=payload, headers=headers, timeout=10)
    except Exception as e:
        return {"error": str(e)}

    return {"message": "Webhook triggered"}


def register_callback(task_id: str, callback: Callable):
    _webhook_callbacks[task_id] = callback


async def notify_webhook(task_id: str, event: str, data: dict):
    webhook = _webhook_store.get(task_id)
    if webhook and webhook.get("enabled"):
        if event in webhook.get("events", []):
            callback = _webhook_callbacks.get(task_id)
            if callback:
                await callback(event, data)
