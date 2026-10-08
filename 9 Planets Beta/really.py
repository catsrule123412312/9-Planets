import math

# ======================================================================
# Physical constant
# ======================================================================
SIGMA = 5.670374419e-8  # W / m^2 / K^4


# ======================================================================
# Built-in approximate material table
# ======================================================================
MATERIAL_PROPERTIES = {
    "berry bush": {
        "emissivity": 0.95,
        "absorptivity_IR": 0.95,
        "solar_albedo": 0.18,
        "density": 300.0,
        "specific_heat": 3200.0,
        "thermal_conductivity": 0.20,
        "phase_change_enabled": False,
    },

    "mushrooms": {
        "emissivity": 0.96,
        "absorptivity_IR": 0.96,
        "solar_albedo": 0.30,
        "density": 950.0,
        "specific_heat": 3800.0,
        "thermal_conductivity": 0.50,
        "phase_change_enabled": False,
    },

    "snow": {
        "emissivity": 0.98,
        "absorptivity_IR": 0.98,
        "solar_albedo": 0.85,
        "density": 200.0,
        "specific_heat": 2100.0,
        "thermal_conductivity": 0.15,
        "phase_change_enabled": True,
        "melting_point_K": 273.15,
        "latent_heat_fusion_J_kg": 334000.0,
        "latent_heat_sublimation_J_kg": 2.83e6,

        # Optional explicit phase-change heat capacities.
        "specific_heat_solid": 2100.0,
        "specific_heat_liquid": 4186.0,
    },

    "ice": {
        "emissivity": 0.97,
        "absorptivity_IR": 0.97,
        "solar_albedo": 0.40,
        "density": 917.0,
        "specific_heat": 2100.0,
        "thermal_conductivity": 2.10,
        "phase_change_enabled": True,
        "melting_point_K": 273.15,
        "latent_heat_fusion_J_kg": 334000.0,
        "latent_heat_sublimation_J_kg": 2.83e6,

        # Optional explicit phase-change heat capacities.
        "specific_heat_solid": 2100.0,
        "specific_heat_liquid": 4186.0,
    },

    "dust": {
        "emissivity": 0.95,
        "absorptivity_IR": 0.95,
        "solar_albedo": 0.30,
        "density": 1300.0,
        "specific_heat": 900.0,
        "thermal_conductivity": 0.20,
        "phase_change_enabled": False,
    },

    "sand": {
        "emissivity": 0.93,
        "absorptivity_IR": 0.93,
        "solar_albedo": 0.35,
        "density": 1600.0,
        "specific_heat": 800.0,
        "thermal_conductivity": 0.30,
        "phase_change_enabled": False,
    },

    "water": {
        "emissivity": 0.98,
        "absorptivity_IR": 0.98,
        "solar_albedo": 0.10,
        "density": 1000.0,
        "specific_heat": 4186.0,
        "thermal_conductivity": 0.60,
        "phase_change_enabled": False,  # Set True if you want freezing/melting.
        "melting_point_K": 273.15,
        "latent_heat_fusion_J_kg": 334000.0,

        # If phase change is enabled manually, use proper solid/liquid cp.
        "specific_heat_solid": 2100.0,
        "specific_heat_liquid": 4186.0,
    },

    "wood": {
        "emissivity": 0.90,
        "absorptivity_IR": 0.90,
        "solar_albedo": 0.40,
        "density": 600.0,
        "specific_heat": 1500.0,
        "thermal_conductivity": 0.15,
        "phase_change_enabled": False,
    },

    "grass": {
        "emissivity": 0.95,
        "absorptivity_IR": 0.95,
        "solar_albedo": 0.20,
        "density": 300.0,
        "specific_heat": 3000.0,
        "thermal_conductivity": 0.15,
        "phase_change_enabled": False,
    },

    "catnip": {
        "emissivity": 0.95,
        "absorptivity_IR": 0.95,
        "solar_albedo": 0.20,
        "density": 250.0,
        "specific_heat": 3000.0,
        "thermal_conductivity": 0.15,
        "phase_change_enabled": False,
    },

    "rock": {
        "emissivity": 0.93,
        "absorptivity_IR": 0.93,
        "solar_albedo": 0.25,
        "density": 2500.0,
        "specific_heat": 800.0,
        "thermal_conductivity": 2.50,
        "phase_change_enabled": False,
    },
}


# ======================================================================
# USER INPUT
# ======================================================================

# Choose materials by name, or leave None and set properties manually.
material_1 = None   # Example: "snow", "ice", "sand", "water", "wood"
material_2 = None   # Example: "snow", "ice", "sand", "water", "wood"

# Optional names for output.
object_1_name = None
object_2_name = None

# ----------------------------------------------------------------------
# Object 1 manual overrides
# If these are None, the code uses the material table.
# ----------------------------------------------------------------------
area_1_m2 = None
temperature_1_K = None
temperature_1_C = None

emissivity_1 = None
absorptivity_1_IR = None

solar_albedo_1 = None
solar_absorptivity_1 = None

external_irradiance_on_1_W_m2 = 0.0

mass_1_kg = None
density_1_kg_m3 = None
volume_1_m3 = None
thickness_1_m = None

specific_heat_capacity_1_J_kgK = None
thermal_conductivity_1_W_mK = None

phase_change_enabled_1 = None
melting_point_1_K = None
latent_heat_fusion_1_J_kg = None
latent_heat_sublimation_1_J_kg = None

ice_mass_1_kg = None
liquid_water_mass_1_kg = None
sublimation_rate_1_kg_s = None

# ----------------------------------------------------------------------
# Object 2 manual overrides
# ----------------------------------------------------------------------
area_2_m2 = None
temperature_2_K = None
temperature_2_C = None

emissivity_2 = None
absorptivity_2_IR = None

solar_albedo_2 = None
solar_absorptivity_2 = None

external_irradiance_on_2_W_m2 = 0.0

mass_2_kg = None
density_2_kg_m3 = None
volume_2_m3 = None
thickness_2_m = None

specific_heat_capacity_2_J_kgK = None
thermal_conductivity_2_W_mK = None

phase_change_enabled_2 = None
melting_point_2_K = None
latent_heat_fusion_2_J_kg = None
latent_heat_sublimation_2_J_kg = None

ice_mass_2_kg = None
liquid_water_mass_2_kg = None
sublimation_rate_2_kg_s = None

# ----------------------------------------------------------------------
# Environment
# ----------------------------------------------------------------------
temperature_env_K = None
temperature_env_C = None
include_environment_in_simulation = True
view_factor_1_to_env = None   # Defaults to 1 - view_factor_1_to_2
view_factor_2_to_env = None   # Defaults to 1 - view_factor_2_to_1

# Optional separate air and sky temperatures.
# If None, they default to temperature_env.
temperature_air_K = None
temperature_air_C = None
temperature_sky_K = None
temperature_sky_C = None

# ----------------------------------------------------------------------
# Geometry / view factor
# ----------------------------------------------------------------------
distance_m = None
cos_angle_at_emitter = None
cos_angle_at_receiver = None
visibility_fraction = 1.0

view_factor_1_to_2 = None
view_factor_2_to_1 = None

# ----------------------------------------------------------------------
# Medium between objects
# ----------------------------------------------------------------------
# If both coefficient and transmissivity are available, coefficient wins.
medium_transmissivity_1_to_2 = None
medium_absorption_coefficient_1_per_m = None

# ----------------------------------------------------------------------
# External radiation sources
# ----------------------------------------------------------------------
solar_irradiance_W_m2 = 0.0
lamp_irradiance_W_m2 = 0.0
fire_irradiance_W_m2 = 0.0
reflected_external_irradiance_W_m2 = 0.0

# ----------------------------------------------------------------------
# Time and solver settings
# ----------------------------------------------------------------------
duration_seconds = 1.0
time_step_seconds = None

simulate_temperature_change = True
use_adaptive_time_stepping = True
max_temperature_change_per_step_K = 1.0

# Additional solver safeguards.
min_time_step_seconds = 1e-9
max_time_step_seconds = 60.0
max_time_steps = 1_000_000

# Phase-change accuracy controls.
# max_phase_fraction_per_step limits how much latent capacity is consumed per step.
# phase_change_band_K defines a temperature band around melting where phase limiting is active.
max_phase_fraction_per_step = 0.10
phase_change_band_K = 1.0

# ----------------------------------------------------------------------
# Water phase-change constants
# ----------------------------------------------------------------------
specific_heat_ice_J_kgK = 2100.0
specific_heat_water_J_kgK = 4186.0

# Optional explicit solid/liquid specific heat overrides for phase objects.
specific_heat_solid_1_J_kgK = None
specific_heat_liquid_1_J_kgK = None
specific_heat_solid_2_J_kgK = None
specific_heat_liquid_2_J_kgK = None

# ----------------------------------------------------------------------
# Optional convection model
# ----------------------------------------------------------------------
# Positive heat transfer coefficient causes loss/gain toward air temperature.
# If None or 0, convection is disabled for that object.
convection_coefficient_1_W_m2K = None
convection_coefficient_2_W_m2K = None

# ----------------------------------------------------------------------
# Optional solar projection / sun-angle model
# ----------------------------------------------------------------------
# Priority:
#   1. solar_projected_area if provided
#   2. area * solar_cos_incidence_angle if angle provided
#   3. full area for backward compatibility
solar_projected_area_1_m2 = None
solar_projected_area_2_m2 = None
solar_cos_incidence_angle_1 = None
solar_cos_incidence_angle_2 = None

# ----------------------------------------------------------------------
# Optional conductive/contact link between object 1 and object 2
# ----------------------------------------------------------------------
# This gives thermal_conductivity an actual use.
# If contact_enabled is True, the code tries to estimate a conductance:
#
#   G = k_effective * contact_area / contact_thickness
#
# If you already know the conductance, set contact_conductance_W_K directly.
contact_enabled = False
contact_area_m2 = None
contact_thickness_m = None
contact_thermal_conductivity_W_mK = None
contact_conductance_W_K = None

# ----------------------------------------------------------------------
# Multi-layer object temperature mode
# ----------------------------------------------------------------------
# This is a simplified 1D layered thermal model.
#
# Layer 0 is the exposed surface layer. It receives:
#   - radiation exchange,
#   - environment radiation,
#   - convection,
#   - solar/lamp/fire irradiance,
#   - object-to-object contact heat,
#   - sublimation.
#
# Deeper layers exchange heat only by conduction with neighboring layers.
multilayer_enabled = True

# Number of thermal layers per object.
# 1 layer behaves like the old lumped model.
# 2-5 layers is usually enough for a game-like approximation.
thermal_layers_1 = 1
thermal_layers_2 = 1

# Safety cap for layer count.
max_layers_per_object = 20

# Advanced / internal state carryover.
# Normally leave these as None.
thermal_state_1 = None
thermal_state_2 = None

