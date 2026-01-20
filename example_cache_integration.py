#!/usr/bin/env python3
"""
Example: Integrating Redis cache with AURA Block Explorer

This example shows how to integrate the RedisCache and MultiTierCache
into the block explorer for improved performance.
"""

import os
import time
from cache import RedisCache, MultiTierCache


class CachedBlockExplorer:
    """
    Example block explorer with Redis caching
    """

    def __init__(self, node_rpc_url: str = "http://localhost:26657"):
        """Initialize explorer with cache"""
        self.node_rpc_url = node_rpc_url

        # Initialize Redis cache with fallback
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_cache = RedisCache(redis_url=redis_url, key_prefix="aura:explorer:")

        # Use multi-tier cache for best performance
        self.cache = MultiTierCache(redis_cache=redis_cache)

        print("Explorer initialized with cache")
        if redis_cache.enabled and not redis_cache.fallback_mode:
            print(f"  ✓ Redis cache active at {redis_url}")
        else:
            print("  ⚠ Using fallback MemoryCache (Redis unavailable)")

    def get_block(self, height: int) -> dict:
        """
        Get block by height with caching

        First checks cache, then fetches from node if needed.
        Blocks are cached for 10 minutes (600s).
        """
        cache_key = f"block:{height}"

        # Try cache first
        cached_block = self.cache.get(cache_key)
        if cached_block is not None:
            print(f"  ✓ Block {height} from cache")
            return cached_block

        # Cache miss - fetch from node
        print(f"  ⊕ Fetching block {height} from node...")
        block = self._fetch_block_from_node(height)

        # Cache for 10 minutes
        self.cache.set(cache_key, block, ttl=600)

        return block

    def get_latest_blocks(self, count: int = 10) -> list:
        """
        Get latest blocks with caching

        Latest blocks are cached for 30 seconds since they change frequently.
        """
        cache_key = f"latest_blocks:{count}"

        # Try cache first
        cached_blocks = self.cache.get(cache_key)
        if cached_blocks is not None:
            print(f"  ✓ Latest {count} blocks from cache")
            return cached_blocks

        # Cache miss - fetch from node
        print(f"  ⊕ Fetching latest {count} blocks from node...")
        blocks = self._fetch_latest_blocks_from_node(count)

        # Cache for 30 seconds
        self.cache.set(cache_key, blocks, ttl=30)

        return blocks

    def get_address_info(self, address: str) -> dict:
        """
        Get address information with caching

        Address data is cached for 5 minutes.
        """
        cache_key = f"address:{address}"

        # Try cache first
        cached_info = self.cache.get(cache_key)
        if cached_info is not None:
            print(f"  ✓ Address {address[:10]}... from cache")
            return cached_info

        # Cache miss - fetch from node
        print(f"  ⊕ Fetching address {address[:10]}... from node...")
        info = self._fetch_address_from_node(address)

        # Cache for 5 minutes
        self.cache.set(cache_key, info, ttl=300)

        return info

    def get_validator_set(self) -> list:
        """
        Get active validators with caching

        Validator set is cached for 1 minute.
        """
        cache_key = "validators:active"

        # Try cache first
        cached_validators = self.cache.get(cache_key)
        if cached_validators is not None:
            print("  ✓ Validator set from cache")
            return cached_validators

        # Cache miss - fetch from node
        print("  ⊕ Fetching validator set from node...")
        validators = self._fetch_validators_from_node()

        # Cache for 1 minute
        self.cache.set(cache_key, validators, ttl=60)

        return validators

    def invalidate_block_cache(self, height: int):
        """Manually invalidate cached block"""
        cache_key = f"block:{height}"
        self.cache.delete(cache_key)
        print(f"  ✗ Invalidated cache for block {height}")

    def clear_all_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        print("  ✗ All cache cleared")

    def get_cache_stats(self) -> dict:
        """Get cache performance statistics"""
        return self.cache.get_stats()

    # Mock methods (replace with actual node queries in production)

    def _fetch_block_from_node(self, height: int) -> dict:
        """Simulate fetching block from node"""
        time.sleep(0.1)  # Simulate network delay
        return {
            "height": height,
            "hash": f"block_hash_{height}",
            "timestamp": int(time.time()),
            "num_txs": 5,
            "proposer": "aura1validator...",
        }

    def _fetch_latest_blocks_from_node(self, count: int) -> list:
        """Simulate fetching latest blocks"""
        time.sleep(0.2)  # Simulate network delay
        current_height = 1000
        return [self._fetch_block_from_node(current_height - i) for i in range(count)]

    def _fetch_address_from_node(self, address: str) -> dict:
        """Simulate fetching address info"""
        time.sleep(0.15)  # Simulate network delay
        return {
            "address": address,
            "balance": 1000000,
            "sequence": 42,
            "account_number": 123,
        }

    def _fetch_validators_from_node(self) -> list:
        """Simulate fetching validators"""
        time.sleep(0.1)  # Simulate network delay
        return [
            {"address": "aura1val1...", "voting_power": 1000000},
            {"address": "aura1val2...", "voting_power": 900000},
            {"address": "aura1val3...", "voting_power": 800000},
        ]


