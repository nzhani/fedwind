"""
Reference wind turbine power curve (plan T3.3, DR-01, DR-03).

  v < cut_in or v >= cut_out   -> 0 kW
  cut_in <= v < rated_speed    -> rated_kw * (v^3 - cut_in^3) / (rated_speed^3 - cut_in^3)
  rated_speed <= v < cut_out   -> rated_kw

Never negative, never above rated power. Defaults describe a generic 2 MW turbine;
set TURBINE_* env vars on the inference service to change them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PowerCurve:
    rated_kw: float = 2000.0
    cut_in: float = 3.0
    rated_speed: float = 12.0
    cut_out: float = 25.0

    def __post_init__(self):
        if not (0 <= self.cut_in < self.rated_speed < self.cut_out) or self.rated_kw <= 0:
            raise ValueError(f"invalid power curve {self}")

    def power_kw(self, speed: float) -> float:
        if speed < self.cut_in or speed >= self.cut_out:
            return 0.0
        if speed >= self.rated_speed:
            return self.rated_kw
        frac = (speed ** 3 - self.cut_in ** 3) / (self.rated_speed ** 3 - self.cut_in ** 3)
        return self.rated_kw * min(1.0, max(0.0, frac))
