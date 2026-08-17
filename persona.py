# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

# ============================  Persona Management Router  =============================
# Purpose: User persona CRUD operations and RAG enhancement for Citra AI
# Features: Professional personas, MongoDB storage, persona-driven query enhancement
# ----------------------------------------------------------------------------------------
# =============================  XAI PROMPT CACHING OPTIMIZATION  =======================
# The persona system prompt is structured for optimal xAI prefix caching:
# - STATIC content first: Response strategy, tools, formatting (identical across users)
# - DYNAMIC content last: User name, profession (varies per user)
#
# This allows xAI to cache the static prefix (~80% of tokens) across ALL users,
# achieving ~66% cost savings on subsequent queries (80% of tokens at 83% discount)
# Prompt caching: cached input tokens are far cheaper than fresh (~83% savings on the cached portion)
# ======================================================================================

from typing import Dict, Optional, List, Any
from fastapi import APIRouter, Request, Query, Body, HTTPException, status
from fastapi.responses import JSONResponse

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
import logging
import json
import os
import requests
from datetime import datetime
from bson import ObjectId
from citra_mongo import get_mongo_client

# Import authentication middleware
from citra_auth import get_secure_user_id

# MongoDB Configuration - read from .env only
from citra_mongo import MONGODB_DATABASE, get_mongo_client

def get_user_personas_col():
    return get_mongo_client()[MONGODB_DATABASE]['user_personas']

def get_users_col():
    return get_mongo_client()[MONGODB_DATABASE]['users']

router = APIRouter()

# =========================== Pydantic Models ===========================

class SimplePersonaData(BaseModel):
    """Simplified persona data structure - name, mobile, and profession"""
    name: Optional[str] = None
    mobile: Optional[str] = None
    profession: Optional[str] = None

class SimplePersonaRequest(BaseModel):
    user_type: Optional[str] = "professional"  # Keep for backward compatibility
    persona: SimplePersonaData
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class SimplePersonaUpdateRequest(BaseModel):
    persona: SimplePersonaData

# =========================== Utility Functions ===========================

def serialize_mongo_doc(doc):
    """Convert MongoDB document to JSON serializable format"""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize_mongo_doc(item) for item in doc]
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == '_id':
                result[key] = str(value)
            elif isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = serialize_mongo_doc(value)
            elif isinstance(value, list):
                result[key] = serialize_mongo_doc(value)
            else:
                result[key] = value
        return result
    elif isinstance(doc, datetime):
        return doc.isoformat()
    return doc

def generate_simple_rag_context(persona: dict, user_type: str) -> dict:
    """Generate simplified RAG enhancement context from persona data"""
    
    # Extract only name and profession
    name = persona.get('name', 'User')
    profession = persona.get('profession', 'Professional')
    
    # Create simplified context with only name and profession
    context_parts = []
    
    if name:
        context_parts.append(f"User name: {name}")
    
    if profession:
        context_parts.append(f"Profession: {profession}")
    
    query_enhancement_prompt = "\\n".join(context_parts)
    
    # Create simplified response guidelines based only on name and profession
    guidelines = [
        f"Address the user as {name}" if name else "Address the user professionally",
        f"Tailor responses for a {profession}" if profession else "Provide professional-level advice",
        "Provide practical, actionable insights"
    ]
    
    return {
        "query_enhancement_prompt": query_enhancement_prompt,
        "response_guidelines": "\\n".join([f"- {guideline}" for guideline in guidelines]),
        "focus_areas": [profession] if profession else [],
        "user_context": {
            "name": name,
            "profession": profession
        }
    }

def enhance_query_with_persona(query: str, persona: dict) -> str:
    """
    DEPRECATED: Query enhancement with persona context has been disabled.
    This function now returns the original query unchanged.
    """
    logging.info("[QUERY_ENHANCE] Persona query enhancement is disabled - returning original query")
    return query

# =========================== Profession Configuration Data ===========================
# SIMPLIFIED: Only General Professional is supported - this is the default for all users

