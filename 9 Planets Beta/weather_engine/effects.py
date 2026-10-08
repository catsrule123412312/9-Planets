"""Legacy-compatible weather event/effect translator.

The old 9 Planets weather system remains useful here: it knows what the game
should do when rain, storms, drought, lightning, tornadoes, or blizzards exist.
This module supplies deterministic event magnitudes from the physical engine.
"""

def event_effects(snapshot):
    rain=snapshot.rain_rate_mm_h
    wind=snapshot.wind_speed_m_s
    intensity='clear'
    if snapshot.storm_intensity=='violent': intensity='violent_storm'
    elif snapshot.storm_intensity=='severe': intensity='heavy_storm'
    elif snapshot.storm_intensity=='heavy': intensity='medium_storm'
    elif rain>=2.5: intensity='moderate_rain'
    elif rain>0.1: intensity='light_rain'
    if snapshot.latitude>70 and snapshot.temperature_c<0 and snapshot.wind_speed_m_s>12: intensity='blizzard'
    return {'weather':intensity,'rain_mm_h':rain,'wind_m_s':wind,'lightning':snapshot.storm_intensity in {'severe','violent'},'tornado':snapshot.storm_intensity=='violent'}

def precipitation_class(snapshot):
    r=snapshot.rain_rate_mm_h
    return 'heavy' if r>=12 else 'moderate' if r>=2.5 else 'light' if r>0.1 else 'none'
def wind_class(snapshot):
    w=snapshot.wind_speed_m_s; return 'severe' if w>=32 else 'strong' if w>=22 else 'moderate' if w>=12 else 'light'
def temperature_class(snapshot):
    t=snapshot.surface_temperature_c; return 'extreme_cold' if t<=-20 else 'cold' if t<5 else 'warm' if t>=25 else 'mild'
def sky_tint_from_dust(dust,is_day):
    if not is_day:return 'night'
    d=max(0.0,min(4.0,float(dust)))
    return 'dusty_amber' if d<1 else 'amber' if d<2 else 'deep_amber' if d<3 else 'brown_orange'
