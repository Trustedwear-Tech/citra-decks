# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Structured Prompt Builder
=========================
Builds specialized prompts for generating charts and tables from structured data.

This service creates prompts that:
1. Instruct AI to generate Chart.js configs for visual outputs (presentations, reports, printables)
2. Instruct AI to generate markdown tables for chat responses
3. Provide clear data context and schema information to the AI
"""

import logging
import json
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class OutputMode(Enum):
    """Output format for structured data visualization"""
    CHART = "chart"  # Chart.js compatible configuration
    TABLE = "table"  # Markdown table format


@dataclass
class PromptContext:
    """Context for prompt generation"""
    user_query: str
    data_source: str  # 'excel', 'json', 'saas', 'document'
    provider: Optional[str] = None  # SaaS provider if applicable
    schema_fields: List[str] = None
    record_count: int = 0
    sample_records: List[Dict[str, Any]] = None
    source_filename: Optional[str] = None
    narrative_context: str = ""
    page_context: Optional[Dict[str, Any]] = None  # Current slide/page for context


# ===================== CHART GENERATION PROMPTS =====================

CHART_SYSTEM_PROMPT = """You are a data visualization expert. Your task is to analyze structured data and generate a Chart.js compatible configuration.

RULES:
1. Always return a valid JSON object with the Chart.js config structure
2. Choose the most appropriate chart type based on the data:
   - bar: For comparing categories or discrete values
   - line: For showing trends over time or continuous data
   - pie/doughnut: For showing proportions of a whole (use when total makes sense)
   - bar (horizontal): Same as bar but with options.indexAxis = "y" for horizontal layout
   - bar (stacked): Same as bar but with options.scales.x.stacked = true and options.scales.y.stacked = true
   - line (area): Same as line but with dataset fill = true and backgroundColor with alpha
   - line (stepped): Same as line but with dataset stepped = true
   - scatter: For showing correlation between two numeric variables. Use {x, y} point objects instead of labels/values
   - bubble: Like scatter but with a size dimension. Use {x, y, r} point objects
   - radar: For comparing multiple variables across categories (spider chart)
   - polarArea: Like pie but all segments have equal angle, varying radius
3. Select appropriate fields for labels (X-axis) and values (Y-axis)
4. Use clear, readable labels
5. Limit data points to 15-20 for readability (aggregate if needed)
6. Use the provided color palette for consistency

RESPONSE FORMAT:
Return ONLY a JSON object with this structure:
{
    "type": "bar|line|pie|doughnut|scatter|bubble|radar|polarArea",
    "data": {
        "labels": ["Label1", "Label2", ...],
        "datasets": [{
            "label": "Dataset Label",
            "data": [value1, value2, ...],
            "backgroundColor": [...],
            "borderColor": [...],
            "borderWidth": 1
        }]
    },
    "options": {
        "responsive": true,
        "plugins": {
            "title": {"display": true, "text": "Chart Title"},
            "legend": {"display": true|false}
        },
        "scales": {
            "x": {"title": {"display": true, "text": "X Axis Label"}},
            "y": {"title": {"display": true, "text": "Y Axis Label"}, "beginAtZero": true}
        }
    }
}

VARIANT OPTIONS:
- Horizontal bar: type="bar", add "indexAxis": "y" in options
- Stacked bar: type="bar", add "stacked": true to both x and y scales
- Area chart: type="line", add "fill": true to dataset, use semi-transparent backgroundColor
- Step line: type="line", add "stepped": true to dataset
- Scatter: type="scatter", data is [{x: 1, y: 2}, ...] instead of flat values, no labels needed
- Bubble: type="bubble", data is [{x: 1, y: 2, r: 8}, ...], r controls bubble size
- Radar/polarArea: omit scales option (like pie/doughnut)

COLOR PALETTE (use these colors):
- Blue: #3B82F6
- Green: #10B981
- Amber: #F59E0B
- Red: #EF4444
- Purple: #8B5CF6
- Pink: #EC4899
- Cyan: #06B6D4
- Lime: #84CC16
- Orange: #F97316
- Indigo: #6366F1

