"""Bridge between the deterministic weather engine and 9 Planets v17."""
from dataclasses import dataclass
from .effects import event_effects,sky_tint_from_dust
from .core import WeatherEngine,EngineConfig
@dataclass
class GameWeatherBridge:
    engine: WeatherEngine
    previous: dict|None=None
    last_snapshot: object|None=None
    def tick(self,dt,x,y,player=None,world=None):
        s=self.engine.tick(dt,int(x),int(y)); self.last_snapshot=s
        e=event_effects(s); self._apply(player,world,e)
        self.previous=e
        return s,e
    def _apply(self,player,world,e):
        if player is not None:
            player.weather_physical_temperature_c=self.last_snapshot.surface_temperature_c
            player.weather_solar_units=self.last_snapshot.received_units
            player.weather_retained=self.last_snapshot.atmospheric_retention
            player.weather_rain_rate=self.last_snapshot.rain_rate_mm_h
            player.weather_wind_speed=self.last_snapshot.wind_speed_m_s
            player.weather_dust=self.last_snapshot.dust
        # The actual visual/audio resources are handled by the game's legacy layer.
    def ingest(self,action,magnitude=1,x=0,y=0): return self.engine.ingest_player_action(action,magnitude,x,y)
    def status(self): return self.engine.diagnostics()
