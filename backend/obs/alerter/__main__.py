import logging
import signal
import time

from obs.alerter.notify import dispatch
from obs.alerter.rules import evaluate
from obs.redact import redact
from obs.settings import settings

stopping = False


def stop(*_: object) -> None:
    global stopping
    stopping = True


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
due = 0.0
while not stopping:
    try:
        if time.monotonic() >= due:
            evaluate()
            due = time.monotonic() + settings().alert_interval_sec
        dispatch()
    except Exception as exc:
        logging.error("Alert worker: %s", redact(str(exc)))
    time.sleep(1)
