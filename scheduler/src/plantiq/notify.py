# scheduler/src/plantiq/notify.py

import httpx

from plantiq.core.config import NTFY_TOPIC
from plantiq.core.logging import get_logger

log = get_logger(__name__)


def send(title: str, body: str) -> None:
    httpx.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        content=body.encode(),
        headers={
            "Title": title,
            "Content-Type": "text/plain; charset=utf-8",
        },
        timeout=10,
    )
    log.info("Notification sent: %s", title)
