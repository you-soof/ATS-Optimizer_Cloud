"""
ATS-Optimizer FastAPI Application

Main API endpoints for the Adaptive Thermal-Storage Heat Pump Optimizer
"""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
import logging
import os
from contextlib import asynccontextmanager

from app.database import get_db, init_db
from app.models import (
    Device,
    DeviceRegistration,
    DeviceResponse,
    DailyPlanRequest,
    DailyPlanResponse,
    HourlySchedule,
    ComfortRiskRequest,
    ComfortRiskResponse,
    DemandResponseRequest,
    DemandResponseResponse,
)
from app.optimization import optimizer, OptimizationInput
from app.thermal_model import (
    BuildingParameters,
    HeatPumpParameters,
    ThermalSimulator,
    calculate_comfort_score,
)
from app.external_apis.weather import weather_api
from app.external_apis.spotutilarian import entsoe_api
from app.external_apis.fingrid import fingrid_api

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="ATS-Optimizer API",
    description="Adaptive Thermal-Storage & Heat Pump Optimizer for Nordic Buildings",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# # CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# ============================================================================
# Startup/Shutdown Events
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize database and connections on startup"""
    logger.info("Starting ATS-Optimizer API...")
    init_db()
    logger.info("✓ ATS-Optimizer API ready")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "service": "ATS-Optimizer",
    }


# ============================================================================
# Device Management Endpoints
# ============================================================================


@app.post(
    "/devices/register",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_device(device: DeviceRegistration, db: Session = Depends(get_db)):
    """
    Register a new heat pump device

    This is the first step - users must register their building and heat pump
    characteristics before getting optimization recommendations.
    """
    # Check if device already exists
    existing = db.query(Device).filter(Device.device_id == device.device_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Device {device.device_id} already registered",
        )

    # Create new device
    db_device = Device(
        device_id=device.device_id,
        name=device.name,
        latitude=device.latitude,
        longitude=device.longitude,
        insulation_level=device.insulation_level.value,
        floor_area=device.floor_area,
        volume=device.volume,
        heat_pump_type=device.heat_pump_type.value,
        rated_power=device.rated_power,
        cop_rating=device.cop_rating,
        comfort_min_temp=device.comfort_min_temp,
        comfort_max_temp=device.comfort_max_temp,
        vpp_enabled=device.vpp_enabled,
    )

    db.add(db_device)
    db.commit()
    db.refresh(db_device)

    logger.info(f"Registered new device: {device.device_id}")

    return db_device


@app.get("/devices/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: str, db: Session = Depends(get_db)):
    """Get device information"""
    device = db.query(Device).filter(Device.device_id == device_id).first()
    print(device)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {device_id} not found",
        )

    return device


@app.get("/devices", response_model=List[DeviceResponse])
async def list_devices(db: Session = Depends(get_db)):
    """List all registered devices"""
    devices = db.query(Device).all()
    return devices


# ============================================================================
# Endpoint A: Daily Optimization Plan
# ============================================================================


@app.post("/strategy/daily-plan", response_model=DailyPlanResponse)
async def get_daily_plan(request: DailyPlanRequest, db: Session = Depends(get_db)):
    """
    Get 24-hour optimized heat pump schedule

    This is the main optimization endpoint. It:
    1. Fetches weather forecast
    2. Fetches electricity prices
    3. Runs optimization algorithm
    4. Returns hourly schedule with modes (BOOST/NORMAL/ECO/OFF)

    The optimization tries to:
    - Heat during cheap electricity hours
    - Coast on thermal mass during expensive hours
    - Always maintain comfort
    """
    # Get device
    device = db.query(Device).filter(Device.device_id == request.device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {request.device_id} not found. Please register first.",
        )

    # Determine target date (default to tomorrow for day-ahead prices)
    target_date = request.target_date or (datetime.now() + timedelta(days=1))
    target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)

    logger.info(f"Generating daily plan for {device.device_id} on {target_date.date()}")

    try:
        # Fetch weather forecast
        weather_data = await weather_api.get_forecast(
            latitude=device.latitude, longitude=device.longitude, hours=24
        )

        # Fetch electricity prices
        price_data = await entsoe_api.get_day_ahead_prices(area="FI", date=target_date)
        print(
            {
                "weather": weather_data,
                "prices": price_data,
            }
        )
        # Prepare optimization inputs
        building = BuildingParameters(
            floor_area=device.floor_area,
            volume=device.volume,
            insulation_level=device.insulation_level,
        )

        heat_pump = HeatPumpParameters(
            type=device.heat_pump_type,
            rated_power=device.rated_power,
            rated_cop=device.cop_rating,
        )

        # Assume current indoor temp is at comfort midpoint
        current_temp = (device.comfort_min_temp + device.comfort_max_temp) / 2

        opt_input = OptimizationInput(
            building=building,
            heat_pump=heat_pump,
            current_indoor_temp=current_temp,
            outdoor_temps=weather_data["temperature"][:24],
            electricity_prices=price_data["prices"][:24],
            solar_radiation=weather_data["solar_radiation"][:24],
            comfort_min_temp=device.comfort_min_temp,
            comfort_max_temp=device.comfort_max_temp,
            start_time=target_date,
        )

        # Run optimization
        result = optimizer.optimize(opt_input)

        # Build response
        response = DailyPlanResponse(
            device_id=device.device_id,
            generated_at=datetime.now(),
            schedule=[HourlySchedule(**item) for item in result["schedule"]],
            estimated_cost=result["total_cost"],
            estimated_savings=result["savings"],
            total_energy_kwh=sum(
                device.rated_power * 0.7 for _ in range(24)  # Approximate average
            ),
        )

        logger.info(
            f"Generated plan for {device.device_id}: "
            f"Cost={result['total_cost']:.2f} EUR, "
            f"Savings={result['savings']:.2f} EUR"
        )

        return response

    except Exception as e:
        logger.error(f"Error generating daily plan: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate optimization plan: {str(e)}",
        )


# ============================================================================
# Endpoint B: Comfort Risk Analysis
# ============================================================================


@app.post("/analytics/comfort-risk", response_model=ComfortRiskResponse)
async def analyze_comfort_risk(
    request: ComfortRiskRequest, db: Session = Depends(get_db)
):
    """
    Analyze comfort risk of a proposed schedule

    This endpoint simulates the proposed schedule and checks if indoor
    temperature will stay within comfort bounds. Returns a comfort score
    (0-100) and warnings about potential issues.

    Useful for users who want to manually adjust the schedule.
    """
    # Get device
    device = db.query(Device).filter(Device.device_id == request.device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {request.device_id} not found",
        )

    try:
        # Fetch weather forecast
        weather_data = await weather_api.get_forecast(
            latitude=device.latitude, longitude=device.longitude, hours=24
        )

        # Create thermal simulator
        building = BuildingParameters(
            floor_area=device.floor_area,
            volume=device.volume,
            insulation_level=device.insulation_level,
        )

        heat_pump = HeatPumpParameters(
            type=device.heat_pump_type,
            rated_power=device.rated_power,
            rated_cop=device.cop_rating,
        )

        simulator = ThermalSimulator(building, heat_pump)

        # Extract schedule
        schedule = [item["mode"] != "OFF" for item in request.proposed_schedule]

        # Simulate
        current_temp = (device.comfort_min_temp + device.comfort_max_temp) / 2
        indoor_temps = simulator.simulate_day(
            t_indoor_initial=current_temp,
            t_outdoor_hourly=weather_data["temperature"][:24],
            heat_pump_schedule=schedule,
            solar_radiation_hourly=weather_data["solar_radiation"][:24],
        )

        # Calculate comfort score
        comfort_score, hours_outside = calculate_comfort_score(
            indoor_temps=indoor_temps,
            comfort_min=device.comfort_min_temp,
            comfort_max=device.comfort_max_temp,
        )

        # Generate warnings
        warnings = []
        if min(indoor_temps) < device.comfort_min_temp:
            warnings.append(f"Temperature may drop to {min(indoor_temps):.1f}°C")
        if min(indoor_temps) < 16.0:
            warnings.append("⚠️ CRITICAL: Risk of pipe freezing!")
        if hours_outside > 6:
            warnings.append(f"Uncomfortable for {hours_outside} hours")

        # Generate recommendation
        if comfort_score >= 90:
            recommendation = "Schedule looks good!"
        elif comfort_score >= 70:
            recommendation = "Acceptable, but consider more heating during cold periods"
        else:
            recommendation = "Not recommended - temperature will drop too much"

        return ComfortRiskResponse(
            device_id=device.device_id,
            comfort_score=comfort_score,
            min_predicted_temp=min(indoor_temps),
            max_predicted_temp=max(indoor_temps),
            hours_below_comfort=hours_outside,
            warnings=warnings,
            recommendation=recommendation,
        )

    except Exception as e:
        logger.error(f"Error analyzing comfort risk: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze comfort risk: {str(e)}",
        )


# ============================================================================
# Endpoint C: Demand Response (VPP)
# ============================================================================


@app.post("/grid/demand-response", response_model=DemandResponseResponse)
async def trigger_demand_response(
    request: DemandResponseRequest, db: Session = Depends(get_db)
):
    """
    Trigger demand response event for grid stabilization

    This endpoint is called by VPP aggregators or grid operators when
    the grid is under stress. It sends SHUTDOWN commands to participating
    heat pumps to reduce load temporarily.

    This is critical for grid stability during:
    - Unexpected plant outages
    - Extreme weather events
    - Frequency deviations
    """
    logger.warning(
        f"Demand response triggered: {request.severity} severity, "
        f"duration {request.duration_minutes} minutes"
    )

    # Get all VPP-enabled devices
    devices = db.query(Device).filter(Device.vpp_enabled == True).all()

    if not devices:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No VPP-enabled devices found"
        )

    # Estimate load reduction (assuming 8 kW average per device)
    estimated_reduction = len(devices) * 8 / 1000  # MW

    # Generate event ID
    event_id = f"DR-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # In production, this would send MQTT messages to all devices
    # For now, we just log it
    for device in devices:
        logger.info(f"Sending demand response to device {device.device_id}")
        # TODO: Send MQTT message
        # mqtt_client.publish(f"ats/{device.device_id}/control", "SHUTDOWN")

    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=request.duration_minutes)

    return DemandResponseResponse(
        event_id=event_id,
        devices_notified=len(devices),
        estimated_load_reduction_mw=estimated_reduction,
        start_time=start_time,
        end_time=end_time,
    )


# ============================================================================
# Additional Utility Endpoints
# ============================================================================


@app.get("/forecasts/price-carbon")
async def get_price_carbon_forecast():
    """
    Get combined 48-hour forecast of electricity prices and carbon intensity

    This helps users see when electricity is both cheap AND green.
    """
    # Fetch price forecast
    price_data = await entsoe_api.get_day_ahead_prices(area="FI")

    # Fetch grid status
    grid_status = await fingrid_api.get_grid_status()

    # Fetch wind forecast
    wind_forecast = await fingrid_api.get_wind_forecast(hours=48)

    # Combine data
    combined = []
    for i in range(
        min(len(price_data["prices"]), len(wind_forecast["wind_percentage"]))
    ):
        combined.append(
            {
                "timestamp": price_data["timestamps"][i],
                "price_eur_mwh": price_data["prices"][i],
                "wind_percentage": wind_forecast["wind_percentage"][i],
                "is_green": wind_forecast["wind_percentage"][i] > 30,
                "is_cheap": price_data["prices"][i] < 50,
            }
        )

    return {
        "forecast": combined,
        "current_wind_percentage": grid_status["wind_percentage"],
        "grid_stress_level": grid_status["stress_level"],
    }


@app.get("/strategy/current-action/{device_id}")
async def get_current_action(device_id: str, db: Session = Depends(get_db)):
    """
    Get immediate action: Should the heat pump run RIGHT NOW?

    This is a real-time decision endpoint for immediate control.
    """
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {device_id} not found",
        )

    # Get current conditions
    weather_data = await weather_api.get_forecast(
        latitude=device.latitude, longitude=device.longitude, hours=1
    )

    price_data = await entsoe_api.get_day_ahead_prices(area="FI")
    grid_status = await fingrid_api.get_grid_status()

    current_hour = datetime.now().hour
    current_temp = weather_data["temperature"][0]
    current_price = (
        price_data["prices"][current_hour]
        if current_hour < len(price_data["prices"])
        else 50.0
    )

    # Simple decision logic
    if grid_status["stress_level"] == "critical":
        action = "OFF"
        reason = "Grid emergency - demand response active"
    elif current_temp < -15 and current_price < 60:
        action = "BOOST"
        reason = f"Very cold ({current_temp}°C) and reasonable price"
    elif current_price < 30:
        action = "BOOST"
        reason = "Cheap electricity - pre-heating"
    elif current_price > 80:
        action = "ECO"
        reason = "Expensive electricity - coasting"
    else:
        action = "NORMAL"
        reason = "Standard operation"

    return {
        "device_id": device_id,
        "timestamp": datetime.now(),
        "recommended_mode": action,
        "reason": reason,
        "current_conditions": {
            "outdoor_temp": current_temp,
            "electricity_price": current_price,
            "grid_stress": grid_status["stress_level"],
            "wind_percentage": grid_status["wind_percentage"],
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
