# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Shared test fixtures for the planner / edit-all test suites.

Provides realistic sample data for presentations, printables, and reports
so that every test file can share the same canonical structures.
"""

import copy
import json

# ---------------------------------------------------------------------------
# Presentation slides (element-based, 960×540 canvas)
# ---------------------------------------------------------------------------

_PRESENTATION_TOPICS = [
    ("Introduction", "Company overview and mission statement", "text"),
    ("Q3 Revenue", "Revenue breakdown by region and product line", "chart"),
    ("Market Analysis", "Competitive landscape and market share trends", "text"),
    ("Product Roadmap", "Upcoming features and release timeline", "image_placeholder"),
    ("Customer Success", "Case studies and testimonials from key clients", "card"),
    ("Financial Summary", "P&L summary, EBITDA and cash flow highlights", "chart"),
    ("Team & Hiring", "Current headcount and open positions by department", "text"),
    ("Risks & Mitigations", "Top risk register items and mitigation plans", "text"),
    ("Next Steps", "Action items and owners for Q4", "text"),
    ("Thank You", "Contact information and Q&A", "text"),
]


def _make_presentation_slide(index: int, topic: str, description: str, primary_type: str):
    """Build a single realistic presentation slide dict."""
    elements = [
        {
            "id": f"title_{index}",
            "type": "text",
            "text": topic,
            "x": 40, "y": 20, "width": 880, "height": 60,
            "fontSize": 32, "fill": "#1a1a2e", "fontWeight": "bold",
        },
        {
            "id": f"body_{index}",
            "type": "text",
            "text": description,
            "x": 40, "y": 100, "width": 880, "height": 380,
            "fontSize": 18, "fill": "#333333",
        },
    ]
    if primary_type == "chart":
        elements.append({
            "id": f"chart_{index}",
            "type": "chart",
            "chartType": "bar",
            "x": 480, "y": 100, "width": 440, "height": 350,
        })
    elif primary_type == "image_placeholder":
        elements.append({
            "id": f"img_{index}",
            "type": "image_placeholder",
            "imageDescription": f"Illustration of {topic.lower()}",
            "imageType": "photo",
            "x": 480, "y": 100, "width": 440, "height": 350,
        })
    elif primary_type == "card":
        elements.append({
            "id": f"card_{index}",
            "type": "card",
            "title": "Key Point",
            "description": description[:60],
            "x": 480, "y": 100, "width": 440, "height": 200,
        })

    return {
        "id": f"slide_{index}",
        "title": topic,
        "outline": description,
        "sectionTopic": topic,
        "backgroundColor": "#ffffff",
        "elements": elements,
    }


def sample_presentation_slides(n: int = 5):
    """Return *n* presentation slide dicts (cycles through topics if n > 10)."""
    slides = []
    for i in range(n):
        topic, desc, ptype = _PRESENTATION_TOPICS[i % len(_PRESENTATION_TOPICS)]
        slides.append(_make_presentation_slide(i, topic, desc, ptype))
    return slides


# ---------------------------------------------------------------------------
# Printable pages (element-based, 794×1123 A4 canvas)
# ---------------------------------------------------------------------------

_PRINTABLE_TOPICS = [
    ("Cover Page", "Annual Report 2025 — Citra Technologies"),
    ("Executive Summary", "Key achievements and financial highlights for the year"),
    ("Revenue Analysis", "Detailed revenue breakdown by region and segment"),
    ("Operational Review", "Manufacturing output, supply chain improvements, and logistics"),
    ("Sustainability", "Our ESG initiatives and carbon reduction commitments"),
]


def sample_printable_pages(n: int = 5):
    pages = []
    for i in range(n):
        topic, desc = _PRINTABLE_TOPICS[i % len(_PRINTABLE_TOPICS)]
        pages.append({
            "id": f"page_{i}",
            "title": topic,
            "outline": desc,
            "backgroundColor": "#ffffff",
            "elements": [
                {"id": f"pt_{i}", "type": "text", "text": topic,
                 "x": 40, "y": 40, "width": 714, "height": 60,
                 "fontSize": 28, "fill": "#1a1a2e", "fontWeight": "bold"},
                {"id": f"pb_{i}", "type": "text", "text": desc,
                 "x": 40, "y": 120, "width": 714, "height": 900,
                 "fontSize": 14, "fill": "#333333"},
            ],
        })
    return pages


# ---------------------------------------------------------------------------
# Report pages (HTML content)
# ---------------------------------------------------------------------------

_REPORT_TOPICS = [
    ("Introduction", "<p>This report covers Q3 2025 performance across all business units.</p>"),
    ("Revenue", "<p>Total revenue reached <strong>$42M</strong>, up 15% YoY.</p><ul><li>APAC: $18M</li><li>EMEA: $14M</li><li>Americas: $10M</li></ul>"),
    ("Expenses", "<p>Operating expenses were <strong>$28M</strong>. R&amp;D spend increased by 20%.</p>"),
    ("Outlook", "<p>We expect Q4 revenue of <strong>$48M</strong> driven by new product launches.</p>"),
    ("Appendix", "<p>Supplementary tables &amp; charts are available in the <em>data room</em>.</p>"),
]


def sample_report_pages(n: int = 5):
    pages = []
    for i in range(n):
        title, html = _REPORT_TOPICS[i % len(_REPORT_TOPICS)]
        pages.append({
            "id": f"rpt_{i}",
            "title": title,
            "content": html,
            "order": i + 1,
            "outline": title,
        })
    return pages


# ---------------------------------------------------------------------------
# Summary builders (mimic Citra-UI slideTextExtractor.js output)
# ---------------------------------------------------------------------------

def build_slides_summary(slides):
    """Mimic buildSlidesSummary() from slideTextExtractor.js."""
    summaries = []
    for i, s in enumerate(slides):
        element_types = list({e.get("type", "unknown") for e in s.get("elements", [])})
        texts = []
        if s.get("title"):
            texts.append(s["title"])
        for el in s.get("elements", []):
            for k in ("text", "content", "label", "caption"):
                if el.get(k):
                    texts.append(str(el[k]))
        text_summary = " ".join(texts)[:300]
        summaries.append({
            "slide_index": i,
            "slide_id": s.get("id", f"slide_{i}"),
            "title": s.get("title", "Untitled"),
            "outline": text_summary[:150],
            "old_outline": s.get("outline", "") or s.get("sectionTopic", ""),
            "text_summary": text_summary,
            "element_types": element_types,
        })
    return summaries


def build_pages_summary(pages):
    """Mimic buildPagesSummary() from slideTextExtractor.js (report pages)."""
    import re as _re
    summaries = []
    for i, p in enumerate(pages):
        plain = _re.sub(r"<[^>]*>", " ", p.get("content", ""))
        plain = plain.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        plain = plain.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
        plain = _re.sub(r"\s+", " ", plain).strip()[:300]
        summaries.append({
            "page_index": i,
            "page_id": p.get("id", f"page_{i}"),
            "title": p.get("title", "Untitled"),
            "section_order": p.get("order", i + 1),
            "text_summary": plain,
            "old_outline": p.get("outline", ""),
        })
    return summaries


# ---------------------------------------------------------------------------
# Mock LLM responses
# ---------------------------------------------------------------------------

def mock_planner_response(relevant_indices, instructions_map=None):
    """Build a realistic planner JSON response string.

    Args:
        relevant_indices: list of ints – slide indices
        instructions_map: optional dict {idx: custom_instruction}
    """
    plans = []
    for idx in relevant_indices:
        custom = (instructions_map or {}).get(idx)
        instr = custom or f"Unique instruction for slide {idx} — update content specific to this slide's topic."
        plans.append({"slide_index": idx, "specific_instruction": instr, "skip": False})
    return json.dumps({"global_constraints": "", "plan": plans})


def mock_planner_response_with_constraints(relevant_indices, constraint_text):
    """Planner response that includes global constraints."""
    plans = []
    for idx in relevant_indices:
        plans.append({
            "slide_index": idx,
            "specific_instruction": f"Update slide {idx} with new data. {constraint_text}",
            "skip": False,
        })
    return json.dumps({"global_constraints": constraint_text, "plan": plans})


def mock_planner_response_with_skips(relevant_indices, skip_indices):
    """Planner response where some slides are marked skip=True."""
    plans = []
    for idx in relevant_indices:
        plans.append({
            "slide_index": idx,
            "specific_instruction": f"Update slide {idx}.",
            "skip": idx in skip_indices,
        })
    return json.dumps({"global_constraints": "", "plan": plans})


def mock_intent_response(intent: str, topic: str = ""):
    """Mock LLM intent classification response."""
    return json.dumps({"intent": intent, "new_slide_topic": topic})


def mock_relevance_response(indices):
    """Mock llm relevance determination response."""
    return json.dumps({"relevant_slides": [{"slide_index": i} for i in indices]})


def mock_enhance_result(slide, canvas_type="presentation"):
    """Build a mock response from enhance_page_legacy."""
    key = "enhanced_slide" if canvas_type == "presentation" else "enhanced_PAGE"
    enhanced = copy.deepcopy(slide)
    enhanced["_enhanced"] = True
    return {"success": True, key: enhanced}


def sample_style():
    return {
        "textPrimary": "#1a1a2e",
        "accentColor": "#e94560",
        "slideBackground": "#ffffff",
        "PAGEBackground": "#ffffff",
        "fontFamily": "Inter",
    }
