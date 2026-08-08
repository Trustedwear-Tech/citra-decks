"""
Template Service - Manage document templates with format preservation
Handles template CRUD operations, format-preserving uploads, and template organization
"""

import os
import sys
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient

# Import DocumentParser from utils directory
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'utils'))
from document_parser import DocumentParser
sys.path.pop(0)


class TemplateService:
    """Service for managing document templates with rich formatting"""
    
    def __init__(self, mongo_client: AsyncIOMotorClient, db_name: str):
        """
        Initialize template service
        
        Args:
            mongo_client: MongoDB async client
            db_name: Database name
        """
        self.db = mongo_client[db_name]
        self.collection = self.db['document_templates']
        self.document_parser = DocumentParser()
        
        # Note: Index creation is handled in init_template_service() in main.py

    def _to_serializable(self, value):
        """Safely convert Mongo/Datetime objects to JSON-friendly values."""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [self._to_serializable(v) for v in value]
        if isinstance(value, dict):
            return {k: self._to_serializable(v) for k, v in value.items()}
        return value
    
    async def ensure_indexes(self):
        """Create necessary indexes for template collection (async)"""
        try:
            # Unique index on template_id and user_id
            await self.collection.create_index(
                [("template_id", 1), ("user_id", 1)],
                unique=True,
                background=True
            )
            
            # Index for listing user templates by category
            await self.collection.create_index(
                [("user_id", 1), ("template_category", 1)],
                background=True
            )
            
            # Text index for template name search
            await self.collection.create_index(
                [("template_name", "text"), ("metadata.tags", "text")],
                background=True
            )
            
            # Index for system templates
            await self.collection.create_index(
                [("is_system_template", 1), ("template_category", 1)],
                background=True
            )
            
            print("✅ Template collection indexes created successfully")
        except Exception as e:
            print(f"⚠️ Error creating indexes: {e}")
    
    async def create_template(
        self,
        user_id: str,
        file_path: str,
        file_type: str,
        original_filename: str,
        template_name: str,
        template_category: str = "general",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create new template from uploaded file
        
        Args:
            user_id: User email/ID
            file_path: Path to uploaded file
            file_type: MIME type (application/pdf or application/vnd.openxmlformats-officedocument.wordprocessingml.document)
            original_filename: Original file name
            template_name: User-friendly template name
            template_category: Category (contract, petition, notice, etc.)
            metadata: Additional metadata (tags, jurisdiction, etc.)
        
        Returns:
            template_id: Unique template identifier
        """
        try:
            # Generate template ID
            template_id = str(uuid.uuid4())
            
            # Extract content with format preservation (Markdown-first)
            print(f"📄 Extracting content from {original_filename}...")
            content = await self.document_parser.parse_document(file_path, file_type)
            
            # Get file size for metadata
            file_size = os.path.getsize(file_path)
            
            # Prepare template document
            template_doc = {
                "_id": template_id,
                "template_id": template_id,
                "user_id": user_id,
                "template_name": template_name,
                "template_category": template_category,
                "original_filename": original_filename,
                "file_type": file_type,
                
                # Rich content (Markdown-first)
                "content": {
                    "markdown": content.get("markdown", ""),
                    "html": content.get("html", ""),
                    "plain_text": content.get("plain_text", ""),
                    "structure": content.get("structure", {})
                },
                
                # Metadata
                "metadata": {
                    "word_count": content.get("word_count", 0),
                    "page_count": content.get("page_count", 0),
                    "language": metadata.get("language", "en") if metadata else "en",
                    "jurisdiction": metadata.get("jurisdiction") if metadata else None,
                    "practice_area": metadata.get("practice_area") if metadata else None,
                    "tags": metadata.get("tags", []) if metadata else [],
                    "usage_count": 0,
                    "last_used": None,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "file_size_bytes": file_size
                },
                
                # Access control
                "is_public": False,
                "shared_with": [],
                "is_system_template": False,
                "version": 1,
                "version_history": []
            }
            
            # Insert into database
            await self.collection.insert_one(template_doc)
            
            print(f"✅ Template created successfully: {template_id}")
            return template_id
            
        except Exception as e:
            print(f"❌ Error creating template: {e}")
            raise Exception(f"Failed to create template: {str(e)}")
    
    async def list_templates(
        self,
        user_id: str,
        category: Optional[str] = None,
        search_query: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        include_system: bool = True
    ) -> Dict[str, Any]:
        """
        List user's templates with optional filtering
        
        Args:
            user_id: User email/ID
            category: Filter by category (optional)
            search_query: Search in template name and tags (optional)
            page: Page number (1-indexed)
            per_page: Results per page
            include_system: Include system-provided templates
        
        Returns:
            Dict with templates list and pagination info
        """
        try:
            # Build query
            query = {"$or": [{"user_id": user_id}]}
            
            if include_system:
                query["$or"].append({"is_system_template": True})
            
            if category and category != "all":
                query["template_category"] = category
            
            if search_query:
                query["$text"] = {"$search": search_query}
            
            # Calculate skip
            skip = (page - 1) * per_page
            
            # Get total count
            total_count = await self.collection.count_documents(query)
            
            # Fetch templates (without full content for list view)
            cursor = self.collection.find(
                query,
                {
                    "template_id": 1,
                    "template_name": 1,
                    "template_category": 1,
                    "original_filename": 1,
                    "file_type": 1,
                    "metadata.word_count": 1,
                    "metadata.page_count": 1,
                    "metadata.tags": 1,
                    "metadata.usage_count": 1,
                    "metadata.last_used": 1,
                    "metadata.created_at": 1,
                    "is_system_template": 1,
                    "storage.file_size_bytes": 1
                }
            ).sort("metadata.created_at", -1).skip(skip).limit(per_page)
            
            templates = await cursor.to_list(length=per_page)

            # Convert Mongo datetimes and other non-serializables
            templates = [self._to_serializable(t) for t in templates]
            
            # Calculate pagination
            total_pages = (total_count + per_page - 1) // per_page
            has_next = page < total_pages
            has_prev = page > 1
            
            return {
                "templates": templates,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "has_next": has_next,
                    "has_prev": has_prev
                }
            }
            
        except Exception as e:
            print(f"❌ Error listing templates: {e}")
            raise Exception(f"Failed to list templates: {str(e)}")
    
    async def get_template(
        self,
        template_id: str,
        user_id: str,
        include_content: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get template by ID with full content
        
        Args:
            template_id: Template ID
            user_id: User ID (for access control)
            include_content: Whether to include full content (default: True)
        
        Returns:
            Template document or None if not found/unauthorized
        """
        try:
            # Build query with access control
            query = {
                "template_id": template_id,
                "$or": [
                    {"user_id": user_id},
                    {"is_system_template": True},
                    {"shared_with": user_id}
                ]
            }
            
            # Projection (exclude content if not needed)
            projection = None if include_content else {"content": 0}
            
            template = await self.collection.find_one(query, projection)
            
            if template:
                # Update last used timestamp and usage count
                await self.collection.update_one(
                    {"template_id": template_id},
                    {
                        "$set": {"metadata.last_used": datetime.utcnow()},
                        "$inc": {"metadata.usage_count": 1}
                    }
                )
            
            return template
            
        except Exception as e:
            print(f"❌ Error getting template: {e}")
            return None
    
    async def update_template(
        self,
        template_id: str,
        user_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update template metadata or content
        
        Args:
            template_id: Template ID
            user_id: User ID (only owner can update)
            updates: Fields to update
        
        Returns:
            True if updated, False otherwise
        """
        try:
            # Only owner can update (not system templates)
            query = {
                "template_id": template_id,
                "user_id": user_id,
                "is_system_template": False
            }
            
            # Add updated_at timestamp
            updates["metadata.updated_at"] = datetime.utcnow()
            
            result = await self.collection.update_one(
                query,
                {"$set": updates}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            print(f"❌ Error updating template: {e}")
            return False
    
    async def delete_template(
        self,
        template_id: str,
        user_id: str
    ) -> bool:
        """
        Delete template (owner only)
        
        Args:
            template_id: Template ID
            user_id: User ID (only owner can delete)
        
        Returns:
            True if deleted, False otherwise
        """
        try:
            # Get template first to get blob path
            template = await self.collection.find_one({
                "template_id": template_id,
                "user_id": user_id,
                "is_system_template": False
            })
            
            if not template:
                return False
            
            # Delete from database (no blob storage needed)
            result = await self.collection.delete_one({
                "template_id": template_id,
                "user_id": user_id
            })
            
            return result.deleted_count > 0
            
        except Exception as e:
            print(f"❌ Error deleting template: {e}")
            return False
    
    async def duplicate_template(
        self,
        template_id: str,
        user_id: str,
        new_name: str
    ) -> Optional[str]:
        """
        Duplicate template for customization
        
        Args:
            template_id: Source template ID
            user_id: User ID
            new_name: Name for duplicated template
        
        Returns:
            New template ID or None if failed
        """
        try:
            # Get source template
            source_template = await self.get_template(template_id, user_id, include_content=True)
            
            if not source_template:
                return None
            
            # Create new template ID
            new_template_id = str(uuid.uuid4())
            
            # Prepare new template document
            new_template = {
                **source_template,
                "_id": new_template_id,
                "template_id": new_template_id,
                "user_id": user_id,
                "template_name": new_name,
                "is_system_template": False,
                "metadata": {
                    **source_template.get("metadata", {}),
                    "usage_count": 0,
                    "last_used": None,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
            
            # Note: We don't copy the blob, just reference the content
            # User's copy will use the same content but can be modified later
            
            # Insert new template
            await self.collection.insert_one(new_template)
            
            print(f"✅ Template duplicated: {template_id} -> {new_template_id}")
            return new_template_id
            
        except Exception as e:
            print(f"❌ Error duplicating template: {e}")
            return None
    
    async def get_categories(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all categories with template counts
        
        Args:
            user_id: User ID
        
        Returns:
            List of categories with counts
        """
        try:
            pipeline = [
                {
                    "$match": {
                        "$or": [
                            {"user_id": user_id},
                            {"is_system_template": True}
                        ]
                    }
                },
                {
                    "$group": {
                        "_id": "$template_category",
                        "count": {"$sum": 1}
                    }
                },
                {
                    "$sort": {"count": -1}
                }
            ]
            
            cursor = self.collection.aggregate(pipeline)
            categories = await cursor.to_list(length=None)
            
            return [
                {"category": cat["_id"], "count": cat["count"]}
                for cat in categories
            ]
            
        except Exception as e:
            print(f"❌ Error getting categories: {e}")
            return []
