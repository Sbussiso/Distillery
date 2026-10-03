"""FastAPI application factory."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routes.api import router

# Where the built Svelte/Vite frontend lives (preferred), and the legacy
# vanilla static dir as a fallback when the frontend hasn't been built.
_FRONTEND_CANDIDATES = [
    Path.cwd() / "frontend" / "dist",
    Path(__file__).resolve().parents[2] / "frontend" / "dist",  # repo root when running from src
]
_LEGACY_STATIC_CANDIDATES = [
    Path.cwd() / "static",
    Path(__file__).resolve().parents[2] / "static",
]


def _find_dir(candidates: list[Path], marker: str) -> Path | None:
    for p in candidates:
        if (p / marker).exists():
            return p
    return None


def create_app() -> FastAPI:
    app = FastAPI(title="Distillery", version="0.1.0")
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(router)

    frontend_dir = _find_dir(_FRONTEND_CANDIDATES, "index.html")

    if frontend_dir is not None:
        assets_dir = frontend_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(str(frontend_dir / "index.html"))

        @app.get("/favicon.ico")
        async def favicon() -> dict:
            return {}
    else:
        # Legacy fallback: serve the vanilla static UI if the new frontend
        # hasn't been built yet (so the app is never left without a UI).
        static_dir = _find_dir(_LEGACY_STATIC_CANDIDATES, "index.html")
        if static_dir is not None:
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

            @app.get("/")
            async def index() -> FileResponse:  # type: ignore[no-redef]
                return FileResponse(str(static_dir / "index.html"))

            @app.get("/favicon.ico")
            async def favicon() -> dict:  # type: ignore[no-redef]
                return {}
        else:
            @app.get("/")
            async def index() -> dict:  # type: ignore[no-redef]
                return {
                    "name": "Distillery",
                    "status": "no UI found; build the frontend (cd frontend && npm run build) or the API is live at /api",
                }

    return app


app = create_app()