import logging
import signal
import threading
from types import FrameType

from liftcam.core.settings import get_settings

log = logging.getLogger("liftcam.worker")


def run(stop: threading.Event, poll_interval_s: float) -> None:
    """Idle loop. Phase 6 replaces the body with the job claim and stage runner."""
    log.info("worker started")
    while not stop.is_set():
        log.info("heartbeat: no work, sleeping %.1fs", poll_interval_s)
        stop.wait(poll_interval_s)
    log.info("worker stopped")


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    stop = threading.Event()

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        log.info("received signal %s, shutting down", signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    # Windows consoles deliver Ctrl-Break as SIGBREAK; treat it like Ctrl-C.
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        signal.signal(sigbreak, request_stop)

    run(stop, settings.worker_poll_interval_s)


if __name__ == "__main__":
    main()
