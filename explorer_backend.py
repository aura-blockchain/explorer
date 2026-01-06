"""
AURA Block Explorer - Production-Grade Backend
Advanced analytics, search, and real-time capabilities for AURA blockchain
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock
from flasgger import Swagger

# Import AURA configuration
try:
    from config import config
except ImportError:
    # Fallback if config not available
    class config:
        NODE_RPC_URL = os.getenv("NODE_RPC_URL", "http://localhost:26657")
        NODE_API_URL = os.getenv("NODE_API_URL", "http://localhost:1317")
        CHAIN_ID = os.getenv("CHAIN_ID", "aura-testnet-1")
        DENOM = os.getenv("DENOM", "uaura")
        EXPLORER_PORT = int(os.getenv("EXPLORER_PORT", "8082"))
        EXPLORER_HOST = os.getenv("EXPLORER_HOST", "0.0.0.0")
        DB_PATH = os.getenv("EXPLORER_DB_PATH", "./explorer.db")
        DEBUG = os.getenv("DEBUG", "false").lower() == "true"
        LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT
)
logger = logging.getLogger(__name__)


# ==================== DATA MODELS ====================

class SearchType(Enum):
    """Types of searchable items"""
    BLOCK_HEIGHT = "block_height"
    BLOCK_HASH = "block_hash"
    TRANSACTION_ID = "transaction_id"
    ADDRESS = "address"
    UNKNOWN = "unknown"


@dataclass
class SearchResult:
    """Search result data"""
    type: SearchType
    item_id: str
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class AddressLabel:
    """Address labeling system"""
    address: str
    label: str
    category: str  # exchange, pool, whale, contract, etc.
    description: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class CachedMetric:
    """Cached metric data"""
    timestamp: float
    data: Dict[str, Any]
    ttl: int = 300  # 5 minutes default


# ==================== DATABASE MANAGEMENT ====================

class ExplorerDatabase:
    """SQLite database for explorer data with indexing"""

    def __init__(self, db_path: str = ":memory:"):
        """Initialize database"""
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.lock = threading.RLock()
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = self.conn.cursor()

            # Search history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    search_type TEXT NOT NULL,
                    user_id TEXT,
                    timestamp REAL NOT NULL,
                    result_found BOOLEAN DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_query ON search_history(query)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_timestamp ON search_history(timestamp)")

            # Address labels table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS address_labels (
                    address TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    created_at REAL NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_address_label ON address_labels(label)")

            # Analytics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    value REAL NOT NULL,
                    data TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_type ON analytics(metric_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_timestamp ON analytics(timestamp)")

            # Block explorer cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS explorer_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    ttl REAL NOT NULL
                )
            """)

            self.conn.commit()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

    def add_search(self, query: str, search_type: str, result_found: bool, user_id: str = "anonymous") -> None:
        """Record search query"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO search_history (query, search_type, user_id, timestamp, result_found)
                    VALUES (?, ?, ?, ?, ?)
                """, (query, search_type, user_id, time.time(), int(result_found)))
                self.conn.commit()
        except Exception as e:
            logger.error(f"Error recording search: {e}")

    def get_recent_searches(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent searches"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT query, search_type, timestamp
                    FROM search_history
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                return [
                    {"query": row[0], "type": row[1], "timestamp": row[2]}
                    for row in cursor.fetchall()
                ]
        except Exception as e:
            logger.error(f"Error fetching recent searches: {e}")
            return []

    def add_address_label(self, label: AddressLabel) -> None:
        """Add address label"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO address_labels (address, label, category, description, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (label.address, label.label, label.category, label.description, label.created_at))
                self.conn.commit()
        except Exception as e:
            logger.error(f"Error adding label: {e}")

    def get_address_label(self, address: str) -> Optional[AddressLabel]:
        """Get address label"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT address, label, category, description, created_at
                    FROM address_labels
                    WHERE address = ?
                """, (address,))
                row = cursor.fetchone()
                if row:
                    return AddressLabel(*row)
        except Exception as e:
            logger.error(f"Error fetching label: {e}")
        return None

    def record_metric(self, metric_type: str, value: float, data: Optional[Dict] = None) -> None:
        """Record analytics metric"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO analytics (metric_type, timestamp, value, data)
                    VALUES (?, ?, ?, ?)
                """, (metric_type, time.time(), value, json.dumps(data) if data else None))
                self.conn.commit()
        except Exception as e:
            logger.error(f"Error recording metric: {e}")

    def get_metrics(self, metric_type: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Get metrics for time period"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cutoff_time = time.time() - (hours * 3600)
                cursor.execute("""
                    SELECT timestamp, value, data
                    FROM analytics
                    WHERE metric_type = ? AND timestamp > ?
                    ORDER BY timestamp ASC
                """, (metric_type, cutoff_time))
                return [
                    {"timestamp": row[0], "value": row[1], "data": json.loads(row[2]) if row[2] else None}
                    for row in cursor.fetchall()
                ]
        except Exception as e:
            logger.error(f"Error fetching metrics: {e}")
            return []

    def set_cache(self, key: str, value: str, ttl: int = 300) -> None:
        """Set cache value"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO explorer_cache (key, value, ttl)
                    VALUES (?, ?, ?)
                """, (key, value, time.time() + ttl))
                self.conn.commit()
        except Exception as e:
            logger.error(f"Error setting cache: {e}")

    def get_cache(self, key: str) -> Optional[str]:
        """Get cache value"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT value FROM explorer_cache
                    WHERE key = ? AND ttl > ?
                """, (key, time.time()))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Error getting cache: {e}")
        return None


# ==================== ANALYTICS ENGINE ====================

class AnalyticsEngine:
    """Real-time analytics and metrics collection"""

    def __init__(self, node_url: str, db: ExplorerDatabase):
        """Initialize analytics engine"""
        self.node_url = node_url
        self.db = db
        self.metrics_cache: Dict[str, CachedMetric] = {}
        self.lock = threading.RLock()

        # Time-series data for recent metrics
        self.hashrate_history: deque = deque(maxlen=1440)  # 24 hours at 1-minute intervals
        self.tx_volume_history: deque = deque(maxlen=1440)
        self.active_addresses: Set[str] = set()
        self.mempool_sizes: deque = deque(maxlen=1440)

    def get_network_hashrate(self) -> Dict[str, Any]:
        """Calculate network hashrate"""
        cache_key = "hashrate"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            stats = self._fetch_stats()
            if not stats:
                return {"error": "Unable to fetch stats"}

            current_height = stats.get("total_blocks", 0)
            difficulty = stats.get("difficulty", 0)

            # Estimate hashrate from difficulty and block time
            avg_block_time = 60  # seconds (adjustable)
            estimated_hashrate = difficulty / avg_block_time if difficulty > 0 else 0

            result = {
                "hashrate": estimated_hashrate,
                "difficulty": difficulty,
                "block_height": current_height,
                "unit": "hashes/second",
                "timestamp": time.time()
            }

            self.db.set_cache(cache_key, json.dumps(result))
            self.db.record_metric("hashrate", estimated_hashrate)
            return result
        except Exception as e:
            logger.error(f"Error calculating hashrate: {e}")
            return {"error": str(e)}

    def get_transaction_volume(self, period: str = "24h") -> Dict[str, Any]:
        """Get transaction volume metrics"""
        cache_key = f"tx_volume_{period}"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            hours_map = {"24h": 24, "7d": 168, "30d": 720}
            hours = hours_map.get(period, 24)

            blocks_data = self._fetch_blocks()
            if not blocks_data:
                return {"error": "Unable to fetch blocks"}

            blocks = blocks_data.get("blocks", [])
            recent_cutoff = time.time() - (hours * 3600)

            tx_count = 0
            unique_txs = set()
            fees_collected = 0.0

            for block in blocks:
                if block.get("timestamp", 0) > recent_cutoff:
                    block_txs = block.get("transactions", [])
                    tx_count += len(block_txs)
                    for tx in block_txs:
                        unique_txs.add(tx.get("txid", ""))
                        fees_collected += float(tx.get("fee", 0))

            avg_tx_per_block = tx_count / len(blocks) if blocks else 0

            result = {
                "period": period,
                "total_transactions": tx_count,
                "unique_transactions": len(unique_txs),
                "average_tx_per_block": avg_tx_per_block,
                "total_fees_collected": fees_collected,
                "timestamp": time.time()
            }

            self.db.set_cache(cache_key, json.dumps(result))
            self.db.record_metric(f"tx_volume_{period}", tx_count, result)
            return result
        except Exception as e:
            logger.error(f"Error calculating transaction volume: {e}")
            return {"error": str(e)}

    def get_active_addresses(self) -> Dict[str, Any]:
        """Get count of active addresses"""
        cache_key = "active_addresses"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            blocks_data = self._fetch_blocks()
            if not blocks_data:
                return {"error": "Unable to fetch blocks"}

            blocks = blocks_data.get("blocks", [])
            addresses: Set[str] = set()

            for block in blocks:
                for tx in block.get("transactions", []):
                    if tx.get("sender"):
                        addresses.add(tx["sender"])
                    if tx.get("recipient"):
                        addresses.add(tx["recipient"])

            result = {
                "total_unique_addresses": len(addresses),
                "timestamp": time.time()
            }

            self.db.set_cache(cache_key, json.dumps(result))
            self.db.record_metric("active_addresses", len(addresses))
            return result
        except Exception as e:
            logger.error(f"Error calculating active addresses: {e}")
            return {"error": str(e)}

    def get_average_block_time(self) -> Dict[str, Any]:
        """Calculate average block time"""
        cache_key = "avg_block_time"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            blocks_data = self._fetch_blocks()
            if not blocks_data:
                return {"error": "Unable to fetch blocks"}

            blocks = sorted(
                blocks_data.get("blocks", []),
                key=lambda b: b.get("timestamp", 0)
            )

            if len(blocks) < 2:
                return {"error": "Insufficient blocks for calculation"}

            block_times = []
            for i in range(1, len(blocks)):
                time_diff = blocks[i].get("timestamp", 0) - blocks[i-1].get("timestamp", 0)
                if time_diff > 0:
                    block_times.append(time_diff)

            avg_block_time = sum(block_times) / len(block_times) if block_times else 0

            result = {
                "average_block_time_seconds": avg_block_time,
                "blocks_sampled": len(block_times),
                "timestamp": time.time()
            }

            self.db.set_cache(cache_key, json.dumps(result))
            self.db.record_metric("avg_block_time", avg_block_time)
            return result
        except Exception as e:
            logger.error(f"Error calculating average block time: {e}")
            return {"error": str(e)}

    def get_mempool_size(self) -> Dict[str, Any]:
        """Get pending transactions (mempool) size"""
        cache_key = "mempool_size"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            response = requests.get(f"{self.node_url}/transactions", timeout=15)
            response.raise_for_status()
            data = response.json()

            pending_count = data.get("count", 0)
            transactions = data.get("transactions", [])

            total_value = 0.0
            total_fees = 0.0
            for tx in transactions:
                total_value += float(tx.get("amount", 0))
                total_fees += float(tx.get("fee", 0))

            result = {
                "pending_transactions": pending_count,
                "total_value": total_value,
                "total_fees": total_fees,
                "avg_fee": total_fees / pending_count if pending_count > 0 else 0,
                "timestamp": time.time()
            }

            self.db.set_cache(cache_key, json.dumps(result))
            self.db.record_metric("mempool_size", pending_count, result)
            return result
        except Exception as e:
            logger.error(f"Error getting mempool size: {e}")
            return {"error": str(e)}

    def get_network_difficulty(self) -> Dict[str, Any]:
        """Get network difficulty trend"""
        try:
            stats = self._fetch_stats()
            if not stats:
                return {"error": "Unable to fetch stats"}

            difficulty = stats.get("difficulty", 0)

            result = {
                "current_difficulty": difficulty,
                "timestamp": time.time()
            }

            self.db.record_metric("network_difficulty", difficulty)
            return result
        except Exception as e:
            logger.error(f"Error getting difficulty: {e}")
            return {"error": str(e)}

    def _fetch_stats(self) -> Optional[Dict[str, Any]]:
        """Fetch stats from Cosmos SDK node"""
        try:
            # Get blockchain info from Cosmos SDK RPC
            response = requests.get(f"{self.node_url}/blockchain", timeout=15)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                last_height = data["result"].get("last_height", "0")
                return {
                    "total_blocks": int(last_height),
                    "difficulty": 0,  # PoS chains don't have difficulty
                    "last_height": int(last_height)
                }
        except Exception as e:
            logger.error(f"Error fetching stats: {e}")
        return None

    def _fetch_blocks(self, limit: int = 100, offset: int = 0) -> Optional[Dict[str, Any]]:
        """Fetch blocks from Cosmos SDK node"""
        try:
            # Get latest blockchain info
            blockchain_response = requests.get(
                f"{self.node_url}/blockchain?minHeight=1&maxHeight={limit}",
                timeout=30
            )
            blockchain_response.raise_for_status()
            data = blockchain_response.json()

            blocks = []
            if data.get("result") and data["result"].get("block_metas"):
                for meta in data["result"]["block_metas"]:
                    block_time = meta["header"]["time"]
                    # Parse ISO timestamp to unix timestamp
                    try:
                        dt = datetime.fromisoformat(block_time.replace("Z", "+00:00"))
                        timestamp = dt.timestamp()
                    except:
                        timestamp = time.time()

                    blocks.append({
                        "height": int(meta["header"]["height"]),
                        "hash": meta.get("block_id", {}).get("hash", ""),
                        "timestamp": timestamp,
                        "num_txs": int(meta["num_txs"]),
                        "transactions": []  # Would need separate queries
                    })

            return {"blocks": blocks, "count": len(blocks)}
        except Exception as e:
            logger.error(f"Error fetching blocks: {e}")
        return None


# ==================== SEARCH ENGINE ====================

class SearchEngine:
    """Advanced search with autocomplete and history"""

    def __init__(self, node_url: str, db: ExplorerDatabase):
        """Initialize search engine"""
        self.node_url = node_url
        self.db = db
        self.recent_searches: deque = deque(maxlen=100)

    def search(self, query: str, user_id: str = "anonymous") -> Dict[str, Any]:
        """Perform search and determine type"""
        query = query.strip()
        search_type = self._identify_search_type(query)

        result = {
            "query": query,
            "type": search_type.value,
            "results": None,
            "timestamp": time.time()
        }

        try:
            if search_type == SearchType.BLOCK_HEIGHT:
                result["results"] = self._search_block_height(int(query))
            elif search_type == SearchType.BLOCK_HASH:
                result["results"] = self._search_block_hash(query)
            elif search_type == SearchType.TRANSACTION_ID:
                result["results"] = self._search_transaction(query)
            elif search_type == SearchType.ADDRESS:
                result["results"] = self._search_address(query)

            # Record search
            found = result["results"] is not None
            self.db.add_search(query, search_type.value, found, user_id)

            result["found"] = found
        except Exception as e:
            logger.error(f"Search error: {e}")
            result["error"] = str(e)

        return result

    def get_autocomplete_suggestions(self, prefix: str, limit: int = 10) -> List[str]:
        """Get autocomplete suggestions from recent searches"""
        try:
            recent = self.db.get_recent_searches(limit * 2)
            suggestions = [
                item["query"] for item in recent
                if item["query"].startswith(prefix)
            ]
            return suggestions[:limit]
        except Exception as e:
            logger.error(f"Autocomplete error: {e}")
            return []

    def get_recent_searches(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent searches"""
        return self.db.get_recent_searches(limit)

    def _identify_search_type(self, query: str) -> SearchType:
        """Identify search query type - AURA compatible"""
        if query.isdigit():
            return SearchType.BLOCK_HEIGHT

        # AURA uses bech32 addresses starting with 'aura'
        if query.startswith("aura") and len(query) > 10:
            return SearchType.ADDRESS

        # Cosmos SDK transaction hashes are uppercase hex strings
        if len(query) == 64 and all(c in '0123456789abcdefABCDEF' for c in query):
            return SearchType.TRANSACTION_ID

        # Block hash format
        if len(query) == 64:
            return SearchType.BLOCK_HASH

        return SearchType.UNKNOWN

    def _search_block_height(self, height: int) -> Optional[Dict[str, Any]]:
        """Search by block height - Cosmos SDK RPC"""
        try:
            # Use Cosmos SDK RPC endpoint
            response = requests.get(
                f"{self.node_url}/block?height={height}",
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("result"):
                    block = data["result"]["block"]
                    return {
                        "height": block["header"]["height"],
                        "hash": block["header"].get("last_block_id", {}).get("hash", ""),
                        "time": block["header"]["time"],
                        "proposer": block["header"].get("proposer_address", ""),
                        "num_txs": len(block.get("data", {}).get("txs", [])),
                        "txs": block.get("data", {}).get("txs", [])
                    }
        except Exception as e:
            logger.error(f"Block search error: {e}")
        return None

    def _search_block_hash(self, block_hash: str) -> Optional[Dict[str, Any]]:
        """Search by block hash - Cosmos SDK RPC"""
        try:
            # Use Cosmos SDK RPC to get block by hash
            response = requests.get(
                f"{self.node_url}/block_by_hash?hash=0x{block_hash}",
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("result"):
                    block = data["result"]["block"]
                    return {
                        "height": block["header"]["height"],
                        "hash": block_hash,
                        "time": block["header"]["time"],
                        "proposer": block["header"].get("proposer_address", ""),
                        "num_txs": len(block.get("data", {}).get("txs", []))
                    }
        except Exception as e:
            logger.error(f"Hash search error: {e}")
        return None

    def _search_transaction(self, txid: str) -> Optional[Dict[str, Any]]:
        """Search by transaction ID - Cosmos SDK RPC"""
        try:
            # Use Cosmos SDK RPC to get transaction
            response = requests.get(
                f"{self.node_url}/tx?hash=0x{txid}",
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("result"):
                    return data["result"]
        except Exception as e:
            logger.error(f"Transaction search error: {e}")
        return None

    def _search_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Search by address - Cosmos SDK API"""
        try:
            # Use Cosmos SDK REST API for balance
            api_url = config.NODE_API_URL if hasattr(config, 'NODE_API_URL') else "http://localhost:1317"
            balance_response = requests.get(
                f"{api_url}/cosmos/bank/v1beta1/balances/{address}",
                timeout=15
            )

            if balance_response.status_code == 200:
                balance_data = balance_response.json()
                balances = balance_data.get("balances", [])

                # Calculate total balance in uaura
                total_balance = 0
                for bal in balances:
                    if bal.get("denom") == config.DENOM:
                        total_balance = int(bal.get("amount", 0))

                return {
                    "address": address,
                    "balance": total_balance,
                    "balances": balances,
                    "denom": config.DENOM
                }
        except Exception as e:
            logger.error(f"Address search error: {e}")
        return None


# ==================== RICH LIST MANAGER ====================

class RichListManager:
    """Manage top address holders"""

    def __init__(self, node_url: str, db: ExplorerDatabase):
        """Initialize rich list manager"""
        self.node_url = node_url
        self.db = db
        self.rich_list_cache: Optional[List[Dict[str, Any]]] = None
        self.cache_timestamp: float = 0

    def get_rich_list(self, limit: int = 100, refresh: bool = False) -> List[Dict[str, Any]]:
        """Get top address holders"""
        cache_key = f"rich_list_{limit}"

        if not refresh:
            cached = self.db.get_cache(cache_key)
            if cached:
                return json.loads(cached)

        try:
            rich_list = self._calculate_rich_list(limit)

            if rich_list:
                self.db.set_cache(cache_key, json.dumps(rich_list), ttl=600)  # Cache for 10 minutes
                self.db.record_metric("richlist_top_holder", rich_list[0]["balance"])

            return rich_list
        except Exception as e:
            logger.error(f"Rich list error: {e}")
            return []

    def _calculate_rich_list(self, limit: int) -> List[Dict[str, Any]]:
        """Calculate rich list from blockchain"""
        try:
            blocks_response = requests.get(f"{self.node_url}/blocks?limit=10000", timeout=30)
            blocks_response.raise_for_status()
            blocks = blocks_response.json().get("blocks", [])

            # Aggregate all transactions
            address_balances: Dict[str, float] = defaultdict(float)

            for block in blocks:
                for tx in block.get("transactions", []):
                    # Handle sender
                    if tx.get("sender") and tx.get("sender") != "COINBASE":
                        address_balances[tx["sender"]] -= float(tx.get("amount", 0))
                        address_balances[tx["sender"]] -= float(tx.get("fee", 0))

                    # Handle recipient
                    if tx.get("recipient"):
                        address_balances[tx["recipient"]] += float(tx.get("amount", 0))

            # Sort by balance
            sorted_addresses = sorted(
                address_balances.items(),
                key=lambda x: x[1],
                reverse=True
            )

            # Build rich list with labels
            rich_list = []
            for rank, (address, balance) in enumerate(sorted_addresses[:limit], 1):
                label_data = self.db.get_address_label(address)
                rich_list.append({
                    "rank": rank,
                    "address": address,
                    "balance": balance,
                    "label": label_data.label if label_data else None,
                    "category": label_data.category if label_data else None,
                    "percentage_of_supply": (balance / sum(dict(address_balances).values())) * 100 if sum(address_balances.values()) > 0 else 0
                })

            return rich_list
        except Exception as e:
            logger.error(f"Error calculating rich list: {e}")
            return []


# ==================== CSV EXPORT ====================

class ExportManager:
    """Handle data exports"""

    def __init__(self, node_url: str):
        """Initialize export manager"""
        self.node_url = node_url

    def export_transactions_csv(self, address: str) -> Optional[str]:
        """Export address transactions as CSV"""
        try:
            history_response = requests.get(f"{self.node_url}/history/{address}", timeout=15)
            if history_response.status_code != 200:
                return None

            transactions = history_response.json().get("transactions", [])

            # Build CSV
            csv_lines = ["txid,timestamp,from,to,amount,fee,type"]

            for tx in transactions:
                timestamp = datetime.fromtimestamp(tx.get("timestamp", 0)).isoformat()
                txid = tx.get("txid", "")
                sender = tx.get("sender", "")
                recipient = tx.get("recipient", "")
                amount = tx.get("amount", 0)
                fee = tx.get("fee", 0)
                tx_type = tx.get("type", "transfer")

                csv_lines.append(
                    f'{txid},"{timestamp}",{sender},{recipient},{amount},{fee},{tx_type}'
                )

            return "\n".join(csv_lines)
        except Exception as e:
            logger.error(f"Export error: {e}")
            return None


# ==================== GOVERNANCE SERVICE ====================

class GovernanceService:
    """
    Governance data service for proposals and voting.
    Uses Cosmos SDK REST API endpoints.
    """

    def __init__(self, api_url: str, db: ExplorerDatabase):
        self.api_url = api_url.rstrip("/")
        self.db = db

    def get_proposals(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get list of governance proposals with optional status filter."""
        cache_key = f"proposals:{status or 'all'}:{limit}:{offset}"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            params = {
                "pagination.limit": str(limit),
                "pagination.offset": str(offset),
                "pagination.reverse": "true"
            }
            if status:
                # Map friendly status to Cosmos SDK status
                status_map = {
                    "voting": "PROPOSAL_STATUS_VOTING_PERIOD",
                    "passed": "PROPOSAL_STATUS_PASSED",
                    "rejected": "PROPOSAL_STATUS_REJECTED",
                    "deposit": "PROPOSAL_STATUS_DEPOSIT_PERIOD",
                    "failed": "PROPOSAL_STATUS_FAILED"
                }
                cosmos_status = status_map.get(status.lower(), status)
                params["proposal_status"] = cosmos_status

            response = requests.get(
                f"{self.api_url}/cosmos/gov/v1beta1/proposals",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            proposals = []
            for prop in data.get("proposals", []):
                proposals.append(self._format_proposal(prop))

            total = int(data.get("pagination", {}).get("total", len(proposals)))
            result = {"proposals": proposals, "total": total}
            self.db.set_cache(cache_key, json.dumps(result), ttl=30)
            return result
        except Exception as e:
            logger.error(f"Proposals fetch error: {e}")
            return {"proposals": [], "error": str(e)}

    def get_proposal(self, proposal_id: int) -> Dict[str, Any]:
        """Get single proposal details."""
        cache_key = f"proposal:{proposal_id}"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            response = requests.get(
                f"{self.api_url}/cosmos/gov/v1beta1/proposals/{proposal_id}",
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            proposal = self._format_proposal(data.get("proposal", {}))

            # Also fetch tally results
            tally_response = requests.get(
                f"{self.api_url}/cosmos/gov/v1beta1/proposals/{proposal_id}/tally",
                timeout=30
            )
            if tally_response.status_code == 200:
                tally_data = tally_response.json()
                proposal["tally"] = self._format_tally(tally_data.get("tally", {}))

            self.db.set_cache(cache_key, json.dumps(proposal), ttl=30)
            return proposal
        except Exception as e:
            logger.error(f"Proposal {proposal_id} fetch error: {e}")
            return {"error": str(e)}

    def get_proposal_votes(
        self,
        proposal_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get votes for a proposal."""
        cache_key = f"votes:{proposal_id}:{limit}:{offset}"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            params = {
                "pagination.limit": str(limit),
                "pagination.offset": str(offset)
            }
            response = requests.get(
                f"{self.api_url}/cosmos/gov/v1beta1/proposals/{proposal_id}/votes",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            votes = []
            for vote in data.get("votes", []):
                votes.append(self._format_vote(vote))

            total = int(data.get("pagination", {}).get("total", len(votes)))
            result = {"votes": votes, "total": total, "proposal_id": proposal_id}
            self.db.set_cache(cache_key, json.dumps(result), ttl=30)
            return result
        except Exception as e:
            logger.error(f"Votes fetch error for proposal {proposal_id}: {e}")
            return {"votes": [], "error": str(e)}

    def get_governance_params(self) -> Dict[str, Any]:
        """Get governance parameters."""
        cache_key = "gov_params"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            params = {}
            for param_type in ["deposit", "voting", "tallying"]:
                response = requests.get(
                    f"{self.api_url}/cosmos/gov/v1beta1/params/{param_type}",
                    timeout=15
                )
                if response.status_code == 200:
                    data = response.json()
                    params[param_type] = data.get(f"{param_type}_params", {})

            self.db.set_cache(cache_key, json.dumps(params), ttl=300)
            return params
        except Exception as e:
            logger.error(f"Governance params fetch error: {e}")
            return {"error": str(e)}

    def _format_proposal(self, prop: Dict[str, Any]) -> Dict[str, Any]:
        """Format proposal data for frontend."""
        content = prop.get("content", {})
        status = prop.get("status", "")
        status_friendly = self._friendly_status(status)

        # Parse timestamps
        submit_time = prop.get("submit_time")
        deposit_end = prop.get("deposit_end_time")
        voting_start = prop.get("voting_start_time")
        voting_end = prop.get("voting_end_time")

        # Get final tally result if available
        final_tally = prop.get("final_tally_result", {})

        return {
            "id": prop.get("proposal_id"),
            "title": content.get("title", "Untitled Proposal"),
            "description": content.get("description", ""),
            "type": content.get("@type", "").split(".")[-1],
            "status": status_friendly,
            "status_raw": status,
            "submit_time": submit_time,
            "deposit_end_time": deposit_end,
            "voting_start_time": voting_start,
            "voting_end_time": voting_end,
            "total_deposit": self._format_coins(prop.get("total_deposit", [])),
            "tally": self._format_tally(final_tally) if final_tally else None
        }

    def _format_tally(self, tally: Dict[str, Any]) -> Dict[str, Any]:
        """Format tally results."""
        yes = int(tally.get("yes", "0"))
        no = int(tally.get("no", "0"))
        abstain = int(tally.get("abstain", "0"))
        no_with_veto = int(tally.get("no_with_veto", "0"))
        total = yes + no + abstain + no_with_veto

        return {
            "yes": yes,
            "no": no,
            "abstain": abstain,
            "no_with_veto": no_with_veto,
            "total": total,
            "yes_percent": (yes / total * 100) if total > 0 else 0,
            "no_percent": (no / total * 100) if total > 0 else 0,
            "abstain_percent": (abstain / total * 100) if total > 0 else 0,
            "veto_percent": (no_with_veto / total * 100) if total > 0 else 0
        }

    def _format_vote(self, vote: Dict[str, Any]) -> Dict[str, Any]:
        """Format vote data."""
        option = vote.get("option", "")
        option_friendly = {
            "VOTE_OPTION_YES": "Yes",
            "VOTE_OPTION_NO": "No",
            "VOTE_OPTION_ABSTAIN": "Abstain",
            "VOTE_OPTION_NO_WITH_VETO": "No with Veto"
        }.get(option, option)

        return {
            "voter": vote.get("voter"),
            "option": option_friendly,
            "option_raw": option
        }

    def _friendly_status(self, status: str) -> str:
        """Convert Cosmos SDK status to friendly name."""
        status_map = {
            "PROPOSAL_STATUS_DEPOSIT_PERIOD": "Deposit",
            "PROPOSAL_STATUS_VOTING_PERIOD": "Voting",
            "PROPOSAL_STATUS_PASSED": "Passed",
            "PROPOSAL_STATUS_REJECTED": "Rejected",
            "PROPOSAL_STATUS_FAILED": "Failed"
        }
        return status_map.get(status, status)

    def _format_coins(self, coins: List[Dict[str, Any]]) -> str:
        """Format coin amounts."""
        if not coins:
            return "0"
        parts = []
        for coin in coins:
            amount = int(coin.get("amount", "0"))
            denom = coin.get("denom", config.DENOM)
            if denom == config.DENOM:
                aura_amount = amount / 1_000_000
                parts.append(f"{aura_amount:.6f} AURA")
            else:
                parts.append(f"{amount} {denom}")
        return ", ".join(parts) if parts else "0"


# ==================== STAKING SERVICE ====================

class StakingService:
    """
    Staking data service for delegations, rewards, and pool info.
    Uses Cosmos SDK REST API endpoints.
    """

    def __init__(self, api_url: str, db: ExplorerDatabase):
        self.api_url = api_url.rstrip("/")
        self.db = db

    def get_staking_pool(self) -> Dict[str, Any]:
        """Get staking pool information."""
        cache_key = "staking_pool"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            response = requests.get(
                f"{self.api_url}/cosmos/staking/v1beta1/pool",
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            pool = data.get("pool", {})

            bonded = int(pool.get("bonded_tokens", "0"))
            not_bonded = int(pool.get("not_bonded_tokens", "0"))
            total = bonded + not_bonded

            result = {
                "bonded_tokens": bonded,
                "not_bonded_tokens": not_bonded,
                "total_tokens": total,
                "bonded_ratio": (bonded / total * 100) if total > 0 else 0,
                "bonded_formatted": f"{bonded / 1_000_000:.2f} AURA",
                "not_bonded_formatted": f"{not_bonded / 1_000_000:.2f} AURA",
                "total_formatted": f"{total / 1_000_000:.2f} AURA"
            }

            self.db.set_cache(cache_key, json.dumps(result), ttl=60)
            return result
        except Exception as e:
            logger.error(f"Staking pool fetch error: {e}")
            return {"error": str(e)}

    def get_delegations(self, address: str) -> Dict[str, Any]:
        """Get delegations for an address."""
        cache_key = f"delegations:{address}"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            response = requests.get(
                f"{self.api_url}/cosmos/staking/v1beta1/delegations/{address}",
                params={"pagination.limit": "100"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            delegations = []
            total_staked = 0

            for item in data.get("delegation_responses", []):
                delegation = item.get("delegation", {})
                balance = item.get("balance", {})
                amount = int(balance.get("amount", "0"))
                total_staked += amount

                delegations.append({
                    "validator_address": delegation.get("validator_address"),
                    "delegator_address": delegation.get("delegator_address"),
                    "shares": delegation.get("shares"),
                    "amount": amount,
                    "amount_formatted": f"{amount / 1_000_000:.6f} AURA",
                    "denom": balance.get("denom", config.DENOM)
                })

            result = {
                "delegations": delegations,
                "total_staked": total_staked,
                "total_staked_formatted": f"{total_staked / 1_000_000:.6f} AURA",
                "count": len(delegations)
            }

            self.db.set_cache(cache_key, json.dumps(result), ttl=30)
            return result
        except Exception as e:
            logger.error(f"Delegations fetch error for {address}: {e}")
            return {"delegations": [], "error": str(e)}

    def get_unbonding_delegations(self, address: str) -> Dict[str, Any]:
        """Get unbonding delegations for an address."""
        cache_key = f"unbonding:{address}"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            response = requests.get(
                f"{self.api_url}/cosmos/staking/v1beta1/delegators/{address}/unbonding_delegations",
                params={"pagination.limit": "100"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            unbondings = []
            total_unbonding = 0

            for item in data.get("unbonding_responses", []):
                validator = item.get("validator_address")
                for entry in item.get("entries", []):
                    balance = int(entry.get("balance", "0"))
                    total_unbonding += balance
                    unbondings.append({
                        "validator_address": validator,
                        "delegator_address": item.get("delegator_address"),
                        "creation_height": entry.get("creation_height"),
                        "completion_time": entry.get("completion_time"),
                        "initial_balance": int(entry.get("initial_balance", "0")),
                        "balance": balance,
                        "balance_formatted": f"{balance / 1_000_000:.6f} AURA"
                    })

            result = {
                "unbonding_delegations": unbondings,
                "total_unbonding": total_unbonding,
                "total_unbonding_formatted": f"{total_unbonding / 1_000_000:.6f} AURA",
                "count": len(unbondings)
            }

            self.db.set_cache(cache_key, json.dumps(result), ttl=30)
            return result
        except Exception as e:
            logger.error(f"Unbonding fetch error for {address}: {e}")
            return {"unbonding_delegations": [], "error": str(e)}

    def get_rewards(self, address: str) -> Dict[str, Any]:
        """Get pending rewards for an address."""
        cache_key = f"rewards:{address}"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            response = requests.get(
                f"{self.api_url}/cosmos/distribution/v1beta1/delegators/{address}/rewards",
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            rewards_by_validator = []
            for item in data.get("rewards", []):
                validator_rewards = []
                for reward in item.get("reward", []):
                    amount = float(reward.get("amount", "0"))
                    validator_rewards.append({
                        "amount": amount,
                        "denom": reward.get("denom", config.DENOM),
                        "amount_formatted": f"{amount / 1_000_000:.6f} AURA"
                    })
                rewards_by_validator.append({
                    "validator_address": item.get("validator_address"),
                    "rewards": validator_rewards
                })

            # Total rewards
            total_rewards = []
            total_amount = 0
            for reward in data.get("total", []):
                amount = float(reward.get("amount", "0"))
                total_amount += amount
                total_rewards.append({
                    "amount": amount,
                    "denom": reward.get("denom", config.DENOM),
                    "amount_formatted": f"{amount / 1_000_000:.6f} AURA"
                })

            result = {
                "rewards_by_validator": rewards_by_validator,
                "total_rewards": total_rewards,
                "total_amount": total_amount,
                "total_formatted": f"{total_amount / 1_000_000:.6f} AURA"
            }

            self.db.set_cache(cache_key, json.dumps(result), ttl=30)
            return result
        except Exception as e:
            logger.error(f"Rewards fetch error for {address}: {e}")
            return {"rewards_by_validator": [], "total_rewards": [], "error": str(e)}

    def get_staking_params(self) -> Dict[str, Any]:
        """Get staking parameters."""
        cache_key = "staking_params"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            response = requests.get(
                f"{self.api_url}/cosmos/staking/v1beta1/params",
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            params = data.get("params", {})

            result = {
                "unbonding_time": params.get("unbonding_time"),
                "max_validators": int(params.get("max_validators", 0)),
                "max_entries": int(params.get("max_entries", 0)),
                "historical_entries": int(params.get("historical_entries", 0)),
                "bond_denom": params.get("bond_denom", config.DENOM)
            }

            self.db.set_cache(cache_key, json.dumps(result), ttl=300)
            return result
        except Exception as e:
            logger.error(f"Staking params fetch error: {e}")
            return {"error": str(e)}


# ==================== CORE DATA SERVICE ====================

class BlockchainDataService:
    """
    Provides explorer-specific data aggregates for the frontend.
    Handles pagination, filtering, and caching for blocks, transactions,
    validators, and summary statistics.
    """

    def __init__(self, node_url: str, api_url: str, db: ExplorerDatabase):
        self.node_url = node_url.rstrip("/")
        self.api_url = api_url.rstrip("/")
        self.db = db
        self.max_limit = 50

    # ------- Public API -------

    def get_blocks(self, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """Return paginated block metadata for dashboard views."""
        limit, offset = self._normalize_pagination(limit, offset)
        cache_key = f"blocks:{limit}:{offset}"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            latest_height = self._get_latest_height()
            if latest_height == 0:
                return {"blocks": [], "latest_height": 0}

            end_height = max(1, latest_height - offset)
            start_height = max(1, end_height - limit + 1)
            metas = self._fetch_block_metas(start_height, end_height)
            blocks = [
                self._format_block_meta(meta)
                for meta in sorted(
                    metas,
                    key=lambda m: int(m["header"]["height"]),
                    reverse=True
                )
            ]

            result = {"blocks": blocks, "latest_height": latest_height}
            self.db.set_cache(cache_key, json.dumps(result), ttl=5)
            return result
        except Exception as e:
            logger.error(f"Block fetch error: {e}")
            return {"blocks": [], "error": str(e)}

    def get_transactions(
        self,
        limit: int = 20,
        offset: int = 0,
        tx_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return paginated transaction list with optional filters."""
        limit, offset = self._normalize_pagination(limit, offset)
        tx_type_key = (tx_type or "").strip().lower()
        status_key = (status or "").strip().lower()

        cache_key = f"txs:{limit}:{offset}:{tx_type_key}:{status_key}"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            params = {
                "events": "tx.height>0",
                "pagination.limit": str(limit),
                "pagination.offset": str(offset),
                "order_by": "ORDER_BY_DESC"
            }
            response = requests.get(
                f"{self.api_url}/cosmos/tx/v1beta1/txs",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            formatted: List[Dict[str, Any]] = []
            for raw in data.get("tx_responses", []):
                tx_entry = self._format_transaction(raw)
                if tx_type_key and tx_entry["type_key"] != tx_type_key:
                    continue
                if status_key and tx_entry["status"] != status_key:
                    continue
                formatted.append(tx_entry)

            total = int(data.get("pagination", {}).get("total", len(formatted)))
            result = {"transactions": formatted, "total": total}
            self.db.set_cache(cache_key, json.dumps(result), ttl=5)
            return result
        except Exception as e:
            logger.warning(f"Transaction fetch error (REST), falling back to RPC: {e}")

        try:
            page = max(1, (offset // limit) + 1)
            rpc_params = {
                "query": '"tx.height>0"',
                "prove": "false",
                "page": str(page),
                "per_page": str(limit),
                "order_by": '"desc"'
            }
            rpc_response = requests.get(
                f"{self.node_url}/tx_search",
                params=rpc_params,
                timeout=30
            )
            rpc_response.raise_for_status()
            rpc_data = rpc_response.json().get("result", {})

            formatted: List[Dict[str, Any]] = []
            for raw in rpc_data.get("txs", []):
                tx_hash = raw.get("hash")
                if not tx_hash:
                    continue
                try:
                    tx_detail = requests.get(
                        f"{self.api_url}/cosmos/tx/v1beta1/txs/{tx_hash}",
                        timeout=30
                    )
                    tx_detail.raise_for_status()
                    tx_response = tx_detail.json().get("tx_response", {})
                    formatted.append(self._format_transaction(tx_response))
                except Exception as tx_err:
                    logger.error(f"Transaction detail fetch error ({tx_hash}): {tx_err}")
                    formatted.append({
                        "hash": tx_hash,
                        "height": int(raw.get("height", 0)),
                        "type": "Unknown",
                        "type_key": "unknown",
                        "from": None,
                        "to": None,
                        "amount": None,
                        "status": "success" if raw.get("tx_result", {}).get("code", 0) == 0 else "failed",
                        "fee": None,
                        "time": None
                    })

            total = int(rpc_data.get("total_count", len(formatted)))
            result = {"transactions": formatted, "total": total}
            self.db.set_cache(cache_key, json.dumps(result), ttl=5)
            return result
        except Exception as rpc_error:
            logger.error(f"Transaction fetch error (RPC fallback): {rpc_error}")
            return {"transactions": [], "error": str(rpc_error)}

    def get_validators(self, sort_by: str = "voting_power") -> Dict[str, Any]:
        """Return validator list sorted by provided metric."""
        sort_key = sort_by if sort_by in {"voting_power", "commission", "uptime"} else "voting_power"
        cache_key = f"validators:{sort_key}"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            params = {
                "status": "BOND_STATUS_BONDED",
                "pagination.limit": "200"
            }
            response = requests.get(
                f"{self.api_url}/cosmos/staking/v1beta1/validators",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            validators = []

            for item in response.json().get("validators", []):
                commission_rate = float(item.get("commission", {})
                                        .get("commission_rates", {})
                                        .get("rate", "0"))
                tokens = int(item.get("tokens", "0"))
                jailed = item.get("jailed", False)
                status = item.get("status", "")

                validators.append({
                    "moniker": item.get("description", {}).get("moniker", "Unknown"),
                    "address": item.get("operator_address"),
                    "consensus_address": item.get("consensus_pubkey", {}).get("key"),
                    "voting_power": tokens,
                    "commission": commission_rate,
                    "uptime": 0.0 if jailed else 0.99,
                    "status": "active" if status == "BOND_STATUS_BONDED" else "inactive"
                })

            validators.sort(key=lambda v: v[sort_key], reverse=True)
            result = {"validators": validators, "count": len(validators)}
            self.db.set_cache(cache_key, json.dumps(result), ttl=30)
            return result
        except Exception as e:
            logger.warning(f"Validator fetch error (REST), falling back to RPC: {e}")

        try:
            rpc_params = {"page": "1", "per_page": "200"}
            rpc_response = requests.get(
                f"{self.node_url}/validators",
                params=rpc_params,
                timeout=15
            )
            rpc_response.raise_for_status()
            validators = []

            for item in rpc_response.json().get("result", {}).get("validators", []):
                voting_power = int(item.get("voting_power", 0))
                consensus_addr = item.get("address")
                validators.append({
                    "moniker": consensus_addr or "Unknown",
                    "address": None,
                    "consensus_address": consensus_addr,
                    "voting_power": voting_power,
                    "commission": 0.0,
                    "uptime": 0.99 if voting_power > 0 else 0.0,
                    "status": "active" if voting_power > 0 else "inactive"
                })

            validators.sort(key=lambda v: v[sort_key], reverse=True)
            result = {"validators": validators, "count": len(validators)}
            self.db.set_cache(cache_key, json.dumps(result), ttl=30)
            return result
        except Exception as rpc_error:
            logger.error(f"Validator fetch error (RPC fallback): {rpc_error}")
            return {"validators": [], "error": str(rpc_error)}

    def get_core_stats(self) -> Dict[str, Any]:
        """Return base stats for quick dashboard cards."""
        cache_key = "core_stats"
        cached = self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            latest_height = self._get_latest_height()
            latest_block = None
            blocks = self.get_blocks(limit=1, offset=0).get("blocks", [])
            if blocks:
                latest_block = blocks[0]

            total_txs = self._get_total_transactions()
            validator_count = self.get_validators().get("count", 0)

            stats = {
                "latest_block": latest_block["height"] if latest_block else latest_height,
                "latest_block_time": latest_block["time"] if latest_block else None,
                "total_txs": total_txs,
                "active_validators": validator_count
            }
            self.db.set_cache(cache_key, json.dumps(stats), ttl=10)
            return stats
        except Exception as e:
            logger.error(f"Stats fetch error: {e}")
            return {"latest_block": 0, "total_txs": 0, "active_validators": 0, "error": str(e)}

    # ------- Helpers -------

    def _normalize_pagination(self, limit: int, offset: int) -> Tuple[int, int]:
        limit = max(1, min(self.max_limit, limit or 20))
        offset = max(0, offset or 0)
        return limit, offset

    def _get_latest_height(self) -> int:
        try:
            response = requests.get(f"{self.node_url}/status", timeout=15)
            response.raise_for_status()
            return int(response.json()
                       .get("result", {})
                       .get("sync_info", {})
                       .get("latest_block_height", 0))
        except Exception as e:
            logger.error(f"Status fetch error: {e}")
            return 0

    def _fetch_block_metas(self, start_height: int, end_height: int) -> List[Dict[str, Any]]:
        metas: List[Dict[str, Any]] = []
        cursor = end_height
        while cursor >= start_height:
            chunk_end = cursor
            chunk_start = max(start_height, chunk_end - 19)
            try:
                response = requests.get(
                    f"{self.node_url}/blockchain",
                    params={"minHeight": str(chunk_start), "maxHeight": str(chunk_end)},
                    timeout=30
                )
                response.raise_for_status()
                chunk = response.json().get("result", {}).get("block_metas", [])
                metas.extend(chunk)
            except Exception as e:
                logger.error(f"Block meta fetch error ({chunk_start}-{chunk_end}): {e}")
                break
            cursor = chunk_start - 1
        return metas

    def _format_block_meta(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        header = meta.get("header", {})
        height = int(header.get("height", 0))
        timestamp_str = header.get("time")
        timestamp = timestamp_str
        if timestamp_str:
            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                timestamp = dt.isoformat()
            except Exception:
                timestamp = timestamp_str

        return {
            "height": height,
            "hash": meta.get("block_id", {}).get("hash"),
            "time": timestamp,
            "proposer": header.get("proposer_address"),
            "num_txs": int(meta.get("num_txs", 0)),
            "size": meta.get("block_size")
        }

    def _format_transaction(self, tx_response: Dict[str, Any]) -> Dict[str, Any]:
        tx_hash = tx_response.get("txhash") or tx_response.get("hash")
        timestamp = tx_response.get("timestamp")
        code = tx_response.get("code", 0)
        status = "success" if code == 0 else "failed"
        raw_tx = tx_response.get("tx", {})
        tx_body = raw_tx.get("body") if isinstance(raw_tx, dict) else {}
        if not isinstance(tx_body, dict):
            tx_body = {}
        messages = tx_body.get("messages", [])

        msg_type = messages[0].get("@type", "") if messages else ""
        friendly_type = self._friendly_type(msg_type)
        type_key = self._type_key(friendly_type)
        amount = self._extract_amount(messages)
        sender, recipient = self._extract_addresses(messages)

        return {
            "hash": tx_hash,
            "height": int(tx_response.get("height", 0)),
            "type": friendly_type,
            "type_key": type_key,
            "from": sender,
            "to": recipient,
            "amount": amount,
            "status": status,
            "fee": self._format_fee(raw_tx),
            "time": timestamp
        }

    def _extract_amount(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        for msg in messages:
            value = msg.get("amount") or msg.get("token") or msg.get("value")
            if isinstance(value, list) and value:
                coin = value[0]
                denom = coin.get("denom", config.DENOM)
                return self._format_coin(coin.get("amount", "0"), denom)
            if isinstance(value, dict) and value.get("denom"):
                return self._format_coin(value.get("amount", "0"), value.get("denom"))
        return None

    def _extract_addresses(self, messages: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
        sender = None
        recipient = None
        for msg in messages:
            sender = sender or msg.get("from_address") or msg.get("sender") or msg.get("signer")
            recipient = recipient or msg.get("to_address") or msg.get("recipient")
            if sender and recipient:
                break
        return sender, recipient

    def _format_fee(self, raw_tx: Dict[str, Any]) -> Optional[str]:
        if not isinstance(raw_tx, dict):
            return None
        fee = raw_tx.get("auth_info", {}).get("fee", {})
        if not isinstance(fee, dict):
            return None
        amounts = fee.get("amount", [])
        if not amounts:
            return None
        coin = amounts[0]
        denom = coin.get("denom", config.DENOM)
        return self._format_coin(coin.get("amount", "0"), denom)

    def _friendly_type(self, raw_type: str) -> str:
        """Return human-friendly transaction type."""
        if not raw_type:
            return "Unknown"
        clean = raw_type.split(".")[-1]
        return clean or "Unknown"

    def _type_key(self, friendly_type: str) -> str:
        key = friendly_type.replace("Msg", "", 1) if friendly_type.lower().startswith("msg") else friendly_type
        normalized = []
        for idx, ch in enumerate(key):
            if idx > 0 and ch.isupper():
                normalized.append("-")
            normalized.append(ch.lower())
        return f"msg-{''.join(normalized)}"

    def _format_coin(self, amount: str, denom: str) -> str:
        try:
            value = int(amount)
            if denom == config.DENOM and value >= 0:
                aura_amount = value / 1_000_000
                return f"{aura_amount:.6f} AURA"
            return f"{value} {denom}"
        except Exception:
            return f"{amount} {denom}"

    def _get_total_transactions(self) -> int:
        try:
            response = requests.get(
                f"{self.api_url}/cosmos/tx/v1beta1/txs",
                params={"events": "tx.height>0", "pagination.limit": "1"},
                timeout=15
            )
            response.raise_for_status()
            total = response.json().get("pagination", {}).get("total")
            return int(total) if total is not None else 0
        except Exception as e:
            logger.warning(f"Total tx fetch error (REST), falling back to RPC: {e}")

        try:
            rpc_response = requests.get(
                f"{self.node_url}/tx_search",
                params={
                    "query": '"tx.height>0"',
                    "prove": "false",
                    "page": "1",
                    "per_page": "1",
                    "order_by": '"desc"'
                },
                timeout=15
            )
            rpc_response.raise_for_status()
            total = rpc_response.json().get("result", {}).get("total_count")
            return int(total) if total is not None else 0
        except Exception as rpc_error:
            logger.error(f"Total tx fetch error (RPC fallback): {rpc_error}")
            return 0


# ==================== FLASK APP ====================

app = Flask(__name__)
CORS(app)
sock = Sock(app)

# ==================== SWAGGER CONFIGURATION ====================

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec',
            "route": '/apispec.json',
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/api/docs"
}

swagger_template = {
    "info": {
        "title": "AURA Blockchain Explorer API",
        "description": "API for exploring the AURA blockchain - blocks, transactions, accounts, staking, governance, and IBC",
        "version": "1.0.0",
        "contact": {
            "name": "AURA Blockchain",
            "url": "https://aurablockchain.org"
        }
    },
    "host": "explorer.aurablockchain.org",
    "basePath": "/",
    "schemes": ["https", "http"],
    "tags": [
        {"name": "Health", "description": "Health check endpoints"},
        {"name": "Blocks", "description": "Block data endpoints"},
        {"name": "Transactions", "description": "Transaction endpoints"},
        {"name": "Accounts", "description": "Account/address endpoints"},
        {"name": "Staking", "description": "Staking and delegation endpoints"},
        {"name": "Governance", "description": "Governance proposal endpoints"},
        {"name": "Validators", "description": "Validator endpoints"},
        {"name": "IBC", "description": "Inter-Blockchain Communication endpoints"},
        {"name": "Analytics", "description": "Analytics and statistics endpoints"},
        {"name": "Search", "description": "Search and discovery endpoints"},
        {"name": "RichList", "description": "Top holders endpoints"},
        {"name": "Supply", "description": "Token supply endpoints"},
        {"name": "Export", "description": "Data export endpoints"}
    ]
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

# Initialize components with AURA configuration
NODE_URL = config.NODE_RPC_URL
API_URL = getattr(config, "NODE_API_URL", "http://localhost:1317")
DB_PATH = config.DB_PATH

db = ExplorerDatabase(DB_PATH)
analytics = AnalyticsEngine(NODE_URL, db)
search_engine = SearchEngine(NODE_URL, db)
rich_list = RichListManager(NODE_URL, db)
export_manager = ExportManager(NODE_URL)
data_service = BlockchainDataService(NODE_URL, API_URL, db)
governance_service = GovernanceService(API_URL, db)
staking_service = StakingService(API_URL, db)

# WebSocket connections for real-time updates
ws_clients: Set[Any] = set()
ws_lock = threading.RLock()


# ==================== ANALYTICS ENDPOINTS ====================

@app.route("/api/analytics/hashrate", methods=["GET"])
def get_hashrate_endpoint():
    """
    Get network hashrate
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Network hashrate information
        schema:
          type: object
          properties:
            hashrate:
              type: number
              description: Estimated network hashrate
            difficulty:
              type: number
              description: Current network difficulty
            block_height:
              type: integer
              description: Current block height
            unit:
              type: string
              description: Unit of measurement
            timestamp:
              type: number
              description: Unix timestamp
      500:
        description: Server error
    """
    return jsonify(analytics.get_network_hashrate())


@app.route("/api/analytics/tx-volume", methods=["GET"])
def get_tx_volume_endpoint():
    """
    Get transaction volume
    ---
    tags:
      - Analytics
    parameters:
      - name: period
        in: query
        type: string
        default: "24h"
        enum: ["24h", "7d", "30d"]
        description: Time period for volume calculation
    responses:
      200:
        description: Transaction volume metrics
        schema:
          type: object
          properties:
            period:
              type: string
              description: Time period
            total_transactions:
              type: integer
              description: Total transaction count
            unique_transactions:
              type: integer
              description: Unique transaction count
            average_tx_per_block:
              type: number
              description: Average transactions per block
            total_fees_collected:
              type: number
              description: Total fees collected
            timestamp:
              type: number
              description: Unix timestamp
      500:
        description: Server error
    """
    period = request.args.get("period", "24h")
    return jsonify(analytics.get_transaction_volume(period))


@app.route("/api/analytics/active-addresses", methods=["GET"])
def get_active_addresses_endpoint():
    """
    Get active addresses count
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Active addresses count
        schema:
          type: object
          properties:
            total_unique_addresses:
              type: integer
              description: Total unique active addresses
            timestamp:
              type: number
              description: Unix timestamp
      500:
        description: Server error
    """
    return jsonify(analytics.get_active_addresses())


@app.route("/api/analytics/block-time", methods=["GET"])
def get_block_time_endpoint():
    """
    Get average block time
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Average block time information
        schema:
          type: object
          properties:
            average_block_time_seconds:
              type: number
              description: Average time between blocks in seconds
            blocks_sampled:
              type: integer
              description: Number of blocks used for calculation
            timestamp:
              type: number
              description: Unix timestamp
      500:
        description: Server error
    """
    return jsonify(analytics.get_average_block_time())


@app.route("/api/analytics/mempool", methods=["GET"])
def get_mempool_endpoint():
    """
    Get mempool size
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Mempool (pending transactions) information
        schema:
          type: object
          properties:
            pending_transactions:
              type: integer
              description: Number of pending transactions
            total_value:
              type: number
              description: Total value of pending transactions
            total_fees:
              type: number
              description: Total fees of pending transactions
            avg_fee:
              type: number
              description: Average fee per transaction
            timestamp:
              type: number
              description: Unix timestamp
      500:
        description: Server error
    """
    return jsonify(analytics.get_mempool_size())


@app.route("/api/analytics/difficulty", methods=["GET"])
def get_difficulty_endpoint():
    """
    Get network difficulty
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Network difficulty information
        schema:
          type: object
          properties:
            current_difficulty:
              type: number
              description: Current network difficulty
            timestamp:
              type: number
              description: Unix timestamp
      500:
        description: Server error
    """
    return jsonify(analytics.get_network_difficulty())


@app.route("/api/analytics/dashboard", methods=["GET"])
def get_analytics_dashboard():
    """
    Get all analytics for dashboard
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Complete analytics dashboard data
        schema:
          type: object
          properties:
            hashrate:
              type: object
              description: Network hashrate data
            transaction_volume:
              type: object
              description: Transaction volume data
            active_addresses:
              type: object
              description: Active addresses data
            average_block_time:
              type: object
              description: Block time data
            mempool:
              type: object
              description: Mempool data
            difficulty:
              type: object
              description: Network difficulty data
            timestamp:
              type: number
              description: Unix timestamp
      500:
        description: Server error
    """
    return jsonify({
        "hashrate": analytics.get_network_hashrate(),
        "transaction_volume": analytics.get_transaction_volume(),
        "active_addresses": analytics.get_active_addresses(),
        "average_block_time": analytics.get_average_block_time(),
        "mempool": analytics.get_mempool_size(),
        "difficulty": analytics.get_network_difficulty(),
        "timestamp": time.time()
    })


# ==================== CORE DATA ENDPOINTS ====================

@app.route("/api/blocks", methods=["GET"])
def get_blocks_endpoint():
    """
    Get paginated blocks for explorer dashboard
    ---
    tags:
      - Blocks
    parameters:
      - name: limit
        in: query
        type: integer
        default: 20
        description: Number of blocks to return (max 50)
      - name: offset
        in: query
        type: integer
        default: 0
        description: Offset for pagination
    responses:
      200:
        description: List of recent blocks
        schema:
          type: object
          properties:
            blocks:
              type: array
              items:
                type: object
                properties:
                  height:
                    type: integer
                    description: Block height
                  hash:
                    type: string
                    description: Block hash
                  time:
                    type: string
                    description: Block timestamp (ISO format)
                  proposer:
                    type: string
                    description: Proposer address
                  num_txs:
                    type: integer
                    description: Number of transactions in block
                  size:
                    type: integer
                    description: Block size in bytes
            latest_height:
              type: integer
              description: Latest block height on chain
      500:
        description: Server error
    """
    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", 0, type=int)
    return jsonify(data_service.get_blocks(limit, offset))


@app.route("/api/transactions", methods=["GET"])
def get_transactions_endpoint():
    """
    Get paginated transactions with filtering
    ---
    tags:
      - Transactions
    parameters:
      - name: limit
        in: query
        type: integer
        default: 20
        description: Number of transactions to return (max 50)
      - name: offset
        in: query
        type: integer
        default: 0
        description: Offset for pagination
      - name: type
        in: query
        type: string
        description: Filter by transaction type (e.g., msg-send, msg-delegate)
      - name: status
        in: query
        type: string
        enum: ["success", "failed"]
        description: Filter by transaction status
    responses:
      200:
        description: List of transactions
        schema:
          type: object
          properties:
            transactions:
              type: array
              items:
                type: object
                properties:
                  hash:
                    type: string
                    description: Transaction hash
                  height:
                    type: integer
                    description: Block height
                  type:
                    type: string
                    description: Transaction type (friendly name)
                  type_key:
                    type: string
                    description: Transaction type key
                  from:
                    type: string
                    description: Sender address
                  to:
                    type: string
                    description: Recipient address
                  amount:
                    type: string
                    description: Transaction amount formatted
                  status:
                    type: string
                    description: Transaction status (success/failed)
                  fee:
                    type: string
                    description: Transaction fee formatted
                  time:
                    type: string
                    description: Transaction timestamp
            total:
              type: integer
              description: Total transaction count
      500:
        description: Server error
    """
    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", 0, type=int)
    tx_type = request.args.get("type")
    status = request.args.get("status")
    return jsonify(data_service.get_transactions(limit, offset, tx_type, status))


@app.route("/api/validators", methods=["GET"])
def get_validators_endpoint():
    """
    Get validator list for explorer
    ---
    tags:
      - Validators
    parameters:
      - name: sort
        in: query
        type: string
        default: "voting_power"
        enum: ["voting_power", "commission", "uptime"]
        description: Sort validators by field
    responses:
      200:
        description: List of validators
        schema:
          type: object
          properties:
            validators:
              type: array
              items:
                type: object
                properties:
                  moniker:
                    type: string
                    description: Validator moniker/name
                  address:
                    type: string
                    description: Operator address
                  consensus_address:
                    type: string
                    description: Consensus public key
                  voting_power:
                    type: integer
                    description: Voting power in tokens
                  commission:
                    type: number
                    description: Commission rate (0-1)
                  uptime:
                    type: number
                    description: Uptime percentage (0-1)
                  status:
                    type: string
                    description: Validator status (active/inactive)
            count:
              type: integer
              description: Total validator count
      500:
        description: Server error
    """
    sort_by = request.args.get("sort", "voting_power")
    return jsonify(data_service.get_validators(sort_by))


@app.route("/api/stats", methods=["GET"])
def get_stats_endpoint():
    """
    Get quick stats for dashboard
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Quick dashboard statistics
        schema:
          type: object
          properties:
            latest_block:
              type: integer
              description: Latest block height
            latest_block_time:
              type: string
              description: Latest block timestamp
            avg_block_time:
              type: number
              description: Average block time in seconds
            total_txs:
              type: integer
              description: Total transaction count
            active_validators:
              type: integer
              description: Active validator count
      500:
        description: Server error
    """
    core_stats = data_service.get_core_stats()
    avg_block = analytics.get_average_block_time()
    return jsonify({
        "latest_block": core_stats.get("latest_block"),
        "latest_block_time": core_stats.get("latest_block_time"),
        "avg_block_time": avg_block.get("average_block_time_seconds"),
        "total_txs": core_stats.get("total_txs"),
        "active_validators": core_stats.get("active_validators")
    })


# ==================== ACCOUNT ENDPOINTS ====================

def _fetch_with_retry(url, max_retries=3, timeout=15):
    """Fetch URL with retry logic for REST API connection issues."""
    import time as time_module
    for attempt in range(max_retries):
        try:
            response = requests.get(
                url,
                headers={"Connection": "close"},
                timeout=timeout
            )
            return response
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
            if attempt < max_retries - 1:
                time_module.sleep(0.5)
                continue
            raise e
    return None


@app.route("/api/account/<address>", methods=["GET"])
def api_account(address):
    """
    Get account details including balances and account info
    ---
    tags:
      - Accounts
    parameters:
      - name: address
        in: path
        type: string
        required: true
        description: AURA address (bech32 format, e.g., aura1...)
    responses:
      200:
        description: Account details
        schema:
          type: object
          properties:
            address:
              type: string
              description: Account address
            balances:
              type: array
              items:
                type: object
                properties:
                  denom:
                    type: string
                    description: Token denomination
                  amount:
                    type: string
                    description: Raw amount
                  amount_formatted:
                    type: string
                    description: Formatted amount (e.g., "100.000000 AURA")
            account_number:
              type: string
              description: Account number
            sequence:
              type: string
              description: Account sequence (nonce)
            account_type:
              type: string
              description: Account type (BaseAccount, VestingAccount, etc.)
      500:
        description: Server error
    """
    try:
        account_type = "Unknown"
        account_number = None
        sequence = None

        # Fetch account info from auth module with retry
        try:
            account_response = _fetch_with_retry(
                f"{config.NODE_API_URL}/cosmos/auth/v1beta1/accounts/{address}"
            )
            if account_response and account_response.status_code == 200:
                result = account_response.json()
                account = result.get("account", {})
                account_type = account.get("@type", "").split(".")[-1]
                account_number = account.get("account_number")
                sequence = account.get("sequence")
                # Handle nested base_account for vesting accounts
                if account.get("base_account"):
                    base = account["base_account"]
                    account_number = base.get("account_number")
                    sequence = base.get("sequence")
        except Exception as auth_err:
            logger.warning(f"Account info fetch failed: {auth_err}")

        # Fetch balances with retry
        balances = []
        try:
            balance_response = _fetch_with_retry(
                f"{config.NODE_API_URL}/cosmos/bank/v1beta1/balances/{address}"
            )
            if balance_response and balance_response.status_code == 200:
                balance_data = balance_response.json()
                balances = balance_data.get("balances", [])
        except Exception as bal_err:
            logger.warning(f"Balance fetch failed: {bal_err}")

        # Format balances with AURA conversion
        formatted_balances = []
        for bal in balances:
            denom = bal.get("denom", "")
            amount = int(bal.get("amount", "0"))
            formatted = {
                "denom": denom,
                "amount": str(amount)
            }
            if denom == config.DENOM:
                formatted["amount_formatted"] = f"{amount / 1_000_000:.6f} AURA"
            formatted_balances.append(formatted)

        return jsonify({
            "address": address,
            "balances": formatted_balances,
            "account_number": account_number,
            "sequence": sequence,
            "account_type": account_type
        })
    except Exception as e:
        logger.error(f"Account fetch error for {address}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/account/<address>/transactions", methods=["GET"])
def api_account_transactions(address):
    """
    Get transaction history for an account
    ---
    tags:
      - Accounts
    parameters:
      - name: address
        in: path
        type: string
        required: true
        description: AURA address (bech32 format)
      - name: page
        in: query
        type: integer
        default: 1
        description: Page number
      - name: limit
        in: query
        type: integer
        default: 20
        description: Number of transactions per page (max 100)
    responses:
      200:
        description: Account transaction history
        schema:
          type: object
          properties:
            address:
              type: string
              description: Account address
            transactions:
              type: array
              items:
                type: object
                properties:
                  hash:
                    type: string
                    description: Transaction hash
                  height:
                    type: integer
                    description: Block height
                  timestamp:
                    type: string
                    description: Transaction timestamp
                  type:
                    type: string
                    description: Transaction type
                  status:
                    type: string
                    description: Transaction status
            total:
              type: integer
              description: Total transaction count
            page:
              type: integer
              description: Current page
            limit:
              type: integer
              description: Page size
      500:
        description: Server error
    """
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 20, type=int)
        limit = min(limit, 100)  # Cap at 100

        # Search for transactions where address is sender
        sender_params = {
            "query": f'"message.sender=\'{address}\'"',
            "prove": "false",
            "page": str(page),
            "per_page": str(limit),
            "order_by": '"desc"'
        }
        sender_response = requests.get(
            f"{config.NODE_RPC_URL}/tx_search",
            params=sender_params,
            timeout=30
        )

        transactions = []
        total_count = 0

        if sender_response.status_code == 200:
            result = sender_response.json().get("result", {})
            total_count = int(result.get("total_count", "0"))

            for tx in result.get("txs", []):
                tx_hash = tx.get("hash", "")
                height = int(tx.get("height", "0"))
                tx_result = tx.get("tx_result", {})
                code = tx_result.get("code", 0)
                status = "success" if code == 0 else "failed"

                # Get timestamp from block
                timestamp = None
                try:
                    block_resp = requests.get(
                        f"{config.NODE_RPC_URL}/block?height={height}",
                        timeout=10
                    )
                    if block_resp.status_code == 200:
                        block_data = block_resp.json().get("result", {}).get("block", {})
                        timestamp = block_data.get("header", {}).get("time")
                except Exception:
                    pass

                # Parse transaction type from events
                tx_type = "Unknown"
                events = tx_result.get("events", [])
                for event in events:
                    if event.get("type") == "message":
                        for attr in event.get("attributes", []):
                            if attr.get("key") == "action" or attr.get("key") == "YWN0aW9u":
                                action = attr.get("value", "")
                                # Handle base64 encoded values
                                if action:
                                    try:
                                        import base64
                                        decoded = base64.b64decode(action).decode("utf-8")
                                        tx_type = decoded.split(".")[-1]
                                    except Exception:
                                        tx_type = action.split(".")[-1]
                                break

                transactions.append({
                    "hash": tx_hash,
                    "height": height,
                    "timestamp": timestamp,
                    "type": tx_type,
                    "status": status
                })

        return jsonify({
            "address": address,
            "transactions": transactions,
            "total": total_count,
            "page": page,
            "limit": limit
        })
    except Exception as e:
        logger.error(f"Account transactions fetch error for {address}: {e}")
        return jsonify({"error": str(e)}), 500


# ==================== BLOCK DETAIL ENDPOINT ====================

@app.route("/api/blocks/<int:height>", methods=["GET"])
def api_block_by_height(height):
    """
    Get specific block by height
    ---
    tags:
      - Blocks
    parameters:
      - name: height
        in: path
        type: integer
        required: true
        description: Block height
    responses:
      200:
        description: Block details
        schema:
          type: object
          properties:
            height:
              type: integer
              description: Block height
            hash:
              type: string
              description: Block hash
            time:
              type: string
              description: Block timestamp
            proposer:
              type: string
              description: Proposer consensus address
            proposer_moniker:
              type: string
              description: Proposer moniker (if available)
            num_txs:
              type: integer
              description: Number of transactions
            transactions:
              type: array
              items:
                type: object
                properties:
                  hash:
                    type: string
                    description: Transaction hash
            chain_id:
              type: string
              description: Chain ID
            app_hash:
              type: string
              description: Application hash
            last_block_hash:
              type: string
              description: Previous block hash
      404:
        description: Block not found
      500:
        description: Server error
    """
    try:
        # Fetch block from RPC
        response = requests.get(
            f"{config.NODE_RPC_URL}/block?height={height}",
            timeout=15
        )

        if response.status_code != 200:
            return jsonify({"error": f"Block {height} not found"}), 404

        data = response.json()
        if not data.get("result"):
            return jsonify({"error": f"Block {height} not found"}), 404

        block = data["result"]["block"]
        block_id = data["result"].get("block_id", {})
        header = block.get("header", {})
        txs = block.get("data", {}).get("txs", [])

        # Parse timestamp
        timestamp = header.get("time")

        # Get proposer moniker if possible
        proposer_address = header.get("proposer_address", "")
        proposer_moniker = proposer_address  # Default to address

        # Build transaction list with hashes
        import hashlib
        import base64
        tx_list = []
        for tx_b64 in txs:
            try:
                tx_bytes = base64.b64decode(tx_b64)
                tx_hash = hashlib.sha256(tx_bytes).hexdigest().upper()
                tx_list.append({"hash": tx_hash})
            except Exception:
                tx_list.append({"hash": "unknown"})

        return jsonify({
            "height": int(header.get("height", height)),
            "hash": block_id.get("hash", ""),
            "time": timestamp,
            "proposer": proposer_address,
            "proposer_moniker": proposer_moniker,
            "num_txs": len(txs),
            "transactions": tx_list,
            "chain_id": header.get("chain_id", config.CHAIN_ID),
            "app_hash": header.get("app_hash", ""),
            "last_block_hash": header.get("last_block_id", {}).get("hash", "")
        })
    except Exception as e:
        logger.error(f"Block fetch error for height {height}: {e}")
        return jsonify({"error": str(e)}), 500


# ==================== TRANSACTION DETAIL ENDPOINT ====================

@app.route("/api/transactions/<tx_hash>", methods=["GET"])
def api_transaction_by_hash(tx_hash):
    """
    Get specific transaction by hash
    ---
    tags:
      - Transactions
    parameters:
      - name: tx_hash
        in: path
        type: string
        required: true
        description: Transaction hash (hex string, with or without 0x prefix)
    responses:
      200:
        description: Transaction details
        schema:
          type: object
          properties:
            hash:
              type: string
              description: Transaction hash
            height:
              type: integer
              description: Block height
            timestamp:
              type: string
              description: Transaction timestamp
            type:
              type: string
              description: Transaction type
            status:
              type: string
              description: Transaction status (success/failed)
            messages:
              type: array
              items:
                type: object
                properties:
                  type:
                    type: string
                    description: Message type
                  content:
                    type: object
                    description: Message content
            fee:
              type: string
              description: Transaction fee formatted
            memo:
              type: string
              description: Transaction memo
            gas_wanted:
              type: integer
              description: Gas requested
            gas_used:
              type: integer
              description: Gas consumed
            log:
              type: string
              description: Error log (if failed)
      404:
        description: Transaction not found
      500:
        description: Server error
    """
    try:
        # Normalize hash format (remove 0x prefix if present, ensure uppercase)
        clean_hash = tx_hash.upper()
        if clean_hash.startswith("0X"):
            clean_hash = clean_hash[2:]

        # Fetch transaction from RPC
        response = requests.get(
            f"{config.NODE_RPC_URL}/tx?hash=0x{clean_hash}",
            timeout=15
        )

        if response.status_code != 200:
            return jsonify({"error": f"Transaction {tx_hash} not found"}), 404

        data = response.json()
        result = data.get("result")
        if not result:
            return jsonify({"error": f"Transaction {tx_hash} not found"}), 404

        height = int(result.get("height", "0"))
        tx_result = result.get("tx_result", {})
        code = tx_result.get("code", 0)
        status = "success" if code == 0 else "failed"
        gas_wanted = int(tx_result.get("gas_wanted", "0"))
        gas_used = int(tx_result.get("gas_used", "0"))
        log = tx_result.get("log", "")

        # Get timestamp from block
        timestamp = None
        try:
            block_resp = requests.get(
                f"{config.NODE_RPC_URL}/block?height={height}",
                timeout=10
            )
            if block_resp.status_code == 200:
                block_data = block_resp.json().get("result", {}).get("block", {})
                timestamp = block_data.get("header", {}).get("time")
        except Exception:
            pass

        # Parse transaction body for messages, fee, memo
        import base64
        messages = []
        fee = None
        memo = ""
        tx_type = "Unknown"

        tx_b64 = result.get("tx")
        if tx_b64:
            try:
                # Try to get detailed tx info from REST API
                rest_response = requests.get(
                    f"{config.NODE_API_URL}/cosmos/tx/v1beta1/txs/{clean_hash}",
                    headers={"Connection": "close"},
                    timeout=15
                )
                if rest_response.status_code == 200:
                    rest_data = rest_response.json()
                    tx_response = rest_data.get("tx_response", {})
                    raw_tx = rest_data.get("tx", {})

                    # Extract messages
                    body = raw_tx.get("body", {})
                    raw_messages = body.get("messages", [])
                    for msg in raw_messages:
                        msg_type = msg.get("@type", "").split(".")[-1]
                        messages.append({
                            "type": msg_type,
                            "content": msg
                        })
                    if messages:
                        tx_type = messages[0]["type"]

                    memo = body.get("memo", "")

                    # Extract fee
                    auth_info = raw_tx.get("auth_info", {})
                    fee_info = auth_info.get("fee", {})
                    fee_amounts = fee_info.get("amount", [])
                    if fee_amounts:
                        fee_coin = fee_amounts[0]
                        fee_amount = int(fee_coin.get("amount", "0"))
                        fee_denom = fee_coin.get("denom", config.DENOM)
                        if fee_denom == config.DENOM:
                            fee = f"{fee_amount / 1_000_000:.6f} AURA"
                        else:
                            fee = f"{fee_amount} {fee_denom}"
            except Exception as parse_err:
                logger.warning(f"Could not parse tx details: {parse_err}")

        return jsonify({
            "hash": clean_hash,
            "height": height,
            "timestamp": timestamp,
            "type": tx_type,
            "status": status,
            "messages": messages,
            "fee": fee,
            "memo": memo,
            "gas_wanted": gas_wanted,
            "gas_used": gas_used,
            "log": log if code != 0 else None
        })
    except Exception as e:
        logger.error(f"Transaction fetch error for {tx_hash}: {e}")
        return jsonify({"error": str(e)}), 500


# ==================== VALIDATOR DETAIL ENDPOINT ====================

@app.route("/api/validators/<address>", methods=["GET"])
def api_validator_by_address(address):
    """
    Get individual validator details
    ---
    tags:
      - Validators
    parameters:
      - name: address
        in: path
        type: string
        required: true
        description: Validator operator address (auravaloper1...)
    responses:
      200:
        description: Validator details
        schema:
          type: object
          properties:
            operator_address:
              type: string
              description: Operator address
            consensus_pubkey:
              type: object
              description: Consensus public key
            moniker:
              type: string
              description: Validator name
            identity:
              type: string
              description: Keybase identity
            website:
              type: string
              description: Validator website
            security_contact:
              type: string
              description: Security contact email
            details:
              type: string
              description: Validator description
            status:
              type: string
              description: Validator status (Active/Inactive/Unbonding)
            status_raw:
              type: string
              description: Raw Cosmos SDK status
            jailed:
              type: boolean
              description: Whether validator is jailed
            tokens:
              type: integer
              description: Total staked tokens
            tokens_formatted:
              type: string
              description: Formatted staked amount
            delegator_shares:
              type: string
              description: Delegator shares
            commission:
              type: object
              properties:
                rate:
                  type: number
                  description: Current commission rate
                max_rate:
                  type: number
                  description: Maximum commission rate
                max_change_rate:
                  type: number
                  description: Maximum daily commission change
                update_time:
                  type: string
                  description: Last commission update time
            min_self_delegation:
              type: string
              description: Minimum self-delegation
            unbonding_height:
              type: string
              description: Height when unbonding started
            unbonding_time:
              type: string
              description: Time when unbonding completes
      404:
        description: Validator not found
      500:
        description: Server error
    """
    try:
        validator = None

        # Try REST API first with retry
        try:
            response = _fetch_with_retry(
                f"{config.NODE_API_URL}/cosmos/staking/v1beta1/validators/{address}"
            )
            if response and response.status_code == 200:
                data = response.json()
                validator = data.get("validator")
        except Exception as rest_err:
            logger.warning(f"REST validator fetch failed: {rest_err}")

        # If REST failed, try to find in genesis validators
        if not validator:
            try:
                genesis_response = requests.get(
                    f"{config.NODE_RPC_URL}/genesis",
                    timeout=30
                )
                if genesis_response.status_code == 200:
                    genesis_data = genesis_response.json()
                    genesis_validators = genesis_data.get("result", {}).get("genesis", {}).get("app_state", {}).get("staking", {}).get("validators", [])
                    for v in genesis_validators:
                        if v.get("operator_address") == address:
                            validator = v
                            break
            except Exception as genesis_err:
                logger.warning(f"Genesis validator fetch failed: {genesis_err}")

        if not validator:
            return jsonify({"error": f"Validator {address} not found"}), 404

        description = validator.get("description", {})
        commission = validator.get("commission", {})
        commission_rates = commission.get("commission_rates", {})
        tokens = int(validator.get("tokens", "0"))
        status = validator.get("status", "")
        jailed = validator.get("jailed", False)

        # Map status to friendly name
        status_map = {
            "BOND_STATUS_BONDED": "Active",
            "BOND_STATUS_UNBONDING": "Unbonding",
            "BOND_STATUS_UNBONDED": "Inactive"
        }
        status_friendly = status_map.get(status, status)

        return jsonify({
            "operator_address": validator.get("operator_address"),
            "consensus_pubkey": validator.get("consensus_pubkey"),
            "moniker": description.get("moniker", "Unknown"),
            "identity": description.get("identity", ""),
            "website": description.get("website", ""),
            "security_contact": description.get("security_contact", ""),
            "details": description.get("details", ""),
            "status": status_friendly,
            "status_raw": status,
            "jailed": jailed,
            "tokens": tokens,
            "tokens_formatted": f"{tokens / 1_000_000:.2f} AURA",
            "delegator_shares": validator.get("delegator_shares"),
            "commission": {
                "rate": float(commission_rates.get("rate", "0")),
                "max_rate": float(commission_rates.get("max_rate", "0")),
                "max_change_rate": float(commission_rates.get("max_change_rate", "0")),
                "update_time": commission.get("update_time")
            },
            "min_self_delegation": validator.get("min_self_delegation"),
            "unbonding_height": validator.get("unbonding_height"),
            "unbonding_time": validator.get("unbonding_time")
        })
    except Exception as e:
        logger.error(f"Validator fetch error for {address}: {e}")
        return jsonify({"error": str(e)}), 500


# ==================== IBC ENDPOINTS ====================

@app.route("/api/ibc/transfers", methods=["GET"])
def api_ibc_transfers():
    """
    Get IBC transfer history
    ---
    tags:
      - IBC
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
        description: Page number
      - name: limit
        in: query
        type: integer
        default: 20
        description: Number of transfers per page (max 100)
    responses:
      200:
        description: IBC transfer history
        schema:
          type: object
          properties:
            transfers:
              type: array
              items:
                type: object
                properties:
                  hash:
                    type: string
                    description: Transaction hash
                  height:
                    type: integer
                    description: Block height
                  timestamp:
                    type: string
                    description: Transfer timestamp
                  sender:
                    type: string
                    description: Sender address
                  receiver:
                    type: string
                    description: Receiver address
                  amount:
                    type: string
                    description: Transfer amount
                  channel:
                    type: string
                    description: IBC channel ID
                  status:
                    type: string
                    description: Transfer status
            total:
              type: integer
              description: Total transfer count
            page:
              type: integer
              description: Current page
            limit:
              type: integer
              description: Page size
      500:
        description: Server error
    """
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 20, type=int)
        limit = min(limit, 100)

        # Search for IBC transfer transactions
        params = {
            "query": '"message.action=\'/ibc.applications.transfer.v1.MsgTransfer\'"',
            "prove": "false",
            "page": str(page),
            "per_page": str(limit),
            "order_by": '"desc"'
        }
        response = requests.get(
            f"{config.NODE_RPC_URL}/tx_search",
            params=params,
            timeout=30
        )

        transfers = []
        total_count = 0

        if response.status_code == 200:
            result = response.json().get("result", {})
            total_count = int(result.get("total_count", "0"))

            for tx in result.get("txs", []):
                tx_hash = tx.get("hash", "")
                height = int(tx.get("height", "0"))
                tx_result = tx.get("tx_result", {})
                code = tx_result.get("code", 0)
                status = "success" if code == 0 else "failed"

                # Parse transfer details from events
                sender = None
                receiver = None
                amount = None
                channel = None

                events = tx_result.get("events", [])
                for event in events:
                    event_type = event.get("type", "")
                    if event_type == "send_packet" or event_type == "ibc_transfer":
                        for attr in event.get("attributes", []):
                            key = attr.get("key", "")
                            value = attr.get("value", "")
                            # Handle base64 encoded keys/values
                            try:
                                import base64
                                key = base64.b64decode(key).decode("utf-8")
                            except Exception:
                                pass
                            try:
                                import base64
                                value = base64.b64decode(value).decode("utf-8")
                            except Exception:
                                pass

                            if key == "sender":
                                sender = value
                            elif key == "receiver":
                                receiver = value
                            elif key == "amount":
                                amount = value
                            elif key == "packet_src_channel":
                                channel = value

                # Get timestamp
                timestamp = None
                try:
                    block_resp = requests.get(
                        f"{config.NODE_RPC_URL}/block?height={height}",
                        timeout=10
                    )
                    if block_resp.status_code == 200:
                        block_data = block_resp.json().get("result", {}).get("block", {})
                        timestamp = block_data.get("header", {}).get("time")
                except Exception:
                    pass

                transfers.append({
                    "hash": tx_hash,
                    "height": height,
                    "timestamp": timestamp,
                    "sender": sender,
                    "receiver": receiver,
                    "amount": amount,
                    "channel": channel,
                    "status": status
                })

        return jsonify({
            "transfers": transfers,
            "total": total_count,
            "page": page,
            "limit": limit
        })
    except Exception as e:
        logger.error(f"IBC transfers fetch error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/ibc/channels", methods=["GET"])
def api_ibc_channels():
    """
    Get IBC channel status
    ---
    tags:
      - IBC
    responses:
      200:
        description: List of IBC channels
        schema:
          type: object
          properties:
            channels:
              type: array
              items:
                type: object
                properties:
                  channel_id:
                    type: string
                    description: Channel ID (e.g., channel-0)
                  port_id:
                    type: string
                    description: Port ID (e.g., transfer)
                  state:
                    type: string
                    description: Channel state (STATE_OPEN, STATE_CLOSED, etc.)
                  ordering:
                    type: string
                    description: Channel ordering (ORDER_ORDERED, ORDER_UNORDERED)
                  version:
                    type: string
                    description: IBC version
                  counterparty:
                    type: object
                    properties:
                      channel_id:
                        type: string
                        description: Counterparty channel ID
                      port_id:
                        type: string
                        description: Counterparty port ID
                  connection_hops:
                    type: array
                    items:
                      type: string
                    description: Connection IDs
            count:
              type: integer
              description: Total channel count
      500:
        description: Server error
    """
    try:
        # Fetch channels from REST API with retry
        try:
            response = _fetch_with_retry(
                f"{config.NODE_API_URL}/ibc/core/channel/v1/channels?pagination.limit=100",
                max_retries=2,
                timeout=30
            )
        except Exception:
            response = None

        if not response or response.status_code != 200:
            return jsonify({"channels": [], "error": "IBC module not available or no channels"}), 200

        data = response.json()
        raw_channels = data.get("channels", [])

        channels = []
        for ch in raw_channels:
            counterparty = ch.get("counterparty", {})
            channels.append({
                "channel_id": ch.get("channel_id"),
                "port_id": ch.get("port_id"),
                "state": ch.get("state"),
                "ordering": ch.get("ordering"),
                "version": ch.get("version"),
                "counterparty": {
                    "channel_id": counterparty.get("channel_id"),
                    "port_id": counterparty.get("port_id")
                },
                "connection_hops": ch.get("connection_hops", [])
            })

        return jsonify({
            "channels": channels,
            "count": len(channels)
        })
    except Exception as e:
        logger.error(f"IBC channels fetch error: {e}")
        return jsonify({"error": str(e)}), 500


# ==================== SUPPLY ENDPOINT ====================

@app.route("/api/supply", methods=["GET"])
def api_supply():
    """
    Get token supply information
    ---
    tags:
      - Supply
    responses:
      200:
        description: Token supply information
        schema:
          type: object
          properties:
            total_supply:
              type: array
              items:
                type: object
                properties:
                  denom:
                    type: string
                    description: Token denomination
                  amount:
                    type: string
                    description: Raw amount
                  amount_formatted:
                    type: string
                    description: Formatted amount for AURA denom
            primary_denom:
              type: string
              description: Primary denomination (uaura)
            primary_supply:
              type: integer
              description: Total supply of primary token
            primary_supply_formatted:
              type: string
              description: Formatted primary supply
      500:
        description: Server error
    """
    try:
        import base64

        # Use RPC ABCI query which is more reliable than REST for supply
        response = requests.get(
            f"{config.NODE_RPC_URL}/abci_query",
            params={"path": '"/cosmos.bank.v1beta1.Query/TotalSupply"'},
            timeout=15
        )

        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch supply"}), 500

        data = response.json()
        result = data.get("result", {}).get("response", {})

        if result.get("code", 0) != 0:
            return jsonify({"error": "ABCI query failed"}), 500

        # Decode the protobuf response - parse simple format
        value_b64 = result.get("value", "")
        if not value_b64:
            return jsonify({"error": "No supply data"}), 500

        raw_bytes = base64.b64decode(value_b64)

        # Parse the protobuf manually for coin entries
        # Format: repeated Coin { string denom = 1; string amount = 2; }
        formatted_supply = []
        total_aura = 0
        i = 0

        while i < len(raw_bytes):
            if raw_bytes[i] == 0x0a:  # Field 1, wire type 2 (length-delimited)
                i += 1
                coin_len = raw_bytes[i]
                i += 1
                coin_data = raw_bytes[i:i + coin_len]
                i += coin_len

                # Parse coin: denom at field 1, amount at field 2
                j = 0
                denom = ""
                amount = 0

                while j < len(coin_data):
                    field_tag = coin_data[j]
                    j += 1
                    if field_tag == 0x0a:  # Field 1 (denom)
                        denom_len = coin_data[j]
                        j += 1
                        denom = coin_data[j:j + denom_len].decode('utf-8')
                        j += denom_len
                    elif field_tag == 0x12:  # Field 2 (amount as string)
                        amount_len = coin_data[j]
                        j += 1
                        amount = int(coin_data[j:j + amount_len].decode('utf-8'))
                        j += amount_len
                    else:
                        break

                entry = {
                    "denom": denom,
                    "amount": str(amount)
                }
                if denom == config.DENOM:
                    total_aura = amount
                    entry["amount_formatted"] = f"{amount / 1_000_000:.2f} AURA"
                formatted_supply.append(entry)
            else:
                i += 1

        return jsonify({
            "total_supply": formatted_supply,
            "primary_denom": config.DENOM,
            "primary_supply": total_aura,
            "primary_supply_formatted": f"{total_aura / 1_000_000:.2f} AURA"
        })
    except Exception as e:
        logger.error(f"Supply fetch error: {e}")
        return jsonify({"error": str(e)}), 500


# ==================== SEARCH ENDPOINTS ====================

@app.route("/api/search", methods=["POST", "GET"])
def search_endpoint():
    """
    Advanced search endpoint
    ---
    tags:
      - Search
    parameters:
      - name: q
        in: query
        type: string
        description: Search query (GET method)
      - name: user_id
        in: query
        type: string
        description: Optional user ID for search history
      - name: body
        in: body
        schema:
          type: object
          properties:
            query:
              type: string
              description: Search query (POST method)
            user_id:
              type: string
              description: Optional user ID
    responses:
      200:
        description: Search results
        schema:
          type: object
          properties:
            query:
              type: string
              description: Original search query
            type:
              type: string
              description: Detected query type (block_height, block_hash, transaction_id, address)
            results:
              type: object
              description: Search results based on query type
            found:
              type: boolean
              description: Whether results were found
            timestamp:
              type: number
              description: Unix timestamp
      400:
        description: Query required
      500:
        description: Server error
    """
    if request.method == "POST":
        data = request.json or {}
        query = data.get("query", "").strip()
        user_id = data.get("user_id", "anonymous")
    else:
        query = request.args.get("q", "").strip()
        user_id = request.args.get("user_id", "anonymous")

    if not query:
        return jsonify({"error": "Query required"}), 400

    return jsonify(search_engine.search(query, user_id))


@app.route("/api/search/autocomplete", methods=["GET"])
def autocomplete_endpoint():
    """
    Get autocomplete suggestions
    ---
    tags:
      - Search
    parameters:
      - name: prefix
        in: query
        type: string
        required: true
        description: Search prefix for suggestions
      - name: limit
        in: query
        type: integer
        default: 10
        description: Maximum number of suggestions
    responses:
      200:
        description: Autocomplete suggestions
        schema:
          type: object
          properties:
            suggestions:
              type: array
              items:
                type: string
              description: List of suggested queries
    """
    prefix = request.args.get("prefix", "").strip()
    limit = request.args.get("limit", 10, type=int)

    if not prefix:
        return jsonify({"suggestions": []})

    return jsonify({
        "suggestions": search_engine.get_autocomplete_suggestions(prefix, limit)
    })


@app.route("/api/search/recent", methods=["GET"])
def recent_searches_endpoint():
    """
    Get recent searches
    ---
    tags:
      - Search
    parameters:
      - name: limit
        in: query
        type: integer
        default: 10
        description: Number of recent searches to return
    responses:
      200:
        description: Recent search history
        schema:
          type: object
          properties:
            recent:
              type: array
              items:
                type: object
                properties:
                  query:
                    type: string
                    description: Search query
                  type:
                    type: string
                    description: Query type
                  timestamp:
                    type: number
                    description: Search timestamp
    """
    limit = request.args.get("limit", 10, type=int)
    return jsonify({
        "recent": search_engine.get_recent_searches(limit)
    })


# ==================== RICH LIST ENDPOINTS ====================

@app.route("/api/richlist", methods=["GET"])
def richlist_endpoint():
    """
    Get top address holders
    ---
    tags:
      - RichList
    parameters:
      - name: limit
        in: query
        type: integer
        default: 100
        description: Number of addresses to return (max 1000)
    responses:
      200:
        description: Rich list of top holders
        schema:
          type: object
          properties:
            richlist:
              type: array
              items:
                type: object
                properties:
                  rank:
                    type: integer
                    description: Rank position
                  address:
                    type: string
                    description: Account address
                  balance:
                    type: number
                    description: Token balance
                  label:
                    type: string
                    description: Address label (if available)
                  category:
                    type: string
                    description: Address category (exchange, pool, whale, etc.)
                  percentage_of_supply:
                    type: number
                    description: Percentage of total supply
      500:
        description: Server error
    """
    limit = request.args.get("limit", 100, type=int)
    limit = min(limit, 1000)  # Cap at 1000

    return jsonify({
        "richlist": rich_list.get_rich_list(limit)
    })


@app.route("/api/richlist/refresh", methods=["POST"])
def richlist_refresh_endpoint():
    """
    Force refresh rich list
    ---
    tags:
      - RichList
    parameters:
      - name: limit
        in: query
        type: integer
        default: 100
        description: Number of addresses to return (max 1000)
    responses:
      200:
        description: Refreshed rich list
        schema:
          type: object
          properties:
            richlist:
              type: array
              items:
                type: object
                description: Rich list entries
      500:
        description: Server error
    """
    limit = request.args.get("limit", 100, type=int)
    limit = min(limit, 1000)

    return jsonify({
        "richlist": rich_list.get_rich_list(limit, refresh=True)
    })


# ==================== ADDRESS LABELING ====================

@app.route("/api/address/<address>/label", methods=["GET"])
def get_address_label(address):
    """
    Get address label
    ---
    tags:
      - Accounts
    parameters:
      - name: address
        in: path
        type: string
        required: true
        description: AURA address
    responses:
      200:
        description: Address label information
        schema:
          type: object
          properties:
            address:
              type: string
              description: Address
            label:
              type: string
              description: Address label
            category:
              type: string
              description: Category (exchange, pool, whale, contract, etc.)
            description:
              type: string
              description: Label description
            created_at:
              type: number
              description: Creation timestamp
    """
    label = db.get_address_label(address)
    if label:
        return jsonify(asdict(label))
    return jsonify({"label": None})


@app.route("/api/address/<address>/label", methods=["POST"])
def set_address_label(address):
    """
    Set address label (admin endpoint)
    ---
    tags:
      - Accounts
    parameters:
      - name: address
        in: path
        type: string
        required: true
        description: AURA address
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - label
          properties:
            label:
              type: string
              description: Label for the address
            category:
              type: string
              description: Category (exchange, pool, whale, contract, etc.)
            description:
              type: string
              description: Additional description
    responses:
      200:
        description: Label set successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            label:
              type: object
              description: The created label
      400:
        description: Label required
    """
    # In production, this should have authentication
    data = request.json or {}

    if not data.get("label"):
        return jsonify({"error": "Label required"}), 400

    label = AddressLabel(
        address=address,
        label=data["label"],
        category=data.get("category", "other"),
        description=data.get("description", "")
    )

    db.add_address_label(label)
    return jsonify({"success": True, "label": asdict(label)})


# ==================== EXPORT ENDPOINTS ====================

@app.route("/api/export/transactions/<address>", methods=["GET"])
def export_transactions(address):
    """
    Export address transactions as CSV
    ---
    tags:
      - Export
    parameters:
      - name: address
        in: path
        type: string
        required: true
        description: AURA address to export transactions for
    produces:
      - text/csv
    responses:
      200:
        description: CSV file download
        schema:
          type: file
      404:
        description: Unable to export (no transactions or error)
    """
    csv_data = export_manager.export_transactions_csv(address)
    if csv_data:
        return csv_data, 200, {
            "Content-Type": "text/csv",
            "Content-Disposition": f"attachment; filename=transactions_{address}.csv"
        }
    return jsonify({"error": "Unable to export"}), 404


# ==================== GOVERNANCE ENDPOINTS ====================

@app.route("/api/governance/proposals", methods=["GET"])
def get_proposals_endpoint():
    """
    Get list of governance proposals
    ---
    tags:
      - Governance
    parameters:
      - name: limit
        in: query
        type: integer
        default: 20
        description: Number of proposals to return
      - name: offset
        in: query
        type: integer
        default: 0
        description: Offset for pagination
      - name: status
        in: query
        type: string
        enum: ["voting", "passed", "rejected", "deposit", "failed"]
        description: Filter by proposal status
    responses:
      200:
        description: List of governance proposals
        schema:
          type: object
          properties:
            proposals:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                    description: Proposal ID
                  title:
                    type: string
                    description: Proposal title
                  description:
                    type: string
                    description: Proposal description
                  type:
                    type: string
                    description: Proposal type
                  status:
                    type: string
                    description: Proposal status
                  submit_time:
                    type: string
                    description: Submission timestamp
                  voting_start_time:
                    type: string
                    description: Voting start timestamp
                  voting_end_time:
                    type: string
                    description: Voting end timestamp
                  total_deposit:
                    type: string
                    description: Total deposit amount
                  tally:
                    type: object
                    description: Tally results
            total:
              type: integer
              description: Total proposal count
      500:
        description: Server error
    """
    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", 0, type=int)
    status = request.args.get("status")
    return jsonify(governance_service.get_proposals(status, limit, offset))


@app.route("/api/governance/proposals/<int:proposal_id>", methods=["GET"])
def get_proposal_endpoint(proposal_id):
    """
    Get single proposal details
    ---
    tags:
      - Governance
    parameters:
      - name: proposal_id
        in: path
        type: integer
        required: true
        description: Proposal ID
    responses:
      200:
        description: Proposal details
        schema:
          type: object
          properties:
            id:
              type: string
              description: Proposal ID
            title:
              type: string
              description: Proposal title
            description:
              type: string
              description: Proposal description
            type:
              type: string
              description: Proposal type
            status:
              type: string
              description: Proposal status
            tally:
              type: object
              properties:
                yes:
                  type: integer
                  description: Yes votes
                no:
                  type: integer
                  description: No votes
                abstain:
                  type: integer
                  description: Abstain votes
                no_with_veto:
                  type: integer
                  description: No with veto votes
                total:
                  type: integer
                  description: Total votes
                yes_percent:
                  type: number
                  description: Yes percentage
      404:
        description: Proposal not found
      500:
        description: Server error
    """
    return jsonify(governance_service.get_proposal(proposal_id))


@app.route("/api/governance/proposals/<int:proposal_id>/votes", methods=["GET"])
def get_proposal_votes_endpoint(proposal_id):
    """
    Get votes for a proposal
    ---
    tags:
      - Governance
    parameters:
      - name: proposal_id
        in: path
        type: integer
        required: true
        description: Proposal ID
      - name: limit
        in: query
        type: integer
        default: 50
        description: Number of votes to return
      - name: offset
        in: query
        type: integer
        default: 0
        description: Offset for pagination
    responses:
      200:
        description: List of votes for proposal
        schema:
          type: object
          properties:
            votes:
              type: array
              items:
                type: object
                properties:
                  voter:
                    type: string
                    description: Voter address
                  option:
                    type: string
                    description: Vote option (Yes, No, Abstain, No with Veto)
                  option_raw:
                    type: string
                    description: Raw vote option
            total:
              type: integer
              description: Total vote count
            proposal_id:
              type: integer
              description: Proposal ID
      500:
        description: Server error
    """
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    return jsonify(governance_service.get_proposal_votes(proposal_id, limit, offset))


@app.route("/api/governance/params", methods=["GET"])
def get_governance_params_endpoint():
    """
    Get governance parameters
    ---
    tags:
      - Governance
    responses:
      200:
        description: Governance parameters
        schema:
          type: object
          properties:
            deposit:
              type: object
              description: Deposit parameters
            voting:
              type: object
              description: Voting parameters
            tallying:
              type: object
              description: Tallying parameters
      500:
        description: Server error
    """
    return jsonify(governance_service.get_governance_params())


# ==================== STAKING ENDPOINTS ====================

@app.route("/api/staking/pool", methods=["GET"])
def get_staking_pool_endpoint():
    """
    Get staking pool information
    ---
    tags:
      - Staking
    responses:
      200:
        description: Staking pool information
        schema:
          type: object
          properties:
            bonded_tokens:
              type: integer
              description: Total bonded tokens
            not_bonded_tokens:
              type: integer
              description: Total unbonded tokens
            total_tokens:
              type: integer
              description: Total tokens
            bonded_ratio:
              type: number
              description: Percentage of tokens bonded
            bonded_formatted:
              type: string
              description: Formatted bonded amount
            not_bonded_formatted:
              type: string
              description: Formatted unbonded amount
            total_formatted:
              type: string
              description: Formatted total amount
      500:
        description: Server error
    """
    return jsonify(staking_service.get_staking_pool())


@app.route("/api/staking/delegations/<address>", methods=["GET"])
def get_delegations_endpoint(address):
    """
    Get delegations for an address
    ---
    tags:
      - Staking
    parameters:
      - name: address
        in: path
        type: string
        required: true
        description: Delegator address (aura1...)
    responses:
      200:
        description: Delegation information
        schema:
          type: object
          properties:
            delegations:
              type: array
              items:
                type: object
                properties:
                  validator_address:
                    type: string
                    description: Validator operator address
                  delegator_address:
                    type: string
                    description: Delegator address
                  shares:
                    type: string
                    description: Delegation shares
                  amount:
                    type: integer
                    description: Delegation amount
                  amount_formatted:
                    type: string
                    description: Formatted delegation amount
                  denom:
                    type: string
                    description: Token denomination
            total_staked:
              type: integer
              description: Total staked amount
            total_staked_formatted:
              type: string
              description: Formatted total staked
            count:
              type: integer
              description: Number of delegations
      500:
        description: Server error
    """
    return jsonify(staking_service.get_delegations(address))


@app.route("/api/staking/unbonding/<address>", methods=["GET"])
def get_unbonding_endpoint(address):
    """
    Get unbonding delegations for an address
    ---
    tags:
      - Staking
    parameters:
      - name: address
        in: path
        type: string
        required: true
        description: Delegator address (aura1...)
    responses:
      200:
        description: Unbonding delegation information
        schema:
          type: object
          properties:
            unbonding_delegations:
              type: array
              items:
                type: object
                properties:
                  validator_address:
                    type: string
                    description: Validator operator address
                  delegator_address:
                    type: string
                    description: Delegator address
                  creation_height:
                    type: string
                    description: Height when unbonding started
                  completion_time:
                    type: string
                    description: Time when unbonding completes
                  initial_balance:
                    type: integer
                    description: Initial unbonding amount
                  balance:
                    type: integer
                    description: Current unbonding amount
                  balance_formatted:
                    type: string
                    description: Formatted unbonding amount
            total_unbonding:
              type: integer
              description: Total unbonding amount
            total_unbonding_formatted:
              type: string
              description: Formatted total unbonding
            count:
              type: integer
              description: Number of unbonding delegations
      500:
        description: Server error
    """
    return jsonify(staking_service.get_unbonding_delegations(address))


@app.route("/api/staking/rewards/<address>", methods=["GET"])
def get_rewards_endpoint(address):
    """
    Get pending rewards for an address
    ---
    tags:
      - Staking
    parameters:
      - name: address
        in: path
        type: string
        required: true
        description: Delegator address (aura1...)
    responses:
      200:
        description: Pending rewards information
        schema:
          type: object
          properties:
            rewards_by_validator:
              type: array
              items:
                type: object
                properties:
                  validator_address:
                    type: string
                    description: Validator operator address
                  rewards:
                    type: array
                    items:
                      type: object
                      properties:
                        amount:
                          type: number
                          description: Reward amount
                        denom:
                          type: string
                          description: Token denomination
                        amount_formatted:
                          type: string
                          description: Formatted reward amount
            total_rewards:
              type: array
              items:
                type: object
                description: Total rewards by denomination
            total_amount:
              type: number
              description: Total reward amount
            total_formatted:
              type: string
              description: Formatted total rewards
      500:
        description: Server error
    """
    return jsonify(staking_service.get_rewards(address))


@app.route("/api/staking/params", methods=["GET"])
def get_staking_params_endpoint():
    """
    Get staking parameters
    ---
    tags:
      - Staking
    responses:
      200:
        description: Staking parameters
        schema:
          type: object
          properties:
            unbonding_time:
              type: string
              description: Unbonding duration
            max_validators:
              type: integer
              description: Maximum number of validators
            max_entries:
              type: integer
              description: Maximum unbonding entries
            historical_entries:
              type: integer
              description: Number of historical entries
            bond_denom:
              type: string
              description: Staking token denomination
      500:
        description: Server error
    """
    return jsonify(staking_service.get_staking_params())


# ==================== WEBSOCKET REAL-TIME UPDATES ====================

@sock.route("/api/ws/updates")
def websocket_updates(ws):
    """WebSocket endpoint for real-time updates"""
    with ws_lock:
        ws_clients.add(ws)

    logger.info(f"WebSocket client connected. Total: {len(ws_clients)}")

    try:
        while True:
            # Receive heartbeat
            data = ws.receive()
            if data == "ping":
                ws.send("pong")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        with ws_lock:
            ws_clients.discard(ws)
        logger.info(f"WebSocket client disconnected. Total: {len(ws_clients)}")


def broadcast_update(update_type: str, data: Dict[str, Any]) -> None:
    """Broadcast update to all WebSocket clients"""
    message = json.dumps({
        "type": update_type,
        "data": data,
        "timestamp": time.time()
    })

    with ws_lock:
        for client in list(ws_clients):
            try:
                client.send(message)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                ws_clients.discard(client)


# ==================== METRICS ENDPOINTS ====================

@app.route("/api/metrics/<metric_type>", methods=["GET"])
def get_metric_history(metric_type):
    """
    Get metric history
    ---
    tags:
      - Analytics
    parameters:
      - name: metric_type
        in: path
        type: string
        required: true
        description: Type of metric (hashrate, tx_volume_24h, active_addresses, etc.)
      - name: hours
        in: query
        type: integer
        default: 24
        description: Number of hours of history to return
    responses:
      200:
        description: Metric history data
        schema:
          type: object
          properties:
            metric_type:
              type: string
              description: Metric type
            period_hours:
              type: integer
              description: Time period in hours
            data:
              type: array
              items:
                type: object
                properties:
                  timestamp:
                    type: number
                    description: Unix timestamp
                  value:
                    type: number
                    description: Metric value
                  data:
                    type: object
                    description: Additional metric data
      500:
        description: Server error
    """
    hours = request.args.get("hours", 24, type=int)
    metrics = db.get_metrics(metric_type, hours)
    return jsonify({
        "metric_type": metric_type,
        "period_hours": hours,
        "data": metrics
    })


# ==================== HEALTH CHECK ====================

@app.route("/health", methods=["GET"])
def health_check():
    """
    Health check
    ---
    tags:
      - Health
    responses:
      200:
        description: Health status
        schema:
          type: object
          properties:
            status:
              type: string
              description: Overall health status (healthy/degraded)
            explorer:
              type: string
              description: Explorer service status
            node:
              type: object
              properties:
                reachable:
                  type: boolean
                  description: Whether blockchain node is reachable
                rpc:
                  type: string
                  description: RPC URL
            timestamp:
              type: number
              description: Unix timestamp
    """
    try:
        response = requests.get(f"{NODE_URL}/health", timeout=10)
        node_status = response.status_code == 200
    except Exception as e:
        logger.warning(f"RPC health degraded: {e}")
        node_status = False

    status = "healthy" if node_status else "degraded"
    return jsonify({
        "status": status,
        "explorer": "running",
        "node": {
            "reachable": node_status,
            "rpc": NODE_URL
        },
        "timestamp": time.time()
    }), 200


# ==================== INFO ENDPOINT ====================

@app.route("/", methods=["GET"])
def explorer_info():
    """
    Explorer information
    ---
    tags:
      - Health
    responses:
      200:
        description: Explorer service information
        schema:
          type: object
          properties:
            name:
              type: string
              description: Explorer name
            version:
              type: string
              description: API version
            chain_id:
              type: string
              description: Blockchain chain ID
            denom:
              type: string
              description: Primary token denomination
            features:
              type: object
              description: Enabled features
            endpoints:
              type: object
              description: Available API endpoints
            node_url:
              type: string
              description: Connected node URL
            timestamp:
              type: number
              description: Unix timestamp
    """
    return jsonify({
        "name": "AURA Block Explorer",
        "version": "2.0.0",
        "chain_id": config.CHAIN_ID,
        "denom": config.DENOM,
        "features": {
            "advanced_search": True,
            "analytics": True,
            "rich_list": True,
            "address_labels": True,
            "csv_export": True,
            "websocket_updates": True,
            "address_labeling": True,
            "cosmos_sdk_compatible": True,
            "governance": True,
            "staking": True
        },
        "endpoints": {
            "analytics": "/api/analytics/*",
            "search": "/api/search",
            "richlist": "/api/richlist",
            "export": "/api/export/*",
            "websocket": "/api/ws/updates",
            "health": "/health",
            "governance": "/api/governance/*",
            "staking": "/api/staking/*",
            "swagger_docs": "/api/docs",
            "openapi_spec": "/apispec.json"
        },
        "node_url": NODE_URL,
        "timestamp": time.time()
    })


if __name__ == "__main__":
    logger.info(f"Starting AURA Block Explorer")
    logger.info(f"Chain ID: {config.CHAIN_ID}")
    logger.info(f"Node RPC URL: {NODE_URL}")
    logger.info(f"Node API URL: {config.NODE_API_URL if hasattr(config, 'NODE_API_URL') else 'Not configured'}")
    logger.info(f"Database: {DB_PATH}")
    logger.info(f"Port: {config.EXPLORER_PORT}")

    app.run(
        host=config.EXPLORER_HOST,
        port=config.EXPLORER_PORT,
        debug=config.DEBUG,
        threaded=True
    )
