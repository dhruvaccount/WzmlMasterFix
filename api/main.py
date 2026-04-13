import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes.tasks import router as tasks_router
from api.routes.tasks_extended import router as tasks_extended_router
from api.routes.status import router as status_router
from api.routes.files import router as files_router
from api.routes.webhooks import router as webhooks_router


API_TITLE = "WZML-X API"
API_VERSION = "4.0.0"
API_DESCRIPTION = """
Scalable file processing platform API.

## Features
- Task creation and management
- Pipeline-based file processing
- Plugin system for download/upload/processors
- Real-time status updates
- Multi-client support

## Quick Start

```bash
# Create a task
POST /tasks
{
  "source": "https://example.com/file.zip",
  "pipeline_id": "download_upload",
  "user_id": 12345
}

# Get task status
GET /tasks/{task_id}

# List tasks
GET /tasks?user_id=12345
```
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Starting {API_TITLE} v{API_VERSION}")
    yield
    print("Shutting down API...")


app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description=API_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])
app.include_router(tasks_extended_router, prefix="/api", tags=["Extended"])
app.include_router(status_router, prefix="/status", tags=["Status"])
app.include_router(files_router, prefix="/files", tags=["Files"])
app.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])


@app.get("/")
async def root():
    return {
        "name": API_TITLE,
        "version": API_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/services/status")
async def services_status():
    from core.queue import get_queue_manager
    from core.worker import get_worker_pool
    from core.pipeline import list_pipelines
    from core.registry import get_registry
    from plugins import get_available_plugins

    queue = get_queue_manager()
    queue_stats = await queue.get_stats()

    return {
        "queue": {
            "pending": queue_stats.pending,
            "running": queue_stats.running,
            "completed": queue_stats.completed,
            "failed": queue_stats.failed,
        },
        "pipelines": len(list_pipelines()),
        "plugins": len(get_available_plugins()),
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
            }
        },
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
