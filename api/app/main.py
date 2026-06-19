"""FastAPI application factory for the Clinic Cash Register (Milestone 0)."""

from __future__ import annotations

from fastapi import FastAPI

from app.routers import dashboard, movements, patients, periods, setup


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clinic Cash Register API",
        version="0.1.0",
        summary="Partnership cash-management for a small clinic (V1 Milestone 0).",
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(setup.router)
    app.include_router(patients.router)
    app.include_router(movements.router)
    app.include_router(periods.router)
    app.include_router(dashboard.router)
    return app


app = create_app()
