import json
from unittest.mock import patch, Mock

import pytest

from explorer_backend import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def make_rpc_mock(payload: dict, status: int = 200):
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status.side_effect = None if status < 400 else Exception("rpc error")
    return resp


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = json.loads(resp.data.decode())
    assert body["status"] in ("ok", "healthy", "degraded")


@patch("requests.get")
def test_blocks_endpoint(mock_get, client):
    mock_get.return_value = make_rpc_mock({"result": {"block_metas": []}})
    resp = client.get("/api/blocks")
    assert resp.status_code == 200
    data = json.loads(resp.data.decode())
    assert "blocks" in data


@patch("requests.get")
def test_validators_endpoint(mock_get, client):
    mock_get.return_value = make_rpc_mock({"result": {"validators": []}})
    resp = client.get("/api/validators")
    assert resp.status_code == 200
    data = json.loads(resp.data.decode())
    assert "validators" in data


@patch("requests.get")
def test_search_endpoint(mock_get, client):
    mock_get.return_value = make_rpc_mock({"result": {"block": {"header": {"height": "1"}, "data": {"txs": []}}}})
    resp = client.get("/api/search?q=1")
    assert resp.status_code == 200
    data = json.loads(resp.data.decode())
    assert "results" in data


@patch("requests.get")
def test_account_not_found_graceful(mock_get, client):
    mock_get.return_value = make_rpc_mock({}, status=404)
    resp = client.get("/api/account/aura1doesnotexist")
    assert resp.status_code in (200, 404)


@patch("requests.get")
def test_transaction_endpoint(mock_get, client):
    mock_get.return_value = make_rpc_mock({"result": {"tx": {"hash": "ABC"}, "tx_result": {"code": 0}}})
    resp = client.get("/api/transactions/ABC")
    assert resp.status_code == 200


@patch("requests.get")
def test_governance_proposals(mock_get, client):
    mock_get.return_value = make_rpc_mock({"result": {"proposals": []}})
    resp = client.get("/api/governance/proposals")
    assert resp.status_code == 200
    data = json.loads(resp.data.decode())
    assert "proposals" in data


@patch("requests.get")
def test_staking_delegations(mock_get, client):
    mock_get.return_value = make_rpc_mock({"result": {"delegation_responses": []}})
    resp = client.get("/api/staking/delegations/aura1delegator")
    assert resp.status_code == 200


@patch("requests.get")
def test_supply_endpoint(mock_get, client):
    coin_data = bytes([0x0A, 0x05]) + b"uaura" + bytes([0x12, 0x07]) + b"1000000"
    raw = bytes([0x0A, len(coin_data)]) + coin_data
    value_b64 = __import__("base64").b64encode(raw).decode()
    mock_get.return_value = make_rpc_mock({
        "result": {
            "response": {
                "code": 0,
                "value": value_b64
            }
        }
    })
    resp = client.get("/api/supply")
    assert resp.status_code == 200
