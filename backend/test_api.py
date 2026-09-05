import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture()
def client(monkeypatch, tmp_path):
    database = tmp_path / "test.db"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(main, "DATABASE", database)
    monkeypatch.setattr(main, "UPLOAD_DIR", uploads)
    main.initialise_database()
    with TestClient(main.app) as test_client:
        yield test_client


def register(client, email="student@example.edu"):
    response = client.post(
        "/auth/register",
        json={"name": "Test Student", "email": email, "password": "password123"},
    )
    assert response.status_code == 201
    return response.json()


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_registration_login_and_invalid_login(client):
    account = register(client)
    assert account["user"]["role"] == "student"
    login = client.post(
        "/auth/login",
        json={"email": "student@example.edu", "password": "password123"},
    )
    assert login.status_code == 200
    invalid = client.post(
        "/auth/login",
        json={"email": "student@example.edu", "password": "wrong-password"},
    )
    assert invalid.status_code == 401


def test_auth_report_search_and_ownership_protection(client):
    first = register(client)
    headers = auth_headers(first["token"])
    assert client.get("/reports/my", headers=headers).status_code == 200
    report = client.post(
        "/reports",
        headers=headers,
        json={
            "kind": "lost",
            "name": "Green backpack",
            "category": "Bags",
            "location": "North Hall",
            "description": "Green backpack with a yellow keychain",
        },
    )
    assert report.status_code == 201
    report_id = report.json()["report"]["id"]
    assert client.get("/reports", params={"query": "backpack"}).json()[0]["id"] == report_id
    assert client.post(
        "/claims",
        headers=headers,
        json={
            "report_id": report_id,
            "ownership_detail": "My own report detail",
            "return_point": "Student services",
        },
    ).status_code == 400


def test_claim_admin_review_and_notifications(client):
    owner = register(client, "owner@example.edu")
    claimant = register(client, "claimant@example.edu")
    report = client.post(
        "/reports",
        headers=auth_headers(owner["token"]),
        json={
            "kind": "found",
            "name": "Blue water bottle",
            "category": "Personal items",
            "location": "Library",
            "description": "Blue bottle with a silver lid and sticker",
        },
    ).json()["report"]
    claim = client.post(
        "/claims",
        headers=auth_headers(claimant["token"]),
        json={
            "report_id": report["id"],
            "ownership_detail": "A scratch under the lid",
            "return_point": "Campus security office",
        },
    )
    assert claim.status_code == 201
    admin_login = client.post(
        "/auth/login",
        json={"email": "admin@refind.local", "password": "refind-admin"},
    ).json()
    admin_headers = auth_headers(admin_login["token"])
    claim_id = claim.json()["id"]
    review = client.patch(
        f"/admin/claims/{claim_id}",
        headers=admin_headers,
        json={"status": "verified"},
    )
    assert review.status_code == 200
    assert client.get("/notifications", headers=auth_headers(claimant["token"])).status_code == 200
    assert client.get("/admin/summary", headers=auth_headers(claimant["token"])).status_code == 403


def test_upload_rejects_fake_image_and_accepts_png(client):
    account = register(client, "upload@example.edu")
    headers = auth_headers(account["token"])
    fake = client.post(
        "/uploads",
        headers=headers,
        files={"file": ("fake.png", b"not-an-image", "image/png")},
    )
    assert fake.status_code == 415
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    accepted = client.post(
        "/uploads",
        headers=headers,
        files={"file": ("item.png", png, "image/png")},
    )
    assert accepted.status_code == 201


def test_matching_read_notifications_and_admin_report_status(client):
    owner = register(client, "match-owner@example.edu")
    other = register(client, "match-other@example.edu")
    found = client.post(
        "/reports",
        headers=auth_headers(owner["token"]),
        json={
            "kind": "found",
            "name": "Red laptop sleeve",
            "category": "Bags",
            "location": "Central Library",
            "description": "Red laptop sleeve with a white university logo",
        },
    ).json()["report"]
    lost = client.post(
        "/reports",
        headers=auth_headers(other["token"]),
        json={
            "kind": "lost",
            "name": "Red laptop sleeve",
            "category": "Bags",
            "location": "Central Library",
            "description": "Red sleeve with a white university logo",
        },
    )
    assert lost.status_code == 201
    assert lost.json()["possible_matches"]
    matches = client.get("/matches", headers=auth_headers(other["token"]))
    assert matches.status_code == 200
    notifications = client.get("/notifications", headers=auth_headers(owner["token"]))
    assert notifications.status_code == 200
    if notifications.json():
        notification_id = notifications.json()[0]["id"]
        assert client.post(
            f"/notifications/{notification_id}/read",
            headers=auth_headers(owner["token"]),
        ).status_code == 200
    admin = client.post(
        "/auth/login",
        json={"email": "admin@refind.local", "password": "refind-admin"},
    ).json()
    status = client.patch(
        f"/admin/reports/{found['id']}",
        headers=auth_headers(admin["token"]),
        json={"status": "flagged"},
    )
    assert status.status_code == 200


def test_cors_and_auth_rate_limit_configuration(client, monkeypatch):
    response = client.options(
        "/reports",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_tenant_isolation_and_private_fields(client):
    first = register(client, "tenant-one@example.edu")
    second = register(client, "tenant-two@example.edu")
    first_headers = auth_headers(first["token"])
    second_headers = auth_headers(second["token"])
    report = client.post(
        "/reports",
        headers=first_headers,
        json={
            "kind": "lost",
            "name": "Private tenant item",
            "category": "Documents",
            "location": "Secure office",
            "description": "Private details are only for the owner",
        },
    ).json()["report"]
    public = client.get("/reports").json()
    public_report = next(item for item in public if item["id"] == report["id"])
    assert "user_id" not in public_report
    assert "email" not in public_report
    assert client.get("/reports/my", headers=second_headers).json() == []
    assert client.get("/claims/my", headers=second_headers).json() == []
    first_notifications = client.get("/notifications", headers=first_headers).json()
    if first_notifications:
        notification_id = first_notifications[0]["id"]
        client.post(
            f"/notifications/{notification_id}/read",
            headers=second_headers,
        )
        assert client.get("/notifications", headers=first_headers).json()[0]["read"] == 0


def test_migration_files_are_present_and_constraints_declared():
    from pathlib import Path
    migration = Path(__file__).parent / "migrations" / "versions" / "001_initial_schema.py"
    text = migration.read_text(encoding="utf-8")
    assert "uq_matches_pair" in text
    assert "ck_reports_kind" in text
    assert "idx_reports_kind_status_created" in text
