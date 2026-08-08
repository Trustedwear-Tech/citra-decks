"""
Page Vectorization Service - Sync page content to Milvus for vault enrichment

This service extracts text content from pages and their blocks,
creates vector embeddings, and stores them in Milvus to enrich
the user's vault for better AI retrieval.

Features:
- Extract text from all block types
- Include survey responses in vectorization
- Chunk content appropriately
- Store with proper metadata for filtering
"""

import logging
import asyncio
import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from citra_mongo import get_async_database
from utils import embed_text, embed_texts_batch

logger = logging.getLogger(__name__)

# Chunk configuration
CHUNK_SIZE = 500  # characters
CHUNK_OVERLAP = 50  # characters

def extract_text_from_block(block: Dict[str, Any]) -> str:
    """Extract plain text content from a block"""
    block_type = block.get("type", "")
    content = block.get("content", {})
    
    if not content:
        return ""
    
    text_parts = []
    
    if block_type == "heading":
        text_parts.append(content.get("text", ""))
        
    elif block_type == "paragraph":
        text_parts.append(content.get("text", ""))
        
    elif block_type == "list":
        items = content.get("items", [])
        text_parts.extend(items)
        
    elif block_type == "checklist":
        items = content.get("items", [])
        for item in items:
            if isinstance(item, dict):
                text_parts.append(item.get("text", ""))
            else:
                text_parts.append(str(item))
                
    elif block_type == "table":
        headers = content.get("headers", [])
        rows = content.get("rows", [])
        text_parts.append(" | ".join(headers))
        for row in rows:
            text_parts.append(" | ".join([str(cell) for cell in row]))
            
    elif block_type == "quote":
        text_parts.append(content.get("text", ""))
        author = content.get("author", "")
        if author:
            text_parts.append(f"- {author}")
            
    elif block_type == "callout":
        text_parts.append(content.get("text", ""))
        
    elif block_type == "code":
        text_parts.append(content.get("code", ""))
        
    elif block_type in ["survey_text", "survey_multiple_choice", "survey_checkbox", 
                        "survey_rating", "survey_scale", "survey_date"]:
        text_parts.append(content.get("question", ""))
        options = content.get("options", [])
        if options:
            text_parts.extend(options)
            
    elif block_type == "dynamic_text":
        text_parts.append(content.get("text", ""))
        
    elif block_type == "dynamic_table":
        # Similar to table
        headers = content.get("headers", [])
        rows = content.get("rows", [])
        text_parts.append(" | ".join(headers))
        for row in rows:
            text_parts.append(" | ".join([str(cell) for cell in row]))
            
    elif block_type == "chart":
        text_parts.append(content.get("title", ""))
        labels = content.get("labels", [])
        text_parts.extend(labels)
        
    # Generic fallback
    else:
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, dict):
            for key, value in content.items():
                if isinstance(value, str):
                    text_parts.append(value)
                elif isinstance(value, list):
                    text_parts.extend([str(v) for v in value])
    
    return " ".join(text_parts)

