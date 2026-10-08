"""Deterministic boundary stability parameterizations.

No random numbers or event probabilities are used.
"""
import numpy as np
import math

def _a(x): return np.asarray(x,dtype=float)

def stability_richardson(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def stability_Obukhov(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def stability_mixing(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def stability_exchange(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def stability_lapse(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def stability_inversion(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def stability_convective(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def stability_neutral(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def stability_surface(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def stability_cloud(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def stability_turbulence(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def stability_shear(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def stability_heat(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def stability_moisture(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def stability_length(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def stability_timescale(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def stability_flux(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def stability_layer(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def stability_transition(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def stability_closure(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

