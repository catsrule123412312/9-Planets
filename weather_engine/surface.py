"""Land/ocean/snow surface energy partitioning."""
import numpy as np

def surface_albedo(surface_type,snow_fraction,ice_fraction,dust_loading):
    st=np.asarray(surface_type); snow=np.clip(np.asarray(snow_fraction,float),0,1); ice=np.clip(np.asarray(ice_fraction,float),0,1); dust=np.maximum(np.asarray(dust_loading,float),0)
    base=np.where(st=='ocean',0.08,np.where(st=='desert',0.35,np.where(st=='forest',0.14,0.22)))
    alb=base*(1-snow-ice)+0.82*snow+0.55*ice
    alb=np.clip(alb-0.03*np.minimum(dust,3)*snow,0.02,0.95); return alb

def surface_heat_capacity(surface_type,soil_moisture):
    st=np.asarray(surface_type); wet=np.clip(np.asarray(soil_moisture,float),0,1)
    return np.where(st=='ocean',4.0e8,np.where(st=='snow',1.2e7,1.1e7+2e7*wet))
def sensible_heat_flux(h,T_surface,T_air): return np.maximum(0,np.asarray(h,float))* (np.asarray(T_surface,float)-np.asarray(T_air,float))
def latent_heat_flux(rho,lv,evaporation): return np.maximum(0,np.asarray(rho,float))*lv*np.maximum(np.asarray(evaporation,float),0)
def net_radiation(sw,lw_down,T,emissivity=0.96): return np.asarray(sw,float)+np.asarray(lw_down,float)-emissivity*5.670374419e-8*np.asarray(T,float)**4
def aerodynamic_resistance(wind_speed,roughness): return 1/np.maximum(0.5*np.maximum(wind_speed,0)+1e-3,1e-3)*np.maximum(roughness,0.01)
def evapotranspiration(soil_moisture,rh,wind,net_rad):
    s=np.clip(np.asarray(soil_moisture,float),0,1); dry=np.clip(1-np.asarray(rh,float),0,1); w=np.maximum(np.asarray(wind,float),0); r=np.maximum(np.asarray(net_rad,float),0)
    return 1e-6*r*s*(0.4+0.08*w)*dry
def roughness_length(surface_type):
    st=np.asarray(surface_type)
    return np.where(st=='forest',1.5,np.where(st=='grass',0.05,np.where(st=='desert',0.002,np.where(st=='ocean',0.0002,0.03))))
def momentum_drag_coefficient(z0,wind): return (0.4/np.log(10/np.maximum(z0,1e-6)))**2
def ground_conduction(T_surface,T_deep,k,depth): return np.asarray(k,float)*(np.asarray(T_surface,float)-np.asarray(T_deep,float))/np.maximum(np.asarray(depth,float),0.01)
def stomatal_conductance(soil_moisture,vpd,light):
    return 0.2*np.clip(np.asarray(soil_moisture,float),0,1)*np.exp(-0.15*np.maximum(np.asarray(vpd,float),0))*np.tanh(np.maximum(np.asarray(light,float),0)/300)
def leaf_area_index(vegetation_fraction,soil_moisture,T):
    thermal=np.clip(1-np.abs(np.asarray(T,float)-295)/35,0,1); return 6*np.clip(np.asarray(vegetation_fraction,float),0,1)*np.clip(np.asarray(soil_moisture,float),0,1)*thermal
