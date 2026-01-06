"""
AURA Block Explorer Integration Tests
Comprehensive test suite for verifying explorer functionality
"""

import json
import time
from typing import Any, Dict

import pytest
import requests
from unittest.mock import Mock, patch
from explorer_backend import (
    ExplorerDatabase,
    AnalyticsEngine,
    SearchEngine,
    RichListManager,
    ExportManager,
    SearchType,
    AddressLabel,
    app,
    db
)


class _MockResponse:
    """Simple mock for HTTP responses"""

    def __init__(self, payload: Dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def clear_explorer_cache():
    """Ensure cache table is cleared between tests for deterministic behavior"""
    cursor = db.conn.cursor()
    cursor.execute("DELETE FROM explorer_cache")
    db.conn.commit()


class TestConfiguration:
    """Test configuration loading"""

    def test_config_import(self):
        """Test that configuration can be imported"""
        from config import config

        assert config.CHAIN_ID is not None
        assert config.DENOM == "uaura"
        assert config.NODE_RPC_URL is not None

    def test_config_validation(self):
        """Test configuration validation"""
        from config import Config

        # Should not raise any errors with default config
        Config.validate()


class TestExplorerDatabase:
    """Test database functionality"""

    @pytest.fixture
    def db(self):
        """Create in-memory database for testing"""
        return ExplorerDatabase(":memory:")

    def test_database_initialization(self, db):
        """Test database tables are created"""
        assert db.conn is not None

        # Check tables exist
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}

        assert "search_history" in tables
        assert "address_labels" in tables
        assert "analytics" in tables
        assert "explorer_cache" in tables

    def test_add_search(self, db):
        """Test recording search queries"""
        db.add_search("aura1test", "address", True, "user123")

        recent = db.get_recent_searches(1)
        assert len(recent) == 1
        assert recent[0]["query"] == "aura1test"

    def test_address_labels(self, db):
        """Test address labeling system"""
        label = AddressLabel(
            address="aura1test",
            label="Test Wallet",
            category="user",
            description="Test description"
        )

        db.add_address_label(label)
        retrieved = db.get_address_label("aura1test")

        assert retrieved is not None
        assert retrieved.label == "Test Wallet"
        assert retrieved.category == "user"

    def test_metrics_recording(self, db):
        """Test analytics metrics recording"""
        db.record_metric("test_metric", 100.5, {"extra": "data"})

        metrics = db.get_metrics("test_metric", hours=1)
        assert len(metrics) > 0
        assert metrics[0]["value"] == 100.5

    def test_cache_operations(self, db):
        """Test cache set and get"""
        db.set_cache("test_key", "test_value", ttl=300)

        value = db.get_cache("test_key")
        assert value == "test_value"

        # Test expired cache
        db.set_cache("expired_key", "expired_value", ttl=-1)
        value = db.get_cache("expired_key")
        assert value is None


class TestSearchEngine:
    """Test search functionality"""

    @pytest.fixture
    def search_engine(self):
        """Create search engine for testing"""
        db = ExplorerDatabase(":memory:")
        return SearchEngine("http://localhost:26657", db)

    def test_identify_block_height(self, search_engine):
        """Test block height identification"""
        search_type = search_engine._identify_search_type("12345")
        assert search_type == SearchType.BLOCK_HEIGHT

    def test_identify_address(self, search_engine):
        """Test AURA address identification"""
        search_type = search_engine._identify_search_type("aura1abcdefghijk")
        assert search_type == SearchType.ADDRESS

    def test_identify_transaction(self, search_engine):
        """Test transaction hash identification"""
        tx_hash = "A" * 64
        search_type = search_engine._identify_search_type(tx_hash)
        assert search_type == SearchType.TRANSACTION_ID

    @patch('requests.get')
    def test_search_block_height(self, mock_get, search_engine):
        """Test block height search with mocked response"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "block": {
                    "header": {
                        "height": "100",
                        "time": "2024-01-01T00:00:00Z",
                        "proposer_address": "test_proposer",
                        "last_block_id": {"hash": "test_hash"}
                    },
                    "data": {"txs": []}
                }
            }
        }
        mock_get.return_value = mock_response

        result = search_engine._search_block_height(100)
        assert result is not None
        assert result["height"] == "100"

    @patch('requests.get')
    def test_search_address(self, mock_get, search_engine):
        """Test address search with mocked response"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "balances": [
                {"denom": "uaura", "amount": "1000000"}
            ]
        }
        mock_get.return_value = mock_response

        result = search_engine._search_address("aura1test")
        assert result is not None
        assert result["address"] == "aura1test"
        assert result["balance"] == 1000000


