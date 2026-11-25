"""
Checks on client updates before aggregation (SITE_NETWORK_PLAN.md §2.1 L6, §7.5).

Many independent plants means some updates will be broken (a bad sensor feed, a bug) or hostile.
Before FedAvg sees them, each update is checked:
  - every value finite (no NaN / inf)
  - same keys and shapes as the global trainable state
  - its distance from the global model (L2 norm of the update) at most `ratio` x the round's median
    (only with 3+ updates: with fewer there is no meaningful median)
Rejected updates are left out of this round and logged with the reason; the run goes on.
"""

import math
import statistics
from typing import Callable, Dict, List, Mapping, Optional, Tuple

import torch


def update_norm(client: Mapping[str, torch.Tensor], global_state: Mapping[str, torch.Tensor],
                skip: Callable[[str], bool] = lambda k: False) -> float:
    total = 0.0
    for k, v in client.items():
        if k in global_state and not skip(k):
            d = v.float() - global_state[k].float()
            total += float(torch.sum(d * d))
    return math.sqrt(total)


def check_state(client: Mapping[str, torch.Tensor], global_state: Optional[Mapping[str, torch.Tensor]]) -> Optional[str]:
    """Reason the state is unusable, or None."""
    for k, v in client.items():
        if not torch.isfinite(v.float()).all():
            return f"non-finite values in {k}"
    if global_state is not None:
        missing = set(global_state) - set(client)
        extra = set(client) - set(global_state)
        if missing or extra:
            return f"parameter names differ ({len(missing)} missing, {len(extra)} unexpected)"
        for k, v in client.items():
            if tuple(v.shape) != tuple(global_state[k].shape):
                return f"shape of {k} is {tuple(v.shape)}, expected {tuple(global_state[k].shape)}"
    return None


def screen(states: Dict[object, Mapping[str, torch.Tensor]], global_state: Optional[Mapping[str, torch.Tensor]],
           ratio: float = 5.0, skip: Callable[[str], bool] = lambda k: False) -> Tuple[List[object], Dict[object, str]]:
    """states: {client key: trainable state}. Returns (accepted keys, {rejected key: reason})."""
    rejected: Dict[object, str] = {}
    norms: Dict[object, float] = {}
    for key, state in states.items():
        reason = check_state(state, global_state)
        if reason:
            rejected[key] = reason
        elif global_state is not None:
            norms[key] = update_norm(state, global_state, skip)
    if ratio and ratio > 0 and len(norms) >= 3:
        median = statistics.median(norms.values())
        if median > 0:
            for key, n in norms.items():
                if n > ratio * median:
                    rejected[key] = f"update norm {n:.3g} is more than {ratio:g} x the round median {median:.3g}"
    return [k for k in states if k not in rejected], rejected
