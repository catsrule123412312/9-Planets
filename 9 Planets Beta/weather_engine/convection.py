"""Deterministic convective diagnostics and conservative adjustment."""
import numpy as np

def lifted_condensation_level(T,rh):
    T=np.asarray(T,float); rh=np.clip(np.asarray(rh,float),1e-5,1); Td=273.15+(T-273.15 - (1-rh)*25)
    return 125*np.maximum(0,T-Td)
def cape_cin(T,rh,z):
    T=np.asarray(T,float); rh=np.clip(np.asarray(rh,float),0,1.2); z=np.asarray(z,float)
    parcel=np.empty_like(T); parcel[0]=T[0]
    for k in range(1,len(T)): parcel[k]=parcel[k-1]-(9.80665/1000 if rh[0]<0.8 else 6.5/1000)*(z[k]-z[k-1])
    Tv_env=T*(1+0.61*(rh*0.02)); Tv_parcel=parcel*(1+0.61*(rh[0]*0.02)); buoy=9.80665*(Tv_parcel-Tv_env)/np.maximum(Tv_env,150)
    cape=np.trapezoid(np.maximum(buoy,0),z); cin=np.trapezoid(np.minimum(buoy,0),z); return float(max(0,cape)),float(min(0,cin))
def convective_depth(T,rh,z):
    cape,cin=cape_cin(T,rh,z); return float(np.clip(3000+1.2*cape-10*abs(cin),0,z[-1]))
def convective_adjust(T,z,q):
    T=np.asarray(T,float).copy(); z=np.asarray(z,float); q=np.asarray(q,float)
    # Last axis is vertical. Works for either one column or a global grid of columns.
    target=np.empty_like(T)
    target[...,0]=T[...,0]
    for k in range(1,T.shape[-1]):
        gamma=np.where(q[...,k-1]>0.008,6.5/1000,9.80665/1000)
        dz=np.asarray(z[...,k]-z[...,k-1] if z.ndim==T.ndim else z[k]-z[k-1],float)
        target[...,k]=target[...,k-1]-gamma*dz
    unstable=T-target>0.5
    if np.any(unstable):
        T=np.where(unstable,np.minimum(T,target+0.25),T)
    return T
def mass_flux_cu(cape,cin,convergence): return np.maximum(0,0.0002*np.asarray(cape)+0.001*np.asarray(convergence)-0.00001*np.abs(np.asarray(cin)))
def cloud_base_height(lcl,cape): return np.maximum(50,np.asarray(lcl)-0.2*np.asarray(cape))
def equilibrium_boundary_layer(T_surface,T_air,wind): return np.clip(80+18*np.maximum(wind,0)+6*(T_surface-T_air),50,2500)
def convective_timescale(depth,w): return np.maximum(20,np.asarray(depth)/np.maximum(np.asarray(w),0.2))
def entrainment_rate(depth): return np.clip(0.0003+1e-7*np.asarray(depth),0.0002,0.001)
def updraft_speed(cape): return np.sqrt(2*np.maximum(np.asarray(cape),0))
def downdraft_speed(precip): return np.clip(0.3*np.sqrt(np.maximum(np.asarray(precip),0)),0,35)
def inhibition_release(cin,forcing): return np.maximum(0,np.asarray(forcing)-np.asarray(cin))
def convective_fraction(cape,lcl,shear): return np.clip(np.asarray(cape)/(np.maximum(np.asarray(cape),1)+300)*np.exp(-np.asarray(lcl)/8000)*(1+0.025*np.asarray(shear)),0,1)
