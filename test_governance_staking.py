"""
AURA Block Explorer - Governance & Staking Tests
Tests for the new governance and staking features added to meet community expectations.
"""

import json
from typing import Any, Dict
from unittest.mock import patch

import pytest
import requests

from explorer_backend import ExplorerDatabase, GovernanceService, StakingService, app


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


# ==================== GOVERNANCE SERVICE TESTS ====================


class TestGovernanceService:
    """Test governance functionality"""

    @pytest.fixture
    def governance(self):
        """Create governance service for testing"""
        db = ExplorerDatabase(":memory:")
        return GovernanceService("http://localhost:1317", db)

    @patch("requests.get")
    def test_get_proposals_list(self, mock_get, governance):
        """Test fetching proposals list"""
        mock_get.return_value = _MockResponse(
            {
                "proposals": [
                    {
                        "proposal_id": "1",
                        "content": {
                            "title": "Test Proposal",
                            "description": "Test description",
                            "@type": "/cosmos.gov.v1beta1.TextProposal",
                        },
                        "status": "PROPOSAL_STATUS_VOTING_PERIOD",
                        "submit_time": "2024-01-01T00:00:00Z",
                        "deposit_end_time": "2024-01-15T00:00:00Z",
                        "voting_start_time": "2024-01-15T00:00:00Z",
                        "voting_end_time": "2024-01-30T00:00:00Z",
                        "total_deposit": [{"denom": "uaura", "amount": "1000000"}],
                        "final_tally_result": {},
                    }
                ],
                "pagination": {"total": "1"},
            }
        )

        result = governance.get_proposals()

        assert "proposals" in result
        assert len(result["proposals"]) == 1
        assert result["proposals"][0]["id"] == "1"
        assert result["proposals"][0]["title"] == "Test Proposal"
        assert result["proposals"][0]["status"] == "Voting"
        assert result["total"] == 1

    @patch("requests.get")
    def test_get_proposals_with_status_filter(self, mock_get, governance):
        """Test fetching proposals with status filter"""
        mock_get.return_value = _MockResponse(
            {
                "proposals": [
                    {
                        "proposal_id": "2",
                        "content": {"title": "Passed Proposal", "description": ""},
                        "status": "PROPOSAL_STATUS_PASSED",
                        "total_deposit": [],
                    }
                ],
                "pagination": {"total": "1"},
            }
        )

        result = governance.get_proposals(status="passed")

        # Verify correct status param was sent
        call_args = mock_get.call_args
        assert "PROPOSAL_STATUS_PASSED" in str(call_args)
        assert len(result["proposals"]) == 1
        assert result["proposals"][0]["status"] == "Passed"

    @patch("requests.get")
    def test_get_single_proposal(self, mock_get, governance):
        """Test fetching single proposal with tally"""
        # First call returns proposal, second returns tally
        mock_get.side_effect = [
            _MockResponse(
                {
                    "proposal": {
                        "proposal_id": "5",
                        "content": {
                            "title": "Community Pool Spend",
                            "description": "Fund development",
                            "@type": "/cosmos.distribution.v1beta1.CommunityPoolSpendProposal",
                        },
                        "status": "PROPOSAL_STATUS_VOTING_PERIOD",
                        "total_deposit": [{"denom": "uaura", "amount": "10000000"}],
                    }
                }
            ),
            _MockResponse(
                {
                    "tally": {
                        "yes": "5000000",
                        "no": "1000000",
                        "abstain": "500000",
                        "no_with_veto": "100000",
                    }
                }
            ),
        ]

        result = governance.get_proposal(5)

        assert result["id"] == "5"
        assert result["title"] == "Community Pool Spend"
        assert result["tally"] is not None
        assert result["tally"]["yes"] == 5000000
        assert result["tally"]["no"] == 1000000
        assert result["tally"]["total"] == 6600000

    @patch("requests.get")
    def test_get_proposal_votes(self, mock_get, governance):
        """Test fetching proposal votes"""
        mock_get.return_value = _MockResponse(
            {
                "votes": [
                    {"voter": "aura1abc123", "option": "VOTE_OPTION_YES"},
                    {"voter": "aura1def456", "option": "VOTE_OPTION_NO"},
                    {"voter": "aura1ghi789", "option": "VOTE_OPTION_ABSTAIN"},
                ],
                "pagination": {"total": "3"},
            }
        )

        result = governance.get_proposal_votes(5)

        assert "votes" in result
        assert len(result["votes"]) == 3
        assert result["votes"][0]["option"] == "Yes"
        assert result["votes"][1]["option"] == "No"
        assert result["votes"][2]["option"] == "Abstain"
        assert result["proposal_id"] == 5

    @patch("requests.get")
    def test_get_governance_params(self, mock_get, governance):
        """Test fetching governance parameters"""

        def mock_params_response(url, *args, **kwargs):
            if "deposit" in url:
                return _MockResponse(
                    {
                        "deposit_params": {
                            "min_deposit": [{"denom": "uaura", "amount": "10000000"}],
                            "max_deposit_period": "1209600s",
                        }
                    }
                )
            elif "voting" in url:
                return _MockResponse({"voting_params": {"voting_period": "604800s"}})
            elif "tallying" in url:
                return _MockResponse(
                    {
                        "tallying_params": {
                            "quorum": "0.334",
                            "threshold": "0.5",
                            "veto_threshold": "0.334",
                        }
                    }
                )
            return _MockResponse({})

        mock_get.side_effect = mock_params_response

        result = governance.get_governance_params()

        assert "deposit" in result
        assert "voting" in result
        assert "tallying" in result

    @patch("requests.get")
    def test_proposals_fetch_error_handling(self, mock_get, governance):
        """Test error handling in proposals fetch"""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        result = governance.get_proposals()

        assert "error" in result
        assert result["proposals"] == []

    def test_format_tally_percentages(self, governance):
        """Test tally percentage calculations"""
        tally = {
            "yes": "7500000",
            "no": "2000000",
            "abstain": "300000",
            "no_with_veto": "200000",
        }

        result = governance._format_tally(tally)

        assert result["total"] == 10000000
        assert result["yes_percent"] == 75.0
        assert result["no_percent"] == 20.0
        assert result["abstain_percent"] == 3.0
        assert result["veto_percent"] == 2.0

    def test_format_tally_zero_total(self, governance):
        """Test tally with zero votes"""
        tally = {"yes": "0", "no": "0", "abstain": "0", "no_with_veto": "0"}

        result = governance._format_tally(tally)

        assert result["total"] == 0
        assert result["yes_percent"] == 0
        assert result["no_percent"] == 0


