"""
Generate JWT token for testing Citra AI Service
"""
import jwt
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ISSUER = os.getenv("JWT_ISSUER", "Citra-AI")
JWT_EXPIRES_IN = os.getenv("JWT_EXPIRES_IN", "7d")

# Test user
test_user = {
    "user_id": "rohitkumarchandan1982@gmail.com",  # Required by auth middleware
    "email": "rohitkumarchandan1982@gmail.com",
    "name": "Rohit Kumar Chandan",
    "googleId": "test123"
}

print("=" * 80)
print("JWT Token Generator for Citra AI")
print("=" * 80)
print(f"\n✅ JWT_SECRET exists: {bool(JWT_SECRET)}")
print(f"✅ JWT_ISSUER: {JWT_ISSUER}")
print(f"✅ JWT_EXPIRES_IN: {JWT_EXPIRES_IN}")

# Parse expiration (7d = 7 days)
if "d" in JWT_EXPIRES_IN:
    days = int(JWT_EXPIRES_IN.replace("d", ""))
    expiration = datetime.utcnow() + timedelta(days=days)
elif "h" in JWT_EXPIRES_IN:
    hours = int(JWT_EXPIRES_IN.replace("h", ""))
    expiration = datetime.utcnow() + timedelta(hours=hours)
else:
    expiration = datetime.utcnow() + timedelta(days=7)

# Create payload (auth middleware requires: user_id, email, exp)
payload = {
    "user_id": test_user["user_id"],  # Required by auth middleware
    "email": test_user["email"],
    "name": test_user.get("name"),
    "googleId": test_user.get("googleId"),
    "exp": expiration,
    "iat": datetime.utcnow(),
    "iss": JWT_ISSUER
}

print(f"\n📧 User: {test_user['email']}")
print(f"📅 Expires: {expiration.strftime('%Y-%m-%d %H:%M:%S')} UTC")

# Generate token
try:
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    print("\n" + "=" * 80)
    print("✅ JWT TOKEN GENERATED SUCCESSFULLY")
    print("=" * 80)
    print(f"\n{token}\n")
    
    # Decode to verify
    decoded = jwt.decode(jwt=token, key=JWT_SECRET, algorithms=["HS256"])
    print("=" * 80)
    print("Decoded Token Payload:")
    print("=" * 80)
    import json
    print(json.dumps(decoded, indent=2, default=str))
    
    # Save to file for easy copying
    with open("generated_token.txt", "w") as f:
        f.write(token)
    print("\n✅ Token also saved to: generated_token.txt")
    
except Exception as e:
    print(f"\n❌ Error generating token: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
