"""
Advanced search API for block explorer
Supports searching by address, hash, height, module, and more
"""

import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class SearchCategory(Enum):
    """Search result categories"""

    BLOCK = "block"
    TRANSACTION = "transaction"
    ADDRESS = "address"
    VALIDATOR = "validator"
    MODULE = "module"
    UNKNOWN = "unknown"


@dataclass
class SearchResult:
    """Unified search result"""

    category: SearchCategory
    id: str
    title: str
    description: str
    data: Dict
    score: float = 1.0  # Relevance score


class AdvancedSearch:
    """Advanced search engine for blockchain data"""

    # Regex patterns for different search types
    PATTERNS = {
        "block_height": r"^\d+$",
        "block_hash": r"^[A-Fa-f0-9]{64}$",
        "tx_hash": r"^[A-Fa-f0-9]{64}$",
        "address_bech32": r"^aura[a-z0-9]{39}$",
        "validator_operator": r"^auravaloper[a-z0-9]{39}$",
    }

    def __init__(self, db_connection, node_client):
        """Initialize search engine"""
        self.db = db_connection
        self.node = node_client

    def search(self, query: str, limit: int = 20, offset: int = 0) -> Dict:
        """
        Perform comprehensive search
        Returns results categorized by type
        """
        query = query.strip()

        if not query:
            return {"results": [], "total": 0, "query": query}

        # Detect query type and search accordingly
        category = self._detect_category(query)

        results = []

        if category == SearchCategory.BLOCK:
            results.extend(self._search_blocks(query, limit))
        elif category == SearchCategory.TRANSACTION:
            results.extend(self._search_transactions(query, limit))
        elif category == SearchCategory.ADDRESS:
            results.extend(self._search_addresses(query, limit))
        elif category == SearchCategory.VALIDATOR:
            results.extend(self._search_validators(query, limit))
        else:
            # Multi-category search
            results.extend(self._search_all(query, limit))

        # Sort by relevance score
        results.sort(key=lambda x: x.score, reverse=True)

        # Apply pagination
        total = len(results)
        paginated_results = results[offset : offset + limit]

        return {
            "results": [self._format_result(r) for r in paginated_results],
            "total": total,
            "query": query,
            "category": category.value,
            "limit": limit,
            "offset": offset,
        }

    def search_by_address(self, address: str, tx_type: Optional[str] = None) -> Dict:
        """Search all activity for a specific address"""
        results = {
            "address": address,
            "transactions": [],
            "balance": None,
            "total_sent": 0,
            "total_received": 0,
            "tx_count": 0,
        }

        # Get transactions involving this address
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM transactions
            WHERE sender = ? OR recipient = ?
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            (address, address),
        )
        rows = cursor.fetchall()

        for row in rows:
            tx_data = dict(row)

            # Filter by type if specified
            if tx_type and tx_data.get("type") != tx_type:
                continue

            results["transactions"].append(tx_data)

            # Update statistics
            if tx_data.get("sender") == address:
                results["total_sent"] += tx_data.get("amount", 0)
            if tx_data.get("recipient") == address:
                results["total_received"] += tx_data.get("amount", 0)

        results["tx_count"] = len(results["transactions"])

        return results

    def search_by_module(self, module: str, limit: int = 50) -> List[Dict]:
        """Search transactions by module"""
        query = """
            SELECT * FROM transactions
            WHERE module = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """

        cursor = self.db.conn.cursor()
        cursor.execute(query, (module, limit))
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def search_by_hash(self, hash_value: str) -> Optional[Dict]:
        """Search by transaction or block hash"""
        # Try transaction first
        tx = self._get_transaction_by_hash(hash_value)
        if tx:
            return {
                "type": "transaction",
                "data": tx,
            }

        # Try block hash
        block = self._get_block_by_hash(hash_value)
        if block:
            return {
                "type": "block",
                "data": block,
            }

        return None

    def search_by_height(self, height: int) -> Optional[Dict]:
        """Search block by height"""
        block = self._get_block_by_height(height)
        if block:
            return {
                "type": "block",
                "data": block,
            }
        return None

    def autocomplete(self, query: str, limit: int = 10) -> List[Dict]:
        """Provide autocomplete suggestions"""
        suggestions = []

        query = query.lower().strip()

        if not query:
            return suggestions

        # Search in labeled addresses
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            SELECT address, label, category
            FROM address_labels
            WHERE LOWER(label) LIKE ?
            LIMIT ?
            """,
            (f"%{query}%", limit),
        )

        for row in cursor.fetchall():
            suggestions.append(
                {
                    "type": "address",
                    "value": row[0],
                    "label": row[1],
                    "category": row[2],
                }
            )

        # Search in modules
        modules = ["bank", "staking", "bridge", "vcregistry", "dex"]
        for module in modules:
            if query in module.lower():
                suggestions.append({"type": "module", "value": module, "label": module})

        return suggestions[:limit]

    def _detect_category(self, query: str) -> SearchCategory:
        """Detect search category from query"""
        if re.match(self.PATTERNS["block_height"], query):
            return SearchCategory.BLOCK

        if re.match(self.PATTERNS["block_hash"], query):
            return SearchCategory.BLOCK

        if re.match(self.PATTERNS["tx_hash"], query):
            return SearchCategory.TRANSACTION

        if re.match(self.PATTERNS["address_bech32"], query):
            return SearchCategory.ADDRESS

        if re.match(self.PATTERNS["validator_operator"], query):
            return SearchCategory.VALIDATOR

        return SearchCategory.UNKNOWN

    def _search_blocks(self, query: str, limit: int) -> List[SearchResult]:
        """Search blocks"""
        results = []

        # Try by height
        if query.isdigit():
            block = self._get_block_by_height(int(query))
            if block:
                results.append(
                    SearchResult(
                        category=SearchCategory.BLOCK,
                        id=str(block["height"]),
                        title=f"Block #{block['height']}",
                        description=f"Hash: {block.get('hash', 'N/A')[:16]}...",
                        data=block,
                        score=1.0,
                    )
                )

        # Try by hash
        elif re.match(self.PATTERNS["block_hash"], query):
            block = self._get_block_by_hash(query)
            if block:
                results.append(
                    SearchResult(
                        category=SearchCategory.BLOCK,
                        id=str(block["height"]),
                        title=f"Block #{block['height']}",
                        description=f"Hash: {query[:16]}...",
                        data=block,
                        score=1.0,
                    )
                )

        return results

    def _search_transactions(self, query: str, limit: int) -> List[SearchResult]:
        """Search transactions"""
        results = []

        if re.match(self.PATTERNS["tx_hash"], query):
            tx = self._get_transaction_by_hash(query)
            if tx:
                results.append(
                    SearchResult(
                        category=SearchCategory.TRANSACTION,
                        id=tx["hash"],
                        title=f"Transaction {query[:16]}...",
                        description=f"Type: {tx.get('type', 'N/A')}",
                        data=tx,
                        score=1.0,
                    )
                )

        return results

    def _search_addresses(self, query: str, limit: int) -> List[SearchResult]:
        """Search addresses"""
        results = []

        if re.match(self.PATTERNS["address_bech32"], query):
            # Get address info
            address_data = self._get_address_info(query)
            if address_data:
                results.append(
                    SearchResult(
                        category=SearchCategory.ADDRESS,
                        id=query,
                        title=f"Address {query[:16]}...",
                        description=f"Balance: {address_data.get('balance', 0)}",
                        data=address_data,
                        score=1.0,
                    )
                )

        return results

    def _search_validators(self, query: str, limit: int) -> List[SearchResult]:
        """Search validators"""
        results = []

        if re.match(self.PATTERNS["validator_operator"], query):
            validator = self._get_validator_info(query)
            if validator:
                results.append(
                    SearchResult(
                        category=SearchCategory.VALIDATOR,
                        id=query,
                        title=validator.get("moniker", query[:16] + "..."),
                        description=f"Status: {validator.get('status', 'Unknown')}",
                        data=validator,
                        score=1.0,
                    )
                )

        return results

    def _search_all(self, query: str, limit: int) -> List[SearchResult]:
        """Perform multi-category search"""
        results = []

        # Search in all categories
        results.extend(self._search_blocks(query, limit))
        results.extend(self._search_transactions(query, limit))
        results.extend(self._search_addresses(query, limit))
        results.extend(self._search_validators(query, limit))

        # Also search in labeled addresses
        results.extend(self._search_labels(query, limit))

        return results

    def _search_labels(self, query: str, limit: int) -> List[SearchResult]:
        """Search in address labels"""
        results = []

        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            SELECT address, label, category, description
            FROM address_labels
            WHERE LOWER(label) LIKE ? OR LOWER(description) LIKE ?
            LIMIT ?
            """,
            (f"%{query.lower()}%", f"%{query.lower()}%", limit),
        )

        for row in cursor.fetchall():
            results.append(
                SearchResult(
                    category=SearchCategory.ADDRESS,
                    id=row[0],
                    title=row[1],
                    description=row[3] or row[2],
                    data={"address": row[0], "label": row[1], "category": row[2]},
                    score=0.8,  # Lower score for label matches
                )
            )

        return results

    def _get_block_by_height(self, height: int) -> Optional[Dict]:
        """Get block by height"""
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT * FROM blocks WHERE height = ?", (height,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def _get_block_by_hash(self, block_hash: str) -> Optional[Dict]:
        """Get block by hash"""
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT * FROM blocks WHERE hash = ?", (block_hash,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def _get_transaction_by_hash(self, tx_hash: str) -> Optional[Dict]:
        """Get transaction by hash"""
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT * FROM transactions WHERE hash = ?", (tx_hash,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def _get_address_info(self, address: str) -> Optional[Dict]:
        """Get address information"""
        # This would query the node for current balance
        return {
            "address": address,
            "balance": "0",  # Would fetch from node
            "tx_count": 0,
        }

    def _get_validator_info(self, operator_address: str) -> Optional[Dict]:
        """Get validator information"""
        # This would query the node for validator info
        return {
            "operator_address": operator_address,
            "moniker": "Unknown",
            "status": "Unknown",
        }

    def _format_result(self, result: SearchResult) -> Dict:
        """Format search result for API response"""
        return {
            "category": result.category.value,
            "id": result.id,
            "title": result.title,
            "description": result.description,
            "score": result.score,
            "data": result.data,
        }
