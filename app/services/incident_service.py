from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import Incident
from app.schemas import IncidentCreate, IncidentStatus, IncidentResponse
from app.websocket import manager


VALID_TRANSITIONS = {
    IncidentStatus.REPORTED: {IncidentStatus.ACKNOWLEDGED, IncidentStatus.CANCELLED},
    IncidentStatus.ACKNOWLEDGED: {IncidentStatus.DISPATCHED, IncidentStatus.CANCELLED},
    IncidentStatus.DISPATCHED: {IncidentStatus.EN_ROUTE, IncidentStatus.CANCELLED},
    IncidentStatus.EN_ROUTE: {IncidentStatus.ON_SCENE, IncidentStatus.CANCELLED},
    IncidentStatus.ON_SCENE: {IncidentStatus.RESOLVED},
    IncidentStatus.RESOLVED: set(),
    IncidentStatus.CANCELLED: set(),
}


async def create_report(db: Session, report_data: IncidentCreate) -> Incident:
    incident = Incident(
        type=report_data.type.value,
        description=report_data.description,
        latitude=report_data.latitude,
        longitude=report_data.longitude,
        address=report_data.address,
        priority=report_data.priority.value,
        status=IncidentStatus.REPORTED.value,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    # Broadcast event via WebSockets
    incident_resp = IncidentResponse.model_validate(incident).model_dump(mode="json")
    await manager.broadcast({
        "event": "INCIDENT_CREATED",
        "incident": incident_resp
    })

    return incident


def list_reports(db: Session, status_filter: IncidentStatus | None = None) -> list[Incident]:
    query = db.query(Incident)
    if status_filter:
        query = query.filter(Incident.status == status_filter.value)
    return query.order_by(Incident.created_at.desc()).all()


def get_report(db: Session, incident_id: str) -> Incident:
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found"
        )
    return incident


async def update_report_status(db: Session, incident_id: str, new_status: IncidentStatus) -> Incident:
    incident = get_report(db, incident_id)

    current_status = IncidentStatus(incident.status)
    allowed_next = VALID_TRANSITIONS.get(current_status, set())

    if new_status not in allowed_next:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid status transition from '{current_status.value}' to '{new_status.value}'"
        )

    incident.status = new_status.value
    incident.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(incident)

    incident_resp = IncidentResponse.model_validate(incident).model_dump(mode="json")
    await manager.broadcast({
        "event": "INCIDENT_STATUS_UPDATED",
        "incident": incident_resp
    })

    return incident
