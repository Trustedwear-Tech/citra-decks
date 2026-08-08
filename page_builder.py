"""
Page Builder API - AI-powered page creation with Notion-like capabilities

This module provides endpoints for creating, managing, and sharing dynamic pages
including wiki pages, surveys, dashboards, and visualization pages.

Features:
- Block-based content architecture (TipTap compatible)
- AI-powered page generation from vault data
- Survey creation and response collection
- Public sharing with access control
- Page vectorization for vault enrichment

Endpoints:
- POST /api/v2/pages - Create new page
- GET /api/v2/pages/list - List user's pages
- GET /api/v2/pages/{page_id} - Get page by ID
- PUT /api/v2/pages/{page_id} - Update page
- DELETE /api/v2/pages/{page_id} - Delete page
- POST /api/v2/pages/{page_id}/ai-assist - AI generates/updates blocks
- GET /api/v2/pages/{page_id}/blocks - Get page blocks
- POST /api/v2/pages/{page_id}/blocks - Add block to page
- PUT /api/v2/pages/{page_id}/blocks/{block_id} - Update block
- DELETE /api/v2/pages/{page_id}/blocks/{block_id} - Delete block
- POST /api/v2/pages/{page_id}/share - Generate share link
- GET /api/v2/pages/shared/{share_link} - Public access to shared page
- POST /api/v2/pages/{page_id}/survey/submit - Submit survey response
- GET /api/v2/pages/{page_id}/survey/responses - Get survey responses
- POST /api/v2/pages/{page_id}/vectorize - Trigger vectorization
"""

from typing import Dict, Any, Optional, List, Tuple
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import logging
import json
import uuid
import re
import hashlib
import time
import os
from datetime import datetime, timedelta
import asyncio
from bson import ObjectId
import base64

# Supplementary sources configuration
INCLUDE_SUPPLEMENTARY_DEFAULT = os.getenv("INCLUDE_SUPPLEMENTARY_SOURCES", "true").lower() == "true"

# Local imports
from citra_mongo import get_async_database
from citra_auth import get_current_user
from llm_oss import llm_call
import bucket

logger = logging.getLogger(__name__)

# Create router
page_router = APIRouter(prefix="/api/v2/pages", tags=["Page Builder"])

# ==================== Constants ====================

PAGE_TYPES = ["wiki", "survey", "dashboard", "report", "visualization", "custom"]
BLOCK_TYPES = [
    "paragraph", "heading", "table", "chart", "chartjs", "image", "code", 
    "callout", "divider", "quote", "list", "checklist",
    "survey_text", "survey_multiple_choice", "survey_checkbox", 
    "survey_rating", "survey_scale", "survey_date", "survey_file",
    "dynamic_text", "dynamic_table", "embed",
    "editable_text", "wiki_block", "notes",  # User-editable text blocks
    "diagram", "mermaid", "subpage", "toggle"  # User-created diagrams (protected from AI edits)
]

# Word count limits for AI context management
MAX_PAGE_WORDS = 20000  # Maximum words per page (recommended)
AI_CONTEXT_WORDS = 15000  # Words to send to AI (leave buffer for response)
WORD_COUNT_WARNING = 18000  # Show warning when approaching limit

# ==================== Request/Response Models ====================

class PageOrchestrateRequest(BaseModel):
    """Request for AI orchestrator"""
    page_id: str = Field(..., description="Page ID to edit")
    message: str = Field(..., description="User's natural language request")
    vault_id: Optional[str] = Field(default=None, description="Vault ID for context retrieval")
    selected_block_ids: Optional[List[str]] = Field(default=None, description="Block IDs if in selection mode")
    use_nano_banana: bool = Field(default=False, description="Use premium image generation")
    user_device_id: Optional[str] = Field(default=None, description="User device ID")
    # NEW: Support for UI-driven architecture (no auto-save)
    current_blocks: Optional[List[Dict[str, Any]]] = Field(default=None, description="Current blocks from UI (for preview mode)")
    preview_mode: bool = Field(default=False, description="If true, return blocks to UI instead of saving to DB")

class BlockContent(BaseModel):
    """Block content structure"""
    type: str = Field(..., description="Block type")
    content: Any = Field(default=None, description="Type-specific content")
    order: int = Field(default=0, description="Sort order")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
class CreatePageRequest(BaseModel):
    """Request to create a new page"""
    title: str = Field(default="Untitled Page", description="Page title")
    page_type: str = Field(default="wiki", description="Page type")
    vault_id: Optional[str] = Field(default=None, description="Associated vault/folder ID")
    icon: str = Field(default="📄", description="Page icon emoji")
    prompt: Optional[str] = Field(default=None, description="AI prompt for auto-generation")
    blocks: Optional[List[Dict[str, Any]]] = Field(default=None, description="Initial blocks")
    parent_page_id: Optional[str] = Field(default=None, description="Parent page ID for hierarchy")

class UpdatePageRequest(BaseModel):
    """Request to update a page"""
    title: Optional[str] = None
    page_type: Optional[str] = None
    icon: Optional[str] = None
    blocks: Optional[List[Dict[str, Any]]] = None
    layout_groups: Optional[List[Dict[str, Any]]] = Field(default=None, description="Layout groups for multi-block layouts")

class AIAssistRequest(BaseModel):
    """Request for AI assistance"""
    prompt: str = Field(..., description="User's request for AI")
    context_block_ids: Optional[List[str]] = Field(default=None, description="Blocks to use as context")
    vault_ids: Optional[List[str]] = Field(default=None, description="Vault IDs for data retrieval")

class CreateBlockRequest(BaseModel):
    """Request to create a block"""
    type: str = Field(..., description="Block type")
    content: Any = Field(default=None, description="Block content")
    order: Optional[int] = Field(default=None, description="Sort order")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Block metadata")

class UpdateBlockRequest(BaseModel):
    """Request to update a block"""
    content: Optional[Any] = None
    order: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

class ShareSettingsRequest(BaseModel):
    """Request to configure sharing"""
    is_public: bool = Field(default=False, description="Make publicly accessible")
    permissions: str = Field(default="view", description="view, edit, or comment")
    password: Optional[str] = Field(default=None, description="Optional password protection")
    expires_in_days: Optional[int] = Field(default=None, description="Link expiration in days")
    allowed_emails: Optional[List[str]] = Field(default=None, description="Allowed email addresses")

class SurveySubmitRequest(BaseModel):
    """Request to submit survey response"""
    answers: Dict[str, Any] = Field(..., description="Block ID to answer mapping")
    respondent_email: Optional[str] = Field(default=None, description="Respondent email (if not anonymous)")

# ==================== Helper Functions ====================

def serialize_page(page: dict) -> dict:
    """Convert MongoDB document to JSON-serializable format"""
    if page is None:
        return None
    
    result = {**page}
    if "_id" in result:
        result["_id"] = str(result["_id"])
    if "created_at" in result and isinstance(result["created_at"], datetime):
        result["created_at"] = result["created_at"].isoformat()
    if "updated_at" in result and isinstance(result["updated_at"], datetime):
        result["updated_at"] = result["updated_at"].isoformat()
    
    # Serialize blocks
    if "blocks" in result:
        for block in result["blocks"]:
            if "block_id" not in block:
                block["block_id"] = str(uuid.uuid4())
    
    # Calculate and include word count
    blocks = result.get("blocks", [])
    title = result.get("title", "")
    result["word_count"] = calculate_word_count(blocks, title)
    
    return result

def serialize_block(block: dict) -> dict:
    """Convert block to JSON-serializable format"""
    if block is None:
        return None
    result = {**block}
    if "_id" in result:
        result["_id"] = str(result["_id"])
    return result

def calculate_word_count(blocks: List[dict], title: str = "") -> dict:
    """
    Calculate word count for a page and its blocks.
    Returns word count stats for AI context management.
    """
    total_words = 0
    block_word_counts = {}
    
    # Count words in title
    if title:
        total_words += len(title.split())
    
    for block in blocks:
        block_id = block.get("block_id", "unknown")
        content = block.get("content", {})
        block_words = 0
        
        # Extract text from different block types
        if isinstance(content, dict):
            # Text content
            text = content.get("text", "") or content.get("markdown", "") or ""
            block_words += len(text.split())
            
            # Table content
            if "rows" in content:
                for row in content.get("rows", []):
                    for cell in row:
                        if isinstance(cell, str):
                            block_words += len(cell.split())
            
            # List items
            for item in content.get("items", []):
                if isinstance(item, str):
                    block_words += len(item.split())
                elif isinstance(item, dict):
                    block_words += len(item.get("text", "").split())
            
            # Code content
            if "code" in content:
                block_words += len(content["code"].split())
            
            # Caption
            if "caption" in content:
                block_words += len(content.get("caption", "").split())
                
        elif isinstance(content, str):
            block_words = len(content.split())
        
        block_word_counts[block_id] = block_words
        total_words += block_words
    
    return {
        "total_words": total_words,
        "block_word_counts": block_word_counts,
        "exceeds_limit": total_words > MAX_PAGE_WORDS,
        "exceeds_ai_context": total_words > AI_CONTEXT_WORDS,
        "warning": total_words > WORD_COUNT_WARNING,
        "percentage": min(100, round((total_words / MAX_PAGE_WORDS) * 100, 1))
    }

# ==================== Image Management Helpers ====================

def prepare_blocks_for_ai(blocks: List[dict]) -> Tuple[List[dict], dict]:
    """
    Prepare blocks for AI editing:
    - Replace image blocks with placeholder + description only
    - Replace diagram blocks with protected placeholder (AI should NOT modify)
    - Store mapping for restoration
    - AI NEVER sees aws_url or raw bytes
    
    Returns: (ai_safe_blocks, image_map)
    """
    image_map = {}  # placeholder -> {aws_url, layout, caption, type}
    ai_safe_blocks = []
    
    for block in blocks:
        if block.get("type") == "image":
            placeholder = block.get("placeholder") or f"{{{{IMAGE_{block.get('block_id', uuid.uuid4())}}}}}"
            
            # Store restoration data
            image_map[placeholder] = {
                "aws_url": block.get("aws_url") or block.get("src"),
                "layout": block.get("layout"),
                "caption": block.get("caption", ""),
                "block_id": block.get("block_id"),
                "type": "image"
            }
            
            # AI only sees placeholder and description
            ai_safe_blocks.append({
                "block_id": block.get("block_id"),
                "type": "image",
                "placeholder": placeholder,
                "description": block.get("description", "User uploaded image"),
                "order": block.get("order", 0)
            })
        elif block.get("type") == "diagram":
            # Diagram blocks are PROTECTED - store full data and give AI a simple placeholder
            placeholder = f"{{{{DIAGRAM_PROTECTED_{block.get('block_id', uuid.uuid4())}}}}}"
            
            # Store full restoration data
            image_map[placeholder] = {
                "full_block": block,  # Store the entire block for perfect restoration
                "type": "diagram"
            }
            
            # AI sees only a protected placeholder with info it should NOT modify
            ai_safe_blocks.append({
                "block_id": block.get("block_id"),
                "type": "diagram",
                "placeholder": placeholder,
                "title": block.get("title", "User Diagram"),
                "metadata": {"user_created": True, "protected": True},
                "_ai_instruction": "DO NOT MODIFY OR REMOVE - This is a user-created diagram. Pass through unchanged.",
                "order": block.get("order", 0)
            })
        else:
            ai_safe_blocks.append(block)
    
    return ai_safe_blocks, image_map


