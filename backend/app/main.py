"""AFM: Action–Consequence Foresight Model. "Think before acting."

Run:  cd backend && .venv/bin/uvicorn app.main:app --port 8530
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .domain.errors import AFMError
from .engine.service import AFMService
from .engine.usecases import UseCaseService
from .projects.service import ProjectService

log = logging.getLogger("afm")


def create_app(service: AFMService | None = None) -> FastAPI:
    app = FastAPI(title="AFM — Action–Consequence Foresight Model", version="0.2.0",
                  description="Think before acting. A generic local prototype over simulated environment adapters.")
    app.state.afm = service or AFMService()
    app.state.usecases = UseCaseService(app.state.afm)
    app.state.projects = ProjectService(app.state.afm.db, lambda: app.state.afm.llm)
    origins = os.environ.get("AFM_CORS_ORIGINS", "http://localhost:5530,http://127.0.0.1:5530").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)

    @app.exception_handler(AFMError)
    async def afm_error(_: Request, exc: AFMError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        msgs = sorted({f"{'.'.join(str(x) for x in e['loc'] if x != 'body')}: {e['msg']}" for e in exc.errors()})
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_input", "message": "; ".join(msgs)}})

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("unexpected error")  # details stay in the server log, never sent to the UI
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Something went wrong on the AFM server."}})

    @app.get("/api/health")
    def health():
        return {"ok": True, "name": "AFM", "mode": "local prototype, simulated environments only"}

    return app


app = create_app()
