"""Deterministic wave ocean parameterizations.

No random numbers or event probabilities are used.
"""
import numpy as np
import math

def _a(x): return np.asarray(x,dtype=float)

def wave_height(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def wave_period(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def wave_length(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def wave_energy(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def wave_roughness(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def wave_stress(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def wave_breaking(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def wave_whitecap(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def wave_evaporation(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def wave_spray(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def wave_momentum(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def wave_heat(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def wave_current_coupling(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def wave_surface_drag(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def wave_stokes_drift(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def wave_group_speed(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def wave_phase_speed(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def wave_fetch(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def wave_age(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def wave_closure(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

