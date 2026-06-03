from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.db import init_db
from app.web.routes import router
from app.web.projects_routes import router as projects_router
from app.web.rename_routes import router as rename_router

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="library-eka", version="0.1.0")
    init_db()
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(router)
    app.include_router(projects_router)
    app.include_router(rename_router)
    return app


app = create_app()
