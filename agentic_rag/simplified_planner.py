# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Simplified Intelligent Strategy Planner for Agentic RAG System

This planner uses LLM to intelligently analyze user queries and generate optimal
sub-queries based on:
1. User persona/profession (Legal Professional, Arbitrator, Engineering Professional, Contract Professional)
2. Query intent and domain
3. Vector database retrieval optimization
4. Multi-hop reasoning needs
"""

import os
import json
import re
import asyncio
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

@dataclass
class SubQuery:
    """Individual sub-query for vector database retrieval - contains ONLY optimized query text"""
    query_text: str
    priority: int = 1  # 1 = highest priority
    reasoning: str = ""
    retrieval_strategy: str = ""  # Specific instructions for vector DB retrieval

@dataclass 
class QueryIntent:
    """Query intent analysis with intelligent sub-query decomposition"""
    needs_decomposition: bool = False
    sub_queries: List[SubQuery] = field(default_factory=list)
    complexity: str = "simple"  # simple, moderate, complex
    reasoning: str = ""
    requires_project_data: bool = False  # For project management queries
    
    # Data routing
    requires_data: bool = True  # Whether query needs any data retrieval
    
    # For backward compatibility with orchestrator
    original_query: str = ""
    enhanced_query: str = ""
    
    # Legacy fields from old planner (for backward compatibility)
    requires_personal_context: bool = False
    decomposed_queries: List[str] = field(default_factory=list)
    confidence_score: float = 0.8
    original_complexity: str = "simple"  # Alias for complexity

class SimplifiedStrategyPlanner:
    """
    Intelligent strategy planner that uses LLM to analyze queries and generate
    optimal retrieval sub-queries based on user persona and vector DB characteristics
    """
    
    def __init__(self):
        logger.info("🧠 SimplifiedStrategyPlanner initialized with LLM")
    
    async def analyze_and_generate_subqueries(
        self,
        query: str,
        user_persona: Optional[Dict[str, Any]] = None,
        user_id: str = None,
        user_email: str = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> QueryIntent:
        """
        Intelligently analyze query and generate optimal sub-queries for vector DB retrieval.
        
        NOTE: SaaS data routing is now automatic via SaaSDataTool semantic search.
        No AI decision needed for supplementary sources.
        
        Args:
            query: User's original query
            user_persona: User profile including profession, domain expertise, etc.
                         Example: {'profession': 'Legal Professional', 'domain': 'Corporate Law'}
            user_id: Optional user ID for token tracking
            user_email: Optional user email for token tracking
        
        Returns:
            QueryIntent with generated sub-queries optimized for vector DB retrieval
        """
        
        # Build context for the LLM
        user_persona = user_persona or {}
        
        # Extract profession - handle both nested and flat structures
        if isinstance(user_persona.get('persona'), dict):
            profession = user_persona['persona'].get('profession', 'General User')
            domain = user_persona['persona'].get('domain', 'General')
        else:
            profession = user_persona.get('profession', 'General User')
            domain = user_persona.get('domain', 'General')
        
        # Build the intelligent prompt (split into system + user)
        system_prompt, user_prompt = self._build_analysis_prompt(
            query=query,
            profession=profession,
            domain=domain,
            conversation_history=conversation_history
        )
        
        try:
            logger.info(f"🧠 Analyzing query with LLM for profession: {profession}")
            logger.info(f"📝 Original query: '{query}'")
            

            from llm_oss import llm_call
            response = await asyncio.to_thread(lambda: llm_call(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=4000, json_mode=True, temperature=0.2, user_id=user_id, user_email=user_email, tier="large"))
            
            # Parse response
            analysis = self._extract_json_from_response(response)
            
            # Parse sub-queries (no validation - orchestrator handles routing)
            sub_queries = []
            for sq_data in analysis.get('sub_queries', []):
                sub_queries.append(SubQuery(
                    query_text=sq_data['query_text'],
                    priority=sq_data.get('priority', 1),
                    reasoning=sq_data.get('reasoning', ''),
                    retrieval_strategy=sq_data.get('retrieval_strategy', '')
                ))
            
            logger.info(f"✅ Generated {len(sub_queries)} sub-queries")
            for i, sq in enumerate(sub_queries, 1):
                logger.info(f"   Sub-query {i}: '{sq.query_text}'")
            
            # Determine if any sub-queries suggest multi-hop reasoning need
            # (Orchestrator will decide actual routing based on enabled sources)
            # Check if multi-hop is enabled via environment variable
            # Build backward compatibility fields
            complexity_value = analysis.get('complexity', 'simple')
            
            # Extract data requirement decision
            requires_data = analysis.get('requires_data', True)  # Default True (most queries need data)
            
            if not requires_data:
                logger.info(f"💬 Query doesn't require data (e.g., simple edit/clarification)")
            
            return QueryIntent(
                needs_decomposition=analysis.get('needs_decomposition', False),
                sub_queries=sub_queries,
                complexity=complexity_value,
                reasoning=analysis.get('reasoning', ''),
                # requires_project_data=analysis.get('requires_project_data', False),
                requires_project_data=False, # DISCONNECTED
                requires_data=requires_data,
                original_query=query,
                enhanced_query=query,
                
                # Backward compatibility fields
                requires_personal_context=True,  # Default to True, orchestrator decides actual routing
                decomposed_queries=[sq.query_text for sq in sub_queries],
                confidence_score=0.9,  # High confidence for LLM-generated queries
                original_complexity=complexity_value  # Alias for complexity
            )
            
        except Exception as e:
            logger.error(f"❌ Query analysis failed: {e}")
            # Fallback: single query with original text
            
            return QueryIntent(
                needs_decomposition=False,
                sub_queries=[SubQuery(
                    query_text=query,
                    priority=1,
                    reasoning='Fallback due to analysis error'
                )],
                complexity='simple',
                reasoning=f'Error during analysis: {str(e)}',
                requires_project_data=False,  # Default to False in fallback
                requires_data=True,  # Assume we need data in fallback
                original_query=query,
                enhanced_query=query,
                
                # Backward compatibility fields
                requires_personal_context=True,  # Default to True, orchestrator decides
                decomposed_queries=[query],
                confidence_score=0.5,  # Low confidence due to error
                original_complexity='simple'
            )
    
    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """
        Robustly extract JSON from LLM response, handling markdown blocks and extra text.
        Finds the largest substring between { and } that parses as valid JSON.
        """
        text = response.strip()
        
        # 1. Try standard extraction (if it's just JSON or simple markdown)
        clean_text = text
        if clean_text.startswith('```json'):
            clean_text = clean_text[7:]
        elif clean_text.startswith('```'):
            clean_text = clean_text[3:]
        if clean_text.endswith('```'):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            pass  # Fall through to more robust extraction
            
        # 2. Try to find the first '{' and last '}'
        # This handles "Here is the JSON: {...} I hope this helps."
        try:
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = text[start_idx : end_idx + 1]
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass
            
        # 3. If that fails (maybe multiple JSONs?), try regex for balanced braces? 
        # For now, let's just log and re-raise the original error from the cleanest attempt
        # to ensure we don't mask the underlying issue if there really is no JSON.
        
        # One last attempt: maybe the model output python object syntax?
        # (Not implementing eval() for safety)
        
        # 4. Truncation recovery: the JSON was cut off mid-stream (e.g. max_tokens hit).
        # Walk backwards to find the last complete sub_queries item, then close the structure.
        try:
            start_idx = text.find('{')
            if start_idx != -1:
                fragment = text[start_idx:]
                
                # Find the last complete object closing inside the fragment
                # Strategy: find last '}'  that brings brace depth back to 1 (inside root object)
                depth = 0
                in_string = False
                escape_next = False
                last_safe_end = -1  # index of last '}' at depth=1 (completes a sub_query item)
                
                for i, ch in enumerate(fragment):
                    if escape_next:
                        escape_next = False
                        continue
                    if ch == '\\' and in_string:
                        escape_next = True
                        continue
                    if ch == '"':
                        in_string = not in_string
                        continue
                    if not in_string:
                        if ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1
                            if depth == 1:
                                # This closes a sub_query item (depth returns to root-object level)
                                last_safe_end = i
                
                if last_safe_end != -1:
                    # Close: end the sub_queries array and the root object
                    salvaged = fragment[:last_safe_end + 1] + ']}'
                    try:
                        parsed = json.loads(salvaged)
                        logger.warning("⚠️ [PLANNER] Recovered truncated JSON — some sub-queries may be missing")
                        return parsed
                    except json.JSONDecodeError:
                        pass
                
                # Last resort: extract scalar fields via regex and return minimal valid object
                complexity_match = re.search(r'"complexity"\s*:\s*"(simple|moderate|complex)"', fragment)
                requires_data_match = re.search(r'"requires_data"\s*:\s*(true|false)', fragment)
                complexity_val = complexity_match.group(1) if complexity_match else 'simple'
                requires_data_val = requires_data_match.group(1) != 'false' if requires_data_match else True
                logger.warning("⚠️ [PLANNER] Using regex-salvaged minimal JSON from truncated response")
                return {
                    'complexity': complexity_val,
                    'needs_decomposition': False,
                    'reasoning': 'Salvaged from truncated response',
                    'requires_project_data': False,
                    'requires_data': requires_data_val,
                    'sub_queries': []
                }
        except Exception:
            pass
        
        # Re-raise with a clear message
        try:
            return json.loads(clean_text)
        except Exception as e:
            raise ValueError(f"Could not extract valid JSON from response. Error: {e}")

    def _format_conversation_context(self, conversation_history: Optional[List[Dict[str, Any]]] = None) -> str:
        """Format recent conversation history for the planner prompt so follow-up queries are contextualized."""
        if not conversation_history:
            return ""
        # Keep last 3 messages, truncate each to 200 words max
        recent = conversation_history[-3:]
        lines = []
        for msg in recent:
            if not isinstance(msg, dict):
                continue
            role = msg.get('role', 'user')
            content = msg.get('content', msg.get('message', '')).strip()
            if not content:
                continue
            words = content.split()
            if len(words) > 200:
                content = ' '.join(words[:200]) + "..."
            label = "User" if role == "user" else "Assistant"
            lines.append(f"  {label}: {content}")
        if not lines:
            return ""
        return "\n\n**CONVERSATION CONTEXT (use this to understand follow-up queries):**\n" + "\n".join(lines)

    def _build_analysis_prompt(
        self,
        query: str,
        profession: str,
        domain: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> tuple:
        """Build the analysis prompt split into (system_prompt, user_prompt).
        
        Returns a tuple of (system_prompt, user_prompt) for the LLM call.
        System prompt contains role and instructions; user prompt contains the specific query.
        
        NOTE: SaaS data routing is handled automatically via semantic search
        on the Milvus `saas` collection. No AI decision needed.
        """
        
        system_prompt = """You are an intelligent query analyzer for a RAG system.
