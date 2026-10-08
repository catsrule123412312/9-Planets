"""Global and local grid geometry."""
from dataclasses import dataclass
import math
import numpy as np
@dataclass
class InterpolatedColumn:
    temperature_k: np.ndarray
    pressure_hpa: np.ndarray
    rh: np.ndarray
    u: np.ndarray
    v: np.ndarray
@dataclass
class WorldGrid:
    nlat: int
    nlon: int
    def __post_init__(self):
        self.latitudes = np.linspace(-89.5, 89.5, self.nlat)
        self.longitudes = np.linspace(-180, 180, self.nlon, endpoint=False)
    def nearest_indices(self, latitude: float, longitude: float):
        i = int(np.argmin(abs(self.latitudes-latitude)))
        j = int(np.argmin(abs(((self.longitudes-longitude+180)%360)-180)))
        return i,j
    def interpolate_column(self, atmosphere, latitude: float, longitude: float) -> InterpolatedColumn:
        i,j = self.nearest_indices(latitude, longitude)
        return InterpolatedColumn(
            temperature_k=atmosphere.temperature_k[i,j].copy(),
            pressure_hpa=atmosphere.pressure_hpa[i,j].copy(),
            rh=atmosphere.rh[i,j].copy(),
            u=atmosphere.wind_u[i,j].copy(),
            v=atmosphere.wind_v[i,j].copy(),
        )
@dataclass
class LocalPatch:
    n: int = 33
    spacing_km: float = 1.0
    def coordinates(self):
        half = self.n//2
        axis = (np.arange(self.n)-half)*self.spacing_km
        return np.meshgrid(axis, axis, indexing='xy')
