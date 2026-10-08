"""Thermodynamic relationships used throughout the weather model."""
import numpy as np
R_D=287.05; R_V=461.5; CP=1004.0; LV=2.5e6; G=9.80665

def saturation_vapor_pressure(T):
    T=np.asarray(T,dtype=float); Tc=T-273.15
    return 6.112*np.exp((17.67*Tc)/(Tc+243.5))

def mixing_ratio_from_rh(p_hpa,rh,T):
    p=np.maximum(np.asarray(p_hpa,float),1e-4); r=np.clip(np.asarray(rh,float),0,1.5); es=saturation_vapor_pressure(T)
    e=np.minimum(p*0.95,r*es); return 0.622*e/np.maximum(p-e,1e-8)

def rh_from_mixing_ratio(p_hpa,q,T):
    p=np.maximum(np.asarray(p_hpa,float),1e-4); es=saturation_vapor_pressure(T); e=p*q/(0.622+q)
    return np.clip(e/np.maximum(es,1e-9),0,2)

def virtual_temperature(T,q): return np.asarray(T,float)*(1+0.61*np.asarray(q,float))
def theta(T,p_hpa,p0=1000.0): return np.asarray(T,float)*(p0/np.maximum(p_hpa,1e-6))**(R_D/CP)
def temperature_from_theta(th,p_hpa,p0=1000.0): return np.asarray(th,float)*(np.maximum(p_hpa,1e-6)/p0)**(R_D/CP)
def air_density(p_hpa,T,q=0): return (np.asarray(p_hpa,float)*100)/(R_D*virtual_temperature(T,q))
def moist_static_energy(T,z,q): return CP*np.asarray(T,float)+G*np.asarray(z,float)+LV*np.asarray(q,float)
def equivalent_potential_temperature(T,p,q):
    T=np.asarray(T,float); q=np.asarray(q,float); th=theta(T,p); return th*np.exp((LV*q)/(CP*np.maximum(T,150.0)))
def lifted_temperature(T0,rh,delta_z):
    rh=float(np.clip(rh,1e-5,1)); lcl=125*(T0-273.15)*(1-rh)+50
    dry=max(0,min(delta_z,lcl)); moist=max(0,delta_z-lcl)
    return T0-9.80665/1000*dry-6.5/1000*moist
def density_altitude(p,T,q=0): return R_D*virtual_temperature(T,q)*np.log(1013.25/np.maximum(p,1e-6))/G
def scale_height(T): return R_D*np.asarray(T,float)/G
def potential_temperature_gradient(T,z,p=None):
    if p is None: p=np.full_like(T,1000.0)
    return np.gradient(theta(T,p),z)
def hydrostatic_pressure(p_surface,z,T):
    z=np.asarray(z,float); Tv=np.asarray(T,float); out=np.empty_like(Tv); out[0]=p_surface
    for k in range(1,len(z)): out[k]=out[k-1]*np.exp(-G*(z[k]-z[k-1])/(R_D*0.5*(Tv[k]+Tv[k-1])))
    return out

def hydrostatic_height(p_surface,p,T):
    p=np.asarray(p,float); out=np.zeros_like(p); Tv=np.asarray(T,float)
    for k in range(1,len(p)): out[k]=out[k-1]+R_D*0.5*(Tv[k]+Tv[k-1])*np.log(p[k-1]/p[k])/G
    return out

def dewpoint_from_rh(T,rh):
    Tc=np.asarray(T,float)-273.15; r=np.clip(np.asarray(rh,float),1e-6,1)
    a=17.27;b=237.7; gamma=np.log(r)+(a*Tc)/(b+Tc); return 273.15+b*gamma/(a-gamma)
def wet_bulb_approx(T,rh):
    Tc=np.asarray(T,float)-273.15; R=np.clip(np.asarray(rh,float)*100,0,100)
    Tw=Tc*np.arctan(0.151977*np.sqrt(R+8.313659))+np.arctan(Tc+R)-np.arctan(R-1.676331)+0.00391838*R**1.5*np.arctan(0.023101*R)-4.686035
    return Tw+273.15

def clausius_clapeyron_dlnes_dT(T): return LV/(461.5*np.asarray(T,float)**2)
def saturation_mixing_ratio(p,T):
    es=np.minimum(saturation_vapor_pressure(T),np.asarray(p,float)*0.95); return 0.622*es/np.maximum(np.asarray(p,float)-es,1e-8)
def moist_adiabatic_lapse_rate(T,p,q=None):
    T=np.maximum(np.asarray(T,float),150); p=np.maximum(np.asarray(p,float),1); qs=saturation_mixing_ratio(p,T) if q is None else np.maximum(np.asarray(q,float),0)
    num=G*(1+LV*qs/(R_D*T)); den=CP+LV**2*qs*0.622/(R_V*T**2); return num/den

def potential_temperature_with_moisture(T,p,q): return theta(T,p)*np.exp(-LV*q/(CP*np.maximum(T,150)))
def sensible_heat_capacity(q): return CP*(1+0.84*np.maximum(np.asarray(q,float),0))
def latent_energy_per_kg(T): return LV-2300.0*(np.asarray(T,float)-273.15)
def virtual_potential_temperature(T,p,q): return virtual_temperature(theta(T,p),q)
def dry_static_stability(T,z): return G/np.maximum(virtual_temperature(T,0),150)+np.gradient(T,z)
def richardson_bulk(T0,T1,z0,z1,u0,v0,u1,v1):
    dt=virtual_temperature(T1,0)-virtual_temperature(T0,0); shear2=(u1-u0)**2+(v1-v0)**2
    return G*np.asarray(z1-z0)*dt/np.maximum(shear2*virtual_temperature(T0,0),1e-6)
def refractivity(p,T,e): return 77.6*p/np.maximum(T,1)+3.73e5*e/np.maximum(T*T,1)
