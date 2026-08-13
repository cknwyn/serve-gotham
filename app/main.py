import os
from typing import List, Optional
from fastapi import FastAPI, Depends, status, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.schemas import (
    IncidentCreate,
    IncidentResponse,
    IncidentStatusUpdate,
    IncidentStatus,
    EmergencyType,
    UnitCreate,
    UnitResponse,
    AssignmentResponse,
    NearbyIncidentResponse,
    NearestUnitResponse,
)
from app.services import incident_service, dispatch_service, geo_service
from app.websocket import manager

# Create database tables automatically on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Gotham Emergency Services Dispatch System",
    description="Backend vertical prototype for citizen emergency reports and real-time dispatcher management.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS configuration
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TODO: Production deployment requires dispatcher authentication and authorization (e.g. OAuth2 / JWT).


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Serve static dashboard UI
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    return FileResponse("app/static/index.html")


@app.get("/dispatcher", include_in_schema=False)
async def serve_dispatcher():
    return FileResponse("app/static/dispatcher.html")


@app.get("/citizen", include_in_schema=False)
async def serve_citizen():
    return FileResponse("app/static/citizen.html")


@app.get("/health", tags=["Health"])
def health_check():

    """Health status endpoint."""
    return {"status": "ok", "service": "gotham-emergency-dispatch"}


# -----------------------------------------------------------------------------
# Citizen API
# -----------------------------------------------------------------------------

@app.post(
    "/api/v1/reports",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Citizen Reports"],
    summary="Submit an emergency report",
    description="Allows citizens to submit an emergency report (FIRE, POLICE, MEDICAL)."
)
async def submit_emergency_report(
    report_data: IncidentCreate,
    db: Session = Depends(get_db)
):
    return await incident_service.create_report(db, report_data)


# -----------------------------------------------------------------------------
# Dispatcher API - Reports
# -----------------------------------------------------------------------------

@app.get(
    "/api/v1/dispatch/reports",
    response_model=List[IncidentResponse],
    tags=["Dispatcher Reports"],
    summary="List emergency reports",
    description="Lists all reported incidents with optional status filtering."
)
def list_reports(
    status: Optional[IncidentStatus] = Query(None, description="Filter incidents by status"),
    db: Session = Depends(get_db)
):
    return incident_service.list_reports(db, status_filter=status)


@app.get(
    "/api/v1/dispatch/reports/{incident_id}",
    response_model=IncidentResponse,
    tags=["Dispatcher Reports"],
    summary="Get single report details",
    description="Retrieves full details for a specific incident by ID."
)
def get_report_by_id(
    incident_id: str,
    db: Session = Depends(get_db)
):
    return incident_service.get_report(db, incident_id)


@app.patch(
    "/api/v1/dispatch/reports/{incident_id}/status",
    response_model=IncidentResponse,
    tags=["Dispatcher Reports"],
    summary="Update incident status",
    description="Updates the lifecycle status of an emergency report according to allowed state transitions."
)
async def update_report_status(
    incident_id: str,
    status_update: IncidentStatusUpdate,
    db: Session = Depends(get_db)
):
    return await incident_service.update_report_status(db, incident_id, status_update.status)


# -----------------------------------------------------------------------------
# Units API & Assignments
# -----------------------------------------------------------------------------

@app.post(
    "/api/v1/units",
    response_model=UnitResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Units"],
    summary="Create a new emergency response unit",
    description="Registers a new unit (FIRE, POLICE, MEDICAL) with a unique call sign."
)
def create_unit(
    unit_data: UnitCreate,
    db: Session = Depends(get_db)
):
    return dispatch_service.create_unit(db, unit_data)


@app.get(
    "/api/v1/dispatch/units",
    response_model=List[UnitResponse],
    tags=["Units"],
    summary="List emergency response units",
    description="Lists all registered units with optional filtering by unit_type."
)
def list_units(
    unit_type: Optional[EmergencyType] = Query(None, description="Filter units by type"),
    db: Session = Depends(get_db)
):
    return dispatch_service.list_units(db, unit_type=unit_type)


@app.post(
    "/api/v1/dispatch/reports/{incident_id}/units/{unit_id}",
    response_model=AssignmentResponse,
    status_code=status.HTTP_200_OK,
    tags=["Dispatch Assignments"],
    summary="Assign a unit to an incident",
    description="Assigns an AVAILABLE unit to an incident, marking unit as DISPATCHED and advancing incident status if ACKNOWLEDGED."
)
async def assign_unit_to_report(
    incident_id: str,
    unit_id: str,
    db: Session = Depends(get_db)
):
    return await dispatch_service.assign_unit(db, incident_id, unit_id)


# -----------------------------------------------------------------------------
# Geolocator & Spatial Map APIs
# -----------------------------------------------------------------------------

@app.get(
    "/api/v1/dispatch/map/geojson",
    tags=["Geolocator & Map"],
    summary="Get GeoJSON FeatureCollection",
    description="Returns standard GeoJSON FeatureCollection of all incidents and response units for map rendering."
)
def get_map_geojson(db: Session = Depends(get_db)):
    return geo_service.get_geojson_feature_collection(db)


@app.get(
    "/api/v1/dispatch/map/incidents/nearby",
    response_model=List[NearbyIncidentResponse],
    tags=["Geolocator & Map"],
    summary="Search incidents within a radius",
    description="Calculates Haversine distance and returns incidents within radius_km (default 10km) sorted by proximity."
)
def get_nearby_incidents(
    latitude: float = Query(..., ge=-90.0, le=90.0),
    longitude: float = Query(..., ge=-180.0, le=180.0),
    radius_km: float = Query(10.0, ge=0.1, le=1000.0),
    status: Optional[IncidentStatus] = Query(None),
    db: Session = Depends(get_db)
):
    return geo_service.find_nearby_incidents(
        db, latitude=latitude, longitude=longitude, radius_km=radius_km, status_filter=status
    )


@app.get(
    "/api/v1/dispatch/map/units/nearest",
    response_model=NearestUnitResponse,
    tags=["Geolocator & Map"],
    summary="Find nearest available unit",
    description="Finds nearest AVAILABLE unit to given coordinates using Haversine distance formula."
)
def get_nearest_unit(
    latitude: float = Query(..., ge=-90.0, le=90.0),
    longitude: float = Query(..., ge=-180.0, le=180.0),
    unit_type: Optional[EmergencyType] = Query(None),
    db: Session = Depends(get_db)
):
    res = geo_service.find_nearest_unit(db, latitude=latitude, longitude=longitude, unit_type=unit_type)
    if not res:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No available response unit found near the specified location"
        )
    return res



# -----------------------------------------------------------------------------
# Real-Time WebSocket Endpoint
# -----------------------------------------------------------------------------

@app.websocket("/ws/dispatch")
async def websocket_dispatch_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    """
    WebSocket connection endpoint for dispatcher clients.
    Sends initial snapshot of incidents on connection and streams real-time updates.
    """
    # Fetch active incidents snapshot
    incidents = incident_service.list_reports(db)
    snapshot_data = [
        IncidentResponse.model_validate(inc).model_dump(mode="json")
        for inc in incidents
    ]
    await manager.connect(websocket, snapshot_data)
    try:
        while True:
            # Keep connection alive; client can send heartbeat or ignore
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
