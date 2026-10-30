"""
In-memory job store for async training jobs.
"""

import uuid
import threading
from typing import Dict, Any, Optional


class JobStore:
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = {
                "status": "running",
                "result": None,
                "error": None,
                "exp_dir": None,
                "current_round": 0,
                "total_rounds": 0,
            }
        return job_id

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._jobs.get(job_id)

    def set_exp_dir(self, job_id: str, exp_dir: str, total_rounds: int):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["exp_dir"] = exp_dir
                self._jobs[job_id]["total_rounds"] = total_rounds

    def update_round(self, job_id: str, round_num: int):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["current_round"] = round_num

    def complete(self, job_id: str, result: dict):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "done"
                self._jobs[job_id]["result"] = result

    def fail(self, job_id: str, error: str):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = error


job_store = JobStore()
