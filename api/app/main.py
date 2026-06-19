"""FastAPI application factory for the Clinic Cash Register."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    config,
    corrections,
    dashboard,
    devauth,
    exports,
    movements,
    patients,
    periods,
    reminders,
    reports,
    setup,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clinic Cash Register API",
        version="1.0.0",
        summary="Partnership cash-management for a small clinic (V1).",
    )

    # The PWA is a separate origin in dev; the API is private and behind a JWT.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (
        setup,
        devauth,
        config,
        patients,
        movements,
        corrections,
        periods,
        reports,
        reminders,
        dashboard,
        exports,
    ):
        app.include_router(module.router)
    return app


app = create_app()
