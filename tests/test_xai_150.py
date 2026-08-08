import xai_sdk
print(f"xai_sdk version: {xai_sdk.__version__ if hasattr(xai_sdk, '__version__') else 'unknown'}")
print(f"xai_sdk location: {xai_sdk.__file__}")
print(f"xai_sdk attributes: {dir(xai_sdk)}")

# Test different import patterns
print("\n=== Testing imports ===")

try:
    from xai_sdk import Client
    print("✅ from xai_sdk import Client - SUCCESS")
except ImportError as e:
    print(f"❌ from xai_sdk import Client - FAILED: {e}")

try:
    from xai_sdk.client import Client
    print("✅ from xai_sdk.client import Client - SUCCESS")
except ImportError as e:
    print(f"❌ from xai_sdk.client import Client - FAILED: {e}")

try:
    from xai_sdk.ide_params import system, user
    print("✅ from xai_sdk.ide_params import system, user - SUCCESS")
except ImportError as e:
    print(f"❌ from xai_sdk.ide_params import system, user - FAILED: {e}")

try:
    from xai_sdk import ide_params
    print(f"✅ from xai_sdk import ide_params - SUCCESS")
    print(f"   ide_params attributes: {dir(ide_params)}")
except ImportError as e:
    print(f"❌ from xai_sdk import ide_params - FAILED: {e}")