PROFESSION_CONFIG = {
    "General Professional": {
        "icon": "💼",
        "identity": "You are Citra AI, a specialized AI assistant for professionals.",
        "mission": "Help professionals achieve their goals through intelligent analysis, research, documentation, and actionable insights.",
        "default_mode": "**DEFAULT: Provide thorough, well-explained responses for all professional queries — let content complexity drive length, not query length**",
        "focus": [
            "Goal-oriented assistance and problem solving",
            "Research, analysis, and documentation support",
            "Professional communication and drafting",
            "Strategic planning and decision support"
        ],
        "metadata_fields": "`document_id`, `topic_or_filename`, and other contextual fields",
        "context_type": "context",
        "shared_ref": "shared reference material",
        "citation_format": "GENERAL",
        "citation_types": [],
        "json_extra_fields": "",
        "json_example_doc": '"display_name": "File.pdf", "document_id": "d92a724c-22c3-4a68-9956-bdee3174b977", "description": "What used"'
    }
}

def get_profession_config(profession: str) -> dict:
    """Get configuration for a profession, falling back to General Professional if not found."""
    return PROFESSION_CONFIG.get(profession, PROFESSION_CONFIG.get("General Professional"))

def get_response_strategy_guide(profession: str = "") -> str:
    """Returns the AI response depth guide for thorough, analytical responses."""
    config = get_profession_config(profession)
    # default_mode provides a profession-specific depth nudge
    default_mode = config.get('default_mode', '**DEFAULT: Provide thorough, well-explained responses — let content complexity drive length**')
    
    return f"""
🎯 RESPONSE DEPTH GUIDE — DEFAULT TO COMPREHENSIVE ANSWERS

Main chat is designed for thorough, analytical, and conversational assistance.
**Detailed answers are the default. Brevity must be earned by the question.**

**Every response must:**
- Explain the "why" and "how", not just the "what"
- Walk through the reasoning step-by-step for any non-trivial question
- Use structure (headers, sub-sections, bullets, tables) when it aids clarity
- Include relevant principles, mechanics, tradeoffs, edge cases, and worked examples
- Include relevant context the user may not have asked for but needs
- Draw on all provided document context — don't leave chunks unused if relevant
- For "review", "analyse", "compare", "explain", "how does X work", "why does X" → produce a multi-section answer covering background, mechanics, evidence, implications, and recommendations

**Length calibration:**
- A one-word or short question can still need a multi-paragraph answer if the topic demands it
- Be brief ONLY when the complete answer genuinely IS brief (a single number, a direct yes/no with no nuance, a greeting)
- Never truncate an explanation that would benefit from depth
- For a GENERAL/CONCEPTUAL question, don't shorten just because vault context is empty — answer at full general-knowledge depth. But for a question about the user's own or the organisation's DATA (specific numbers, counts, records, statuses, names), an empty/failed grounded source means you say the data is unavailable — do NOT substitute general knowledge or a guess to pad length.
- You have up to 60,000 output tokens. Use them when the topic warrants it.

{default_mode}

**⚠️ DO NOT pre-announce response style or length. Just answer comprehensively.**

═══════════════════════════════════════════════════════════════════════════════════════
"""

def _build_profession_focus(config: dict) -> str:
    """Build profession-specific focus section."""
    if not config.get('focus'):
        return ""
    icon = config.get('icon', '📌')
    items = "\n".join([f"- {item}" for item in config['focus']])
    return f"\n**{icon} {config.get('icon', '').upper()} PROFESSION-SPECIFIC FOCUS:**\n{items}\n"