Analyze user queries and generate optimal sub-queries for vector database retrieval.
Respond with JSON only — no explanations, no markdown, no text outside the JSON object.

VECTOR DATABASE:
- 768-dim semantic embeddings with hybrid search (dense + sparse)
- Contains user's documents, notes, files, and professional materials

TASK:
1. Analyze query complexity and intent
2. **If CONVERSATION CONTEXT is provided, you MUST resolve follow-up/vague queries using it.**
   - Pronouns ("it", "this", "they"), elliptical phrases ("what are risks", "summarize", "more details"),
     and bare topic words inherit subject matter from the most recent user/assistant turn.
   - In this case `requires_data` MUST be true and you MUST emit at least one concrete sub-query
     that combines the new query with the inherited subject (document name, entity, topic, etc.).
3. Set "requires_data" to false ONLY when there is NO conversation context AND the query is a pure
   edit/format change ("fix spelling", "convert to bullets") OR a pure clarification with nothing to retrieve.
   Never set it to false just because the standalone query looks vague — check context first.
4. Generate sub-queries optimized for semantic search — each targeting ONE retrieval aspect.

SUB-QUERY PRINCIPLES:
- Use precise, domain-specific terminology
- Include specific names, numbers, identifiers (especially the document/topic from prior turns)
- SIMPLE: single sub-query. MODERATE: usually single. COMPLEX: decompose into distinct aspects

