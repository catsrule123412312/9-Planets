"""Sun, orbit, axial tilt, and game-specific insolation."""
from dataclasses import dataclass
import math
import numpy as np
@dataclass
class Sun:
    luminosity_units: float = 1e9
    radius_miles: float = 0.86e6
@dataclass
class PlanetOrbit:
    semimajor_miles: float = 93e6
    formula_distance_miles: float = 186e6
    axial_tilt_deg: float = 23.439
    eccentricity: float = 0.0167
    precession_deg: float = 102.9
    def distance_factor(self, orbital_phase: float) -> float:
        e = self.eccentricity
        return (1.0 - e*e) / (1.0 + e*math.cos(orbital_phase))
    def seasonal_declination(self, day_fraction: float) -> float:
        phase = 2*math.pi*day_fraction
        tilt = math.radians(self.axial_tilt_deg)
        return math.degrees(math.asin(math.sin(tilt)*math.sin(phase)))
@dataclass
class SolarSystem:
    sun: Sun
    orbit: PlanetOrbit
    def space_flux_units(self) -> float:
        ratio = self.sun.radius_miles / self.orbit.formula_distance_miles
        return self.sun.luminosity_units * ratio * ratio
    def received_units(self, rotation_deg: float, latitude_deg: float, tilt_offset_deg: float = 0.0) -> float:
        # Preserve the game's requested structure: maximum flux * cos(rotation) * cos(latitude).
        r = math.radians(rotation_deg)
        lat = math.radians(latitude_deg + tilt_offset_deg)
        value = self.space_flux_units() * math.cos(r) * math.cos(lat)
        return max(0.0, value)
    def latitude_flux(self, latitude_deg, t_s: float, day_s: float):
        rotation = ((t_s % day_s) / day_s) * 360.0
        day_fraction = (t_s % day_s) / day_s
        decl = self.orbit.seasonal_declination(day_fraction)
        return self.received_units(rotation, float(np.asarray(latitude_deg).flat[0]), decl)
    def surface_irradiance(self, latitude_deg: float, longitude_deg: float, planet_time_s: float, day_period_s: float, energy_to_celsius: float):
        rotation = ((planet_time_s % day_period_s) / day_period_s) * 360.0
        decl = self.orbit.seasonal_declination((planet_time_s % day_period_s) / day_period_s)
        units = self.received_units(rotation, latitude_deg, decl)
        return {
            "received_units": units,
            "space_flux_units": self.space_flux_units(),
            "rotation_deg": rotation,
            "latitude_deg": latitude_deg,
            "longitude_deg": longitude_deg,
            "solar_temperature_equivalent_c": units / max(1e-9, energy_to_celsius),
            "is_day": units > 0.0,
        }
    def global_mean_flux(self, t_s: float, day_s: float) -> float:
        rotation = ((t_s % day_s) / day_s) * 360.0
        return self.received_units(rotation, 0.0, self.orbit.seasonal_declination((t_s % day_s) / day_s))