def _build_chunk_relevance(config: dict, profession: str) -> str:
    """Build chunk relevance control section."""
    
    # Handle professions with simplified configs (missing context_type and shared_ref)
    context_type = config.get('context_type', 'document context')
    shared_ref = config.get('shared_ref', 'shared reference material')
    
    # Check if this profession requires citations
    has_citations = config.get('citation_format') is not None
    
    # Build citation instruction line (only for professions with citations)
    citation_line = "- ✅ Include citations ONLY in the JSON appendix at the end\n" if has_citations else ""
    
    base = f"""
**🔍 CHUNK RELEVANCE CONTROL:**

Before using any chunk, verify relevance via metadata:
- {config['metadata_fields']}

**Rules:**
- ✅ Use ONLY chunks matching query subject
- ❌ Filter OUT unrelated chunks
- ❌ NEVER mix data from different {context_type}s
- If chunks irrelevant to a GENERAL/CONCEPTUAL question → IGNORE them and either answer from training (for stable/conceptual topics) or call `internet_search` directly (for time-sensitive topics). Do NOT refuse, do NOT ask the user for permission to search, and do NOT say "I don't have documents on this topic" — just act.
- BUT for a DATA-SPECIFIC question about the user's or the organisation's records (a count, total, status, list, named entity, dated value) where the grounded source returned nothing or failed → say the data could not be retrieved. Do NOT answer it from training knowledge, and do NOT estimate or guess a value.
- If data missing → State clearly, don't fabricate. A failed/errored retrieval is NOT the same as "zero" — never report a guessed number in place of data you couldn't fetch.

**Folder/Enterprise:**
- One `folder_id` = one {context_type} - never mix folders
- `is_enterprise=true` with empty `entity_id` = {shared_ref}

**📝 PERSONAL DOCUMENTS & NOTES:** Answer directly and naturally from the retrieved content. Never mention document IDs, vector IDs, relevance scores, chunk indices, or create any inline/footnote/numbered citation list in the prose. Citations go only in the JSON block at the end, and ONLY at the document level (one entry per unique document_id — never per-chunk)."""
    
    return base

def _build_citation_guidelines(config: dict) -> str:
    """Build citation guidelines section."""
    format_name = config.get('citation_format', '')
    format_title = f" - {format_name} FORMAT" if format_name else ""

    citation_types_str = "\n".join(config.get('citation_types', [])) if config.get('citation_types') else ""
    if citation_types_str:
        citation_types_str = f"\n**Citation Format:**\n{citation_types_str}\n"

    # Handle missing json_extra_fields gracefully for simplified professions
    json_extra_fields = config.get('json_extra_fields', '')
    # Add comma only if there are extra fields to include
    extra_fields_line = f",\n        {json_extra_fields}" if json_extra_fields else ""

    return f"""
**📚 CITATIONS{format_title}:**

**Citation Sources:**
1. **Personal Documents (Milvus)**: Cite at the DOCUMENT level only — one entry per unique `document_id`, regardless of how many chunks were used. DO NOT emit per-chunk citations.
2. **Web**: For internet-sourced facts, include the URL in the "web" array.
{citation_types_str}
**CRITICAL:** Only cite sources ACTUALLY used. Extract EXACT IDs from context:
  - 📄 Document Name: {{{{filename}}}} ← Use as "display_name"
  - 📄 Document ID: {{{{uuid}}}} ← Use as "document_id" (THIS IS A UUID like d92a724c-22c3-4a68-9956-bdee3174b977)

**IMPORTANT:** The document_id is a UUID (like d92a724c-22c3-4a68-9956-bdee3174b977), NOT the filename. NEVER include `vector_id` or per-chunk entries.

**NOTE:** Multiple chunks may share a Document ID — collapse them into ONE entry in the "documents" array. Citations go ONLY in JSON appendix.

**JSON Appendix:**
- ✅ Include JSON ONLY if you actually used citations from any source (documents, web, etc.)
- ❌ If NO citations were used, DO NOT include the JSON block at all
- ❌ NEVER emit a "chunks" array — doc-level citations only
- ❌ NEVER write "see JSON appendix" or "see below" in prose — the JSON block IS the citation, output it directly
- ❌ NEVER use synthetic labels like "Source 1" as substitutes for real UUIDs
- ❌ NEVER include a separate "References", "Citations", or "Sources" section in the response body — citations go ONLY in the JSON block
- ❌ NEVER produce a numbered/bulleted citation list at the end of the prose — only the JSON block is allowed
- Format when citations are present:
```json
{{{{
    "citations": {{{{
        "documents": [{{{{{config['json_example_doc']}}}}}],
        "web": [{{{{"url": "https://...", "display_name": "Source Name", "description": "What used"}}}}]{extra_fields_line}
    }}}}
}}}}
```"""