# ----------------------------------------------------------------------
# Day/night mode for long runs
# ----------------------------------------------------------------------
# Enable this if you want the sun to turn on/off over long simulations.
use_day_night_cycle = False

# Current local solar time.
# Use either seconds or hours.
# Hours example: 14.5 = 14:30, 0 = midnight, 12 = noon.
current_time_seconds = None
current_time_hours = None

# How long the sun is above the horizon per day.
# Use either seconds or hours.
daylight_duration_seconds = None
daylight_duration_hours = None

# Length of a full day. Normally 86400 seconds.
day_period_seconds = 86400.0

# How to interpret daylight duration:
#
# "centered_noon":
#   Daylight is centered around 12:00.
#   Example: 10 hours of daylight -> sunrise 07:00, sunset 17:00.
#
# "since_sunrise":
#   current_time = 0 is treated as sunrise.
#   Daylight runs from 0 to daylight_duration.
day_night_reference = "centered_noon"

# Optional explicit overrides.
# If both sunrise and sunset are provided, they override daylight duration.
sunrise_time_seconds = None
sunset_time_seconds = None
sunrise_time_hours = None
sunset_time_hours = None


# ======================================================================
# Helper functions
# ======================================================================
def safe_float(value, default=None):
    """
    Safer float conversion.
    Returns default instead of crashing on None/invalid values.
    """
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp_value(value, lower=0.0, upper=1.0):
    """
    Clamp a numeric value to [lower, upper].
    Returns None if value cannot be converted.
    """
    v = safe_float(value)

    if v is None:
        return None

    if v < lower:
        return float(lower)

    if v > upper:
        return float(upper)

    return v


def clamp01(value):
    """Clamp a value to 0.0 to 1.0."""
    return clamp_value(value, 0.0, 1.0)


def clamp_int(value, default=1, lower=1, upper=20):
    """Clamp an integer value."""
    v = safe_float(value)

    if v is None:
        return default

    v = int(v)

    if v < lower:
        return lower

    if v > upper:
        return upper

    return v


def celsius_to_kelvin(celsius):
    """Convert Celsius to Kelvin."""
    return float(celsius) + 273.15


def resolve_temperature(temperature_K, temperature_C, default_K=None):
    """Return temperature in Kelvin."""
    T_K = safe_float(temperature_K)

    if T_K is not None:
        return T_K

    T_C = safe_float(temperature_C)

    if T_C is not None:
        return T_C + 273.15

    T_default = safe_float(default_K)

    if T_default is not None:
        return T_default

    return None


def get_material(material_name):
    """Return material dictionary from built-in table."""
    if material_name is None:
        return {}

    key = str(material_name).strip().lower()
    return MATERIAL_PROPERTIES.get(key, {})


def pick(user_value, material_dict, key, default=None):
    """
    Use user value if provided.
    Otherwise use material table value if available.
    Otherwise use default.
    """
    if user_value is not None:
        return user_value

    if material_dict and key in material_dict and material_dict[key] is not None:
        return material_dict[key]

    return default


def resolve_mass(mass, density, volume, area, thickness):
    """
    Resolve mass from direct mass, density*volume, or density*area*thickness.
    """
    m = safe_float(mass)

    if m is not None:
        return m

    d = safe_float(density)

    if d is not None:
        v = safe_float(volume)

        if v is not None:
            return d * v

        A = safe_float(area)
        t = safe_float(thickness)

        if A is not None and t is not None:
            return d * A * t

    return None


def state_surface_temperature(state):
    """
    Get surface temperature from a layered thermal state if available.
    """
    if isinstance(state, (list, tuple)) and len(state) > 0:
        first = state[0]

        if isinstance(first, dict):
            return safe_float(first.get("T"))

    return None


def effective_solar_absorptivity(solar_absorptivity, solar_albedo, ir_absorptivity):
    """
    Get solar absorptivity.

    Priority:
        1. Explicit solar_absorptivity
        2. 1 - solar_albedo
        3. IR absorptivity fallback
    """
    if solar_absorptivity is not None:
        return clamp01(solar_absorptivity)

    if solar_albedo is not None:
        albedo = clamp01(solar_albedo)

        if albedo is not None:
            return clamp01(1.0 - albedo)

    return clamp01(ir_absorptivity)


def absorbed_external_power_W(
    area_m2,
    solar_absorptivity,
    ir_absorptivity,
    solar_irradiance_W_m2,
    other_irradiance_W_m2,
    solar_area_m2=None,
    other_area_m2=None
):
    """
    Absorbed external power.

    Solar irradiance uses solar absorptivity/albedo.
    Other irradiance uses IR absorptivity.
    """
    area = max(0.0, safe_float(area_m2, 0.0))

    solar_area = max(0.0, safe_float(solar_area_m2, area))
    other_area = max(0.0, safe_float(other_area_m2, area))

    alpha_solar = safe_float(solar_absorptivity, 0.0)
    alpha_ir = safe_float(ir_absorptivity, 0.0)

    solar_irradiance = max(0.0, safe_float(solar_irradiance_W_m2, 0.0))
    other_irradiance = max(0.0, safe_float(other_irradiance_W_m2, 0.0))

    return (
        solar_area * alpha_solar * solar_irradiance
        + other_area * alpha_ir * other_irradiance
    )


def resolve_solar_area(
    area_m2,
    projected_area_m2,
    cos_incidence_angle,
    warnings,
    object_name
):
    """
    Resolve the effective area used for solar absorption.

    Priority:
        1. Explicit projected area
        2. Full area * cos(angle)
        3. Full area for backward compatibility
    """
    area = max(0.0, safe_float(area_m2, 0.0))

    if projected_area_m2 is not None:
        projected = max(0.0, safe_float(projected_area_m2, area))

        if projected > area + 1e-12:
            warnings.append(
                f"{object_name}: solar projected area is larger than full area. "
                "Check geometry."
            )

        return projected

    if cos_incidence_angle is not None:
        cos_value = clamp01(cos_incidence_angle)

        if cos_value is None:
            warnings.append(
                f"{object_name}: invalid solar cosine. Using 0.0."
            )
            cos_value = 0.0

        return area * float(cos_value)

    return area


def view_factor_small_surfaces(
    receiving_area_m2,
    distance_m,
    cos_angle_at_emitter,
    cos_angle_at_receiver,
    visibility_fraction=1.0
):
    """
    Approximate view factor for two small surfaces.

    Formula:
        F12 ≈ A_receiver * cos(theta1) * cos(theta2) / (pi * distance^2)
    """
    distance = safe_float(distance_m)

    if distance is None or distance <= 0.0:
        return None

    receiving_area = safe_float(receiving_area_m2)

    if receiving_area is None or receiving_area <= 0.0:
        return 0.0

    cos1 = clamp01(safe_float(cos_angle_at_emitter, 0.0))
    cos2 = clamp01(safe_float(cos_angle_at_receiver, 0.0))
    visibility = clamp01(visibility_fraction)

    if cos1 is None:
        cos1 = 0.0

    if cos2 is None:
        cos2 = 0.0

    if visibility is None:
        visibility = 1.0

    F = (
        receiving_area
        * cos1
        * cos2
        / (math.pi * distance ** 2)
    )

    F *= visibility

    return clamp01(F)


def sanitize_view_factor(value, name, warnings):
    """
    Safely clamp and warn for invalid view factors.
    """
    if value is None:
        return None

    F = safe_float(value)

    if F is None:
        warnings.append(f"{name} was not numeric. Ignoring it.")
        return None

    F_clamped = clamp01(F)

    if F < -1e-12 or F > 1.0 + 1e-12:
        warnings.append(
            f"{name} was {F:.6g}. View factors must be between 0 and 1. "
            f"Clamped to {F_clamped:.6g}."
        )

    return F_clamped


def gray_two_surface_net_W(
    area_1_m2,
    area_2_m2,
    view_factor_1_to_2,
    medium_transmissivity,
    emissivity_1,
    emissivity_2,
    temperature_1_K,
    temperature_2_K
):
    """
    Net radiative exchange between two diffuse-gray opaque surfaces.

    Positive result means heat flows from Object 1 to Object 2.
    """
    A1 = safe_float(area_1_m2)
    A2 = safe_float(area_2_m2)

    if A1 is None or A2 is None or A1 <= 0.0 or A2 <= 0.0:
        return 0.0

    F12 = clamp01(view_factor_1_to_2)
    tau = clamp01(medium_transmissivity)

    eps1 = clamp01(emissivity_1)
    eps2 = clamp01(emissivity_2)

    T1 = safe_float(temperature_1_K)
    T2 = safe_float(temperature_2_K)

    if F12 is None or tau is None or eps1 is None or eps2 is None:
        return 0.0

    if T1 is None or T2 is None or T1 <= 0.0 or T2 <= 0.0:
        return 0.0

    F12_effective = clamp01(F12 * tau)

    if F12_effective is None or F12_effective <= 0.0:
        return 0.0

    if eps1 <= 0.0 or eps2 <= 0.0:
        return 0.0

    denominator = (
        (1.0 - eps1) / (A1 * eps1)
        + 1.0 / (A1 * F12_effective)
        + (1.0 - eps2) / (A2 * eps2)
    )

    if denominator <= 0.0:
        return 0.0

    return SIGMA * (T1 ** 4 - T2 ** 4) / denominator


def net_surface_to_environment_W(
    area_m2,
    view_factor_to_env,
    emissivity_surface,
    surface_temperature_K,
    environment_temperature_K
):
    """
    Net radiative exchange with a large environment.

    Formula:
        Q_env = A * F_env * eps * sigma * (T_surface^4 - T_env^4)

    Positive means heat flows from surface to environment.
    """
    A = safe_float(area_m2)
    F = clamp01(view_factor_to_env)
    eps = clamp01(emissivity_surface)

    T_s = safe_float(surface_temperature_K)
    T_env = safe_float(environment_temperature_K)

    if A is None or A <= 0.0:
        return 0.0

    if F is None or F <= 0.0:
        return 0.0

    if eps is None or eps <= 0.0:
        return 0.0

    if T_s is None or T_env is None:
        return 0.0

    if T_s <= 0.0 or T_env <= 0.0:
        return 0.0

    return A * F * eps * SIGMA * (T_s ** 4 - T_env ** 4)


def convection_power_W(
    area_m2,
    h_W_m2K,
    surface_temperature_K,
    air_temperature_K
):
    """
    Simple convective heat transfer.

    Positive means heat leaves the surface and goes to the air.

    Q_conv = h * A * (T_surface - T_air)
    """
    A = max(0.0, safe_float(area_m2, 0.0))
    h = max(0.0, safe_float(h_W_m2K, 0.0))

    T_s = safe_float(surface_temperature_K)
    T_air = safe_float(air_temperature_K)

    if A <= 0.0 or h <= 0.0:
        return 0.0

    if T_s is None or T_air is None:
        return 0.0

    return A * h * (T_s - T_air)


