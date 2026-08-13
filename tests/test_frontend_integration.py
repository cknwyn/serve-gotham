import pytest
from tests.test_api import client, Base, test_engine


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


def test_serve_frontend_html_pages():
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "GCPD Beacon" in res_index.text

    res_citizen = client.get("/citizen")
    assert res_citizen.status_code == 200
    assert "GCPD Beacon" in res_citizen.text

    res_dispatcher = client.get("/dispatcher")
    assert res_dispatcher.status_code == 200
    assert "GOTHAM DISPATCH" in res_dispatcher.text


def test_api_dispatch_citizen_payload_contract():
    payload = {
        "id": "e3b8a1c9-7d84-47b2-9d33-9118c4e402a1",
        "type": "Police",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "timestamp": "2026-08-13T10:50:00Z",
        "status": "Pending"
    }
    response = client.post("/api/dispatch", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "e3b8a1c9-7d84-47b2-9d33-9118c4e402a1"
    assert data["type"] == "POLICE"
    assert data["latitude"] == 40.7128
    assert data["longitude"] == -74.0060
    assert data["status"] == "REPORTED"
    assert "timestamp" in data


def test_api_dispatch_dispatcher_grid_and_update():
    # Submit 2 citizen beacon reports
    p1 = {"type": "Fire", "latitude": 40.7128, "longitude": -74.0060}
    p2 = {"type": "Medical", "latitude": 40.7306, "longitude": -73.9352}
    r1 = client.post("/api/dispatch", json=p1).json()
    r2 = client.post("/api/dispatch", json=p2).json()

    # GET /api/dispatch
    res = client.get("/api/dispatch")
    assert res.status_code == 200
    incidents = res.json()
    assert len(incidents) == 2
    assert incidents[0]["timestamp"] is not None

    # PUT /api/dispatch/{id}/status -> "Dispatched"
    res_put = client.put(f"/api/dispatch/{r1['id']}/status", json={"status": "Dispatched"})
    assert res_put.status_code == 200
    assert res_put.json()["status"] == "DISPATCHED"
