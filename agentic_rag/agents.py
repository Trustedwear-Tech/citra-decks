"""
Retrieval Agents for Agentic RAG System
=======================================

ARCHITECTURAL NOTE: Proper LangGraph architecture
- TRUE AGENTS (Make LLM decisions): Autonomous reasoning with LLM-based decision-making
- TOOLS (Data retrieval only): PersonalDataTool, EnterpriseDataTool, etc. in tools.py

All classes in this file (AdvancedQuerySynthesis, AnswerEvaluation, KnowledgeGraphTool, 
ProjectManagementTool) are utility classes or tools that support the main agent workflow.
"""

import asyncio
import logging
import math
import os
import re
import sys
from typing import List, Dict, Any, Optional, Tuple
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from collections import Counter

# Add parent directory to path so we can import from parent directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import unified metadata schema for consistent field names (matching multi_hop_search_service)
from models.unified_metadata_schema import MetadataConstants

logger = logging.getLogger(__name__)

# Removed MultiHopState dataclass - no longer used

class BaseRetrievalAgent(ABC):
    """Base class for all retrieval agents"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        user_id: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Retrieve contexts for the given query"""
        pass

# ============================================================================
# DEPRECATED AGENT CLASSES REMOVED
# ============================================================================
# The following classes have been removed as they are not true autonomous agents:
# - PersonalDataAgent: Use PersonalDataTool from tools.py instead
# - EnterpriseDataAgent: Use EnterpriseDataTool from tools.py instead
# - InternetSearchAgent: Use InternetSearchTool (to be created) instead
# - LegalSearchAgent: Use LegalSearchTool (to be created) instead
# - HybridRetrievalAgent: Orchestrator now uses source_provider and tools directly
# ============================================================================