def estimate_contact_conductance(
    k1,
    k2,
    contact_area_m2,
    contact_thickness_m,
    contact_thermal_conductivity_W_mK,
    contact_conductance_W_K
):
    """
    Estimate conductive/contact conductance between objects.

    If conductance is provided directly, use it.
    Otherwise:
        G = k_effective * A / L
    """
    G_direct = safe_float(contact_conductance_W_K)

    if G_direct is not None:
        return max(0.0, G_direct)

    A = max(0.0, safe_float(contact_area_m2, 0.0))
    L = max(0.0, safe_float(contact_thickness_m, 0.0))

    if A <= 0.0 or L <= 0.0:
        return 0.0

    k_contact = safe_float(contact_thermal_conductivity_W_mK)

    if k_contact is None:
        k1_value = max(0.0, safe_float(k1, 0.0))
        k2_value = max(0.0, safe_float(k2, 0.0))

        if k1_value > 0.0 and k2_value > 0.0:
            # Harmonic-mean-like effective conductivity for two materials in series.
            k_contact = 2.0 / (1.0 / k1_value + 1.0 / k2_value)
        else:
            k_contact = max(k1_value, k2_value)

    if k_contact is None or k_contact <= 0.0:
        return 0.0

    return max(0.0, k_contact * A / L)


# ======================================================================
# Phase-change helpers
# ======================================================================
def initialize_phase_enthalpy(
    temperature_K,
    ice_mass_kg,
    liquid_mass_kg,
    cp_solid,
    cp_liquid,
    latent_heat_fusion,
    melting_point_K
):
    """
    Enthalpy relative to all-solid material at melting point.

    H < 0:
        all solid below melting point

    0 <= H <= mass * L_fusion:
        mixture at melting point

    H > mass * L_fusion:
        all liquid above melting point
    """
    ice_mass = max(0.0, safe_float(ice_mass_kg, 0.0))
    liquid_mass = max(0.0, safe_float(liquid_mass_kg, 0.0))

    T_m = safe_float(melting_point_K, 273.15)
    T = safe_float(temperature_K, T_m)

    cp_s = safe_float(cp_solid, 2100.0)
    cp_l = safe_float(cp_liquid, 4186.0)
    L_f = safe_float(latent_heat_fusion, 0.0)

    sensible_part = (
        ice_mass * cp_s
        + liquid_mass * cp_l
    ) * (T - T_m)

    latent_part = liquid_mass * L_f

    return sensible_part + latent_part


def phase_state_from_enthalpy(
    enthalpy_J,
    total_mass_kg,
    cp_solid,
    cp_liquid,
    latent_heat_fusion,
    melting_point_K
):
    """
    Convert enthalpy back into temperature, ice mass, liquid mass.
    """
    total_mass = max(0.0, safe_float(total_mass_kg, 0.0))
    H = safe_float(enthalpy_J, 0.0)

    T_m = safe_float(melting_point_K, 273.15)
    cp_s = safe_float(cp_solid, 2100.0)
    cp_l = safe_float(cp_liquid, 4186.0)
    L_f = safe_float(latent_heat_fusion, 0.0)

    if total_mass <= 0.0:
        return T_m, 0.0, 0.0

    if cp_s <= 0.0:
        cp_s = 2100.0

    if cp_l <= 0.0:
        cp_l = 4186.0

    if L_f <= 0.0:
        temperature_K = T_m + H / (total_mass * cp_l)
        return max(0.0, temperature_K), 0.0, total_mass

    # All solid, below melting point.
    if H < 0.0:
        temperature_K = T_m + H / (total_mass * cp_s)
        return max(0.0, temperature_K), total_mass, 0.0

    # Phase-change mixture at melting point.
    if H <= total_mass * L_f:
        liquid_mass_kg = H / L_f
        liquid_mass_kg = max(0.0, min(total_mass, liquid_mass_kg))
        ice_mass_kg = total_mass - liquid_mass_kg

        return T_m, ice_mass_kg, liquid_mass_kg

    # All liquid, above melting point.
    excess_J = H - total_mass * L_f
    temperature_K = T_m + excess_J / (total_mass * cp_l)

    return max(0.0, temperature_K), 0.0, total_mass


def update_phase_object_with_sublimation(
    temperature_K,
    ice_mass_kg,
    liquid_mass_kg,
    net_power_W,
    dt_seconds,
    sublimation_rate_kg_s,
    cp_solid,
    cp_liquid,
    latent_heat_fusion,
    latent_heat_sublimation,
    melting_point_K
):
    """
    Update temperature and phase masses using enthalpy.

    This version:
      1. applies non-sublimation power first,
      2. then sublimates ice mass if available,
      3. removes sublimated mass from the phase tracker,
      4. subtracts sublimation latent heat.
    """
    T_m = safe_float(melting_point_K, 273.15)

    ice = max(0.0, safe_float(ice_mass_kg, 0.0))
    liquid = max(0.0, safe_float(liquid_mass_kg, 0.0))
    total = ice + liquid

    T0 = safe_float(temperature_K, T_m)

    dt = max(0.0, safe_float(dt_seconds, 0.0))
    P = safe_float(net_power_W, 0.0)
    rate = max(0.0, safe_float(sublimation_rate_kg_s, 0.0))

    cp_s = safe_float(cp_solid, 2100.0)
    cp_l = safe_float(cp_liquid, 4186.0)
    L_f = safe_float(latent_heat_fusion, 0.0)
    L_sub = safe_float(latent_heat_sublimation, 0.0)

    if total <= 0.0:
        return max(0.0, T0), 0.0, 0.0, 0.0

    H = initialize_phase_enthalpy(
        temperature_K=T0,
        ice_mass_kg=ice,
        liquid_mass_kg=liquid,
        cp_solid=cp_s,
        cp_liquid=cp_l,
        latent_heat_fusion=L_f,
        melting_point_K=T_m
    )

    H += P * dt

    T, ice, liquid = phase_state_from_enthalpy(
        enthalpy_J=H,
        total_mass_kg=total,
        cp_solid=cp_s,
        cp_liquid=cp_l,
        latent_heat_fusion=L_f,
        melting_point_K=T_m
    )

    sublimated_mass = 0.0

    if rate > 0.0 and dt > 0.0 and ice > 0.0:
        sublimated_mass = min(rate * dt, ice)

        if sublimated_mass > 0.0:
            H2 = initialize_phase_enthalpy(
                temperature_K=T,
                ice_mass_kg=ice,
                liquid_mass_kg=liquid,
                cp_solid=cp_s,
                cp_liquid=cp_l,
                latent_heat_fusion=L_f,
                melting_point_K=T_m
            )

            # Remove sensible enthalpy carried away by the sublimated ice.
            H2 -= sublimated_mass * cp_s * (safe_float(T, T_m) - T_m)

            # Remove latent heat of sublimation.
            H2 -= sublimated_mass * L_sub

            ice_after_sublimation = max(0.0, ice - sublimated_mass)
            total_after_sublimation = ice_after_sublimation + liquid

            if total_after_sublimation <= 0.0:
                return max(0.0, safe_float(T, 0.0)), 0.0, 0.0, sublimated_mass

            T, ice, liquid = phase_state_from_enthalpy(
                enthalpy_J=H2,
                total_mass_kg=total_after_sublimation,
                cp_solid=cp_s,
                cp_liquid=cp_l,
                latent_heat_fusion=L_f,
                melting_point_K=T_m
            )

    return (
        max(0.0, safe_float(T, 0.0)),
        max(0.0, ice),
        max(0.0, liquid),
        max(0.0, sublimated_mass)
    )


def update_phase_object(
    temperature_K,
    ice_mass_kg,
    liquid_mass_kg,
    net_power_W,
    dt_seconds,
    cp_solid,
    cp_liquid,
    latent_heat_fusion,
    melting_point_K
):
    """
    Compatibility wrapper around update_phase_object_with_sublimation.
    """
    T, ice, liquid, _ = update_phase_object_with_sublimation(
        temperature_K=temperature_K,
        ice_mass_kg=ice_mass_kg,
        liquid_mass_kg=liquid_mass_kg,
        net_power_W=net_power_W,
        dt_seconds=dt_seconds,
        sublimation_rate_kg_s=0.0,
        cp_solid=cp_solid,
        cp_liquid=cp_liquid,
        latent_heat_fusion=latent_heat_fusion,
        latent_heat_sublimation=0.0,
        melting_point_K=melting_point_K
    )

    return T, ice, liquid


def near_phase_change(
    phase_enabled,
    temperature_K,
    melting_point_K,
    ice_mass_kg,
    liquid_mass_kg,
    band_K
):
    """
    Return True when the material is likely undergoing or near phase change.
    Used to limit latent heat consumed per time step.
    """
    if not phase_enabled:
        return False

    ice = max(0.0, safe_float(ice_mass_kg, 0.0))
    liquid = max(0.0, safe_float(liquid_mass_kg, 0.0))

    if ice > 0.0 and liquid > 0.0:
        return True

    T = safe_float(temperature_K)
    T_m = safe_float(melting_point_K)
    band = max(0.0, safe_float(band_K, 0.0))

    if T is None or T_m is None:
        return False

    return abs(T - T_m) <= band


def phase_plateau(temperature_K, melting_point_K, ice_mass_kg, liquid_mass_kg, net_power_W):
    """
    Return True when a phase-change material is at melting point and
    added/removed heat should primarily change phase rather than temperature.
    """
    T = safe_float(temperature_K)
    T_m = safe_float(melting_point_K)
    ice = max(0.0, safe_float(ice_mass_kg, 0.0))
    liquid = max(0.0, safe_float(liquid_mass_kg, 0.0))
    P = safe_float(net_power_W, 0.0)

    if T is None or T_m is None:
        return False

    if abs(T - T_m) > 1e-9:
        return False

    if ice > 0.0 and liquid > 0.0:
        return True

    if ice > 0.0 and P > 0.0:
        return True

    if liquid > 0.0 and P < 0.0:
        return True

    return False


