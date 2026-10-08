"""Deterministic fire spread parameterizations.

No random numbers or event probabilities are used.
"""
import numpy as np
import math

def _a(x): return np.asarray(x,dtype=float)

def fire_spread_1(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def fire_spread_2(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def fire_spread_3(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def fire_spread_4(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def fire_spread_5(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def fire_spread_6(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def fire_spread_7(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def fire_spread_8(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def fire_spread_9(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def fire_spread_10(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def fire_spread_11(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def fire_spread_12(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def fire_spread_13(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def fire_spread_14(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

def fire_spread_15(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.sqrt(np.maximum(X,0.0)+1e-12)*(1.0+0.05*np.sqrt(np.maximum(Y,0.0))) - 0.01*Z

def fire_spread_16(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return (X-Y)*np.exp(-0.001*np.abs(Z)) + 0.03*np.cos(Z)

def fire_spread_17(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return X + 0.014*Y - 0.003*Z + 0.02*np.sin(X+Y)

def fire_spread_18(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    scale=np.maximum(np.abs(Y)+1.0,1e-9)
    return np.maximum(0.0,X/scale + 0.1*np.tanh(Z))

def fire_spread_19(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    return np.clip(0.5 + 0.45*np.tanh((X-Y)/(1.0+np.abs(Z))) + 0.02*np.sin(X*Z),0.0,1.0)

def fire_spread_20(x=1.0, y=1.0, z=1.0, dt=1.0):
    """Evaluate one deterministic diagnostic/tendency from model state."""
    X,Y,Z=_a(x),_a(y),_a(z)
    rate=np.maximum(0.0,X)*np.maximum(0.0,Y)
    return rate*np.exp(-0.02*np.abs(Z))

