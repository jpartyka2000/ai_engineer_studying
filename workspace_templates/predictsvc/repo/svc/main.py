"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from svc.routers import health, predict

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def create_app() -> FastAPI:
    """Build the application.

    A factory rather than a module-level instance, so tests can construct an app
    against a swapped artifact directory without reimporting the module.
    """
    application = FastAPI(
        title="predictsvc",
        version="3.0.1",
        description="Churn-risk scoring. Serving only; training happens elsewhere.",
    )
    application.include_router(health.router)
    application.include_router(predict.router)
    return application


app = create_app()