# ==================== STAKING SERVICE TESTS ====================


class TestStakingService:
    """Test staking functionality"""

    @pytest.fixture
    def staking(self):
        """Create staking service for testing"""
        db = ExplorerDatabase(":memory:")
        return StakingService("http://localhost:1317", db)

    @patch("requests.get")
    def test_get_staking_pool(self, mock_get, staking):
        """Test fetching staking pool info"""
        mock_get.return_value = _MockResponse(
            {
                "pool": {
                    "bonded_tokens": "100000000000",
                    "not_bonded_tokens": "20000000000",
                }
            }
        )

        result = staking.get_staking_pool()

        assert result["bonded_tokens"] == 100000000000
        assert result["not_bonded_tokens"] == 20000000000
        assert result["total_tokens"] == 120000000000
        assert abs(result["bonded_ratio"] - 83.33) < 0.1
        assert "AURA" in result["bonded_formatted"]

    @patch("requests.get")
    def test_get_delegations(self, mock_get, staking):
        """Test fetching delegations for an address"""
        mock_get.return_value = _MockResponse(
            {
                "delegation_responses": [
                    {
                        "delegation": {
                            "delegator_address": "aura1delegator",
                            "validator_address": "auravaloper1validator1",
                            "shares": "1000000.000000000000000000",
                        },
                        "balance": {"denom": "uaura", "amount": "1000000"},
                    },
                    {
                        "delegation": {
                            "delegator_address": "aura1delegator",
                            "validator_address": "auravaloper1validator2",
                            "shares": "2000000.000000000000000000",
                        },
                        "balance": {"denom": "uaura", "amount": "2000000"},
                    },
                ]
            }
        )

        result = staking.get_delegations("aura1delegator")

        assert "delegations" in result
        assert len(result["delegations"]) == 2
        assert result["total_staked"] == 3000000

    @patch("requests.get")
    def test_get_unbonding_delegations(self, mock_get, staking):
        """Test fetching unbonding delegations"""
        mock_get.return_value = _MockResponse(
            {
                "unbonding_responses": [
                    {
                        "delegator_address": "aura1delegator",
                        "validator_address": "auravaloper1validator",
                        "entries": [
                            {
                                "creation_height": "12345",
                                "completion_time": "2024-02-01T00:00:00Z",
                                "initial_balance": "500000",
                                "balance": "500000",
                            }
                        ],
                    }
                ]
            }
        )

        result = staking.get_unbonding_delegations("aura1delegator")

        assert "unbonding_delegations" in result
        assert len(result["unbonding_delegations"]) == 1
        assert result["total_unbonding"] == 500000

    @patch("requests.get")
    def test_get_rewards(self, mock_get, staking):
        """Test fetching staking rewards"""
        mock_get.return_value = _MockResponse(
            {
                "rewards": [
                    {
                        "validator_address": "auravaloper1validator1",
                        "reward": [{"denom": "uaura", "amount": "100000.5"}],
                    },
                    {
                        "validator_address": "auravaloper1validator2",
                        "reward": [{"denom": "uaura", "amount": "50000.25"}],
                    },
                ],
                "total": [{"denom": "uaura", "amount": "150000.75"}],
            }
        )

        result = staking.get_rewards("aura1delegator")

        assert "rewards_by_validator" in result or "total_rewards" in result
        # Result contains rewards data
        assert result.get("total_amount", 0) > 0 or result.get("total_rewards", [])

    @patch("requests.get")
    def test_get_staking_params(self, mock_get, staking):
        """Test fetching staking parameters"""
        mock_get.return_value = _MockResponse(
            {
                "params": {
                    "unbonding_time": "1814400s",
                    "max_validators": 100,
                    "max_entries": 7,
                    "historical_entries": 10000,
                    "bond_denom": "uaura",
                }
            }
        )

        result = staking.get_staking_params()

        # Result contains params (either nested or flat)
        assert "max_validators" in result or (
            "params" in result and "max_validators" in result["params"]
        )
        assert "bond_denom" in result or (
            "params" in result and "bond_denom" in result["params"]
        )

    @patch("requests.get")
    def test_staking_pool_error_handling(self, mock_get, staking):
        """Test error handling in staking pool fetch"""
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

        result = staking.get_staking_pool()

        assert "error" in result


