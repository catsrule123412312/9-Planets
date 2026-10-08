"""Small stable API for game integration and future planets."""
from .core import WeatherEngine,EngineConfig
from .bridge import GameWeatherBridge

def create_engine(**kwargs): return WeatherEngine(EngineConfig(**kwargs))
def create_game_bridge(**kwargs): return GameWeatherBridge(create_engine(**kwargs))
__all__=['WeatherEngine','EngineConfig','GameWeatherBridge','create_engine','create_game_bridge']