# ======================================================================
# Multi-layer helpers
# ======================================================================
def build_object_layers(
    state_override,
    requested_layers,
    max_layers,
    total_mass,
    thickness,
    area,
    density,
    temperature_K,
    ice_mass,
    liquid_mass,
    phase_enabled,
    melting_point_K,
    object_name,
    warnings
):
    """
    Build a list of thermal layers for one object.

    Each layer is:
        {
            "T": temperature_K,
            "mass": kg,
            "ice": kg,
            "liquid": kg,
            "thickness": m
        }
    """
    override = None

    if isinstance(state_override, (list, tuple)) and len(state_override) > 0:
        override = list(state_override)
        n = len(override)

        if max_layers is not None and n > int(max_layers):
            warnings.append(
                f"{object_name}: thermal state has {n} layers, which exceeds "
                f"max_layers_per_object={max_layers}. Continuing anyway."
            )
    else:
        n = clamp_int(requested_layers, default=1, lower=1, upper=max_layers or 20)

    fallback_T = max(0.0, safe_float(temperature_K, 273.15))
    fallback_mass = max(0.0, safe_float(total_mass, 0.0))

    fallback_ice = max(0.0, safe_float(ice_mass, 0.0))
    fallback_liquid = max(0.0, safe_float(liquid_mass, 0.0))

    T_m = safe_float(melting_point_K, 273.15)

    if phase_enabled and fallback_mass > 0.0:
        if fallback_ice + fallback_liquid <= 0.0:
            if fallback_T <= T_m:
                fallback_ice = fallback_mass
                fallback_liquid = 0.0
            else:
                fallback_ice = 0.0
                fallback_liquid = fallback_mass
        elif abs((fallback_ice + fallback_liquid) - fallback_mass) > 1e-9:
            scale = fallback_mass / (fallback_ice + fallback_liquid)
            fallback_ice *= scale
            fallback_liquid *= scale

    fallback_thickness = safe_float(thickness)

    if fallback_thickness is None or fallback_thickness <= 0.0:
        d = safe_float(density)
        A = safe_float(area)

        if d is not None and A is not None and fallback_mass > 0.0 and d > 0.0 and A > 0.0:
            fallback_thickness = fallback_mass / (d * A)

    if fallback_thickness is None or fallback_thickness < 0.0:
        fallback_thickness = 0.0

    layers = []

    if override:
        for raw in override:
            if not isinstance(raw, dict):
                raw = {}

            T = safe_float(raw.get("T"), fallback_T)
            thick = safe_float(raw.get("thickness"))
            mass = safe_float(raw.get("mass"))

            ice = max(0.0, safe_float(raw.get("ice"), 0.0)) if phase_enabled else 0.0
            liquid = max(0.0, safe_float(raw.get("liquid"), 0.0)) if phase_enabled else 0.0

            if phase_enabled:
                if mass is None:
                    mass = ice + liquid

                if mass is None or mass <= 0.0:
                    if fallback_mass > 0.0:
                        mass = fallback_mass / n

                        fallback_phase_total = fallback_ice + fallback_liquid

                        if fallback_phase_total > 0.0:
                            ice = mass * (fallback_ice / fallback_phase_total)
                            liquid = mass * (fallback_liquid / fallback_phase_total)
                        else:
                            if safe_float(T, T_m) <= T_m:
                                ice = mass
                                liquid = 0.0
                            else:
                                ice = 0.0
                                liquid = mass
                    else:
                        mass = 0.0
            else:
                if mass is None or mass <= 0.0:
                    mass = fallback_mass / n if fallback_mass > 0.0 else 0.0

            if thick is None or thick <= 0.0:
                if fallback_thickness > 0.0:
                    thick = fallback_thickness / n
                else:
                    thick = 0.0

            layers.append(
                {
                    "T": max(0.0, safe_float(T, fallback_T)),
                    "mass": max(0.0, safe_float(mass, 0.0)),
                    "ice": max(0.0, safe_float(ice, 0.0)),
                    "liquid": max(0.0, safe_float(liquid, 0.0)),
                    "thickness": max(0.0, safe_float(thick, 0.0)),
                }
            )
    else:
        if n > 1:
            if fallback_mass <= 0.0:
                warnings.append(
                    f"{object_name}: multi-layer mode requested but no mass is available. "
                    "Using 1 layer."
                )
                n = 1
            elif fallback_thickness <= 0.0:
                warnings.append(
                    f"{object_name}: multi-layer mode requested but thickness could not be estimated. "
                    "Using 1 layer."
                )
                n = 1

        layer_mass = fallback_mass / n if fallback_mass > 0.0 else 0.0
        layer_thickness = fallback_thickness / n if fallback_thickness > 0.0 else 0.0

        for _ in range(n):
            if phase_enabled:
                ice_i = fallback_ice / n if fallback_ice > 0.0 else 0.0
                liquid_i = fallback_liquid / n if fallback_liquid > 0.0 else 0.0
            else:
                ice_i = 0.0
                liquid_i = 0.0

            layers.append(
                {
                    "T": fallback_T,
                    "mass": layer_mass,
                    "ice": ice_i,
                    "liquid": liquid_i,
                    "thickness": layer_thickness,
                }
            )

    if not layers:
        layers.append(
            {
                "T": fallback_T,
                "mass": fallback_mass,
                "ice": fallback_ice,
                "liquid": fallback_liquid,
                "thickness": fallback_thickness,
            }
        )

    # Normalize layer phase masses.
    for layer in layers:
        layer["mass"] = max(0.0, safe_float(layer.get("mass"), 0.0))
        layer["T"] = max(0.0, safe_float(layer.get("T"), fallback_T))
        layer["thickness"] = max(0.0, safe_float(layer.get("thickness"), 0.0))

        if phase_enabled:
            ice = max(0.0, safe_float(layer.get("ice"), 0.0))
            liquid = max(0.0, safe_float(layer.get("liquid"), 0.0))
            m = layer["mass"]

            if m <= 0.0:
                ice = 0.0
                liquid = 0.0
            elif ice + liquid <= 0.0:
                if layer["T"] <= T_m:
                    ice = m
                    liquid = 0.0
                else:
                    ice = 0.0
                    liquid = m
            elif abs((ice + liquid) - m) > 1e-9:
                scale = m / (ice + liquid)
                ice *= scale
                liquid *= scale

            layer["ice"] = ice
            layer["liquid"] = liquid
        else:
            layer["ice"] = 0.0
            layer["liquid"] = 0.0

    return layers


def aggregate_layers(layers):
    """
    Return:
        total_mass,
        total_ice,
        total_liquid,
        mass_weighted_average_temperature,
        surface_temperature
    """
    if not layers:
        return 0.0, 0.0, 0.0, 273.15, 273.15

    total_mass = 0.0
    total_ice = 0.0
    total_liquid = 0.0
    energy_like_sum = 0.0

    for layer in layers:
        m = max(0.0, safe_float(layer.get("mass"), 0.0))
        T = max(0.0, safe_float(layer.get("T"), 273.15))

        total_mass += m
        total_ice += max(0.0, safe_float(layer.get("ice"), 0.0))
        total_liquid += max(0.0, safe_float(layer.get("liquid"), 0.0))
        energy_like_sum += m * T

    if total_mass > 0.0:
        avg_T = energy_like_sum / total_mass
    else:
        avg_T = safe_float(layers[0].get("T"), 273.15)

    surface_T = safe_float(layers[0].get("T"), avg_T)

    return total_mass, total_ice, total_liquid, avg_T, surface_T


def compute_layer_conductances(layers, thermal_conductivity, area_m2):
    """
    Compute conductances between neighboring layers.

    Uses a simple finite-volume-style resistance:
        R = (dx_i/2 + dx_j/2) / (k * A)
        G = 1 / R
    """
    conductances = []

    k = max(0.0, safe_float(thermal_conductivity, 0.0))
    A = max(0.0, safe_float(area_m2, 0.0))

    if len(layers) <= 1:
        return conductances

    for i in range(len(layers) - 1):
        dx1 = max(0.0, safe_float(layers[i].get("thickness"), 0.0))
        dx2 = max(0.0, safe_float(layers[i + 1].get("thickness"), 0.0))

        if k <= 0.0 or A <= 0.0 or (dx1 + dx2) <= 0.0:
            conductances.append(0.0)
            continue

        R = ((dx1 / 2.0) + (dx2 / 2.0)) / (k * A)

        if R <= 0.0:
            conductances.append(0.0)
        else:
            conductances.append(max(0.0, 1.0 / R))

    return conductances


def layer_state_for_output(layers):
    """
    Return a copy of layer states suitable for storing in results.
    """
    output = []

    for layer in layers:
        output.append(
            {
                "T": safe_float(layer.get("T"), 273.15),
                "mass": safe_float(layer.get("mass"), 0.0),
                "ice": safe_float(layer.get("ice"), 0.0),
                "liquid": safe_float(layer.get("liquid"), 0.0),
                "thickness": safe_float(layer.get("thickness"), 0.0),
            }
        )

    return output


# ======================================================================
# Day/night helpers
# ======================================================================
def resolve_day_night_schedule(cfg=None):
    """
    Resolve day/night schedule from config/globals.
    """
    if cfg is None:
        cfg = globals()

    enabled = bool(cfg.get("use_day_night_cycle", False))

    period = safe_float(cfg.get("day_period_seconds"), 86400.0)

    if period is None or period <= 0.0:
        period = 86400.0

    # Current time.
    current = safe_float(cfg.get("current_time_seconds"))

    if current is None:
        current_hours = safe_float(cfg.get("current_time_hours"))

        if current_hours is not None:
            current = current_hours * 3600.0

    if current is None:
        current = 0.0

    current = current % period

    # Daylight duration.
    daylen = safe_float(cfg.get("daylight_duration_seconds"))

    if daylen is None:
        daylen_hours = safe_float(cfg.get("daylight_duration_hours"))

        if daylen_hours is not None:
            daylen = daylen_hours * 3600.0

    if daylen is None:
        daylen = 0.0

    daylen = clamp_value(daylen, 0.0, period)

    if daylen is None:
        daylen = 0.0

    # Optional explicit sunrise/sunset.
    sunrise_user = safe_float(cfg.get("sunrise_time_seconds"))

    if sunrise_user is None:
        sunrise_hours = safe_float(cfg.get("sunrise_time_hours"))

        if sunrise_hours is not None:
            sunrise_user = sunrise_hours * 3600.0

    sunset_user = safe_float(cfg.get("sunset_time_seconds"))

    if sunset_user is None:
        sunset_hours = safe_float(cfg.get("sunset_time_hours"))

        if sunset_hours is not None:
            sunset_user = sunset_hours * 3600.0

    if sunrise_user is not None and sunset_user is not None:
        sunrise = sunrise_user % period
        sunset = sunset_user % period

        if sunset >= sunrise:
            daylen = sunset - sunrise
        else:
            daylen = period - sunrise + sunset
    else:
        reference = str(
            cfg.get("day_night_reference", "centered_noon")
            or "centered_noon"
        ).strip().lower()

        if reference in (
            "since_sunrise",
            "sunrise",
            "start_at_sunrise",
            "after_sunrise"
        ):
            sunrise = 0.0
            sunset = daylen % period
        else:
            # Default: daylight centered around noon.
            sunrise = max(0.0, (period - daylen) / 2.0)
            sunset = (sunrise + daylen) % period

    always_day = daylen >= period - 1e-9
    always_night = daylen <= 1e-9

    if always_day:
        sunrise = 0.0
        sunset = period
    elif always_night:
        sunrise = 0.0
        sunset = 0.0

    return {
        "enabled": enabled,
        "current_time_s": current,
        "day_period_s": period,
        "daylight_duration_s": daylen,
        "sunrise_s": sunrise,
        "sunset_s": sunset,
        "always_day": always_day,
        "always_night": always_night,
        "reference": cfg.get("day_night_reference", "centered_noon"),
    }


