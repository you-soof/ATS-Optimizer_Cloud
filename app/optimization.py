"""
Optimization Engine - The "Brain" of ATS-Optimizer

This module decides when to run the heat pump to minimize costs while
maintaining comfort. It's a constrained optimization problem:

Objective: Minimize total electricity cost
Constraints:
  - Indoor temperature must stay within comfort range
  - Heat pump can't cycle too frequently
  - Must respect thermal dynamics of the building

Algorithm: Dynamic Programming approach
  - State: (hour, indoor_temperature)
  - Decision: heat_pump_mode (BOOST, NORMAL, ECO, OFF)
  - Reward: -electricity_cost - comfort_penalty
"""

import numpy as np
from typing import List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from app.thermal_model import (
    ThermalSimulator,
    BuildingParameters,
    HeatPumpParameters,
    calculate_comfort_score,
)
from app.models import HeatPumpMode

logger = logging.getLogger(__name__)


@dataclass
class OptimizationInput:
    """All inputs needed for optimization"""

    # Building and heat pump specs
    building: BuildingParameters
    heat_pump: HeatPumpParameters

    # Current state
    current_indoor_temp: float

    # Forecasts (24 hours)
    outdoor_temps: List[float]  # °C
    electricity_prices: List[float]  # EUR/MWh
    solar_radiation: List[float]  # W/m²

    # User constraints
    comfort_min_temp: float
    comfort_max_temp: float

    # Timestamps
    start_time: datetime


