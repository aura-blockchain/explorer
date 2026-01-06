"""
AURA Block Explorer Setup Verification Script
Verifies that all components are properly configured
"""

import sys
import os


def check_python_version():
    """Check Python version"""
    print("Checking Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 11:
        print(f"✓ Python {version.major}.{version.minor}.{version.micro} (OK)")
        return True
    else:
        print(f"✗ Python {version.major}.{version.minor}.{version.micro} (Need 3.11+)")
        return False


def check_dependencies():
    """Check required dependencies"""
    print("\nChecking dependencies...")
    required = [
        'flask',
        'flask_cors',
        'flask_sock',
        'requests',
    ]

    missing = []
    for module in required:
        try:
            __import__(module)
            print(f"✓ {module} installed")
        except ImportError:
            print(f"✗ {module} missing")
            missing.append(module)

    return len(missing) == 0, missing


def check_config():
    """Check configuration"""
    print("\nChecking configuration...")
    try:
        from config import config

        print(f"✓ Configuration loaded")
        print(f"  - Chain ID: {config.CHAIN_ID}")
        print(f"  - Denom: {config.DENOM}")
        print(f"  - RPC URL: {config.NODE_RPC_URL}")
        print(f"  - API URL: {config.NODE_API_URL}")
        print(f"  - Explorer Port: {config.EXPLORER_PORT}")
        print(f"  - Database: {config.DB_PATH}")
        return True
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return False


def check_files():
    """Check required files exist"""
    print("\nChecking required files...")
    required_files = [
        'config.py',
        'explorer_backend.py',
        'requirements.txt',
        'Dockerfile',
        'docker-compose.yml',
        'test_explorer.py',
        'README.md'
    ]

    missing = []
    for file in required_files:
        if os.path.exists(file):
            print(f"✓ {file} exists")
        else:
            print(f"✗ {file} missing")
            missing.append(file)

    return len(missing) == 0, missing


def check_database():
    """Check database functionality"""
    print("\nChecking database...")
    try:
        from explorer_backend import ExplorerDatabase

        db = ExplorerDatabase(":memory:")
        print("✓ Database initialization successful")

        # Test basic operations
        from explorer_backend import AddressLabel
        label = AddressLabel(
            address="aura1test",
            label="Test",
            category="test"
        )
        db.add_address_label(label)
        retrieved = db.get_address_label("aura1test")

        if retrieved and retrieved.label == "Test":
            print("✓ Database operations working")
            return True
        else:
            print("✗ Database operations failed")
            return False
    except Exception as e:
        print(f"✗ Database error: {e}")
        return False


def check_search_engine():
    """Check search engine"""
    print("\nChecking search engine...")
    try:
        from explorer_backend import SearchEngine, SearchType, ExplorerDatabase

        db = ExplorerDatabase(":memory:")
        search = SearchEngine("http://localhost:26657", db)

        # Test search type detection
        tests = [
            ("12345", SearchType.BLOCK_HEIGHT),
            ("aura1test123", SearchType.ADDRESS),
            ("A" * 64, SearchType.TRANSACTION_ID),
        ]

        all_passed = True
        for query, expected_type in tests:
            result_type = search._identify_search_type(query)
            if result_type == expected_type:
                print(f"✓ Search type detection: {query[:20]}... → {result_type.value}")
            else:
                print(f"✗ Search type detection failed: {query[:20]}...")
                all_passed = False

        return all_passed
    except Exception as e:
        print(f"✗ Search engine error: {e}")
        return False


def check_flask_app():
    """Check Flask app initialization"""
    print("\nChecking Flask application...")
    try:
        from explorer_backend import app

        print("✓ Flask app initialized")

        # Check routes
        routes = [rule.rule for rule in app.url_map.iter_rules()]
        key_routes = ['/', '/health', '/api/search', '/api/analytics/dashboard']

        all_present = True
        for route in key_routes:
            if route in routes:
                print(f"✓ Route {route} registered")
            else:
                print(f"✗ Route {route} missing")
                all_present = False

        return all_present
    except Exception as e:
        print(f"✗ Flask app error: {e}")
        return False


def main():
    """Run all checks"""
    print("=" * 60)
    print("AURA Block Explorer Setup Verification")
    print("=" * 60)

    results = []

    results.append(("Python Version", check_python_version()))

    deps_ok, missing_deps = check_dependencies()
    results.append(("Dependencies", deps_ok))

    files_ok, missing_files = check_files()
    results.append(("Required Files", files_ok))

    results.append(("Configuration", check_config()))
    results.append(("Database", check_database()))
    results.append(("Search Engine", check_search_engine()))
    results.append(("Flask App", check_flask_app()))

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for check_name, ok in results:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"{check_name:20s} {status}")

    print("=" * 60)
    print(f"Result: {passed}/{total} checks passed")

    if passed == total:
        print("\n✓ All checks passed! Explorer is ready to run.")
        print("\nTo start the explorer:")
        print("  python explorer_backend.py")
        print("\nOr with Docker:")
        print("  docker-compose up -d")
        return 0
    else:
        print("\n✗ Some checks failed. Please review errors above.")

        if not deps_ok:
            print("\nTo install missing dependencies:")
            print("  pip install -r requirements.txt")

        return 1


if __name__ == "__main__":
    sys.exit(main())
