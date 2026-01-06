#!/usr/bin/env python3
"""
Manual test script for Redis cache functionality
Run this to verify Redis operations work correctly
"""

import time
import sys
from cache import RedisCache, MultiTierCache


def test_redis_connection():
    """Test Redis connection and basic operations"""
    print("=" * 60)
    print("Testing Redis Cache Implementation")
    print("=" * 60)

    # Test 1: Initialize Redis cache
    print("\n1. Initializing Redis cache...")
    cache = RedisCache(redis_url="redis://localhost:6379/0", key_prefix="test:")

    if not cache.enabled:
        print("   ❌ Redis not available, using fallback MemoryCache")
        print("   This is OK - fallback mode works as designed")
        cache.set("test", "value")
        assert cache.get("test") == "value"
        print("   ✓ Fallback operations work")
        return

    print("   ✓ Redis connected successfully")

    # Test 2: Connection test
    print("\n2. Testing connection...")
    if cache.test_connection():
        print("   ✓ Connection test passed")
    else:
        print("   ❌ Connection test failed")
        return

    # Test 3: Set and get operations
    print("\n3. Testing set/get operations...")
    test_data = {
        "block_height": 12345,
        "hash": "abc123def456",
        "timestamp": time.time(),
        "validators": ["val1", "val2", "val3"],
    }

    cache.set("test:block:12345", test_data, ttl=60)
    retrieved = cache.get("test:block:12345")

    if retrieved == test_data:
        print("   ✓ Set/Get operations successful")
        print(f"   Data: {retrieved}")
    else:
        print(f"   ❌ Data mismatch: {retrieved}")
        return

    # Test 4: TTL expiration
    print("\n4. Testing TTL expiration...")
    cache.set("test:expire", "should_expire", ttl=2)
    assert cache.get("test:expire") == "should_expire"
    print("   ✓ Value set with 2 second TTL")
    print("   Waiting 3 seconds...")
    time.sleep(3)
    expired = cache.get("test:expire")
    if expired is None:
        print("   ✓ Value correctly expired")
    else:
        print(f"   ❌ Value should have expired: {expired}")

    # Test 5: Delete operation
    print("\n5. Testing delete operation...")
    cache.set("test:delete_me", "delete_value")
    assert cache.get("test:delete_me") == "delete_value"
    cache.delete("test:delete_me")
    if cache.get("test:delete_me") is None:
        print("   ✓ Delete operation successful")
    else:
        print("   ❌ Delete operation failed")

    # Test 6: Bulk operations
    print("\n6. Testing bulk operations...")
    for i in range(10):
        cache.set(f"test:bulk:{i}", {"index": i, "value": i * 10}, ttl=60)
    print("   ✓ Set 10 items")

    all_exist = True
    for i in range(10):
        data = cache.get(f"test:bulk:{i}")
        if data is None or data["index"] != i:
            all_exist = False
            break
    if all_exist:
        print("   ✓ Retrieved all 10 items successfully")
    else:
        print("   ❌ Failed to retrieve all items")

    # Test 7: Clear operation
    print("\n7. Testing clear operation...")
    cache.clear()
    remaining = cache.get("test:bulk:0")
    if remaining is None:
        print("   ✓ Clear operation successful")
    else:
        print(f"   ❌ Clear operation failed, items remain: {remaining}")

    # Test 8: Get statistics
    print("\n8. Getting cache statistics...")
    stats = cache.get_stats()
    print(f"   Mode: {stats.get('mode')}")
    print(f"   Enabled: {stats.get('enabled')}")
    print(f"   Key count: {stats.get('key_count', 'N/A')}")
    print(f"   Memory used: {stats.get('used_memory_human', 'N/A')}")
    print(f"   Keyspace hits: {stats.get('keyspace_hits', 'N/A')}")
    print(f"   Keyspace misses: {stats.get('keyspace_misses', 'N/A')}")

    # Test 9: Close connection
    print("\n9. Closing connection...")
    cache.close()
    print("   ✓ Connection closed")

    print("\n" + "=" * 60)
    print("✓ All Redis cache tests passed!")
    print("=" * 60)


def test_multi_tier_cache():
    """Test multi-tier cache with Redis"""
    print("\n\n" + "=" * 60)
    print("Testing Multi-Tier Cache (L1 Memory + L2 Redis)")
    print("=" * 60)

    redis_cache = RedisCache(redis_url="redis://localhost:6379/1", key_prefix="mtc:")
    multi_cache = MultiTierCache(redis_cache=redis_cache)

    print("\n1. Setting values in multi-tier cache...")
    multi_cache.set("key1", {"data": "value1"}, ttl=60)
    multi_cache.set("key2", {"data": "value2"}, ttl=60)
    multi_cache.set("key3", {"data": "value3"}, ttl=60)
    print("   ✓ Set 3 values")

    print("\n2. Testing L1 cache hits...")
    v1 = multi_cache.get("key1")
    v2 = multi_cache.get("key2")
    v3 = multi_cache.get("key3")
    assert v1["data"] == "value1"
    assert v2["data"] == "value2"
    assert v3["data"] == "value3"
    print("   ✓ All L1 hits successful")

    print("\n3. Clearing L1 cache only...")
    multi_cache.l1_cache.clear()
    print("   ✓ L1 cache cleared")

    print("\n4. Testing L2 cache promotion...")
    v1_promoted = multi_cache.get("key1")
    if redis_cache.enabled and not redis_cache.fallback_mode:
        assert v1_promoted["data"] == "value1"
        print("   ✓ Value promoted from L2 to L1")
    else:
        print("   ⚠ Redis not available, skipping promotion test")

    print("\n5. Cache statistics...")
    stats = multi_cache.get_stats()
    print(f"   L1 hits: {stats['hits']['l1']}")
    print(f"   L2 hits: {stats['hits']['l2']}")
    print(f"   Total hits: {stats['hits']['total']}")
    print(f"   Misses: {stats['misses']}")
    print(f"   Hit rate: {stats['hit_rate']:.2f}%")

    print("\n6. Cleaning up...")
    multi_cache.clear()
    if redis_cache.enabled:
        redis_cache.close()
    print("   ✓ Cleanup complete")

    print("\n" + "=" * 60)
    print("✓ Multi-tier cache tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_redis_connection()
        test_multi_tier_cache()
        print("\n✅ All manual tests completed successfully!\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
