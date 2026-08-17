# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

# ============================  File Management Module  =============================
# Purpose: Centralized file handling with consistent filename usage
# Features: Duplicate checking, cleanup, and filename preservation
# ----------------------------------------------------------------------------------------

import os
import logging
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
# Pinecone import removed - migrated to Milvus/Zilliz
from bson import ObjectId
from utils import sanitize_container_name
from models.unified_metadata_schema import UnifiedMetadataSchema
from config.milvus_config import get_collection_name

logger = logging.getLogger(__name__)

class FileManager:
    """
    Centralized file management with consistent filename handling.
    Ensures original filenames are preserved and used everywhere.
    """

    def __init__(self, mongo_client: AsyncIOMotorClient, mongo_db_name: str):
        self.mongo_client = mongo_client
        self.mongo_db_name = mongo_db_name
        self._milvus_client = None

    def _get_milvus_client(self):
        """Get Milvus client (always fetch fresh singleton)"""
        from config.milvus_config import get_milvus_client
        self._milvus_client = get_milvus_client()
        return self._milvus_client

    def validate_filename(self, filename: str) -> str:
        """
        Validate and return the filename as-is (no alterations).
        Original filename is preserved.
        """
        if not filename or not isinstance(filename, str):
            raise ValueError("Filename must be a non-empty string")

        # Remove any path separators to prevent directory traversal
        filename = filename.replace('/', '').replace('\\', '')

        # Basic sanitization while preserving original name
        # Remove only truly dangerous characters, keep the rest
        dangerous_chars = ['<', '>', ':', '"', '|', '?', '*']
        for char in dangerous_chars:
            filename = filename.replace(char, '')

        return filename.strip()

    async def check_filename_exists(self, user_id: str, filename: str, folder_id: Optional[str] = None) -> bool:
        """
        Check if a file with the given filename already exists for the user.
        Returns True if exists, False otherwise.
        
        Note: document_chunked collection stores filename without extension in 'topic_or_filename' 
        and extension with dot in 'file_type' (e.g., ".pdf")
        """
        try:
            db = self.mongo_client[self.mongo_db_name]

            # Extract filename without extension and the extension itself
            # Example: "document.pdf" -> topic_or_filename="document", file_type=".pdf"
            filename_base, file_ext = os.path.splitext(filename)
            file_ext_lower = file_ext.lower() if file_ext else ""

            logger.info(f"🔍 Checking for duplicate: filename='{filename}', base='{filename_base}', ext='{file_ext_lower}'")

            # Check in document_chunked collection (primary collection for documents)
            # Match topic_or_filename (without extension) and file_type (extension with dot)
            chunk_query = {
                "user_id": user_id,
                "topic_or_filename": filename_base,
            }
            
            # Only add file_type to query if we have an extension
            if file_ext_lower:
                chunk_query["file_type"] = file_ext_lower
            
            if folder_id:
                chunk_query["folder_id"] = folder_id

            logger.info(f"🔍 Checking document_chunked with query: {chunk_query}")

            chunk_exists = await db.document_chunked.find_one(chunk_query)
            if chunk_exists:
                logger.info(f"📄 Found existing chunk: {chunk_exists.get('_id')}, document_id: {chunk_exists.get('document_id')}")
                return True

            # Check transcripts collection (for audio files)
            # Transcripts use topic_or_filename for the filename
            transcript_query = {
                "user_id": user_id,
                "topic_or_filename": filename
            }
            
            if folder_id:
                transcript_query["folder_id"] = folder_id
            
            logger.info(f"🔍 Checking transcripts with query: {transcript_query}")
            
            transcript_exists = await db.transcripts.find_one(transcript_query)
            if transcript_exists:
                logger.info(f"📄 Found existing transcript: {transcript_exists.get('_id')}")
                return True

            logger.info(f"📄 No existing file found for: {filename}")
            return False

        except Exception as e:
            logger.error(f"Error checking filename existence: {e}")
            return False

    async def get_existing_file_info(self, user_id: str, filename: str, folder_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get information about an existing file with the given filename.
        Returns file info dict or None if not found.
        
        Note: document_chunked collection stores filename without extension in 'topic_or_filename' 
        and extension with dot in 'file_type' (e.g., ".pdf")
        """
        try:
            db = self.mongo_client[self.mongo_db_name]

            # Extract filename without extension and the extension itself
            filename_base, file_ext = os.path.splitext(filename)
            file_ext_lower = file_ext.lower() if file_ext else ""

            # Check document_chunked collection (primary collection for documents)
            chunk_query = {
                "user_id": user_id,
                "topic_or_filename": filename_base,
            }
            
            if file_ext_lower:
                chunk_query["file_type"] = file_ext_lower
            
            if folder_id:
                chunk_query["folder_id"] = folder_id

            chunk = await db.document_chunked.find_one(chunk_query)
            if chunk:
                # Reconstruct full filename from topic_or_filename and file_type
                reconstructed_filename = chunk.get("topic_or_filename", "") + chunk.get("file_type", "")
                return {
                    "type": "chunk",
                    "id": str(chunk["_id"]),
                    "document_id": chunk.get("document_id", ""),
                    "filename": reconstructed_filename,
                    "topic_or_filename": chunk.get("topic_or_filename", ""),
                    "file_type": chunk.get("file_type", ""),
                    "folder_id": chunk.get("folder_id"),
                    "created_at": chunk.get("created_at")
                }

            # Check transcripts collection (for audio files)
            transcript_query = {
                "user_id": user_id,
                "topic_or_filename": filename
            }
            
            if folder_id:
                transcript_query["folder_id"] = folder_id
            
            transcript = await db.transcripts.find_one(transcript_query)
            if transcript:
                # Reconstruct full filename
                topic_or_filename = transcript.get("topic_or_filename", "")
                ext = transcript.get("file_type", "")
                reconstructed_filename = topic_or_filename + ext if ext else topic_or_filename
                
                return {
                    "type": "transcript",
                    "id": str(transcript["_id"]),
                    "filename": reconstructed_filename,
                    "topic_or_filename": topic_or_filename,
                    "file_type": ext,
                    "folder_id": transcript.get("folder_id"),
                    "created_at": transcript.get("created_at")
                }

            return None

        except Exception as e:
            logger.error(f"Error getting existing file info: {e}")
            return None

    async def cleanup_existing_file(self, user_id: str, filename: str, folder_id: Optional[str] = None) -> bool:
        """
        Clean up existing file from all storage locations.
        Returns True if cleanup successful, False otherwise.
        
        Note: document_chunked collection stores filename without extension in 'topic_or_filename' 
        and extension with dot in 'file_type' (e.g., ".pdf")
        """
        try:
            db = self.mongo_client[self.mongo_db_name]

            # Get file info first
            file_info = await self.get_existing_file_info(user_id, filename, folder_id)
            logger.info(f"🧹 Cleaning up file: {filename}, info: {file_info}")
            if not file_info:
                logger.warning(f"File {filename} not found for cleanup")
                return True  # Not an error if file doesn't exist

            success = True

            # Extract filename without extension and the extension itself
            filename_base, file_ext = os.path.splitext(filename)
            file_ext_lower = file_ext.lower() if file_ext else ""

            # Build query for document_chunked collection
            chunk_query = {
                "user_id": user_id,
                "topic_or_filename": filename_base
            }
            if file_ext_lower:
                chunk_query["file_type"] = file_ext_lower
            if folder_id:
                chunk_query["folder_id"] = folder_id

            # Delete from S3 using files_service
            try:
                from services.files_service import FilesService
                from bucket import delete_file
                
                files_service = FilesService(self.mongo_client, self.mongo_db_name)
                
                # Get file ID - prioritize document_id, fallback to transcript/chunk ID
                file_id = file_info.get("document_id") or file_info.get("id")
                
                if file_id:
                    # Get S3 URL from files collection (single source of truth)
                    file_resources = await files_service.get_file_resources(file_id, user_id)
                    
                    if file_resources and file_resources.get("s3_url"):
                        s3_url = file_resources["s3_url"]
                        
                        # Extract S3 key from URL
                        if ".amazonaws.com/" in s3_url:
                            s3_key = s3_url.split(".amazonaws.com/")[-1]
                        elif "s3://" in s3_url:
                            s3_key = s3_url.split("s3://", 1)[-1].split("/", 1)[-1]
                        else:
                            s3_key = s3_url  # Fallback
                        
                        # Delete from S3
                        if delete_file(s3_key):
                            logger.info(f"🗑️ Deleted from S3: {s3_key}")
                            
                            # Delete from files registry
                            await files_service.delete_file(file_id, user_id)
                            logger.info(f"🗑️ Deleted from files registry: {file_id}")
                        else:
                            logger.warning(f"⚠️ S3 deletion failed for {s3_key}")
                    else:
                        logger.warning(f"⚠️ No S3 URL found in files collection for {file_id}")
                else:
                    logger.warning(f"⚠️ No file ID found for deletion")
                    
            except Exception as e:
                # Log S3 errors but don't fail the deletion process
                logger.warning(f"⚠️ S3 deletion failed (continuing): {e}")
                # Don't set success = False, allow process to continue

            # Delete from Milvus using filter expressions (migrated from Pinecone)
            try:
                milvus_client = self._get_milvus_client()
                if milvus_client:
                    collection_name = get_collection_name()

                    document_ids = []

                    # Handle transcripts differently - use transcript_id directly as document_id
                    if file_info.get("type") == "transcript":
                        # For transcripts, the transcript_id is the document_id for vectors
                        transcript_id = file_info.get("id")
                        if transcript_id:
                            document_ids = [transcript_id]
                            logger.info(f"🗑️ Using transcript_id '{transcript_id}' as document_id for vector deletion")
                    else:
                        # For documents, find all chunks matching the filename to get document_ids
                        chunks = await db.document_chunked.find(chunk_query).to_list(length=None)
                        document_ids = list(set(chunk.get("document_id") for chunk in chunks if chunk.get("document_id")))

                        # Also check for direct vector_chunks mappings (for audio transcripts and other direct embeddings)
                        mapping_collection = db["milvus_chunks"]  # Vector mapping collection
                        
                        # Build vector mapping query
                        vector_mapping_query = {
                            "user_id": user_id,
                            "topic_or_filename": filename_base,
                            "file_type": file_ext_lower
                        }
                        logger.info(f"🗑️ Querying vector mappings with: {vector_mapping_query}")
                        
                        vector_mappings = await mapping_collection.find(vector_mapping_query).to_list(length=None)
                        
                        # Add document_ids from vector mappings
                        for mapping in vector_mappings:
                            if mapping.get("document_id"):
                                document_ids.append(mapping["document_id"])

                        # Remove duplicates
                        document_ids = list(set(document_ids))

                    if document_ids:
                        vector_ids = []

                        for doc_id in document_ids:
                            mapping_query = {"document_id": doc_id, "user_id": user_id}
                            mappings = await db["milvus_chunks"].find(mapping_query).to_list(length=None)

                            for mapping in mappings:
                                if "vector_ids" in mapping:
                                    vector_ids.extend(mapping["vector_ids"])
                                elif "vector_id" in mapping:
                                    vector_ids.append(mapping["vector_id"])

                        if vector_ids:
                            # Build Milvus filter expression for deletion
                            vector_ids_str = ", ".join([f"'{vid}'" for vid in vector_ids])
                            milvus_filter = f"chunk_id in [{vector_ids_str}] and user_id == '{user_id}'"
                            
                            logger.info(f"🗑️ Deleting {len(vector_ids)} vectors from Milvus collection '{collection_name}' for {len(document_ids)} documents")
                            
                            # Delete vectors using filter expression (Milvus approach)
                            delete_result = milvus_client.delete(
                                collection_name=collection_name,
                                filter=milvus_filter
                            )
                            
                            logger.info(f"✅ Milvus deletion result: {delete_result}")

                            # Clean up mappings
                            for doc_id in document_ids:
                                await db["milvus_chunks"].delete_many({"document_id": doc_id, "user_id": user_id})
                                logger.info(f"🗑️ Deleted vector mappings for document_id: {doc_id} from MongoDB")
                        else:
                            logger.info("No vector IDs found for cleanup")
                    else:
                        logger.info("No document IDs found for Milvus cleanup")
            except Exception as e:
                logger.error(f"Error deleting from Milvus: {e}")
                success = False

            # Delete from MongoDB collections
            try:
                # Delete from document_chunked (primary collection)
                result = await db.document_chunked.delete_many(chunk_query)
                if result.deleted_count > 0:
                    logger.info(f"🗑️ Deleted {result.deleted_count} chunks from MongoDB")

                # Delete from transcripts
                transcript_query = {
                    "user_id": user_id,
                    "topic_or_filename": filename  # Check topic_or_filename without extension
                }
                
                result = await db.transcripts.delete_many(transcript_query)
                if result.deleted_count > 0:
                    logger.info(f"🗑️ Deleted {result.deleted_count} transcripts from MongoDB")

            except Exception as e:
                logger.error(f"Error deleting from MongoDB: {e}")
                success = False

            # Delete structured_file_metadata for this file
            try:
                if document_ids:
                    from document_manager import (
                        _delete_document_structured_metadata,
                        _delete_document_unstructured_metadata,
                    )

                    for doc_id in document_ids:
                        cleanup_result = await _delete_document_structured_metadata(doc_id, user_id)
                        if cleanup_result.get("success"):
                            logger.info(
                                f"🗑️ Structured metadata cleanup removed {cleanup_result.get('deleted_count', 0)} items for {filename} ({doc_id})"
                            )
                        unstructured_cleanup = await _delete_document_unstructured_metadata(doc_id, user_id)
                        if unstructured_cleanup.get("deleted_count", 0) > 0:
                            logger.info(
                                f"🗑️ Unstructured metadata cleanup removed {unstructured_cleanup['deleted_count']} item(s) for {filename} ({doc_id})"
                            )
            except Exception as e:
                logger.warning(f"⚠️ Structured metadata cleanup failed during file cleanup (non-blocking): {e}")

            return success

        except Exception as e:
            logger.error(f"Error during file cleanup: {e}")
            return False

    async def prepare_file_upload(self, user_id: str, filename: str, folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Prepare for file upload by checking duplicates and cleaning up if necessary.
        Returns dict with upload preparation info.
        """
        # Validate filename
        validated_filename = self.validate_filename(filename)

        # Check if file already exists
        exists = await self.check_filename_exists(user_id, validated_filename, folder_id)

        if exists:
            logger.info(f"📁 File {validated_filename} already exists, cleaning up before upload")
            cleanup_success = await self.cleanup_existing_file(user_id, validated_filename, folder_id)
            if not cleanup_success:
                logger.warning(f"⚠️ Failed to cleanup existing file {validated_filename}, proceeding with upload")

        return {
            "filename": validated_filename,
            "exists": exists,
            "ready_for_upload": True
        }

# Global instance
_file_manager_instance = None

def get_file_manager(mongo_client: AsyncIOMotorClient = None, mongo_db_name: str = None) -> FileManager:
    """Get singleton FileManager instance"""
    global _file_manager_instance

    if _file_manager_instance is None:
        if mongo_client is None or mongo_db_name is None:
            raise ValueError("FileManager not initialized. Call get_file_manager with mongo_client and mongo_db_name first.")

        _file_manager_instance = FileManager(mongo_client, mongo_db_name)

    return _file_manager_instance

def initialize_file_manager(mongo_client: AsyncIOMotorClient, mongo_db_name: str):
    """Initialize the global FileManager instance"""
    global _file_manager_instance
    _file_manager_instance = FileManager(mongo_client, mongo_db_name)