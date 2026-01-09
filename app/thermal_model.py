"""
Building Thermal Model - Simplified RC (Resistance-Capacitance) Model

This models a building as a thermal capacitor (stores heat) with thermal
resistance (insulation) to the outside.

Key Physics:
- Heat Loss: Q_loss = U × A × (T_indoor - T_outdoor)
  where U is thermal transmittance (W/m²K), A is surface area

- Thermal Mass: C × dT/dt = Q_in - Q_loss
  where C is heat capacity (J/K), Q_in is heat pump power

- Heat Pump: Q_in = COP × P_electric
  where COP depends on temperature difference
"""

import numpy as np
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class BuildingParameters:
    """Physical parameters of a building"""

    floor_area: float  # m²
    volume: float  # m³
    insulation_level: str  # "low", "medium", "high"

    def get_u_value(self) -> float:
        """
        Get thermal transmittance (U-value) based on insulation level
        Lower U-value = better insulation

        Finnish building code (D3 2012):
        - New buildings: U < 0.17 W/m²K
        - Old buildings: U ≈ 0.4-0.6 W/m²K
        """
        u_values = {
            "low": 0.50,  # Old, poorly insulated
            "medium": 0.30,  # Average renovation standard
            "high": 0.17,  # New building code
        }
        return u_values.get(self.insulation_level, 0.30)

    def get_thermal_mass(self) -> float:
        """
        Estimate building thermal mass (heat capacity)

        Typical values:
        - Lightweight (wood): 50 kJ/K per m² floor area
        - Medium (mixed): 100 kJ/K per m² floor area
        - Heavy (concrete): 150 kJ/K per m² floor area

        We assume medium construction
        """
        return 100_000 * self.floor_area  # J/K

    def get_envelope_area(self) -> float:
        """
        Estimate external surface area
        Rough approximation: A ≈ 4 × floor_area for a typical house
        """
        return 4.0 * self.floor_area  # m²


@dataclass
class HeatPumpParameters:
    """Heat pump specifications"""

    type: str  # "GSHP" or "ASHP"
    rated_power: float  # kW
    rated_cop: float  # Coefficient of Performance at rated conditions

    def get_cop(self, t_outdoor: float, t_indoor: float) -> float:
        """
        Calculate COP based on temperature conditions

        COP degrades with larger temperature difference:
        - GSHP: More stable (ground temp is constant ≈5°C)
        - ASHP: Varies with outdoor temp

        Simplified Carnot-based model:
        COP_real = COP_carnot × efficiency
        COP_carnot = T_hot / (T_hot - T_cold)
        """
        # Convert to Kelvin
        t_hot_k = t_indoor + 273.15
        t_cold_k = (t_outdoor if self.type == "ASHP" else 5.0) + 273.15

        # Carnot COP (theoretical maximum)
        cop_carnot = t_hot_k / (t_hot_k - t_cold_k)

        # Real COP is ~40-50% of Carnot
        efficiency = 0.45
        cop_real = cop_carnot * efficiency

        # Clamp to realistic values
        return np.clip(cop_real, 2.0, 5.0)


