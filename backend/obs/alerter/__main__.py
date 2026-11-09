import logging
import time

from obs.alerter.rules import evaluate
from obs.redact import redact
from obs.settings import require_demo, settings

require_demo()
while True:
    try:
        evaluate()
    except Exception as exc:
        logging.error("Alert evaluation: %s", redact(str(exc)))
    time.sleep(settings().alert_interval_sec)
