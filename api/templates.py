"""
Template API - REST endpoints for template management
Handles template upload, listing, retrieval, and deletion
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from typing import Optional, List
import uuid
import os
import json
import tempfile
from datetime import datetime

from services.template_service import TemplateService
from citra_auth import get_secure_user_id
from citra_mongo import get_mongo_client

# Initialize router
router = APIRouter(prefix="/api/templates", tags=["templates"])

# Initialize service (will be set in main.py)
template_service: Optional[TemplateService] = None


async def init_template_service_async(mongo_client, db_name: str):
    """Initialize template service with MongoDB client (async)"""
    global template_service
    template_service = TemplateService(mongo_client, db_name)
    await template_service.ensure_indexes()
    print("✅ Template service initialized")


def init_template_service(mongo_client, db_name: str):
    """Initialize template service with MongoDB client (sync wrapper)"""
    global template_service
    template_service = TemplateService(mongo_client, db_name)
    print("✅ Template service initialized")


@router.post("/upload")
async def upload_template(
    request: Request,
    file: UploadFile = File(...),
    template_name: str = Form(...),
    template_category: str = Form("general"),
    metadata: Optional[str] = Form(None)  # JSON string
):
    """
    Upload new template
    
    Request:
        - file: PDF or DOCX file
        - template_name: User-friendly name
        - template_category: Category (contract, petition, notice, etc.)
        - metadata: Optional JSON with tags, jurisdiction, practice_area
    
    Response:
        {
            "success": true,
            "template_id": "uuid",
            "template_name": "Sale Agreement Template"
        }
    """
    try:
        user_id = get_secure_user_id(request)
        
        # Validate file type
        allowed_types = [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ]
        
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Only PDF and DOCX files are supported"
            )
        
        # Validate file size (max 50MB)
        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
        file_content = await file.read()
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail="File size exceeds 50MB limit"
            )
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as temp_file:
            temp_file.write(file_content)
            temp_path = temp_file.name
        
        try:
            # Parse metadata if provided
            metadata_dict = json.loads(metadata) if metadata else {}
            
            # Create template
            template_id = await template_service.create_template(
                user_id=user_id,
                file_path=temp_path,
                file_type=file.content_type,
                original_filename=file.filename,
                template_name=template_name,
                template_category=template_category,
                metadata=metadata_dict
            )
            
            return JSONResponse({
                "success": True,
                "template_id": template_id,
                "template_name": template_name
            })
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error uploading template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload template: {str(e)}"
        )


@router.get("/list")
async def list_templates(
    request: Request,
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    include_system: bool = Query(True)
):
    """
    List user's templates with filtering and pagination
    
    Query Parameters:
        - category: Filter by category (optional)
        - search: Search in template name and tags (optional)
        - page: Page number (1-indexed)
        - per_page: Results per page (1-100)
        - include_system: Include system templates (default: true)
    
    Response:
        {
            "templates": [...],
            "pagination": {
                "page": 1,
                "per_page": 20,
                "total_count": 50,
                "total_pages": 3,
                "has_next": true,
                "has_prev": false
            }
        }
    """
    try:
        user_id = get_secure_user_id(request)
        
        result = await template_service.list_templates(
            user_id=user_id,
            category=category,
            search_query=search,
            page=page,
            per_page=per_page,
            include_system=include_system
        )
        
        return JSONResponse(result)
    
    except Exception as e:
        print(f"❌ Error listing templates: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list templates: {str(e)}"
        )


@router.get("/categories")
async def get_categories(request: Request):
    """
    Get all template categories with counts
    
    Response:
        {
            "categories": [
                {"category": "contract", "count": 15},
                {"category": "petition", "count": 8},
                ...
            ]
        }
    """
    try:
        user_id = get_secure_user_id(request)
        
        categories = await template_service.get_categories(user_id)
        
        return JSONResponse({"categories": categories})
    
    except Exception as e:
        print(f"❌ Error getting categories: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get categories: {str(e)}"
        )


@router.get("/{template_id}")
async def get_template(
    request: Request,
    template_id: str,
    include_content: bool = Query(True)
):
    """
    Get template by ID with full content
    
    Path Parameters:
        - template_id: Template ID
    
    Query Parameters:
        - include_content: Include full content (default: true)
    
    Response:
        {
            "template_id": "uuid",
            "template_name": "Sale Agreement",
            "template_category": "contract",
            "content": {
                "markdown": "# Sale Agreement...",
                "html": "<h1>Sale Agreement</h1>...",
                "plain_text": "Sale Agreement...",
                "structure": {...}
            },
            "metadata": {...},
            ...
        }
    """
    try:
        user_id = get_secure_user_id(request)
        
        template = await template_service.get_template(
            template_id=template_id,
            user_id=user_id,
            include_content=include_content
        )
        
        if not template:
            raise HTTPException(
                status_code=404,
                detail="Template not found or access denied"
            )
        
        return JSONResponse(template)
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get template: {str(e)}"
        )


@router.put("/{template_id}")
async def update_template(
    request: Request,
    template_id: str,
    template_name: Optional[str] = Form(None),
    template_category: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None)  # JSON string
):
    """
    Update template metadata
    
    Path Parameters:
        - template_id: Template ID
    
    Form Parameters:
        - template_name: New template name (optional)
        - template_category: New category (optional)
        - metadata: Updated metadata JSON (optional)
    
    Response:
        {
            "success": true,
            "message": "Template updated successfully"
        }
    """
    try:
        user_id = get_secure_user_id(request)
        
        # Build updates dict
        updates = {}
        
        if template_name:
            updates["template_name"] = template_name
        
        if template_category:
            updates["template_category"] = template_category
        
        if metadata:
            metadata_dict = json.loads(metadata)
            for key, value in metadata_dict.items():
                updates[f"metadata.{key}"] = value
        
        if not updates:
            raise HTTPException(
                status_code=400,
                detail="No updates provided"
            )
        
        success = await template_service.update_template(
            template_id=template_id,
            user_id=user_id,
            updates=updates
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Template not found or access denied"
            )
        
        return JSONResponse({
            "success": True,
            "message": "Template updated successfully"
        })
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update template: {str(e)}"
        )


@router.delete("/{template_id}")
async def delete_template(
    request: Request,
    template_id: str
):
    """
    Delete template (owner only)
    
    Path Parameters:
        - template_id: Template ID
    
    Response:
        {
            "success": true,
            "message": "Template deleted successfully"
        }
    """
    try:
        user_id = get_secure_user_id(request)
        
        success = await template_service.delete_template(
            template_id=template_id,
            user_id=user_id
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Template not found or access denied"
            )
        
        return JSONResponse({
            "success": True,
            "message": "Template deleted successfully"
        })
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error deleting template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete template: {str(e)}"
        )


@router.post("/{template_id}/duplicate")
async def duplicate_template(
    request: Request,
    template_id: str,
    new_name: str = Form(...)
):
    """
    Duplicate template for customization
    
    Path Parameters:
        - template_id: Source template ID
    
    Form Parameters:
        - new_name: Name for duplicated template
    
    Response:
        {
            "success": true,
            "template_id": "new-uuid",
            "template_name": "Copy of Original"
        }
    """
    try:
        user_id = get_secure_user_id(request)
        
        new_template_id = await template_service.duplicate_template(
            template_id=template_id,
            user_id=user_id,
            new_name=new_name
        )
        
        if not new_template_id:
            raise HTTPException(
                status_code=404,
                detail="Template not found or access denied"
            )
        
        return JSONResponse({
            "success": True,
            "template_id": new_template_id,
            "template_name": new_name
        })
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error duplicating template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to duplicate template: {str(e)}"
        )