def demo_cache_performance():
    """
    Demonstrate cache performance improvements
    """
    print("=" * 70)
    print("AURA Block Explorer - Redis Cache Integration Demo")
    print("=" * 70)

    explorer = CachedBlockExplorer()

    # Test 1: Block caching
    print("\n1. Block Caching Test")
    print("-" * 70)

    print("First request (cache miss):")
    start = time.time()
    _block = explorer.get_block(100)
    duration1 = time.time() - start
    print(f"  Time: {duration1*1000:.2f}ms")

    print("\nSecond request (cache hit):")
    start = time.time()
    _block = explorer.get_block(100)
    duration2 = time.time() - start
    print(f"  Time: {duration2*1000:.2f}ms")

    speedup = duration1 / duration2
    print(f"\n  ⚡ Speedup: {speedup:.1f}x faster")

    # Test 2: Latest blocks
    print("\n2. Latest Blocks Caching Test")
    print("-" * 70)

    print("First request (cache miss):")
    start = time.time()
    _blocks = explorer.get_latest_blocks(10)
    duration1 = time.time() - start
    print(f"  Time: {duration1*1000:.2f}ms")

    print("\nSecond request (cache hit):")
    start = time.time()
    _blocks = explorer.get_latest_blocks(10)
    duration2 = time.time() - start
    print(f"  Time: {duration2*1000:.2f}ms")

    speedup = duration1 / duration2
    print(f"\n  ⚡ Speedup: {speedup:.1f}x faster")

    # Test 3: Address lookups
    print("\n3. Address Caching Test")
    print("-" * 70)

    test_address = "aura1abc123def456..."

    print("First request (cache miss):")
    start = time.time()
    _info = explorer.get_address_info(test_address)
    duration1 = time.time() - start
    print(f"  Time: {duration1*1000:.2f}ms")

    print("\nSecond request (cache hit):")
    start = time.time()
    _info = explorer.get_address_info(test_address)
    duration2 = time.time() - start
    print(f"  Time: {duration2*1000:.2f}ms")

    speedup = duration1 / duration2
    print(f"\n  ⚡ Speedup: {speedup:.1f}x faster")

    # Test 4: Cache invalidation
    print("\n4. Cache Invalidation Test")
    print("-" * 70)

    explorer.invalidate_block_cache(100)
    print("After invalidation:")
    start = time.time()
    _block = explorer.get_block(100)
    duration = time.time() - start
    print(f"  Time: {duration*1000:.2f}ms (cache miss expected)")

    # Test 5: Cache statistics
    print("\n5. Cache Statistics")
    print("-" * 70)

    stats = explorer.get_cache_stats()
    print(f"  L1 (Memory) hits: {stats['hits']['l1']}")
    print(f"  L2 (Redis) hits:  {stats['hits']['l2']}")
    print(f"  Total hits:       {stats['hits']['total']}")
    print(f"  Misses:           {stats['misses']}")
    print(f"  Hit rate:         {stats['hit_rate']:.2f}%")

    print("\n" + "=" * 70)
    print("✅ Demo completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    demo_cache_performance()