def is_sun_up_at_time(t_seconds, schedule):
    """
    Return True if the sun is up at t_seconds according to schedule.
    """
    if not schedule.get("enabled", False):
        return True

    if schedule.get("always_day", False):
        return True

    if schedule.get("always_night", False):
        return False

    period = safe_float(schedule.get("day_period_s"), 86400.0)

    if period is None or period <= 0.0:
        period = 86400.0

    t = safe_float(t_seconds, 0.0) % period

    sunrise = safe_float(schedule.get("sunrise_s"), 0.0) % period
    sunset = safe_float(schedule.get("sunset_s"), 0.0) % period

    if abs(sunset - sunrise) <= 1e-9:
        return False

    if sunrise <= sunset:
        return sunrise <= t < sunset

    # Night crosses midnight.
    return t >= sunrise or t < sunset


def seconds_to_next_sun_transition(t_seconds, schedule):
    """
    Return seconds until the next sunrise/sunset transition.

    Returns infinity if there is no transition.
    """
    if not schedule.get("enabled", False):
        return float("inf")

    if schedule.get("always_day", False):
        return float("inf")

    if schedule.get("always_night", False):
        return float("inf")

    period = safe_float(schedule.get("day_period_s"), 86400.0)

    if period is None or period <= 0.0:
        period = 86400.0

    t = safe_float(t_seconds, 0.0) % period

    sun_up = is_sun_up_at_time(t, schedule)

    if sun_up:
        target = schedule.get("sunset_s")
    else:
        target = schedule.get("sunrise_s")

    target = safe_float(target, 0.0) % period

    delta = (target - t) % period

    if delta <= 1e-9:
        return 0.0

    return delta


