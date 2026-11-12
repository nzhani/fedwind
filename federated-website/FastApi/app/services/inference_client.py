"""
Inference client - asks a site's inference service for a forecast (plan T3.2, T3.5).

Each site has its own inference service next to its data, so the API never
reads site data: the service returns both the actual values around `as_of`
and the forecast.  Selected by INFERENCE_URL_TEMPLATE
(e.g. "http://inference-{site}:8000"); unset -> NotConnectedInference.

Service contract:  POST {base}/forecast
  request   {"horizon": 72, "as_of": "<ISO or null>", "model_path": "wind/h72/current.pt"}
  response  {"as_of": "...", "unit": "m/s", "actual": [...], "forecast": [...]}
"""

from typing import Any, Dict, Optional, Protocol

import requests

from app.settings import get_settings


class InferenceUnavailable(Exception):
    """The site's inference service can't be reached; the message is shown to the user."""


class InferenceClient(Protocol):
    def forecast(self, site: str, horizon: int, as_of: Optional[str], model_path: str) -> Dict[str, Any]: ...


class NotConnectedInference:
    detail = "Inference not connected: no inference services are configured (INFERENCE_URL_TEMPLATE is unset)."

    def forecast(self, site: str, horizon: int, as_of: Optional[str], model_path: str) -> Dict[str, Any]:
        raise InferenceUnavailable(self.detail)


class HttpInferenceClient:
    def __init__(self, url_template: str, timeout_s: float = 10.0):
        self.url_template = url_template
        self.timeout_s = timeout_s

    def forecast(self, site: str, horizon: int, as_of: Optional[str], model_path: str) -> Dict[str, Any]:
        url = self.url_template.format(site=site).rstrip("/") + "/forecast"
        try:
            resp = requests.post(
                url,
                json={"horizon": horizon, "as_of": as_of, "model_path": model_path},
                timeout=self.timeout_s,
            )
        except requests.RequestException as e:
            raise InferenceUnavailable(f"Inference service for '{site}' is unreachable: {e}") from e
        if resp.status_code != 200:
            raise InferenceUnavailable(
                f"Inference service for '{site}' returned {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()


def get_inference() -> InferenceClient:
    settings = get_settings()
    if settings.inference_url_template:
        return HttpInferenceClient(settings.inference_url_template)
    return NotConnectedInference()