def restore_images_after_ai(blocks: List[dict], image_map: dict) -> List[dict]:
    """
    Restore full image and diagram data after AI editing:
    - Match placeholders to stored aws_url, layout, caption
    - Restore diagram blocks exactly as they were (protected)
    - Preserve any description changes AI made for images
    """
    restored_blocks = []
    
    for block in blocks:
        if block.get("type") == "image":
            placeholder = block.get("placeholder")
            
            if placeholder and placeholder in image_map:
                stored = image_map[placeholder]
                if stored.get("type") == "image":
                    # Restore from map, keep AI's description if changed
                    restored_blocks.append({
                        **block,
                        "aws_url": stored["aws_url"],
                        "src": stored["aws_url"],  # Keep src for backward compatibility
                        "layout": stored.get("layout"),
                        "caption": stored.get("caption", block.get("caption", ""))
                    })
                else:
                    restored_blocks.append(block)
            else:
                # New image placeholder from AI - needs generation later
                restored_blocks.append(block)
        elif block.get("type") == "diagram":
            placeholder = block.get("placeholder")
            
            if placeholder and placeholder in image_map:
                stored = image_map[placeholder]
                if stored.get("type") == "diagram" and stored.get("full_block"):
                    # Restore the EXACT original diagram block (protected)
                    full_block = stored["full_block"]
                    full_block["order"] = block.get("order", full_block.get("order", 0))
                    restored_blocks.append(full_block)
                    logger.info(f"🔒 Protected diagram block restored: {block.get('block_id')}")
                else:
                    restored_blocks.append(block)
            else:
                # Diagram without placeholder - keep as-is
                restored_blocks.append(block)
        else:
            restored_blocks.append(block)
    
    return restored_blocks


def summarize_page_for_ai(blocks: List[dict]) -> str:
    """Create a summary of page content for AI context (no image bytes!)"""
    summary_parts = []
    
    for i, block in enumerate(blocks):
        block_type = block.get("type", "unknown")
        content = block.get("content", {})
        
        if block_type == "heading":
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            summary_parts.append(f"- Heading: {text[:100]}")
        elif block_type == "paragraph":
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            summary_parts.append(f"- Paragraph: {text[:100]}...")
        elif block_type == "table":
            headers = content.get("headers", []) if isinstance(content, dict) else []
            summary_parts.append(f"- Table with columns: {', '.join(headers[:5])}")
        elif block_type == "chartjs":
            chart_type = content.get("chart_config", {}).get("type", "chart") if isinstance(content, dict) else "chart"
            summary_parts.append(f"- Chart ({chart_type})")
        elif block_type == "image":
            desc = block.get("description", "image")
            summary_parts.append(f"- Image: {desc[:50]}")
        elif block_type.startswith("survey_"):
            question = content.get("question", "") if isinstance(content, dict) else ""
            summary_parts.append(f"- Survey question: {question[:50]}")
        elif block_type == "list":
            items = content.get("items", []) if isinstance(content, dict) else []
            summary_parts.append(f"- List with {len(items)} items")
        else:
            summary_parts.append(f"- {block_type} block")
    
    return "\n".join(summary_parts) if summary_parts else "Empty page"


def get_content_types(blocks: List[dict]) -> List[str]:
    """Get unique content types from blocks"""
    return list(set(block.get("type", "unknown") for block in blocks))


async def upload_image_to_s3(image_bytes: bytes, page_id: str, user_id: str) -> str:
    """Upload image bytes to S3 and return URL - with deduplication"""
    try:
        # Generate content hash for deduplication
        content_hash = hashlib.md5(image_bytes).hexdigest()
        
        # Check if image with same hash already exists for this user/page
        existing_prefix = f"pages/{user_id}/{page_id}/images/"
        
        # Try to find existing image with same hash
        existing_url = bucket.find_existing_image_by_hash(existing_prefix, content_hash)
        if existing_url:
            logger.info(f"♻️ Image already exists, reusing: {existing_url}")
            return existing_url
        
        # Generate unique key for new image
        image_id = str(uuid.uuid4())[:12]
        timestamp = int(time.time() * 1000)
        
        # S3 key structure with content hash for future deduplication
        s3_key = f"pages/{user_id}/{page_id}/images/{content_hash}_{timestamp}_{image_id}.png"
        
        # Upload to S3
        aws_url = bucket.upload_file(image_bytes, s3_key, "image/png")
        
        logger.info(f"✅ Image uploaded to S3: {aws_url}")
        return aws_url
        
    except Exception as e:
        logger.error(f"❌ Failed to upload image to S3: {e}")
        raise


# ==================== AI Intent Classification ====================

async def classify_intent_with_ai(
    user_message: str,
    mode: str,
    content_types: List[str],
    page_summary: str,
    user_id: str = None,
    sources_summary: dict = None
) -> dict:
    """
    Use AI to classify user intent - NO HARDCODING!
    Returns JSON with intent classification AND supplementary source selection.
    
    Args:
        user_message: User's request
        mode: "full_page" or "selected_content"
        content_types: List of content types in selection/page
        page_summary: Text summary of page for AI context
        user_id: User ID (for source selection)
        sources_summary: Pre-fetched sources summary with prompt_summary
    
    Returns:
        Dict with intent, action_type, and supplementary_sources
    """
    
    # Build sources prompt section if available
    sources_prompt_section = ""
    if sources_summary and sources_summary.get("has_sources"):
        sources_prompt_section = f"""

{sources_summary.get('prompt_summary', '')}

Based on the user's request, select which supplementary sources (if any) would be helpful.
Include the source IDs in supplementary_sources array (e.g., ["sql:table_name", "saas:hubspot"]).
Leave empty [] if the request doesn't need external data or vault data is sufficient."""
    
    system_prompt = """You are analyzing a user's request to edit their page content.
You must classify the user's intent and return a JSON response.

Current Context:
- Mode: {mode} (full_page means editing everything, selected_content means editing only selected items)
- Content types in selection/page: {content_types}
- Page overview:
{page_summary}
{sources_prompt_section}

IMPORTANT: User speaks in domain terms (survey, report, chart, image, table, data, page).
User does NOT know technical terms like "blocks" or internal structure.

Return ONLY valid JSON (no markdown):
{{
    "intent": "clear description of what user wants to do",
    "action_type": "one of: chat_only, edit_text, add_content, add_editable_block, create_chart, create_image, create_table, create_survey, reorganize, delete, format",
    "requires_vault_context": true or false,
    "requires_image_generation": true or false,
    "scope": "full_page or selected_only",
    "confidence": 0.0 to 1.0,
    "clarification_needed": null or "question to ask user if unclear",
    "supplementary_sources": []
}}

Action type guidelines:
- "chat_only": User is just chatting, asking questions, greeting - NO edits needed
- "edit_text": Modify existing text content (rewrite, improve, translate, etc.)
- "add_content": Add new paragraphs, headings, or general content
- "add_editable_block": Add a user-editable text block (wiki, notes, documentation, free-form text area)
- "create_chart": Generate a visualization/chart
- "create_image": Generate an AI image
- "create_table": Generate a table
- "create_survey": Add survey questions
- "reorganize": Reorder, restructure content
- "delete": Remove content
- "format": Change styling, formatting

add_editable_block guidelines:
- Use when user asks for: wiki section, notes area, editable text, documentation block, free-form text
- Use when user says: "add a place to write", "add notes section", "add wiki", "add editable area"

Scope guidelines:
- In selected_content mode, default to "selected_only" unless user explicitly says "whole page", "entire page", etc.
- In full_page mode, default to "full_page"

requires_vault_context guidelines:
- Set true if user mentions "my data", "my vault", "from my files", "based on my documents", etc.
- Set true if user asks for data-driven content (charts with their data, summaries, etc.)

requires_image_generation guidelines:
- Set true ONLY if user explicitly asks to create/generate/make an image
- Do NOT set true for existing images or non-image requests

supplementary_sources guidelines:
- Select sources that contain data relevant to the user's request
- Use IDs like "sql:table_name" or "saas:hubspot" exactly as shown in available sources
- Leave empty [] if vault context alone is sufficient or no data lookup needed
"""
    
    user_prompt = f"""User Message: "{user_message}"

Analyze this request and return the JSON classification."""

    try:
        response = await asyncio.to_thread(lambda: llm_call(
            user_prompt=user_prompt,
            system_prompt=system_prompt.format(
                mode=mode,
                content_types=", ".join(content_types) if content_types else "none",
                page_summary=page_summary,
                sources_prompt_section=sources_prompt_section
            )
        ))
        
        # Parse JSON from response
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        
        result = json.loads(json_str)
        
        # Ensure supplementary_sources exists
        if "supplementary_sources" not in result:
            result["supplementary_sources"] = []
        
        logger.info(f"🧠 Intent classified: {result.get('action_type')} (confidence: {result.get('confidence')}, sources: {result.get('supplementary_sources')})")
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse intent classification: {e}")
        # Default to chat_only on parse failure
        return {
            "intent": "Unable to classify",
            "action_type": "chat_only",
            "requires_vault_context": False,
            "requires_image_generation": False,
            "scope": "full_page",
            "confidence": 0.0,
            "clarification_needed": "I couldn't understand your request. Could you rephrase it?",
            "supplementary_sources": []
        }
    except Exception as e:
        logger.error(f"❌ Intent classification failed: {e}")
        raise


