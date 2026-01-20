"""
Transaction Decoder for Aura Blockchain
Decodes Cosmos SDK and Aura custom message types into human-readable format
"""

from __future__ import annotations

import json
import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ==================== DATA MODELS ====================


@dataclass
class DecodedMessage:
    """Decoded transaction message"""

    type_url: str
    type_name: str  # Human-readable name
    sender: Optional[str]
    data: Dict[str, Any]
    amount: List[Dict[str, str]] = field(default_factory=list)
    fee: Optional[Dict[str, Any]] = None


@dataclass
class DecodedTransaction:
    """Fully decoded transaction"""

    tx_hash: str
    height: int
    timestamp: str
    success: bool
    code: int
    messages: List[DecodedMessage]
    events: List[Dict[str, Any]]
    gas_wanted: int
    gas_used: int
    fee: Dict[str, Any]
    memo: str
    raw_log: str


# ==================== MESSAGE TYPE REGISTRY ====================


class MessageTypeRegistry:
    """Registry of known message types with decoders"""

    # Cosmos SDK standard messages
    COSMOS_MESSAGES = {
        "/cosmos.bank.v1beta1.MsgSend": "Bank Transfer",
        "/cosmos.bank.v1beta1.MsgMultiSend": "Multi-Send",
        "/cosmos.staking.v1beta1.MsgDelegate": "Delegate",
        "/cosmos.staking.v1beta1.MsgUndelegate": "Undelegate",
        "/cosmos.staking.v1beta1.MsgBeginRedelegate": "Redelegate",
        "/cosmos.staking.v1beta1.MsgCreateValidator": "Create Validator",
        "/cosmos.staking.v1beta1.MsgEditValidator": "Edit Validator",
        "/cosmos.distribution.v1beta1.MsgWithdrawDelegatorReward": "Withdraw Rewards",
        "/cosmos.distribution.v1beta1.MsgWithdrawValidatorCommission": "Withdraw Commission",
        "/cosmos.distribution.v1beta1.MsgSetWithdrawAddress": "Set Withdraw Address",
        "/cosmos.gov.v1beta1.MsgSubmitProposal": "Submit Proposal",
        "/cosmos.gov.v1beta1.MsgVote": "Vote",
        "/cosmos.gov.v1beta1.MsgVoteWeighted": "Weighted Vote",
        "/cosmos.gov.v1beta1.MsgDeposit": "Deposit",
        "/ibc.core.client.v1.MsgCreateClient": "Create IBC Client",
        "/ibc.core.client.v1.MsgUpdateClient": "Update IBC Client",
        "/ibc.core.connection.v1.MsgConnectionOpenInit": "IBC Connection Open Init",
        "/ibc.core.connection.v1.MsgConnectionOpenTry": "IBC Connection Open Try",
        "/ibc.core.connection.v1.MsgConnectionOpenAck": "IBC Connection Open Ack",
        "/ibc.core.connection.v1.MsgConnectionOpenConfirm": "IBC Connection Open Confirm",
        "/ibc.core.channel.v1.MsgChannelOpenInit": "IBC Channel Open Init",
        "/ibc.core.channel.v1.MsgChannelOpenTry": "IBC Channel Open Try",
        "/ibc.core.channel.v1.MsgChannelOpenAck": "IBC Channel Open Ack",
        "/ibc.core.channel.v1.MsgChannelOpenConfirm": "IBC Channel Open Confirm",
        "/ibc.applications.transfer.v1.MsgTransfer": "IBC Transfer",
        "/cosmwasm.wasm.v1.MsgStoreCode": "Store Contract Code",
        "/cosmwasm.wasm.v1.MsgInstantiateContract": "Instantiate Contract",
        "/cosmwasm.wasm.v1.MsgExecuteContract": "Execute Contract",
        "/cosmwasm.wasm.v1.MsgMigrateContract": "Migrate Contract",
        "/cosmwasm.wasm.v1.MsgUpdateAdmin": "Update Contract Admin",
        "/cosmwasm.wasm.v1.MsgClearAdmin": "Clear Contract Admin",
    }

    # Aura custom messages - Identity & Verification
    AURA_IDENTITY_MESSAGES = {
        "/aura.identity.v1.MsgRegisterDID": "Register DID",
        "/aura.identity.v1.MsgUpdateDID": "Update DID",
        "/aura.identity.v1.MsgDeactivateDID": "Deactivate DID",
        "/aura.vcregistry.v1.MsgIssueCredential": "Issue Credential",
        "/aura.vcregistry.v1.MsgRevokeCredential": "Revoke Credential",
        "/aura.vcregistry.v1.MsgVerifyCredential": "Verify Credential",
        "/aura.identitychange.v1.MsgRequestChange": "Request Identity Change",
        "/aura.identitychange.v1.MsgApproveChange": "Approve Identity Change",
        "/aura.identitychange.v1.MsgRejectChange": "Reject Identity Change",
        "/aura.inclusionroutines.v1.MsgUpdateScore": "Update Inclusion Score",
        "/aura.confidencescore.v1.MsgUpdateConfidence": "Update Confidence Score",
    }

    # Aura custom messages - DEX
    AURA_DEX_MESSAGES = {
        "/aura.dex.v1.MsgCreatePool": "Create Liquidity Pool",
        "/aura.dex.v1.MsgAddLiquidity": "Add Liquidity",
        "/aura.dex.v1.MsgRemoveLiquidity": "Remove Liquidity",
        "/aura.dex.v1.MsgSwap": "Swap Tokens",
    }

    # Aura custom messages - Bridge
    AURA_BRIDGE_MESSAGES = {
        "/aura.bridge.v1.MsgLockTokens": "Lock Tokens (Bridge)",
        "/aura.bridge.v1.MsgMintTokens": "Mint Tokens (Bridge)",
        "/aura.bridge.v1.MsgBurnTokens": "Burn Tokens (Bridge)",
        "/aura.bridge.v1.MsgUnlockTokens": "Unlock Tokens (Bridge)",
        "/aura.bridge.v1.MsgRegisterChain": "Register Chain (Bridge)",
        "/aura.bridge.v1.MsgUpdateProof": "Update Merkle Proof (Bridge)",
    }

    # Aura custom messages - Governance
    AURA_GOVERNANCE_MESSAGES = {
        "/aura.governance.v1.MsgSubmitProposal": "Submit Governance Proposal",
        "/aura.governance.v1.MsgVote": "Vote on Proposal",
        "/aura.governance.v1.MsgVetoProposal": "Veto Proposal",
    }

    # Aura custom messages - Security & Privacy
    AURA_SECURITY_MESSAGES = {
        "/aura.privacy.v1.MsgCreatePrivateChannel": "Create Private Channel",
        "/aura.privacy.v1.MsgSendPrivateMessage": "Send Private Message",
        "/aura.cryptography.v1.MsgRegisterKey": "Register Cryptographic Key",
        "/aura.cryptography.v1.MsgRevokeKey": "Revoke Cryptographic Key",
        "/aura.security.v1.MsgReportIncident": "Report Security Incident",
        "/aura.security.v1.MsgUpdateSecurityPolicy": "Update Security Policy",
    }

    # Aura custom messages - Economics & Compliance
    AURA_ECONOMICS_MESSAGES = {
        "/aura.economics.v1.MsgUpdateParameters": "Update Economic Parameters",
        "/aura.economicsecurity.v1.MsgStakeForSecurity": "Stake for Security",
        "/aura.compliance.v1.MsgRegisterEntity": "Register Entity (Compliance)",
        "/aura.compliance.v1.MsgUpdateAMLRules": "Update AML Rules",
        "/aura.compliance.v1.MsgScreenTransaction": "Screen Transaction (AML)",
    }

    # Aura custom messages - Data & Contracts
    AURA_DATA_MESSAGES = {
        "/aura.dataregistry.v1.MsgRegisterData": "Register Data",
        "/aura.dataregistry.v1.MsgUpdateData": "Update Data",
        "/aura.dataregistry.v1.MsgDeleteData": "Delete Data",
        "/aura.contractregistry.v1.MsgRegisterContract": "Register Contract",
        "/aura.contractregistry.v1.MsgVerifyContract": "Verify Contract",
    }

    # Aura custom messages - AI
    AURA_AI_MESSAGES = {
        "/aura.aiassistant.v1.MsgRegisterAgent": "Register AI Agent",
        "/aura.aiassistant.v1.MsgAssignVoucher": "Assign AI Voucher",
        "/aura.aiassistant.v1.MsgRedeemVoucher": "Redeem AI Voucher",
    }

    @classmethod
    def get_all_messages(cls) -> Dict[str, str]:
        """Get combined registry of all message types"""
        all_messages = {}
        all_messages.update(cls.COSMOS_MESSAGES)
        all_messages.update(cls.AURA_IDENTITY_MESSAGES)
        all_messages.update(cls.AURA_DEX_MESSAGES)
        all_messages.update(cls.AURA_BRIDGE_MESSAGES)
        all_messages.update(cls.AURA_GOVERNANCE_MESSAGES)
        all_messages.update(cls.AURA_SECURITY_MESSAGES)
        all_messages.update(cls.AURA_ECONOMICS_MESSAGES)
        all_messages.update(cls.AURA_DATA_MESSAGES)
        all_messages.update(cls.AURA_AI_MESSAGES)
        return all_messages

    @classmethod
    def get_type_name(cls, type_url: str) -> str:
        """Get human-readable name for message type"""
        all_messages = cls.get_all_messages()
        return all_messages.get(type_url, "Unknown Message")


