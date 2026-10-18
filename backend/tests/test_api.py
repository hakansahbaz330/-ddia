import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import main
from app.config import get_settings
from app.db import get_session
from app.schema import Base


@pytest.fixture
def client(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    main.app.dependency_overrides[get_session] = override
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path / "up")
    monkeypatch.setattr(get_settings(), "api_key", "")
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_preview_import_and_summary(client, xlsx):
    with xlsx.open("rb") as f:
        pv = client.post("/api/imports/preview", files={"file": (xlsx.name, f)})
    assert pv.status_code == 200
    sheet = pv.json()["sheets"][0]
    assert sheet["summary"]["unknown"] == ["Weird"] and sheet["mapping"]["B365CH"] == "odds:B365:1X2:1:closing"
    assert client.get("/api/data/summary").json()["matches"] == 0  # önizleme veritabanına yazmaz

    with xlsx.open("rb") as f:
        r = client.post("/api/imports", files={"file": (xlsx.name, f)}, data={"mapping": '{"Weird": "ignore"}'})
    assert r.status_code == 200 and r.json()["matches_imported"] == 3
    s = client.get("/api/data/summary").json()
    assert s["matches"] == 3 and s["seasons"] == {"2023-2024": 3}
    m = client.get("/api/matches", params={"team": "arsen"}).json()
    assert m["total"] == 1 and m["items"][0]["ft"] == [2, 1]
    assert client.get("/api/matches", params={"division": "D1"}).json()["total"] == 1
    assert client.get("/api/imports").json()[0]["matches_imported"] == 3
    assert client.get("/api/imports/999").status_code == 404


def test_errors_are_readable(client, tmp_path):
    r = client.post("/api/imports", files={"file": ("a.pdf", b"x")})
    assert r.status_code == 400 and "Desteklenmeyen" in r.json()["detail"]
    r = client.post("/api/imports", files={"file": ("a-2023-2024.xlsx", b"bozuk")})
    assert r.status_code == 422 and "açılamadı" in r.json()["detail"]
    r = client.post("/api/imports/preview", files={"file": ("a.csv", b"Div,Date\n")}, data={"mapping": "{bozuk"})
    assert r.status_code == 400 and "JSON" in r.json()["detail"]


def test_api_key_required_when_configured(client, xlsx, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "gizli")
    with xlsx.open("rb") as f:
        assert client.post("/api/imports", files={"file": (xlsx.name, f)}).status_code == 401
    with xlsx.open("rb") as f:
        ok = client.post("/api/imports", files={"file": (xlsx.name, f)}, headers={"X-API-Key": "gizli"})
    assert ok.status_code == 200
    assert client.get("/health").status_code == 200  # okuma uçları açık


def test_alias_suggestions(client):
    assert client.get("/api/teams/alias-suggestions").json() == []


def test_similar_endpoint_validation(client):
    r = client.post("/api/similar", json={"odds_1x2": [2.0, 3.4, 0.9]})
    assert r.status_code == 422
    r = client.post("/api/similar", json={"odds_1x2": [2.0, 3.4, 3.8], "scope": "league"})
    assert r.status_code == 409 and "Arşiv boş" in r.json()["detail"]
