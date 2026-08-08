"""
Draft Generation API for Legal Document Drafting
Generates modified/drafted documents from templates using LLM API
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging
from datetime import datetime
import os

from bson import ObjectId
from citra_auth import get_secure_user_id
from citra_mongo import get_mongo_client, get_async_mongo_client

# Import draft service
from draft.draft_service import draft_service

# Import template service
# from api.templates import template_service  # Moved inside function to avoid import timing issues

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


class DraftRequest(BaseModel):
    """Request model for draft generation"""
    user_id: str
    document_id: str
    query: str
    conversation_history: Optional[list] = None  # List of {role, content, timestamp}
    mode: str = "modify"  # modify, generate, transform
    options: Optional[Dict[str, Any]] = None


class TemplateDraftRequest(BaseModel):
    """Request model for template-based draft generation"""
    user_id: str
    template_id: str  # Template ID instead of document_id
    query: str
    conversation_history: Optional[list] = None
    mode: str = "modify"
    options: Optional[Dict[str, Any]] = None


@router.post("/api/draft/generate")
async def generate_draft(data: DraftRequest, req: Request):
    """
    Generate or modify a legal document based on user instructions
    
    Args:
        data: DraftRequest containing user_id, document_id, query, mode, options
        req: FastAPI Request object for accessing user authentication state
        
    Returns:
        JSON response with drafted document, diff, and metadata
    """
    try:
        # SECURITY: Use authenticated user_id from JWT token, not from request body
        user_id = get_secure_user_id(req)
        
        logger.info(f"📝 Draft generation request from user: {user_id}")
        logger.info(f"📝 Document ID: {data.document_id}")
        logger.info(f"📝 Query: {data.query}")
        logger.info(f"📝 Mode: {data.mode}")
        logger.info(f"📝 Conversation history: {len(data.conversation_history) if data.conversation_history else 0} messages")
        
        # Validate inputs
        if not data.document_id or not data.query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="document_id and query are required"
            )
        
        user_email = getattr(req.state, 'user_email', None)
        
        # Fetch document from MongoDB (chunk_index=0 contains metadata)
        try:
            document = documents_collection.find_one({
                "document_id": data.document_id,
                "user_id": user_id,
                "chunk_index": 0
            })
            
            if not document:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document not found: {data.document_id}"
                )
            
            logger.info(f"✅ Document found: {document.get('topic_or_filename', 'Untitled')}")
            
            # Get all text chunks for this document (chunk_index >= 0)
            all_chunks = list(documents_collection.find({
                "document_id": data.document_id,
                "user_id": user_id,
                "chunk_index": {"$gte": 0}
            }).sort("chunk_index", 1))
            
            logger.info(f"📦 Found {len(all_chunks)} chunks for document {data.document_id}")
            
        except Exception as e:
            logger.error(f"❌ Database error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch document: {str(e)}"
            )
        
        # Extract and concatenate document content from all chunks
        document_content = ""
        for chunk in all_chunks:
            chunk_text = chunk.get("metadata", {}).get("text", "")
            if chunk_text:
                document_content += chunk_text + "\n\n"
        
        document_content = document_content.strip()
        
        if not document_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document has no content available for drafting"
            )
        
        logger.info(f"📄 Document content length: {len(document_content)} characters")
        
        # Generate draft using draft service
        result = await draft_service.generate_draft(
            document_content=document_content,
            query=data.query,
            conversation_history=data.conversation_history or [],
            mode=data.mode,
            options=data.options or {},
            user_id=user_id,
            user_email=user_email
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Failed to generate draft")
            )
        
        logger.info("✅ Draft generated successfully")
        
        # Return response
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=result
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        error_str = str(e)
        logger.error(f"❌ Unexpected error in draft generation: {error_str}", exc_info=True)
        
        # Check for credit errors and raise HTTP 402
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {error_str}"
        )


@router.get("/api/draft/health")
async def health_check():
    """Health check endpoint for draft service"""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "service": "draft",
            "timestamp": datetime.now().isoformat()
        }
    )


@router.post("/api/draft/generate-from-template")
async def generate_draft_from_template(data: TemplateDraftRequest, req: Request):
    """
    Generate draft from template with format preservation (Markdown-first)
    
    Args:
        data: TemplateDraftRequest containing user_id, template_id, query, mode, options
        req: FastAPI Request object for accessing user authentication state
        
    Returns:
        JSON response with drafted document (markdown + html), diff, and metadata
    """
    try:
        # SECURITY: Use authenticated user_id from JWT token, not from request body
        user_id = get_secure_user_id(req)
        
        logger.info(f"📝 Template-based draft request from user: {user_id}")
        logger.info(f"📝 Template ID: {data.template_id}")
        logger.info(f"📝 Query: {data.query}")
        logger.info(f"📝 Mode: {data.mode}")
        
        # Validate inputs
        if not data.template_id or not data.query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="template_id and query are required"
            )
        
        user_email = getattr(req.state, 'user_email', None)
        logger.info(f"📧 User email: {user_email}")
        
        # Import template service here to get the current value
        from api.templates import template_service
        
        # Debug: Check template service
        logger.info(f"🔍 Template service available: {template_service is not None}")
        
        # Fetch template from document_templates collection
        if template_service is None:
            logger.error("❌ Template service is None - service not initialized")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Template service not initialized"
            )
        
        logger.info("🔍 Fetching template...")
        try:
            logger.info(f"🔍 Calling get_template with template_id={data.template_id}, user_id={user_id}")
            template = await template_service.get_template(
                template_id=data.template_id,
                user_id=user_id,
                include_content=True
            )
            logger.info(f"🔍 get_template returned: {template is not None}")
            
            if not template:
                logger.warning(f"⚠️ Template not found: {data.template_id} for user {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template not found or access denied: {data.template_id}"
                )
            
            logger.info(f"✅ Template found: {template.get('template_name', 'Untitled')}")
            
        except Exception as e:
            logger.error(f"❌ Error fetching template: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch template: {str(e)}"
            )
        
        # Extract template content (Markdown-first)
        template_content = template.get("content", {})
        
        if not template_content.get("markdown") and not template_content.get("plain_text"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Template has no content available for drafting"
            )
        
        logger.info(f"📄 Template content (Markdown): {len(template_content.get('markdown', ''))} characters")
        logger.info("🤖 Generating draft from template...")
        
        # Check draft service
        logger.info(f"🔍 Draft service available: {draft_service is not None}")
        
        # Generate draft using template service
        result = await draft_service.generate_draft_from_template(
            template_content=template_content,
            query=data.query,
            conversation_history=data.conversation_history or [],
            mode=data.mode,
            options=data.options or {},
            preserve_format=True,  # Always preserve format for templates
            user_id=user_id,
            user_email=user_email
        )
        
        logger.info(f"📋 Draft generation result: success={result.get('success')}, has_content={bool(result.get('drafted_content'))}")
        
        if not result.get("success"):
            logger.error(f"❌ Draft generation failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Failed to generate draft from template")
            )
        
        logger.info("✅ Draft generated successfully from template")
        
        # Return response with markdown and html
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=result
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        error_str = str(e)
        logger.error(f"❌ Unexpected error in template draft generation: {error_str}", exc_info=True)
        
        # Check for credit errors and raise HTTP 402
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {error_str}"
        )