async def generate_chat_response(user_message: str, page_summary: str) -> str:
    """Generate a chat response without editing the page"""
    
    system_prompt = """You are a helpful AI assistant for a page builder application.
The user is chatting with you about their page.

Current page content:
{page_summary}

Respond helpfully to the user's message. If they're asking for help, guide them on how to use the page builder.
Keep responses concise and friendly."""

    try:
        response = await asyncio.to_thread(lambda: llm_call(
            user_prompt=user_message,
            system_prompt=system_prompt.format(page_summary=page_summary)
        ))
        return response.strip()
    except Exception as e:
        logger.error(f"❌ Chat response failed: {e}")
        return "I'm here to help! You can ask me to add content, create charts, generate images, or modify your page."


async def generate_image_description(user_message: str, intent: str, vault_context: str = None) -> str:
    """Generate a detailed image description for AI image generation"""
    
    system_prompt = """You are generating a detailed description for an AI image generator.
Based on the user's request, create a vivid, detailed description that will produce a high-quality image.

Guidelines:
- Be specific about visual elements, colors, lighting, style
- Include artistic style if appropriate (photorealistic, illustration, etc.)
- Keep it focused and coherent
- Maximum 200 words

Return ONLY the image description, nothing else."""

    context_hint = ""
    if vault_context:
        context_hint = f"\n\nContext from user's data:\n{vault_context[:500]}"

    try:
        response = await asyncio.to_thread(lambda: llm_call(
            user_prompt=f"User request: {user_message}\nIntent: {intent}{context_hint}\n\nGenerate the image description:",
            system_prompt=system_prompt
        ))
        return response.strip()
    except Exception as e:
        logger.error(f"❌ Image description generation failed: {e}")
        return user_message  # Fallback to user's message


async def generate_image_with_ai(description: str, use_nano_banana: bool = False) -> bytes:
    """Generate image using AI (image generation backend)"""
    import httpx
    
    try:
        if use_nano_banana:
            # Use image generation API for premium generation
            try:
                from image_gen_api import _generate_single_image
                image_url = await _generate_single_image(
                    prompt=description,
                    width=1024,
                    height=1024,
                    model="runware:400@1"
                )
                
                # Download image from URL
                async with httpx.AsyncClient() as client:
                    response = await client.get(image_url)
                    if response.status_code == 200:
                        return response.content
                    raise ValueError(f"Failed to download image: {response.status_code}")
                    
            except ImportError as e:
                logger.warning(f"Image generation service not available: {e}")
            except Exception as e:
                logger.warning(f"Image generation failed: {e}")
        
        # If image generation was not available above, fall through to error.
        logger.warning("No image generation backend available")
        raise HTTPException(status_code=503, detail="Image generation service not available")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Image generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")


async def edit_blocks_with_ai(
    blocks: List[dict],
    user_message: str,
    intent: dict,
    vault_context: str = None,
    mode: str = "full_page"
) -> List[dict]:
    """Use AI to edit blocks based on user request"""
    
    system_prompt = """You are an AI page editor. Edit the provided blocks based on the user's request.

Current blocks (JSON):
{blocks_json}

User's intent: {intent}
Edit mode: {mode}

{vault_context_section}

IMPORTANT RULES:
1. Return ONLY valid JSON array of blocks
2. For image blocks, ONLY modify the "description" field if needed - NEVER change placeholder or aws_url
3. Preserve block_id for existing blocks
4. For new blocks, generate new block_id using format: block_{{timestamp}}_{{random}}
5. Maintain proper order field values
6. DO NOT remove blocks unless explicitly asked to delete
7. For editable_text/wiki_block/notes blocks, you can edit the text content directly

⚠️ CRITICAL - PROTECTED BLOCKS (DO NOT MODIFY):
8. NEVER modify, remove, or change blocks with type "diagram" - these are USER-CREATED diagrams
9. NEVER modify blocks that have metadata.protected=true or metadata.user_created=true
10. If user EXPLICITLY asks to "edit the diagram", "remove the diagram", "update my diagram" - only then can you modify diagram blocks
11. Treat diagram blocks as placeholder: just pass them through unchanged with format: {{DIAGRAM_PLACEHOLDER: block_id}}

Block types available: paragraph, heading, table, chartjs, image, list, callout, quote, divider, code,
survey_text, survey_multiple_choice, survey_checkbox, survey_rating, survey_scale,
editable_text, wiki_block, notes, diagram

editable_text block format:
{{"type": "editable_text", "title": "Block Title", "content": {{"text": "User-editable content here", "placeholder": "Start typing..."}}, "order": N}}

diagram block format (PROTECTED - copy exactly as-is):
{{"type": "diagram", "block_id": "...", "title": "User Diagram", "content": {{"aws_url": "...", "mermaid_code": "..."}}, "metadata": {{"user_created": true, "protected": true}}, "order": N}}

Return the complete updated blocks array as JSON."""

    vault_section = ""
    if vault_context:
        vault_section = f"Context from user's vault data:\n{vault_context[:2000]}"

    try:
        response = await asyncio.to_thread(lambda: llm_call(
            user_prompt=f"User request: {user_message}\n\nEdit the blocks and return the updated JSON array:",
            system_prompt=system_prompt.format(
                blocks_json=json.dumps(blocks, indent=2),
                intent=intent.get("intent", ""),
                mode=mode,
                vault_context_section=vault_section
            )
        ))
        
        # Parse JSON from response
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        
        result = json.loads(json_str)
        
        # Ensure it's a list
        if isinstance(result, dict) and "blocks" in result:
            result = result["blocks"]
        
        # Validate and add missing block_ids
        for i, block in enumerate(result):
            if "block_id" not in block:
                block["block_id"] = f"block_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            if "order" not in block:
                block["order"] = i
        
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse edited blocks: {e}")
        return blocks  # Return original on failure
    except Exception as e:
        logger.error(f"❌ Block editing failed: {e}")
        raise

async def get_vault_context(
    user_id: str,
    vault_ids: List[str],
    query: str,
    top_k: int = 10,
    include_supplementary: bool = None
) -> List[Dict]:
    """
    Fetch relevant vault data for AI context.
    
    Args:
        user_id: User identifier
        vault_ids: List of vault/folder IDs to search in
        query: Search query for semantic matching
        top_k: Number of top results to return
        include_supplementary: Whether to also fetch from SQL/SaaS sources (AI-routed)
                               Defaults to INCLUDE_SUPPLEMENTARY_SOURCES env var
    
    Returns:
        List of context dictionaries
    """
    # Apply environment variable default if not explicitly provided
    if include_supplementary is None:
        include_supplementary = INCLUDE_SUPPLEMENTARY_DEFAULT
    
    results = []
    
    try:
        from llamaindex_query_engine import UnifiedQueryEngine
        
        engine = UnifiedQueryEngine()
        vault_results = await engine.retrieve_personal_context(
            query=query,
            user_id=user_id,
            top_k=top_k
        )
        results.extend(vault_results)
        
        # Also query personal data if vault_ids provided
        if vault_ids:
            # Build filter for specific folders
            folder_filter = {"vault_id": {"$in": vault_ids}}
            personal_results = await engine._milvus_query(
                vector=engine._get_query_embedding(query),
                filter_expr=f'user_id == "{user_id}" and vault_id in {json.dumps(vault_ids)}',
                top_k=top_k
            )
            results.extend(personal_results)
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch vault context: {e}")
    
    # Optionally fetch supplementary sources (SQL/SaaS)
    if include_supplementary:
        try:
            from composer_query import retrieve_supplementary_context
            
            supp_result = await retrieve_supplementary_context(
                user_id=user_id,
                query=query,
                include_sql=True,
                include_saas=True
            )
            
            if supp_result.get("has_data") and supp_result.get("context_parts"):
                # Convert supplementary text to dict format for consistency
                for i, part in enumerate(supp_result["context_parts"]):
                    results.append({
                        "metadata": {
                            "topic_or_filename": f"Supplementary Source {i+1}",
                            "text": part,
                            "source_type": "supplementary"
                        }
                    })
                logger.info(f"📄 [PAGE_BUILDER] Added {len(supp_result['context_parts'])} supplementary sources")
                
        except Exception as supp_error:
            logger.warning(f"📄 [PAGE_BUILDER] Supplementary fetch failed: {supp_error}")
    
    return results

