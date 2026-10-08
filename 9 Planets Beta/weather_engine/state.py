"""State containers for global, surface, regional, and weather layers."""
from dataclasses import dataclass, asdict
import numpy as np
from .constants import DEFAULT_GLOBAL_HEAT_CAP, P0_HPA
@dataclass
class GlobalAtmosphere:
    temperature_k: np.ndarray
    pressure_hpa: np.ndarray
    rh: np.ndarray
    wind_u: np.ndarray
    wind_v: np.ndarray
    omega: np.ndarray
    height_k: np.ndarray
    cloud_fraction: np.ndarray
    surface_pressure_hpa: np.ndarray
    surface_temperature_k: np.ndarray
    heat_capacity_j_m2k: float
    co2_ppm: float = 420.0
    ch4_ppb: float = 1900.0
    n2o_ppb: float = 336.0
    aerosol_index: float = 0.15
    time_s: float = 0.0
    global_solar_w_m2: float = 0.0
    @classmethod
    def create(cls, nlat:int, nlon:int, nlev:int=24):
        z = np.linspace(0.0, 16000.0, nlev)
        base = 288.15 - 6.5*(z/1000.0)
        T = np.broadcast_to(base[None,None,:], (nlat,nlon,nlev)).copy()
        P = P0_HPA*np.exp(-z[None,None,:]/8400.0)
        P = np.broadcast_to(P,(nlat,nlon,nlev)).copy()
        rh = np.full((nlat,nlon,nlev),0.65)
        u = np.zeros_like(T); v=np.zeros_like(T); omega=np.zeros_like(T)
        cf=np.clip(0.55*np.exp(-z/7000.0),0,1)[None,None,:]
        cf=np.broadcast_to(cf,(nlat,nlon,nlev)).copy()
        sp=np.full((nlat,nlon),P0_HPA)
        st=np.full((nlat,nlon),288.15)
        return cls(T,P,rh,u,v,omega,np.broadcast_to(z,(nlat,nlon,nlev)).copy(),cf,sp,st,DEFAULT_GLOBAL_HEAT_CAP)
@dataclass
class SurfaceState:
    albedo: np.ndarray
    soil_moisture: np.ndarray
    snow_fraction: np.ndarray
    ice_fraction: np.ndarray
    vegetation_fraction: np.ndarray
    dust_loading: np.ndarray
    surface_type: np.ndarray
    @classmethod
    def create(cls,nlat:int,nlon:int):
        return cls(np.full((nlat,nlon),0.3),np.full((nlat,nlon),0.5),np.zeros((nlat,nlon)),np.zeros((nlat,nlon)),np.full((nlat,nlon),0.6),np.full((nlat,nlon),0.15),np.full((nlat,nlon),'land',dtype=object))
@dataclass
class RegionalState:
    temperature_k: np.ndarray
    pressure_hpa: np.ndarray
    rh: np.ndarray
    u: np.ndarray
    v: np.ndarray
    cloud_fraction: np.ndarray
    cloud_water: np.ndarray
    height_k: np.ndarray
    soil_moisture: float
    snow_fraction: float
    ice_fraction: float
    vegetation_fraction: float
    dust_loading: float
    surface_type: str
    surface_temperature_k: float
    time_s: float = 0.0
    surface_temperature_field_k: np.ndarray | None = None
    surface_pressure_field_hpa: np.ndarray | None = None
    surface_rh_field: np.ndarray | None = None
    surface_u_field: np.ndarray | None = None
    surface_v_field: np.ndarray | None = None
    rain_field_mm_h: np.ndarray | None = None
    cape_field_j_kg: np.ndarray | None = None
    convergence_field: np.ndarray | None = None
    shear_field_m_s: np.ndarray | None = None
    vorticity_field: np.ndarray | None = None
    @classmethod
    def create(cls,n:int=33,nlev:int=24):
        z=np.linspace(0,16000,nlev)
        T=288.15-6.5*z/1000
        P=P0_HPA*np.exp(-z/8400)
        empty=np.zeros((n,n),dtype=float)
        center=np.full((n,n),288.15,dtype=float)
        return cls(T.copy(),P.copy(),np.full(nlev,0.65),np.zeros(nlev),np.zeros(nlev),np.clip(0.5*np.exp(-z/7000),0,1),np.zeros(nlev),z.copy(),0.5,0,0,0.6,0.15,'land',288.15,0.0,center,np.full((n,n),P0_HPA),np.full((n,n),0.65),empty.copy(),empty.copy(),empty.copy(),empty.copy(),empty.copy(),empty.copy(),empty.copy())
    def bulk_shear(self):
        return float(np.hypot(self.u[-1]-self.u[0], self.v[-1]-self.v[0]))
    def vorticity(self):
        return float(np.gradient(self.v, self.height_k).mean()-np.gradient(self.u,self.height_k).mean())
    def convergence(self):
        return float(max(0.0,-np.gradient(self.u,self.height_k).mean()-np.gradient(self.v,self.height_k).mean()))
    def precipitable_water(self):
        return float(np.trapezoid(self.rh*0.02,self.height_k)/9.80665)
@dataclass
class WeatherSnapshot:
    x:int; y:int; latitude:float; longitude:float
    received_units:float; space_flux_units:float; rotation_deg:float; is_day:bool
    surface_temperature_c:float; atmospheric_temperature_c:float; humidity:float
    wind_speed_m_s:float; wind_direction_deg:float; rain_rate_mm_h:float
    cloud_fraction:float; cape_j_kg:float; cin_j_kg:float; lcl_m:float
    storm_intensity:str; dust:float; co2_ppm:float; ch4_ppb:float; n2o_ppb:float
    thermal_emission_w_m2:float; atmospheric_retention:float
    @classmethod
    def from_regional(cls,**kw):
        wu,wv=kw.pop('wind_u'),kw.pop('wind_v')
        speed=float(np.hypot(wu,wv)); direction=float((np.degrees(np.arctan2(-wu,-wv))+360)%360)
        return cls(
            x=kw['x'],y=kw['y'],latitude=kw['latitude'],longitude=kw['longitude'],
            received_units=kw['solar']['received_units'],space_flux_units=kw['solar']['space_flux_units'],rotation_deg=kw['solar']['rotation_deg'],is_day=kw['solar']['is_day'],
            surface_temperature_c=kw['surface_temperature_k']-273.15,atmospheric_temperature_c=kw['atmospheric_temperature_k']-273.15,humidity=kw['humidity'],wind_speed_m_s=speed,wind_direction_deg=direction,rain_rate_mm_h=max(0.0,kw['rain_rate']),cloud_fraction=kw['cloud_fraction'],cape_j_kg=max(0.0,kw['cape']),cin_j_kg=kw['cin'],lcl_m=max(0.0,kw['lcl_m']),storm_intensity=kw['storm_intensity'],dust=kw['dust'],co2_ppm=kw['co2_ppm'],ch4_ppb=kw['ch4_ppb'],n2o_ppb=kw['n2o_ppb'],thermal_emission_w_m2=kw['thermal_emission_w_m2'],atmospheric_retention=float(np.clip(kw['atmospheric_retention'],0,1)))
    def as_dict(self): return asdict(self)
