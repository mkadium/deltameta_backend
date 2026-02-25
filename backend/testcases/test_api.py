from fastapi.testclient import TestClient
import pytest

from app.main import app

client = TestClient(app)


def test_root_status():
    resp = client.get("/")
    assert resp.status_code == 200


def test_root_body():
    resp = client.get("/")
    assert resp.json() == {"message": "Hello, Deltameta!"}


def test_404_on_unknown_path():
    resp = client.get("/this-route-does-not-exist")
    assert resp.status_code == 404


def test_content_type_json():
    resp = client.get("/")
    assert "application/json" in resp.headers.get("content-type", "")

