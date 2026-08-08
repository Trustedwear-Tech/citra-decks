
import os
import requests
import json
import time
import jwt
import datetime

API_URL = "http://localhost:8085/presentation/generate-slides-batch"
USER_ID = "test_user_123"
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise SystemExit("Set JWT_SECRET env var before running this script")

def generate_token():
    payload = {
        "user_id": USER_ID,
        "email": "test@example.com",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def test_batch_generation():
    print("🚀 Testing Batch Presentation Generation...")
    
    token = generate_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Mock slide requests
    items = []
    for i in range(5):
        items.append({
            "slide_info": {
                "title": f"Test Slide {i+1}",
                "content_hint": "This is a test slide generated via batch API.",
                "layout": "title_content"
            },
            "slide_index": i,
            "total_slides": 5,
            "presentation_goal": "Test Parallel Processing",
            "presentation_type": "informative",
            "user_id": USER_ID,
            "folder_ids": []
        })

    payload = {
        "items": items,
        "user_id": USER_ID
    }
    
    start_time = time.time()
    try:
        print(f"📡 Sending request with {len(items)} slides...")
        response = requests.post(API_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            duration = time.time() - start_time
            data = response.json()
            print(f"✅ Success! Generated {len(data['slides'])} slides in {duration:.2f} seconds")
            print(f"   Success Rate: {len(data['slides'])}/{data['total']}")
            
            # Check for errors in results
            errors = [r for r in data['results'] if not r.get('success', False)]
            if errors:
                print(f"⚠️ {len(errors)} slides failed:")
                for err in errors:
                    print(f"   - Slide {err.get('slide_index')}: {err.get('error')}")
            else:
                print("✨ All slides generated successfully without errors.")
                
            # print sample
            # print(json.dumps(data['slides'][0] if data['slides'] else {}, indent=2))
        else:
            print(f"❌ Basic Request Failed: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    test_batch_generation()
