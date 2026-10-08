"""Command line smoke test for the deterministic weather engine."""
import argparse,json
from .core import WeatherEngine,EngineConfig
p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=2);p.add_argument('--x',type=int,default=0);p.add_argument('--y',type=int,default=0);a=p.parse_args()
e=WeatherEngine(EngineConfig()); s=e.tick(a.seconds,a.x,a.y); print(json.dumps(s.as_dict(),indent=2,default=float))