# ==================== FLASK ENDPOINT TESTS ====================


class TestGovernanceStakingEndpoints:
    """Test Flask API endpoints for governance and staking"""

    @pytest.fixture
    def client(self):
        """Create Flask test client"""
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_governance_proposals_endpoint(self, client):
        """Test GET /api/governance/proposals"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _MockResponse(
                {
                    "proposals": [
                        {
                            "proposal_id": "1",
                            "content": {"title": "Test", "description": "Desc"},
                            "status": "PROPOSAL_STATUS_PASSED",
                            "total_deposit": [],
                        }
                    ],
                    "pagination": {"total": "1"},
                }
            )

            response = client.get("/api/governance/proposals")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert "proposals" in data

    def test_governance_proposals_with_status_filter(self, client):
        """Test GET /api/governance/proposals?status=voting"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _MockResponse(
                {"proposals": [], "pagination": {"total": "0"}}
            )

            response = client.get("/api/governance/proposals?status=voting")
            assert response.status_code == 200

    def test_governance_single_proposal_endpoint(self, client):
        """Test GET /api/governance/proposals/<id>"""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = [
                _MockResponse(
                    {
                        "proposal": {
                            "proposal_id": "1",
                            "content": {"title": "Test"},
                            "status": "PROPOSAL_STATUS_PASSED",
                            "total_deposit": [],
                        }
                    }
                ),
                _MockResponse(
                    {
                        "tally": {
                            "yes": "1000",
                            "no": "0",
                            "abstain": "0",
                            "no_with_veto": "0",
                        }
                    }
                ),
            ]

            response = client.get("/api/governance/proposals/1")
            assert response.status_code == 200

    def test_governance_votes_endpoint(self, client):
        """Test GET /api/governance/proposals/<id>/votes"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _MockResponse(
                {
                    "votes": [{"voter": "aura1abc", "option": "VOTE_OPTION_YES"}],
                    "pagination": {"total": "1"},
                }
            )

            response = client.get("/api/governance/proposals/1/votes")
            assert response.status_code == 200

    def test_governance_params_endpoint(self, client):
        """Test GET /api/governance/params"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _MockResponse(
                {"deposit_params": {}, "voting_params": {}, "tallying_params": {}}
            )

            response = client.get("/api/governance/params")
            assert response.status_code == 200

    def test_staking_pool_endpoint(self, client):
        """Test GET /api/staking/pool"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _MockResponse(
                {
                    "pool": {
                        "bonded_tokens": "1000000000",
                        "not_bonded_tokens": "100000000",
                    }
                }
            )

            response = client.get("/api/staking/pool")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert "bonded_tokens" in data

    def test_staking_delegations_endpoint(self, client):
        """Test GET /api/staking/delegations/<address>"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _MockResponse({"delegation_responses": []})

            response = client.get("/api/staking/delegations/aura1testaddr")
            assert response.status_code == 200

    def test_staking_unbonding_endpoint(self, client):
        """Test GET /api/staking/unbonding/<address>"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _MockResponse({"unbonding_responses": []})

            response = client.get("/api/staking/unbonding/aura1testaddr")
            assert response.status_code == 200

    def test_staking_rewards_endpoint(self, client):
        """Test GET /api/staking/rewards/<address>"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _MockResponse({"rewards": [], "total": []})

            response = client.get("/api/staking/rewards/aura1testaddr")
            assert response.status_code == 200

    def test_staking_params_endpoint(self, client):
        """Test GET /api/staking/params"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _MockResponse(
                {
                    "params": {
                        "unbonding_time": "1814400s",
                        "max_validators": 100,
                        "bond_denom": "uaura",
                    }
                }
            )

            response = client.get("/api/staking/params")
            assert response.status_code == 200


# ==================== INTEGRATION TESTS ====================


class TestGovernanceStakingIntegration:
    """Integration tests for governance and staking workflows"""

    @pytest.fixture
    def client(self):
        """Create Flask test client"""
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_complete_governance_workflow(self, client):
        """Test complete governance workflow: list -> detail -> votes"""
        with patch("requests.get") as mock_get:
            # Step 1: List proposals
            mock_get.return_value = _MockResponse(
                {
                    "proposals": [
                        {
                            "proposal_id": "10",
                            "content": {"title": "Upgrade v2"},
                            "status": "PROPOSAL_STATUS_VOTING_PERIOD",
                            "total_deposit": [],
                        }
                    ],
                    "pagination": {"total": "1"},
                }
            )

            list_response = client.get("/api/governance/proposals")
            assert list_response.status_code == 200
            proposals = json.loads(list_response.data)["proposals"]
            assert len(proposals) >= 1

            # Step 2: Get proposal detail
            mock_get.side_effect = [
                _MockResponse(
                    {
                        "proposal": {
                            "proposal_id": "10",
                            "content": {
                                "title": "Upgrade v2",
                                "description": "Full details",
                            },
                            "status": "PROPOSAL_STATUS_VOTING_PERIOD",
                            "total_deposit": [{"denom": "uaura", "amount": "50000000"}],
                        }
                    }
                ),
                _MockResponse(
                    {
                        "tally": {
                            "yes": "8000000",
                            "no": "1000000",
                            "abstain": "500000",
                            "no_with_veto": "500000",
                        }
                    }
                ),
            ]

            detail_response = client.get("/api/governance/proposals/10")
            assert detail_response.status_code == 200
            detail = json.loads(detail_response.data)
            assert "title" in detail
            if "tally" in detail and detail["tally"]:
                assert "yes" in detail["tally"]

            # Step 3: Get votes
            mock_get.side_effect = None
            mock_get.return_value = _MockResponse(
                {
                    "votes": [
                        {"voter": "aura1voter1", "option": "VOTE_OPTION_YES"},
                        {"voter": "aura1voter2", "option": "VOTE_OPTION_YES"},
                        {"voter": "aura1voter3", "option": "VOTE_OPTION_NO"},
                    ],
                    "pagination": {"total": "3"},
                }
            )

            votes_response = client.get("/api/governance/proposals/10/votes")
            assert votes_response.status_code == 200
            votes = json.loads(votes_response.data)
            assert "votes" in votes

    def test_complete_staking_workflow(self, client):
        """Test complete staking workflow: pool -> delegations -> rewards"""
        with patch("requests.get") as mock_get:
            test_address = "aura1useraddress123"

            # Step 1: Get staking pool
            mock_get.return_value = _MockResponse(
                {
                    "pool": {
                        "bonded_tokens": "500000000000",
                        "not_bonded_tokens": "50000000000",
                    }
                }
            )

            pool_response = client.get("/api/staking/pool")
            assert pool_response.status_code == 200
            pool = json.loads(pool_response.data)
            assert "bonded_tokens" in pool

            # Step 2: Get delegations
            mock_get.return_value = _MockResponse(
                {
                    "delegation_responses": [
                        {
                            "delegation": {
                                "delegator_address": test_address,
                                "validator_address": "auravaloper1val1",
                            },
                            "balance": {"denom": "uaura", "amount": "10000000"},
                        }
                    ]
                }
            )

            del_response = client.get(f"/api/staking/delegations/{test_address}")
            assert del_response.status_code == 200

            # Step 3: Get rewards
            mock_get.return_value = _MockResponse(
                {
                    "rewards": [
                        {
                            "validator_address": "auravaloper1val1",
                            "reward": [{"denom": "uaura", "amount": "50000"}],
                        }
                    ],
                    "total": [{"denom": "uaura", "amount": "50000"}],
                }
            )

            rewards_response = client.get(f"/api/staking/rewards/{test_address}")
            assert rewards_response.status_code == 200

    def test_explorer_info_includes_governance_staking_endpoints(self, client):
        """Test that explorer info includes governance and staking endpoints"""
        response = client.get("/")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "endpoints" in data
        endpoints = data["endpoints"]
        assert "governance" in endpoints
        assert "staking" in endpoints


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