class AdvancedQuerySynthesis:
    """Advanced query synthesis capabilities from MultiHopRAGService (Phase 1)"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.QuerySynthesis")
        
    async def synthesize_next_query(
        self, 
        current_insights: List[str], 
        contexts: List[Dict], 
        original_query: str,
        user_id: str = None,
        user_email: str = None
    ) -> Optional[str]:
        """Generate next hop query based on insights and context gaps"""
        try:
            # Use llm_oss for query synthesis
            from llm_oss import llm_call
            
            # Build synthesis prompt
            context_summary = self._summarize_contexts(contexts)
            
            synthesis_prompt = f"""
            Based on the current analysis for: "{original_query}"
            
            Current insights found:
            {chr(10).join(current_insights)}
            
            Context summary:
            {context_summary}
            
            What specific aspect or relationship should be explored next to provide a more complete answer?
            Generate a focused follow-up query that explores missing connections or deeper relationships.
            
            If the current insights are sufficient, respond with "COMPLETE".
            Otherwise, provide a specific, focused query that will uncover additional relevant information.
            """
            
            response = await asyncio.to_thread(lambda: llm_call(
                user_prompt=synthesis_prompt,
                system_prompt="You are a query synthesis expert.",
                user_id=user_id, 
                user_email=user_email,
                tier="large",
            ))
            next_query = response.strip() if response else None
            
            if next_query and next_query.upper() != "COMPLETE":
                self.logger.info(f"🔍 Synthesized next query: {next_query}")
                return next_query
            else:
                self.logger.info("✅ Query synthesis indicates completion")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Query synthesis failed: {e}")
            return None
    
    def _summarize_contexts(self, contexts: List[Dict]) -> str:
        """Summarize contexts for query synthesis"""
        if not contexts:
            return "No contexts available"
        
        summaries = []
        for i, ctx in enumerate(contexts[:5]):  # Limit to avoid token overflow
            text = ctx.get('metadata', {}).get('text', ctx.get('text', ''))[:200]
            source = ctx.get('multi_hop_source', ctx.get('source', 'unknown'))
            summaries.append(f"{i+1}. [{source}] {text}...")
        
        return chr(10).join(summaries)
    
    def _format_conversation_history(self, history: List[Dict]) -> str:
        """Format conversation history for context"""
        if not history:
            return ""
        
        formatted = ["Previous conversation context:"]
        for item in history[-3:]:  # Last 3 exchanges
            if isinstance(item, dict):
                role = item.get('role', 'user')
                content = item.get('content', '')[:150]
                formatted.append(f"{role}: {content}...")
        
        return chr(10).join(formatted)

class AnswerEvaluation:
    """Answer evaluation capabilities from MultiHopRAGService (Phase 1)"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.AnswerEvaluation")
    
    async def evaluate_answer_completeness(
        self, 
        query: str, 
        answer: str, 
        contexts: List[Dict],
        insights: List[str],
        user_id: str = None,
        user_email: str = None
    ) -> Dict[str, Any]:
        """Evaluate answer completeness and suggest improvements"""
        try:
            # Use llm_oss for answer evaluation
            from llm_oss import llm_call
            
            evaluation_prompt = f"""
            Evaluate this multi-hop analysis for completeness and accuracy:
            
            Original Query: "{query}"
            
            Generated Answer: "{answer}"
            
            Available Insights: {len(insights)} insights
            Available Contexts: {len(contexts)} contexts
            
            Rate the answer on these criteria (1-10 scale):
            1. Completeness: Does it fully address the query?
            2. Accuracy: Is the information factually correct?
            3. Coherence: Does it logically connect different pieces of information?
            4. Depth: Does it provide sufficient detail and analysis?
            
            Respond in this format:
            COMPLETENESS: [score]/10
            ACCURACY: [score]/10  
            COHERENCE: [score]/10
            DEPTH: [score]/10
            OVERALL: [average]/10
            SUGGESTIONS: [specific improvements needed]
            """
            
            response = await asyncio.to_thread(lambda: llm_call(
                user_prompt=evaluation_prompt,
                system_prompt="You are an answer evaluation expert.",
                user_id=user_id, 
                user_email=user_email,
                tier="large",
            ))
            evaluation_text = response.strip() if response else ""
            
            # Parse evaluation scores
            evaluation = self._parse_evaluation_response(evaluation_text)
            evaluation['evaluation_text'] = evaluation_text
            evaluation['timestamp'] = datetime.now().isoformat()
            
            self.logger.info(f"📊 Answer evaluation: Overall {evaluation.get('overall', 0):.1f}/10")
            return evaluation
            
        except Exception as e:
            self.logger.error(f"❌ Answer evaluation failed: {e}")
            return {
                'completeness': 5.0,
                'accuracy': 5.0,
                'coherence': 5.0,
                'depth': 5.0,
                'overall': 5.0,
                'suggestions': f"Evaluation failed: {e}",
                'error': str(e)
            }
    
    def _parse_evaluation_response(self, response_text: str) -> Dict[str, Any]:
        """Parse evaluation response into structured data"""
        evaluation = {}
        
        try:
            lines = response_text.split('\n')
            for line in lines:
                if 'COMPLETENESS:' in line:
                    evaluation['completeness'] = float(line.split('/')[0].split(':')[-1].strip())
                elif 'ACCURACY:' in line:
                    evaluation['accuracy'] = float(line.split('/')[0].split(':')[-1].strip())
                elif 'COHERENCE:' in line:
                    evaluation['coherence'] = float(line.split('/')[0].split(':')[-1].strip())
                elif 'DEPTH:' in line:
                    evaluation['depth'] = float(line.split('/')[0].split(':')[-1].strip())
                elif 'OVERALL:' in line:
                    evaluation['overall'] = float(line.split('/')[0].split(':')[-1].strip())
                elif 'SUGGESTIONS:' in line:
                    evaluation['suggestions'] = line.split('SUGGESTIONS:')[-1].strip()
            
            # Calculate overall if not provided
            if 'overall' not in evaluation and all(k in evaluation for k in ['completeness', 'accuracy', 'coherence', 'depth']):
                evaluation['overall'] = sum([evaluation['completeness'], evaluation['accuracy'], 
                                          evaluation['coherence'], evaluation['depth']]) / 4
                                          
        except Exception as e:
            # Fallback values
            evaluation = {
                'completeness': 5.0, 'accuracy': 5.0, 'coherence': 5.0, 'depth': 5.0,
                'overall': 5.0, 'suggestions': f"Parse error: {e}"
            }
        
        return evaluation


# KnowledgeGraphTool and ProjectManagementTool removed at
# generation time: both defer-import modules this product does
# not carry, and neither has a caller anywhere in the tree.