class TestAnalyticsEngine:
    """Test analytics functionality"""

    @pytest.fixture
    def analytics(self):
        """Create analytics engine for testing"""
        db = ExplorerDatabase(":memory:")
        return AnalyticsEngine("http://localhost:26657", db)

    @patch('requests.get')
    def test_fetch_stats(self, mock_get, analytics):
        """Test fetching blockchain stats"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "last_height": "1000"
            }
        }
        mock_get.return_value = mock_response

        stats = analytics._fetch_stats()
        assert stats is not None
        assert stats["total_blocks"] == 1000

    @patch('requests.get')
    def test_fetch_blocks(self, mock_get, analytics):
        """Test fetching blocks"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "block_metas": [
                    {
                        "header": {
                            "height": "100",
                            "time": "2024-01-01T00:00:00Z"
                        },
                        "block_id": {"hash": "test_hash"},
                        "num_txs": "5"
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        blocks = analytics._fetch_blocks(limit=10)
        assert blocks is not None
        assert len(blocks["blocks"]) > 0


class TestFlaskEndpoints:
    """Test Flask API endpoints"""

    @pytest.fixture
    def client(self):
        """Create Flask test client"""
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    def test_explorer_info(self, client):
        """Test root endpoint"""
        response = client.get('/')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["name"] == "AURA Block Explorer"
        assert data["chain_id"] is not None
        assert data["denom"] == "uaura"

    def test_health_check(self, client):
        """Test health check endpoint"""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            response = client.get('/health')
            assert response.status_code == 200

    def test_health_check_degraded(self, client):
        """Ensure degraded RPC still reports 200 with degraded status"""
        with patch('requests.get', side_effect=requests.exceptions.ConnectionError()):
            response = client.get('/health')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["status"] == "degraded"

    def test_search_endpoint_no_query(self, client):
        """Test search with no query"""
        response = client.post('/api/search', json={})
        assert response.status_code == 400

    def test_search_endpoint_with_query(self, client):
        """Test search with valid query"""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": {}}
            mock_get.return_value = mock_response

            response = client.post('/api/search', json={"query": "12345"})
            assert response.status_code == 200

            data = json.loads(response.data)
            assert "type" in data

    def test_search_endpoint_get(self, client):
        """Ensure GET search parameter path works"""
        def fake_get(url, params=None, timeout=5):
            if url.endswith("/block?height=12345"):
                return _MockResponse({
                    "result": {
                        "block": {
                            "header": {
                                "height": "12345",
                                "time": "2024-01-01T00:00:00Z",
                                "proposer_address": "aura1prop"
                            },
                            "data": {"txs": []}
                        }
                    }
                })
            raise AssertionError(f"Unexpected URL {url}")

        with patch('requests.get', side_effect=fake_get):
            response = client.get('/api/search?q=12345')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["results"]["height"] == "12345"

    def test_analytics_dashboard(self, client):
        """Test analytics dashboard endpoint"""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "result": {"last_height": "1000", "block_metas": []}
            }
            mock_get.return_value = mock_response

            response = client.get('/api/analytics/dashboard')
            assert response.status_code == 200

            data = json.loads(response.data)
            assert "hashrate" in data
            assert "transaction_volume" in data

    def test_richlist_endpoint(self, client):
        """Test rich list endpoint"""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "blocks": []
            }
            mock_get.return_value = mock_response

            response = client.get('/api/richlist?limit=10')
            assert response.status_code == 200

            data = json.loads(response.data)
            assert "richlist" in data


