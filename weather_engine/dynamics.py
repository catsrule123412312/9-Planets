"""Reduced-order horizontal and vertical atmospheric dynamics."""
import numpy as np

def geostrophic_wind(T,p,latitudes):
    T=np.asarray(T,float); p=np.asarray(p,float); lat=np.asarray(latitudes,float)
    nlat,nlon,nlev=T.shape; phi=np.radians(lat)[:,None,None]; f=2*7.2921159e-5*np.sin(phi); f=np.where(np.abs(f)<1e-5,np.where(f>=0,1e-5,-1e-5),f)
    pressure_gradient=np.gradient(np.log(np.maximum(p,1)),axis=1)
    thermal_gradient=np.gradient(T,axis=1)
    u=-287.05*np.maximum(T,180)*pressure_gradient/(f*1e5)
    v=287.05*np.maximum(T,180)*thermal_gradient/(f*1e5)
    u=np.nan_to_num(u);v=np.nan_to_num(v); return u,v

def horizontal_laplacian(a,dx=1):
    a=np.asarray(a,float); dx=float(dx); return (np.roll(a,-1,axis=-2)+np.roll(a,1,axis=-2)+np.roll(a,-1,axis=-1)+np.roll(a,1,axis=-1)-4*a)/(dx*dx)
def diffusion(a,coef,dt,dx=1): return np.asarray(a,float)+max(0,float(dt))*float(coef)*horizontal_laplacian(a,dx)
def advect_scalar(u,v,scalar,moisture,dt,dx):
    s=np.asarray(scalar,float); q=np.asarray(moisture,float); u=np.asarray(u,float); v=np.asarray(v,float)
    du=np.gradient(s,axis=0); dv=np.gradient(s,axis=0)
    return u-0.001*dt*du, v-0.001*dt*dv
def vertical_motion(u,v,latitudes):
    div=np.gradient(u,axis=1)+np.gradient(v,axis=0); return -0.03*div
def thermal_wind(T,z,lat):
    dTdy=np.gradient(np.asarray(T,float),axis=0); f=2*7.2921159e-5*np.sin(np.radians(np.asarray(lat,float)))[:,None]
    return -287.05*np.nan_to_num(dTdy)/np.where(abs(f)>1e-5,f,1e-5)
def coriolis_acceleration(u,v,lat):
    f=2*7.2921159e-5*np.sin(np.radians(np.asarray(lat,float)))
    return f[...,None]*v,-f[...,None]*u
def surface_friction(u,v,roughness,dt):
    drag=np.clip(0.001+0.004*np.sqrt(np.maximum(roughness,0)),0.0005,0.03)
    fac=np.exp(-drag*max(float(dt),0)/60); return u*fac,v*fac
def pressure_tendency(divergence,dt): return -0.9*np.asarray(divergence,float)*max(float(dt),0)
def omega_from_convergence(convergence): return -0.1*np.asarray(convergence,float)
def mass_flux(w,rho,area): return np.asarray(w,float)*np.asarray(rho,float)*np.asarray(area,float)
def vorticity_from_winds(u,v,dx=1,dy=1): return np.gradient(v,dx,axis=-1)-np.gradient(u,dy,axis=-2)
def convergence_from_winds(u,v,dx=1,dy=1): return -(np.gradient(u,dx,axis=-1)+np.gradient(v,dy,axis=-2))
def ageostrophic_wind(u,v,drag,dt): return np.asarray(u)*np.exp(-drag*dt),np.asarray(v)*np.exp(-drag*dt)
def divergence_free_projection(u,v,iters=8):
    u=np.asarray(u,float).copy();v=np.asarray(v,float).copy()
    for _ in range(max(1,int(iters))):
        div=convergence_from_winds(u,v);u+=0.02*np.gradient(div,axis=-1);v+=0.02*np.gradient(div,axis=-2)
    return u,v
