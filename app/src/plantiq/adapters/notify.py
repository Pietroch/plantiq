# app/src/plantiq/adapters/notify.py

import httpx

from plantiq.core.config import NTFY_TOPIC
from plantiq.core.logging import get_logger

log = get_logger(__name__)

# Publishing as JSON rather than through headers: the Title header is latin-1
# on the wire, so accents would either break or arrive mangled. The JSON body
# is UTF-8 throughout, which lets the messages stay in plain French.
BASE_URL = "https://ntfy.sh"
TIMEOUT = 10


def send(title: str, message: str, *, tags: list[str] | None = None, priority: int = 3) -> None:
    if not NTFY_TOPIC:
        raise RuntimeError("NTFY_TOPIC absente de l'environnement.")

    payload = {
        "topic": NTFY_TOPIC,
        "title": title,
        "message": message,
        "priority": priority,
    }
    if tags:
        payload["tags"] = tags

    response = httpx.post(BASE_URL, json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    log.info("Notification envoyée : %s", title)
