"""Broadband radiative transfer for game-scale atmospheric columns."""
import numpy as np
SIGMA=5.670374419e-8

def gas_absorption_coefficient(co2_ppm,ch4_ppb,n2o_ppb,pressure_hpa):
    p=np.asarray(pressure_hpa,float)/1013.25
    co2=0.017*(1+0.18*np.log(np.maximum(co2_ppm,1)/280))
    ch4=0.007*(1+0.12*np.log(np.maximum(ch4_ppb,1)/722))
    n2o=0.003*(1+0.10*np.log(np.maximum(n2o_ppb,1)/270))
    return p*(co2+ch4+n2o)

def water_vapor_optical_depth(q,pressure_hpa): return 2.2*np.clip(np.asarray(q,float),0,0.05)*(np.asarray(pressure_hpa,float)/500)**0.35
def cloud_optical_depth(cloud_fraction,cloud_water): return 18.0*np.clip(cloud_fraction,0,1)*(1+40*np.maximum(cloud_water,0))
def aerosol_optical_depth(aerosol_index): return 0.15*np.maximum(np.asarray(aerosol_index,float),0)
def total_optical_depth(gas,water,cloud,aerosol): return np.maximum(0,np.asarray(gas)+np.asarray(water)+np.asarray(cloud)+aerosol)
def transmittance(tau): return np.exp(-np.maximum(np.asarray(tau,float),0))
def absorptance(tau): return 1-transmittance(tau)
def longwave_emission(T,tau):
    T=np.maximum(np.asarray(T,float),100); a=np.clip(0.15+0.68*(1-np.exp(-np.maximum(tau,0))),0,0.95); return SIGMA*T**4*(1-a)
def atmospheric_back_radiation(T,tau):
    T=np.maximum(np.asarray(T,float),100); emiss=np.clip(1-np.exp(-np.maximum(tau,0)),0,0.98); return SIGMA*T**4*emiss
def clear_sky_olr(surface_T,atmos_T,tau): return longwave_emission(surface_T,0.2*tau)+0.5*longwave_emission(atmos_T,0.8*tau)
def shortwave_at_surface(toa,albedo,tau_sw): return np.maximum(0,np.asarray(toa,float))*(1-np.clip(albedo,0,1))*np.exp(-np.maximum(tau_sw,0))
def rayleigh_scattering(pressure_hpa,zenith_cos):
    mu=np.maximum(np.asarray(zenith_cos,float),0.02); return 0.12*(np.asarray(pressure_hpa,float)/1013.25)/mu
def beam_path_length(zenith_cos): return 1/np.maximum(np.asarray(zenith_cos,float),0.05)
def aerosol_direct_beam(toa,aod,mu): return np.asarray(toa,float)*np.exp(-np.maximum(aod,0)/np.maximum(mu,0.05))
def two_stream_reflectance(tau,omega0=0.9):
    t=np.maximum(np.asarray(tau,float),0); w=np.clip(omega0,0,1); return np.clip(w*t/(2+0.8*t),0,1)
def emissivity_from_tau(tau): return np.clip(1-np.exp(-np.maximum(np.asarray(tau,float),0)),0,1)
def greenhouse_surface_factor(co2_ppm,ch4_ppb,n2o_ppb):
    co2=np.log1p(np.maximum(co2_ppm,0)/278); ch4=np.sqrt(np.maximum(ch4_ppb,0)/722); n2o=np.sqrt(np.maximum(n2o_ppb,0)/270)
    return np.clip(0.55+0.08*co2+0.035*ch4+0.02*n2o,0.45,0.95)
def outgoing_flux_balance(sw_down,surface_up,atm_down): return np.asarray(sw_down,float)-np.asarray(surface_up,float)+np.asarray(atm_down,float)

def layer_heating_from_flux(flux,pressure_hpa,cp=1004,g=9.80665):
    f=np.asarray(flux,float); p=np.asarray(pressure_hpa,float); grad=np.gradient(f,axis=-1); dp=np.maximum(np.gradient(p,axis=-1),1e-6)
    return -(g/cp)*grad/dp

def radiative_equilibrium_temperature(absorbed_w_m2, emissivity=1): return (np.maximum(absorbed_w_m2,0)/(SIGMA*np.maximum(emissivity,1e-4)))**0.25
def net_surface_radiation(sw_down,lw_down,T_surface,emissivity=0.96): return np.asarray(sw_down,float)+np.asarray(lw_down,float)-emissivity*SIGMA*np.asarray(T_surface,float)**4

def radiative_cooling_time(heat_capacity,T,emissivity=0.96): return np.asarray(heat_capacity,float)/np.maximum(4*emissivity*SIGMA*np.maximum(np.asarray(T,float),100)**3,1e-12)
def spectral_proxy_weights(): return np.array([0.03,0.05,0.08,0.12,0.17,0.21,0.17,0.1,0.05,0.02])
def correlated_k_transmission(k_coeffs,gas_amounts):
    k=np.asarray(k_coeffs,float); g=np.asarray(gas_amounts,float); return np.mean(np.exp(-k*g[...,None]),axis=-1)
def integrate_band_flux(flux,weights=None):
    f=np.asarray(flux,float); w=spectral_proxy_weights() if weights is None else np.asarray(weights,float); return np.sum(f*w,axis=-1)
