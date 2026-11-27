"""
Background jobs of the platform (SITE_NETWORK_PLAN.md M7, M8): every JOBS_EVERY_S seconds
  - finished runs become model versions; scheduled runs that pass the gates are promoted
  - missing central forecasts are made for plants that share their window
  - once a day: data retention (app/services/retention.py)
Off with PLATFORM_JOBS_LOOP=off (tests drive the functions directly).
"""

import logging
import os
import threading
import time

log = logging.getLogger("fedwind.jobs")

JOBS_EVERY_S = int(os.environ.get("JOBS_EVERY_S", "300"))


def tick() -> dict:
    from app.services import forecast_store, model_registry
    from app.services.inference_client import get_inference
    from app.settings import get_settings

    settings = get_settings()
    out = {"models": model_registry.sync(settings)}
    out["forecasts"] = forecast_store.refresh_due(settings, get_inference())
    global _last_cleanup
    if time.time() - _last_cleanup > 24 * 3600:          # retention once a day (app/services/retention.py)
        from app.services import retention

        out["deleted"] = retention.cleanup()
        _last_cleanup = time.time()
    from app.services.health import beat

    beat("platform jobs")
    return out


_last_cleanup = 0.0


def start_background() -> bool:
    if os.environ.get("PLATFORM_JOBS_LOOP", "on").lower() == "off" or not os.environ.get("DATABASE_URL"):
        return False

    def loop():
        wait = threading.Event()
        while True:
            try:
                done = tick()
                if done["models"] or done["forecasts"]:
                    log.info("jobs: %d model event(s), %d forecast(s)", len(done["models"]), len(done["forecasts"]))
            except Exception as e:  # never kill the API; the next pass tries again
                log.warning("jobs: %s: %s", type(e).__name__, e)
            wait.wait(JOBS_EVERY_S)

    threading.Thread(target=loop, name="platform-jobs", daemon=True).start()
    return True
