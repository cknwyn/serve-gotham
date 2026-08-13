from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class EmergencyType(str, Enum):
    FIRE = "FIRE"
    POLICE = "POLICE"
    MEDICAL = "MEDICAL"


class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(str, Enum):
    REPORTED = "REPORTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISPATCHED = "DISPATCHED"
    EN_ROUTE = "EN_ROUTE"
    ON_SCENE = "ON_SCENE"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


class UnitStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DISPATCHED = "DISPATCHED"
    BUSY = "BUSY"
    OFFLINE = "OFFLINE"


class IncidentCreate(BaseModel):
    type: EmergencyType
    description: str = Field(..., min_length=1, description="Description of the emergency")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude between -90 and 90")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude between -180 and 180")
    address: str | None = Field(default=None, description="Optional street address")
    priority: Priority


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus


class IncidentResponse(BaseModel):
    id: str
    type: EmergencyType
    description: str
    latitude: float
    longitude: float
    address: str | None = None
    priority: Priority
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UnitCreate(BaseModel):
    type: EmergencyType
    call_sign: str = Field(..., min_length=1, description="Unique call sign (e.g. MED-12)")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude between -90 and 90")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude between -180 and 180")


class UnitResponse(BaseModel):
    id: str
    type: EmergencyType
    call_sign: str
    status: UnitStatus
    latitude: float
    longitude: float

    model_config = ConfigDict(from_attributes=True)


class AssignmentResponse(BaseModel):
    id: str
    incident_id: str
    unit_id: str
    assigned_at: datetime
    unassigned_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# Geo & Spatial Schemas

class NearbyIncidentResponse(BaseModel):
    incident: IncidentResponse
    distance_km: float


class NearestUnitResponse(BaseModel):
    unit: UnitResponse
    distance_km: float
