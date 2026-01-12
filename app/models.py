"""
Pydantic models for request/response validation and SQLAlchemy models for database
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


# ============================================================================
# Enums
# ============================================================================


class InsulationLevel(str, Enum):
    """Building insulation quality"""

    LOW = "low"  # Old buildings, U-value > 0.4 W/m²K
    MEDIUM = "medium"  # Standard, U-value 0.2-0.4 W/m²K
    HIGH = "high"  # New/renovated, U-value < 0.2 W/m²K


class HeatPumpMode(str, Enum):
    """Operating modes for heat pump"""

    BOOST = "BOOST"  # Maximum heating, use during price valleys
    NORMAL = "NORMAL"  # Standard operation
    ECO = "ECO"  # Reduced heating, coast on thermal mass
    OFF = "OFF"  # Completely off (only for mild weather)


class HeatPumpType(str, Enum):
    """Type of heat pump system"""

    GSHP = "GSHP"  # Ground Source Heat Pump
    ASHP = "ASHP"  # Air Source Heat Pump (air-to-water)


# ============================================================================
# Database Models (SQLAlchemy)
# ============================================================================


class Device(Base):
    """Registered heat pump device"""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)

    # Location
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    # Building characteristics
    insulation_level = Column(String(255), nullable=False)
    floor_area = Column(Float, nullable=False)  # m²
    volume = Column(Float, nullable=False)  # m³
    thermal_mass = Column(Float, default=50000.0)  # J/K (heat capacity)

    # Heat pump specs
    heat_pump_type = Column(String(255), nullable=False)
    rated_power = Column(Float, nullable=False)  # kW
    cop_rating = Column(Float, default=3.5)  # Coefficient of Performance

    # User preferences
    comfort_min_temp = Column(Float, default=18.0)
    comfort_max_temp = Column(Float, default=24.0)

    # VPP participation
    vpp_enabled = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    measurements = relationship("Measurement", back_populates="device")


class Measurement(Base):
    """Historical temperature and power measurements"""

    __tablename__ = "measurements"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)

    timestamp = Column(DateTime, nullable=False, index=True)
    indoor_temp = Column(Float, nullable=False)  # °C
    outdoor_temp = Column(Float)  # °C
    power_consumption = Column(Float)  # kW
    heat_pump_mode = Column(String(32))

    device = relationship("Device", back_populates="measurements")


class PriceData(Base):
    """Electricity spot prices"""

    __tablename__ = "price_data"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    price = Column(Float, nullable=False)  # EUR/MWh
    area = Column(String(16), default="FI")
    created_at = Column(DateTime, default=datetime.utcnow)


class WeatherForecast(Base):
    """Weather forecast data"""

    __tablename__ = "weather_forecasts"

    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    temperature = Column(Float, nullable=False)  # °C
    solar_radiation = Column(Float)  # W/m²
    wind_speed = Column(Float)  # m/s
    created_at = Column(DateTime, default=datetime.utcnow)


class GridStatus(Base):
    """Real-time grid status from Fingrid"""

    __tablename__ = "grid_status"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    wind_power_percentage = Column(Float)  # % of total production
    frequency = Column(Float)  # Hz
    stress_level = Column(String(16))  # "normal", "warning", "critical"
    maintenance_events = Column(JSON)


# ============================================================================
# Pydantic Models (API Request/Response)
# ============================================================================


class DeviceRegistration(BaseModel):
    """Request model for registering a new device"""

    device_id: str = Field(..., description="Unique device identifier")
    name: str = Field(..., description="User-friendly name")

    latitude: float = Field(
        ..., ge=59.0, le=71.0, description="Latitude (Finland range)"
    )
    longitude: float = Field(
        ..., ge=19.0, le=32.0, description="Longitude (Finland range)"
    )

    insulation_level: InsulationLevel
    floor_area: float = Field(..., gt=0, le=500, description="Floor area in m²")
    volume: float = Field(..., gt=0, le=1500, description="Building volume in m³")

    heat_pump_type: HeatPumpType
    rated_power: float = Field(..., gt=0, le=50, description="Rated power in kW")
    cop_rating: float = Field(default=3.5, ge=2.0, le=5.0)

    comfort_min_temp: float = Field(default=18.0, ge=15.0, le=20.0)
    comfort_max_temp: float = Field(default=24.0, ge=20.0, le=26.0)

    vpp_enabled: bool = Field(default=False)

    @validator("comfort_max_temp")
    def validate_temp_range(cls, v, values):
        if "comfort_min_temp" in values and v <= values["comfort_min_temp"]:
            raise ValueError("comfort_max_temp must be greater than comfort_min_temp")
        return v


class DeviceResponse(BaseModel):
    """Response model for device information"""

    id: int
    device_id: str
    name: str
    latitude: float
    longitude: float
    insulation_level: str
    heat_pump_type: str
    vpp_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class HourlySchedule(BaseModel):
    """Single hour in the optimization schedule"""

    hour: int = Field(..., ge=0, le=23)
    timestamp: datetime
    mode: HeatPumpMode
    expected_indoor_temp: float
    outdoor_temp: float
    electricity_price: float
    reason: str = Field(..., description="Explanation for this mode choice")


class DailyPlanRequest(BaseModel):
    """Request for daily optimization plan"""

    device_id: str
    target_date: Optional[datetime] = None  # Defaults to tomorrow


class DailyPlanResponse(BaseModel):
    """Response with 24-hour optimization schedule"""

    device_id: str
    generated_at: datetime
    schedule: List[HourlySchedule]
    estimated_cost: float = Field(
        ..., description="Total estimated cost for the day in EUR"
    )
    estimated_savings: float = Field(..., description="Savings vs. baseline in EUR")
    total_energy_kwh: float


class ComfortRiskRequest(BaseModel):
    """Request for comfort risk analysis"""

    device_id: str
    proposed_schedule: List[dict]  # List of {hour, mode}


class ComfortRiskResponse(BaseModel):
    """Response with comfort risk assessment"""

    device_id: str
    comfort_score: float = Field(
        ..., ge=0, le=100, description="100 = perfect comfort, 0 = unacceptable"
    )
    min_predicted_temp: float
    max_predicted_temp: float
    hours_below_comfort: int
    warnings: List[str]
    recommendation: str


class DemandResponseRequest(BaseModel):
    """Request to trigger demand response event"""

    duration_minutes: int = Field(..., ge=5, le=60)
    severity: str = Field(..., description="normal, high, critical")
    affected_areas: List[str] = Field(default=["FI"])


class DemandResponseResponse(BaseModel):
    """Response from demand response trigger"""

    event_id: str
    devices_notified: int
    estimated_load_reduction_mw: float
    start_time: datetime
    end_time: datetime
