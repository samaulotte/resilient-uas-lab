"""Orchestrator entrypoint."""

from __future__ import annotations

import asyncio
import signal

from prometheus_client import start_http_server

from reslab_orchestrator.service import OrchestratorService
from reslab_platform.logging import configure_logging, get_logger
from reslab_platform.settings import get_settings

log = get_logger(__name__)


async def _main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format, service="orchestrator")
    if settings.orchestrator_metrics_port:
        start_http_server(settings.orchestrator_metrics_port)
    service = OrchestratorService(settings)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, service.request_stop)
    await service.run_forever()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
