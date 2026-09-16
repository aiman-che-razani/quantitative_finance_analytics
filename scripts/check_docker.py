"""End-to-end verification through the containerized dashboard proxy."""

import httpx

base = "http://127.0.0.1:8823"
with httpx.Client(base_url=base, timeout=180) as client:
    assert client.get("/").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"
    dataset = client.get("/api/datasets").json()[0]
    request = {"dataset_id": dataset["id"], "symbols": ["SPY"], "strategy": "ema_trend"}
    denied = client.post(
        "/api/experiments", json=request, headers={"Origin": "https://untrusted.example"}
    )
    assert denied.status_code == 403
    result = client.post("/api/experiments", json=request, headers={"Origin": base})
    result.raise_for_status()
    assert result.json()["provenance"]["code_tree_sha256"]
    identity = client.post("/api/paper", json=request, headers={"Origin": base}).json()["id"]
    first = client.post(
        f"/api/paper/{identity}/advance", json={"as_of": "2025-12-31"}, headers={"Origin": base}
    )
    first.raise_for_status()
    second = client.post(
        f"/api/paper/{identity}/advance", json={"as_of": "2025-12-31"}, headers={"Origin": base}
    )
    assert first.json() == second.json()
    print("Docker proxy, research, source fingerprint, CSRF rejection and paper idempotency passed")