def generate_persona_system_prompt(persona: dict) -> str:
    """
    Generate system prompt based on simplified user persona - only name and profession.
    
    🚀 XAI PROMPT CACHING OPTIMIZATION:
    The prompt is structured in TWO parts for optimal prefix caching:
    1. STATIC SECTION (first ~80%): Identical across all users of same profession
       - Response mode selection, tool availability, formatting rules
       - Citation guidelines, chunk relevance control
       - Profession-specific focus and analysis framework
    2. DYNAMIC SECTION (last ~20%): User-specific info
       - User name, profession identity
       - Personalized response alignment
    
    This structure ensures xAI can cache the static prefix across ALL users
    with the same profession, achieving significant cost savings.
    """
    if not persona:
        return "You are a helpful AI assistant."
    
    logging.debug(f"🔍 [PERSONA_DEBUG] Received persona data: {persona}")
    
    # Handle both nested (old) and flat (new) persona data structures
    if "persona" in persona:
        persona_data = persona.get("persona", {})
        name = persona_data.get("name", "User")  
        profession = persona_data.get("profession", "")
    else:
        name = persona.get("name", "User")
        profession = persona.get("profession", "")
    
    # Get profession config
    config = get_profession_config(profession)
    
    # Build all static sections (cacheable across users of same profession)
    response_strategy = get_response_strategy_guide(profession)
    profession_focus = _build_profession_focus(config)
    chunk_relevance = _build_chunk_relevance(config, profession)
    # Build citation guidelines only for professions that have citation_format
    citation_guidelines = _build_citation_guidelines(config) if config.get('citation_format') else ""
    analysis_framework = config.get('analysis_framework', '')
    
    # ═══════════════════════════════════════════════════════════════════════════════════════
    # STATIC SECTION - CACHEABLE ACROSS ALL USERS OF SAME PROFESSION
    # Place all static, profession-specific content first for optimal prefix caching
    # ═══════════════════════════════════════════════════════════════════════════════════════
    # 🛡️ Anti-hallucination grounding rules — kept at the top of the static
    # section so they remain inside the xAI prefix cache for every user.
    try:
        from prompts.grounding import STRICT_GROUNDING_PROMPT
        # NOTE: the main-chat streaming path does NOT strip inline citation
        # markers before rendering (unlike composer/presentation/printable),
        # so CITATION_TAGS_RULE is intentionally NOT appended here — it would
        # leak raw `[vault:...]` tags into the streamed prose. Vault/source
        # citations belong ONLY in the JSON appendix (see CITATIONS section).
        _no_inline_citations = (
            "**🚫 NO INLINE CITATION MARKERS:** Do NOT write any inline citation "
            "tags, document IDs, or bracketed source markers — e.g. `[vault:...]`, "
            "`[doc:...]`, `[source:...]`, `[internet:...]`, `[structured:...]` — "
            "anywhere in the visible reply. They are NOT stripped before display "
            "and would appear verbatim to the user. Document citations go ONLY in "
            "the JSON appendix at the end of the response, at the document level."
        )
        _grounding_prefix = f"{STRICT_GROUNDING_PROMPT}\n\n{_no_inline_citations}\n\n---\n\n"
    except Exception:
        # If import fails for any reason, persona must still be usable.
        _grounding_prefix = ""

    static_section = f"""{_grounding_prefix}{response_strategy}

**Response Strategy:** Tailor responses to the user's profession. For DATA-SPECIFIC questions (the user's documents or the organisation's records — any number, count, status, name, date, or list), answer ONLY from grounded source data: enterprise `dept_*` tool results and Milvus/vault context. If that grounded data is missing or its retrieval failed, say so — never substitute training knowledge or a guessed value for it. Answer stable/conceptual questions (definitions, mechanics, how-things-work) from training knowledge at full depth; use internet search only when enabled and the query is time-sensitive.

---

{config['identity']}

---
{chunk_relevance}

---
{citation_guidelines}

---

**📝 FORMATTING:**
- Markdown headers with blank lines, lists with `-`, tables with `|`
- NO HTML tags, NO separator lines (═══)

**📊 DIAGRAMS:** Use ` ```ascii ` (never ` ```mermaid `) for all structural/relational visuals — flows, architectures, hierarchies, state machines. Be proactive: include a diagram whenever a visual saves explanation. Keep under 80 chars wide, 20 lines tall. Use box-drawing chars (┌┐└┘│─├┤) and arrows (→ ← ↑ ↓ ⇒).

**📈 CHARTS:** Use ` ```chartjs ` with Chart.js v4 JSON for all data visualizations (bar, line, pie, scatter, bubble, etc.). Required keys: `type`, `data` with `labels` and `datasets`. Do NOT include colors. Bubble: `{{x,y,r}}`; Scatter: `{{x,y}}`. Use ASCII for structure/flow diagrams, chartjs for data.
{analysis_framework}

---

**🎯 APPROACH:** Understand what the user truly needs (draft? analysis? information?). Ask for clarification only when genuinely vague — check conversation history first. Be comprehensive and actionable: if drafting, draft fully; if researching, cover thoroughly. You have up to 60,000 output tokens — use them.

**🧩 INTERACTIVE CLARIFY BLOCK (preferred way to ask):**
Whenever you need to ask the user to choose between a small set of options
(e.g. an ambiguous filter value the user typed, an ambiguous metric definition,
an ambiguous date range, or "did you mean ...?" for a misspelled name), you
MUST emit a single fenced JSON block of the form below in addition to — or
instead of — a free-text question. The UI renders the options as clickable
chips so the user can answer in one tap.

```
<clarify>
{{
  "message": "Which interpretation did you mean?",
  "reason": "metric_definition",
  "options": [
    {{"id": "1", "label": "Mean (arithmetic average)", "value": "mean", "follow_up_query": "compute the mean"}},
    {{"id": "2", "label": "Median", "value": "median", "follow_up_query": "compute the median"}}
  ],
  "allow_freeform": true
}}
</clarify>
```

Rules:
- Use **`reason`** = `"filter_value_mismatch"`, `"ambiguous_intent"`, `"metric_definition"`, or `"other"`.
- Provide 2–6 `options`; each MUST have at minimum `label` and `value`.
- Add `"follow_up_query"` whenever you can construct the exact query the user
  would type if they picked that option — the UI submits it as the next turn.
- Set `"allow_freeform": true` (default) so the user can also type a custom
  answer.
- Emit AT MOST ONE `<clarify>` block per turn. Place it after a one-line
  natural-language explanation. Do NOT call tools in the same turn — wait for
  the user's pick.
- The block is stripped from the visible message; the UI renders the chips.
  Do not duplicate the option list as plain text.

**📋 FOLLOW-UP SUGGESTIONS (ALWAYS INCLUDE):**

After every response, suggest 2–3 follow-up questions to help the user continue the conversation:
- ✅ Questions that go deeper on the topic you just covered
- ✅ Related angles or implications the user hasn't explored yet
- ✅ Natural "what next?" questions that keep the conversation productive
- ❌ DO NOT generate generic filler (e.g. "Would you like to know more?")
- ❌ DO NOT repeat the user's original question as a follow-up
- ❌ DO NOT ask follow-ups when the user clearly wants to close the topic (e.g. "thanks", "that's all")

**Format:** List follow-ups at the end of your response preceded by a brief **"You might also ask:"** or **"To explore further:"** label."""
    
    # Add mission only if it exists (for backward compatibility with simplified professions)
    mission_field = config.get('mission', '')
    if mission_field:
        static_section += f"\n\n---\n\n**Core Mission:** {mission_field}"

    # ═══════════════════════════════════════════════════════════════════════════════════════
    # DYNAMIC SECTION - USER-SPECIFIC (placed at END for cache optimization)
    # All variable/user-specific content goes here to maximize static prefix caching
    # ═══════════════════════════════════════════════════════════════════════════════════════
    
    # Build user-specific persona context
    persona_context_parts = []
    if name and name != "User":
        persona_context_parts.append(f"User name: {name}")
    if profession:
        persona_context_parts.append(f"Profession: {profession}")
    persona_context_str = "\n".join([f"- {item}" for item in persona_context_parts])
    
    # Handle profession display in dynamic section
    profession_display = profession if profession else "the user's"
    
    dynamic_section = f"""

═══════════════════════════════════════════════════════════════════════════════════════
**👤 USER-SPECIFIC CONTEXT:**
═══════════════════════════════════════════════════════════════════════════════════════

**PROFESSIONAL CONTEXT:**
{persona_context_str}

**🎯 RESPONSE ALIGNMENT:**
- Tailor ALL responses to {profession_display} profession
- Frame answers through their professional perspective
- Adapt to actual query intent - profession guides tone/examples but doesn't restrict topics
- Address the user appropriately based on their professional context"""

    final_prompt = static_section + dynamic_section
    return final_prompt