For pie/doughnut/radar/polarArea, omit the scales option.
For scatter/bubble, use numeric x/y axes with descriptive titles."""


def build_chart_prompt(context: PromptContext) -> str:
    """
    Build a prompt for generating Chart.js configuration from structured data.
    
    Args:
        context: PromptContext with data information
        
    Returns:
        Formatted prompt string for AI
    """
    prompt_parts = []
    
    # User's request
    prompt_parts.append(f"USER REQUEST: {context.user_query}")
    prompt_parts.append("")
    
    # Data source information
    prompt_parts.append("=== DATA SOURCE INFORMATION ===")
    prompt_parts.append(f"Source Type: {context.data_source}")
    if context.provider:
        prompt_parts.append(f"Provider: {context.provider}")
    if context.source_filename:
        prompt_parts.append(f"File: {context.source_filename}")
    prompt_parts.append(f"Total Records: {context.record_count}")
    prompt_parts.append(f"Available Fields: {', '.join(context.schema_fields or [])}")
    prompt_parts.append("")
    
    # Sample data
    if context.sample_records:
        prompt_parts.append("=== SAMPLE DATA (JSON) ===")
        # Limit to 50 records max for prompt size
        sample_data = context.sample_records[:50]
        prompt_parts.append(json.dumps(sample_data, indent=2, default=str))
        prompt_parts.append("")
    
    # Page context for better relevance
    if context.page_context:
        prompt_parts.append("=== CURRENT PAGE CONTEXT ===")
        prompt_parts.append(f"Page Title: {context.page_context.get('title', 'N/A')}")
        prompt_parts.append(f"Page Topic: {context.page_context.get('topic', 'N/A')}")
        prompt_parts.append("")
    
    # Narrative context if available
    if context.narrative_context:
        prompt_parts.append("=== SUPPLEMENTARY CONTEXT ===")
        prompt_parts.append(context.narrative_context[:1000])  # Limit size
        prompt_parts.append("")
    
    # Instructions
    prompt_parts.append("=== INSTRUCTIONS ===")
    prompt_parts.append("Analyze the data above and generate a Chart.js configuration that best visualizes the data to answer the user's request.")
    prompt_parts.append("Return ONLY the JSON configuration object, no explanation needed.")
    
    return "\n".join(prompt_parts)


# ===================== TABLE GENERATION PROMPTS =====================

TABLE_SYSTEM_PROMPT = """You are a data analyst assistant. Your task is to present structured data as a clear, formatted markdown table.

RULES:
1. Create a well-formatted markdown table from the data
2. Select the most relevant columns (max 6-8 for readability)
3. Use clear, human-readable column headers
4. Format numbers appropriately (currency with $, percentages with %)
5. Truncate very long text values with "..."
6. Sort data meaningfully if a natural order exists
7. Include a brief summary sentence above the table
8. If there are many records, show top 15-20 with a note about remaining

RESPONSE FORMAT:
Start with a brief summary sentence, then the markdown table:

Based on the data, here's a summary of [what the data shows]:

| Column1 | Column2 | Column3 |
|---------|---------|---------|
| value1  | value2  | value3  |
| ...     | ...     | ...     |

*Showing X of Y total records*