async def generate_blocks_with_ai(prompt: str, vault_context: List[Dict], page_type: str) -> List[Dict]:
    """Generate TipTap-compatible blocks using AI"""
    
    context_text = ""
    if vault_context:
        context_text = "\n\n".join([
            f"Document: {item.get('metadata', {}).get('topic_or_filename', 'Unknown')}\n{item.get('metadata', {}).get('text', '')[:500]}"
            for item in vault_context[:5]
        ])
    
    system_prompt = f"""You are an AI page builder assistant similar to Notion AI. Generate structured content blocks based on user requests.

Page Type: {page_type}

You must output ONLY valid JSON with the following structure:
{{
    "title": "Page Title",
    "blocks": [
        {{"type": "heading", "content": {{"level": 1, "text": "Title"}}, "order": 0}},
        {{"type": "paragraph", "content": {{"text": "Paragraph text here"}}, "order": 1}},
        {{"type": "editable_text", "title": "Notes", "content": {{"text": "User can edit this text...", "placeholder": "Start typing..."}}, "order": 2}},
        {{"type": "table", "content": {{"headers": ["Col1", "Col2"], "rows": [["A", "B"], ["C", "D"]]}}, "order": 3}},
        {{"type": "chartjs", "title": "My Chart", "content": {{
            "chart_config": {{
                "type": "bar",
                "data": {{
                    "labels": ["Jan", "Feb", "Mar", "Apr"],
                    "datasets": [{{
                        "label": "Sales",
                        "data": [12, 19, 8, 15],
                        "backgroundColor": ["#3B82F6", "#10B981", "#F59E0B", "#EF4444"]
                    }}]
                }},
                "options": {{
                    "plugins": {{
                        "title": {{"display": true, "text": "Monthly Sales"}}
                    }}
                }}
            }}
        }}, "order": 4}},
        {{"type": "list", "content": {{"style": "bullet", "items": ["Item 1", "Item 2"]}}, "order": 5}},
        {{"type": "callout", "content": {{"type": "info", "text": "Important note"}}, "order": 6}},
        {{"type": "quote", "content": {{"text": "Quote text", "author": "Author"}}, "order": 7}}
    ]
}}

IMPORTANT:
- For wiki pages, use "editable_text" blocks for user-editable content (notes, documentation, wiki entries)
- For charts, use type "chartjs" with Chart.js configuration format:
  - type: "bar", "line", "pie", "doughnut", "radar", "polarArea"
  - data: {{ labels: [...], datasets: [{{ label, data, backgroundColor, borderColor }}] }}
  - options: {{ plugins: {{ title: {{ display: true, text: "Title" }} }} }}

Chart colors to use: ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16"]

For survey pages, also include survey blocks:
{{"type": "survey_multiple_choice", "content": {{"question": "Your question?", "options": ["Option A", "Option B", "Option C"], "required": true}}, "order": 7}}
{{"type": "survey_rating", "content": {{"question": "Rate this", "maxRating": 5, "required": true}}, "order": 8}}
{{"type": "survey_text", "content": {{"question": "Your feedback?", "placeholder": "Enter your answer", "required": false}}, "order": 9}}

Available block types: {', '.join(BLOCK_TYPES)}

Generate blocks that best match the user's request. Use the context data to populate content where appropriate.
When user asks for charts/visualizations, ALWAYS use the "chartjs" block type with proper Chart.js config.
When user asks for wiki pages, notes, or editable content, use "editable_text" blocks.
"""

    user_prompt = f"""User Request: {prompt}

{"Context from vault:" if context_text else "No vault context available."}
{context_text if context_text else ""}

Generate a complete page with appropriate blocks. Output ONLY valid JSON, no markdown formatting."""

    try:
        response = await asyncio.to_thread(lambda: llm_call(
            user_prompt=user_prompt,
            system_prompt=system_prompt
        ))
        
        # Parse JSON from response
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        
        result = json.loads(json_str)
        
        # Add block_ids if not present
        blocks = result.get("blocks", [])
        for i, block in enumerate(blocks):
            if "block_id" not in block:
                block["block_id"] = str(uuid.uuid4())
            if "order" not in block:
                block["order"] = i
        
        return {
            "title": result.get("title", "AI Generated Page"),
            "blocks": blocks
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse AI response as JSON: {e}")
        # Return basic structure on parse failure
        return {
            "title": "New Page",
            "blocks": [{
                "block_id": str(uuid.uuid4()),
                "type": "paragraph",
                "content": {"text": f"AI response: {response[:500]}"},
                "order": 0
            }]
        }
    except Exception as e:
        logger.error(f"❌ AI block generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

# ==================== Page CRUD Endpoints ====================

@page_router.post("")
async def create_page(request: CreatePageRequest, current_user: dict = Depends(get_current_user)):
    """Create a new page, optionally with AI-generated content"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        logger.info(f"📄 Creating page for user: {user_id}")
        
        # Initialize page document
        page_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        page_doc = {
            "page_id": page_id,
            "user_id": user_id,
            "vault_id": request.vault_id,
            "title": request.title,
            "page_type": request.page_type if request.page_type in PAGE_TYPES else "wiki",
            "icon": request.icon,
            "blocks": [],
            "share_settings": {
                "is_public": False,
                "share_link": None,
                "allowed_users": [],
                "permissions": "view",
                "password_protected": False,
                "expires_at": None
            },
            "survey_config": {
                "is_survey": request.page_type == "survey",
                "collect_responses": request.page_type == "survey",
                "anonymous_responses": True,
                "response_limit": None
            },
            "survey_responses": [],
            "ai_context": {
                "source_chunks": [],
                "generation_prompts": [],
                "last_ai_update": None
            },
            "created_at": now,
            "updated_at": now,
            "is_vectorized": False,
            "vectorized_at": None,
            "parent_page_id": request.parent_page_id,
            "tags": [],
            "layout_groups": [],
            "depth": 0  # Will be calculated if has parent
        }
        
        # If has parent, calculate depth and update parent's child_pages
        if request.parent_page_id:
            parent_page = await db.pages.find_one({"page_id": request.parent_page_id})
            if parent_page:
                page_doc["depth"] = (parent_page.get("depth", 0) or 0) + 1
                # Add to parent's child_pages list
                await db.pages.update_one(
                    {"page_id": request.parent_page_id},
                    {"$addToSet": {"child_pages": page_id}}
                )
        
        # If AI prompt provided, generate content
        if request.prompt:
            vault_ids = [request.vault_id] if request.vault_id else []
            vault_context = await get_vault_context(user_id, vault_ids, request.prompt)
            
            ai_result = await generate_blocks_with_ai(request.prompt, vault_context, request.page_type)
            
            page_doc["title"] = ai_result.get("title", request.title)
            page_doc["blocks"] = ai_result.get("blocks", [])
            page_doc["ai_context"]["generation_prompts"].append(request.prompt)
            page_doc["ai_context"]["last_ai_update"] = now
            page_doc["ai_context"]["source_chunks"] = [
                item.get("id", "") for item in vault_context[:10]
            ]
        
        # If initial blocks provided, use them
        elif request.blocks:
            for i, block in enumerate(request.blocks):
                if "block_id" not in block:
                    block["block_id"] = str(uuid.uuid4())
                if "order" not in block:
                    block["order"] = i
            page_doc["blocks"] = request.blocks
        
        # Insert into database
        result = await db.pages.insert_one(page_doc)
        
        logger.info(f"✅ Page created: {page_id}")
        
        return {
            "success": True,
            "page": serialize_page(page_doc),
            "blocks": page_doc["blocks"],
            "message": "Page created successfully"
        }
        
    except Exception as e:
        logger.error(f"❌ Page creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@page_router.get("/list")
async def list_pages(
    page_type: Optional[str] = None,
    vault_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """List user's pages with optional filtering"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        # Build query filter
        query = {"user_id": user_id}
        if page_type:
            query["page_type"] = page_type
        if vault_id:
            query["vault_id"] = vault_id
        
        # Fetch pages
        cursor = db.pages.find(query).sort("updated_at", -1).skip(offset).limit(limit)
        pages = await cursor.to_list(length=limit)
        
        # Get total count
        total = await db.pages.count_documents(query)
        
        return {
            "success": True,
            "pages": [serialize_page(p) for p in pages],
            "total": total,
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to list pages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@page_router.get("/{page_id}")
async def get_page(page_id: str, current_user: dict = Depends(get_current_user)):
    """Get a specific page by ID"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        page = await db.pages.find_one({
            "page_id": page_id,
            "user_id": user_id
        })
        
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        return serialize_page(page)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get page: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@page_router.get("/{page_id}/hierarchy")
async def get_page_hierarchy(page_id: str, current_user: dict = Depends(get_current_user)):
    """Get page hierarchy (breadcrumbs + children) for navigation"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        page = await db.pages.find_one({
            "page_id": page_id,
            "user_id": user_id
        })
        
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        # Build breadcrumb path (ancestors)
        breadcrumbs = []
        current = page
        visited = set()  # Prevent infinite loops
        
        while current.get("parent_page_id") and current["parent_page_id"] not in visited:
            visited.add(current.get("page_id"))
            parent = await db.pages.find_one({
                "page_id": current["parent_page_id"],
                "user_id": user_id
            })
            if parent:
                breadcrumbs.insert(0, {
                    "page_id": parent["page_id"],
                    "title": parent.get("title", "Untitled"),
                    "icon": parent.get("icon", "📄")
                })
                current = parent
            else:
                break
        
        # Get child pages
        child_pages = []
        child_page_ids = page.get("child_pages", [])
        if child_page_ids:
            children = await db.pages.find({
                "page_id": {"$in": child_page_ids},
                "user_id": user_id
            }).to_list(100)
            
            for child in children:
                child_word_count = calculate_word_count(child.get("blocks", []), child.get("title", ""))
                child_pages.append({
                    "page_id": child["page_id"],
                    "title": child.get("title", "Untitled"),
                    "icon": child.get("icon", "📄"),
                    "page_type": child.get("page_type", "wiki"),
                    "word_count": child_word_count["total_words"],
                    "updated_at": child.get("updated_at").isoformat() if child.get("updated_at") else None
                })
        
        # Also find pages that reference this page via subpage blocks
        subpage_references = []
        pages_with_refs = await db.pages.find({
            "user_id": user_id,
            "blocks.content.pageId": page_id
        }).to_list(20)
        
        for ref_page in pages_with_refs:
            if ref_page["page_id"] != page_id:
                subpage_references.append({
                    "page_id": ref_page["page_id"],
                    "title": ref_page.get("title", "Untitled"),
                    "icon": ref_page.get("icon", "📄")
                })
        
        return {
            "page_id": page_id,
            "title": page.get("title", "Untitled"),
            "icon": page.get("icon", "📄"),
            "depth": page.get("depth", 0),
            "breadcrumbs": breadcrumbs,
            "child_pages": child_pages,
            "referenced_by": subpage_references,
            "word_count": calculate_word_count(page.get("blocks", []), page.get("title", ""))
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get page hierarchy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@page_router.put("/{page_id}")
async def update_page(
    page_id: str,
    request: UpdatePageRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update a page with dirty checking optimization"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        # Fetch existing page for comparison
        existing_page = await db.pages.find_one({
            "page_id": page_id,
            "user_id": user_id
        })
        
        if not existing_page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        # Build update document - only include changed fields
        update_doc = {}
        has_changes = False
        
        if request.title is not None and request.title != existing_page.get("title"):
            update_doc["title"] = request.title
            has_changes = True
            
        if request.page_type is not None and request.page_type in PAGE_TYPES:
            if request.page_type != existing_page.get("page_type"):
                update_doc["page_type"] = request.page_type
                has_changes = True
                
        if request.icon is not None and request.icon != existing_page.get("icon"):
            update_doc["icon"] = request.icon
            has_changes = True
        
        if request.blocks is not None:
            # Compare blocks using content hash
            existing_blocks = existing_page.get("blocks", [])
            existing_hash = hashlib.md5(json.dumps(existing_blocks, sort_keys=True).encode()).hexdigest()
            
            # Ensure all blocks have IDs
            for i, block in enumerate(request.blocks):
                if "block_id" not in block:
                    block["block_id"] = str(uuid.uuid4())
                if "order" not in block:
                    block["order"] = i
            
            new_hash = hashlib.md5(json.dumps(request.blocks, sort_keys=True).encode()).hexdigest()
            
            if existing_hash != new_hash:
                update_doc["blocks"] = request.blocks
                update_doc["is_vectorized"] = False  # Mark for re-vectorization
                has_changes = True
                logger.info(f"📝 Blocks changed for page {page_id} (hash: {existing_hash[:8]} → {new_hash[:8]})")
            else:
                logger.info(f"⏭️ Blocks unchanged for page {page_id}, skipping save")
        
        if request.layout_groups is not None:
            existing_groups = existing_page.get("layout_groups", [])
            if request.layout_groups != existing_groups:
                update_doc["layout_groups"] = request.layout_groups
                has_changes = True
        
        # Only update if there are actual changes
        if has_changes:
            update_doc["updated_at"] = datetime.utcnow()
            result = await db.pages.update_one(
                {"page_id": page_id, "user_id": user_id},
                {"$set": update_doc}
            )
            
            if result.matched_count == 0:
                raise HTTPException(status_code=404, detail="Page not found")
            
            # Fetch updated page
            page = await db.pages.find_one({"page_id": page_id})
            
            return {
                "success": True,
                "page": serialize_page(page),
                "message": "Page updated successfully",
                "changes_saved": True
            }
        else:
            # No changes - return existing page without DB write
            logger.info(f"⏭️ No changes detected for page {page_id}, skipping DB update")
            return {
                "success": True,
                "page": serialize_page(existing_page),
                "message": "No changes detected",
                "changes_saved": False
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to update page: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@page_router.delete("/{page_id}")
async def delete_page(page_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a page"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        result = await db.pages.delete_one({
            "page_id": page_id,
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Page not found")
        
        logger.info(f"🗑️ Page deleted: {page_id}")
        
        return {
            "success": True,
            "message": "Page deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete page: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== AI Assistance Endpoints ====================

@page_router.post("/{page_id}/ai-assist")
async def ai_assist_page(
    page_id: str,
    request: AIAssistRequest,
    current_user: dict = Depends(get_current_user)
):
    """AI generates or modifies page content based on user request"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        # Get existing page
        page = await db.pages.find_one({
            "page_id": page_id,
            "user_id": user_id
        })
        
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        # Get vault context
        vault_ids = request.vault_ids or ([page.get("vault_id")] if page.get("vault_id") else [])
        vault_context = await get_vault_context(user_id, vault_ids, request.prompt)
        
        # Generate new blocks or modifications
        ai_result = await generate_blocks_with_ai(
            request.prompt, 
            vault_context, 
            page.get("page_type", "wiki")
        )
        
        # Update page with new content
        now = datetime.utcnow()
        existing_blocks = page.get("blocks", [])
        new_blocks = ai_result.get("blocks", [])
        
        # Append new blocks with correct order
        max_order = max([b.get("order", 0) for b in existing_blocks], default=-1)
        for i, block in enumerate(new_blocks):
            block["order"] = max_order + 1 + i
        
        combined_blocks = existing_blocks + new_blocks
        
        await db.pages.update_one(
            {"page_id": page_id},
            {
                "$set": {
                    "blocks": combined_blocks,
                    "updated_at": now,
                    "is_vectorized": False,
                    "ai_context.last_ai_update": now
                },
                "$push": {
                    "ai_context.generation_prompts": request.prompt,
                    "ai_context.source_chunks": {
                        "$each": [item.get("id", "") for item in vault_context[:10]]
                    }
                }
            }
        )
        
        logger.info(f"🤖 AI assist completed for page: {page_id}")
        
        return {
            "success": True,
            "message": f"Added {len(new_blocks)} new blocks",
            "new_blocks": new_blocks,
            "total_blocks": len(combined_blocks)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ AI assist failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== AI Orchestrator Endpoint ====================

@page_router.post("/orchestrate")
async def orchestrate_page_edit(
    request: PageOrchestrateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    AI-driven orchestrator for page editing:
    1. AI classifies user intent (no hardcoding)
    2. Processes request based on classified intent
    3. Updates MongoDB directly
    4. Returns completion signal (NOT block data - UI fetches from DB)
    
    Image handling:
    - AI only sees placeholder + description (never aws_url or bytes)
    - Images stored in AWS S3, URL stored in MongoDB
    - Existing images preserved unless explicitly asked to change
    """
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        preview_mode = request.preview_mode
        logger.info(f"🎯 Orchestrator called for page: {request.page_id}, preview_mode: {preview_mode}, message: {request.message[:100]}...")
        
        # 1. Load page from MongoDB
        page = await db.pages.find_one({
            "page_id": request.page_id,
            "user_id": user_id
        })
        
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        # Use current_blocks from UI if provided (preview mode), otherwise use DB blocks
        if preview_mode and request.current_blocks is not None:
            blocks = request.current_blocks
            logger.info(f"📝 Using {len(blocks)} blocks from UI (preview mode)")
        else:
            blocks = page.get("blocks", [])
        
        # 2. Determine mode and prepare context
        mode = "selected_content" if request.selected_block_ids else "full_page"
        
        # Get target blocks based on selection
        if request.selected_block_ids:
            target_blocks = [b for b in blocks if b.get("block_id") in request.selected_block_ids]
        else:
            target_blocks = blocks
        
        # Summarize page for AI context (no image bytes!)
        page_summary = summarize_page_for_ai(blocks)
        content_types = get_content_types(target_blocks)
        
        # Note: Supplementary sources selection has been removed.
        # SaaS data is now pre-embedded in Milvus and retrieved via semantic search.
        
        # 3. PARALLEL CLASSIFICATION - 2 focused calls instead of 1 heavy call
        # Each call has smaller prompt → faster processing → run in parallel
        try:
            from services.parallel_classifier import classify_page_edit
            classification = await classify_page_edit(
                user_message=request.message,
                page_summary=page_summary,
                mode=mode,
                user_id=user_id
            )
            
            # Convert to legacy format for compatibility
            intent_result = {
                "intent": classification.intent,
                "action_type": classification.action_type,
                "requires_vault_context": classification.requires_vault,
                "requires_image_generation": classification.requires_image,
                "scope": classification.scope,
                "confidence": classification.confidence,
                "clarification_needed": classification.clarification_needed,
                "ai_message": classification.ai_message
            }
            logger.info(f"⚡ [PAGE_BUILDER] Parallel classification: action={classification.action_type}, "
                       f"requires_data={classification.requires_data}")
        except ImportError:
            # Fallback to original classifier if parallel_classifier not available
            logger.warning("📄 [PAGE_BUILDER] Parallel classifier not available, using legacy")
            intent_result = await classify_intent_with_ai(
                user_message=request.message,
                mode=mode,
                content_types=content_types,
                page_summary=page_summary,
                user_id=user_id
            )
        
        logger.info(f"🧠 Intent classified: {intent_result.get('action_type')}")
        
        # 4. Handle clarification if needed
        if intent_result.get("clarification_needed"):
            return {
                "status": "clarification_needed",
                "action_taken": "none",
                "message": intent_result["clarification_needed"]
            }
        
        # 5. Chat-only intent (no edits)
        if intent_result.get("action_type") == "chat_only":
            response_message = await generate_chat_response(request.message, page_summary)
            return {
                "status": "success",
                "action_taken": "none",
                "message": response_message
            }
        
        # 6. Get vault context if needed (SaaS data is now in Milvus)
        vault_context_text = ""
        vault_results = []
        vault_ids_used = []
        if intent_result.get("requires_vault_context"):
            vault_ids_used = [request.vault_id] if request.vault_id else ([page.get("vault_id")] if page.get("vault_id") else [])
            
            vault_results = await get_vault_context(
                user_id, vault_ids_used, request.message
            )
            
            # Build vault context text
            vault_context_text = "\n\n".join([
                f"Document: {item.get('metadata', {}).get('topic_or_filename', 'Unknown')}\n{item.get('metadata', {}).get('text', '')[:500]}"
                for item in vault_results[:5]
            ])
        
        # 7. Process based on AI-determined action type
        action_type = intent_result.get("action_type")
        now = datetime.utcnow()
        
        if action_type == "create_image":
            # Handle image generation
            result = await _handle_image_generation(
                db=db,
                page=page,
                blocks=blocks,
                request=request,
                intent_result=intent_result,
                vault_context=vault_context_text,
                user_id=user_id,
                now=now,
                preview_mode=preview_mode
            )
            return result
        
        elif action_type == "add_editable_block":
            # Handle adding editable text block (wiki, notes, documentation)
            result = await _handle_add_editable_block(
                db=db,
                page=page,
                blocks=blocks,
                request=request,
                intent_result=intent_result,
                user_id=user_id,
                now=now,
                preview_mode=preview_mode
            )
            return result
        
        elif action_type in ["edit_text", "add_content", "create_chart", 
                            "create_table", "create_survey", "reorganize", 
                            "delete", "format"]:
            # Handle content editing with smart image management
            result = await _handle_content_edit(
                db=db,
                page=page,
                blocks=blocks,
                target_blocks=target_blocks,
                request=request,
                intent_result=intent_result,
                vault_context=vault_context_text,
                vault_results=vault_results,
                vault_ids_used=vault_ids_used,
                user_id=user_id,
                mode=mode,
                now=now,
                preview_mode=preview_mode
            )
            return result
        
        else:
            # Unknown action type - treat as chat
            return {
                "status": "success",
                "action_taken": "none",
                "message": f"I understood your request as: {intent_result.get('intent')}. However, I'm not sure how to proceed. Could you please clarify?"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Orchestrator failed: {e}", exc_info=True)
        return {
            "status": "error",
            "action_taken": "none",
            "message": f"Sorry, I encountered an error: {str(e)}",
            "error": str(e)
        }


async def _handle_image_generation(
    db, page: dict, blocks: List[dict], request: PageOrchestrateRequest,
    intent_result: dict, vault_context: str, user_id: str, now: datetime,
    preview_mode: bool = False
) -> dict:
    """Handle AI image generation request. In preview_mode, returns blocks without saving to DB."""
    try:
        # Generate image description with AI
        image_description = await generate_image_description(
            request.message,
            intent_result.get("intent", ""),
            vault_context
        )
        
        logger.info(f"🎨 Generating image: {image_description[:100]}...")
        
        # Generate actual image
        try:
            image_bytes = await generate_image_with_ai(
                image_description,
                request.use_nano_banana
            )
        except HTTPException as e:
            # Image generation service not available - create placeholder block
            logger.warning(f"Image generation not available, creating placeholder")
            image_id = str(uuid.uuid4())[:12]
            new_image_block = {
                "block_id": f"block_{int(time.time())}_{image_id}",
                "type": "image",
                "placeholder": f"{{{{IMAGE_{image_id}}}}}",
                "description": image_description,
                "aws_url": None,
                "src": None,
                "layout": {"width": "100%", "alignment": "center"},
                "caption": "",
                "pending_generation": True,
                "order": len(blocks)
            }
            
            blocks.append(new_image_block)
            
            # PREVIEW MODE: Return blocks without saving
            if preview_mode:
                return {
                    "status": "partial",
                    "action_taken": "create_image_placeholder",
                    "message": f"I've added an image placeholder for: {image_description}. The actual image generation service is currently unavailable.",
                    "blocks": blocks,
                    "preview": True
                }
            
            await db.pages.update_one(
                {"page_id": request.page_id},
                {"$set": {"blocks": blocks, "updated_at": now}}
            )
            
            return {
                "status": "partial",
                "action_taken": "create_image_placeholder",
                "message": f"I've added an image placeholder for: {image_description}. The actual image generation service is currently unavailable."
            }
        
        # Upload to AWS S3
        aws_url = await upload_image_to_s3(image_bytes, request.page_id, user_id)
        
        # Create image block (NO raw bytes stored!)
        image_id = str(uuid.uuid4())[:12]
        new_image_block = {
            "block_id": f"block_{int(time.time())}_{image_id}",
            "type": "image",
            "placeholder": f"{{{{IMAGE_{image_id}}}}}",
            "description": image_description,
            "aws_url": aws_url,
            "src": aws_url,  # For backward compatibility
            "layout": {"width": "100%", "alignment": "center"},
            "caption": "",
            "order": len(blocks)
        }
        
        # Add to blocks
        blocks.append(new_image_block)
        
        # PREVIEW MODE: Return blocks without saving (S3 upload already done)
        if preview_mode:
            logger.info(f"👁️ Preview mode: Returning image block to UI (not saved to DB)")
            return {
                "status": "success",
                "action_taken": "create_image",
                "message": f"I've created an image: {image_description[:100]}...",
                "blocks": blocks,
                "preview": True
            }
        
        # UPDATE MONGODB (stores url, not bytes)
        await db.pages.update_one(
            {"page_id": request.page_id},
            {
                "$set": {
                    "blocks": blocks,
                    "updated_at": now,
                    "is_vectorized": False
                }
            }
        )
        
        logger.info(f"✅ Image created and added to page: {request.page_id}")
        
        return {
            "status": "success",
            "action_taken": "create_image",
            "message": f"I've created an image: {image_description[:100]}..."
        }
        
    except Exception as e:
        logger.error(f"❌ Image generation handler failed: {e}", exc_info=True)
        return {
            "status": "error",
            "action_taken": "none",
            "message": f"Failed to generate image: {str(e)}",
            "error": str(e)
        }


async def _handle_add_editable_block(
    db, page: dict, blocks: List[dict], request: PageOrchestrateRequest,
    intent_result: dict, user_id: str, now: datetime,
    preview_mode: bool = False
) -> dict:
    """
    Handle adding editable text blocks (wiki, notes, documentation areas).
    These blocks allow users to type directly while also being AI-editable.
    """
    try:
        # Determine block title based on intent
        intent_text = intent_result.get("intent", "").lower()
        user_message = request.message.lower()
        
        # Determine type and default title
        if "wiki" in user_message or "wiki" in intent_text:
            block_type = "wiki_block"
            default_title = "Wiki"
            placeholder = "Start writing your wiki content..."
        elif "notes" in user_message or "note" in intent_text:
            block_type = "notes"
            default_title = "Notes"
            placeholder = "Jot down your notes here..."
        elif "documentation" in user_message or "doc" in intent_text:
            block_type = "editable_text"
            default_title = "Documentation"
            placeholder = "Write your documentation..."
        else:
            block_type = "editable_text"
            default_title = "Editable Text"
            placeholder = "Start typing..."
        
        # Use AI to generate initial content if user provided context
        initial_text = ""
        if len(request.message) > 50:  # User provided substantial context
            try:
                ai_response = await asyncio.to_thread(lambda: llm_call(
                    user_prompt=f"User request: {request.message}\n\nGenerate initial content for a {block_type} block (keep it brief, 2-3 paragraphs max). Return ONLY the text content, no JSON:",
                    system_prompt="You help create initial content for editable text blocks. Generate relevant, helpful starting content that users can then edit and expand. Be concise."
                ))
                initial_text = ai_response.strip()
            except Exception as e:
                logger.warning(f"AI content generation skipped: {e}")
                initial_text = ""
        
        # Create the editable block
        block_id = f"block_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        new_block = {
            "block_id": block_id,
            "type": block_type,
            "title": default_title,
            "content": {
                "text": initial_text,
                "placeholder": placeholder
            },
            "order": len(blocks),
            "created_at": now.isoformat(),
            "created_by": "ai"
        }
        
        # Add to blocks
        blocks.append(new_block)
        
        content_preview = f" with initial content" if initial_text else ""
        message = f"I've added a {default_title} section{content_preview}. You can click on it to edit directly, or ask me to update it anytime!"
        
        # PREVIEW MODE: Return blocks without saving
        if preview_mode:
            logger.info(f"👁️ Preview mode: Returning editable block to UI (not saved)")
            return {
                "status": "success",
                "action_taken": "add_editable_block",
                "message": message,
                "block_id": block_id,
                "blocks": blocks,
                "preview": True
            }
        
        # Update MongoDB
        await db.pages.update_one(
            {"page_id": request.page_id},
            {
                "$set": {
                    "blocks": blocks,
                    "updated_at": now,
                    "is_vectorized": False
                }
            }
        )
        
        logger.info(f"✅ Editable block ({block_type}) added to page: {request.page_id}")
        
        return {
            "status": "success",
            "action_taken": "add_editable_block",
            "message": message,
            "block_id": block_id
        }
        
    except Exception as e:
        logger.error(f"❌ Add editable block failed: {e}", exc_info=True)
        return {
            "status": "error",
            "action_taken": "none",
            "message": f"Failed to add editable block: {str(e)}",
            "error": str(e)
        }


async def _handle_content_edit(
    db, page: dict, blocks: List[dict], target_blocks: List[dict],
    request: PageOrchestrateRequest, intent_result: dict, vault_context: str,
    vault_results: List[dict], vault_ids_used: List[str],
    user_id: str, mode: str, now: datetime,
    preview_mode: bool = False
) -> dict:
    """
    Handle content editing with smart image management:
    1. Extract images (AI sees placeholder+description only)
    2. AI edits content
    3. Restore image URLs from map
    4. Handle any new image placeholders AI created
    5. Update MongoDB (unless preview_mode is True)
    
    If preview_mode is True, returns blocks to UI instead of saving to DB.
    """
    try:
        # Prepare blocks for AI (images become placeholder+description)
        ai_safe_blocks, image_map = prepare_blocks_for_ai(target_blocks)
        
        logger.info(f"📝 Editing {len(ai_safe_blocks)} blocks, {len(image_map)} images extracted")
        
        # Call AI to edit blocks
        edited_blocks = await edit_blocks_with_ai(
            blocks=ai_safe_blocks,
            user_message=request.message,
            intent=intent_result,
            vault_context=vault_context,
            mode=mode
        )
        
        # Restore images from map
        restored_blocks = restore_images_after_ai(edited_blocks, image_map)
        
        # Check for new image placeholders AI might have added (with description but no aws_url)
        for block in restored_blocks:
            if block.get("type") == "image" and not block.get("aws_url"):
                # New image placeholder - mark for potential generation
                block["pending_generation"] = True
                logger.info(f"📌 New image placeholder detected: {block.get('description', 'no description')[:50]}")
        
        # Merge back if selection mode
        if request.selected_block_ids:
            # Build a map of edited blocks by block_id
            edited_map = {b.get("block_id"): b for b in restored_blocks}
            
            # Replace selected blocks in original list
            final_blocks = []
            edited_ids = set()
            
            for block in blocks:
                if block.get("block_id") in request.selected_block_ids:
                    # Check if this block was edited
                    if block.get("block_id") in edited_map:
                        final_blocks.append(edited_map[block.get("block_id")])
                        edited_ids.add(block.get("block_id"))
                    else:
                        final_blocks.append(block)
                else:
                    final_blocks.append(block)
            
            # Add any new blocks from edited_blocks that weren't in original
            for block in restored_blocks:
                if block.get("block_id") not in edited_ids and block.get("block_id") not in [b.get("block_id") for b in blocks]:
                    final_blocks.append(block)
        else:
            final_blocks = restored_blocks
        
        # Ensure proper ordering
        for i, block in enumerate(final_blocks):
            block["order"] = i
        
        # Build vault snapshot info for tracking data freshness
        vault_snapshot = {}
        if vault_results and len(vault_results) > 0:
            # Extract document IDs that were used
            source_doc_ids = []
            for item in vault_results[:10]:
                doc_id = item.get("id") or item.get("metadata", {}).get("document_id") or item.get("metadata", {}).get("id")
                if doc_id:
                    source_doc_ids.append(str(doc_id))
            
            vault_snapshot = {
                "ai_context.vault_snapshot_at": now,
                "ai_context.source_vault_ids": vault_ids_used,
                "ai_context.source_document_ids": source_doc_ids
            }
        
        # Generate response message based on action
        action_messages = {
            "edit_text": "I've updated the content as requested.",
            "add_content": "I've added new content to your page.",
            "create_chart": "I've created a chart and added it to your page.",
            "create_table": "I've created a table for you.",
            "create_survey": "I've added survey questions to your page.",
            "reorganize": "I've reorganized the content.",
            "delete": "I've removed the content as requested.",
            "format": "I've updated the formatting."
        }
        
        message = action_messages.get(intent_result.get("action_type"), "I've updated your page.")
        
        # PREVIEW MODE: Return blocks to UI without saving to DB
        if preview_mode:
            logger.info(f"👁️ Preview mode: Returning {len(final_blocks)} blocks to UI (not saved)")
            return {
                "status": "success",
                "action_taken": intent_result.get("action_type"),
                "message": message,
                "blocks": final_blocks,  # Return blocks for UI to render
                "preview": True
            }
        
        # SAVE MODE: Update MongoDB with vault snapshot tracking
        update_doc = {
            "$set": {
                "blocks": final_blocks,
                "updated_at": now,
                "is_vectorized": False,
                **vault_snapshot
            },
            "$push": {
                "ai_context.generation_prompts": request.message
            }
        }
        
        await db.pages.update_one(
            {"page_id": request.page_id},
            update_doc
        )
        
        logger.info(f"✅ Content edited for page: {request.page_id}, action: {intent_result.get('action_type')}")
        
        return {
            "status": "success",
            "action_taken": intent_result.get("action_type"),
            "message": message
        }
        
    except Exception as e:
        logger.error(f"❌ Content edit handler failed: {e}", exc_info=True)
        return {
            "status": "error",
            "action_taken": "none",
            "message": f"Failed to edit content: {str(e)}",
            "error": str(e)
        }


# ==================== Block Management Endpoints ====================

@page_router.get("/{page_id}/blocks")
async def get_page_blocks(page_id: str, current_user: dict = Depends(get_current_user)):
    """Get all blocks for a page"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        page = await db.pages.find_one(
            {"page_id": page_id, "user_id": user_id},
            {"blocks": 1}
        )
        
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        blocks = page.get("blocks", [])
        # Sort by order
        blocks.sort(key=lambda x: x.get("order", 0))
        
        return blocks
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get blocks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@page_router.post("/{page_id}/blocks")
async def add_block(
    page_id: str,
    request: CreateBlockRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add a new block to a page"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        # Verify page exists and belongs to user
        page = await db.pages.find_one({"page_id": page_id, "user_id": user_id})
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        # Create block
        block = {
            "block_id": str(uuid.uuid4()),
            "type": request.type,
            "content": request.content,
            "order": request.order if request.order is not None else len(page.get("blocks", [])),
            "metadata": request.metadata
        }
        
        # Add to page
        await db.pages.update_one(
            {"page_id": page_id},
            {
                "$push": {"blocks": block},
                "$set": {
                    "updated_at": datetime.utcnow(),
                    "is_vectorized": False
                }
            }
        )
        
        return {
            "success": True,
            "block": block,
            "message": "Block added successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to add block: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@page_router.put("/{page_id}/blocks/{block_id}")
async def update_block(
    page_id: str,
    block_id: str,
    request: UpdateBlockRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update a specific block with dirty checking"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        # Fetch existing block for comparison
        page = await db.pages.find_one(
            {"page_id": page_id, "user_id": user_id, "blocks.block_id": block_id},
            {"blocks.$": 1}
        )
        
        if not page or not page.get("blocks"):
            raise HTTPException(status_code=404, detail="Block not found")
        
        existing_block = page["blocks"][0]
        
        # Check if content actually changed
        has_changes = False
        update_ops = {}
        
        if request.content is not None:
            existing_content = existing_block.get("content", {})
            existing_hash = hashlib.md5(json.dumps(existing_content, sort_keys=True).encode()).hexdigest()
            new_hash = hashlib.md5(json.dumps(request.content, sort_keys=True).encode()).hexdigest()
            
            if existing_hash != new_hash:
                update_ops["blocks.$.content"] = request.content
                has_changes = True
                logger.info(f"📝 Block {block_id} content changed (hash: {existing_hash[:8]} → {new_hash[:8]})")
            else:
                logger.info(f"⏭️ Block {block_id} content unchanged, skipping")
        
        if request.order is not None and request.order != existing_block.get("order"):
            update_ops["blocks.$.order"] = request.order
            has_changes = True
            
        if request.metadata is not None:
            existing_meta = existing_block.get("metadata", {})
            if request.metadata != existing_meta:
                update_ops["blocks.$.metadata"] = request.metadata
                has_changes = True
        
        if has_changes:
            update_ops["updated_at"] = datetime.utcnow()
            update_ops["is_vectorized"] = False
            
            result = await db.pages.update_one(
                {
                    "page_id": page_id,
                    "user_id": user_id,
                    "blocks.block_id": block_id
                },
                {"$set": update_ops}
            )
            
            return {
                "success": True,
                "message": "Block updated successfully",
                "changes_saved": True
            }
        else:
            return {
                "success": True,
                "message": "No changes detected",
                "changes_saved": False
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to update block: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@page_router.delete("/{page_id}/blocks/{block_id}")
async def delete_block(
    page_id: str,
    block_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a specific block"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        result = await db.pages.update_one(
            {"page_id": page_id, "user_id": user_id},
            {
                "$pull": {"blocks": {"block_id": block_id}},
                "$set": {
                    "updated_at": datetime.utcnow(),
                    "is_vectorized": False
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Page not found")
        
        return {
            "success": True,
            "message": "Block deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete block: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class DiagramUploadRequest(BaseModel):
    """Request for uploading diagram image"""
    image_data: str = Field(..., description="Base64 encoded image data")
    page_id: str = Field(..., description="Page ID to associate diagram with")
    filename: Optional[str] = Field(default=None, description="Optional filename")


@page_router.post("/upload-diagram-image")
async def upload_diagram_image(
    request: DiagramUploadRequest,
    current_user: dict = Depends(get_current_user)
):
    """Upload a diagram image to S3 and return the URL"""
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        # Decode base64 image
        import base64
        image_bytes = base64.b64decode(request.image_data)
        
        # Generate unique filename
        filename = request.filename or f"diagram_{int(time.time())}.png"
        content_hash = hashlib.md5(image_bytes).hexdigest()[:12]
        
        # S3 key for diagram
        s3_key = f"pages/{user_id}/{request.page_id}/diagrams/{content_hash}_{filename}"
        
        # Upload to S3
        aws_url = bucket.upload_file(image_bytes, s3_key, "image/png")
        
        logger.info(f"✅ Diagram image uploaded: {aws_url}")
        
        return {
            "success": True,
            "url": aws_url,
            "s3_key": s3_key,
            "content_hash": content_hash
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to upload diagram image: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload diagram: {str(e)}")


@page_router.post("/{page_id}/blocks/{block_id}/refresh")
async def refresh_block(
    page_id: str,
    block_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Refresh a dynamic block's data"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        # Get page and block
        page = await db.pages.find_one({"page_id": page_id, "user_id": user_id})
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        # Find the block
        block = next((b for b in page.get("blocks", []) if b.get("block_id") == block_id), None)
        if not block:
            raise HTTPException(status_code=404, detail="Block not found")
        
        # Only refresh dynamic blocks
        if block.get("type") not in ["dynamic_text", "dynamic_table"]:
            return {
                "success": True,
                "message": "Block does not require refresh"
            }
        
        # Re-fetch data based on block's data_source
        # This would integrate with your integration sources
        # For now, just update the last_refreshed timestamp
        
        await db.pages.update_one(
            {
                "page_id": page_id,
                "blocks.block_id": block_id
            },
            {
                "$set": {
                    "blocks.$.last_refreshed": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "success": True,
            "message": "Block refreshed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to refresh block: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Sharing Endpoints ====================

@page_router.post("/{page_id}/share")
async def configure_sharing(
    page_id: str,
    request: ShareSettingsRequest,
    current_user: dict = Depends(get_current_user)
):
    """Configure sharing settings for a page"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        # Verify ownership
        page = await db.pages.find_one({"page_id": page_id, "user_id": user_id})
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        # Generate share link if making public
        share_link = None
        if request.is_public:
            share_link = page.get("share_settings", {}).get("share_link")
            if not share_link:
                share_link = str(uuid.uuid4())[:12]  # Short unique link
        
        # Calculate expiration
        expires_at = None
        if request.expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)
        
        # Update share settings
        share_settings = {
            "is_public": request.is_public,
            "share_link": share_link,
            "allowed_users": request.allowed_emails or [],
            "permissions": request.permissions,
            "password_protected": request.password is not None,
            "password_hash": request.password,  # In production, hash this!
            "expires_at": expires_at
        }
        
        await db.pages.update_one(
            {"page_id": page_id},
            {
                "$set": {
                    "share_settings": share_settings,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"🔗 Share settings updated for page: {page_id}")
        
        return {
            "success": True,
            "share_link": share_link,
            "share_settings": share_settings,
            "message": "Sharing settings updated"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to configure sharing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@page_router.get("/shared/{share_link}")
async def get_shared_page(share_link: str, password: Optional[str] = None):
    """Access a publicly shared page"""
    try:
        db = await get_async_database()
        
        page = await db.pages.find_one({
            "share_settings.share_link": share_link,
            "share_settings.is_public": True
        })
        
        if not page:
            raise HTTPException(status_code=404, detail="Shared page not found")
        
        share_settings = page.get("share_settings", {})
        
        # Check expiration
        expires_at = share_settings.get("expires_at")
        if expires_at and datetime.utcnow() > expires_at:
            raise HTTPException(status_code=410, detail="Share link has expired")
        
        # Check password
        if share_settings.get("password_protected"):
            if not password or password != share_settings.get("password_hash"):
                raise HTTPException(status_code=401, detail="Password required")
        
        # Return page without sensitive info
        safe_page = serialize_page(page)
        del safe_page["share_settings"]
        del safe_page["survey_responses"]
        del safe_page["ai_context"]
        
        return safe_page
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get shared page: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Survey Endpoints ====================

@page_router.post("/{page_id}/survey/submit")
async def submit_survey_response(
    page_id: str,
    request: SurveySubmitRequest
):
    """Submit a survey response (can be anonymous)"""
    try:
        db = await get_async_database()
        
        # Get page
        page = await db.pages.find_one({"page_id": page_id})
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        # Verify it's a survey
        survey_config = page.get("survey_config", {})
        if not survey_config.get("is_survey") or not survey_config.get("collect_responses"):
            raise HTTPException(status_code=400, detail="This page does not accept survey responses")
        
        # Check response limit
        response_limit = survey_config.get("response_limit")
        if response_limit:
            current_count = len(page.get("survey_responses", []))
            if current_count >= response_limit:
                raise HTTPException(status_code=400, detail="Survey response limit reached")
        
        # Create response
        response_doc = {
            "response_id": str(uuid.uuid4()),
            "respondent_email": request.respondent_email if not survey_config.get("anonymous_responses") else None,
            "answers": request.answers,
            "submitted_at": datetime.utcnow(),
            "metadata": {}
        }
        
        # Add response
        await db.pages.update_one(
            {"page_id": page_id},
            {
                "$push": {"survey_responses": response_doc},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        logger.info(f"📋 Survey response submitted for page: {page_id}")
        
        return {
            "success": True,
            "response_id": response_doc["response_id"],
            "message": "Survey response submitted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to submit survey response: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@page_router.get("/{page_id}/survey/responses")
async def get_survey_responses(
    page_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all survey responses (owner only)"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        page = await db.pages.find_one(
            {"page_id": page_id, "user_id": user_id},
            {"survey_responses": 1, "survey_config": 1, "blocks": 1}
        )
        
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        responses = page.get("survey_responses", [])
        
        # Serialize datetime fields
        for response in responses:
            if "submitted_at" in response and isinstance(response["submitted_at"], datetime):
                response["submitted_at"] = response["submitted_at"].isoformat()
        
        return {
            "success": True,
            "responses": responses,
            "total": len(responses),
            "survey_config": page.get("survey_config", {})
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get survey responses: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Vectorization Endpoint ====================

@page_router.post("/{page_id}/vectorize")
async def vectorize_page(page_id: str, current_user: dict = Depends(get_current_user)):
    """Trigger vectorization of page content to enrich vault"""
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        page = await db.pages.find_one({"page_id": page_id, "user_id": user_id})
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        # Call vectorization service
        try:
            from page_vectorization_service import vectorize_page_content
            result = await vectorize_page_content(page_id, user_id)
            
            return {
                "success": True,
                "chunks_created": result.get("chunks_created", 0),
                "message": "Page vectorized successfully"
            }
        except ImportError:
            logger.warning("Page vectorization service not available")
            return {
                "success": False,
                "message": "Vectorization service not available"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to vectorize page: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Integration Endpoints ====================

@page_router.get("/integrations/connected")
async def get_connected_integrations(current_user: dict = Depends(get_current_user)):
    """Get list of connected integrations for the user"""
    try:
        # Placeholder for future OAuth integration
        # For now, return empty list
        return {
            "success": True,
            "integrations": [],
            "message": "No integrations connected"
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get integrations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@page_router.post("/integrations/session-token")
async def create_integration_session_token(
    provider: str,
    current_user: dict = Depends(get_current_user)
):
    """Create session token for OAuth flow"""
    try:
        # Placeholder for future OAuth integration
        return {
            "success": True,
            "session_token": str(uuid.uuid4()),
            "provider": provider
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to create session token: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Health Check ====================

@page_router.get("/health")
async def page_builder_health():
    """Health check for page builder service"""
    return {
        "status": "healthy",
        "service": "page_builder",
        "timestamp": datetime.utcnow().isoformat()
    }


# ==================== Data Freshness Endpoints ====================

class RefreshDataRequest(BaseModel):
    """Request to refresh page data from vault"""
    refresh_type: str = Field(default="all", description="'all' or 'data_blocks_only'")


@page_router.get("/{page_id}/check-freshness")
async def check_data_freshness(
    page_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Check if page data is stale compared to vault updates.
    Returns staleness info so UI can show warning banner.
    """
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        # Get page with ai_context
        page = await db.pages.find_one({
            "page_id": page_id,
            "user_id": user_id
        })
        
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        ai_context = page.get("ai_context", {})
        vault_snapshot_at = ai_context.get("vault_snapshot_at")
        source_vault_ids = ai_context.get("source_vault_ids", [])
        source_document_ids = ai_context.get("source_document_ids", [])
        
        # If no vault data was used, page is not data-driven
        if not vault_snapshot_at or not source_vault_ids:
            return {
                "success": True,
                "is_data_driven": False,
                "is_stale": False,
                "message": "This page doesn't use vault data"
            }
        
        # Get latest document update time from vault
        # Check the documents collection for any updates after snapshot
        vault_updated_at = None
        documents_updated = 0
        
        try:
            # Check if any source documents were updated
            if source_document_ids:
                docs_cursor = db.documents.find({
                    "document_id": {"$in": source_document_ids},
                    "updated_at": {"$gt": vault_snapshot_at}
                })
                updated_docs = await docs_cursor.to_list(length=100)
                documents_updated = len(updated_docs)
                if updated_docs:
                    vault_updated_at = max(d.get("updated_at") for d in updated_docs)
            
            # Also check for any new documents in the vault
            if source_vault_ids:
                new_docs_cursor = db.documents.find({
                    "vault_id": {"$in": source_vault_ids},
                    "created_at": {"$gt": vault_snapshot_at}
                })
                new_docs = await new_docs_cursor.to_list(length=100)
                if new_docs:
                    documents_updated += len(new_docs)
                    new_max = max(d.get("created_at") for d in new_docs)
                    if vault_updated_at:
                        vault_updated_at = max(vault_updated_at, new_max)
                    else:
                        vault_updated_at = new_max
                        
        except Exception as e:
            logger.warning(f"Could not check vault updates: {e}")
        
        is_stale = documents_updated > 0
        
        # Calculate days since snapshot
        days_since_snapshot = 0
        if vault_snapshot_at:
            days_since_snapshot = (datetime.utcnow() - vault_snapshot_at).days
        
        return {
            "success": True,
            "is_data_driven": True,
            "is_stale": is_stale,
            "page_data_from": vault_snapshot_at.isoformat() if vault_snapshot_at else None,
            "vault_updated_at": vault_updated_at.isoformat() if vault_updated_at else None,
            "documents_updated": documents_updated,
            "days_since_snapshot": days_since_snapshot,
            "source_vault_ids": source_vault_ids,
            "message": f"{documents_updated} document(s) have been updated since this page was created" if is_stale else "Data is up to date"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to check freshness: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@page_router.post("/{page_id}/refresh-data")
async def refresh_page_data(
    page_id: str,
    request: RefreshDataRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Refresh page data by re-fetching from vault.
    Processes blocks synchronously and returns progress updates.
    
    This endpoint:
    1. Identifies data-driven blocks (tables, charts with vault data)
    2. Re-queries vault for fresh data
    3. Updates each block sequentially
    4. Returns final updated page
    """
    try:
        db = await get_async_database()
        user_id = current_user.get("user_id") or current_user.get("sub")
        
        # Get page
        page = await db.pages.find_one({
            "page_id": page_id,
            "user_id": user_id
        })
        
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        
        blocks = page.get("blocks", [])
        ai_context = page.get("ai_context", {})
        source_vault_ids = ai_context.get("source_vault_ids", [])
        generation_prompts = ai_context.get("generation_prompts", [])
        
        if not source_vault_ids:
            # Try to get vault_id from page
            if page.get("vault_id"):
                source_vault_ids = [page.get("vault_id")]
            else:
                return {
                    "success": False,
                    "message": "No vault data associated with this page",
                    "blocks_refreshed": 0
                }
        
        # Identify blocks that might contain data (tables, charts)
        # NOTE: image and diagram blocks are EXCLUDED - they are static/user-created
        data_block_types = ["table", "chartjs", "chart", "dynamic_table", "dynamic_text"]
        static_block_types = ["image", "diagram", "editable_text", "wiki_block", "notes"]  # Never auto-refresh
        
        data_blocks = [b for b in blocks if b.get("type") in data_block_types]
        
        if not data_blocks and request.refresh_type == "data_blocks_only":
            return {
                "success": True,
                "message": "No data blocks found to refresh",
                "blocks_refreshed": 0
            }
        
        # Get fresh vault context using the last generation prompt or a generic query
        refresh_query = generation_prompts[-1] if generation_prompts else "refresh all data"
        vault_results = await get_vault_context(user_id, source_vault_ids, refresh_query, top_k=20)
        
        vault_context_text = "\n\n".join([
            f"Document: {item.get('metadata', {}).get('topic_or_filename', 'Unknown')}\n{item.get('metadata', {}).get('text', '')[:1000]}"
            for item in vault_results[:10]
        ])
        
        now = datetime.utcnow()
        blocks_refreshed = 0
        refresh_results = []
        
        # Process each data block
        for i, block in enumerate(blocks):
            block_type = block.get("type")
            
            # Skip static blocks (images, diagrams, user-editable content)
            if block_type in static_block_types:
                refresh_results.append({
                    "block_id": block.get("block_id"),
                    "status": "skipped",
                    "reason": f"Static content ({block_type}) - not refreshed"
                })
                continue
            
            # Skip non-data blocks
            if block_type not in data_block_types:
                refresh_results.append({
                    "block_id": block.get("block_id"),
                    "status": "skipped",
                    "reason": "Not a data block"
                })
                continue
            
            try:
                # Generate fresh content for this block using AI
                block_prompt = f"""Refresh the data in this {block.get('type')} block using the latest vault data.

Current block:
{json.dumps(block, indent=2)}

Latest vault data:
{vault_context_text}

Return ONLY the updated block as JSON. Keep the same structure, block_id, and type.
Update the data/content with fresh information from the vault data.
If the vault data doesn't have relevant updates, return the block unchanged."""

                response = await asyncio.to_thread(lambda: llm_call(
                    user_prompt=block_prompt,
                    system_prompt="You are refreshing data blocks with the latest vault information. Return only valid JSON for the block."
                ))
                
                # Parse response
                json_str = response.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0]
                
                updated_block = json.loads(json_str)
                
                # Preserve block_id and order
                updated_block["block_id"] = block.get("block_id")
                updated_block["order"] = block.get("order")
                updated_block["last_refreshed"] = now.isoformat()
                
                # Update block in list
                block_idx = next((idx for idx, b in enumerate(blocks) if b.get("block_id") == block.get("block_id")), None)
                if block_idx is not None:
                    blocks[block_idx] = updated_block
                
                blocks_refreshed += 1
                refresh_results.append({
                    "block_id": block.get("block_id"),
                    "type": block.get("type"),
                    "status": "refreshed",
                    "progress": int((i + 1) / len(data_blocks) * 100) if data_blocks else 100
                })
                
            except Exception as e:
                logger.error(f"Failed to refresh block {block.get('block_id')}: {e}")
                refresh_results.append({
                    "block_id": block.get("block_id"),
                    "status": "error",
                    "error": str(e)
                })
        
        # Update document IDs from fresh vault results
        source_doc_ids = []
        for item in vault_results[:10]:
            doc_id = item.get("id") or item.get("metadata", {}).get("document_id")
            if doc_id:
                source_doc_ids.append(str(doc_id))
        
        # Update MongoDB with refreshed blocks and new snapshot time
        await db.pages.update_one(
            {"page_id": page_id},
            {
                "$set": {
                    "blocks": blocks,
                    "updated_at": now,
                    "ai_context.vault_snapshot_at": now,
                    "ai_context.source_document_ids": source_doc_ids,
                    "ai_context.last_refresh": now
                }
            }
        )
        
        logger.info(f"✅ Refreshed {blocks_refreshed} blocks for page: {page_id}")
        
        return {
            "success": True,
            "message": f"Refreshed {blocks_refreshed} data blocks with latest vault data",
            "blocks_refreshed": blocks_refreshed,
            "total_blocks": len(blocks),
            "refresh_results": refresh_results,
            "vault_snapshot_at": now.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to refresh page data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