# ======================================================================
# Main calculation internal function
# ======================================================================
def _calculate_from_globals_internal():
    missing = []
    warnings = []

    # ------------------------------------------------------------------
    # Material lookup
    # ------------------------------------------------------------------
    mat1 = get_material(material_1)
    mat2 = get_material(material_2)

    if material_1 is not None and not mat1:
        warnings.append(f"Material '{material_1}' not found in MATERIAL_PROPERTIES.")

    if material_2 is not None and not mat2:
        warnings.append(f"Material '{material_2}' not found in MATERIAL_PROPERTIES.")

    name1 = object_1_name or material_1 or "object_1"
    name2 = object_2_name or material_2 or "object_2"

    # ------------------------------------------------------------------
    # Object 1 core properties
    # ------------------------------------------------------------------
    a1_raw = area_1_m2

    if a1_raw is None:
        a1_raw = pick(None, mat1, "area_m2", None)

    a1 = safe_float(a1_raw)

    if a1 is None or a1 <= 0.0:
        missing.append("area_1_m2 must be provided and greater than zero")

    T1 = resolve_temperature(temperature_1_K, temperature_1_C)

    if T1 is None:
        T1 = state_surface_temperature(thermal_state_1)

    if T1 is None:
        missing.append("temperature_1_K or temperature_1_C")
    elif T1 <= 0.0:
        missing.append("temperature_1_K must be greater than 0 K")

    eps1 = clamp01(pick(emissivity_1, mat1, "emissivity", None))

    if eps1 is None:
        missing.append("emissivity_1")

    abs1 = clamp01(pick(absorptivity_1_IR, mat1, "absorptivity_IR", eps1))

    if abs1 is None:
        missing.append("absorptivity_1_IR")

    solar_albedo1 = clamp01(pick(solar_albedo_1, mat1, "solar_albedo", None))

    solar_abs1 = effective_solar_absorptivity(
        solar_absorptivity_1,
        solar_albedo1,
        abs1
    )

    solar_abs1 = safe_float(solar_abs1, 0.0)

    density1 = safe_float(pick(density_1_kg_m3, mat1, "density", None))
    cp1 = safe_float(pick(specific_heat_capacity_1_J_kgK, mat1, "specific_heat", None))
    k1 = safe_float(pick(thermal_conductivity_1_W_mK, mat1, "thermal_conductivity", None))

    mass1 = resolve_mass(
        mass=mass_1_kg,
        density=density1,
        volume=volume_1_m3,
        area=a1,
        thickness=thickness_1_m
    )

    if mass1 is not None and mass1 < 0.0:
        warnings.append("Object 1 resolved mass was negative. Clamped to 0.")
        mass1 = 0.0

    # ------------------------------------------------------------------
    # Object 2 core properties
    # ------------------------------------------------------------------
    a2_raw = area_2_m2

    if a2_raw is None:
        a2_raw = pick(None, mat2, "area_m2", None)

    a2 = safe_float(a2_raw)

    if a2 is None or a2 <= 0.0:
        missing.append("area_2_m2 must be provided and greater than zero")

    T2 = resolve_temperature(temperature_2_K, temperature_2_C)

    if T2 is None:
        T2 = state_surface_temperature(thermal_state_2)

    if T2 is None:
        missing.append("temperature_2_K or temperature_2_C")
    elif T2 <= 0.0:
        missing.append("temperature_2_K must be greater than 0 K")

    eps2 = clamp01(pick(emissivity_2, mat2, "emissivity", None))

    if eps2 is None:
        missing.append("emissivity_2")

    abs2 = clamp01(pick(absorptivity_2_IR, mat2, "absorptivity_IR", eps2))

    if abs2 is None:
        missing.append("absorptivity_2_IR")

    solar_albedo2 = clamp01(pick(solar_albedo_2, mat2, "solar_albedo", None))

    solar_abs2 = effective_solar_absorptivity(
        solar_absorptivity_2,
        solar_albedo2,
        abs2
    )

    solar_abs2 = safe_float(solar_abs2, 0.0)

    density2 = safe_float(pick(density_2_kg_m3, mat2, "density", None))
    cp2 = safe_float(pick(specific_heat_capacity_2_J_kgK, mat2, "specific_heat", None))
    k2 = safe_float(pick(thermal_conductivity_2_W_mK, mat2, "thermal_conductivity", None))

    mass2 = resolve_mass(
        mass=mass_2_kg,
        density=density2,
        volume=volume_2_m3,
        area=a2,
        thickness=thickness_2_m
    )

    if mass2 is not None and mass2 < 0.0:
        warnings.append("Object 2 resolved mass was negative. Clamped to 0.")
        mass2 = 0.0

    # ------------------------------------------------------------------
    # Phase-change properties
    # ------------------------------------------------------------------
    phase1 = pick(phase_change_enabled_1, mat1, "phase_change_enabled", False)
    phase2 = pick(phase_change_enabled_2, mat2, "phase_change_enabled", False)

    Tm1 = safe_float(pick(melting_point_1_K, mat1, "melting_point_K", 273.15), 273.15)
    Tm2 = safe_float(pick(melting_point_2_K, mat2, "melting_point_K", 273.15), 273.15)

    Lf1 = safe_float(pick(latent_heat_fusion_1_J_kg, mat1, "latent_heat_fusion_J_kg", 334000.0), 334000.0)
    Lf2 = safe_float(pick(latent_heat_fusion_2_J_kg, mat2, "latent_heat_fusion_J_kg", 334000.0), 334000.0)

    Lsub1 = safe_float(pick(latent_heat_sublimation_1_J_kg, mat1, "latent_heat_sublimation_J_kg", 2.83e6), 2.83e6)
    Lsub2 = safe_float(pick(latent_heat_sublimation_2_J_kg, mat2, "latent_heat_sublimation_J_kg", 2.83e6), 2.83e6)

    sub1 = max(0.0, safe_float(pick(sublimation_rate_1_kg_s, mat1, "sublimation_rate_kg_s", 0.0), 0.0))
    sub2 = max(0.0, safe_float(pick(sublimation_rate_2_kg_s, mat2, "sublimation_rate_kg_s", 0.0), 0.0))

    # Use explicit solid/liquid specific heats for phase-change objects.
    cp_solid1_raw = pick(specific_heat_solid_1_J_kgK, mat1, "specific_heat_solid", None)

    if cp_solid1_raw is None:
        cp_solid1_raw = pick(None, mat1, "specific_heat", specific_heat_ice_J_kgK)

    cp_solid1 = safe_float(cp_solid1_raw, safe_float(specific_heat_ice_J_kgK, 2100.0))

    if cp_solid1 <= 0.0:
        cp_solid1 = 2100.0

    cp_liquid1_raw = pick(specific_heat_liquid_1_J_kgK, mat1, "specific_heat_liquid", None)

    if cp_liquid1_raw is None:
        cp_liquid1_raw = specific_heat_water_J_kgK

    cp_liquid1 = safe_float(cp_liquid1_raw, safe_float(specific_heat_water_J_kgK, 4186.0))

    if cp_liquid1 <= 0.0:
        cp_liquid1 = 4186.0

    cp_solid2_raw = pick(specific_heat_solid_2_J_kgK, mat2, "specific_heat_solid", None)

    if cp_solid2_raw is None:
        cp_solid2_raw = pick(None, mat2, "specific_heat", specific_heat_ice_J_kgK)

    cp_solid2 = safe_float(cp_solid2_raw, safe_float(specific_heat_ice_J_kgK, 2100.0))

    if cp_solid2 <= 0.0:
        cp_solid2 = 2100.0

    cp_liquid2_raw = pick(specific_heat_liquid_2_J_kgK, mat2, "specific_heat_liquid", None)

    if cp_liquid2_raw is None:
        cp_liquid2_raw = specific_heat_water_J_kgK

    cp_liquid2 = safe_float(cp_liquid2_raw, safe_float(specific_heat_water_J_kgK, 4186.0))

    if cp_liquid2 <= 0.0:
        cp_liquid2 = 4186.0

    # Initial phase masses.
    ice1 = ice_mass_1_kg
    liquid1 = liquid_water_mass_1_kg

    ice2 = ice_mass_2_kg
    liquid2 = liquid_water_mass_2_kg

    if phase1:
        if ice1 is None and liquid1 is None:
            if mass1 is not None:
                if T1 is None or T1 <= Tm1:
                    ice1 = mass1
                    liquid1 = 0.0
                else:
                    ice1 = 0.0
                    liquid1 = mass1
        else:
            ice1_value = safe_float(ice1)
            liquid1_value = safe_float(liquid1)

            if ice1_value is not None and ice1_value < 0.0:
                warnings.append("Object 1 ice mass was negative. Clamped to 0.")

            if liquid1_value is not None and liquid1_value < 0.0:
                warnings.append("Object 1 liquid mass was negative. Clamped to 0.")

            ice1 = max(0.0, ice1_value if ice1_value is not None else 0.0)
            liquid1 = max(0.0, liquid1_value if liquid1_value is not None else 0.0)

            phase_total1 = ice1 + liquid1

            if mass1 is None:
                mass1 = phase_total1
            elif abs(mass1 - phase_total1) > 1e-9:
                warnings.append(
                    "Object 1 phase masses do not match resolved mass. "
                    "Using ice + liquid mass for phase simulation."
                )
                mass1 = phase_total1

    if phase2:
        if ice2 is None and liquid2 is None:
            if mass2 is not None:
                if T2 is None or T2 <= Tm2:
                    ice2 = mass2
                    liquid2 = 0.0
                else:
                    ice2 = 0.0
                    liquid2 = mass2
        else:
            ice2_value = safe_float(ice2)
            liquid2_value = safe_float(liquid2)

            if ice2_value is not None and ice2_value < 0.0:
                warnings.append("Object 2 ice mass was negative. Clamped to 0.")

            if liquid2_value is not None and liquid2_value < 0.0:
                warnings.append("Object 2 liquid mass was negative. Clamped to 0.")

            ice2 = max(0.0, ice2_value if ice2_value is not None else 0.0)
            liquid2 = max(0.0, liquid2_value if liquid2_value is not None else 0.0)

            phase_total2 = ice2 + liquid2

            if mass2 is None:
                mass2 = phase_total2
            elif abs(mass2 - phase_total2) > 1e-9:
                warnings.append(
                    "Object 2 phase masses do not match resolved mass. "
                    "Using ice + liquid mass for phase simulation."
                )
                mass2 = phase_total2

    # ------------------------------------------------------------------
    # View factor
    # ------------------------------------------------------------------
    F12 = sanitize_view_factor(view_factor_1_to_2, "view_factor_1_to_2", warnings)

    if F12 is None:
        if (
            a2 is not None
            and a2 > 0.0
            and distance_m is not None
            and cos_angle_at_emitter is not None
            and cos_angle_at_receiver is not None
        ):
            F12 = view_factor_small_surfaces(
                receiving_area_m2=a2,
                distance_m=distance_m,
                cos_angle_at_emitter=cos_angle_at_emitter,
                cos_angle_at_receiver=cos_angle_at_receiver,
                visibility_fraction=visibility_fraction
            )

            F12 = sanitize_view_factor(
                F12,
                "estimated view_factor_1_to_2",
                warnings
            )

            if F12 is None:
                missing.append("view_factor_1_to_2 could not be estimated from distance and angles.")
        else:
            missing.append(
                "view_factor_1_to_2 "
                "or distance_m + cos_angle_at_emitter + cos_angle_at_receiver"
            )

    F21 = sanitize_view_factor(view_factor_2_to_1, "view_factor_2_to_1", warnings)

    if F21 is None and F12 is not None:
        if a1 is not None and a2 is not None and a1 > 0.0 and a2 > 0.0:
            raw_F21 = float(F12) * float(a1) / float(a2)
            F21 = clamp01(raw_F21)

            if raw_F21 < -1e-12 or raw_F21 > 1.0 + 1e-12:
                warnings.append(
                    "Reciprocity gave view_factor_2_to_1 "
                    f"{raw_F21:.6g}. Clamped to {F21:.6g}. "
                    "Check geometry/areas."
                )
        else:
            F21 = 0.0

    if F21 is None:
        F21 = 0.0

    # ------------------------------------------------------------------
    # Medium transmissivity
    # ------------------------------------------------------------------
    coeff = safe_float(medium_absorption_coefficient_1_per_m)
    dist = safe_float(distance_m)

    if coeff is not None and dist is not None and dist >= 0.0:
        tau = math.exp(-coeff * dist)
    else:
        tau = safe_float(medium_transmissivity_1_to_2)

        if tau is None:
            tau = 1.0

    tau = clamp01(tau)

    if tau is None:
        tau = 1.0

    # ------------------------------------------------------------------
    # External irradiance
    # ------------------------------------------------------------------
    solar_irr = max(0.0, safe_float(solar_irradiance_W_m2, 0.0))

    common_other_irr = (
        max(0.0, safe_float(lamp_irradiance_W_m2, 0.0))
        + max(0.0, safe_float(fire_irradiance_W_m2, 0.0))
        + max(0.0, safe_float(reflected_external_irradiance_W_m2, 0.0))
    )

    other_irr1 = common_other_irr + max(0.0, safe_float(external_irradiance_on_1_W_m2, 0.0))
    other_irr2 = common_other_irr + max(0.0, safe_float(external_irradiance_on_2_W_m2, 0.0))

    solar_area1 = resolve_solar_area(
        area_m2=a1,
        projected_area_m2=solar_projected_area_1_m2,
        cos_incidence_angle=solar_cos_incidence_angle_1,
        warnings=warnings,
        object_name=name1
    )

    solar_area2 = resolve_solar_area(
        area_m2=a2,
        projected_area_m2=solar_projected_area_2_m2,
        cos_incidence_angle=solar_cos_incidence_angle_2,
        warnings=warnings,
        object_name=name2
    )

    # ------------------------------------------------------------------
    # Stop if essential variables are missing
    # ------------------------------------------------------------------
    if missing:
        return {
            "error": "Fill in missing variables before calculating.",
            "missing": missing,
            "warnings": warnings
        }

    # ------------------------------------------------------------------
    # Day/night schedule
    # ------------------------------------------------------------------
    schedule = resolve_day_night_schedule()

    if schedule["enabled"]:
        initial_sun_up = is_sun_up_at_time(schedule["current_time_s"], schedule)
        initial_solar_irr = solar_irr if initial_sun_up else 0.0
    else:
        initial_sun_up = True
        initial_solar_irr = solar_irr

    # ------------------------------------------------------------------
    # Build thermal layers
    # ------------------------------------------------------------------
    max_layers = clamp_int(max_layers_per_object, default=20, lower=1, upper=100)

    requested_layers1 = thermal_layers_1 if multilayer_enabled else 1
    requested_layers2 = thermal_layers_2 if multilayer_enabled else 1

    layers1 = build_object_layers(
        state_override=thermal_state_1,
        requested_layers=requested_layers1,
        max_layers=max_layers,
        total_mass=mass1,
        thickness=thickness_1_m,
        area=a1,
        density=density1,
        temperature_K=T1,
        ice_mass=ice1,
        liquid_mass=liquid1,
        phase_enabled=phase1,
        melting_point_K=Tm1,
        object_name=name1,
        warnings=warnings
    )

    layers2 = build_object_layers(
        state_override=thermal_state_2,
        requested_layers=requested_layers2,
        max_layers=max_layers,
        total_mass=mass2,
        thickness=thickness_2_m,
        area=a2,
        density=density2,
        temperature_K=T2,
        ice_mass=ice2,
        liquid_mass=liquid2,
        phase_enabled=phase2,
        melting_point_K=Tm2,
        object_name=name2,
        warnings=warnings
    )

    total_mass1, total_ice1, total_liquid1, avg_T1, surface_T1 = aggregate_layers(layers1)
    total_mass2, total_ice2, total_liquid2, avg_T2, surface_T2 = aggregate_layers(layers2)

    # For radiation and compatibility, use surface temperature as the object temperature.
    T1 = surface_T1
    T2 = surface_T2

    mass1 = total_mass1
    mass2 = total_mass2

    initial_ice1 = total_ice1
    initial_liquid1 = total_liquid1

    initial_ice2 = total_ice2
    initial_liquid2 = total_liquid2

    # ------------------------------------------------------------------
    # Initial instantaneous radiation values
    # ------------------------------------------------------------------
    Q12_initial = gray_two_surface_net_W(
        area_1_m2=a1,
        area_2_m2=a2,
        view_factor_1_to_2=F12,
        medium_transmissivity=tau,
        emissivity_1=eps1,
        emissivity_2=eps2,
        temperature_1_K=T1,
        temperature_2_K=T2
    )

    emitted_by_1_total_initial = eps1 * SIGMA * float(a1) * float(T1) ** 4
    emitted_by_1_to_2_initial = emitted_by_1_total_initial * clamp01(F12) * clamp01(tau)
    absorbed_by_2_from_1_initial = emitted_by_1_to_2_initial * clamp01(abs2)

    P_ext1_initial = absorbed_external_power_W(
        area_m2=a1,
        solar_absorptivity=solar_abs1,
        ir_absorptivity=abs1,
        solar_irradiance_W_m2=initial_solar_irr,
        other_irradiance_W_m2=other_irr1,
        solar_area_m2=solar_area1,
        other_area_m2=None
    )

    P_ext2_initial = absorbed_external_power_W(
        area_m2=a2,
        solar_absorptivity=solar_abs2,
        ir_absorptivity=abs2,
        solar_irradiance_W_m2=initial_solar_irr,
        other_irradiance_W_m2=other_irr2,
        solar_area_m2=solar_area2,
        other_area_m2=None
    )

    result = {
        "object_1_name": name1,
        "object_2_name": name2,

        "material_1": material_1,
        "material_2": material_2,

        "initial_temperature_1_K": T1,
        "initial_temperature_1_C": T1 - 273.15,
        "initial_average_temperature_1_K": avg_T1,

        "initial_temperature_2_K": T2,
        "initial_temperature_2_C": T2 - 273.15,
        "initial_average_temperature_2_K": avg_T2,

        "initial_net_exchange_1_to_2_W": Q12_initial,
        "initial_emitted_by_1_total_W": emitted_by_1_total_initial,
        "initial_emitted_by_1_to_2_W": emitted_by_1_to_2_initial,
        "initial_absorbed_by_2_from_1_W": absorbed_by_2_from_1_initial,

        "initial_absorbed_external_1_W": P_ext1_initial,
        "initial_absorbed_external_2_W": P_ext2_initial,

        "used_solar_absorptivity_1": solar_abs1,
        "used_solar_absorptivity_2": solar_abs2,

        "used_solar_area_1_m2": solar_area1,
        "used_solar_area_2_m2": solar_area2,

        "day_night_schedule": schedule,
        "initial_sun_up": initial_sun_up,
        "initial_solar_irradiance_W_m2": initial_solar_irr,

        "layers_1": len(layers1),
        "layers_2": len(layers2),

        "warnings": warnings
    }

    # ------------------------------------------------------------------
    # Temperature simulation
    # ------------------------------------------------------------------
    if not simulate_temperature_change:
        result["final_temperature_1_K"] = T1
        result["final_temperature_1_C"] = T1 - 273.15
        result["final_average_temperature_1_K"] = avg_T1

        result["final_temperature_2_K"] = T2
        result["final_temperature_2_C"] = T2 - 273.15
        result["final_average_temperature_2_K"] = avg_T2

        result["thermal_state_1"] = layer_state_for_output(layers1)
        result["thermal_state_2"] = layer_state_for_output(layers2)

        result["temperature_simulation"] = "disabled by simulate_temperature_change=False"
        return result

    duration = safe_float(duration_seconds, 0.0)

    if duration is None or duration <= 0.0:
        result["final_temperature_1_K"] = T1
        result["final_temperature_1_C"] = T1 - 273.15
        result["final_average_temperature_1_K"] = avg_T1

        result["final_temperature_2_K"] = T2
        result["final_temperature_2_C"] = T2 - 273.15
        result["final_average_temperature_2_K"] = avg_T2

        result["thermal_state_1"] = layer_state_for_output(layers1)
        result["thermal_state_2"] = layer_state_for_output(layers2)

        result["temperature_simulation"] = "duration_seconds is 0, so temperatures did not change."
        return result

    # Check whether temperature simulation is possible.
    can_simulate = True

    if total_mass1 <= 0.0:
        can_simulate = False
        warnings.append("Object 1 needs positive mass to simulate temperature change.")

    if total_mass2 <= 0.0:
        can_simulate = False
        warnings.append("Object 2 needs positive mass to simulate temperature change.")

    if not phase1 and (cp1 is None or cp1 <= 0.0):
        can_simulate = False
        warnings.append("Object 1 needs positive specific heat to simulate temperature change.")

    if not phase2 and (cp2 is None or cp2 <= 0.0):
        can_simulate = False
        warnings.append("Object 2 needs positive specific heat to simulate temperature change.")

    if phase1 and (cp_solid1 <= 0.0 or cp_liquid1 <= 0.0):
        can_simulate = False
        warnings.append("Object 1 phase-change simulation needs positive solid/liquid specific heat.")

    if phase2 and (cp_solid2 <= 0.0 or cp_liquid2 <= 0.0):
        can_simulate = False
        warnings.append("Object 2 phase-change simulation needs positive solid/liquid specific heat.")

    if not can_simulate:
        result["final_temperature_1_K"] = T1
        result["final_temperature_1_C"] = T1 - 273.15
        result["final_average_temperature_1_K"] = avg_T1

        result["final_temperature_2_K"] = T2
        result["final_temperature_2_C"] = T2 - 273.15
        result["final_average_temperature_2_K"] = avg_T2

        result["thermal_state_1"] = layer_state_for_output(layers1)
        result["thermal_state_2"] = layer_state_for_output(layers2)

        result["temperature_simulation"] = "Not enough thermal mass data to simulate temperature change."
        result["warnings"] = warnings
        return result

    # Environment temperature.
    T_env = resolve_temperature(
        temperature_env_K,
        temperature_env_C,
        default_K=293.15
    )

    if temperature_env_K is None and temperature_env_C is None:
        warnings.append(
            "Environment temperature was not provided. "
            "Defaulted to 293.15 K, which is 20 C. "
            "For snow/ice, set temperature_env_C below freezing."
        )

    # Separate air and sky temperatures.
    T_air = resolve_temperature(
        temperature_air_K,
        temperature_air_C,
        default_K=T_env
    )

    T_sky = resolve_temperature(
        temperature_sky_K,
        temperature_sky_C,
        default_K=T_env
    )

    # Convection coefficients.
    h1_raw = safe_float(convection_coefficient_1_W_m2K)
    h2_raw = safe_float(convection_coefficient_2_W_m2K)

    if h1_raw is not None and h1_raw < 0.0:
        warnings.append("convection_coefficient_1_W_m2K was negative. Clamped to 0.")

    if h2_raw is not None and h2_raw < 0.0:
        warnings.append("convection_coefficient_2_W_m2K was negative. Clamped to 0.")

    h1 = max(0.0, h1_raw if h1_raw is not None else 0.0)
    h2 = max(0.0, h2_raw if h2_raw is not None else 0.0)

    # Environment view factors.
    if include_environment_in_simulation:
        F1_env = sanitize_view_factor(view_factor_1_to_env, "view_factor_1_to_env", warnings)

        if F1_env is None:
            F1_env = clamp01(1.0 - float(F12))
        else:
            F1_env = clamp01(F1_env)

        F2_env = sanitize_view_factor(view_factor_2_to_env, "view_factor_2_to_env", warnings)

        if F2_env is None:
            F2_env = clamp01(1.0 - float(F21))
        else:
            F2_env = clamp01(F2_env)

        if F1_env is None:
            F1_env = 0.0

        if F2_env is None:
            F2_env = 0.0
    else:
        F1_env = 0.0
        F2_env = 0.0

    # Contact conduction.
    contact_G = 0.0

    if contact_enabled:
        contact_G = estimate_contact_conductance(
            k1=k1,
            k2=k2,
            contact_area_m2=contact_area_m2,
            contact_thickness_m=contact_thickness_m,
            contact_thermal_conductivity_W_mK=contact_thermal_conductivity_W_mK,
            contact_conductance_W_K=contact_conductance_W_K
        )

        if contact_G <= 0.0:
            warnings.append(
                "contact_enabled is True but contact conductance is zero. "
                "Check contact_area_m2, contact_thickness_m, contact thermal conductivity, "
                "or provide contact_conductance_W_K."
            )

    # Internal layer conduction.
    cond1 = compute_layer_conductances(layers1, k1, a1)
    cond2 = compute_layer_conductances(layers2, k2, a2)

    if len(layers1) > 1 and (k1 is None or k1 <= 0.0):
        warnings.append(
            "Object 1 has multiple layers but thermal_conductivity_1_W_mK is zero/missing. "
            "Internal conduction is disabled."
        )

    if len(layers2) > 1 and (k2 is None or k2 <= 0.0):
        warnings.append(
            "Object 2 has multiple layers but thermal_conductivity_2_W_mK is zero/missing. "
            "Internal conduction is disabled."
        )

    # Time settings.
    elapsed = 0.0
    steps = 0

    sublimated_total1 = 0.0
    sublimated_total2 = 0.0

    min_dt = max(0.0, safe_float(min_time_step_seconds, 1e-9))
    max_dt = safe_float(max_time_step_seconds, 60.0)

    if max_dt is None or max_dt <= 0.0:
        max_dt = 60.0

    if time_step_seconds is not None:
        base_dt = safe_float(time_step_seconds, max_dt)

        if base_dt is None or base_dt <= 0.0:
            base_dt = max_dt
    else:
        base_dt = min(max_dt, max(min_dt, duration / 1000.0))

    base_dt = min(base_dt, max_dt)

    max_phase_fraction = safe_float(max_phase_fraction_per_step)

    if max_phase_fraction is not None:
        max_phase_fraction = clamp_value(max_phase_fraction, 0.0, 1.0)

    phase_band = max(0.0, safe_float(phase_change_band_K, 1.0))

    max_steps = int(safe_float(max_time_steps, 1_000_000) or 1_000_000)

    warned_min_dt = False

    if schedule["enabled"]:
        sim_day_time = schedule["current_time_s"]
    else:
        sim_day_time = 0.0

    # ------------------------------------------------------------------
    # Time loop
    # ------------------------------------------------------------------
    while elapsed < duration:
        steps += 1

        if steps > max_steps:
            warnings.append(
                f"Stopped time loop after exceeding max_time_steps={max_steps}. "
                "Consider increasing max_time_steps, increasing time step, or simplifying the model."
            )
            break

        # Day/night solar state.
        if schedule["enabled"]:
            sun_up = is_sun_up_at_time(sim_day_time, schedule)
            current_solar_irr = solar_irr if sun_up else 0.0
        else:
            sun_up = True
            current_solar_irr = solar_irr

        # Surface temperatures.
        curr_T1 = layers1[0]["T"]
        curr_T2 = layers2[0]["T"]

        Q12 = gray_two_surface_net_W(
            area_1_m2=a1,
            area_2_m2=a2,
            view_factor_1_to_2=F12,
            medium_transmissivity=tau,
            emissivity_1=eps1,
            emissivity_2=eps2,
            temperature_1_K=curr_T1,
            temperature_2_K=curr_T2
        )

        if include_environment_in_simulation:
            Q1_env = net_surface_to_environment_W(
                area_m2=a1,
                view_factor_to_env=F1_env,
                emissivity_surface=eps1,
                surface_temperature_K=curr_T1,
                environment_temperature_K=T_sky
            )

            Q2_env = net_surface_to_environment_W(
                area_m2=a2,
                view_factor_to_env=F2_env,
                emissivity_surface=eps2,
                surface_temperature_K=curr_T2,
                environment_temperature_K=T_sky
            )
        else:
            Q1_env = 0.0
            Q2_env = 0.0

        Q_conv1 = convection_power_W(
            area_m2=a1,
            h_W_m2K=h1,
            surface_temperature_K=curr_T1,
            air_temperature_K=T_air
        )

        Q_conv2 = convection_power_W(
            area_m2=a2,
            h_W_m2K=h2,
            surface_temperature_K=curr_T2,
            air_temperature_K=T_air
        )

        # Positive Q_contact means heat flows from Object 2 to Object 1.
        if contact_G > 0.0:
            Q_contact = contact_G * (curr_T2 - curr_T1)
        else:
            Q_contact = 0.0

        P_ext1 = absorbed_external_power_W(
            area_m2=a1,
            solar_absorptivity=solar_abs1,
            ir_absorptivity=abs1,
            solar_irradiance_W_m2=current_solar_irr,
            other_irradiance_W_m2=other_irr1,
            solar_area_m2=solar_area1,
            other_area_m2=None
        )

        P_ext2 = absorbed_external_power_W(
            area_m2=a2,
            solar_absorptivity=solar_abs2,
            ir_absorptivity=abs2,
            solar_irradiance_W_m2=current_solar_irr,
            other_irradiance_W_m2=other_irr2,
            solar_area_m2=solar_area2,
            other_area_m2=None
        )

        # Layer power arrays.
        P1 = [0.0] * len(layers1)
        P2 = [0.0] * len(layers2)

        # Surface layer receives boundary fluxes.
        P1[0] += -Q12 - Q1_env - Q_conv1 + Q_contact + P_ext1
        P2[0] +=  Q12 - Q2_env - Q_conv2 - Q_contact + P_ext2

        # Internal conduction Object 1.
        for i, G in enumerate(cond1):
            if G <= 0.0:
                continue

            Q_layer = G * (layers1[i]["T"] - layers1[i + 1]["T"])
            P1[i] -= Q_layer
            P1[i + 1] += Q_layer

        # Internal conduction Object 2.
        for i, G in enumerate(cond2):
            if G <= 0.0:
                continue

            Q_layer = G * (layers2[i]["T"] - layers2[i + 1]["T"])
            P2[i] -= Q_layer
            P2[i + 1] += Q_layer

        # Estimate max temperature rate and latent/sublimation time-step limits.
        remaining = duration - elapsed
        dt = base_dt

        max_rate = 1e-12
        dt_limit = float("inf")

        # Object 1 layer rates/limits.
        for i, layer in enumerate(layers1):
            m = max(0.0, safe_float(layer.get("mass"), 0.0))

            if m <= 0.0:
                continue

            P = P1[i]

            if phase1:
                ice = max(0.0, safe_float(layer.get("ice"), 0.0))
                liquid = max(0.0, safe_float(layer.get("liquid"), 0.0))

                C = max(ice * cp_solid1 + liquid * cp_liquid1, 1e-9)

                P_est = P

                if i == 0 and sub1 > 0.0 and ice > 0.0:
                    P_est -= sub1 * Lsub1

                if not phase_plateau(layer["T"], Tm1, ice, liquid, P_est):
                    max_rate = max(max_rate, abs(P_est) / C)

                if max_phase_fraction is not None and max_phase_fraction > 0.0:
                    if near_phase_change(True, layer["T"], Tm1, ice, liquid, phase_band):
                        if m > 0.0 and Lf1 > 0.0 and abs(P_est) > 1e-12:
                            dt_limit = min(
                                dt_limit,
                                max_phase_fraction * m * Lf1 / abs(P_est)
                            )

                    if i == 0 and sub1 > 0.0 and ice > 0.0:
                        dt_limit = min(
                            dt_limit,
                            max_phase_fraction * ice / sub1
                        )
            else:
                C = max(m * float(cp1), 1e-9)
                max_rate = max(max_rate, abs(P) / C)

        # Object 2 layer rates/limits.
        for i, layer in enumerate(layers2):
            m = max(0.0, safe_float(layer.get("mass"), 0.0))

            if m <= 0.0:
                continue

            P = P2[i]

            if phase2:
                ice = max(0.0, safe_float(layer.get("ice"), 0.0))
                liquid = max(0.0, safe_float(layer.get("liquid"), 0.0))

                C = max(ice * cp_solid2 + liquid * cp_liquid2, 1e-9)

                P_est = P

                if i == 0 and sub2 > 0.0 and ice > 0.0:
                    P_est -= sub2 * Lsub2

                if not phase_plateau(layer["T"], Tm2, ice, liquid, P_est):
                    max_rate = max(max_rate, abs(P_est) / C)

                if max_phase_fraction is not None and max_phase_fraction > 0.0:
                    if near_phase_change(True, layer["T"], Tm2, ice, liquid, phase_band):
                        if m > 0.0 and Lf2 > 0.0 and abs(P_est) > 1e-12:
                            dt_limit = min(
                                dt_limit,
                                max_phase_fraction * m * Lf2 / abs(P_est)
                            )

                    if i == 0 and sub2 > 0.0 and ice > 0.0:
                        dt_limit = min(
                            dt_limit,
                            max_phase_fraction * ice / sub2
                        )
            else:
                C = max(m * float(cp2), 1e-9)
                max_rate = max(max_rate, abs(P) / C)

        if use_adaptive_time_stepping and max_temperature_change_per_step_K is not None:
            max_allowed_dT = safe_float(max_temperature_change_per_step_K)

            if max_allowed_dT is not None and max_allowed_dT > 0.0:
                adaptive_dt = max_allowed_dT / max_rate
                dt = min(dt, adaptive_dt)

        dt = min(dt, max_dt)

        if math.isfinite(dt_limit):
            dt = min(dt, dt_limit)

        # Limit time step at sunrise/sunset transitions.
        if schedule["enabled"]:
            transition_dt = seconds_to_next_sun_transition(sim_day_time, schedule)

            if math.isfinite(transition_dt):
                if transition_dt > 0.0:
                    dt = min(dt, transition_dt)
                else:
                    dt = min(dt, min_dt)

        dt = min(dt, remaining)

        if dt <= 0.0:
            dt = min(min_dt, remaining)
        elif dt < min_dt and remaining > min_dt:
            if not warned_min_dt:
                warnings.append(
                    "Time step reached min_time_step_seconds. "
                    "The simulation continued, but accuracy may be reduced."
                )
                warned_min_dt = True

            dt = min(min_dt, remaining)

        if dt <= 0.0:
            break

        # Update Object 1 layers.
        for i, layer in enumerate(layers1):
            m = max(0.0, safe_float(layer.get("mass"), 0.0))

            if m <= 0.0:
                continue

            if phase1:
                sub_rate = sub1 if i == 0 else 0.0

                new_T, new_ice, new_liquid, sub_mass = update_phase_object_with_sublimation(
                    temperature_K=layer["T"],
                    ice_mass_kg=layer["ice"],
                    liquid_mass_kg=layer["liquid"],
                    net_power_W=P1[i],
                    dt_seconds=dt,
                    sublimation_rate_kg_s=sub_rate,
                    cp_solid=cp_solid1,
                    cp_liquid=cp_liquid1,
                    latent_heat_fusion=Lf1,
                    latent_heat_sublimation=Lsub1,
                    melting_point_K=Tm1
                )

                layer["T"] = new_T
                layer["ice"] = new_ice
                layer["liquid"] = new_liquid

                if i == 0:
                    sublimated_total1 += sub_mass
            else:
                C = max(m * float(cp1), 1e-9)
                layer["T"] = max(0.0, layer["T"] + P1[i] * dt / C)

        # Update Object 2 layers.
        for i, layer in enumerate(layers2):
            m = max(0.0, safe_float(layer.get("mass"), 0.0))

            if m <= 0.0:
                continue

            if phase2:
                sub_rate = sub2 if i == 0 else 0.0

                new_T, new_ice, new_liquid, sub_mass = update_phase_object_with_sublimation(
                    temperature_K=layer["T"],
                    ice_mass_kg=layer["ice"],
                    liquid_mass_kg=layer["liquid"],
                    net_power_W=P2[i],
                    dt_seconds=dt,
                    sublimation_rate_kg_s=sub_rate,
                    cp_solid=cp_solid2,
                    cp_liquid=cp_liquid2,
                    latent_heat_fusion=Lf2,
                    latent_heat_sublimation=Lsub2,
                    melting_point_K=Tm2
                )

                layer["T"] = new_T
                layer["ice"] = new_ice
                layer["liquid"] = new_liquid

                if i == 0:
                    sublimated_total2 += sub_mass
            else:
                C = max(m * float(cp2), 1e-9)
                layer["T"] = max(0.0, layer["T"] + P2[i] * dt / C)

        if schedule["enabled"]:
            sim_day_time = (sim_day_time + dt) % schedule["day_period_s"]

        elapsed += dt

    # ------------------------------------------------------------------
    # Final results
    # ------------------------------------------------------------------
    final_mass1, final_ice1, final_liquid1, final_avg_T1, final_surface_T1 = aggregate_layers(layers1)
    final_mass2, final_ice2, final_liquid2, final_avg_T2, final_surface_T2 = aggregate_layers(layers2)

    result["final_temperature_1_K"] = final_surface_T1
    result["final_temperature_1_C"] = final_surface_T1 - 273.15
    result["final_average_temperature_1_K"] = final_avg_T1

    result["final_temperature_2_K"] = final_surface_T2
    result["final_temperature_2_C"] = final_surface_T2 - 273.15
    result["final_average_temperature_2_K"] = final_avg_T2

    result["temperature_change_1_K"] = final_surface_T1 - T1
    result["temperature_change_2_K"] = final_surface_T2 - T2

    result["SIMULATION_DURATION_SECONDS"] = duration
    result["SIMULATION_ELAPSED_SECONDS"] = elapsed
    result["time_steps_used"] = steps

    result["thermal_state_1"] = layer_state_for_output(layers1)
    result["thermal_state_2"] = layer_state_for_output(layers2)

    if phase1:
        ice_change1 = initial_ice1 - final_ice1

        result["object_1_phase"] = {
            "initial_ice_kg": initial_ice1,
            "initial_liquid_kg": initial_liquid1,
            "final_ice_kg": final_ice1,
            "final_liquid_kg": final_liquid1,

            # Net ice decrease can be caused by melting and/or sublimation.
            "ice_mass_decrease_kg": ice_change1,

            # Explicitly report sublimated mass.
            "ice_sublimated_kg": sublimated_total1,

            # Approximate separation of melting and sublimation.
            "ice_melted_kg": max(0.0, ice_change1 - sublimated_total1),

            # Approximate frozen liquid. If sublimation removed ice while freezing
            # occurred, this tries to compensate.
            "liquid_frozen_kg": max(0.0, -ice_change1 + sublimated_total1),
        }

    if phase2:
        ice_change2 = initial_ice2 - final_ice2

        result["object_2_phase"] = {
            "initial_ice_kg": initial_ice2,
            "initial_liquid_kg": initial_liquid2,
            "final_ice_kg": final_ice2,
            "final_liquid_kg": final_liquid2,

            # Net ice decrease can be caused by melting and/or sublimation.
            "ice_mass_decrease_kg": ice_change2,

            # Explicitly report sublimated mass.
            "ice_sublimated_kg": sublimated_total2,

            # Approximate separation of melting and sublimation.
            "ice_melted_kg": max(0.0, ice_change2 - sublimated_total2),

            # Approximate frozen liquid. If sublimation removed ice while freezing
            # occurred, this tries to compensate.
            "liquid_frozen_kg": max(0.0, -ice_change2 + sublimated_total2),
        }

    result["warnings"] = warnings

    return result


