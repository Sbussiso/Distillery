"""Run with: python -m distillery"""
from __future__ import annotations

import uvicorn

from .app import app
from .config import settings


def main() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()