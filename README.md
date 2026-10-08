# 9 Planets deterministic weather engine v19

This release makes the physical weather model the source of truth for weather in 9 Planets.
The old weather system is retained as a legacy event/effects layer: its videos, sounds, resource responses, lightning/tornado presentation, drought damage, blizzard behavior, and similar game-facing effects remain available, but they no longer decide weather by random rolls.

## Architecture

**Sun → global atmosphere → regional model everywhere → high-resolution local storm nests → game effects.**

The Sun uses the game's requested calibration:

- Sun energy = 1,000,000,000 units
- Sun radius = 0.86 million miles
- orbital distance value = 93 million miles
- inverse-square formula distance = 186 million miles
- maximum space flux ≈ 21,378.19 game energy units
- planet rotation = 720 real seconds (6 minutes day, 6 minutes night)
- rotation changes 1 degree every 2 real seconds
- solar energy is clamped to zero below the horizon
- game energy temperature conversion = 178 energy units / °C
- one game energy unit is also exposed as 8 TW for large-scale bookkeeping

The old procedural world remains lazy. A weather state is materialized when a coordinate becomes relevant, and the physical state is continuous in simulated time.

## Weather states

Rain intensity comes from modeled condensation/available moisture, not an event roll. Storms are diagnosed from CAPE, CIN, convergence, vertical shear, vorticity, lifting level, and precipitable water. Tornadoes and lightning use deterministic clocks and trajectories derived from the storm state.

Drought is integrated over time. Three complete 12-minute game days of moisture deficit are required before the drought state becomes active. Once active, vegetation and animal water/food stores are reduced by deterministic daily stress.

Blizzards emerge when cold, moisture, and strong wind satisfy the Arctic thresholds. Heat/cold waves, fog, snow, hail/graupel, dust, flooding, and fire-weather diagnostics are part of the physical catalogue.

## Environmental interaction

The engine accepts deterministic external changes. Burning oil increases CO2, CH4, N2O, and aerosol loading. Irrigation increases soil moisture. Vegetation clearing reduces canopy cover. Dust sources increase aerosol loading. These changes feed back into radiation and surface conditions.

The in-game `weather` command shows Sun energy, rotation, surface temperature, humidity, wind, rain, CAPE, storm class, dust, greenhouse-gas state, and atmospheric infrared retention.

## Detailed thermal solver

`really.py` is included unchanged as the high-detail material thermal/emission reference. The new weather engine exposes an adapter so game-scale surfaces can use its Stefan–Boltzmann emission and heat-storage logic.

## Engine size

The `weather_engine/` source tree contains **more than 22,000 lines of Python** across modular physical, numerical, regional, game-feedback, and diagnostic components. The generated parameterization catalogue is intentionally modular so new planets can reuse the same solver structure with different constants.

## Run

From this folder:

```bat
run_9_planets_v19.bat
```

Or directly:

```bat
python 9_planets_v18_deterministic_weather.py
```

The game file and `weather_engine/` directory must be in the same folder. Keep your existing 9 Planets `assets/` directory next to the game file.

## Test

```bat
python -m pytest -q
```
