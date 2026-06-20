# scheduler/src/plantiq/notify.py

import httpx

from plantiq.core.config import NTFY_TOPIC


def send(title: str, body: str) -> None:
    httpx.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        content=body.encode("utf-8"),
        headers={
            "Title": title,
            "Content-Type": "text/plain; charset=utf-8",
        },
        timeout=10,
    )
