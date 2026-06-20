# scheduler/src/plantiq/run.py

from plantiq.core.logging import get_logger
from plantiq.engine import run_engine

log = get_logger(__name__)


def run() -> None:
    log.info("Scheduler starting")
    run_engine()
    log.info("Scheduler run complete")


if __name__ == "__main__":
    run()