class ThermalSimulator:
    """
    Simulates building temperature over time given:
    - Outdoor temperature profile
    - Heat pump operating schedule
    - Solar radiation (free heating through windows)
    """

    def __init__(self, building: BuildingParameters, heat_pump: HeatPumpParameters):
        self.building = building
        self.heat_pump = heat_pump

        # Physical constants
        self.U = building.get_u_value()  # W/m²K
        self.A = building.get_envelope_area()  # m²
        self.C = building.get_thermal_mass()  # J/K
        self.UA = self.U * self.A  # Overall heat loss coefficient W/K

        # Solar gain factor (windows typically 15% of floor area)
        self.window_area = 0.15 * building.floor_area
        self.solar_gain_factor = 0.7  # g-value for double glazing

    def simulate_hour(
        self,
        t_indoor_current: float,
        t_outdoor: float,
        heat_pump_on: bool,
        heat_pump_power_fraction: float,
        solar_radiation: float = 0.0,
        dt: float = 3600.0,
    ) -> float:
        """
        Simulate one time step (default 1 hour = 3600 seconds)

        Returns: New indoor temperature

        Energy balance equation:
        C × dT/dt = Q_heat_pump + Q_solar - Q_loss

        Q_loss = UA × (T_indoor - T_outdoor)
        Q_heat_pump = COP × P_electric (if on)
        Q_solar = solar_radiation × window_area × g_value
        """
        # Heat loss through envelope (always happening)
        q_loss = self.UA * (t_indoor_current - t_outdoor)  # Watts

        # Solar gain (free heating)
        q_solar = solar_radiation * self.window_area * self.solar_gain_factor  # Watts

        # Heat pump input
        if heat_pump_on:
            p_electric = (
                self.heat_pump.rated_power * heat_pump_power_fraction * 1000
            )  # Convert kW to W
            cop = self.heat_pump.get_cop(t_outdoor, t_indoor_current)
            q_heat_pump = cop * p_electric  # Watts
        else:
            q_heat_pump = 0.0

        # Net heat flow
        q_net = q_heat_pump + q_solar - q_loss  # Watts

        # Temperature change: dT = Q_net × dt / C
        dt_change = (q_net * dt) / self.C

        t_indoor_new = t_indoor_current + dt_change

        return t_indoor_new

    def simulate_day(
        self,
        t_indoor_initial: float,
        t_outdoor_hourly: List[float],
        heat_pump_schedule: List[bool],
        solar_radiation_hourly: List[float] = None,
    ) -> List[float]:
        """
        Simulate 24 hours of operation

        Args:
            t_indoor_initial: Starting indoor temperature (°C)
            t_outdoor_hourly: 24 outdoor temperatures (°C)
            heat_pump_schedule: 24 booleans (True = on, False = off)
            solar_radiation_hourly: Optional 24 solar radiation values (W/m²)

        Returns:
            List of 24 indoor temperatures (°C)
        """
        if solar_radiation_hourly is None:
            solar_radiation_hourly = [0.0] * 24

        indoor_temps = [t_indoor_initial]

        for hour in range(24):
            # Get power fraction based on mode
            # BOOST = 100%, NORMAL = 70%, ECO = 30%
            power_fraction = 0.7  # Default to NORMAL

            t_new = self.simulate_hour(
                t_indoor_current=indoor_temps[-1],
                t_outdoor=t_outdoor_hourly[hour],
                heat_pump_on=heat_pump_schedule[hour],
                heat_pump_power_fraction=power_fraction,
                solar_radiation=solar_radiation_hourly[hour],
            )

            indoor_temps.append(t_new)

        return indoor_temps[1:]  # Return 24 values (exclude initial)

    def estimate_power_consumption(
        self, t_outdoor: float, t_indoor: float, mode: str
    ) -> float:
        """
        Estimate electrical power consumption for one hour

        Returns: Energy consumption in kWh
        """
        power_fractions = {"BOOST": 1.0, "NORMAL": 0.7, "ECO": 0.3, "OFF": 0.0}

        fraction = power_fractions.get(mode, 0.7)

        if mode == "OFF":
            return 0.0

        # Average power over the hour
        p_electric_kw = self.heat_pump.rated_power * fraction

        return p_electric_kw  # kWh (since we're calculating for 1 hour)


def calculate_comfort_score(
    indoor_temps: List[float], comfort_min: float, comfort_max: float
) -> Tuple[float, int]:
    """
    Calculate comfort score based on predicted temperatures

    Returns:
        (score, hours_outside_comfort)

    Score calculation:
    - 100 if always in comfort zone
    - Penalty for each hour outside comfort
    - Extra penalty for extreme deviations
    """
    hours_too_cold = sum(1 for t in indoor_temps if t < comfort_min)
    hours_too_hot = sum(1 for t in indoor_temps if t > comfort_max)
    hours_outside = hours_too_cold + hours_too_hot

    # Calculate severity of violations
    violations = []
    for t in indoor_temps:
        if t < comfort_min:
            violations.append(comfort_min - t)
        elif t > comfort_max:
            violations.append(t - comfort_max)
        else:
            violations.append(0.0)

    # Score starts at 100
    score = 100.0

    # Penalty: -3 points per hour outside comfort
    score -= hours_outside * 3

    # Extra penalty for severe violations (>2°C deviation)
    severe_violations = sum(1 for v in violations if v > 2.0)
    score -= severe_violations * 5

    # Extra penalty for average violation severity
    avg_violation = np.mean(violations) if violations else 0
    score -= avg_violation * 10

    return max(0.0, min(100.0, score)), hours_outside