Additional insights: [any notable patterns or highlights]"""


def build_table_prompt(context: PromptContext) -> str:
    """
    Build a prompt for generating markdown table from structured data.
    
    Args:
        context: PromptContext with data information
        
    Returns:
        Formatted prompt string for AI
    """
    prompt_parts = []
    
    # User's request
    prompt_parts.append(f"USER REQUEST: {context.user_query}")
    prompt_parts.append("")
    
    # Data source information
    prompt_parts.append("=== DATA SOURCE ===")
    prompt_parts.append(f"Type: {context.data_source}")
    if context.provider:
        prompt_parts.append(f"Provider: {context.provider}")
    if context.source_filename:
        prompt_parts.append(f"File: {context.source_filename}")
    prompt_parts.append(f"Records: {context.record_count}")
    prompt_parts.append(f"Fields: {', '.join(context.schema_fields or [])}")
    prompt_parts.append("")
    
    # Full data for table generation
    if context.sample_records:
        prompt_parts.append("=== DATA (JSON) ===")
        # Include more records for table view
        sample_data = context.sample_records[:50]
        prompt_parts.append(json.dumps(sample_data, indent=2, default=str))
        prompt_parts.append("")
    
    # Narrative context
    if context.narrative_context:
        prompt_parts.append("=== ADDITIONAL CONTEXT ===")
        prompt_parts.append(context.narrative_context[:500])
        prompt_parts.append("")
    
    # Instructions
    prompt_parts.append("=== INSTRUCTIONS ===")
    prompt_parts.append("Create a clear markdown table from this data that answers the user's question.")
    prompt_parts.append("Include a summary and any notable insights.")
    
    return "\n".join(prompt_parts)


# ===================== COMBINED PROMPT BUILDER =====================

class StructuredPromptBuilder:
    """
    Builds prompts for structured data visualization based on output mode.
    """
    
    def __init__(self):
        self.chart_system_prompt = CHART_SYSTEM_PROMPT
        self.table_system_prompt = TABLE_SYSTEM_PROMPT
    
    def build_prompt(
        self,
        user_query: str,
        structured_result: Any,  # StructuredDataResult from retriever
        output_mode: OutputMode,
        page_context: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """
        Build system prompt and user prompt for AI generation.
        
        Args:
            user_query: User's natural language query
            structured_result: StructuredDataResult with file schemas + sample rows
            output_mode: CHART or TABLE
            page_context: Optional current page/slide context
            
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        # Build context object
        context = PromptContext(
            user_query=user_query,
            data_source=structured_result.data_source or 'unknown',
            provider=structured_result.provider,
            schema_fields=structured_result.schema_fields,
            record_count=structured_result.record_count,
            sample_records=structured_result.records,
            source_filename=structured_result.source_filename,
            narrative_context=structured_result.narrative_context,
            page_context=page_context
        )
        
        if output_mode == OutputMode.CHART:
            return self.chart_system_prompt, build_chart_prompt(context)
        else:
            return self.table_system_prompt, build_table_prompt(context)
    
    def build_chart_prompt_simple(
        self,
        user_query: str,
        data: List[Dict[str, Any]],
        schema_fields: List[str],
        data_source: str = "document",
        page_context: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """
        Simplified method to build chart prompt from raw data.
        
        Args:
            user_query: User's query
            data: List of record dictionaries
            schema_fields: List of field names
            data_source: Source type
            page_context: Optional page context
            
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        context = PromptContext(
            user_query=user_query,
            data_source=data_source,
            schema_fields=schema_fields,
            record_count=len(data),
            sample_records=data,
            page_context=page_context
        )
        
        return self.chart_system_prompt, build_chart_prompt(context)
    
    def build_table_prompt_simple(
        self,
        user_query: str,
        data: List[Dict[str, Any]],
        schema_fields: List[str],
        data_source: str = "document"
    ) -> tuple:
        """
        Simplified method to build table prompt from raw data.
        
        Args:
            user_query: User's query
            data: List of record dictionaries
            schema_fields: List of field names
            data_source: Source type
            
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        context = PromptContext(
            user_query=user_query,
            data_source=data_source,
            schema_fields=schema_fields,
            record_count=len(data),
            sample_records=data
        )
        
        return self.table_system_prompt, build_table_prompt(context)
    
    def extract_chart_config(self, ai_response: str) -> Optional[Dict[str, Any]]:
        """
        Extract Chart.js configuration from AI response.
        
        Args:
            ai_response: Raw AI response text
            
        Returns:
            Parsed Chart.js config dict or None
        """
        try:
            # Try direct JSON parse
            response = ai_response.strip()
            
            # Remove markdown code blocks if present
            if response.startswith('```'):
                lines = response.split('\n')
                # Remove first and last lines if they're code fence markers
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                response = '\n'.join(lines)
            
            # Find JSON object
            start_idx = response.find('{')
            if start_idx == -1:
                return None
            
            # Find matching closing brace
            brace_count = 0
            end_idx = start_idx
            for i in range(start_idx, len(response)):
                if response[i] == '{':
                    brace_count += 1
                elif response[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            json_str = response[start_idx:end_idx]
            config = json.loads(json_str)
            
            # Validate it has required Chart.js structure
            if 'type' in config and 'data' in config:
                return config
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to extract chart config: {e}")
            return None
    
    def validate_chart_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate Chart.js configuration structure.
        
        Args:
            config: Chart configuration dict
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Required fields
            if 'type' not in config:
                return False
            if config['type'] not in ['bar', 'line', 'pie', 'doughnut', 'radar', 'scatter', 'bubble', 'polarArea']:
                return False
            
            if 'data' not in config:
                return False
            
            data = config['data']
            chart_type = config['type']
            
            # scatter and bubble charts use point data [{x,y}] / [{x,y,r}] and don't require labels
            if chart_type not in ('scatter', 'bubble'):
                if 'labels' not in data or not isinstance(data['labels'], list):
                    return False
            
            if 'datasets' not in data:
                return False
            
            if not isinstance(data['datasets'], list) or len(data['datasets']) == 0:
                return False
            
            # Check first dataset
            dataset = data['datasets'][0]
            if 'data' not in dataset or not isinstance(dataset['data'], list):
                return False
            
            return True
            
        except Exception:
            return False


# Module-level singleton
_prompt_builder = None

def get_structured_prompt_builder() -> StructuredPromptBuilder:
    """Get or create singleton StructuredPromptBuilder instance"""
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = StructuredPromptBuilder()
    return _prompt_builder
