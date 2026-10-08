"""Deterministic 12-minute planetary rotation clock."""
from dataclasses import dataclass
import math
@dataclass
class PlanetClock:
    day_seconds: float = 720.0
    time_s: float = 0.0
    def advance(self, dt: float) -> None:
        self.time_s += max(0.0, float(dt))
    @property
    def fraction_of_day(self) -> float:
        return (self.time_s % self.day_seconds) / self.day_seconds
    @property
    def rotation_degrees(self) -> float:
        return self.fraction_of_day * 360.0
    @property
    def sun_angle_deg(self) -> float:
        return self.rotation_degrees
    @property
    def hour_angle_rad(self) -> float:
        return math.radians(self.rotation_degrees - 180.0)
    @property
    def is_day(self) -> bool:
        return self.rotation_degrees < 180.0
