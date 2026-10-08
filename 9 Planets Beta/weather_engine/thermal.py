"""Adapter around the uploaded really.py thermal solver.

The original object-to-object radiation model remains available as the detailed
material/emission calculator. The weather engine calls this adapter for local
surface emission and material heat storage calculations.
"""
from pathlib import Path
import importlib.util
_CACHE={}
def load_really(path=None):
    p=Path(path) if path else Path(__file__).resolve().parents[2]/'really.py'
    key=str(p.resolve())
    if key in _CACHE:return _CACHE[key]
    spec=importlib.util.spec_from_file_location('nine_planets_really',key)
    if spec is None or spec.loader is None: raise ImportError(f'Unable to load {p}')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); _CACHE[key]=mod; return mod

def material_emission(material,temperature_c,area_m2=1.0,**overrides):
    mod=load_really()
    cfg={'material_1':material,'area_1_m2':area_m2,'temperature_1_C':temperature_c,'material_2':'air','area_2_m2':area_m2,'temperature_2_C':temperature_c,'view_factor_1_to_2':0.0}
    cfg.update(overrides)
    r=mod.calculate_from_globals(cfg)
    return float(r.get('initial_emitted_by_1_total_W',0.0))

def object_energy_j(mass_kg,specific_heat_j_kgk,temperature_change_k,latent_mass_kg=0.0,latent_heat_j_kg=0.0):
    return float(mass_kg)*float(specific_heat_j_kgk)*float(temperature_change_k)+float(latent_mass_kg)*float(latent_heat_j_kg)

def temperature_change_for_energy(energy_j,mass_kg,specific_heat_j_kgk): return float(energy_j)/max(float(mass_kg)*float(specific_heat_j_kgk),1e-12)

def equivalent_temperature_from_energy_units(units,per_degree=178.0): return float(units)/max(float(per_degree),1e-12)

def terawatts_from_energy_units(units): return float(units)*8.0