def extract_survey_responses_text(responses: List[Dict[str, Any]], blocks: List[Dict[str, Any]]) -> str:
    """Extract text from survey responses"""
    if not responses:
        return ""
    
    # Create block_id to question mapping
    block_questions = {}
    for block in blocks:
        if block.get("type", "").startswith("survey_"):
            block_id = block.get("block_id", "")
            question = block.get("content", {}).get("question", "Unknown question")
            block_questions[block_id] = question
    
    text_parts = []
    text_parts.append("Survey Responses Summary:")
    
    for response in responses:
        answers = response.get("answers", {})
        for block_id, answer in answers.items():
            question = block_questions.get(block_id, "Question")
            if isinstance(answer, list):
                answer_text = ", ".join([str(a) for a in answer])
            else:
                answer_text = str(answer)
            text_parts.append(f"Q: {question} A: {answer_text}")
    
    return " ".join(text_parts)

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks"""
    if not text or len(text) <= chunk_size:
        return [text] if text else []
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence endings
            for sep in ['. ', '! ', '? ', '\n', '; ']:
                last_sep = text[start:end].rfind(sep)
                if last_sep > chunk_size * 0.5:  # Only if we're past halfway
                    end = start + last_sep + len(sep)
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap
    
    return chunks

async def vectorize_page_content(page_id: str, user_id: str) -> Dict[str, Any]:
    """
    Vectorize page content and store in Milvus
    
    Args:
        page_id: The page ID to vectorize
        user_id: The owner user ID
        
    Returns:
        Dict with vectorization results
    """
    try:
        db = await get_async_database()
        
        # Get page
        page = await db.pages.find_one({"page_id": page_id, "user_id": user_id})
        if not page:
            logger.error(f"Page not found: {page_id}")
            return {"success": False, "error": "Page not found"}
        
        logger.info(f"📄 Vectorizing page: {page.get('title', 'Untitled')}")
        
        # Extract all text content
        blocks = page.get("blocks", [])
        text_parts = []
        
        # Add title
        title = page.get("title", "")
        if title:
            text_parts.append(f"Title: {title}")
        
        # Extract from blocks
        for block in blocks:
            block_text = extract_text_from_block(block)
            if block_text:
                text_parts.append(block_text)
        
        # Include survey responses if any
        survey_responses = page.get("survey_responses", [])
        if survey_responses:
            responses_text = extract_survey_responses_text(survey_responses, blocks)
            if responses_text:
                text_parts.append(responses_text)
        
        # Combine all text
        full_text = "\n\n".join(text_parts)
        
        if not full_text.strip():
            logger.warning(f"No content to vectorize for page: {page_id}")
            return {"success": True, "chunks_created": 0, "message": "No content to vectorize"}
        
        # Chunk the content
        chunks = chunk_text(full_text)
        
        logger.info(f"📊 Created {len(chunks)} chunks from page content")
        
        # Generate embeddings
        try:
            embeddings = await embed_texts_batch(chunks, task_type="RETRIEVAL_DOCUMENT")
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            return {"success": False, "error": f"Embedding failed: {str(e)}"}
        
        # Prepare documents for Milvus
        from config.milvus_config import get_milvus_client, get_collection_name
        
        collection_name = get_collection_name()
        
        try:
            client = get_milvus_client()
        except Exception:
            logger.error("Milvus configuration not found")
            return {"success": False, "error": "Milvus not configured"}
        
        # Delete existing page vectors
        try:
            client.delete(
                collection_name=collection_name,
                filter=f'document_id == "{page_id}" and source_type == "page"'
            )
            logger.info(f"🗑️ Deleted existing vectors for page: {page_id}")
        except Exception as e:
            logger.warning(f"Could not delete existing vectors: {e}")
        
        # Insert new vectors
        documents = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            doc = {
                "chunk_id": f"{page_id}_chunk_{i}",
                "text": chunk,
                "dense_vector": embedding,
                "user_id": user_id,
                "document_id": page_id,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "created_at": int(datetime.utcnow().timestamp() * 1000),
                "topic_or_filename": page.get("title", "Page"),
                "file_type": "page",
                "source_type": "page",
                "page_type": page.get("page_type", "wiki"),
                "vault_id": page.get("vault_id", "none"),
                "is_enterprise": False,
                "entity_id": "none"
            }
            documents.append(doc)
        
        if documents:
            try:
                client.insert(collection_name=collection_name, data=documents)
                logger.info(f"✅ Inserted {len(documents)} vectors for page: {page_id}")
            except Exception as e:
                logger.error(f"Failed to insert vectors: {e}")
                return {"success": False, "error": f"Insert failed: {str(e)}"}
        
        # Update page status
        await db.pages.update_one(
            {"page_id": page_id},
            {
                "$set": {
                    "is_vectorized": True,
                    "vectorized_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "success": True,
            "chunks_created": len(documents),
            "message": f"Successfully vectorized {len(documents)} chunks"
        }
        
    except Exception as e:
        logger.error(f"❌ Page vectorization failed: {e}")
        return {"success": False, "error": str(e)}

async def vectorize_all_pending_pages(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Vectorize all pages that haven't been vectorized yet
    
    Args:
        user_id: Optional filter by user
        
    Returns:
        Summary of vectorization results
    """
    try:
        db = await get_async_database()
        
        # Build query
        query = {"is_vectorized": False}
        if user_id:
            query["user_id"] = user_id
        
        # Find all pending pages
        cursor = db.pages.find(query)
        pages = await cursor.to_list(length=100)
        
        logger.info(f"📚 Found {len(pages)} pages pending vectorization")
        
        results = {
            "total": len(pages),
            "success": 0,
            "failed": 0,
            "errors": []
        }
        
        for page in pages:
            page_id = page.get("page_id")
            page_user_id = page.get("user_id")
            
            result = await vectorize_page_content(page_id, page_user_id)
            
            if result.get("success"):
                results["success"] += 1
            else:
                results["failed"] += 1
                results["errors"].append({
                    "page_id": page_id,
                    "error": result.get("error", "Unknown error")
                })
        
        logger.info(f"✅ Vectorization complete: {results['success']}/{results['total']} successful")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Batch vectorization failed: {e}")
        return {"success": False, "error": str(e)}

# ==================== Scheduled Task ====================

async def scheduled_vectorization_task():
    """Background task to vectorize pending pages periodically"""
    while True:
        try:
            logger.info("🔄 Running scheduled page vectorization...")
            result = await vectorize_all_pending_pages()
            logger.info(f"📊 Scheduled vectorization result: {result}")
        except Exception as e:
            logger.error(f"❌ Scheduled vectorization error: {e}")
        
        # Run every 5 minutes
        await asyncio.sleep(300)
