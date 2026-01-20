"""
Advanced Cosmos SDK Client for Aura Blockchain
Provides specialized query methods for all Cosmos SDK modules and Aura custom modules
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from decimal import Decimal

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# ==================== DATA MODELS ====================


@dataclass
class Coin:
    """Token amount with denomination"""

    denom: str
    amount: str

    @property
    def amount_decimal(self) -> Decimal:
        return Decimal(self.amount)


@dataclass
class Validator:
    """Validator information"""

    operator_address: str
    consensus_address: str
    jailed: bool
    status: str
    tokens: str
    delegator_shares: str
    description: Dict[str, str]
    unbonding_height: int
    unbonding_time: str
    commission: Dict[str, str]
    min_self_delegation: str
    voting_power: int = 0
    uptime: float = 0.0


@dataclass
class Delegation:
    """Delegation information"""

    delegator_address: str
    validator_address: str
    shares: str
    balance: Coin


@dataclass
class Proposal:
    """Governance proposal"""

    proposal_id: int
    content: Dict[str, Any]
    status: str
    final_tally_result: Dict[str, str]
    submit_time: str
    deposit_end_time: str
    total_deposit: List[Coin]
    voting_start_time: str
    voting_end_time: str


@dataclass
class Pool:
    """DEX liquidity pool"""

    pool_id: int
    token_a_denom: str
    token_b_denom: str
    token_a_reserve: str
    token_b_reserve: str
    total_shares: str
    swap_fee: str


@dataclass
class DIDDocument:
    """Decentralized Identity Document"""

    did: str
    owner: str
    controller: List[str]
    verification_method: List[Dict[str, Any]]
    authentication: List[str]
    service: List[Dict[str, Any]]


@dataclass
class VerifiableCredential:
    """Verifiable Credential"""

    credential_id: str
    issuer: str
    holder: str
    credential_type: str
    status: str
    issuance_date: str
    expiration_date: Optional[str]
    credential_data: Dict[str, Any]


@dataclass
class BridgeState:
    """Cross-chain bridge state"""

    total_locked: Dict[str, str]
    total_minted: Dict[str, str]
    supported_chains: List[str]
    active_transfers: int


# ==================== COSMOS SDK CLIENT ====================


class CosmosSDKClient:
    """
    Advanced Cosmos SDK query client for Aura blockchain
    Supports all standard modules and Aura custom modules
    """

    def __init__(
        self,
        rpc_url: str,
        api_url: str,
        grpc_url: Optional[str] = None,
        timeout: int = 10,
        retry_count: int = 3,
    ):
        """
        Initialize Cosmos SDK client

        Args:
            rpc_url: Tendermint RPC endpoint (e.g., http://localhost:26657)
            api_url: Cosmos SDK REST API endpoint (e.g., http://localhost:1317)
            grpc_url: gRPC endpoint (e.g., localhost:9090)
            timeout: Request timeout in seconds
            retry_count: Number of retries for failed requests
        """
        self.rpc_url = rpc_url.rstrip("/")
        self.api_url = api_url.rstrip("/")
        self.grpc_url = grpc_url
        self.timeout = timeout

        # Configure session with retry logic
        self.session = requests.Session()
        retry = Retry(
            total=retry_count, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _get(self, url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make GET request with error handling"""
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {url} - {e}")
            raise

    def _rpc_get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Query Tendermint RPC"""
        return self._get(f"{self.rpc_url}/{endpoint}", params)

    def _api_get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Query Cosmos SDK REST API"""
        return self._get(f"{self.api_url}/{endpoint}", params)

    # ==================== TENDERMINT RPC ====================

    def get_status(self) -> Dict[str, Any]:
        """Get node status"""
        return self._rpc_get("status")

    def get_block(self, height: Optional[int] = None) -> Dict[str, Any]:
        """Get block at height (latest if None)"""
        params = {"height": str(height)} if height else None
        return self._rpc_get("block", params)

    def get_block_results(self, height: int) -> Dict[str, Any]:
        """Get block results (events, begin_block, end_block)"""
        return self._rpc_get("block_results", {"height": str(height)})

    def get_blockchain(self, min_height: int, max_height: int) -> Dict[str, Any]:
        """Get block metadata for height range"""
        return self._rpc_get(
            "blockchain", {"minHeight": str(min_height), "maxHeight": str(max_height)}
        )

    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """Get transaction by hash"""
        return self._rpc_get("tx", {"hash": f"0x{tx_hash}"})

    def search_transactions(
        self, query: str, page: int = 1, per_page: int = 30
    ) -> Dict[str, Any]:
        """Search transactions by query"""
        return self._rpc_get(
            "tx_search", {"query": query, "page": str(page), "per_page": str(per_page)}
        )

    def get_validators(self, height: Optional[int] = None) -> Dict[str, Any]:
        """Get validator set at height"""
        params = {"height": str(height)} if height else None
        return self._rpc_get("validators", params)

    # ==================== BANK MODULE ====================

    def get_balance(self, address: str, denom: str) -> Coin:
        """Get balance of single denomination"""
        data = self._api_get(f"cosmos/bank/v1beta1/balances/{address}/{denom}")
        balance = data.get("balance", {})
        return Coin(
            denom=balance.get("denom", denom), amount=balance.get("amount", "0")
        )

    def get_balances(self, address: str) -> List[Coin]:
        """Get all token balances for address"""
        data = self._api_get(f"cosmos/bank/v1beta1/balances/{address}")
        balances = data.get("balances", [])
        return [Coin(denom=b["denom"], amount=b["amount"]) for b in balances]

    def get_supply(self, denom: str) -> Coin:
        """Get total supply of denomination"""
        data = self._api_get(f"cosmos/bank/v1beta1/supply/{denom}")
        supply = data.get("amount", {})
        return Coin(denom=supply.get("denom", denom), amount=supply.get("amount", "0"))

    def get_total_supply(self) -> List[Coin]:
        """Get total supply of all denominations"""
        data = self._api_get("cosmos/bank/v1beta1/supply")
        supply = data.get("supply", [])
        return [Coin(denom=s["denom"], amount=s["amount"]) for s in supply]

    # ==================== STAKING MODULE ====================

    def get_staking_validators(
        self, status: Optional[str] = None, pagination_limit: int = 100
    ) -> List[Validator]:
        """
        Get validator set with optional status filter

        Args:
            status: BOND_STATUS_BONDED, BOND_STATUS_UNBONDING, BOND_STATUS_UNBONDED
            pagination_limit: Max validators to return
        """
        params = {"pagination.limit": str(pagination_limit)}
        if status:
            params["status"] = status

        data = self._api_get("cosmos/staking/v1beta1/validators", params)
        validators = data.get("validators", [])

        return [
            Validator(
                operator_address=v["operator_address"],
                consensus_address=v.get("consensus_pubkey", {}).get("key", ""),
                jailed=v["jailed"],
                status=v["status"],
                tokens=v["tokens"],
                delegator_shares=v["delegator_shares"],
                description=v["description"],
                unbonding_height=int(v.get("unbonding_height", 0)),
                unbonding_time=v.get("unbonding_time", ""),
                commission=v["commission"],
                min_self_delegation=v["min_self_delegation"],
            )
            for v in validators
        ]

    def get_validator(self, validator_address: str) -> Validator:
        """Get single validator details"""
        data = self._api_get(f"cosmos/staking/v1beta1/validators/{validator_address}")
        v = data["validator"]

        return Validator(
            operator_address=v["operator_address"],
            consensus_address=v.get("consensus_pubkey", {}).get("key", ""),
            jailed=v["jailed"],
            status=v["status"],
            tokens=v["tokens"],
            delegator_shares=v["delegator_shares"],
            description=v["description"],
            unbonding_height=int(v.get("unbonding_height", 0)),
            unbonding_time=v.get("unbonding_time", ""),
            commission=v["commission"],
            min_self_delegation=v["min_self_delegation"],
        )

    def get_delegations(self, delegator_address: str) -> List[Delegation]:
        """Get all delegations for address"""
        data = self._api_get(f"cosmos/staking/v1beta1/delegations/{delegator_address}")
        delegations = data.get("delegation_responses", [])

        return [
            Delegation(
                delegator_address=d["delegation"]["delegator_address"],
                validator_address=d["delegation"]["validator_address"],
                shares=d["delegation"]["shares"],
                balance=Coin(
                    denom=d["balance"]["denom"], amount=d["balance"]["amount"]
                ),
            )
            for d in delegations
        ]

    def get_validator_delegations(self, validator_address: str) -> List[Delegation]:
        """Get all delegations to a validator"""
        data = self._api_get(
            f"cosmos/staking/v1beta1/validators/{validator_address}/delegations"
        )
        delegations = data.get("delegation_responses", [])

        return [
            Delegation(
                delegator_address=d["delegation"]["delegator_address"],
                validator_address=d["delegation"]["validator_address"],
                shares=d["delegation"]["shares"],
                balance=Coin(
                    denom=d["balance"]["denom"], amount=d["balance"]["amount"]
                ),
            )
            for d in delegations
        ]

    def get_staking_pool(self) -> Dict[str, str]:
        """Get staking pool totals"""
        data = self._api_get("cosmos/staking/v1beta1/pool")
        return data.get("pool", {})

    def get_staking_params(self) -> Dict[str, Any]:
        """Get staking module parameters"""
        data = self._api_get("cosmos/staking/v1beta1/params")
        return data.get("params", {})

    # ==================== GOVERNANCE MODULE ====================

    def get_proposals(
        self,
        status: Optional[str] = None,
        voter: Optional[str] = None,
        depositor: Optional[str] = None,
    ) -> List[Proposal]:
        """
        Get governance proposals with optional filters

        Args:
            status: PROPOSAL_STATUS_VOTING_PERIOD, PROPOSAL_STATUS_PASSED, etc.
            voter: Filter by voter address
            depositor: Filter by depositor address
        """
        params = {"pagination.limit": "100"}
        if status:
            params["proposal_status"] = status
        if voter:
            params["voter"] = voter
        if depositor:
            params["depositor"] = depositor

        data = self._api_get("cosmos/gov/v1beta1/proposals", params)
        proposals = data.get("proposals", [])

        return [
            Proposal(
                proposal_id=int(p["proposal_id"]),
                content=p.get("content", {}),
                status=p["status"],
                final_tally_result=p.get("final_tally_result", {}),
                submit_time=p["submit_time"],
                deposit_end_time=p["deposit_end_time"],
                total_deposit=[
                    Coin(denom=c["denom"], amount=c["amount"])
                    for c in p.get("total_deposit", [])
                ],
                voting_start_time=p.get("voting_start_time", ""),
                voting_end_time=p.get("voting_end_time", ""),
            )
            for p in proposals
        ]

    def get_proposal(self, proposal_id: int) -> Proposal:
        """Get single proposal details"""
        data = self._api_get(f"cosmos/gov/v1beta1/proposals/{proposal_id}")
        p = data["proposal"]

        return Proposal(
            proposal_id=int(p["proposal_id"]),
            content=p.get("content", {}),
            status=p["status"],
            final_tally_result=p.get("final_tally_result", {}),
            submit_time=p["submit_time"],
            deposit_end_time=p["deposit_end_time"],
            total_deposit=[
                Coin(denom=c["denom"], amount=c["amount"])
                for c in p.get("total_deposit", [])
            ],
            voting_start_time=p.get("voting_start_time", ""),
            voting_end_time=p.get("voting_end_time", ""),
        )

    def get_proposal_votes(self, proposal_id: int) -> Dict[str, Any]:
        """Get votes for proposal"""
        data = self._api_get(
            f"cosmos/gov/v1beta1/proposals/{proposal_id}/votes",
            {"pagination.limit": "1000"},
        )
        return data

    def get_proposal_tally(self, proposal_id: int) -> Dict[str, str]:
        """Get current tally for proposal"""
        data = self._api_get(f"cosmos/gov/v1beta1/proposals/{proposal_id}/tally")
        return data.get("tally", {})

    # ==================== DISTRIBUTION MODULE ====================

    def get_delegation_rewards(
        self, delegator_address: str, validator_address: Optional[str] = None
    ) -> List[Coin]:
        """Get delegation rewards"""
        if validator_address:
            endpoint = f"cosmos/distribution/v1beta1/delegators/{delegator_address}/rewards/{validator_address}"
        else:
            endpoint = (
                f"cosmos/distribution/v1beta1/delegators/{delegator_address}/rewards"
            )

        data = self._api_get(endpoint)

        if validator_address:
            rewards = data.get("rewards", [])
        else:
            rewards = data.get("total", [])

        return [Coin(denom=r["denom"], amount=r["amount"]) for r in rewards]

    def get_validator_commission(self, validator_address: str) -> List[Coin]:
        """Get validator commission"""
        data = self._api_get(
            f"cosmos/distribution/v1beta1/validators/{validator_address}/commission"
        )
        commission = data.get("commission", {}).get("commission", [])
        return [Coin(denom=c["denom"], amount=c["amount"]) for c in commission]

    def get_community_pool(self) -> List[Coin]:
        """Get community pool balance"""
        data = self._api_get("cosmos/distribution/v1beta1/community_pool")
        pool = data.get("pool", [])
        return [Coin(denom=p["denom"], amount=p["amount"]) for p in pool]

    # ==================== AURA CUSTOM MODULES ====================

    def get_did_document(self, did: str) -> Optional[DIDDocument]:
        """Query identity module for DID document"""
        try:
            data = self._api_get(f"aura/identity/v1/dids/{did}")
            doc = data.get("did_document", {})

            return DIDDocument(
                did=doc.get("id", did),
                owner=doc.get("controller", [""])[0],
                controller=doc.get("controller", []),
                verification_method=doc.get("verificationMethod", []),
                authentication=doc.get("authentication", []),
                service=doc.get("service", []),
            )
        except Exception as e:
            logger.error(f"Failed to get DID document: {e}")
            return None

    def get_verifiable_credentials(self, holder: str) -> List[VerifiableCredential]:
        """Query vcregistry module for credentials"""
        try:
            data = self._api_get(f"aura/vcregistry/v1/credentials/holder/{holder}")
            credentials = data.get("credentials", [])

            return [
                VerifiableCredential(
                    credential_id=vc.get("id", ""),
                    issuer=vc.get("issuer", ""),
                    holder=vc.get("credentialSubject", {}).get("id", holder),
                    credential_type=vc.get("type", [""])[0],
                    status=vc.get("credentialStatus", {}).get("type", "active"),
                    issuance_date=vc.get("issuanceDate", ""),
                    expiration_date=vc.get("expirationDate"),
                    credential_data=vc.get("credentialSubject", {}),
                )
                for vc in credentials
            ]
        except Exception as e:
            logger.error(f"Failed to get VCs: {e}")
            return []

    def get_dex_pools(self) -> List[Pool]:
        """Query DEX module for liquidity pools"""
        try:
            data = self._api_get("aura/dex/v1/pools")
            pools = data.get("pools", [])

            return [
                Pool(
                    pool_id=int(p.get("pool_id", 0)),
                    token_a_denom=p.get("token_a_denom", ""),
                    token_b_denom=p.get("token_b_denom", ""),
                    token_a_reserve=p.get("token_a_reserve", "0"),
                    token_b_reserve=p.get("token_b_reserve", "0"),
                    total_shares=p.get("total_shares", "0"),
                    swap_fee=p.get("swap_fee", "0"),
                )
                for p in pools
            ]
        except Exception as e:
            logger.error(f"Failed to get DEX pools: {e}")
            return []

    def get_dex_pool(self, pool_id: int) -> Optional[Pool]:
        """Query DEX module for single pool"""
        try:
            data = self._api_get(f"aura/dex/v1/pools/{pool_id}")
            p = data.get("pool", {})

            return Pool(
                pool_id=int(p.get("pool_id", pool_id)),
                token_a_denom=p.get("token_a_denom", ""),
                token_b_denom=p.get("token_b_denom", ""),
                token_a_reserve=p.get("token_a_reserve", "0"),
                token_b_reserve=p.get("token_b_reserve", "0"),
                total_shares=p.get("total_shares", "0"),
                swap_fee=p.get("swap_fee", "0"),
            )
        except Exception as e:
            logger.error(f"Failed to get DEX pool: {e}")
            return None

    def get_bridge_state(self) -> Optional[BridgeState]:
        """Query bridge module state"""
        try:
            data = self._api_get("aura/bridge/v1/state")
            state = data.get("state", {})

            return BridgeState(
                total_locked=state.get("total_locked", {}),
                total_minted=state.get("total_minted", {}),
                supported_chains=state.get("supported_chains", []),
                active_transfers=int(state.get("active_transfers", 0)),
            )
        except Exception as e:
            logger.error(f"Failed to get bridge state: {e}")
            return None

    def get_bridge_transfers(
        self,
        sender: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query bridge module for transfer history"""
        try:
            params = {"pagination.limit": str(limit)}
            if sender:
                params["sender"] = sender
            if status:
                params["status"] = status

            data = self._api_get("aura/bridge/v1/transfers", params)
            return data.get("transfers", [])
        except Exception as e:
            logger.error(f"Failed to get bridge transfers: {e}")
            return []

    def get_contracts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Query WASM module for deployed contracts"""
        try:
            data = self._api_get(
                "cosmwasm/wasm/v1/code", {"pagination.limit": str(limit)}
            )
            return data.get("code_infos", [])
        except Exception as e:
            logger.error(f"Failed to get contracts: {e}")
            return []

    def get_contract_info(self, contract_address: str) -> Optional[Dict[str, Any]]:
        """Query contract info"""
        try:
            data = self._api_get(f"cosmwasm/wasm/v1/contract/{contract_address}")
            return data.get("contract_info", {})
        except Exception as e:
            logger.error(f"Failed to get contract info: {e}")
            return None

    def query_contract(
        self, contract_address: str, query_msg: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Execute smart contract query"""
        try:
            import base64

            query_data = base64.b64encode(json.dumps(query_msg).encode()).decode()
            data = self._api_get(
                f"cosmwasm/wasm/v1/contract/{contract_address}/smart/{query_data}"
            )
            return data.get("data", {})
        except Exception as e:
            logger.error(f"Failed to query contract: {e}")
            return None
