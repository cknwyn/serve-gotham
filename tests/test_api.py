import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# Setup in-memory SQLite database for testing
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


client = TestClient(app)


# -----------------------------------------------------------------------------
# 1. Health Check
# -----------------------------------------------------------------------------

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "gotham-emergency-dispatch"}


# -----------------------------------------------------------------------------
# 2. Incident Creation & Validation
# -----------------------------------------------------------------------------

def test_create_incident_success():
    payload = {
        "type": "MEDICAL",
        "description": "Person collapsed outside the building.",
        "latitude": 14.5995,
        "longitude": 120.9842,
        "address": "123 Gotham Avenue",
        "priority": "HIGH",
    }
    response = client.post("/api/v1/reports", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["type"] == "MEDICAL"
    assert data["status"] == "REPORTED"
    assert data["description"] == "Person collapsed outside the building."
    assert data["latitude"] == 14.5995
    assert data["longitude"] == 120.9842
    assert data["address"] == "123 Gotham Avenue"
    assert data["priority"] == "HIGH"
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.parametrize(
    "invalid_field, payload",
    [
        ("latitude_too_high", {
            "type": "FIRE",
            "description": "Fire in alley",
            "latitude": 95.0,
            "longitude": 10.0,
            "priority": "CRITICAL"
        }),
        ("latitude_too_low", {
            "type": "FIRE",
            "description": "Fire in alley",
            "latitude": -95.0,
            "longitude": 10.0,
            "priority": "CRITICAL"
        }),
        ("longitude_too_high", {
            "type": "FIRE",
            "description": "Fire in alley",
            "latitude": 10.0,
            "longitude": 185.0,
            "priority": "CRITICAL"
        }),
        ("longitude_too_low", {
            "type": "FIRE",
            "description": "Fire in alley",
            "latitude": 10.0,
            "longitude": -185.0,
            "priority": "CRITICAL"
        }),
        ("invalid_type", {
            "type": "ALIEN_ATTACK",
            "description": "UFO landed",
            "latitude": 10.0,
            "longitude": 10.0,
            "priority": "CRITICAL"
        }),
        ("missing_description", {
            "type": "POLICE",
            "description": "",
            "latitude": 10.0,
            "longitude": 10.0,
            "priority": "LOW"
        }),
    ],
)
def test_create_incident_validation_errors(invalid_field, payload):
    response = client.post("/api/v1/reports", json=payload)
    assert response.status_code == 422


# -----------------------------------------------------------------------------
# 3. Incident Retrieval & Filtering
# -----------------------------------------------------------------------------

def test_list_and_get_incidents():
    # Create two incidents
    r1 = client.post("/api/v1/reports", json={
        "type": "FIRE", "description": "Building fire", "latitude": 40.0, "longitude": -74.0, "priority": "CRITICAL"
    }).json()
    r2 = client.post("/api/v1/reports", json={
        "type": "POLICE", "description": "Robbery in progress", "latitude": 40.1, "longitude": -74.1, "priority": "HIGH"
    }).json()

    # List all
    res = client.get("/api/v1/dispatch/reports")
    assert res.status_code == 200
    incidents = res.json()
    assert len(incidents) == 2

    # Filter by status
    res_filtered = client.get("/api/v1/dispatch/reports?status=REPORTED")
    assert res_filtered.status_code == 200
    assert len(res_filtered.json()) == 2

    res_empty = client.get("/api/v1/dispatch/reports?status=RESOLVED")
    assert res_empty.status_code == 200
    assert len(res_empty.json()) == 0

    # Get single incident
    res_single = client.get(f"/api/v1/dispatch/reports/{r1['id']}")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == r1["id"]


def test_get_nonexistent_incident():
    response = client.get("/api/v1/dispatch/reports/non-existent-id")
    assert response.status_code == 404


# -----------------------------------------------------------------------------
# 4. Status Lifecycle & Invalid Transitions
# -----------------------------------------------------------------------------

def test_valid_status_lifecycle():
    report = client.post("/api/v1/reports", json={
        "type": "MEDICAL", "description": "Heart attack", "latitude": 40.0, "longitude": -74.0, "priority": "CRITICAL"
    }).json()
    inc_id = report["id"]

    # REPORTED -> ACKNOWLEDGED
    res = client.patch(f"/api/v1/dispatch/reports/{inc_id}/status", json={"status": "ACKNOWLEDGED"})
    assert res.status_code == 200
    assert res.json()["status"] == "ACKNOWLEDGED"

    # ACKNOWLEDGED -> DISPATCHED
    res = client.patch(f"/api/v1/dispatch/reports/{inc_id}/status", json={"status": "DISPATCHED"})
    assert res.status_code == 200
    assert res.json()["status"] == "DISPATCHED"

    # DISPATCHED -> EN_ROUTE
    res = client.patch(f"/api/v1/dispatch/reports/{inc_id}/status", json={"status": "EN_ROUTE"})
    assert res.status_code == 200
    assert res.json()["status"] == "EN_ROUTE"

    # EN_ROUTE -> ON_SCENE
    res = client.patch(f"/api/v1/dispatch/reports/{inc_id}/status", json={"status": "ON_SCENE"})
    assert res.status_code == 200
    assert res.json()["status"] == "ON_SCENE"

    # ON_SCENE -> RESOLVED
    res = client.patch(f"/api/v1/dispatch/reports/{inc_id}/status", json={"status": "RESOLVED"})
    assert res.status_code == 200
    assert res.json()["status"] == "RESOLVED"


def test_invalid_status_transitions():
    report = client.post("/api/v1/reports", json={
        "type": "FIRE", "description": "Alarm ringing", "latitude": 40.0, "longitude": -74.0, "priority": "LOW"
    }).json()
    inc_id = report["id"]

    # REPORTED -> RESOLVED (invalid, 409)
    res = client.patch(f"/api/v1/dispatch/reports/{inc_id}/status", json={"status": "RESOLVED"})
    assert res.status_code == 409

    # Cancel report: REPORTED -> CANCELLED
    res_cancel = client.patch(f"/api/v1/dispatch/reports/{inc_id}/status", json={"status": "CANCELLED"})
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "CANCELLED"

    # CANCELLED -> DISPATCHED (invalid, 409)
    res_invalid = client.patch(f"/api/v1/dispatch/reports/{inc_id}/status", json={"status": "DISPATCHED"})
    assert res_invalid.status_code == 409


# -----------------------------------------------------------------------------
# 5. Units & Duplicate Call Signs
# -----------------------------------------------------------------------------

def test_unit_creation_and_filtering():
    unit1_payload = {"type": "MEDICAL", "call_sign": "MED-12", "latitude": 14.6000, "longitude": 120.9850}
    res1 = client.post("/api/v1/units", json=unit1_payload)
    assert res1.status_code == 201
    data1 = res1.json()
    assert data1["call_sign"] == "MED-12"
    assert data1["status"] == "AVAILABLE"

    unit2_payload = {"type": "FIRE", "call_sign": "FIRE-01", "latitude": 14.6100, "longitude": 120.9860}
    res2 = client.post("/api/v1/units", json=unit2_payload)
    assert res2.status_code == 201

    # List all units
    res_all = client.get("/api/v1/dispatch/units")
    assert res_all.status_code == 200
    assert len(res_all.json()) == 2

    # Filter by type
    res_med = client.get("/api/v1/dispatch/units?unit_type=MEDICAL")
    assert res_med.status_code == 200
    assert len(res_med.json()) == 1
    assert res_med.json()[0]["call_sign"] == "MED-12"


def test_duplicate_call_sign():
    unit_payload = {"type": "POLICE", "call_sign": "POLICE-99", "latitude": 40.0, "longitude": -74.0}
    client.post("/api/v1/units", json=unit_payload)

    # Attempt duplicate
    res_dup = client.post("/api/v1/units", json=unit_payload)
    assert res_dup.status_code == 409
    assert "already exists" in res_dup.json()["detail"]


# -----------------------------------------------------------------------------
# 6. Unit Assignment
# -----------------------------------------------------------------------------

def test_unit_assignment_success():
    # 1. Create incident
    report = client.post("/api/v1/reports", json={
        "type": "MEDICAL", "description": "Fainting incident", "latitude": 40.0, "longitude": -74.0, "priority": "MEDIUM"
    }).json()
    inc_id = report["id"]

    # 2. Transition incident to ACKNOWLEDGED
    client.patch(f"/api/v1/dispatch/reports/{inc_id}/status", json={"status": "ACKNOWLEDGED"})

    # 3. Create unit
    unit = client.post("/api/v1/units", json={
        "type": "MEDICAL", "call_sign": "MED-55", "latitude": 40.01, "longitude": -74.01
    }).json()
    unit_id = unit["id"]

    # 4. Assign unit to incident
    assign_res = client.post(f"/api/v1/dispatch/reports/{inc_id}/units/{unit_id}")
    assert assign_res.status_code == 200
    assignment = assign_res.json()
    assert assignment["incident_id"] == inc_id
    assert assignment["unit_id"] == unit_id

    # 5. Verify unit is now DISPATCHED
    res_units = client.get("/api/v1/dispatch/units?unit_type=MEDICAL")
    assigned_unit = [u for u in res_units.json() if u["id"] == unit_id][0]
    assert assigned_unit["status"] == "DISPATCHED"

    # 6. Verify incident status transitioned to DISPATCHED
    res_inc = client.get(f"/api/v1/dispatch/reports/{inc_id}")
    assert res_inc.json()["status"] == "DISPATCHED"


def test_assign_unavailable_unit():
    report = client.post("/api/v1/reports", json={
        "type": "FIRE", "description": "Kitchen fire", "latitude": 40.0, "longitude": -74.0, "priority": "HIGH"
    }).json()
    unit = client.post("/api/v1/units", json={
        "type": "FIRE", "call_sign": "FIRE-99", "latitude": 40.0, "longitude": -74.0
    }).json()

    # First assignment
    client.post(f"/api/v1/dispatch/reports/{report['id']}/units/{unit['id']}")

    # Create second report
    report2 = client.post("/api/v1/reports", json={
        "type": "FIRE", "description": "Trash fire", "latitude": 40.05, "longitude": -74.05, "priority": "LOW"
    }).json()

    # Attempt second assignment with same unit (now DISPATCHED)
    assign_res2 = client.post(f"/api/v1/dispatch/reports/{report2['id']}/units/{unit['id']}")
    assert assign_res2.status_code == 409
    assert "not available" in assign_res2.json()["detail"]


def test_assign_missing_resources():
    # Missing incident
    unit = client.post("/api/v1/units", json={
        "type": "POLICE", "call_sign": "POLICE-10", "latitude": 40.0, "longitude": -74.0
    }).json()
    res1 = client.post(f"/api/v1/dispatch/reports/invalid-inc-id/units/{unit['id']}")
    assert res1.status_code == 404

    # Missing unit
    report = client.post("/api/v1/reports", json={
        "type": "POLICE", "description": "Traffic stop", "latitude": 40.0, "longitude": -74.0, "priority": "LOW"
    }).json()
    res2 = client.post(f"/api/v1/dispatch/reports/{report['id']}/units/invalid-unit-id")
    assert res2.status_code == 404


# -----------------------------------------------------------------------------
# 7. WebSocket Dispatcher Endpoint
# -----------------------------------------------------------------------------

def test_websocket_dispatcher():
    # Create an initial report
    client.post("/api/v1/reports", json={
        "type": "FIRE", "description": "Smoke reported", "latitude": 40.0, "longitude": -74.0, "priority": "MEDIUM"
    })

    with client.websocket_connect("/ws/dispatch") as websocket:
        # Receive initial snapshot
        data = websocket.receive_json()
        assert data["event"] == "INITIAL_SNAPSHOT"
        assert isinstance(data["incidents"], list)
        assert len(data["incidents"]) == 1
        assert data["incidents"][0]["type"] == "FIRE"


# -----------------------------------------------------------------------------
# 8. Geolocator & Spatial Map APIs
# -----------------------------------------------------------------------------

def test_map_geojson():
    client.post("/api/v1/reports", json={
        "type": "FIRE", "description": "Chemical spill", "latitude": 40.7128, "longitude": -74.0060, "priority": "HIGH"
    })
    client.post("/api/v1/units", json={
        "type": "FIRE", "call_sign": "FIRE-GEO-1", "latitude": 40.7200, "longitude": -74.0100
    })

    res = client.get("/api/v1/dispatch/map/geojson")
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) >= 2