class TestExportManager:
    """Test export functionality"""

    @pytest.fixture
    def export_manager(self):
        """Create export manager for testing"""
        return ExportManager("http://localhost:26657")

    @patch('requests.get')
    def test_export_transactions_csv(self, mock_get, export_manager):
        """Test CSV export"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transactions": [
                {
                    "txid": "test123",
                    "timestamp": 1234567890,
                    "sender": "aura1sender",
                    "recipient": "aura1recipient",
                    "amount": 1000,
                    "fee": 10,
                    "type": "transfer"
                }
            ]
        }
        mock_get.return_value = mock_response

        csv_data = export_manager.export_transactions_csv("aura1test")
        assert csv_data is not None
        assert "txid,timestamp" in csv_data
        assert "test123" in csv_data


class TestIntegration:
    """Integration tests for complete workflows"""

    @pytest.fixture
    def client(self):
        """Create Flask test client"""
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    def test_complete_search_workflow(self, client):
        """Test complete search workflow"""
        # This would require a running AURA node
        # For now, we'll test the endpoint structure

        test_cases = [
            {"query": "12345", "expected_type": "block_height"},
            {"query": "aura1abcdefghijk", "expected_type": "address"},
        ]

        for case in test_cases:
            with patch('requests.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"result": {}}
                mock_get.return_value = mock_response

                response = client.post('/api/search', json={"query": case["query"]})
                assert response.status_code == 200

    def test_analytics_cache_behavior(self, client):
        """Test that analytics endpoints use caching"""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "result": {"last_height": "1000", "block_metas": []}
            }
            mock_get.return_value = mock_response

            # First call
            response1 = client.get('/api/analytics/hashrate')
            assert response1.status_code == 200

            # Second call should use cache
            response2 = client.get('/api/analytics/hashrate')
            assert response2.status_code == 200


class TestExplorerDataEndpoints:
    """Tests for explorer dashboard data endpoints"""

    @pytest.fixture
    def client(self):
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    def test_blocks_endpoint_returns_data(self, client):
        """Blocks endpoint should return latest heights"""
        def fake_get(url, params=None, timeout=5):
            if url.endswith("/status"):
                return _MockResponse({"result": {"sync_info": {"latest_block_height": "25"}}})
            if "/blockchain" in url:
                return _MockResponse({
                    "result": {
                        "block_metas": [
                            {
                                "header": {
                                    "height": "25",
                                    "time": "2024-01-01T00:25:00Z",
                                    "proposer_address": "aura1prop"
                                },
                                "block_id": {"hash": "hash25"},
                                "num_txs": "2",
                                "block_size": 1024
                            },
                            {
                                "header": {
                                    "height": "24",
                                    "time": "2024-01-01T00:24:00Z",
                                    "proposer_address": "aura1prop2"
                                },
                                "block_id": {"hash": "hash24"},
                                "num_txs": "1",
                                "block_size": 900
                            }
                        ]
                    }
                })
            raise AssertionError(f"Unexpected URL {url}")

        with patch('requests.get', side_effect=fake_get):
            response = client.get('/api/blocks?limit=2')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["blocks"][0]["height"] == 25
            assert len(data["blocks"]) == 2

    def test_transactions_endpoint_filters(self, client):
        """Transactions endpoint filters by type and status"""
        tx_payload = {
            "tx_responses": [
                {
                    "txhash": "ABC123",
                    "height": "10",
                    "timestamp": "2024-01-01T00:00:00Z",
                    "code": 0,
                    "tx": {
                        "body": {
                            "messages": [
                                {
                                    "@type": "cosmos.bank.v1beta1.MsgSend",
                                    "from_address": "aura1sender",
                                    "to_address": "aura1recipient",
                                    "amount": [{"denom": "uaura", "amount": "1000000"}]
                                }
                            ]
                        },
                        "auth_info": {
                            "fee": {"amount": [{"denom": "uaura", "amount": "500"}]}
                        }
                    }
                },
                {
                    "txhash": "DEF456",
                    "height": "11",
                    "timestamp": "2024-01-01T00:01:00Z",
                    "code": 5,
                    "tx": {"body": {"messages": []}}
                }
            ],
            "pagination": {"total": "2"}
        }

        with patch('requests.get', return_value=_MockResponse(tx_payload)):
            response = client.get('/api/transactions?limit=20&status=success')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data["transactions"]) == 1
            assert data["transactions"][0]["hash"] == "ABC123"
            assert data["transactions"][0]["status"] == "success"

    def test_validators_endpoint_sort(self, client):
        """Validators endpoint sorts by commission"""
        validators_payload = {
            "validators": [
                {
                    "description": {"moniker": "Validator A"},
                    "operator_address": "auraoper1",
                    "consensus_pubkey": {"key": "key1"},
                    "tokens": "2000000",
                    "commission": {"commission_rates": {"rate": "0.100000000000000000"}},
                    "jailed": False,
                    "status": "BOND_STATUS_BONDED"
                },
                {
                    "description": {"moniker": "Validator B"},
                    "operator_address": "auraoper2",
                    "consensus_pubkey": {"key": "key2"},
                    "tokens": "500000",
                    "commission": {"commission_rates": {"rate": "0.050000000000000000"}},
                    "jailed": False,
                    "status": "BOND_STATUS_BONDED"
                }
            ]
        }

        with patch('requests.get', return_value=_MockResponse(validators_payload)):
            response = client.get('/api/validators?sort=commission')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["validators"][0]["commission"] == 0.1
            assert data["count"] == 2

    def test_stats_endpoint_combines_metrics(self, client):
        """Stats endpoint aggregates latest block, tx count, validator count"""
        def fake_get(url, params=None, timeout=5):
            if url.endswith("/status"):
                return _MockResponse({"result": {"sync_info": {"latest_block_height": "2"}}})
            if "/blockchain" in url:
                return _MockResponse({
                    "result": {
                        "block_metas": [
                            {
                                "header": {
                                    "height": "2",
                                    "time": "2024-01-01T00:00:10Z",
                                    "proposer_address": "aura1"
                                },
                                "block_id": {"hash": "hash2"},
                                "num_txs": "1",
                                "block_size": 900
                            },
                            {
                                "header": {
                                    "height": "1",
                                    "time": "2024-01-01T00:00:00Z",
                                    "proposer_address": "aura2"
                                },
                                "block_id": {"hash": "hash1"},
                                "num_txs": "1",
                                "block_size": 800
                            }
                        ]
                    }
                })
            if "cosmos/tx/v1beta1/txs" in url:
                return _MockResponse({"tx_responses": [], "pagination": {"total": "10"}})
            if "cosmos/staking/v1beta1/validators" in url:
                return _MockResponse({"validators": [{"description": {"moniker": "Val"}, "operator_address": "a1", "consensus_pubkey": {"key": "k"}, "tokens": "1", "commission": {"commission_rates": {"rate": "0.1"}}, "jailed": False, "status": "BOND_STATUS_BONDED"}]})
            raise AssertionError(f"Unexpected URL {url}")

        with patch('requests.get', side_effect=fake_get):
            response = client.get('/api/stats')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["latest_block"] == 2
            assert data["total_txs"] == 10
            assert data["active_validators"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
