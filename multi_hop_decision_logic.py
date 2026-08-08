#!/usr/bin/env python3
"""
Multi-Hop Decision Logic in LangGraph Orchestrator
==================================================

This document explains how the LangGraph orchestrator decides whether to use 
multi-hop reasoning at the first level of query analysis.
"""

print("""
🎯 MULTI-HOP DECISION FLOW IN LANGGRAPH ORCHESTRATOR
===================================================

The LangGraph orchestrator uses a sophisticated 2-stage decision process to determine 
whether to use multi-hop reasoning:

STAGE 1: QUERY INTENT ANALYSIS (StrategyPlanner)
-----------------------------------------------

1️⃣ **LLM Analysis**
   The StrategyPlanner sends the query to LLM with specific criteria:

   MULTI-HOP TRIGGERS:
   ✓ needs_deep_research: Requires finding deep relationships, connections
   ✓ needs_relationship_mapping: Needs to map relationships between concepts  
   ✓ needs_multi_hop: Requires iterative searches with evolving questions

   EXAMPLE ANALYSIS PROMPT:
   "Analyze this query for multi-hop requirements:
   - Does this need iterative searches with evolving questions?
   - Does this require finding deep relationships, connections, or multi-step reasoning?
   - Consider if deep_research_requested=true or query_type='multi_hop'"

2️⃣ **Query Types That Trigger Multi-Hop:**

   ❌ SIMPLE QUERIES (No Multi-Hop):
   - "What is the company sick leave policy?"
   - "Show me John's recent files"
   - "Find documents about project X"

   ✅ COMPLEX QUERIES (Multi-Hop Triggered):
   - "How has the new drug policy affected patient outcomes?" 
   - "What's the relationship between X and Y trends?"
   - "Analyze the impact of policy changes on performance"
   - "How do these factors connect to overall results?"

3️⃣ **Parameter Overrides:**
   Even if llm says no multi-hop, these parameters force it:
   - additional_sources.get('deep_research', False) = True
   - additional_sources.get('query_type') == 'multi_hop'

STAGE 2: STRATEGY PLANNING & ROUTING
-----------------------------------

4️⃣ **Strategy Planning Logic:**
   ```python
   # In plan_retrieval_strategies()
   if intent.needs_multi_hop or intent.needs_deep_research or intent.needs_relationship_mapping:
       strategies.append(RetrievalStrategy.MULTI_HOP)
   ```

5️⃣ **LangGraph Routing Decision:**
   ```python
   # In route_execution()
   def route_execution(self, state: QueryState) -> str:
       strategies = state.get('selected_strategies', [])
       
       # If multi-hop is needed, route to multi-hop
       if RetrievalStrategy.MULTI_HOP in strategies:
           return "multi_hop"  # ← GOES TO MULTI-HOP PATH
       
       # Otherwise use regular retrieval
       if strategies:
           return "retrieval"  # ← GOES TO REGULAR AGENT PATH
   ```

DECISION CRITERIA SUMMARY:
=========================

The orchestrator will choose MULTI-HOP if ANY of these are true:

🔍 **AI Analysis (LLM decides):**
   - Query requires deep research/analysis
   - Query needs relationship mapping
   - Query needs iterative multi-hop reasoning
   - Query asks "how", "why", "what's the impact", "analyze", "relate"

⚡ **Parameter Overrides:**
   - deep_research=True in additional_sources  
   - query_type='multi_hop' in additional_sources

📊 **Complexity Indicators:**
   - Multiple concepts that need to be connected
   - Causal relationship questions
   - Trend analysis requests
   - Impact assessment queries

LANGGRAPH WORKFLOW PATHS:
========================

PATH 1: MULTI-HOP (Complex Queries)
   Query → Analyze → Plan → Route → execute_multi_hop → generate_response

PATH 2: REGULAR RETRIEVAL (Simple Queries)  
   Query → Analyze → Plan → Route → execute_retrieval → merge_contexts → generate_response

The key insight: Multi-hop is decided by AI analysis of query complexity, 
not by hardcoded rules! 🤖
""")

# Example demonstration
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 EXAMPLE QUERY ANALYSIS")
    print("="*60)
    
    examples = [
        {
            "query": "What is the company policy?",
            "multi_hop": False,
            "reason": "Simple information retrieval - no deep analysis needed"
        },
        {
            "query": "How has the new policy affected employee satisfaction and what are the long-term implications?",
            "multi_hop": True,
            "reason": "Requires: relationship analysis (policy→satisfaction), causal reasoning, trend analysis"
        },
        {
            "query": "Show me Dr. Smith's patient records",
            "multi_hop": False,
            "reason": "Simple entity-specific data retrieval"
        },
        {
            "query": "Analyze how Dr. Smith's treatment approaches compare to hospital outcomes and industry standards",
            "multi_hop": True,
            "reason": "Requires: multi-step comparison, relationship mapping, complex analysis"
        }
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"\n{i}️⃣ Query: \"{example['query']}\"")
        print(f"   Multi-Hop: {'✅ YES' if example['multi_hop'] else '❌ NO'}")
        print(f"   Reason: {example['reason']}")
    
    print(f"\n{'='*60}")
    print("🎯 The orchestrator uses AI to automatically detect complexity!")