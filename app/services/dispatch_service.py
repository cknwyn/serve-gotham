from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import Unit, Incident, Assignment
from app.schemas import UnitCreate, EmergencyType, UnitStatus, IncidentStatus
from app.websocket import manager
from app.services.incident_service import get_report


def create_unit(db: Session, unit_data: UnitCreate) -> Unit:
    existing = db.query(Unit).filter(Unit.call_sign == unit_data.call_sign).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unit with call sign '{unit_data.call_sign}' already exists"
        )

    unit = Unit(
        type=unit_data.type.value,
        call_sign=unit_data.call_sign,
        latitude=unit_data.latitude,
        longitude=unit_data.longitude,
        status=UnitStatus.AVAILABLE.value,
    )
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


def list_units(db: Session, unit_type: EmergencyType | None = None) -> list[Unit]:
    query = db.query(Unit)
    if unit_type:
        query = query.filter(Unit.type == unit_type.value)
    return query.order_by(Unit.call_sign.asc()).all()


def get_unit(db: Session, unit_id: str) -> Unit:
    unit = db.query(Unit).filter(Unit.id == unit_id).first()
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit '{unit_id}' not found"
        )
    return unit


async def assign_unit(db: Session, incident_id: str, unit_id: str) -> Assignment:
    incident = get_report(db, incident_id)
    unit = get_unit(db, unit_id)

    if unit.status != UnitStatus.AVAILABLE.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unit '{unit.call_sign}' is not available (current status: '{unit.status}')"
        )

    # Create assignment record
    assignment = Assignment(
        incident_id=incident.id,
        unit_id=unit.id,
        assigned_at=datetime.now(timezone.utc),
    )
    db.add(assignment)

    # Change unit status to DISPATCHED
    unit.status = UnitStatus.DISPATCHED.value

    # If incident is ACKNOWLEDGED, transition to DISPATCHED
    if incident.status == IncidentStatus.ACKNOWLEDGED.value:
        incident.status = IncidentStatus.DISPATCHED.value
        incident.updated_at = datetime.now(timezone.utc)

    # Transactional commit
    db.commit()
    db.refresh(assignment)

    # Broadcast event
    await manager.broadcast({
        "event": "UNIT_ASSIGNED",
        "incident_id": incident.id,
        "unit_id": unit.id,
        "unit_call_sign": unit.call_sign,
        "status": "DISPATCHED"
    })

    return assignment
