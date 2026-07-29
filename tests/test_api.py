from fastapi.testclient import TestClient

from voice_agent_eval_lab.api import app


def test_create_and_fetch_run(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_EVAL_REPORT_DIR", str(tmp_path))
    client = TestClient(app)
    created = client.post("/runs", json={"scenario": "basic_booking", "adapter": "cascade"})
    assert created.status_code == 201
    payload = created.json()
    fetched = client.get(f"/runs/{payload['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["evaluation"]["tool_recall"] == 1


def test_missing_run():
    assert TestClient(app).get("/runs/unknown").status_code == 404


def test_create_and_fetch_compare(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_EVAL_REPORT_DIR", str(tmp_path))
    client = TestClient(app)
    created = client.post(
        "/compare",
        json={"scenario": "basic_booking", "adapters": ["cascade", "realtime"]},
    )
    assert created.status_code == 201
    payload = created.json()
    assert [run["adapter"] for run in payload["runs"]] == ["cascade", "realtime"]
    fetched = client.get(f"/compare/{payload['id']}")
    assert fetched.status_code == 200


def test_missing_compare():
    assert TestClient(app).get("/compare/unknown").status_code == 404


def test_list_scenarios():
    response = TestClient(app).get("/scenarios")
    assert response.status_code == 200
    assert "basic_booking" in response.json()
