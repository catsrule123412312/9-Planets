"""Deterministic multiscale weather engine for 9 Planets.

This module contains the orchestration layer.  Weather is never sampled from
an event probability table.  State transitions come from deterministic
conservation, threshold, and relaxation equations.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math
import copy
import numpy as np

from .constants import *
from .clock import PlanetClock
from .solar import SolarSystem, Sun, PlanetOrbit
from .grid import WorldGrid, LocalPatch
from .state import GlobalAtmosphere, SurfaceState, RegionalState, WeatherSnapshot
from .thermo import saturation_vapor_pressure, mixing_ratio_from_rh, virtual_temperature
from .greenhouse import greenhouse_retention
from .aerosol import aerosol_optics
from .radiation import longwave_emission, atmospheric_back_radiation
from .surface import surface_albedo, surface_heat_capacity
from .dynamics import advect_scalar, geostrophic_wind, vertical_motion
from .convection import cape_cin, lifted_condensation_level, convective_depth, convective_adjust
from .precipitation import condensation_tendency, precipitation_rate
from .storms import diagnose_storm, storm_intensity
from .effects import event_effects

@dataclass
class EngineConfig:
    global_lat: int = 32
    global_lon: int = 64
    regional_n: int = 33
    regional_spacing_km: float = 1.0
    global_dt_s: float = 30.0
    regional_dt_s: float = 2.0
    forecast_horizon_s: float = 720.0
    game_day_s: float = 720.0
    latitude_deg_per_coordinate: float = 1.0 / 55.0
    coordinate_pole: int = 4950
    sun_energy_units: float = 1_000_000_000.0
    sun_radius_miles: float = 0.86e6
    planet_distance_formula_miles: float = 186.0e6
    planet_orbit_distance_miles: float = 93.0e6
    game_energy_to_celsius: float = 178.0
    game_energy_terawatts: float = 8.0
    axial_tilt_deg: float = 23.439
    diurnal_substep_s: float = 0.5
    deterministic_seed: int = 9

@dataclass
class WeatherEngine:
    cfg: EngineConfig = field(default_factory=EngineConfig)
    solar: SolarSystem = field(init=False)
    clock: PlanetClock = field(init=False)
    grid: WorldGrid = field(init=False)
    atmosphere: GlobalAtmosphere = field(init=False)
    surface: SurfaceState = field(init=False)
    regional_cache: dict[tuple[int,int], RegionalState] = field(default_factory=dict)
    snapshots: dict[tuple[int,int], WeatherSnapshot] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.clock = PlanetClock(day_seconds=self.cfg.game_day_s)
        sun = Sun(
            luminosity_units=self.cfg.sun_energy_units,
            radius_miles=self.cfg.sun_radius_miles,
        )
        orbit = PlanetOrbit(
            semimajor_miles=self.cfg.planet_orbit_distance_miles,
            formula_distance_miles=self.cfg.planet_distance_formula_miles,
            axial_tilt_deg=self.cfg.axial_tilt_deg,
        )
        self.solar = SolarSystem(sun=sun, orbit=orbit)
        self.grid = WorldGrid(self.cfg.global_lat, self.cfg.global_lon)
        self.atmosphere = GlobalAtmosphere.create(self.cfg.global_lat, self.cfg.global_lon)
        self.surface = SurfaceState.create(self.cfg.global_lat, self.cfg.global_lon)
        self.regional_diagnostics = np.zeros((self.cfg.global_lat, self.cfg.global_lon), dtype=np.float64)
        self.nest_candidates = np.zeros((self.cfg.global_lat, self.cfg.global_lon), dtype=bool)
        self.active_nests: dict[tuple[int,int], dict] = {}
        self.coordinate_history: dict[tuple[int,int], dict] = {}

    def coordinate_to_latitude(self, y: float) -> float:
        n = float(self.cfg.coordinate_pole)
        folded = abs(((y % (4.0*n)) - 2.0*n))
        if folded > n:
            folded = 2.0*n - folded
        return folded * self.cfg.latitude_deg_per_coordinate

    def coordinate_to_longitude(self, x: float) -> float:
        # Game world wraps in the synthetic planetary longitude domain.
        width = max(1.0, float(self.cfg.global_lon))
        return ((x % width) / width) * 360.0 - 180.0

    def local_forcing(self, x: int, y: int) -> RegionalState:
        key = (int(x), int(y))
        if key not in self.regional_cache:
            self.regional_cache[key] = RegionalState.create(self.cfg.regional_n)
        return self.regional_cache[key]

    def _solar_for(self, x: int, y: int, t: float) -> dict[str,float]:
        lat = self.coordinate_to_latitude(y)
        lon = self.coordinate_to_longitude(x)
        return self.solar.surface_irradiance(
            latitude_deg=lat,
            longitude_deg=lon,
            planet_time_s=t,
            day_period_s=self.cfg.game_day_s,
            energy_to_celsius=self.cfg.game_energy_to_celsius,
        )

    def _deterministic_surface_forcing(self, x: int, y: int, t: float, reg: RegionalState) -> None:
        """Construct a deterministic mesoscale forcing field over the local patch.

        The field is a physical surrogate for terrain/coastline/airstream structure:
        smooth spatial waves are used instead of random weather draws. The result
        is continuous in time, so storms move and intensify rather than respawning.
        """
        n = len(reg.surface_temperature_field_k) if reg.surface_temperature_field_k is not None else 33
        yy, xx = np.mgrid[0:n, 0:n]
        cx = (n - 1) / 2.0; cy = (n - 1) / 2.0
        rx = (xx - cx); ry = (yy - cy)
        dist = np.sqrt(rx*rx + ry*ry)
        phase = 2.0*np.pi*(t / max(self.cfg.game_day_s, 1.0))
        spatial = 0.012*float(x) + 0.009*float(y)
        thermal_wave = np.sin(phase + 0.035*rx + 0.021*ry + spatial)
        secondary = np.cos(0.017*rx - 0.031*ry - 0.7*phase + 0.4*spatial)
        front = np.tanh((rx*np.cos(phase) + ry*np.sin(phase))/5.5)
        lat = self.coordinate_to_latitude(y)
        seasonal = self.solar.orbit.seasonal_declination((t % self.cfg.game_day_s)/max(self.cfg.game_day_s,1.0))
        base_t = 288.15 - 28.0*(abs(lat)/90.0)**1.35 + 6.0*np.cos(np.radians(lat-seasonal))
        diurnal = 4.8*thermal_wave + 1.8*secondary - 3.2*front
        reg.surface_temperature_field_k[:] = base_t + diurnal - 0.025*dist**1.2
        reg.surface_temperature_k = float(reg.surface_temperature_field_k[cy.astype(int) if hasattr(cy, 'astype') else int(cy), cx.astype(int) if hasattr(cx, 'astype') else int(cx)])
        rh = np.clip(0.62 + 0.18*secondary - 0.10*front + 0.06*np.sin(phase+0.04*dist), 0.15, 1.08)
        reg.surface_rh_field[:] = rh
        pressure = 1013.25 - 4.5*front - 1.5*thermal_wave + 0.03*dist**1.25
        reg.surface_pressure_field_hpa[:] = pressure
        u = 7.0 + 9.0*thermal_wave + 5.0*front + 0.8*secondary
        v = 2.0 + 7.0*secondary - 4.0*front + 0.6*thermal_wave
        reg.surface_u_field[:] = u
        reg.surface_v_field[:] = v
        convergence = np.maximum(0.0, 0.065*front + 0.025*secondary + 0.015*np.sin(phase+0.08*rx))
        shear = 8.0 + 7.0*np.abs(front) + 4.0*np.abs(secondary) + 0.8*np.maximum(0,dist-10)/10
        shear += 10.0*np.abs(np.sin(phase + np.radians(lat)*2.0 + 0.014*float(x) - 0.011*float(y)))
        cape = np.maximum(0.0, (reg.surface_temperature_field_k-278.0)*90.0 + (rh-0.55)*3200.0 + 600*convergence)
        cape *= np.clip(1.0 - 0.08*abs(lat)/90.0, 0.35, 1.0)
        reg.convergence_field[:] = convergence
        reg.shear_field_m_s[:] = shear
        reg.cape_field_j_kg[:] = cape
        reg.rain_field_mm_h[:] = np.maximum(0.0, 0.015*(cape-350.0) + 5.5*convergence + 0.3*np.maximum(secondary,0))
        reg.vorticity_field[:] = 0.0003*np.gradient(v, axis=1) - 0.0003*np.gradient(u, axis=0)
        cloud = np.clip(0.25 + 0.5*rh + 0.15*np.tanh((cape-400)/700), 0.0, 1.0)
        reg.cloud_fraction[:] = np.clip(cloud.mean()*0.2 + 0.8*cloud.mean(), 0.0, 1.0)

    def _regional_hotspot_summary(self, t: float) -> None:
        """Run the inexpensive everywhere-regional diagnostic on every global cell."""
        nlat,nlon=self.cfg.global_lat,self.cfg.global_lon
        lat_field=self.grid.latitudes[:,None]
        phase=2*np.pi*(t/max(self.cfg.game_day_s,1.0))
        thermal=np.sin(phase+np.radians(lat_field))
        moist=np.clip(0.72-0.25*(np.abs(lat_field)/90)+0.08*np.cos(phase+lat_field/20),0.05,1.0)
        convergence=np.maximum(0.0,0.03*np.cos(phase+lat_field/15)+0.025*np.sin(2*phase+lat_field/33))
        cape=np.maximum(0.0,(302-0.34*np.abs(lat_field)+5*thermal-286)*110 + (moist-0.55)*3600)
        shear=8+10*np.abs(np.sin(np.radians(lat_field)+phase))
        score=(cape/1000)+shear/15+convergence*35+moist
        self.regional_diagnostics[:] = score
        self.nest_candidates[:] = (cape>1200) & (convergence>0.025) & (shear>14)

    def _promote_local_nest(self, x:int, y:int, snapshot:WeatherSnapshot) -> None:
        """Promote a physically strong global/regional cell to a high-resolution nest."""
        if snapshot.storm_intensity in {'heavy','severe','violent'}:
            self.active_nests[(int(x),int(y))] = {
                'x':int(x),'y':int(y),'started_s':self.clock.time_s,
                'intensity':snapshot.storm_intensity,'rain_rate_mm_h':snapshot.rain_rate_mm_h,
                'cape_j_kg':snapshot.cape_j_kg,'shear_m_s':snapshot.wind_speed_m_s}

    def _advance_global(self, dt: float, t: float) -> None:
        sol = self.solar.global_mean_flux(t, self.cfg.game_day_s)
        self._regional_hotspot_summary(t)
        lat = self.grid.latitudes[:, None]
        solar = self.solar.latitude_flux(lat, t, self.cfg.game_day_s)
        rh = np.clip(self.atmosphere.rh, 0.0, 1.2)
        q = mixing_ratio_from_rh(self.atmosphere.pressure_hpa, rh, self.atmosphere.temperature_k)
        water_vapor = np.clip(q, 0.0, 0.05)
        retention = greenhouse_retention(
            co2_ppm=self.atmosphere.co2_ppm,
            ch4_ppb=self.atmosphere.ch4_ppb,
            n2o_ppb=self.atmosphere.n2o_ppb,
            water_vapor=water_vapor,
            cloud_fraction=self.atmosphere.cloud_fraction,
            pressure_hpa=self.atmosphere.pressure_hpa,
        )
        tau = retention.total_optical_depth
        olr = longwave_emission(self.atmosphere.temperature_k, tau)
        back = atmospheric_back_radiation(self.atmosphere.temperature_k, tau)
        shortwave_column = solar * (1.0 - self.surface.albedo)
        profile_weight = np.exp(-self.atmosphere.height_k / 4500.0)
        profile_weight = profile_weight / np.maximum(profile_weight.sum(axis=2, keepdims=True), 1e-12)
        net = shortwave_column[..., None] * profile_weight + back - olr
        self.atmosphere.temperature_k += dt * net / self.atmosphere.heat_capacity_j_m2k
        self.atmosphere.temperature_k = convective_adjust(
            self.atmosphere.temperature_k,
            self.atmosphere.height_k,
            water_vapor,
        )
        self.atmosphere.pressure_hpa = np.maximum(
            1.0,
            self.atmosphere.surface_pressure_hpa[...,None] * np.exp(-self.atmosphere.height_k / SCALE_HEIGHT_M),
        )
        self.atmosphere.wind_u, self.atmosphere.wind_v = geostrophic_wind(
            self.atmosphere.temperature_k, self.atmosphere.pressure_hpa, self.grid.latitudes
        )
        self.atmosphere.omega = vertical_motion(
            self.atmosphere.wind_u, self.atmosphere.wind_v, self.grid.latitudes
        )
        self.atmosphere.time_s = t
        self.atmosphere.global_solar_w_m2 = sol

    def _advance_regional(self, x: int, y: int, dt: float, t: float, reg_override=None, record: bool=True, promote: bool=True) -> WeatherSnapshot:
        reg = reg_override if reg_override is not None else self.local_forcing(x, y)
        self._deterministic_surface_forcing(x, y, t, reg)
        lat = self.coordinate_to_latitude(y)
        lon = self.coordinate_to_longitude(x)
        sol = self._solar_for(x, y, t)
        parent = self.grid.interpolate_column(self.atmosphere, lat, lon)
        reg.temperature_k[:] = parent.temperature_k
        reg.pressure_hpa[:] = parent.pressure_hpa
        reg.rh[:] = parent.rh
        reg.u[:] = parent.u
        reg.v[:] = parent.v
        reg.cloud_fraction[:] = np.clip(0.5*np.exp(-reg.height_k/7000.0),0,1)
        reg.surface_temperature_k = float(np.clip(reg.surface_temperature_k, 180.0, 340.0))
        sea_level_temp = reg.temperature_k[0]
        center_idx = reg.surface_rh_field.shape[0]//2 if reg.surface_rh_field is not None else 0
        rh0 = float(np.clip(reg.surface_rh_field[center_idx, center_idx] if reg.surface_rh_field is not None else reg.rh[0], 0.0, 1.2))
        q0 = float(mixing_ratio_from_rh(np.array([reg.pressure_hpa[0]]), np.array([rh0]), np.array([sea_level_temp]))[0])
        theta_v = virtual_temperature(sea_level_temp, q0)
        parcel_lcl = lifted_condensation_level(sea_level_temp, rh0)
        cape, cin = cape_cin(reg.temperature_k, reg.rh, reg.height_k)
        depth = convective_depth(reg.temperature_k, reg.rh, reg.height_k)
        condensation = condensation_tendency(reg.rh, reg.temperature_k, reg.pressure_hpa, dt)
        rain = precipitation_rate(condensation, reg.cloud_water, reg.temperature_k, dt)
        ret = greenhouse_retention(
            co2_ppm=self.atmosphere.co2_ppm,
            ch4_ppb=self.atmosphere.ch4_ppb,
            n2o_ppb=self.atmosphere.n2o_ppb,
            water_vapor=np.asarray(reg.rh) * 0.02,
            cloud_fraction=np.asarray(reg.cloud_fraction),
            pressure_hpa=np.asarray(reg.pressure_hpa),
        )
        albedo = surface_albedo(reg.surface_type, reg.snow_fraction, reg.ice_fraction, reg.dust_loading)
        heatcap = 4.0e8 if reg.surface_type == "ocean" else 1.1e7 + 2.0e7*float(np.asarray(reg.soil_moisture).mean())
        shortwave = sol["received_units"] * (1.0 - albedo)
        longwave_down = float(np.asarray(atmospheric_back_radiation(np.asarray([reg.temperature_k[0]]), np.asarray([ret.total_optical_depth[0]]))).flat[0])
        emitted = float(np.asarray(longwave_emission(np.asarray([reg.surface_temperature_k]), np.asarray([ret.total_optical_depth[0]]))).flat[0])
        ground_net = shortwave + longwave_down - emitted
        reg.surface_temperature_k += dt * ground_net / max(1.0, heatcap)
        reg.soil_moisture = np.clip(reg.soil_moisture + rain * dt - 0.00001 * sol["received_units"] * dt, 0.0, 1.0)
        reg.rh[:] = np.clip(reg.rh[:] + condensation * dt, 0.0, 1.2)
        reg.cloud_water[:] = np.maximum(0.0, reg.cloud_water[:] + condensation * dt - rain * 0.001)
        reg.cloud_fraction[:] = np.clip(reg.cloud_fraction[:] + 0.15 * condensation * dt, 0.0, 1.0)
        reg.u[:], reg.v[:] = advect_scalar(reg.u, reg.v, reg.temperature_k, reg.rh, dt, self.cfg.regional_spacing_km)
        reg.u[:] = np.clip(reg.u, -120.0, 120.0)
        reg.v[:] = np.clip(reg.v, -120.0, 120.0)
        reg.time_s = t
        center=(reg.surface_rh_field.shape[0]//2, reg.surface_rh_field.shape[1]//2) if reg.surface_rh_field is not None else (0,0)
        local_cape=float(reg.cape_field_j_kg[center]) if reg.cape_field_j_kg is not None else cape
        local_conv=float(reg.convergence_field[center]) if reg.convergence_field is not None else reg.convergence()
        local_shear=float(reg.shear_field_m_s[center]) if reg.shear_field_m_s is not None else reg.bulk_shear()
        local_vort=float(reg.vorticity_field[center]) if reg.vorticity_field is not None else reg.vorticity()
        local_rain=float(reg.rain_field_mm_h[center]) if reg.rain_field_mm_h is not None else rain
        storm = diagnose_storm(
            cape=local_cape,
            cin=cin,
            shear=local_shear,
            vorticity=local_vort,
            convergence=local_conv,
            lcl_m=parcel_lcl,
            precipitable_water=reg.precipitable_water(),
            surface_temp_k=reg.surface_temperature_k,
        )
        intensity = storm_intensity(storm)
        snapshot = WeatherSnapshot.from_regional(
            x=x, y=y, latitude=lat, longitude=lon,
            solar=sol,
            surface_temperature_k=reg.surface_temperature_k,
            atmospheric_temperature_k=float(np.mean(reg.temperature_k[:8])),
            humidity=rh0,
            wind_u=float(reg.surface_u_field[center]), wind_v=float(reg.surface_v_field[center]),
            rain_rate=local_rain,
            cloud_fraction=float(np.mean(reg.cloud_fraction[:8])),
            cape=local_cape, cin=cin, lcl_m=parcel_lcl, storm_intensity=intensity,
            dust=reg.dust_loading,
            co2_ppm=self.atmosphere.co2_ppm,
            ch4_ppb=self.atmosphere.ch4_ppb,
            n2o_ppb=self.atmosphere.n2o_ppb,
            thermal_emission_w_m2=float(emitted),
            atmospheric_retention=float(np.mean(ret.retained_fraction)),
        )
        if record:
            self.snapshots[(x, y)] = snapshot
            if promote:
                self._promote_local_nest(x, y, snapshot)
            self.coordinate_history[(int(x),int(y))] = {'last_time_s':t,'snapshot':snapshot.as_dict()}
        return snapshot

    def tick(self, dt: float, x: int = 0, y: int = 0) -> WeatherSnapshot:
        """Advance the physical system without any random weather sampling."""
        dt = max(0.0, float(dt))
        if dt == 0.0:
            return self.snapshots.get((x, y), self._advance_regional(x, y, 0.0, self.clock.time_s))
        start = self.clock.time_s
        end = start + dt
        t = start
        while t < end - 1e-12:
            step = min(self.cfg.global_dt_s, end - t)
            self.clock.advance(step)
            t = self.clock.time_s
            self._advance_global(step, t)
        current_snapshot = self._advance_regional(x, y, 0.0, t, record=True, promote=True)
        forecast_reg = copy.deepcopy(self.local_forcing(x, y))
        forecast_end = t + self.cfg.forecast_horizon_s
        local_t = t
        forecast_snapshot = current_snapshot
        while local_t < forecast_end - 1e-12:
            step = min(self.cfg.regional_dt_s, forecast_end - local_t)
            local_t += step
            forecast_snapshot = self._advance_regional(x, y, step, local_t, reg_override=forecast_reg, record=False, promote=False)
        self.forecasts = getattr(self, 'forecasts', {})
        self.forecasts[(int(x),int(y))] = forecast_snapshot
        return current_snapshot

    def ingest_player_action(self, action: str, magnitude: float = 1.0, x: int = 0, y: int = 0) -> dict:
        """Apply deterministic environment changes caused by gameplay."""
        action = str(action).lower().strip()
        m = max(0.0, float(magnitude))
        if action in {"burn_oil", "oil_fire", "burn_petroleum"}:
            # Combustion source is deterministic and proportional to burned mass.
            self.atmosphere.co2_ppm += 0.00286 * m
            self.atmosphere.ch4_ppb += 0.0012 * m
            self.atmosphere.n2o_ppb += 0.00005 * m
            self.atmosphere.aerosol_index += 0.002 * m
            self.local_forcing(x, y).dust_loading = np.clip(self.local_forcing(x, y).dust_loading + 0.01*m, 0, 4)
        elif action in {"burn_wood", "campfire"}:
            self.atmosphere.co2_ppm += 0.00042 * m
            self.atmosphere.aerosol_index += 0.0005*m
        elif action in {"water_plant", "irrigate"}:
            self.local_forcing(x, y).soil_moisture = min(1.0, self.local_forcing(x, y).soil_moisture + 0.08*m)
        elif action in {"remove_vegetation", "clear_forest"}:
            self.local_forcing(x, y).vegetation_fraction = max(0.0, self.local_forcing(x, y).vegetation_fraction - 0.04*m)
        elif action in {"add_dust", "dust"}:
            self.local_forcing(x, y).dust_loading = min(4.0, self.local_forcing(x, y).dust_loading + 0.02*m)
            self.atmosphere.aerosol_index += 0.003*m
        self.atmosphere.co2_ppm = max(0.0, self.atmosphere.co2_ppm)
        return {"action": action, "magnitude": m, "co2_ppm": self.atmosphere.co2_ppm, "aerosol_index": self.atmosphere.aerosol_index}

    def event_for_snapshot(self, snapshot: WeatherSnapshot) -> dict:
        return event_effects(snapshot)

    def diagnostics(self, x: int = 0, y: int = 0) -> dict:
        s = self.snapshots.get((x, y))
        if s is None:
            s = self.tick(0.0, x, y)
        return s.as_dict()