def test_spatial_nearby_and_nearest_units():
    # Create incident
    report = client.post("/api/v1/reports", json={
        "type": "MEDICAL", "description": "Collapsed runner", "latitude": 40.7128, "longitude": -74.0060, "priority": "HIGH"
    }).json()

    # Create two medical units at different distances
    unit_close = client.post("/api/v1/units", json={
        "type": "MEDICAL", "call_sign": "MED-CLOSE", "latitude": 40.7150, "longitude": -74.0050
    }).json()
    unit_far = client.post("/api/v1/units", json={
        "type": "MEDICAL", "call_sign": "MED-FAR", "latitude": 40.8000, "longitude": -74.1000
    }).json()

    # Test nearest unit search
    res_nearest = client.get("/api/v1/dispatch/map/units/nearest?latitude=40.7128&longitude=-74.0060&unit_type=MEDICAL")
    assert res_nearest.status_code == 200
    nearest_data = res_nearest.json()
    assert nearest_data["unit"]["call_sign"] == "MED-CLOSE"
    assert nearest_data["distance_km"] < 1.0

    # Test nearby incident search
    res_nearby = client.get("/api/v1/dispatch/map/incidents/nearby?latitude=40.7128&longitude=-74.0060&radius_km=5.0")
    assert res_nearby.status_code == 200
    assert len(res_nearby.json()) >= 1
    assert res_nearby.json()[0]["incident"]["id"] == report["id"]