requires_project_data: true only for project/case status, milestones, tasks, risks, timelines, budgets, teams.
requires_data: see rule 3 above. Default true.

LEGAL QUERIES: use "appeal allowed/dismissed", "conviction upheld/set aside", "judgment", "decree". Include IPC/BNS sections, case numbers, party names.

JSON SCHEMA:
{"complexity": "simple|moderate|complex", "needs_decomposition": bool, "reasoning": "brief", "requires_project_data": bool, "requires_data": bool, "sub_queries": [{"query_text": "optimized query", "priority": 1, "reasoning": "why", "retrieval_strategy": "exact_match|semantic_broad|semantic_focused"}]}"""

        user_prompt = f"""User profession: {profession}
Domain: {domain}

Query: "{query}"
{self._format_conversation_context(conversation_history)}"""
        
        return system_prompt, user_prompt
    
    async def _get_user_folders(self, user_id: str) -> List[str]:
        """Get user's folder IDs (categories) for filtering."""
        try:
            # Import here to avoid circular dependency
            from folder_management import FolderManager
            from citra_mongo import MongoDBManager
            
            # Initialize managers
            mongo_manager = MongoDBManager()
            folder_manager = FolderManager(mongo_manager)
            
            # Get user's folders
            folders = await folder_manager.list_folders(user_id)
            folder_ids = [folder.get('_id') or folder.get('folder_id') for folder in folders]
            
            logger.info(f"📁 Retrieved {len(folder_ids)} folders for user {user_id}")
            return folder_ids
            
        except Exception as e:
            logger.warning(f"⚠️ Could not retrieve folders for user {user_id}: {e}")
            return []


