import threading

from liftcam.worker.main import run


def test_run_returns_once_stop_is_set() -> None:
    stop = threading.Event()
    stop.set()

    run(stop, poll_interval_s=0.01)


def test_run_exits_shortly_after_stop_requested() -> None:
    stop = threading.Event()
    threading.Timer(0.05, stop.set).start()

    run(stop, poll_interval_s=0.01)

    assert stop.is_set()
