"""Deterministic advection scalar parameterizations.

No random numbers or event probabilities are used.
"""
import numpy as np
import math

def _a(x): return np.asarray(x,dtype=float)

def advect_temperature(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def advect_humidity(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def advect_cloud(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def advect_aerosol(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def advect_pressure(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def advect_soil_moisture(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def advect_snow(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def advect_ice(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def advect_energy(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def advect_carbon(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def advect_vapor(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def advect_smoke(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def advect_dust(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def advect_precip(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def advect_heat(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def advect_mass(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def advect_trace(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def advect_tendency(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def advect_flux(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def advect_stability(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