# ==================== TRANSACTION DECODER ====================


class TransactionDecoder:
    """Decode Cosmos SDK and Aura custom message types"""

    def __init__(self):
        """Initialize transaction decoder"""
        self.message_registry = MessageTypeRegistry.get_all_messages()

    def decode_transaction(self, tx_response: Dict[str, Any]) -> DecodedTransaction:
        """
        Decode full transaction with all messages

        Args:
            tx_response: Raw transaction response from RPC/API

        Returns:
            DecodedTransaction with decoded messages
        """
        try:
            # Extract transaction data
            tx_hash = tx_response.get("txhash", tx_response.get("hash", ""))
            height = int(tx_response.get("height", 0))
            timestamp = tx_response.get("timestamp", "")
            code = int(tx_response.get("code", 0))
            success = code == 0

            # Decode messages
            tx_body = tx_response.get("tx", {}).get("body", {})
            messages_raw = tx_body.get("messages", [])
            messages = [self.decode_message(msg) for msg in messages_raw]

            # Extract events
            events = tx_response.get("events", [])
            if not events:
                # Try extracting from logs
                logs = tx_response.get("logs", [])
                if logs:
                    events = logs[0].get("events", [])

            # Extract fee
            auth_info = tx_response.get("tx", {}).get("auth_info", {})
            fee_data = auth_info.get("fee", {})
            fee = {
                "amount": fee_data.get("amount", []),
                "gas_limit": int(fee_data.get("gas_limit", 0)),
            }

            # Extract gas
            gas_wanted = int(tx_response.get("gas_wanted", 0))
            gas_used = int(tx_response.get("gas_used", 0))

            # Extract memo
            memo = tx_body.get("memo", "")

            # Raw log
            raw_log = tx_response.get("raw_log", "")

            return DecodedTransaction(
                tx_hash=tx_hash,
                height=height,
                timestamp=timestamp,
                success=success,
                code=code,
                messages=messages,
                events=events,
                gas_wanted=gas_wanted,
                gas_used=gas_used,
                fee=fee,
                memo=memo,
                raw_log=raw_log,
            )

        except Exception as e:
            logger.error(f"Failed to decode transaction: {e}")
            raise

    def decode_message(self, msg: Dict[str, Any]) -> DecodedMessage:
        """
        Decode individual message

        Args:
            msg: Raw message data

        Returns:
            DecodedMessage with decoded content
        """
        type_url = msg.get("@type", msg.get("type", ""))
        type_name = MessageTypeRegistry.get_type_name(type_url)

        # Route to specific decoder based on type
        if type_url.startswith("/cosmos.bank."):
            return self._decode_bank_message(type_url, type_name, msg)
        elif type_url.startswith("/cosmos.staking."):
            return self._decode_staking_message(type_url, type_name, msg)
        elif type_url.startswith("/cosmos.distribution."):
            return self._decode_distribution_message(type_url, type_name, msg)
        elif type_url.startswith("/cosmos.gov."):
            return self._decode_gov_message(type_url, type_name, msg)
        elif type_url.startswith("/ibc."):
            return self._decode_ibc_message(type_url, type_name, msg)
        elif type_url.startswith("/cosmwasm."):
            return self._decode_wasm_message(type_url, type_name, msg)
        elif type_url.startswith("/aura.dex."):
            return self._decode_dex_message(type_url, type_name, msg)
        elif type_url.startswith("/aura.bridge."):
            return self._decode_bridge_message(type_url, type_name, msg)
        elif type_url.startswith("/aura.identity.") or type_url.startswith(
            "/aura.vcregistry."
        ):
            return self._decode_identity_message(type_url, type_name, msg)
        else:
            return self._decode_generic_message(type_url, type_name, msg)

    # ==================== COSMOS SDK MESSAGE DECODERS ====================

    def _decode_bank_message(
        self, type_url: str, type_name: str, msg: Dict
    ) -> DecodedMessage:
        """Decode bank module messages"""
        if "MsgSend" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("from_address"),
                data={
                    "from": msg.get("from_address"),
                    "to": msg.get("to_address"),
                    "recipient": msg.get("to_address"),
                },
                amount=msg.get("amount", []),
            )
        elif "MsgMultiSend" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=None,
                data={
                    "inputs": msg.get("inputs", []),
                    "outputs": msg.get("outputs", []),
                },
            )
        else:
            return self._decode_generic_message(type_url, type_name, msg)

    def _decode_staking_message(
        self, type_url: str, type_name: str, msg: Dict
    ) -> DecodedMessage:
        """Decode staking module messages"""
        if "MsgDelegate" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("delegator_address"),
                data={
                    "delegator": msg.get("delegator_address"),
                    "validator": msg.get("validator_address"),
                },
                amount=[msg.get("amount", {})],
            )
        elif "MsgUndelegate" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("delegator_address"),
                data={
                    "delegator": msg.get("delegator_address"),
                    "validator": msg.get("validator_address"),
                },
                amount=[msg.get("amount", {})],
            )
        elif "MsgBeginRedelegate" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("delegator_address"),
                data={
                    "delegator": msg.get("delegator_address"),
                    "validator_src": msg.get("validator_src_address"),
                    "validator_dst": msg.get("validator_dst_address"),
                },
                amount=[msg.get("amount", {})],
            )
        elif "MsgCreateValidator" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("delegator_address"),
                data={
                    "validator": msg.get("validator_address"),
                    "description": msg.get("description", {}),
                    "commission": msg.get("commission", {}),
                    "min_self_delegation": msg.get("min_self_delegation"),
                },
                amount=[msg.get("value", {})],
            )
        else:
            return self._decode_generic_message(type_url, type_name, msg)

    def _decode_distribution_message(
        self, type_url: str, type_name: str, msg: Dict
    ) -> DecodedMessage:
        """Decode distribution module messages"""
        if "MsgWithdrawDelegatorReward" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("delegator_address"),
                data={
                    "delegator": msg.get("delegator_address"),
                    "validator": msg.get("validator_address"),
                },
            )
        elif "MsgWithdrawValidatorCommission" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("validator_address"),
                data={"validator": msg.get("validator_address")},
            )
        else:
            return self._decode_generic_message(type_url, type_name, msg)

    def _decode_gov_message(
        self, type_url: str, type_name: str, msg: Dict
    ) -> DecodedMessage:
        """Decode governance module messages"""
        if "MsgSubmitProposal" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("proposer"),
                data={
                    "proposer": msg.get("proposer"),
                    "content": msg.get("content", {}),
                    "initial_deposit": msg.get("initial_deposit", []),
                },
            )
        elif "MsgVote" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("voter"),
                data={
                    "voter": msg.get("voter"),
                    "proposal_id": msg.get("proposal_id"),
                    "option": msg.get("option"),
                },
            )
        elif "MsgDeposit" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("depositor"),
                data={
                    "depositor": msg.get("depositor"),
                    "proposal_id": msg.get("proposal_id"),
                },
                amount=msg.get("amount", []),
            )
        else:
            return self._decode_generic_message(type_url, type_name, msg)

    def _decode_ibc_message(
        self, type_url: str, type_name: str, msg: Dict
    ) -> DecodedMessage:
        """Decode IBC module messages"""
        if "MsgTransfer" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("sender"),
                data={
                    "sender": msg.get("sender"),
                    "receiver": msg.get("receiver"),
                    "source_port": msg.get("source_port"),
                    "source_channel": msg.get("source_channel"),
                    "timeout_height": msg.get("timeout_height"),
                    "timeout_timestamp": msg.get("timeout_timestamp"),
                },
                amount=[msg.get("token", {})],
            )
        else:
            return self._decode_generic_message(type_url, type_name, msg)

    def _decode_wasm_message(
        self, type_url: str, type_name: str, msg: Dict
    ) -> DecodedMessage:
        """Decode CosmWasm messages"""
        if "MsgStoreCode" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("sender"),
                data={
                    "sender": msg.get("sender"),
                    "wasm_byte_code_size": len(msg.get("wasm_byte_code", "")),
                },
            )
        elif "MsgInstantiateContract" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("sender"),
                data={
                    "sender": msg.get("sender"),
                    "admin": msg.get("admin"),
                    "code_id": msg.get("code_id"),
                    "label": msg.get("label"),
                    "msg": self._decode_base64_json(msg.get("msg")),
                },
                amount=msg.get("funds", []),
            )
        elif "MsgExecuteContract" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("sender"),
                data={
                    "sender": msg.get("sender"),
                    "contract": msg.get("contract"),
                    "msg": self._decode_base64_json(msg.get("msg")),
                },
                amount=msg.get("funds", []),
            )
        else:
            return self._decode_generic_message(type_url, type_name, msg)

    # ==================== AURA CUSTOM MESSAGE DECODERS ====================

    def _decode_dex_message(
        self, type_url: str, type_name: str, msg: Dict
    ) -> DecodedMessage:
        """Decode Aura DEX messages"""
        if "MsgCreatePool" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("creator"),
                data={
                    "creator": msg.get("creator"),
                    "token_a": msg.get("token_a"),
                    "token_b": msg.get("token_b"),
                    "swap_fee": msg.get("swap_fee"),
                },
            )
        elif "MsgSwap" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("sender"),
                data={
                    "sender": msg.get("sender"),
                    "pool_id": msg.get("pool_id"),
                    "token_in": msg.get("token_in"),
                    "token_out_min": msg.get("token_out_min"),
                },
            )
        elif "MsgAddLiquidity" in type_url or "MsgRemoveLiquidity" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("sender"),
                data={
                    "sender": msg.get("sender"),
                    "pool_id": msg.get("pool_id"),
                    "token_a": msg.get("token_a"),
                    "token_b": msg.get("token_b"),
                },
            )
        else:
            return self._decode_generic_message(type_url, type_name, msg)

    def _decode_bridge_message(
        self, type_url: str, type_name: str, msg: Dict
    ) -> DecodedMessage:
        """Decode Aura bridge messages"""
        if "MsgLockTokens" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("sender"),
                data={
                    "sender": msg.get("sender"),
                    "dest_chain": msg.get("dest_chain"),
                    "dest_address": msg.get("dest_address"),
                },
                amount=[msg.get("amount", {})],
            )
        elif "MsgMintTokens" in type_url or "MsgBurnTokens" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("sender"),
                data={
                    "sender": msg.get("sender"),
                    "recipient": msg.get("recipient"),
                    "source_chain": msg.get("source_chain"),
                    "proof": "Merkle proof included",
                },
                amount=[msg.get("amount", {})],
            )
        else:
            return self._decode_generic_message(type_url, type_name, msg)

    def _decode_identity_message(
        self, type_url: str, type_name: str, msg: Dict
    ) -> DecodedMessage:
        """Decode Aura identity/VC messages"""
        if "MsgRegisterDID" in type_url or "MsgUpdateDID" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("controller"),
                data={
                    "did": msg.get("did"),
                    "controller": msg.get("controller"),
                    "document": msg.get("did_document", {}),
                },
            )
        elif "MsgIssueCredential" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("issuer"),
                data={
                    "issuer": msg.get("issuer"),
                    "holder": msg.get("holder"),
                    "credential_type": msg.get("credential_type"),
                    "credential_data": msg.get("credential_data", {}),
                },
            )
        elif "MsgRevokeCredential" in type_url:
            return DecodedMessage(
                type_url=type_url,
                type_name=type_name,
                sender=msg.get("issuer"),
                data={
                    "issuer": msg.get("issuer"),
                    "credential_id": msg.get("credential_id"),
                    "reason": msg.get("reason"),
                },
            )
        else:
            return self._decode_generic_message(type_url, type_name, msg)

    def _decode_generic_message(
        self, type_url: str, type_name: str, msg: Dict
    ) -> DecodedMessage:
        """Decode unknown/generic message"""
        # Try to find sender field (common patterns)
        sender = (
            msg.get("sender")
            or msg.get("from_address")
            or msg.get("delegator_address")
            or msg.get("creator")
            or msg.get("signer")
            or None
        )

        # Try to find amount field
        amount = msg.get("amount") or msg.get("funds") or msg.get("value") or []
        if not isinstance(amount, list):
            amount = [amount]

        return DecodedMessage(
            type_url=type_url,
            type_name=type_name,
            sender=sender,
            data=msg,
            amount=amount,
        )

    # ==================== HELPER METHODS ====================

    def _decode_base64_json(self, base64_str: Optional[str]) -> Dict[str, Any]:
        """Decode base64-encoded JSON"""
        if not base64_str:
            return {}
        try:
            decoded = base64.b64decode(base64_str).decode("utf-8")
            return json.loads(decoded)
        except Exception as e:
            logger.error(f"Failed to decode base64 JSON: {e}")
            return {"raw": base64_str}

    def get_message_summary(self, message: DecodedMessage) -> str:
        """Generate human-readable message summary"""
        summary = f"{message.type_name}"

        if message.sender:
            summary += f" from {self._truncate_address(message.sender)}"

        if message.amount:
            amounts_str = ", ".join(
                [f"{a.get('amount', '0')} {a.get('denom', '')}" for a in message.amount]
            )
            summary += f" ({amounts_str})"

        return summary

    def _truncate_address(self, address: str, length: int = 10) -> str:
        """Truncate address for display"""
        if len(address) <= length * 2:
            return address
        return f"{address[:length]}...{address[-length:]}"
