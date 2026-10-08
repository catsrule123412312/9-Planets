import importlib.util, math, pathlib, sys
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from weather_engine import create_engine, EngineConfig

def test_sun_calibration():
    e=create_engine(global_lat=8,global_lon=16,regional_n=17,forecast_horizon_s=0)
    assert math.isclose(e.solar.space_flux_units(),21378.19401086831,rel_tol=1e-12)

def test_12_minute_day():
    e=create_engine(forecast_horizon_s=0)
    vals=[e.solar.surface_irradiance(0,0,t,720,178)['received_units'] for t in (0,180,360,540,720)]
    assert vals[0]>20000
    assert vals[2]==0.0
    assert math.isclose(vals[4],vals[0],rel_tol=1e-12)

def test_deterministic_same_state():
    e=create_engine(global_lat=8,global_lon=16,regional_n=17,forecast_horizon_s=0)
    e.clock.time_s=113.5; a=e.tick(0,123,456).as_dict()
    e.clock.time_s=113.5; b=e.tick(0,123,456).as_dict()
    assert a==b

def test_oil_changes_atmosphere():
    e=create_engine(forecast_horizon_s=0)
    before=e.atmosphere.co2_ppm
    e.ingest_player_action('burn_oil',10)
    assert e.atmosphere.co2_ppm>before

def test_regional_field_is_2d():
    e=create_engine(global_lat=8,global_lon=16,regional_n=33,forecast_horizon_s=0)
    e.tick(0,0,0)
    r=e.local_forcing(0,0)
    assert r.cape_field_j_kg.shape==(33,33)
    assert np.isfinite(r.rain_field_mm_h).all()

def test_game_imports():
    p=ROOT/'9_planets_v18_deterministic_weather.py'
    spec=importlib.util.spec_from_file_location('nine_planets_game',p)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert getattr(mod,'HAVE_PHYSICAL_WEATHER',False)
    assert mod.WeatherSystem.__name__=='WeatherSystem'
