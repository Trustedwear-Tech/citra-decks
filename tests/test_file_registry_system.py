# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Test script for unified file registry system
Tests all upload endpoints and file registry API endpoints
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
import httpx
import json

# Service configuration
BASE_URL = "http://localhost:8085"
TEST_USER_ID = "test@example.com"
TEST_FOLDER_ID = "test_folder"

# JWT token (replace with actual token from your system)
# For testing, you'll need to generate a valid JWT token with your secret key
JWT_TOKEN = "YOUR_JWT_TOKEN_HERE"

headers = {
    "Authorization": f"Bearer {JWT_TOKEN}"
}

async def test_document_upload():
    """Test document upload with registry integration"""
    print("\n" + "="*60)
    print("TEST 1: Document Upload with Registry Integration")
    print("="*60)
    
    # Create a test document
    test_content = "This is a test document for file registry system."
    test_filename = f"test_document_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    files = {
        'file': (test_filename, test_content.encode(), 'text/plain')
    }
    
    data = {
        'topic_or_filename': 'Test Document',
        'folder_id': TEST_FOLDER_ID
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                f"{BASE_URL}/api/v2/documents",
                files=files,
                data=data,
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Document uploaded successfully")
                print(f"   Document ID: {result.get('document_id')}")
                print(f"   Stored vectors: {result.get('stored_vectors')}")
                return result.get('document_id')
            else:
                print(f"❌ Document upload failed: {response.status_code}")
                print(f"   Error: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Exception during document upload: {e}")
            return None


async def test_audio_upload():
    """Test audio upload with registry integration"""
    print("\n" + "="*60)
    print("TEST 2: Audio Upload with Registry Integration")
    print("="*60)
    
    # Note: This requires a valid audio file
    # For now, we'll just show the test structure
    print("⚠️ Audio upload test requires a valid audio file")
    print("   Skipping audio upload test in this run")
    print("   To test: Provide a .mp3/.wav file and uncomment the code")
    
    # Uncomment and modify when testing with real audio file:
    # audio_file_path = "path/to/test_audio.mp3"
    # if not os.path.exists(audio_file_path):
    #     print(f"❌ Audio file not found: {audio_file_path}")
    #     return None
    #     
    # files = {
    #     'audio': (Path(audio_file_path).name, open(audio_file_path, 'rb'), 'audio/mpeg')
    # }
    # 
    # data = {
    #     'topic_or_filename': 'Test Audio Recording',
    #     'folder_id': TEST_FOLDER_ID
    # }
    # 
    # async with httpx.AsyncClient(timeout=120.0) as client:
    #     response = await client.post(
    #         f"{BASE_URL}/api/v2/transcripts",
    #         files=files,
    #         data=data,
    #         headers=headers
    #     )
    #     ...
    
    return None


async def test_list_files(folder_id=None, file_type=None):
    """Test GET /api/v2/files endpoint"""
    print("\n" + "="*60)
    print("TEST 3: List/Search Files")
    print("="*60)
    
    params = {}
    if folder_id:
        params['folder_id'] = folder_id
    if file_type:
        params['file_type_category'] = file_type
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v2/files",
                params=params,
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                files = result.get('files', [])
                total = result.get('total', 0)
                
                print(f"✅ Retrieved {len(files)} files (total: {total})")
                
                if files:
                    print("\nFiles found:")
                    for file in files[:5]:  # Show first 5 files
                        print(f"   - {file.get('filename')} ({file.get('file_type_category')})")
                        print(f"     Size: {file.get('file_size_bytes')} bytes")
                        print(f"     Folder: {file.get('folder_id')}")
                        print(f"     Uploaded: {file.get('upload_datetime')}")
                        print(f"     File ID: {file.get('_id')}")
                        print()
                
                return files
            else:
                print(f"❌ Failed to list files: {response.status_code}")
                print(f"   Error: {response.text}")
                return []
                
        except Exception as e:
            print(f"❌ Exception during file listing: {e}")
            return []


async def test_get_storage_stats():
    """Test GET /api/v2/files/stats endpoint"""
    print("\n" + "="*60)
    print("TEST 4: Get Storage Statistics")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v2/files/stats",
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                stats = result.get('stats', [])
                
                print(f"✅ Retrieved storage statistics")
                print("\nStorage by file type:")
                
                total_files = 0
                total_size = 0
                
                for stat in stats:
                    file_type = stat.get('_id', 'unknown')
                    count = stat.get('count', 0)
                    size_bytes = stat.get('total_size_bytes', 0)
                    size_mb = size_bytes / (1024 * 1024)
                    
                    total_files += count
                    total_size += size_bytes
                    
                    print(f"   {file_type}: {count} files, {size_mb:.2f} MB")
                
                print(f"\nTotal: {total_files} files, {total_size / (1024 * 1024):.2f} MB")
                
                return result
            else:
                print(f"❌ Failed to get storage stats: {response.status_code}")
                print(f"   Error: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Exception during storage stats: {e}")
            return None


async def test_delete_file(file_id):
    """Test DELETE /api/v2/files/{file_id} endpoint"""
    print("\n" + "="*60)
    print("TEST 5: Delete File (Complete Deletion)")
    print("="*60)
    
    if not file_id:
        print("⚠️ No file_id provided, skipping deletion test")
        return False
    
    print(f"Attempting to delete file: {file_id}")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.delete(
                f"{BASE_URL}/api/v2/files/{file_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ File deleted successfully")
                print(f"   Azure deletion: {result.get('azure_deleted', False)}")
                print(f"   Milvus vectors deleted: {result.get('milvus_deleted_count', 0)}")
                print(f"   MongoDB documents deleted: {result.get('mongodb_deleted_count', 0)}")
                print(f"   Registry entry deleted: {result.get('registry_deleted', False)}")
                return True
            else:
                print(f"❌ Failed to delete file: {response.status_code}")
                print(f"   Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Exception during file deletion: {e}")
            return False


async def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "="*80)
    print("UNIFIED FILE REGISTRY SYSTEM - COMPLETE TEST SUITE")
    print("="*80)
    print(f"Testing against: {BASE_URL}")
    print(f"Test folder: {TEST_FOLDER_ID}")
    
    # Test 1: Document upload (creates file in registry)
    document_id = await test_document_upload()
    
    # Test 2: Audio upload (skipped without audio file)
    await test_audio_upload()
    
    # Test 3: List all files
    all_files = await test_list_files()
    
    # Test 4: List files by folder
    folder_files = await test_list_files(folder_id=TEST_FOLDER_ID)
    
    # Test 5: List files by type
    doc_files = await test_list_files(file_type='document')
    
    # Test 6: Get storage stats
    await test_get_storage_stats()
    
    # Test 7: Delete file (if document was uploaded)
    if document_id and all_files:
        # Find the file_id from the uploaded document
        file_to_delete = None
        for file in all_files:
            if file.get('mongodb_collections', {}).get('document_chunked_id') == document_id:
                file_to_delete = file.get('_id')
                break
        
        if file_to_delete:
            await test_delete_file(file_to_delete)
        else:
            print("\n⚠️ Could not find uploaded document in registry for deletion test")
    
    print("\n" + "="*80)
    print("TEST SUITE COMPLETED")
    print("="*80)


def print_usage():
    """Print usage instructions"""
    print("\n" + "="*80)
    print("FILE REGISTRY SYSTEM TEST SCRIPT")
    print("="*80)
    print("\nBEFORE RUNNING THIS SCRIPT:")
    print("1. Ensure the Citra AI Service is running (http://localhost:8085)")
    print("2. Generate a valid JWT token for authentication")
    print("3. Replace JWT_TOKEN in this script with your token")
    print("4. Update TEST_USER_ID and TEST_FOLDER_ID if needed")
    print("\nTO RUN:")
    print("   python test_file_registry_system.py")
    print("\nTO TEST WITH REAL FILES:")
    print("   - Uncomment audio upload test code")
    print("   - Provide paths to real audio/video files")
    print("="*80 + "\n")


if __name__ == "__main__":
    # Check if JWT token is configured
    if JWT_TOKEN == "YOUR_JWT_TOKEN_HERE":
        print_usage()
        print("❌ ERROR: JWT_TOKEN not configured!")
        print("   Please replace 'YOUR_JWT_TOKEN_HERE' with a valid JWT token")
        sys.exit(1)
    
    # Run all tests
    asyncio.run(run_all_tests())
