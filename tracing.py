"""
Transaction tracing and analytics for block explorer
"""

import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TxTrace:
    """Transaction trace information"""
    tx_hash: str
    height: int
    timestamp: datetime
    sender: str
    recipient: Optional[str]
    amount: int
    fee: int
    gas_used: int
    gas_wanted: int
    status: str
    events: List[Dict] = field(default_factory=list)
    messages: List[Dict] = field(default_factory=list)
    logs: List[Dict] = field(default_factory=list)


@dataclass
class AddressFlow:
    """Track flow of funds for an address"""
    address: str
    inbound: List[TxTrace] = field(default_factory=list)
    outbound: List[TxTrace] = field(default_factory=list)
    total_received: int = 0
    total_sent: int = 0
    net_flow: int = 0


class TransactionTracer:
    """Trace transaction flows and relationships"""

    def __init__(self, db_connection, node_client):
        self.db = db_connection
        self.node = node_client

    def trace_transaction(self, tx_hash: str) -> Dict:
        """
        Trace a single transaction with full details
        """
        # Get transaction from database
        tx = self._get_transaction(tx_hash)
        if not tx:
            return {"error": "Transaction not found"}

        trace = {
            "hash": tx_hash,
            "height": tx.get("height"),
            "timestamp": tx.get("timestamp"),
            "status": tx.get("status", "unknown"),
            "messages": self._parse_messages(tx),
            "events": self._parse_events(tx),
            "gas": {
                "wanted": tx.get("gas_wanted", 0),
                "used": tx.get("gas_used", 0),
                "efficiency": self._calculate_gas_efficiency(tx),
            },
            "fees": self._parse_fees(tx),
            "signers": self._extract_signers(tx),
            "affected_addresses": self._extract_affected_addresses(tx),
            "related_transactions": self._find_related_transactions(tx_hash),
        }

        return trace

    def trace_address_flow(
        self, address: str, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None
    ) -> AddressFlow:
        """
        Trace all flows for an address within a time range
        """
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(days=30)

        flow = AddressFlow(address=address)

        # Get all transactions involving this address
        query = """
            SELECT * FROM transactions
            WHERE (sender = ? OR recipient = ?)
            AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
        """

        cursor = self.db.conn.cursor()
        cursor.execute(query, (address, address, start_time.timestamp(), end_time.timestamp()))

        for row in cursor.fetchall():
            tx_data = dict(row)
            trace = self._create_trace_from_row(tx_data)

            if tx_data.get("sender") == address:
                flow.outbound.append(trace)
                flow.total_sent += trace.amount
            else:
                flow.inbound.append(trace)
                flow.total_received += trace.amount

        flow.net_flow = flow.total_received - flow.total_sent

        return flow

    def trace_fund_path(self, start_address: str, end_address: str, max_hops: int = 5) -> List[List[str]]:
        """
        Find paths of fund transfers between two addresses
        Uses BFS to find shortest paths
        """
        if start_address == end_address:
            return [[start_address]]

        # Build transaction graph
        graph = self._build_transaction_graph()

        # BFS to find paths
        paths = []
        queue = [([start_address], set([start_address]))]

        while queue and len(paths) < 10:  # Limit to 10 paths
            path, visited = queue.pop(0)
            current = path[-1]

            if len(path) > max_hops:
                continue

            # Get all addresses that received from current
            if current in graph:
                for next_addr in graph[current]:
                    if next_addr == end_address:
                        paths.append(path + [next_addr])
                    elif next_addr not in visited:
                        queue.append((path + [next_addr], visited | {next_addr}))

        return paths

    def trace_token_origin(self, address: str, depth: int = 3) -> Dict:
        """
        Trace where tokens in an address originated from
        """
        origins = defaultdict(int)
        visited = set()

        def trace_recursive(addr: str, current_depth: int):
            if current_depth <= 0 or addr in visited:
                return

            visited.add(addr)

            # Get incoming transactions
            query = """
                SELECT sender, amount FROM transactions
                WHERE recipient = ?
                ORDER BY timestamp DESC
                LIMIT 100
            """

            cursor = self.db.conn.cursor()
            cursor.execute(query, (addr,))

            for row in cursor.fetchall():
                sender, amount = row
                origins[sender] += amount

                if current_depth > 1:
                    trace_recursive(sender, current_depth - 1)

        trace_recursive(address, depth)

        # Sort by amount
        sorted_origins = sorted(origins.items(), key=lambda x: x[1], reverse=True)

        return {
            "address": address,
            "depth": depth,
            "origins": [{"address": addr, "total_amount": amount} for addr, amount in sorted_origins],
            "unique_sources": len(origins),
        }

    def analyze_transaction_pattern(self, address: str, days: int = 30) -> Dict:
        """
        Analyze transaction patterns for an address
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        query = """
            SELECT * FROM transactions
            WHERE (sender = ? OR recipient = ?)
            AND timestamp BETWEEN ? AND ?
        """

        cursor = self.db.conn.cursor()
        cursor.execute(query, (address, address, start_time.timestamp(), end_time.timestamp()))

        # Collect statistics
        stats = {
            "total_transactions": 0,
            "sent_count": 0,
            "received_count": 0,
            "total_volume_sent": 0,
            "total_volume_received": 0,
            "avg_tx_size": 0,
            "most_common_counterparty": None,
            "transaction_types": defaultdict(int),
            "hourly_distribution": [0] * 24,
            "daily_distribution": [0] * 7,
        }

        counterparties = defaultdict(int)

        for row in cursor.fetchall():
            tx = dict(row)
            stats["total_transactions"] += 1

            amount = tx.get("amount", 0)
            tx_type = tx.get("type", "unknown")
            timestamp = datetime.fromtimestamp(tx.get("timestamp", 0))

            stats["transaction_types"][tx_type] += 1
            stats["hourly_distribution"][timestamp.hour] += 1
            stats["daily_distribution"][timestamp.weekday()] += 1

            if tx.get("sender") == address:
                stats["sent_count"] += 1
                stats["total_volume_sent"] += amount
                counterparty = tx.get("recipient")
            else:
                stats["received_count"] += 1
                stats["total_volume_received"] += amount
                counterparty = tx.get("sender")

            if counterparty:
                counterparties[counterparty] += 1

        # Calculate averages
        if stats["total_transactions"] > 0:
            total_volume = stats["total_volume_sent"] + stats["total_volume_received"]
            stats["avg_tx_size"] = total_volume // stats["total_transactions"]

        # Find most common counterparty
        if counterparties:
            stats["most_common_counterparty"] = max(counterparties.items(), key=lambda x: x[1])

        return stats

    def _get_transaction(self, tx_hash: str) -> Optional[Dict]:
        """Get transaction from database"""
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT * FROM transactions WHERE hash = ?", (tx_hash,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def _parse_messages(self, tx: Dict) -> List[Dict]:
        """Parse transaction messages"""
        # This would parse the actual message data
        return tx.get("messages", [])

    def _parse_events(self, tx: Dict) -> List[Dict]:
        """Parse transaction events"""
        return tx.get("events", [])

    def _parse_fees(self, tx: Dict) -> Dict:
        """Parse transaction fees"""
        return {
            "amount": tx.get("fee", 0),
            "denom": "uaura",
            "gas_price": tx.get("fee", 0) / max(tx.get("gas_wanted", 1), 1),
        }

    def _extract_signers(self, tx: Dict) -> List[str]:
        """Extract all signers from transaction"""
        return [tx.get("sender", "")]

    def _extract_affected_addresses(self, tx: Dict) -> List[str]:
        """Extract all addresses affected by transaction"""
        addresses = set()

        if tx.get("sender"):
            addresses.add(tx["sender"])
        if tx.get("recipient"):
            addresses.add(tx["recipient"])

        return list(addresses)

    def _find_related_transactions(self, tx_hash: str, limit: int = 5) -> List[str]:
        """Find transactions related to this one"""
        # Get the transaction
        tx = self._get_transaction(tx_hash)
        if not tx:
            return []

        # Find transactions in the same block
        query = """
            SELECT hash FROM transactions
            WHERE height = ? AND hash != ?
            LIMIT ?
        """

        cursor = self.db.conn.cursor()
        cursor.execute(query, (tx.get("height"), tx_hash, limit))

        return [row[0] for row in cursor.fetchall()]

    def _calculate_gas_efficiency(self, tx: Dict) -> float:
        """Calculate gas efficiency"""
        wanted = tx.get("gas_wanted", 0)
        used = tx.get("gas_used", 0)

        if wanted == 0:
            return 0.0

        return (used / wanted) * 100

    def _create_trace_from_row(self, row: Dict) -> TxTrace:
        """Create TxTrace from database row"""
        return TxTrace(
            tx_hash=row.get("hash", ""),
            height=row.get("height", 0),
            timestamp=datetime.fromtimestamp(row.get("timestamp", 0)),
            sender=row.get("sender", ""),
            recipient=row.get("recipient"),
            amount=row.get("amount", 0),
            fee=row.get("fee", 0),
            gas_used=row.get("gas_used", 0),
            gas_wanted=row.get("gas_wanted", 0),
            status=row.get("status", "unknown"),
        )

    def _build_transaction_graph(self) -> Dict[str, Set[str]]:
        """Build a graph of transaction flows"""
        graph = defaultdict(set)

        query = "SELECT sender, recipient FROM transactions WHERE recipient IS NOT NULL"

        cursor = self.db.conn.cursor()
        cursor.execute(query)

        for sender, recipient in cursor.fetchall():
            graph[sender].add(recipient)

        return graph
