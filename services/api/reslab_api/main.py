"""API entrypoint (`python -m reslab_api.main`)."""

from __future__ import annotations

import uvicorn

from reslab_platform.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "reslab_api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
        ws_ping_interval=20,
        ws_ping_timeout=20,
        ws_max_size=64 * 1024,
    )


if __name__ == "__main__":
    main()
