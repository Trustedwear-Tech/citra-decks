import xai_sdk
print(f"xai_sdk version: {xai_sdk.__version__}")
print(f"\nAvailable attributes in xai_sdk:")
print([attr for attr in dir(xai_sdk) if not attr.startswith('_')])

# Test imports
print("\n=== Testing imports ===")

try:
    from xai_sdk import Client
    print("✅ from xai_sdk import Client")
except ImportError as e:
    print(f"❌ from xai_sdk import Client: {e}")

try:
    from xai_sdk.chat import system, user
    print("✅ from xai_sdk.chat import system, user")
except ImportError as e:
    print(f"❌ from xai_sdk.chat import system, user: {e}")

try:
    import xai_sdk.chat
    print(f"✅ xai_sdk.chat module exists")
    print(f"   Available: {[attr for attr in dir(xai_sdk.chat) if not attr.startswith('_')]}")
except Exception as e:
    print(f"❌ xai_sdk.chat: {e}")
