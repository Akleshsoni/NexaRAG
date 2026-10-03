from httpx import ASGITransport, AsyncClient

from app import main


async def test_health_reports_services(monkeypatch):
    async def ok():
        return None

    monkeypatch.setattr(main, "_check_postgres", ok)
    monkeypatch.setattr(main, "_check_redis", ok)
    monkeypatch.setattr(main, "_check_qdrant", ok)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/health")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert set(body["services"]) == {"api", "postgres", "redis", "qdrant"}


async def test_health_degraded_when_dependency_down(monkeypatch):
    async def ok():
        return None

    async def down():
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "_check_postgres", ok)
    monkeypatch.setattr(main, "_check_redis", down)
    monkeypatch.setattr(main, "_check_qdrant", ok)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        body = (await client.get("/health")).json()
    assert body["status"] == "degraded"
    assert body["services"]["redis"]["status"] == "down"
    assert "boom" not in str(body)  # internal error text is never exposed


async def test_protected_route_without_token_is_401():
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        for path in ("/documents", "/queries", "/stats"):
            assert (await client.get(path)).status_code == 401
