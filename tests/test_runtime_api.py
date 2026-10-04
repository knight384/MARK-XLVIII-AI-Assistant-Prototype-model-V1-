import pytest
from fastapi.testclient import TestClient
from core.runtime.api import app, set_runtime
from core.runtime.app import MarkRuntime
from core.runtime.mode import RuntimeMode

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_runtime():
    runtime = MarkRuntime(mode=RuntimeMode.HEADLESS)
    set_runtime(runtime)
    yield
    set_runtime(None)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mode"] == "HEADLESS"

def test_identity_endpoint():
    response = client.get("/identity")
    assert response.status_code == 200
    assert "identity" in response.json()

def test_capabilities_endpoint():
    response = client.get("/capabilities")
    assert response.status_code == 200
    assert "capabilities" in response.json()
    assert len(response.json()["capabilities"]) > 0

def test_models_endpoint():
    response = client.get("/models")
    assert response.status_code == 200
    assert "providers" in response.json()

def test_task_submission_and_status():
    response = client.post("/tasks", json={"goal": "say hello"})
    assert response.status_code == 200
    task_id = response.json()["task_id"]
    
    status_resp = client.get(f"/tasks/{task_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] in ["CREATED", "PLANNING", "QUEUED", "RUNNING", "FAILED"]

def test_task_cancellation():
    response = client.post("/tasks", json={"goal": "sleep for 10 seconds"})
    assert response.status_code == 200
    task_id = response.json()["task_id"]
    
    cancel_resp = client.post(f"/tasks/{task_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelling"
