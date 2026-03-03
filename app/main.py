from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.database import ensure_database
from app.handlers.webhook_handler import router as webhook_router
from app.workers.email_worker import start_email_worker, stop_email_worker

app = FastAPI(title="WR WH Leads")


@app.on_event("startup")
def startup() -> None:
    ensure_database()
    start_email_worker()


@app.on_event("shutdown")
def shutdown() -> None:
    stop_email_worker()


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True})


app.include_router(webhook_router)

