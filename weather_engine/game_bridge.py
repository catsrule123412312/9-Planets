"""Deterministic bridge from physical weather to 9 Planets gameplay effects."""
from __future__ import annotations
import math
from dataclasses import dataclass
from .core import WeatherEngine, EngineConfig
from .effects import event_effects

@dataclass
class GameWeatherBridge:
    engine: WeatherEngine
    last_snapshot: object | None = None
    last_event: dict | None = None
    last_tick_s: float = 0.0
    lightning_clock_s: float = 0.0

    def is_raining(self) -> bool:
        return bool(self.last_snapshot and self.last_snapshot.rain_rate_mm_h > 0.1)

    @property
    def current(self) -> str:
        if not self.last_snapshot:
            return "☀️ CLEAR"
        e = event_effects(self.last_snapshot)
        labels={
            'clear':'☀️ CLEAR','light_rain':'🌦️ LIGHT RAIN','moderate_rain':'🌧️ MODERATE RAIN','heavy_storm':'⛈️ HEAVY STORM',
            'severe_storm':'🌩️ SEVERE STORM','violent_storm':'🌪️ VIOLENT STORM','blizzard':'❄️ BLIZZARD'
        }
        return labels.get(e['weather'],'☁️ OVERCAST')

    @property
    def intensity(self) -> int:
        if not self.last_snapshot:return 0
        return {'clear':0,'light_rain':1,'moderate_rain':2,'heavy_storm':3,'severe_storm':4,'violent_storm':4,'blizzard':4}.get(event_effects(self.last_snapshot)['weather'],1)

    @property
    def is_drought(self) -> bool:
        s=self.last_snapshot
        if not s:return False
        return s.rain_rate_mm_h < 0.03 and s.surface_temperature_c > 12 and s.humidity < 0.45

    @property
    def firestorm_active(self) -> bool:
        return bool(self.last_snapshot and self.last_snapshot.dust >= 0 and self.last_snapshot.wind_speed_m_s >= 18 and self.last_snapshot.surface_temperature_c >= 25 and self.last_snapshot.rain_rate_mm_h < 0.1)

    @firestorm_active.setter
    def firestorm_active(self,value):
        self._firestorm_override=bool(value)

    def _deterministic_lightning(self, snapshot, now_s: float) -> bool:
        if snapshot.storm_intensity not in {'severe','violent'}: return False
        # Flash interval comes directly from convective intensity, never a random roll.
        rate_per_min = max(0.2, 0.004*max(snapshot.cape_j_kg-500,0)+0.8*8+0.12*snapshot.rain_rate_mm_h)
        interval=max(2.0,60.0/rate_per_min)
        bucket=int(now_s/interval)
        return bucket != int(self.lightning_clock_s/interval)

    def _tornado_hit(self,snapshot,now_s:float,x:int,y:int):
        active=snapshot.storm_intensity=='violent' and snapshot.cape_j_kg>2500 and snapshot.wind_speed_m_s>24
        if not active:return False,0.0,0.0
        angle=0.012*now_s + math.radians(snapshot.wind_direction_deg)
        base_radius=70+0.015*math.sqrt(max(snapshot.cape_j_kg,0))*100
        radial=base_radius*0.55*(1.0+math.sin(0.004*now_s+0.7))
        cx=x+radial*math.cos(angle); cy=y+radial*math.sin(angle)
        distance=math.hypot(cx-x,cy-y)
        hit=distance <= max(6.0,0.035*base_radius)
        return hit,cx,cy

    def _apply_rain(self,world,snapshot,dt):
        if world is None:return
        rain=snapshot.rain_rate_mm_h
        if rain<=0.1:return
        # Existing water remains an explicit resource. Rain never fabricates plant maturity.
        for c in world.clusters.values():
            if c.get('real_item') in {'water','fresh_water','dirty_water'}:
                c['qty']=min(100,int(c.get('qty',0)+max(1.0,rain*dt/60.0)))
            meta=c.get('meta',{}) or {}
            if meta.get('regrows') and c.get('real_item') not in {'water','fresh_water','dirty_water'}:
                c['rain_moisture']=min(1.0,float(c.get('rain_moisture',0))+rain*dt/360000.0)

    def _apply_drought(self,world,player):
        if world is None:return
        for c in world.clusters.values():
            if c.get('real_item') in {'rock','dirt','sand','ash'}:continue
            meta=c.get('meta',{}) or {}
            if meta.get('regrows') or c.get('real_item') in {'wood','fibergrass','ironroot','mushrooms','wild_berries'}:
                c['qty']=max(0,int(c.get('qty',0)*0.985))
        for a in getattr(world,'animals',[]):
            a['thirst']=max(0,float(a.get('thirst',100))-0.7)
            a['hunger']=max(0,float(a.get('hunger',100))-0.35)

    def _apply_blizzard(self,player,snapshot,dt):
        if player is None:return
        if snapshot.temperature_class if hasattr(snapshot,'temperature_class') else False: pass
        if snapshot.surface_temperature_c < 0 and snapshot.wind_speed_m_s > 12:
            if hasattr(player,'temp'):
                player.temp=max(0.0,player.temp-0.12*dt)
            if hasattr(player,'arctic_insulation_req'):
                player.arctic_insulation_req=min(10.0,player.arctic_insulation_req+0.002*dt)

    def tick(self,dt:float,x:int,y:int,player=None,world=None,msg=None,hooks=None):
        now=self.engine.clock.time_s+max(0.0,float(dt))
        snapshot=self.engine.tick(dt,int(x),int(y))
        self.last_snapshot=snapshot
        event=event_effects(snapshot)
        event['temperature_c']=snapshot.surface_temperature_c
        event['drought']=self.is_drought
        event['blizzard']=event['weather']=='blizzard'
        flash=self._deterministic_lightning(snapshot,now)
        event['lightning_flash']=flash
        storm_radius=max(0.5,8.0+0.004*max(snapshot.cape_j_kg,0))
        light_angle=0.018*now+math.radians(snapshot.wind_direction_deg)
        radial=0.15*storm_radius + 0.85*storm_radius*abs(math.sin(0.007*now+0.03*snapshot.latitude))
        lx=int(x)+radial*math.cos(light_angle)
        ly=int(y)+radial*math.sin(light_angle)
        event['lightning_x']=lx; event['lightning_y']=ly
        event['lightning_hit']=bool(flash and math.hypot(lx-int(x),ly-int(y))<=1.25)
        event['lightning_nearby']=bool(flash and math.hypot(lx-int(x),ly-int(y))<=12.0)
        tornado_hit,tx,ty=self._tornado_hit(snapshot,now,int(x),int(y))
        event['tornado']=snapshot.storm_intensity=='violent'
        event['tornado_hit']=tornado_hit
        event['tornado_x']=tx; event['tornado_y']=ty
        if flash:
            self.lightning_clock_s=now
        if player is not None:
            player.weather_physical_temperature_c=snapshot.surface_temperature_c
            player.weather_solar_units=snapshot.received_units
            player.weather_retained=snapshot.atmospheric_retention
            player.weather_rain_rate=snapshot.rain_rate_mm_h
            player.weather_wind_speed=snapshot.wind_speed_m_s
            player.weather_dust=snapshot.dust
            player.weather_cape=snapshot.cape_j_kg
            player.weather_cin=snapshot.cin_j_kg
            player.weather_storm=snapshot.storm_intensity
        # Hook only on event transitions; the game's old video/audio layer remains authoritative for rendering.
        changed = self.last_event is None or event['weather'] != self.last_event.get('weather')
        if changed and hooks:
            try:
                hooks('weather_transition',snapshot,event)
            except Exception:
                pass
        if event['lightning_hit'] and hooks:
            try:hooks('lightning',snapshot,event)
            except Exception:pass
        if tornado_hit and hooks:
            try:hooks('tornado',snapshot,event)
            except Exception:pass
        if msg is not None and changed:
            msg.append(f"{self.current} | {snapshot.surface_temperature_c:.1f}°C | 💧{snapshot.humidity*100:.0f}% | 💨{snapshot.wind_speed_m_s:.1f}m/s")
            del msg[:-3]
        self.last_event=event
        self.last_tick_s=now
        return snapshot,event

    def update_hourly(self,world,player):
        snapshot,event=self.tick(300.0,player.x,player.y,player,world)
        return f"{self.current}: rain={snapshot.rain_rate_mm_h:.2f} mm/h, wind={snapshot.wind_speed_m_s:.1f} m/s"