# ======================================================================
# Public wrapper
# ======================================================================
_MISSING = object()


def calculate_from_globals(config=None):
    """
    You can call calculate_from_globals() exactly as before.

    You can also pass a config dictionary:

        calculate_from_globals({
            "material_1": "snow",
            "area_1_m2": 1.0,
            ...
        })
    """
    if config is None:
        return _calculate_from_globals_internal()

    old_values = {}

    for key, value in config.items():
        old_values[key] = globals().get(key, _MISSING)

    globals().update(config)

    try:
        return _calculate_from_globals_internal()
    finally:
        for key, old_value in old_values.items():
            if old_value is _MISSING:
                globals().pop(key, None)
            else:
                globals()[key] = old_value


# ======================================================================
# Run example
# ======================================================================
if __name__ == "__main__":
    import pprint

    # Example: snow next to ice.
    material_1 = "snow"
    material_2 = "ice"

    # Geometry / size.
    area_1_m2 = 1.0
    thickness_1_m = 0.05

    area_2_m2 = 1.0
    thickness_2_m = 0.02

    # Multi-layer example.
    # Layer 0 is the exposed surface.
    # Layer 1 is deeper/interior.
    multilayer_enabled = True
    thermal_layers_1 = 3
    thermal_layers_2 = 2

    # Initial temperatures.
    temperature_1_C = -5.0
    temperature_2_C = -2.0

    # Surroundings.
    temperature_env_C = -10.0

    # View factor.
    view_factor_1_to_2 = 0.5

    # Sunlight when the sun is up.
    solar_irradiance_W_m2 = 300.0

    # Day/night example:
    # Current time 15:00, 10 hours daylight centered on noon.
    # Sunrise 07:00, sunset 17:00.
    use_day_night_cycle = True
    current_time_hours = 15.0 #can be changed (based on other variables; this is a placeholder)
    daylight_duration_hours = 10.0 #modified based on seasons engine
    day_night_reference = "centered_noon"

    # Simulate 24 hours.
    duration_seconds = 24.0 * 3600.0

    pprint.pprint(calculate_from_globals())