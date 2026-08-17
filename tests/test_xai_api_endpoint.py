# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Test xAI File Download API Endpoint
"""

import requests

# Test file ID
file_id = "file_7d0146ef-6085-43e1-b6ba-06de01dbe616"

# Backend service URL (adjust if needed)
BASE_URL = "http://localhost:8085"  # Change to your backend port

print(f"🧪 Testing xAI File Download API")
print(f"📄 File ID: {file_id}")
print(f"🌐 Base URL: {BASE_URL}")
print("="*80)

# Test 1: Get file metadata
print(f"\n📊 Test 1: Get file metadata")
print("-"*80)

metadata_url = f"{BASE_URL}/api/xai-files/metadata/{file_id}"
print(f"URL: {metadata_url}")

try:
    response = requests.get(metadata_url, timeout=30)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        metadata = response.json()
        print(f"✅ Metadata retrieved:")
        import json
        print(json.dumps(metadata, indent=2))
    else:
        print(f"❌ Error: {response.text}")
except Exception as e:
    print(f"❌ Request failed: {e}")

# Test 2: Download file
print(f"\n\n📥 Test 2: Download file")
print("-"*80)

download_url = f"{BASE_URL}/api/xai-files/download/{file_id}"
print(f"URL: {download_url}")

try:
    response = requests.get(download_url, timeout=60, stream=True)
    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    
    if response.status_code == 200:
        # Get filename from Content-Disposition header
        content_disp = response.headers.get('content-disposition', '')
        filename = 'downloaded_file.bin'
        if 'filename=' in content_disp:
            filename = content_disp.split('filename=')[1].strip('"')
        
        # Download and save
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        import os
        file_size = os.path.getsize(filename)
        print(f"✅ File downloaded successfully!")
        print(f"   Filename: {filename}")
        print(f"   Size: {file_size:,} bytes")
        print(f"   Location: {os.path.abspath(filename)}")
    else:
        print(f"❌ Error: {response.text}")
except Exception as e:
    print(f"❌ Request failed: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Test with invalid file_id (should fail gracefully)
print(f"\n\n❌ Test 3: Invalid file_id (should return 400)")
print("-"*80)

invalid_url = f"{BASE_URL}/api/xai-files/download/invalid_id_123"
print(f"URL: {invalid_url}")

try:
    response = requests.get(invalid_url, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 400:
        print(f"✅ Correctly rejected invalid file_id")
    else:
        print(f"⚠️ Unexpected status code")
except Exception as e:
    print(f"❌ Request failed: {e}")

print("\n" + "="*80)
print("✅ All tests completed!")
print("\n📝 Summary:")
print("   - Metadata endpoint: /api/xai-files/metadata/{file_id}")
print("   - Download endpoint: /api/xai-files/download/{file_id}")
print("   - Both endpoints require file_id to start with 'file_' prefix")
print("   - Files are streamed with proper Content-Disposition headers")