# Example usage function
async def example_usage():
    """Example of how to use the simplified planner"""
    
    planner = SimplifiedStrategyPlanner()
    
    # Example 1: Legal Professional query
    legal_result = await planner.analyze_and_generate_subqueries(
        query="Give details of case Independent Sugar Corporation Limited vs Girish Sriram Juneja and its outcome and final supreme court judgment, and the winning party?",
        user_persona={
            'profession': 'Legal Professional',
            'domain': 'Corporate Law'
        }
    )
    
    print("Legal Professional Query Analysis:")
    print(f"Complexity: {legal_result.complexity}")
    print(f"Decomposition needed: {legal_result.needs_decomposition}")
    print(f"Sub-queries generated: {len(legal_result.sub_queries)}")
    for i, sq in enumerate(legal_result.sub_queries, 1):
        print(f"  {i}. [{sq.query_type}] {sq.query_text}")
        print(f"     Strategy: {sq.retrieval_strategy}")
        print(f"     Reasoning: {sq.reasoning}")
    
    # Example 2: General user query
    general_result = await planner.analyze_and_generate_subqueries(
        query="What is the company sick leave policy?",
        user_persona={
            'profession': 'Employee',
            'domain': 'General'
        }
    )
    
    print("\nGeneral User Query Analysis:")
    print(f"Complexity: {general_result.complexity}")
    print(f"Decomposition needed: {general_result.needs_decomposition}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())
