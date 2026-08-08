#!/usr/bin/env python3
"""
Test Redis connection using settings from .env file
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    import redis
    print("✅ Redis package is installed")
except ImportError:
    print("❌ Redis package is NOT installed. Install with: pip install redis")
    exit(1)

# Get Redis settings from environment
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_USERNAME = os.getenv("REDIS_USERNAME")
REDIS_SSL = os.getenv("REDIS_SSL", "false").lower() == "true"

print("\n📋 Redis Configuration from .env:")
print(f"  Host: {REDIS_HOST}")
print(f"  Port: {REDIS_PORT}")
print(f"  Database: {REDIS_DB}")
print(f"  Username: {REDIS_USERNAME or '(none)'}")
print(f"  Password: {'***' if REDIS_PASSWORD else '(none)'}")
print(f"  SSL: {REDIS_SSL}")

# Test connection
print(f"\n🔌 Attempting to connect to Redis at {REDIS_HOST}:{REDIS_PORT}...")

try:
    # Build connection parameters
    conn_params = {
        'host': REDIS_HOST,
        'port': REDIS_PORT,
        'db': REDIS_DB,
        'decode_responses': True,
        'socket_connect_timeout': 5,
        'socket_timeout': 5
    }
    
    # Add authentication if provided
    if REDIS_USERNAME:
        conn_params['username'] = REDIS_USERNAME
    if REDIS_PASSWORD:
        conn_params['password'] = REDIS_PASSWORD
    
    if REDIS_SSL:
        conn_params['ssl'] = True
        conn_params['ssl_cert_reqs'] = None
    
    # Create Redis client
    client = redis.Redis(**conn_params)
    
    # Test connection
    client.ping()
    
    print("✅ Redis connection SUCCESSFUL!")
    
    # Get Redis info
    info = client.info()
    print(f"\n📊 Redis Server Info:")
    print(f"  Version: {info.get('redis_version', 'unknown')}")
    print(f"  Mode: {info.get('redis_mode', 'unknown')}")
    print(f"  Connected Clients: {info.get('connected_clients', 'unknown')}")
    print(f"  Used Memory: {info.get('used_memory_human', 'unknown')}")
    
    # Test basic operations
    print(f"\n🧪 Testing basic operations...")
    client.set('test_key', 'test_value', ex=10)
    value = client.get('test_key')
    print(f"  SET/GET test: {'✅ PASS' if value == 'test_value' else '❌ FAIL'}")
    client.delete('test_key')
    
except redis.exceptions.ConnectionError as e:
    print(f"❌ Connection Error: {e}")
    print("\n💡 Troubleshooting:")
    print("  1. Check if Redis server is running")
    print("  2. Verify REDIS_HOST and REDIS_PORT are correct")
    print("  3. Check firewall settings")
    
except redis.exceptions.AuthenticationError as e:
    print(f"❌ Authentication Error: {e}")
    print("\n💡 Troubleshooting:")
    print("  1. Check REDIS_PASSWORD in .env file")
    print("  2. Check REDIS_USERNAME if using Redis 6+")
    print("  3. Verify Redis ACL settings")
    
except redis.exceptions.ResponseError as e:
    print(f"❌ Response Error: {e}")
    print("\n💡 This is the error your application is getting!")
    print("  The error message suggests invalid credentials or disabled user")
    
except Exception as e:
    print(f"❌ Unexpected Error: {type(e).__name__}: {e}")

print("\n" + "="*60)
