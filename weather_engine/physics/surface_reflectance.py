"""Deterministic surface reflectance parameterizations.

No random numbers or event probabilities are used.
"""
import numpy as np
import math

def _a(x): return np.asarray(x,dtype=float)

def land_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def water_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def snow_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def ice_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def vegetation_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def soil_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def dust_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def sun_angle_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def wet_soil_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def dry_soil_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def canopy_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def cloud_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def surface_albedo(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def surface_absorptance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def surface_transmittance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def spectral_proxy(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def visible_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def near_ir_reflectance(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def surface_radiative_temperature(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def reflectance_closure(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

