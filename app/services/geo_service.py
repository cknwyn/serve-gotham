import math
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import Incident, Unit
from app.schemas import EmergencyType, UnitStatus, IncidentStatus


EARTH_RADIUS_KM = 6371.0


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees) using the Haversine formula.
    """
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def get_geojson_feature_collection(db: Session) -> dict:
    """
    Generate standard GeoJSON FeatureCollection of all incidents and response units.
    """
    incidents = db.query(Incident).all()
    units = db.query(Unit).all()

    features = []

    # Map incidents
    for inc in incidents:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [inc.longitude, inc.latitude]
            },
            "properties": {
                "id": inc.id,
                "entity_type": "incident",
                "type": inc.type,
                "description": inc.description,
                "address": inc.address,
                "priority": inc.priority,
                "status": inc.status,
                "created_at": inc.created_at.isoformat() if inc.created_at else None,
            }
        })

    # Map response units
    for u in units:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [u.longitude, u.latitude]
            },
            "properties": {
                "id": u.id,
                "entity_type": "unit",
                "type": u.type,
                "call_sign": u.call_sign,
                "status": u.status,
            }
        })

    return {
        "type": "FeatureCollection",
        "features": features
    }


def find_nearby_incidents(
    db: Session,
    latitude: float,
    longitude: float,
    radius_km: float = 10.0,
    status_filter: Optional[IncidentStatus] = None
) -> List[dict]:
    """
    Find incidents within a specified radius (in km) sorted by distance.
    """
    query = db.query(Incident)
    if status_filter:
        query = query.filter(Incident.status == status_filter.value)
    
    incidents = query.all()
    results = []

    for inc in incidents:
        dist = haversine_distance_km(latitude, longitude, inc.latitude, inc.longitude)
        if dist <= radius_km:
            results.append({
                "incident": inc,
                "distance_km": round(dist, 2)
            })

    results.sort(key=lambda x: x["distance_km"])
    return results


def find_nearest_unit(
    db: Session,
    latitude: float,
    longitude: float,
    unit_type: Optional[EmergencyType] = None,
    must_be_available: bool = True
) -> Optional[dict]:
    """
    Find nearest unit to a location, optionally filtered by emergency type and availability.
    """
    query = db.query(Unit)
    if unit_type:
        query = query.filter(Unit.type == unit_type.value)
    if must_be_available:
        query = query.filter(Unit.status == UnitStatus.AVAILABLE.value)

    units = query.all()
    if not units:
        return None

    nearest = None
    min_dist = float("inf")

    for u in units:
        dist = haversine_distance_km(latitude, longitude, u.latitude, u.longitude)
        if dist < min_dist:
            min_dist = dist
            nearest = u

    if nearest:
        return {
            "unit": nearest,
            "distance_km": round(min_dist, 2)
        }
    return None