class HeatPumpOptimizer:
    """
    Optimizes heat pump schedule using dynamic programming

    The idea: Instead of just heating when it's cold, we "pre-heat" the
    building during cheap electricity hours, then let it coast using
    thermal mass during expensive hours.
    """

    def __init__(self):
        self.penalty_per_degree = 100.0  # EUR penalty for being 1°C outside comfort
        self.cycling_penalty = 5.0  # EUR penalty for changing modes

    def optimize(self, inputs: OptimizationInput) -> Dict:
        """
        Main optimization function

        Returns:
            Dict with:
            - 'schedule': List of HourlySchedule objects
            - 'total_cost': Estimated total cost (EUR)
            - 'baseline_cost': Cost without optimization (EUR)
            - 'indoor_temps': Predicted indoor temperatures
        """
        logger.info(f"Starting optimization for 24 hours from {inputs.start_time}")

        # Create thermal simulator
        simulator = ThermalSimulator(inputs.building, inputs.heat_pump)

        # Use greedy algorithm (simpler than full DP for now)
        schedule, indoor_temps = self._greedy_optimize(
            simulator=simulator, inputs=inputs
        )

        # Calculate costs
        total_cost = self._calculate_cost(
            schedule=schedule,
            prices=inputs.electricity_prices,
            simulator=simulator,
            outdoor_temps=inputs.outdoor_temps,
            indoor_temps=indoor_temps[:-1],  # Exclude final temp
        )

        # Calculate baseline (always running in NORMAL mode)
        baseline_cost = self._calculate_baseline_cost(
            simulator=simulator, inputs=inputs
        )

        # Generate detailed schedule response
        detailed_schedule = self._create_detailed_schedule(
            modes=schedule,
            indoor_temps=indoor_temps,
            outdoor_temps=inputs.outdoor_temps,
            prices=inputs.electricity_prices,
            start_time=inputs.start_time,
        )

        result = {
            "schedule": detailed_schedule,
            "total_cost": total_cost,
            "baseline_cost": baseline_cost,
            "savings": baseline_cost - total_cost,
            "indoor_temps": indoor_temps[:-1],  # 24 values
        }

        logger.info(
            f"Optimization complete: Cost={total_cost:.2f} EUR, Savings={result['savings']:.2f} EUR"
        )

        return result

    def _greedy_optimize(
        self, simulator: ThermalSimulator, inputs: OptimizationInput
    ) -> Tuple[List[str], List[float]]:
        """
        Greedy optimization algorithm:

        Strategy:
        1. Find "price valleys" (cheap hours)
        2. Schedule BOOST mode during valleys
        3. Use ECO/OFF during expensive hours if we have thermal buffer
        4. Always maintain minimum comfort
        """
        n_hours = len(inputs.outdoor_temps)

        # Normalize prices to 0-100 scale for easier comparison
        price_min = min(inputs.electricity_prices)
        price_max = max(inputs.electricity_prices)
        price_range = price_max - price_min

        if price_range > 0:
            normalized_prices = [
                (p - price_min) / price_range * 100 for p in inputs.electricity_prices
            ]
        else:
            normalized_prices = [50.0] * n_hours

        # Classify hours by price level
        price_categories = []
        for price in normalized_prices:
            if price < 30:
                price_categories.append("cheap")
            elif price < 70:
                price_categories.append("moderate")
            else:
                price_categories.append("expensive")

        # Initial schedule: all NORMAL mode
        schedule = ["NORMAL"] * n_hours

        # Phase 1: Schedule BOOST during cheap hours
        for hour, category in enumerate(price_categories):
            if category == "cheap":
                schedule[hour] = "BOOST"

        # Phase 2: Try to use ECO/OFF during expensive hours
        # But only if we have thermal buffer
        indoor_temps = [inputs.current_indoor_temp]

        for hour in range(n_hours):
            t_current = indoor_temps[-1]

            # Check if we can afford to reduce heating
            if price_categories[hour] == "expensive":
                # If we're well above comfort min, try ECO
                if t_current > inputs.comfort_min_temp + 2.0:
                    schedule[hour] = "ECO"
                # If we're just at comfort, stay NORMAL
                elif t_current > inputs.comfort_min_temp + 0.5:
                    schedule[hour] = "NORMAL"
                else:
                    # Too cold, must heat
                    schedule[hour] = "BOOST"

            # Simulate this hour to update temperature
            heat_pump_on = schedule[hour] != "OFF"
            power_fractions = {"BOOST": 1.0, "NORMAL": 0.7, "ECO": 0.3, "OFF": 0.0}

            t_new = simulator.simulate_hour(
                t_indoor_current=t_current,
                t_outdoor=inputs.outdoor_temps[hour],
                heat_pump_on=heat_pump_on,
                heat_pump_power_fraction=power_fractions[schedule[hour]],
                solar_radiation=inputs.solar_radiation[hour],
            )

            indoor_temps.append(t_new)

            # Safety check: never let it get too cold
            if t_new < inputs.comfort_min_temp:
                schedule[hour] = "BOOST"
                # Re-simulate with BOOST
                t_new = simulator.simulate_hour(
                    t_indoor_current=t_current,
                    t_outdoor=inputs.outdoor_temps[hour],
                    heat_pump_on=True,
                    heat_pump_power_fraction=1.0,
                    solar_radiation=inputs.solar_radiation[hour],
                )
                indoor_temps[-1] = t_new

        return schedule, indoor_temps

    def _calculate_cost(
        self,
        schedule: List[str],
        prices: List[float],
        simulator: ThermalSimulator,
        outdoor_temps: List[float],
        indoor_temps: List[float],
    ) -> float:
        """Calculate total cost for a given schedule"""
        total_cost = 0.0

        for hour, mode in enumerate(schedule):
            # Energy consumption (kWh)
            energy = simulator.estimate_power_consumption(
                t_outdoor=outdoor_temps[hour], t_indoor=indoor_temps[hour], mode=mode
            )

            # Electricity cost (EUR/MWh -> EUR/kWh)
            cost = energy * (prices[hour] / 1000.0)

            total_cost += cost

        return total_cost

    def _calculate_baseline_cost(
        self, simulator: ThermalSimulator, inputs: OptimizationInput
    ) -> float:
        """Calculate cost of naive strategy (always NORMAL mode)"""
        baseline_schedule = ["NORMAL"] * len(inputs.outdoor_temps)

        # Simulate to get indoor temps
        indoor_temps = simulator.simulate_day(
            t_indoor_initial=inputs.current_indoor_temp,
            t_outdoor_hourly=inputs.outdoor_temps,
            heat_pump_schedule=[True] * 24,
            solar_radiation_hourly=inputs.solar_radiation,
        )

        return self._calculate_cost(
            schedule=baseline_schedule,
            prices=inputs.electricity_prices,
            simulator=simulator,
            outdoor_temps=inputs.outdoor_temps,
            indoor_temps=indoor_temps,
        )

    def _create_detailed_schedule(
        self,
        modes: List[str],
        indoor_temps: List[float],
        outdoor_temps: List[float],
        prices: List[float],
        start_time: datetime,
    ) -> List[Dict]:
        """Create human-readable schedule with explanations"""
        schedule = []

        for hour, mode in enumerate(modes):
            timestamp = start_time + timedelta(hours=hour)

            # Generate explanation
            price = prices[hour]
            t_indoor = indoor_temps[hour]
            t_outdoor = outdoor_temps[hour]

            if mode == "BOOST":
                if price < 40:
                    reason = (
                        f"Pre-heating during cheap electricity ({price:.1f} EUR/MWh)"
                    )
                else:
                    reason = f"Preventing temperature drop (outdoor: {t_outdoor:.1f}°C)"
            elif mode == "ECO":
                reason = f"Coasting on thermal mass during expensive hour ({price:.1f} EUR/MWh)"
            elif mode == "OFF":
                reason = f"Mild weather, no heating needed"
            else:  # NORMAL
                reason = f"Standard operation ({price:.1f} EUR/MWh)"

            schedule.append(
                {
                    "hour": hour,
                    "timestamp": timestamp,
                    "mode": mode,
                    "expected_indoor_temp": round(t_indoor, 1),
                    "outdoor_temp": round(t_outdoor, 1),
                    "electricity_price": round(price, 2),
                    "reason": reason,
                }
            )

        return schedule


# Singleton instance
optimizer = HeatPumpOptimizer()
