import sys

from obs.db import one
from obs.settings import settings


def main() -> None:
    component = sys.argv[1]
    config = settings()
    if component == "collector":
        row = one(
            "SELECT 1 FROM obs.collector_state WHERE component='worker:poll' AND updated_at>now()-%s*interval '1 second'",
            (config.poll_interval_sec * 3,),
        )
    else:
        row = one(
            "SELECT 1 FROM obs.platform_health WHERE component='alerter' AND checked_at>now()-%s*interval '1 second' LIMIT 1",
            (config.alert_interval_sec * 3,),
        )
    sys.exit(0 if row else 1)


if __name__ == "__main__":
    main()