# =========================== API Endpoints ===========================

@router.post("/api/v2/persona")
async def save_persona(request: Request, persona_request: SimplePersonaRequest):
    """Save or update user persona in MongoDB"""
    try:
        user_id = get_secure_user_id(request)
        
        logging.info(f"[PERSONA_SAVE] Received persona request for authenticated user_id: {user_id}")
        logging.info(f"[PERSONA_SAVE] User type: {persona_request.user_type}")
        logging.info(f"[PERSONA_SAVE] Persona data: {persona_request.persona.dict()}")
        
        # Simplified validation - check required fields and profession
        if not persona_request.persona.name:
            logging.warning(f"[PERSONA_SAVE] Name is missing or empty: '{persona_request.persona.name}'")
            raise HTTPException(
                status_code=400, 
                detail="Name is required for persona"
            )
        
        if not persona_request.persona.mobile:
            logging.warning(f"[PERSONA_SAVE] Mobile is missing or empty: '{persona_request.persona.mobile}'")
            raise HTTPException(
                status_code=400, 
                detail="Mobile number is required for persona"
            )
        
        # Validate mobile number format (Indian mobile numbers)
        import re
        if not re.match(r'^[6-9]\d{9}$', persona_request.persona.mobile):
            logging.warning(f"[PERSONA_SAVE] Invalid mobile number format: '{persona_request.persona.mobile}'")
            raise HTTPException(
                status_code=400,
                detail="Mobile number must be a valid 10-digit number starting with 6-9"
            )
        
        # Always use General Professional - this is now the only supported profession
        # Override any provided profession to ensure consistency
        persona_request.persona.profession = "General Professional"
        logging.info(f"[PERSONA_SAVE] Setting profession to General Professional (only supported profession)")
        
        # Generate simplified RAG context
        rag_context = generate_simple_rag_context(
            persona_request.persona.dict(), 
            persona_request.user_type
        )
        
        # Prepare persona document
        persona_doc = {
            "user_id": user_id,  # Use authenticated user_id
            "user_type": persona_request.user_type,
            "persona": persona_request.persona.dict(),
            "rag_context": rag_context,
            "updated_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()  # Will be overwritten if updating
        }
        
        logging.info(f"[PERSONA_SAVE] Final document to store: {persona_doc}")
        
        # Upsert to MongoDB
        result = get_user_personas_col().replace_one(
            {"user_id": user_id},  # Use authenticated user_id
            persona_doc,
            upsert=True
        )
        
        # Also update the mobile number in the users collection
        users_update_result = get_users_col().update_one(
            {"email": user_id},  # user_id is the email
            {"$set": {"mobile": persona_request.persona.mobile, "name": persona_request.persona.name}},
            upsert=False  # Don't create if user doesn't exist
        )
        
        logging.info(f"[PERSONA_SAVE] Updated users collection for email {user_id}: {users_update_result.modified_count} document(s) modified")
        
        if result.upserted_id:
            logging.info(f"New persona created for user_id: {user_id}")
            
            # Send welcome email for new persona creation (non-blocking)
            try:
                # Get User Service URL from environment
                user_service_url = os.getenv('USER_SERVICE_URL', 'https://api.citra-ai.com/user-service')
                welcome_email_url = f"{user_service_url}/api/auth/send-welcome-email"
                
                # Get JWT token from request headers
                auth_header = request.headers.get('authorization', request.headers.get('Authorization', ''))
                if auth_header and auth_header.startswith('Bearer '):
                    token = auth_header.split(' ')[1]
                    
                    # Extract profession from persona data
                    profession = persona_request.persona.profession or 'Legal Professional'
                    
                    # Call User Service to send welcome email
                    email_payload = {"email": user_id, "profession": profession}
                    email_headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                    
                    # Fire and forget - don't await to prevent email failures from blocking persona creation
                    import threading
                    def send_welcome_email_async():
                        try:
                            response = requests.post(welcome_email_url, json=email_payload, headers=email_headers, timeout=10)
                            if response.status_code == 200:
                                logging.info(f"✅ Welcome email sent successfully for new persona: {user_id} (Profession: {profession})")
                            else:
                                logging.warning(f"⚠️ Failed to send welcome email for {user_id}: HTTP {response.status_code}")
                        except Exception as e:
                            logging.warning(f"⚠️ Exception sending welcome email for {user_id}: {str(e)}")
                    
                    # Start email sending in background thread
                    email_thread = threading.Thread(target=send_welcome_email_async, daemon=True)
                    email_thread.start()
                    
                    logging.info(f"📧 Welcome email initiated for new persona: {user_id} (Profession: {profession})")
                else:
                    logging.warning(f"⚠️ No valid authorization token found for welcome email: {user_id}")
                    
            except Exception as e:
                logging.warning(f"⚠️ Failed to initiate welcome email for {user_id}: {str(e)}")
            
            return JSONResponse(
                content={"status": "success", "message": "Persona created", "persona_id": str(result.upserted_id)},
                status_code=201
            )
        else:
            logging.info(f"Persona updated for user_id: {user_id}")
            return JSONResponse(
                content={"status": "success", "message": "Persona updated"},
                status_code=200
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error saving persona: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving persona: {str(e)}")

@router.options("/api/v2/persona")
async def options_persona():
    """Handle CORS preflight requests for persona endpoints"""
    return {"message": "CORS preflight handled"}

@router.get("/api/v2/persona")
async def get_persona(request: Request):
    """Retrieve user persona"""
    try:
        authenticated_user_id = get_secure_user_id(request)
        
        persona = get_user_personas_col().find_one({"user_id": authenticated_user_id})
        
        if persona:
            logging.debug(f"[PERSONA_DEBUG] Raw persona keys: {list(persona.keys())}")
            for key, value in persona.items():
                logging.debug(f"[PERSONA_DEBUG] {key}: {type(value)}")
            
            # Convert ObjectId to string before serialization
            if '_id' in persona:
                persona['_id'] = str(persona['_id'])
            
            # Use FastAPI's jsonable_encoder to handle datetime serialization
            serialized_persona = jsonable_encoder(persona)
            logging.debug(f"[PERSONA_DEBUG] Serialization successful")
            
            return JSONResponse(
                content={"status": "success", "persona": serialized_persona},
                status_code=200
            )
        else:
            return JSONResponse(
                content={"status": "not_found", "persona": None},
                status_code=404
            )
            
    except Exception as e:
        logging.error(f"Error retrieving persona: {str(e)}")
        logging.error(f"Error type: {type(e)}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error retrieving persona: {str(e)}")

@router.put("/api/v2/persona")
async def update_persona(request: Request, update_request: SimplePersonaUpdateRequest):
    """Update existing user persona"""
    try:
        authenticated_user_id = get_secure_user_id(request)
        
        # Check if persona exists
        existing_persona = user_personas_col.find_one({"user_id": authenticated_user_id})
        if not existing_persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        
        # Generate updated RAG context
        rag_context = generate_simple_rag_context(
            update_request.persona.dict(), 
            existing_persona.get("user_type", "professional")
        )
        
        # Update persona
        update_data = {
            "$set": {
                "persona": update_request.persona.dict(),
                "rag_context": rag_context,
                "updated_at": datetime.utcnow().isoformat()
            }
        }
        
        result = user_personas_col.update_one(
            {"user_id": authenticated_user_id},  # Use authenticated user_id
            update_data
        )
        
        if result.modified_count > 0:
            logging.info(f"Persona updated for user_id: {authenticated_user_id}")
            return JSONResponse(
                content={"status": "success", "message": "Persona updated"},
                status_code=200
            )
        else:
            return JSONResponse(
                content={"status": "no_changes", "message": "No changes made"},
                status_code=200
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating persona: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating persona: {str(e)}")

@router.delete("/api/v2/persona")
async def delete_persona(request: Request):
    """Delete user persona"""
    try:
        authenticated_user_id = get_secure_user_id(request)
        
        result = user_personas_col.delete_one({"user_id": authenticated_user_id})
        
        if result.deleted_count > 0:
            logging.info(f"Persona deleted for authenticated user_id: {authenticated_user_id}")
            return JSONResponse(
                content={"status": "success", "message": "Persona deleted"},
                status_code=200
            )
        else:
            return JSONResponse(
                content={"status": "not_found", "message": "Persona not found"},
                status_code=404
            )
            
    except Exception as e:
        logging.error(f"Error deleting persona: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting persona: {str(e)}")

@router.post("/api/v2/query/enhanced")
async def enhanced_query_with_persona(request: Request):
    """Process query with persona context for enhanced RAG responses"""
    try:
        data = await request.json()
        query = data.get("query")
        user_id = get_secure_user_id(request)
        
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Get user persona
        persona = user_personas_col.find_one({"user_id": user_id})
        
        if persona:
            # Enhance query with persona context
            enhanced_query = enhance_query_with_persona(query, persona)
            
            # Generate persona-aware system prompt
            system_prompt = generate_persona_system_prompt(persona)
            
            # Return enhanced context for RAG processing
            return JSONResponse(
                content={
                    "status": "success",
                    "enhanced_query": enhanced_query,
                    "system_prompt": system_prompt,
                    "persona_context": serialize_mongo_doc(persona),
                    "original_query": query
                },
                status_code=200
            )
        else:
            # No persona found, return minimal response
            return JSONResponse(
                content={
                    "status": "no_persona",
                    "enhanced_query": query,
                    "system_prompt": None,
                    "persona_context": None,
                    "original_query": query
                },
                status_code=200
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error processing enhanced query: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing enhanced query: {str(e)}")

@router.get("/api/v2/persona/rag-context")
async def get_persona_rag_context(request: Request):
    """Get RAG context for the authenticated user's persona"""
    try:
        authenticated_user_id = get_secure_user_id(request)
        
        persona = get_user_personas_col().find_one({"user_id": authenticated_user_id})
        
        if persona:
            rag_context = persona.get("rag_context", {})
            return JSONResponse(
                content={"status": "success", "rag_context": rag_context},
                status_code=200
            )
        else:
            return JSONResponse(
                content={"status": "not_found", "rag_context": None},
                status_code=404
            )
            
    except Exception as e:
        logging.error(f"Error retrieving RAG context: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving RAG context: {str(e)}")

# =========================== Health Check ===========================

@router.get("/api/v2/persona/health")
async def persona_health_check():
    """Health check for persona service"""
    try:
        # Test MongoDB connection
        user_personas_col.find_one({}, {"_id": 1})
        
        return JSONResponse(
            content={
                "status": "healthy",
                "service": "persona_management",
                "mongodb": "connected",
                "timestamp": datetime.utcnow().isoformat()
            },
            status_code=200
        )
    except Exception as e:
        logging.error(f"Persona service health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")
