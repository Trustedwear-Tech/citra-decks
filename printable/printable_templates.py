# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
Printable Templates - Predefined layouts with fixed slot positions for A4 documents

Optimized for A4 portrait format (794x1123 pixels at 96 DPI)

Each template defines named slots with exact x, y, width, height positions.
AI fills content into slots, positions are FIXED for pixel-perfect rendering.

This mirrors the frontend printableTemplates.js for consistency.
"""

from typing import Dict, Any, List, Optional
import logging

# A4 at 96 DPI dimensions
PAGE_WIDTH = 794
PAGE_HEIGHT = 1123
# Backward compatibility
CANVAS_WIDTH = PAGE_WIDTH
CANVAS_HEIGHT = PAGE_HEIGHT

# ==================== Template Definitions ====================

PAGE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    # -------------------- Title Pages --------------------
    "title_hero": {
        "id": "title_hero",
        "deprecated": True,
        "name": "Title Hero",
        "description": "Report cover with title, image, and executive overview",
        "category": "title",
        "tags": ["intro", "opening", "cover", "first page", "welcome"],
        "best_for": "Opening pages, report covers, document introductions",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 60, "y": 60, "width": 440, "height": 80,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 60, "y": 150, "width": 420, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
            "accent_image": {"x": 520, "y": 50, "width": 220, "height": 200, "type": "image_placeholder", "rx": 14, "zIndex": 20, "shadow": {"color": "rgba(0,0,0,0.12)", "blur": 12, "offsetX": 0, "offsetY": 4}},
            "tagline": {
                "x": 60, "y": 220, "width": 420, "height": 40,
                "type": "text", "textType": "body",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7, "zIndex": 55,
            },
            "overview_title": {
                "x": 60, "y": 300, "width": 674, "height": 35,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "overview_col1": {
                "x": 60, "y": 350, "width": 327, "height": 400,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5, "zIndex": 60,
            },
            "overview_col2": {
                "x": 417, "y": 350, "width": 327, "height": 400,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5, "zIndex": 60,
            },
            "description": {
                "x": 60, "y": 780, "width": 674, "height": 180,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5, "zIndex": 55,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 60, "y": 280, "width": 674, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "accent_image", "overview_title", "overview_col1", "overview_col2"],
        "optional_slots": ["subtitle", "tagline", "description"],
    },

    "title_image": {
        "id": "title_image",
        "deprecated": True,
        "name": "Title with Image",
        "description": "Centered title with hero image below",
        "category": "title",
        "tags": ["intro", "cover", "hero", "visual", "photo"],
        "best_for": "Visual introductions, topic covers with imagery",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 60, "y": 60, "width": 674, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 100, "y": 140, "width": 594, "height": 55,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "center",
                "zIndex": 60,
            },
            "image": {
                "x": 147, "y": 220, "width": 500, "height": 400,
                "type": "image_placeholder",
                "zIndex": 20,
            },
            "highlights_title": {
                "x": 60, "y": 660, "width": 674, "height": 35,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "highlight_1": {
                "x": 60, "y": 710, "width": 327, "height": 150,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "highlight_2": {
                "x": 417, "y": 710, "width": 327, "height": 150,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "description": {
                "x": 60, "y": 890, "width": 674, "height": 160,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["title", "image", "highlights_title", "highlight_1", "highlight_2", "description"],
        "optional_slots": ["subtitle"],
    },

    # -------------------- Content PAGES --------------------
    "bullets": {
        "id": "bullets",
        "deprecated": True,
        "name": "Bullet Points",
        "description": "Title with bullet list - classic content PAGE",
        "category": "content",
        "tags": ["bullets", "list", "points", "content", "text"],
        "best_for": "General content, key points, feature lists",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 694, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 50, "y": 108, "width": 500, "height": 30,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7,
                "zIndex": 55,
            },
            "bullets": {
                "x": 60, "y": 155, "width": 480, "height": 830,
                "type": "text", "textType": "body",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
            "key_takeaway": {
                "x": 70, "y": 1010, "width": 654, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "bold", "textAlign": "left",
                "opacity": 0.8,
                "zIndex": 55,
            },
            "accent_image": {"x": 560, "y": 155, "width": 200, "height": 830, "type": "image_placeholder", "rx": 12, "zIndex": 20, "shadow": {"color": "rgba(0,0,0,0.12)", "blur": 12, "offsetX": 0, "offsetY": 4}},
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 105, "width": 694, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "bullets", "accent_image"],
        "optional_slots": ["subtitle", "key_takeaway"],
    },

    "two_columns": {
        "id": "two_columns",
        "deprecated": True,
        "name": "Two Columns",
        "description": "Side-by-side comparison or dual content areas",
        "category": "content",
        "tags": ["comparison", "two column", "side by side", "pros cons", "dual"],
        "best_for": "Comparing two topics, pros/cons, dual content areas",
        "has_image": False, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 694, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "left_icon": {
                "x": 70, "y": 150, "width": 48, "height": 48,
                "type": "icon", "size": 48,
                "zIndex": 35,
            },
            "left_title": {
                "x": 130, "y": 155, "width": 227, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "bold", "textAlign": "left",
                "lineHeight": 1.2,
                "zIndex": 60,
            },
            "left_content": {
                "x": 70, "y": 230, "width": 287, "height": 780,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            "right_icon": {
                "x": 437, "y": 150, "width": 48, "height": 48,
                "type": "icon", "size": 48,
                "zIndex": 35,
            },
            "right_title": {
                "x": 497, "y": 155, "width": 227, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "bold", "textAlign": "left",
                "lineHeight": 1.2,
                "zIndex": 60,
            },
            "right_content": {
                "x": 437, "y": 230, "width": 287, "height": 780,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 105, "width": 694, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "left_title", "left_content", "right_title", "right_content"],
        "optional_slots": ["left_icon", "right_icon"],
    },

    "three_cards": {
        "id": "three_cards",
        "deprecated": True,
        "name": "Three Cards",
        "description": "Three feature cards with icons - great for key points",
        "category": "content",
        "tags": ["cards", "features", "three", "grid", "highlights"],
        "best_for": "Feature highlights, key benefits, service offerings",
        "has_image": False, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 694, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 80, "y": 108, "width": 634, "height": 35,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "center",
                "opacity": 0.7,
                "zIndex": 55,
            },
            "card1_icon": {
                "x": 127, "y": 180, "width": 48, "height": 48,
                "type": "icon", "size": 48,
                "zIndex": 35,
            },
            "card1_title": {
                "x": 60, "y": 245, "width": 198, "height": 45,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "bold", "textAlign": "center",
                "lineHeight": 1.2,
                "zIndex": 60,
            },
            "card1_desc": {
                "x": 60, "y": 300, "width": 198, "height": 400,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "center",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            "card2_icon": {
                "x": 365, "y": 180, "width": 48, "height": 48,
                "type": "icon", "size": 48,
                "zIndex": 35,
            },
            "card2_title": {
                "x": 298, "y": 245, "width": 198, "height": 45,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "bold", "textAlign": "center",
                "lineHeight": 1.2,
                "zIndex": 60,
            },
            "card2_desc": {
                "x": 298, "y": 300, "width": 198, "height": 400,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "center",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            "card3_icon": {
                "x": 603, "y": 180, "width": 48, "height": 48,
                "type": "icon", "size": 48,
                "zIndex": 35,
            },
            "card3_title": {
                "x": 536, "y": 245, "width": 198, "height": 45,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "bold", "textAlign": "center",
                "lineHeight": 1.2,
                "zIndex": 60,
            },
            "card3_desc": {
                "x": 536, "y": 300, "width": 198, "height": 400,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "center",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            "conclusion": {
                "x": 50, "y": 760, "width": 694, "height": 250,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 148, "width": 694, "height": 3, "useAccentColor": True, "opacity": 0.3, "zIndex": 6},
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 745, "width": 694, "height": 3, "useAccentColor": True, "opacity": 0.3, "zIndex": 10},
        ],
        "required_slots": ["title", "card1_title", "card1_desc", "card2_title", "card2_desc", "card3_title", "card3_desc"],
        "optional_slots": ["subtitle", "card1_icon", "card2_icon", "card3_icon", "conclusion"],
    },

    "image_left": {
        "id": "image_left",
        "deprecated": True,
        "name": "Image Left",
        "description": "Large image on left with text content on right",
        "category": "media",
        "tags": ["image", "photo", "visual", "split", "media", "picture"],
        "best_for": "Visual content with explanatory text, product showcases",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 694, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 50, "y": 82, "width": 500, "height": 30,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7,
                "zIndex": 55,
            },
            "visual": {
                "x": 50, "y": 120, "width": 327, "height": 400,
                "type": "visual",
                "zIndex": 20,
                "rx": 12,
                "shadow": {"color": "rgba(0,0,0,0.1)", "blur": 14, "offsetX": 0, "offsetY": 4},
            },
            "content_title": {
                "x": 397, "y": 130, "width": 347, "height": 80,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "lineHeight": 1.3,
                "zIndex": 60,
            },
            "content": {
                "x": 397, "y": 220, "width": 347, "height": 295,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "analysis_title": {
                "x": 50, "y": 555, "width": 694, "height": 35,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "analysis_col1": {
                "x": 50, "y": 600, "width": 327, "height": 430,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "analysis_col2": {
                "x": 417, "y": 600, "width": 327, "height": 430,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 387, "y": 130, "width": 4, "height": 380, "useAccentColor": True, "opacity": 0.25, "rx": 2, "zIndex": 6},
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 540, "width": 694, "height": 3, "useAccentColor": True, "opacity": 0.3, "zIndex": 10},
        ],
        "required_slots": ["title", "content"],
        "optional_slots": ["subtitle", "visual", "content_title", "analysis_title", "analysis_col1", "analysis_col2"],
    },

    "image_right": {
        "id": "image_right",
        "deprecated": True,
        "name": "Image Right",
        "description": "Text content on left with large image on right",
        "category": "media",
        "tags": ["image", "photo", "visual", "split", "media", "picture"],
        "best_for": "Explanatory text with visual support, tutorials",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 694, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 50, "y": 82, "width": 500, "height": 30,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7,
                "zIndex": 55,
            },
            "content_title": {
                "x": 50, "y": 130, "width": 327, "height": 80,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "lineHeight": 1.3,
                "zIndex": 60,
            },
            "content": {
                "x": 50, "y": 220, "width": 327, "height": 295,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "visual": {
                "x": 397, "y": 120, "width": 347, "height": 400,
                "type": "visual",
                "zIndex": 20,
                "rx": 12,
                "shadow": {"color": "rgba(0,0,0,0.1)", "blur": 14, "offsetX": 0, "offsetY": 4},
            },
            "analysis_title": {
                "x": 50, "y": 555, "width": 694, "height": 35,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "analysis_col1": {
                "x": 50, "y": 600, "width": 327, "height": 430,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "analysis_col2": {
                "x": 417, "y": 600, "width": 327, "height": 430,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 387, "y": 130, "width": 4, "height": 380, "useAccentColor": True, "opacity": 0.25, "rx": 2, "zIndex": 6},
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 540, "width": 694, "height": 3, "useAccentColor": True, "opacity": 0.3, "zIndex": 10},
        ],
        "required_slots": ["title", "content"],
        "optional_slots": ["subtitle", "visual", "content_title", "analysis_title", "analysis_col1", "analysis_col2"],
    },

    # ================== SVG DIAGRAM TEMPLATES (full-page vector diagrams) ==================
    # `svg_diagram` slots produce inline SVG markup; UI renders via fabric.loadSVGFromString.
    # A4 portrait page = 794 x 1123 (96 DPI).

    "process_steps": {
        "id": "process_steps",
        "deprecated": True,
        "name": "Process Flow Diagram",
        "description": "Process flow page: short intro paragraph, side-by-side diagram (left SVG, right foreground image), and a key-takeaways paragraph below",
        "category": "diagram",
        "tags": ["process", "flow", "workflow", "steps", "phases", "lifecycle", "pipeline", "diagram", "how to", "methodology", "process diagram", "protein synthesis"],
        "best_for": "Step-by-step processes, lifecycles, scientific/biological/engineering flows, multi-stage pipelines",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 694, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 30, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "intro": {
                "x": 50, "y": 110, "width": 694, "height": 75,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "diagram": {
                "x": 30, "y": 195, "width": 714, "height": 315,
                "type": "svg_diagram",
                "diagramKind": "process",
                "zIndex": 50,
            },
            "image": {
                "x": 30, "y": 520, "width": 714, "height": 315,
                "type": "image_placeholder",
                "zIndex": 20,
            },
            "takeaways": {
                "x": 50, "y": 855, "width": 694, "height": 240,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["title", "intro", "diagram", "image"],
        "optional_slots": ["takeaways"],
    },

    "org_hierarchy": {
        "id": "org_hierarchy",
        "deprecated": True,
        "name": "Org Hierarchy Diagram",
        "description": "Hierarchy/tree page: optional intro, top SVG diagram + bottom foreground image, and a written branch breakdown below",
        "category": "diagram",
        "tags": ["hierarchy", "org chart", "organization", "team", "reporting", "structure", "tree", "taxonomy", "departments", "diagram"],
        "best_for": "Org charts, team structures, reporting lines, taxonomies, decision trees",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 694, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "intro": {
                "x": 50, "y": 108, "width": 694, "height": 65,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "diagram": {
                "x": 30, "y": 180, "width": 714, "height": 315,
                "type": "svg_diagram",
                "diagramKind": "hierarchy",
                "zIndex": 50,
            },
            "image": {
                "x": 30, "y": 505, "width": 714, "height": 315,
                "type": "image_placeholder",
                "zIndex": 20,
            },
            "caption": {
                "x": 50, "y": 830, "width": 694, "height": 260,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["title", "diagram", "image", "caption"],
        "optional_slots": ["intro"],
    },

    "infographic_diagram": {
        "id": "infographic_diagram",
        "deprecated": True,
        "name": "Infographic Diagram",
        "description": "Infographic page: short intro, side-by-side diagram (left SVG cycle/venn/funnel/anatomy, right foreground image), and an explanatory caption below",
        "category": "diagram",
        "tags": ["infographic", "diagram", "visual breakdown", "concept", "anatomy", "cycle", "venn", "funnel", "system"],
        "best_for": "Concept diagrams, anatomies, cycles, venn diagrams, funnels, system overviews",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 694, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 28, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "intro": {
                "x": 50, "y": 98, "width": 694, "height": 65,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "diagram": {
                "x": 30, "y": 170, "width": 714, "height": 305,
                "type": "svg_diagram",
                "diagramKind": "infographic",
                "zIndex": 50,
            },
            "image": {
                "x": 30, "y": 485, "width": 714, "height": 305,
                "type": "image_placeholder",
                "zIndex": 20,
            },
            "caption": {
                "x": 50, "y": 800, "width": 694, "height": 290,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["title", "intro", "diagram", "image", "caption"],
        "optional_slots": [],
    },

    "quote": {
        "id": "quote",
        "deprecated": True,
        "name": "Quote",
        "description": "Highlighted quote with attribution",
        "category": "content",
        "tags": ["quote", "testimonial", "citation", "saying", "inspiration"],
        "best_for": "Testimonials, inspirational quotes, key takeaways",
        "has_image": True, "has_chart": False,
        "suggest_background_image": True,
        "slots": {
            "title": {
                "x": 100, "y": 200, "width": 450, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 30, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "quote_text": {
                "x": 100, "y": 300, "width": 450, "height": 230,
                "type": "text", "textType": "body",
                "fontSize": 32, "fontWeight": "normal", "textAlign": "center",
                "fontStyle": "italic",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "attribution": {
                "x": 100, "y": 560, "width": 450, "height": 45,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "context_text": {
                "x": 130, "y": 630, "width": 400, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "center",
                "opacity": 0.6,
                "zIndex": 55,
            },
            "context": {
                "x": 130, "y": 710, "width": 400, "height": 60,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "center",
                "opacity": 0.6,
                "zIndex": 55,
            },
            "reflection": {
                "x": 100, "y": 810, "width": 450, "height": 230,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "accent_image": {"x": 570, "y": 300, "width": 190, "height": 280, "type": "image_placeholder", "rx": 10, "zIndex": 20, "shadow": {"color": "rgba(0,0,0,0.10)", "blur": 10, "offsetX": 0, "offsetY": 3}},
        },
        "decorations": [
            {"type": "text", "content": '\u201c', "x": 60, "y": 210, "width": 100, "height": 100, "fontSize": 140, "fontWeight": "bold", "textAlign": "left", "useAccentColor": True, "opacity": 0.3, "zIndex": 5},
            {"type": "text", "content": '\u201d', "x": 510, "y": 440, "width": 100, "height": 100, "fontSize": 120, "fontWeight": "bold", "textAlign": "right", "useAccentColor": True, "opacity": 0.3, "zIndex": 5},
            {"type": "shape", "shapeType": "rectangle", "x": 297, "y": 615, "width": 200, "height": 3, "useAccentColor": True, "opacity": 0.4, "zIndex": 6},
        ],
        "required_slots": ["quote_text"],
        "optional_slots": ["title", "attribution", "context_text", "context", "reflection", "accent_image"],
    },

    # -------------------- Advanced Layouts --------------------
    "modern_geometric": {
        "id": "modern_geometric",
        "deprecated": True,
        "name": "Modern Geometric",
        "description": "Dynamic layout with abstract shapes and offset content",
        "category": "advanced",
        "tags": ["modern", "creative", "abstract", "dynamic", "geometric"],
        "best_for": "Creative content, standout pages, artistic layouts",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 60, "y": 50, "width": 350, "height": 70,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 60, "y": 125, "width": 350, "height": 35,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 55,
            },
            "content": {
                "x": 60, "y": 170, "width": 350, "height": 440,
                "type": "text", "textType": "body",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
            "visual": {
                "x": 420, "y": 60, "width": 324, "height": 420,
                "type": "visual",
                "zIndex": 20,
            },
            "detail": {
                "x": 60, "y": 630, "width": 350, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.6,
                "zIndex": 55,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 0, "y": 0, "width": 20, "height": 1123, "useAccentColor": True, "zIndex": 10},
            {"type": "shape", "shapeType": "triangle", "x": 644, "y": -50, "width": 150, "height": 150, "useAccentColor": True, "opacity": 0.2, "zIndex": 5},
            {"type": "shape", "shapeType": "circle", "x": 350, "y": 900, "width": 100, "height": 100, "useAccentColor": True, "opacity": 0.1, "zIndex": 5},
        ],
        "required_slots": ["title", "content"],
        "optional_slots": ["subtitle", "visual", "detail"],
    },

    "data_dashboard": {
        "id": "data_dashboard",
        "deprecated": True,
        "name": "Data Dashboard",
        "description": "Four-quadrant layout for metrics and charts",
        "category": "data",
        "tags": ["data", "dashboard", "metrics", "analytics", "stats", "chart"],
        "best_for": "Data presentations, KPI summaries, analytics overviews",
        "has_image": False, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 694, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "chart_1": {
                "x": 50, "y": 130, "width": 327, "height": 320,
                "type": "chart",
                "zIndex": 50,
            },
            "chart_2": {
                "x": 417, "y": 130, "width": 327, "height": 320,
                "type": "chart",
                "zIndex": 50,
            },
            "stat_1": {
                "x": 50, "y": 490, "width": 327, "height": 240,
                "type": "text", "textType": "body",
                "fontSize": 18, "textAlign": "center",
                "zIndex": 60,
            },
            "stat_2": {
                "x": 417, "y": 490, "width": 327, "height": 240,
                "type": "text", "textType": "body",
                "fontSize": 18, "textAlign": "center",
                "zIndex": 60,
            },
            "analysis": {
                "x": 50, "y": 770, "width": 694, "height": 280,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.6,
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 100, "width": 694, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title"],
        "optional_slots": ["chart_1", "chart_2", "stat_1", "stat_2", "analysis"],
    },

    # ==================== RESUME TEMPLATES ====================
    
    "resume_header_photo": {
        "id": "resume_header_photo",
        "deprecated": True,
        "name": "Resume - Header with Photo",
        "description": "Professional header with photo, name, and contact info",
        "category": "resume",
        "slots": {
            "photo": {
                "x": 60, "y": 60, "width": 150, "height": 150,
                "type": "image_placeholder",
                "zIndex": 20,
            },
            "name": {
                "x": 240, "y": 70, "width": 494, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "title_role": {
                "x": 240, "y": 130, "width": 494, "height": 35,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
            "contact": {
                "x": 240, "y": 175, "width": 494, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
            "summary": {
                "x": 60, "y": 250, "width": 674, "height": 100,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "experience_section": {
                "x": 60, "y": 380, "width": 674, "height": 400,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            "skills_section": {
                "x": 60, "y": 810, "width": 674, "height": 250,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["name", "title_role", "contact", "experience_section"],
        "optional_slots": ["photo", "summary", "skills_section"],
    },

    "resume_two_column": {
        "id": "resume_two_column",
        "deprecated": True,
        "name": "Resume - Two Column",
        "description": "Sidebar with skills, main area for experience",
        "category": "resume",
        "slots": {
            "name": {
                "x": 60, "y": 50, "width": 674, "height": 45,
                "type": "text", "textType": "title",
                "fontSize": 28, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "title_role": {
                "x": 60, "y": 100, "width": 674, "height": 30,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "center",
                "zIndex": 60,
            },
            "contact": {
                "x": 60, "y": 135, "width": 674, "height": 25,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "normal", "textAlign": "center",
                "zIndex": 60,
            },
            "sidebar_title": {
                "x": 60, "y": 190, "width": 200, "height": 25,
                "type": "text", "textType": "subtitle",
                "fontSize": 14, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "sidebar_content": {
                "x": 60, "y": 220, "width": 200, "height": 850,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            "main_title": {
                "x": 290, "y": 190, "width": 444, "height": 25,
                "type": "text", "textType": "subtitle",
                "fontSize": 14, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "main_content": {
                "x": 290, "y": 220, "width": 444, "height": 850,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["name", "title_role", "contact", "sidebar_title", "sidebar_content", "main_title", "main_content"],
        "optional_slots": [],
    },

    # ==================== REPORT TEMPLATES ====================
    
    "report_title_page": {
        "id": "report_title_page",
        "deprecated": True,
        "name": "Report - Title Page",
        "description": "Professional report cover with logo and title",
        "category": "report",
        "slots": {
            "logo": {
                "x": 297, "y": 150, "width": 200, "height": 100,
                "type": "image_placeholder",
                "zIndex": 20,
            },
            "title": {
                "x": 60, "y": 380, "width": 674, "height": 80,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 100, "y": 480, "width": 594, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "normal", "textAlign": "center",
                "zIndex": 60,
            },
            "date": {
                "x": 60, "y": 950, "width": 674, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "center",
                "zIndex": 60,
            },
            "author": {
                "x": 60, "y": 990, "width": 674, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "center",
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["title"],
        "optional_slots": ["logo", "subtitle", "date", "author"],
    },

    "report_chart_focus": {
        "id": "report_chart_focus",
        "deprecated": True,
        "name": "Report - Chart Focus",
        "description": "Large chart with title and annotations",
        "category": "report",
        "slots": {
            "title": {
                "x": 60, "y": 50, "width": 674, "height": 45,
                "type": "text", "textType": "title",
                "fontSize": 24, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "chart": {
                "x": 60, "y": 120, "width": 674, "height": 500,
                "type": "chart",
                "zIndex": 50,
            },
            "caption": {
                "x": 60, "y": 640, "width": 674, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "normal", "fontStyle": "italic", "textAlign": "center",
                "zIndex": 60,
            },
            "analysis": {
                "x": 60, "y": 700, "width": 674, "height": 380,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["title", "chart"],
        "optional_slots": ["caption", "analysis"],
    },

    "report_multi_column": {
        "id": "report_multi_column",
        "deprecated": True,
        "name": "Report - Multi Column",
        "description": "Two or three column text layout for reports",
        "category": "report",
        "slots": {
            "title": {
                "x": 60, "y": 50, "width": 674, "height": 45,
                "type": "text", "textType": "title",
                "fontSize": 24, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "column_1": {
                "x": 60, "y": 120, "width": 220, "height": 950,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "normal", "textAlign": "justify",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            "column_2": {
                "x": 297, "y": 120, "width": 220, "height": 950,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "normal", "textAlign": "justify",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            "column_3": {
                "x": 534, "y": 120, "width": 200, "height": 950,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "normal", "textAlign": "justify",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["title", "column_1", "column_2"],
        "optional_slots": ["column_3"],
    },

    "report_executive_summary": {
        "id": "report_executive_summary",
        "deprecated": True,
        "name": "Report - Executive Summary",
        "description": "Key highlights with bullet points and metrics",
        "category": "report",
        "slots": {
            "title": {
                "x": 60, "y": 50, "width": 674, "height": 45,
                "type": "text", "textType": "title",
                "fontSize": 24, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "highlights_title": {
                "x": 60, "y": 120, "width": 300, "height": 30,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "highlights": {
                "x": 60, "y": 160, "width": 300, "height": 400,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "metrics_title": {
                "x": 400, "y": 120, "width": 334, "height": 30,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "metric_1": {
                "x": 400, "y": 160, "width": 150, "height": 100,
                "type": "text", "textType": "body",
                "fontSize": 28, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "metric_2": {
                "x": 560, "y": 160, "width": 150, "height": 100,
                "type": "text", "textType": "body",
                "fontSize": 28, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "conclusion": {
                "x": 60, "y": 600, "width": 674, "height": 480,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "accent_image": {"x": 560, "y": 290, "width": 170, "height": 160, "type": "image_placeholder", "rx": 10, "zIndex": 20, "shadow": {"color": "rgba(0,0,0,0.10)", "blur": 10, "offsetX": 0, "offsetY": 3}},
        },
        "decorations": [],
        "required_slots": ["title", "highlights_title", "highlights"],
        "optional_slots": ["metrics_title", "metric_1", "metric_2", "conclusion", "accent_image"],
    },

    # ================== NEW TEMPLATES ==================

    "full_bleed_image": {
        "id": "full_bleed_image",
        "deprecated": True,
        "name": "Full Bleed Image",
        "description": "Hero image top half with rich content analysis below",
        "category": "media",
        "tags": ["visual", "photo", "full image", "background", "cinematic", "impactful"],
        "best_for": "Visual impact pages with detailed analysis, chapter openers with content",
        "has_image": True, "has_chart": False,
        "suggest_background_image": False,
        "slots": {
            "image": {
                "x": 0, "y": 0, "width": 794, "height": 420,
                "type": "image_placeholder",
                "zIndex": 5,
            },
            "title": {
                "x": 50, "y": 340, "width": 694, "height": 70,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "fill": "#ffffff",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 60, "y": 450, "width": 674, "height": 40,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
            "content_col1": {
                "x": 60, "y": 510, "width": 327, "height": 440,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "content_col2": {
                "x": 417, "y": 510, "width": 327, "height": 440,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "key_takeaway": {
                "x": 60, "y": 980, "width": 674, "height": 80,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "bold", "textAlign": "left",
                "opacity": 0.8, "lineHeight": 1.4,
                "zIndex": 55,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 0, "y": 300, "width": 794, "height": 130, "fill": "rgba(0,0,0,0.45)", "zIndex": 10},
            {"type": "shape", "shapeType": "rectangle", "x": 60, "y": 435, "width": 674, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "image", "content_col1", "content_col2"],
        "optional_slots": ["subtitle", "key_takeaway"],
    },

    "four_cards": {
        "id": "four_cards",
        "deprecated": True,
        "name": "Four Cards",
        "description": "Four feature cards in 2x2 grid for A4 portrait",
        "category": "content",
        "tags": ["cards", "four", "features", "grid", "overview"],
        "best_for": "Feature overviews, service listings, benefit highlights",
        "has_image": False, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 694, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "card1_icon": {"x": 167, "y": 145, "width": 44, "height": 44, "type": "icon", "size": 44, "zIndex": 35},
            "card1_title": {"x": 70, "y": 210, "width": 280, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 18, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "card1_desc": {"x": 70, "y": 260, "width": 280, "height": 200, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
            "card2_icon": {"x": 527, "y": 145, "width": 44, "height": 44, "type": "icon", "size": 44, "zIndex": 35},
            "card2_title": {"x": 430, "y": 210, "width": 280, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 18, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "card2_desc": {"x": 430, "y": 260, "width": 280, "height": 200, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
            "card3_icon": {"x": 167, "y": 530, "width": 44, "height": 44, "type": "icon", "size": 44, "zIndex": 35},
            "card3_title": {"x": 70, "y": 595, "width": 280, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 18, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "card3_desc": {"x": 70, "y": 645, "width": 280, "height": 200, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
            "card4_icon": {"x": 527, "y": 530, "width": 44, "height": 44, "type": "icon", "size": 44, "zIndex": 35},
            "card4_title": {"x": 430, "y": 595, "width": 280, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 18, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "card4_desc": {"x": 430, "y": 645, "width": 280, "height": 200, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
            "summary": {
                "x": 50, "y": 900, "width": 694, "height": 150,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 885, "width": 694, "height": 3, "useAccentColor": True, "opacity": 0.3, "zIndex": 10},
        ],
        "required_slots": ["title", "card1_title", "card1_desc", "card2_title", "card2_desc", "card3_title", "card3_desc", "card4_title", "card4_desc"],
        "optional_slots": ["card1_icon", "card2_icon", "card3_icon", "card4_icon", "summary"],
    },

    "stats_highlight": {
        "id": "stats_highlight",
        "deprecated": True,
        "name": "Stats Highlight",
        "description": "Three prominent statistics with labels and descriptions",
        "category": "data",
        "tags": ["stats", "numbers", "metrics", "highlights", "KPI"],
        "best_for": "Key metrics, achievements, impact numbers",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 50, "width": 530, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 34, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "stat1_value": {"x": 50, "y": 200, "width": 218, "height": 100, "type": "text", "textType": "title", "fontSize": 56, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "stat1_label": {"x": 50, "y": 310, "width": 218, "height": 55, "type": "text", "textType": "body", "fontSize": 18, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "stat1_desc": {"x": 55, "y": 380, "width": 208, "height": 300, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.5, "opacity": 0.7, "zIndex": 55},
            "stat2_value": {"x": 288, "y": 200, "width": 218, "height": 100, "type": "text", "textType": "title", "fontSize": 56, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "stat2_label": {"x": 288, "y": 310, "width": 218, "height": 55, "type": "text", "textType": "body", "fontSize": 18, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "stat2_desc": {"x": 293, "y": 380, "width": 208, "height": 300, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.5, "opacity": 0.7, "zIndex": 55},
            "stat3_value": {"x": 526, "y": 200, "width": 218, "height": 100, "type": "text", "textType": "title", "fontSize": 56, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "stat3_label": {"x": 526, "y": 310, "width": 218, "height": 55, "type": "text", "textType": "body", "fontSize": 18, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "stat3_desc": {"x": 531, "y": 380, "width": 208, "height": 300, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.5, "opacity": 0.7, "zIndex": 55},
            "summary": {
                "x": 50, "y": 740, "width": 480, "height": 280,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.6,
                "zIndex": 60,
            },
            "accent_image": {"x": 560, "y": 740, "width": 200, "height": 270, "type": "image_placeholder", "rx": 10, "zIndex": 20, "shadow": {"color": "rgba(0,0,0,0.10)", "blur": 10, "offsetX": 0, "offsetY": 3}},
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 130, "width": 694, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "stat1_value", "stat1_label", "stat2_value", "stat2_label", "stat3_value", "stat3_label"],
        "optional_slots": ["stat1_desc", "stat2_desc", "stat3_desc", "summary", "accent_image"],
    },

    "big_number": {
        "id": "big_number",
        "deprecated": True,
        "name": "Big Number",
        "description": "Single prominent statistic with context",
        "category": "data",
        "tags": ["stat", "number", "metric", "single", "focus", "hero metric"],
        "best_for": "Hero metrics, single KPI focus, dramatic stat reveals",
        "has_image": True, "has_chart": False,
        "suggest_background_image": True,
        "slots": {
            "metric": {"x": 60, "y": 300, "width": 674, "height": 180, "type": "text", "textType": "title", "fontSize": 110, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "label": {"x": 60, "y": 500, "width": 440, "height": 80, "type": "text", "textType": "subtitle", "fontSize": 34, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "context": {"x": 60, "y": 610, "width": 440, "height": 200, "type": "text", "textType": "body", "fontSize": 18, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.6, "opacity": 0.8, "zIndex": 55},
            "footnote": {"x": 60, "y": 830, "width": 400, "height": 80, "type": "text", "textType": "body", "fontSize": 12, "fontWeight": "normal", "textAlign": "left", "opacity": 0.5, "zIndex": 50},
            "trend_note": {
                "x": 60, "y": 930, "width": 400, "height": 100,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5, "opacity": 0.7,
                "zIndex": 55,
            },
            "accent_image": {"x": 540, "y": 490, "width": 220, "height": 300, "type": "image_placeholder", "rx": 12, "zIndex": 20, "shadow": {"color": "rgba(0,0,0,0.12)", "blur": 12, "offsetX": 0, "offsetY": 4}},
        },
        "decorations": [
            {"type": "shape", "shapeType": "circle", "x": 50, "y": 880, "width": 120, "height": 120, "useAccentColor": True, "opacity": 0.15, "zIndex": 5},
            {"type": "shape", "shapeType": "circle", "x": 624, "y": 100, "width": 140, "height": 140, "useAccentColor": True, "opacity": 0.12, "zIndex": 5},
            {"type": "shape", "shapeType": "rectangle", "x": 297, "y": 800, "width": 200, "height": 3, "useAccentColor": True, "opacity": 0.3, "zIndex": 6},
        ],
        "required_slots": ["metric", "label"],
        "optional_slots": ["context", "footnote", "trend_note", "accent_image"],
    },

    "chart_focus": {
        "id": "chart_focus",
        "deprecated": True,
        "name": "Chart Focus",
        "description": "Large chart taking most of the page",
        "category": "data",
        "tags": ["chart", "graph", "data", "visualization"],
        "best_for": "Data visualization, trend analysis, chart-focused pages",
        "has_image": False, "has_chart": True,
        "slots": {
            "title": {"x": 50, "y": 40, "width": 694, "height": 50, "type": "text", "textType": "title", "fontSize": 30, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "description": {"x": 50, "y": 100, "width": 400, "height": 35, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "opacity": 0.7, "zIndex": 55},
            "chart": {"x": 50, "y": 150, "width": 694, "height": 550, "type": "chart", "zIndex": 50},
            "analysis": {
                "x": 50, "y": 730, "width": 694, "height": 320,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.6,
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 720, "width": 694, "height": 3, "useAccentColor": True, "opacity": 0.3, "zIndex": 10},
        ],
        "required_slots": ["title", "chart"],
        "optional_slots": ["description", "analysis"],
    },

    "chart_left": {
        "id": "chart_left",
        "deprecated": True,
        "name": "Chart Left",
        "description": "Chart on left with text content on right",
        "category": "data",
        "tags": ["chart", "graph", "data", "split", "visualization", "analysis"],
        "best_for": "Data visualization with explanatory text, trend analysis with commentary",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 694, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 30, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "visual": {
                "x": 50, "y": 120, "width": 347, "height": 450,
                "type": "visual",
                "zIndex": 50,
            },
            "content_title": {
                "x": 417, "y": 130, "width": 327, "height": 45,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "content": {
                "x": 417, "y": 190, "width": 327, "height": 370,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "key_findings_title": {
                "x": 50, "y": 620, "width": 694, "height": 35,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "key_findings": {
                "x": 50, "y": 670, "width": 327, "height": 360,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "analysis": {
                "x": 417, "y": 670, "width": 327, "height": 360,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 407, "y": 130, "width": 4, "height": 440, "useAccentColor": True, "opacity": 0.25, "rx": 2, "zIndex": 6},
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 610, "width": 694, "height": 3, "useAccentColor": True, "opacity": 0.3, "zIndex": 10},
        ],
        "required_slots": ["title", "visual", "content"],
        "optional_slots": ["content_title", "key_findings_title", "key_findings", "analysis"],
    },

    "chart_right": {
        "id": "chart_right",
        "deprecated": True,
        "name": "Chart Right",
        "description": "Text content on left with chart on right",
        "category": "data",
        "tags": ["chart", "graph", "data", "split", "visualization", "analysis"],
        "best_for": "Commentary with supporting data visualization, analysis presentations",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 694, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 30, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "content_title": {
                "x": 50, "y": 130, "width": 327, "height": 45,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "content": {
                "x": 50, "y": 190, "width": 327, "height": 370,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "visual": {
                "x": 397, "y": 120, "width": 347, "height": 450,
                "type": "visual",
                "zIndex": 50,
            },
            "key_findings_title": {
                "x": 50, "y": 620, "width": 694, "height": 35,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "key_findings": {
                "x": 50, "y": 670, "width": 327, "height": 360,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "analysis": {
                "x": 417, "y": 670, "width": 327, "height": 360,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 387, "y": 130, "width": 4, "height": 440, "useAccentColor": True, "opacity": 0.25, "rx": 2, "zIndex": 6},
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 610, "width": 694, "height": 3, "useAccentColor": True, "opacity": 0.3, "zIndex": 10},
        ],
        "required_slots": ["title", "visual", "content"],
        "optional_slots": ["content_title", "key_findings_title", "key_findings", "analysis"],
    },

    "chart_and_image": {
        "id": "chart_and_image",
        "deprecated": True,
        "name": "Chart and Image",
        "description": "Chart on one side with image on the other for data + visual context",
        "category": "data",
        "tags": ["chart", "image", "data", "photo", "visualization", "combined", "mixed"],
        "best_for": "Data with visual context, product metrics with photos, research with charts and images",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 694, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 30, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "chart": {
                "x": 50, "y": 120, "width": 327, "height": 420,
                "type": "chart",
                "zIndex": 50,
            },
            "image": {
                "x": 417, "y": 120, "width": 327, "height": 420,
                "type": "image_placeholder",
                "zIndex": 20,
                "rx": 12,
                "shadow": {"color": "rgba(0,0,0,0.1)", "blur": 14, "offsetX": 0, "offsetY": 4},
            },
            "caption": {
                "x": 50, "y": 560, "width": 694, "height": 40,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "center",
                "opacity": 0.8, "zIndex": 55,
            },
            "insights_title": {
                "x": 50, "y": 620, "width": 694, "height": 35,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "insights": {
                "x": 50, "y": 670, "width": 450, "height": 350,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "stat_1": {
                "x": 520, "y": 670, "width": 224, "height": 160,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "center",
                "zIndex": 60,
            },
            "stat_2": {
                "x": 520, "y": 850, "width": 224, "height": 160,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "center",
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 100, "width": 694, "height": 3, "useAccentColor": True, "zIndex": 10},
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 610, "width": 694, "height": 3, "useAccentColor": True, "opacity": 0.3, "zIndex": 10},
        ],
        "required_slots": ["title", "chart", "image"],
        "optional_slots": ["caption", "insights_title", "insights", "stat_1", "stat_2"],
    },

    "comparison": {
        "id": "comparison",
        "deprecated": True,
        "name": "Comparison",
        "description": "Side-by-side comparison with headers and content",
        "category": "content",
        "tags": ["compare", "versus", "vs", "pros cons", "before after"],
        "best_for": "Product comparisons, before/after, option evaluation",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {"x": 50, "y": 40, "width": 694, "height": 55, "type": "text", "textType": "title", "fontSize": 32, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "left_header": {"x": 60, "y": 130, "width": 320, "height": 50, "type": "text", "textType": "subtitle", "fontSize": 22, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "left_content": {"x": 70, "y": 195, "width": 300, "height": 800, "type": "text", "textType": "body", "fontSize": 15, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.5, "zIndex": 60},
            "right_header": {"x": 414, "y": 130, "width": 320, "height": 50, "type": "text", "textType": "subtitle", "fontSize": 22, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "right_content": {"x": 424, "y": 195, "width": 300, "height": 800, "type": "text", "textType": "body", "fontSize": 15, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.5, "zIndex": 60},
            "accent_image": {"x": 300, "y": 1010, "width": 200, "height": 90, "type": "image_placeholder", "rx": 10, "zIndex": 20, "shadow": {"color": "rgba(0,0,0,0.10)", "blur": 10, "offsetX": 0, "offsetY": 3}},
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 105, "width": 694, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "left_header", "left_content", "right_header", "right_content"],
        "optional_slots": ["accent_image"],
    },

    "timeline": {
        "id": "timeline",
        "deprecated": True,
        "name": "Timeline",
        "description": "Vertical timeline with events and descriptions for A4",
        "category": "content",
        "tags": ["timeline", "history", "milestones", "events", "chronological", "roadmap"],
        "best_for": "Project timelines, company history, milestones, roadmaps",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {"x": 50, "y": 40, "width": 530, "height": 55, "type": "text", "textType": "title", "fontSize": 32, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "event1_date": {"x": 130, "y": 140, "width": 614, "height": 30, "type": "text", "textType": "subtitle", "fontSize": 15, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "event1_title": {"x": 130, "y": 175, "width": 614, "height": 35, "type": "text", "textType": "subtitle", "fontSize": 18, "fontWeight": "bold", "textAlign": "left", "lineHeight": 1.2, "zIndex": 60},
            "event1_desc": {"x": 130, "y": 215, "width": 614, "height": 80, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.4, "zIndex": 60},
            "event2_date": {"x": 130, "y": 340, "width": 614, "height": 30, "type": "text", "textType": "subtitle", "fontSize": 15, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "event2_title": {"x": 130, "y": 375, "width": 614, "height": 35, "type": "text", "textType": "subtitle", "fontSize": 18, "fontWeight": "bold", "textAlign": "left", "lineHeight": 1.2, "zIndex": 60},
            "event2_desc": {"x": 130, "y": 415, "width": 614, "height": 80, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.4, "zIndex": 60},
            "event3_date": {"x": 130, "y": 540, "width": 614, "height": 30, "type": "text", "textType": "subtitle", "fontSize": 15, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "event3_title": {"x": 130, "y": 575, "width": 614, "height": 35, "type": "text", "textType": "subtitle", "fontSize": 18, "fontWeight": "bold", "textAlign": "left", "lineHeight": 1.2, "zIndex": 60},
            "event3_desc": {"x": 130, "y": 615, "width": 614, "height": 80, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.4, "zIndex": 60},
            "event4_date": {"x": 130, "y": 740, "width": 614, "height": 30, "type": "text", "textType": "subtitle", "fontSize": 15, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "event4_title": {"x": 130, "y": 775, "width": 614, "height": 35, "type": "text", "textType": "subtitle", "fontSize": 18, "fontWeight": "bold", "textAlign": "left", "lineHeight": 1.2, "zIndex": 60},
            "event4_desc": {"x": 130, "y": 815, "width": 614, "height": 80, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.4, "zIndex": 60},
            "conclusion": {
                "x": 50, "y": 940, "width": 694, "height": 120,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "accent_image": {"x": 610, "y": 40, "width": 150, "height": 70, "type": "image_placeholder", "rx": 10, "zIndex": 20, "shadow": {"color": "rgba(0,0,0,0.10)", "blur": 10, "offsetX": 0, "offsetY": 3}},
        },
        "decorations": [
            # Vertical timeline line
            {"type": "shape", "shapeType": "rectangle", "x": 83, "y": 130, "width": 4, "height": 770, "useAccentColor": True, "opacity": 0.4, "zIndex": 10},
            # Timeline dots
            {"type": "shape", "shapeType": "circle", "x": 71, "y": 155, "width": 28, "height": 28, "useAccentColor": True, "zIndex": 15},
            {"type": "shape", "shapeType": "circle", "x": 71, "y": 355, "width": 28, "height": 28, "useAccentColor": True, "zIndex": 15},
            {"type": "shape", "shapeType": "circle", "x": 71, "y": 555, "width": 28, "height": 28, "useAccentColor": True, "zIndex": 15},
            {"type": "shape", "shapeType": "circle", "x": 71, "y": 755, "width": 28, "height": 28, "useAccentColor": True, "zIndex": 15},
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 925, "width": 694, "height": 3, "useAccentColor": True, "opacity": 0.3, "zIndex": 10},
        ],
        "required_slots": ["title", "event1_title", "event2_title", "event3_title", "event4_title"],
        "optional_slots": ["event1_date", "event1_desc", "event2_date", "event2_desc", "event3_date", "event3_desc", "event4_date", "event4_desc", "conclusion", "accent_image"],
    },

    "section_break": {
        "id": "section_break",
        "deprecated": True,
        "name": "Section Break",
        "description": "Section opener with overview content and image",
        "category": "title",
        "tags": ["section", "divider", "break", "chapter", "transition"],
        "best_for": "Section transitions with context, chapter introductions",
        "has_image": True, "has_chart": False,
        "suggest_background_image": True,
        "slots": {
            "section_title": {"x": 60, "y": 60, "width": 440, "height": 80, "type": "text", "textType": "title", "fontSize": 36, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "subtitle": {"x": 60, "y": 150, "width": 420, "height": 50, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "normal", "textAlign": "left", "opacity": 0.7, "zIndex": 55},
            "accent_image": {"x": 520, "y": 50, "width": 220, "height": 200, "type": "image_placeholder", "rx": 14, "zIndex": 20, "shadow": {"color": "rgba(0,0,0,0.12)", "blur": 12, "offsetX": 0, "offsetY": 4}},
            "overview": {"x": 60, "y": 240, "width": 674, "height": 250, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.6, "zIndex": 60},
            "highlights_title": {"x": 60, "y": 520, "width": 674, "height": 35, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "highlights_col1": {"x": 60, "y": 570, "width": 327, "height": 380, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.5, "zIndex": 60},
            "highlights_col2": {"x": 417, "y": 570, "width": 327, "height": 380, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.5, "zIndex": 60},
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 60, "y": 220, "width": 674, "height": 3, "useAccentColor": True, "rx": 2, "zIndex": 10},
            {"type": "shape", "shapeType": "rectangle", "x": 60, "y": 505, "width": 674, "height": 3, "useAccentColor": True, "opacity": 0.5, "rx": 2, "zIndex": 10},
        ],
        "required_slots": ["section_title", "overview", "accent_image"],
        "optional_slots": ["subtitle", "highlights_title", "highlights_col1", "highlights_col2"],
    },

    "closing": {
        "id": "closing",
        "deprecated": True,
        "name": "Closing",
        "description": "Closing page with summary, key takeaways, and call-to-action",
        "category": "title",
        "tags": ["closing", "end", "thank you", "cta", "contact", "final"],
        "best_for": "Final pages, executive summary, conclusion with next steps",
        "has_image": True, "has_chart": False,
        "suggest_background_image": True,
        "slots": {
            "title": {"x": 60, "y": 50, "width": 674, "height": 70, "type": "text", "textType": "title", "fontSize": 36, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "subtitle": {"x": 60, "y": 130, "width": 420, "height": 50, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "normal", "textAlign": "left", "zIndex": 60},
            "accent_image": {"x": 520, "y": 50, "width": 220, "height": 200, "type": "image_placeholder", "rx": 14, "zIndex": 20, "shadow": {"color": "rgba(0,0,0,0.12)", "blur": 12, "offsetX": 0, "offsetY": 4}},
            "summary_title": {"x": 60, "y": 210, "width": 674, "height": 35, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "summary": {"x": 60, "y": 255, "width": 674, "height": 280, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.6, "zIndex": 60},
            "cta_text": {"x": 60, "y": 565, "width": 674, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 18, "fontWeight": "bold", "textAlign": "left", "zIndex": 60},
            "next_steps_col1": {"x": 60, "y": 620, "width": 327, "height": 350, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.5, "zIndex": 60},
            "next_steps_col2": {"x": 417, "y": 620, "width": 327, "height": 350, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "lineHeight": 1.5, "zIndex": 60},
            "footer_note": {"x": 60, "y": 1000, "width": 674, "height": 60, "type": "text", "textType": "body", "fontSize": 12, "fontWeight": "normal", "textAlign": "left", "opacity": 0.6, "lineHeight": 1.4, "zIndex": 55},
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 60, "y": 195, "width": 674, "height": 3, "useAccentColor": True, "zIndex": 10},
            {"type": "shape", "shapeType": "rectangle", "x": 60, "y": 555, "width": 674, "height": 3, "useAccentColor": True, "opacity": 0.5, "zIndex": 10},
        ],
        "required_slots": ["title", "summary_title", "summary", "accent_image"],
        "optional_slots": ["subtitle", "cta_text", "next_steps_col1", "next_steps_col2", "footer_note"],
    },

    # ==================== BLANK TEMPLATE ======================================
    
    "blank_freeflow": {
        "id": "blank_freeflow",
        "deprecated": True,
        "name": "Blank Page",
        "description": "Empty canvas for free-form design",
        "category": "blank",
        "tags": ["blank", "empty", "freeform", "custom"],
        "has_image": False, "has_chart": False,
        "slots": {},
        "decorations": [],
        "required_slots": [],
        "optional_slots": [],
    },

    # ================== CITRA EXECUTIVE A4 FAMILY ==================
    # A4 portrait (794 × 1123). Same design language as the 16:9 exec_*
    # templates: kicker → action title → subhead spine, no filler photos,
    # section-coloured cards, dark book-ends. Each template auto-injects
    # the standard footer via inject_exec_footer at composition time.

    "exec_pg_cover": {
        "id": "exec_pg_cover",
        "name": "Executive Cover (A4)",
        "description": "A4 cover page for executive reports. Dark navy background, brand chip top-left, kicker (date/audience), massive two-tone headline, supporting subhead, three pill labels naming the report's pillars. Typography-led — no content image.",
        "category": "title",
        "tags": ["executive", "cover", "board report", "annual report", "title page", "report cover"],
        "best_for": "Cover page for executive reports, annual reports, board briefs",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#0B1020",
        "slots": {
            "brand_chip": {
                "x": 40, "y": 56, "width": 170, "height": 38,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "center",
                "letterSpacing": 3, "color": "#FFFFFF",
                "zIndex": 60,
            },
            "kicker": {
                "x": 40, "y": 320, "width": 700, "height": 22,
                "type": "text", "textType": "kicker",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 4, "color": "#22D3EE",
                "zIndex": 60,
            },
            "title_a": {
                "x": 40, "y": 360, "width": 714, "height": 120,
                "type": "text", "textType": "title",
                "fontSize": 64, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.08,
                "zIndex": 60,
            },
            "title_b": {
                "x": 40, "y": 488, "width": 714, "height": 120,
                "type": "text", "textType": "title",
                "fontSize": 64, "fontWeight": "bold", "textAlign": "left",
                "color": "#22D3EE", "lineHeight": 1.08,
                "zIndex": 60,
            },
            "subhead": {
                "x": 40, "y": 630, "width": 660, "height": 80,
                "type": "text", "textType": "body",
                "fontSize": 17, "fontWeight": "normal", "textAlign": "left",
                "color": "#CBD5E1", "lineHeight": 1.55,
                "zIndex": 60,
            },
            "pill_1": {
                "x": 40, "y": 920, "width": 230, "height": 32,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "center",
                "color": "#FFFFFF", "backgroundColor": "#1E293B", "rx": 16,
                "zIndex": 60,
            },
            "pill_2": {
                "x": 282, "y": 920, "width": 230, "height": 32,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "center",
                "color": "#FFFFFF", "backgroundColor": "#1E293B", "rx": 16,
                "zIndex": 60,
            },
            "pill_3": {
                "x": 524, "y": 920, "width": 230, "height": 32,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "center",
                "color": "#FFFFFF", "backgroundColor": "#1E293B", "rx": 16,
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 40, "y": 56, "width": 170, "height": 38, "rx": 4, "stroke": "#475569", "strokeWidth": 1, "fill": "transparent", "zIndex": 5},
        ],
        "required_slots": ["title_a", "title_b"],
        "optional_slots": ["brand_chip", "kicker", "subhead", "pill_1", "pill_2", "pill_3"],
    },

    "exec_pg_argument": {
        "id": "exec_pg_argument",
        "name": "Executive Argument (A4)",
        "description": "A4 workhorse body page on light background. Kicker + action title + single-sentence subhead, then a single full-width white content card with a heading and 5-7 bullets (sentence case, ≤18 words each), and an optional accent-coloured takeaway strap at the bottom. No images.",
        "category": "content",
        "tags": ["executive", "argument", "body page", "claim", "bullets", "default body", "evidence"],
        "best_for": "Standard body page making one claim supported by bullets — the executive report's workhorse",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#F8FAFC",
        "slots": {
            "kicker": {
                "x": 40, "y": 64, "width": 700, "height": 22,
                "type": "text", "textType": "kicker",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#2563EB",
                "zIndex": 60,
            },
            "title": {
                "x": 40, "y": 96, "width": 714, "height": 120,
                "type": "text", "textType": "title",
                "fontSize": 40, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.15,
                "zIndex": 60,
            },
            "subhead": {
                "x": 40, "y": 230, "width": 714, "height": 60,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.55,
                "zIndex": 60,
            },
            "card_bg": {
                "x": 40, "y": 318, "width": 714, "height": 700,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 10,
                "shadow": {"color": "rgba(15,23,42,0.06)", "blur": 18, "offsetX": 0, "offsetY": 4},
                "zIndex": 10,
            },
            "section_heading": {
                "x": 72, "y": 350, "width": 650, "height": 32,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "section_intro": {
                "x": 72, "y": 392, "width": 650, "height": 80,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "color": "#334155", "lineHeight": 1.65,
                "zIndex": 20,
            },
            "bullets": {
                "x": 72, "y": 490, "width": 650, "height": 500,
                "type": "bullets",
                "fontSize": 14, "color": "#1F2937", "lineHeight": 1.75,
                "bulletStyle": "dot", "bulletColor": "#2563EB",
                "zIndex": 20,
            },
            "takeaway": {
                "x": 40, "y": 1040, "width": 714, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "bold", "textAlign": "center",
                "letterSpacing": 2, "color": "#2563EB",
                "zIndex": 10,
            },
        },
        "decorations": [],
        "required_slots": ["title", "bullets"],
        "optional_slots": ["kicker", "subhead", "section_heading", "section_intro", "takeaway"],
    },

    "exec_pg_stat_grid": {
        "id": "exec_pg_stat_grid",
        "name": "Executive Stat Grid (A4)",
        "description": "A4 business-impact page on light background. Kicker + action title + subhead, then a 2x2 grid of stat cards — each with a thin coloured accent bar on top, a giant number (~88pt), and a label below. Optional 'where the savings come from' explanatory block underneath the grid.",
        "category": "data",
        "tags": ["executive", "stats", "kpi", "business impact", "four stats", "stat grid", "metrics"],
        "best_for": "Business-impact / KPI pages — show 4 headline metrics in an A4 report",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#F8FAFC",
        "slots": {
            "kicker": {
                "x": 40, "y": 64, "width": 700, "height": 22,
                "type": "text", "textType": "kicker",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#2563EB",
                "zIndex": 60,
            },
            "title": {
                "x": 40, "y": 96, "width": 714, "height": 96,
                "type": "text", "textType": "title",
                "fontSize": 40, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.15,
                "zIndex": 60,
            },
            "subhead": {
                "x": 40, "y": 206, "width": 714, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.55,
                "zIndex": 60,
            },
            # Stat card 1 (blue, top-left)
            "s1_accent": {"x": 40, "y": 296, "width": 354, "height": 4, "type": "shape", "shapeType": "rectangle", "fill": "#2563EB", "rx": 2, "zIndex": 20},
            "s1_bg":     {"x": 40, "y": 300, "width": 354, "height": 192, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2}, "zIndex": 10},
            "s1_value":  {"x": 72, "y": 326, "width": 290, "height": 110, "type": "text", "textType": "title", "fontSize": 78, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "lineHeight": 1.0, "zIndex": 20},
            "s1_label":  {"x": 72, "y": 442, "width": 290, "height": 38, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.45, "zIndex": 20},
            # Stat card 2 (cyan, top-right)
            "s2_accent": {"x": 400, "y": 296, "width": 354, "height": 4, "type": "shape", "shapeType": "rectangle", "fill": "#06B6D4", "rx": 2, "zIndex": 20},
            "s2_bg":     {"x": 400, "y": 300, "width": 354, "height": 192, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2}, "zIndex": 10},
            "s2_value":  {"x": 432, "y": 326, "width": 290, "height": 110, "type": "text", "textType": "title", "fontSize": 78, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "lineHeight": 1.0, "zIndex": 20},
            "s2_label":  {"x": 432, "y": 442, "width": 290, "height": 38, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.45, "zIndex": 20},
            # Stat card 3 (purple, bottom-left)
            "s3_accent": {"x": 40, "y": 508, "width": 354, "height": 4, "type": "shape", "shapeType": "rectangle", "fill": "#8B5CF6", "rx": 2, "zIndex": 20},
            "s3_bg":     {"x": 40, "y": 512, "width": 354, "height": 192, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2}, "zIndex": 10},
            "s3_value":  {"x": 72, "y": 538, "width": 290, "height": 110, "type": "text", "textType": "title", "fontSize": 78, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "lineHeight": 1.0, "zIndex": 20},
            "s3_label":  {"x": 72, "y": 654, "width": 290, "height": 38, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.45, "zIndex": 20},
            # Stat card 4 (green, bottom-right)
            "s4_accent": {"x": 400, "y": 508, "width": 354, "height": 4, "type": "shape", "shapeType": "rectangle", "fill": "#10B981", "rx": 2, "zIndex": 20},
            "s4_bg":     {"x": 400, "y": 512, "width": 354, "height": 192, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2}, "zIndex": 10},
            "s4_value":  {"x": 432, "y": 538, "width": 290, "height": 110, "type": "text", "textType": "title", "fontSize": 78, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "lineHeight": 1.0, "zIndex": 20},
            "s4_label":  {"x": 432, "y": 654, "width": 290, "height": 38, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.45, "zIndex": 20},
            # Optional "where the savings come from" explanation
            "detail_heading": {
                "x": 40, "y": 740, "width": 714, "height": 28,
                "type": "text", "textType": "subtitle",
                "fontSize": 17, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "detail_body": {
                "x": 40, "y": 780, "width": 714, "height": 260,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#334155", "lineHeight": 1.65,
                "zIndex": 20,
            },
        },
        "decorations": [],
        "required_slots": ["title", "s1_value", "s1_label", "s2_value", "s2_label", "s3_value", "s3_label", "s4_value", "s4_label"],
        "optional_slots": ["kicker", "subhead", "detail_heading", "detail_body"],
    },

    "exec_pg_features_2x2": {
        "id": "exec_pg_features_2x2",
        "name": "Executive Features 2×2 (A4)",
        "description": "A4 capabilities page on light background. Kicker + action title + subhead, then four white feature cards in a 2x2 grid — each with a coloured icon circle (blue/cyan/purple/green), bold title, and 2-3 line description. Optional dark banner at the bottom with a tag-line claim.",
        "category": "content",
        "tags": ["executive", "features", "capabilities", "four features", "2x2", "feature grid"],
        "best_for": "Capabilities / features pages — show four distinct value props in an A4 report",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#F8FAFC",
        "slots": {
            "kicker":  {"x": 40, "y": 64, "width": 700, "height": 22, "type": "text", "textType": "kicker", "fontSize": 13, "fontWeight": "bold", "textAlign": "left", "letterSpacing": 3, "color": "#8B5CF6", "zIndex": 60},
            "title":   {"x": 40, "y": 96, "width": 714, "height": 96, "type": "text", "textType": "title", "fontSize": 40, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "lineHeight": 1.15, "zIndex": 60},
            "subhead": {"x": 40, "y": 206, "width": 714, "height": 50, "type": "text", "textType": "body", "fontSize": 15, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.55, "zIndex": 60},
            # Card 1 (blue, top-left)
            "f1_bg":      {"x": 40, "y": 296, "width": 354, "height": 220, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 10, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 14, "offsetX": 0, "offsetY": 3}, "zIndex": 10},
            "f1_icon_bg": {"x": 72, "y": 326, "width": 64, "height": 64, "type": "shape", "shapeType": "circle", "fill": "#2563EB", "zIndex": 15},
            "f1_icon":    {"x": 88, "y": 342, "width": 32, "height": 32, "type": "icon", "fill": "#FFFFFF", "zIndex": 20},
            "f1_title":   {"x": 160, "y": 332, "width": 224, "height": 32, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "f1_body":    {"x": 72, "y": 410, "width": 312, "height": 96, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.6, "zIndex": 20},
            # Card 2 (cyan, top-right)
            "f2_bg":      {"x": 400, "y": 296, "width": 354, "height": 220, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 10, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 14, "offsetX": 0, "offsetY": 3}, "zIndex": 10},
            "f2_icon_bg": {"x": 432, "y": 326, "width": 64, "height": 64, "type": "shape", "shapeType": "circle", "fill": "#06B6D4", "zIndex": 15},
            "f2_icon":    {"x": 448, "y": 342, "width": 32, "height": 32, "type": "icon", "fill": "#FFFFFF", "zIndex": 20},
            "f2_title":   {"x": 520, "y": 332, "width": 224, "height": 32, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "f2_body":    {"x": 432, "y": 410, "width": 312, "height": 96, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.6, "zIndex": 20},
            # Card 3 (purple, bottom-left)
            "f3_bg":      {"x": 40, "y": 530, "width": 354, "height": 220, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 10, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 14, "offsetX": 0, "offsetY": 3}, "zIndex": 10},
            "f3_icon_bg": {"x": 72, "y": 560, "width": 64, "height": 64, "type": "shape", "shapeType": "circle", "fill": "#8B5CF6", "zIndex": 15},
            "f3_icon":    {"x": 88, "y": 576, "width": 32, "height": 32, "type": "icon", "fill": "#FFFFFF", "zIndex": 20},
            "f3_title":   {"x": 160, "y": 566, "width": 224, "height": 32, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "f3_body":    {"x": 72, "y": 644, "width": 312, "height": 96, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.6, "zIndex": 20},
            # Card 4 (green, bottom-right)
            "f4_bg":      {"x": 400, "y": 530, "width": 354, "height": 220, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 10, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 14, "offsetX": 0, "offsetY": 3}, "zIndex": 10},
            "f4_icon_bg": {"x": 432, "y": 560, "width": 64, "height": 64, "type": "shape", "shapeType": "circle", "fill": "#10B981", "zIndex": 15},
            "f4_icon":    {"x": 448, "y": 576, "width": 32, "height": 32, "type": "icon", "fill": "#FFFFFF", "zIndex": 20},
            "f4_title":   {"x": 520, "y": 566, "width": 224, "height": 32, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "f4_body":    {"x": 432, "y": 644, "width": 312, "height": 96, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.6, "zIndex": 20},
            # Bottom dark banner
            "banner_bg":   {"x": 40, "y": 780, "width": 714, "height": 50, "type": "shape", "shapeType": "rectangle", "fill": "#0B1020", "rx": 6, "zIndex": 10},
            "banner_text": {"x": 40, "y": 780, "width": 714, "height": 50, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "bold", "textAlign": "center", "letterSpacing": 2, "color": "#22D3EE", "zIndex": 20},
        },
        "decorations": [],
        "required_slots": ["title", "f1_title", "f1_body", "f2_title", "f2_body", "f3_title", "f3_body", "f4_title", "f4_body"],
        "optional_slots": ["kicker", "subhead", "f1_icon", "f2_icon", "f3_icon", "f4_icon", "banner_text"],
    },

    "exec_pg_industries_2x2": {
        "id": "exec_pg_industries_2x2",
        "name": "Executive Industries 2×2 (A4)",
        "description": "A4 industries / use-cases page on light background. Kicker + action title + subhead, then 2×2 grid of industry cards. Each card has a vertical coloured side-rule (blue/green/orange/purple), a coloured icon circle + industry name, and 4-6 checkmarked use-case bullets in two columns.",
        "category": "content",
        "tags": ["executive", "industries", "use cases", "verticals", "applications", "where it works"],
        "best_for": "Industries / verticals page — show 4 verticals each with use-case checklists in an A4 report",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#F8FAFC",
        "slots": {
            "kicker":  {"x": 40, "y": 64, "width": 700, "height": 22, "type": "text", "textType": "kicker", "fontSize": 13, "fontWeight": "bold", "textAlign": "left", "letterSpacing": 3, "color": "#2563EB", "zIndex": 60},
            "title":   {"x": 40, "y": 96, "width": 714, "height": 96, "type": "text", "textType": "title", "fontSize": 40, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "lineHeight": 1.15, "zIndex": 60},
            "subhead": {"x": 40, "y": 206, "width": 714, "height": 50, "type": "text", "textType": "body", "fontSize": 15, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.55, "zIndex": 60},
            # Card 1 (blue, top-left)
            "i1_rule":    {"x": 40, "y": 296, "width": 4, "height": 230, "type": "shape", "shapeType": "rectangle", "fill": "#2563EB", "zIndex": 20},
            "i1_bg":      {"x": 44, "y": 296, "width": 350, "height": 230, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2}, "zIndex": 10},
            "i1_icon_bg": {"x": 70, "y": 320, "width": 44, "height": 44, "type": "shape", "shapeType": "circle", "fill": "#2563EB", "zIndex": 15},
            "i1_icon":    {"x": 82, "y": 332, "width": 20, "height": 20, "type": "icon", "fill": "#FFFFFF", "zIndex": 20},
            "i1_name":    {"x": 130, "y": 324, "width": 250, "height": 36, "type": "text", "textType": "subtitle", "fontSize": 21, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "i1_uses":    {"x": 70, "y": 380, "width": 314, "height": 130, "type": "bullets", "fontSize": 13, "color": "#334155", "lineHeight": 1.75, "bulletStyle": "check", "bulletColor": "#10B981", "columns": 2, "zIndex": 20},
            # Card 2 (green, top-right)
            "i2_rule":    {"x": 400, "y": 296, "width": 4, "height": 230, "type": "shape", "shapeType": "rectangle", "fill": "#10B981", "zIndex": 20},
            "i2_bg":      {"x": 404, "y": 296, "width": 350, "height": 230, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2}, "zIndex": 10},
            "i2_icon_bg": {"x": 430, "y": 320, "width": 44, "height": 44, "type": "shape", "shapeType": "circle", "fill": "#10B981", "zIndex": 15},
            "i2_icon":    {"x": 442, "y": 332, "width": 20, "height": 20, "type": "icon", "fill": "#FFFFFF", "zIndex": 20},
            "i2_name":    {"x": 490, "y": 324, "width": 250, "height": 36, "type": "text", "textType": "subtitle", "fontSize": 21, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "i2_uses":    {"x": 430, "y": 380, "width": 314, "height": 130, "type": "bullets", "fontSize": 13, "color": "#334155", "lineHeight": 1.75, "bulletStyle": "check", "bulletColor": "#10B981", "columns": 2, "zIndex": 20},
            # Card 3 (orange, bottom-left)
            "i3_rule":    {"x": 40, "y": 542, "width": 4, "height": 230, "type": "shape", "shapeType": "rectangle", "fill": "#F59E0B", "zIndex": 20},
            "i3_bg":      {"x": 44, "y": 542, "width": 350, "height": 230, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2}, "zIndex": 10},
            "i3_icon_bg": {"x": 70, "y": 566, "width": 44, "height": 44, "type": "shape", "shapeType": "circle", "fill": "#F59E0B", "zIndex": 15},
            "i3_icon":    {"x": 82, "y": 578, "width": 20, "height": 20, "type": "icon", "fill": "#FFFFFF", "zIndex": 20},
            "i3_name":    {"x": 130, "y": 570, "width": 250, "height": 36, "type": "text", "textType": "subtitle", "fontSize": 21, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "i3_uses":    {"x": 70, "y": 626, "width": 314, "height": 130, "type": "bullets", "fontSize": 13, "color": "#334155", "lineHeight": 1.75, "bulletStyle": "check", "bulletColor": "#10B981", "columns": 2, "zIndex": 20},
            # Card 4 (purple, bottom-right)
            "i4_rule":    {"x": 400, "y": 542, "width": 4, "height": 230, "type": "shape", "shapeType": "rectangle", "fill": "#8B5CF6", "zIndex": 20},
            "i4_bg":      {"x": 404, "y": 542, "width": 350, "height": 230, "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8, "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2}, "zIndex": 10},
            "i4_icon_bg": {"x": 430, "y": 566, "width": 44, "height": 44, "type": "shape", "shapeType": "circle", "fill": "#8B5CF6", "zIndex": 15},
            "i4_icon":    {"x": 442, "y": 578, "width": 20, "height": 20, "type": "icon", "fill": "#FFFFFF", "zIndex": 20},
            "i4_name":    {"x": 490, "y": 570, "width": 250, "height": 36, "type": "text", "textType": "subtitle", "fontSize": 21, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "i4_uses":    {"x": 430, "y": 626, "width": 314, "height": 130, "type": "bullets", "fontSize": 13, "color": "#334155", "lineHeight": 1.75, "bulletStyle": "check", "bulletColor": "#10B981", "columns": 2, "zIndex": 20},
        },
        "decorations": [],
        "required_slots": ["title", "i1_name", "i1_uses", "i2_name", "i2_uses", "i3_name", "i3_uses", "i4_name", "i4_uses"],
        "optional_slots": ["kicker", "subhead", "i1_icon", "i2_icon", "i3_icon", "i4_icon"],
    },

    "exec_pg_sovereignty_dark": {
        "id": "exec_pg_sovereignty_dark",
        "name": "Executive Architecture / Sovereignty (A4 Dark)",
        "description": "A4 architecture / sovereignty / governance page on dark navy. Kicker + action title + subhead, then four equal-width dark cards stacked in a 2x2 (cyan title + white body — 'Zero Copy / Zero ETL / Zero Egress / Zero Lock-in' style), plus an optional 'Governance & deployment' panel at the bottom with 4 light-bg checkmarked items.",
        "category": "content",
        "tags": ["executive", "architecture", "sovereignty", "governance", "security", "trust", "compliance"],
        "best_for": "Architecture / sovereignty / security / governance pages — communicate trust posture in an A4 report",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#0B1020",
        "slots": {
            "kicker":  {"x": 40, "y": 64, "width": 700, "height": 22, "type": "text", "textType": "kicker", "fontSize": 13, "fontWeight": "bold", "textAlign": "left", "letterSpacing": 3, "color": "#22D3EE", "zIndex": 60},
            "title":   {"x": 40, "y": 96, "width": 714, "height": 96, "type": "text", "textType": "title", "fontSize": 40, "fontWeight": "bold", "textAlign": "left", "color": "#FFFFFF", "lineHeight": 1.15, "zIndex": 60},
            "subhead": {"x": 40, "y": 206, "width": 714, "height": 50, "type": "text", "textType": "body", "fontSize": 15, "fontWeight": "normal", "textAlign": "left", "color": "#CBD5E1", "lineHeight": 1.55, "zIndex": 60},
            # 2x2 dark cards
            "z1_bg":    {"x": 40, "y": 296, "width": 354, "height": 200, "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8, "stroke": "#1E293B", "strokeWidth": 1, "zIndex": 10},
            "z1_title": {"x": 72, "y": 322, "width": 290, "height": 36, "type": "text", "textType": "subtitle", "fontSize": 26, "fontWeight": "bold", "textAlign": "left", "color": "#22D3EE", "zIndex": 20},
            "z1_body":  {"x": 72, "y": 374, "width": 290, "height": 108, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "color": "#FFFFFF", "lineHeight": 1.6, "zIndex": 20},

            "z2_bg":    {"x": 400, "y": 296, "width": 354, "height": 200, "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8, "stroke": "#1E293B", "strokeWidth": 1, "zIndex": 10},
            "z2_title": {"x": 432, "y": 322, "width": 290, "height": 36, "type": "text", "textType": "subtitle", "fontSize": 26, "fontWeight": "bold", "textAlign": "left", "color": "#22D3EE", "zIndex": 20},
            "z2_body":  {"x": 432, "y": 374, "width": 290, "height": 108, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "color": "#FFFFFF", "lineHeight": 1.6, "zIndex": 20},

            "z3_bg":    {"x": 40, "y": 512, "width": 354, "height": 200, "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8, "stroke": "#1E293B", "strokeWidth": 1, "zIndex": 10},
            "z3_title": {"x": 72, "y": 538, "width": 290, "height": 36, "type": "text", "textType": "subtitle", "fontSize": 26, "fontWeight": "bold", "textAlign": "left", "color": "#22D3EE", "zIndex": 20},
            "z3_body":  {"x": 72, "y": 590, "width": 290, "height": 108, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "color": "#FFFFFF", "lineHeight": 1.6, "zIndex": 20},

            "z4_bg":    {"x": 400, "y": 512, "width": 354, "height": 200, "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8, "stroke": "#1E293B", "strokeWidth": 1, "zIndex": 10},
            "z4_title": {"x": 432, "y": 538, "width": 290, "height": 36, "type": "text", "textType": "subtitle", "fontSize": 26, "fontWeight": "bold", "textAlign": "left", "color": "#22D3EE", "zIndex": 20},
            "z4_body":  {"x": 432, "y": 590, "width": 290, "height": 108, "type": "text", "textType": "body", "fontSize": 14, "fontWeight": "normal", "textAlign": "left", "color": "#FFFFFF", "lineHeight": 1.6, "zIndex": 20},

            # Bottom light governance panel
            "gov_bg":      {"x": 40, "y": 736, "width": 714, "height": 282, "type": "shape", "shapeType": "rectangle", "fill": "#F8FAFC", "rx": 8, "zIndex": 10},
            "gov_heading": {"x": 72, "y": 758, "width": 650, "height": 26, "type": "text", "textType": "kicker", "fontSize": 13, "fontWeight": "bold", "textAlign": "left", "letterSpacing": 3, "color": "#2563EB", "zIndex": 20},
            "g1_check": {"x": 72, "y": 808, "width": 18, "height": 18, "type": "icon", "iconName": "checkmark-circle", "fill": "#10B981", "zIndex": 20},
            "g1_title": {"x": 96, "y": 806, "width": 260, "height": 22, "type": "text", "textType": "subtitle", "fontSize": 13, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "g1_body":  {"x": 96, "y": 830, "width": 260, "height": 44, "type": "text", "textType": "body", "fontSize": 11, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.5, "zIndex": 20},
            "g2_check": {"x": 392, "y": 808, "width": 18, "height": 18, "type": "icon", "iconName": "checkmark-circle", "fill": "#10B981", "zIndex": 20},
            "g2_title": {"x": 416, "y": 806, "width": 320, "height": 22, "type": "text", "textType": "subtitle", "fontSize": 13, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "g2_body":  {"x": 416, "y": 830, "width": 320, "height": 44, "type": "text", "textType": "body", "fontSize": 11, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.5, "zIndex": 20},
            "g3_check": {"x": 72, "y": 906, "width": 18, "height": 18, "type": "icon", "iconName": "checkmark-circle", "fill": "#10B981", "zIndex": 20},
            "g3_title": {"x": 96, "y": 904, "width": 260, "height": 22, "type": "text", "textType": "subtitle", "fontSize": 13, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "g3_body":  {"x": 96, "y": 928, "width": 260, "height": 44, "type": "text", "textType": "body", "fontSize": 11, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.5, "zIndex": 20},
            "g4_check": {"x": 392, "y": 906, "width": 18, "height": 18, "type": "icon", "iconName": "checkmark-circle", "fill": "#10B981", "zIndex": 20},
            "g4_title": {"x": 416, "y": 904, "width": 320, "height": 22, "type": "text", "textType": "subtitle", "fontSize": 13, "fontWeight": "bold", "textAlign": "left", "color": "#0F172A", "zIndex": 20},
            "g4_body":  {"x": 416, "y": 928, "width": 320, "height": 44, "type": "text", "textType": "body", "fontSize": 11, "fontWeight": "normal", "textAlign": "left", "color": "#475569", "lineHeight": 1.5, "zIndex": 20},
        },
        "decorations": [],
        "required_slots": ["title", "z1_title", "z1_body", "z2_title", "z2_body", "z3_title", "z3_body", "z4_title", "z4_body"],
        "optional_slots": ["kicker", "subhead", "gov_heading", "g1_title", "g1_body", "g2_title", "g2_body", "g3_title", "g3_body", "g4_title", "g4_body"],
    },

    "exec_pg_closing_dark": {
        "id": "exec_pg_closing_dark",
        "name": "Executive Closing — Strategic Reasons (A4 Dark)",
        "description": "A4 closing / 'Why Citra' page on dark navy. Kicker + headline at top, then 2x2 grid of dark feature cards each with a giant cyan numeral (01/02/03/04), bold reason title, and 2-3 line description. Cyan CTA strap spans the full width near the bottom.",
        "category": "closing",
        "tags": ["executive", "closing", "why buy", "strategic reasons", "cta", "ask", "next steps", "summary"],
        "best_for": "Closing page for executive reports — recommendations, asks, the four strategic reasons",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#0B1020",
        "slots": {
            "kicker": {"x": 40, "y": 80, "width": 700, "height": 24, "type": "text", "textType": "kicker", "fontSize": 13, "fontWeight": "bold", "textAlign": "left", "letterSpacing": 4, "color": "#22D3EE", "zIndex": 60},
            "title":  {"x": 40, "y": 120, "width": 714, "height": 96, "type": "text", "textType": "title", "fontSize": 52, "fontWeight": "bold", "textAlign": "left", "color": "#FFFFFF", "zIndex": 60},
            # Card 01
            "c1_bg":     {"x": 40, "y": 260, "width": 354, "height": 200, "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8, "stroke": "#1E293B", "strokeWidth": 1, "zIndex": 10},
            "c1_number": {"x": 70, "y": 282, "width": 110, "height": 88, "type": "text", "textType": "title", "fontSize": 56, "fontWeight": "bold", "textAlign": "left", "color": "#22D3EE", "zIndex": 20},
            # Title slot sized for 2 lines (h=56) so wrapped titles don't bleed
            # down into the body / number area. fontSize 20 (was 22) for one
            # extra char-per-line. Body shifts down to compensate.
            "c1_title":  {"x": 190, "y": 288, "width": 200, "height": 56, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "bold", "textAlign": "left", "color": "#FFFFFF", "lineHeight": 1.2, "zIndex": 20},
            "c1_body":   {"x": 190, "y": 350, "width": 200, "height": 100, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "left", "color": "#CBD5E1", "lineHeight": 1.55, "zIndex": 20},
            # Card 02
            "c2_bg":     {"x": 400, "y": 260, "width": 354, "height": 200, "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8, "stroke": "#1E293B", "strokeWidth": 1, "zIndex": 10},
            "c2_number": {"x": 430, "y": 282, "width": 110, "height": 88, "type": "text", "textType": "title", "fontSize": 56, "fontWeight": "bold", "textAlign": "left", "color": "#22D3EE", "zIndex": 20},
            "c2_title":  {"x": 550, "y": 288, "width": 200, "height": 56, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "bold", "textAlign": "left", "color": "#FFFFFF", "lineHeight": 1.2, "zIndex": 20},
            "c2_body":   {"x": 550, "y": 350, "width": 200, "height": 100, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "left", "color": "#CBD5E1", "lineHeight": 1.55, "zIndex": 20},
            # Card 03
            "c3_bg":     {"x": 40, "y": 478, "width": 354, "height": 200, "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8, "stroke": "#1E293B", "strokeWidth": 1, "zIndex": 10},
            "c3_number": {"x": 70, "y": 500, "width": 110, "height": 88, "type": "text", "textType": "title", "fontSize": 56, "fontWeight": "bold", "textAlign": "left", "color": "#22D3EE", "zIndex": 20},
            "c3_title":  {"x": 190, "y": 506, "width": 200, "height": 56, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "bold", "textAlign": "left", "color": "#FFFFFF", "lineHeight": 1.2, "zIndex": 20},
            "c3_body":   {"x": 190, "y": 568, "width": 200, "height": 100, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "left", "color": "#CBD5E1", "lineHeight": 1.55, "zIndex": 20},
            # Card 04
            "c4_bg":     {"x": 400, "y": 478, "width": 354, "height": 200, "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8, "stroke": "#1E293B", "strokeWidth": 1, "zIndex": 10},
            "c4_number": {"x": 430, "y": 500, "width": 110, "height": 88, "type": "text", "textType": "title", "fontSize": 56, "fontWeight": "bold", "textAlign": "left", "color": "#22D3EE", "zIndex": 20},
            "c4_title":  {"x": 550, "y": 506, "width": 200, "height": 56, "type": "text", "textType": "subtitle", "fontSize": 20, "fontWeight": "bold", "textAlign": "left", "color": "#FFFFFF", "lineHeight": 1.2, "zIndex": 20},
            "c4_body":   {"x": 550, "y": 568, "width": 200, "height": 100, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "left", "color": "#CBD5E1", "lineHeight": 1.55, "zIndex": 20},
            # CTA strap
            "cta_bg":   {"x": 40, "y": 920, "width": 714, "height": 60, "type": "shape", "shapeType": "rectangle", "fill": "#22D3EE", "rx": 8, "zIndex": 10},
            "cta_text": {"x": 40, "y": 920, "width": 714, "height": 60, "type": "text", "textType": "body", "fontSize": 16, "fontWeight": "bold", "textAlign": "center", "color": "#0B1020", "zIndex": 20},
        },
        "decorations": [],
        "required_slots": ["title", "c1_number", "c1_title", "c1_body", "c2_number", "c2_title", "c2_body"],
        "optional_slots": ["kicker", "c3_number", "c3_title", "c3_body", "c4_number", "c4_title", "c4_body", "cta_text"],
    },
}


# ==================== Template Categories ====================

TEMPLATE_CATEGORIES = [
    {"id": "resume", "name": "Resume", "icon": "person"},
    {"id": "report", "name": "Report", "icon": "document-text"},
    {"id": "title", "name": "Title Pages", "icon": "layout"},
    {"id": "content", "name": "Content", "icon": "file-text"},
    {"id": "data", "name": "Data & Charts", "icon": "bar-chart"},
    {"id": "blank", "name": "Blank", "icon": "square-outline"},
]


# ==================== Template Matching ====================

TEMPLATE_KEYWORDS = {
    # Executive consultant-report family (A4) — matched on intent words.
    # The bare exec_pg_* keys mirror what the outline emits as `layout`.
    "exec_pg_cover": [
        "exec_pg_cover", "exec_cover", "executive cover page", "report cover",
        "board report cover", "annual report cover", "pitch cover page",
    ],
    # Citra is enterprise-only. Every legacy A4 layout name a stale outline
    # might emit is migrated into the matching exec_pg_* template below.
    # Deprecated templates stay in PAGE_TEMPLATES (for rendering pre-cutover
    # documents) but are not reachable through this keyword fallback.
    "exec_pg_cover": [
        # exec aliases — already declared above
        # legacy title / cover variants → dark exec cover
        "title_hero", "title_image", "title PAGE", "intro PAGE", "opening PAGE",
        "cover PAGE", "title page", "hero", "title with image", "hero image",
        "cover with image", "title",
        "report_title_page", "report cover", "report title", "document cover",
    ],
    "exec_pg_argument": [
        # exec aliases — already declared above
        # legacy generic body layouts → workhorse exec_pg_argument
        "bullets", "bullet", "bullet points", "list", "points", "bullet list",
        "bullet_points", "title_content",
        "quote", "quotation", "testimonial", "citation",
        "section_break", "section", "divider", "chapter", "break", "transition",
        "modern_geometric", "modern", "geometric", "abstract", "creative", "dynamic",
        "report_multi_column", "multi column", "newspaper", "article layout",
        "report_executive_summary", "executive summary", "summary page", "highlights",
        "image_focus",
    ],
    "exec_pg_stat_grid": [
        # exec aliases — already declared above
        # legacy stats / big-number / dashboard / chart layouts → stat_grid
        "four_cards", "4 card", "four card", "4 box", "four box", "quadruple", "4 section",
        "stats_highlight", "3 stats", "three numbers", "key metrics", "3 metrics",
        "big_number", "big number", "single stat", "one number", "hero metric",
        "data_dashboard", "dashboard", "analytics", "data",
        "chart_focus", "chart_left", "chart_right", "chart_and_image",
        "report_chart_focus", "chart report", "data report", "chart focus",
        "chart", "graph", "bar chart", "pie chart", "visualization",
        "chart left", "chart right", "chart with text", "text with chart",
        "chart and image", "chart with image",
    ],
    "exec_pg_features_2x2": [
        # exec aliases — already declared above
        # 3-cards layouts also fit a 2x2 feature grid better than anything else
        "three_cards", "3 card", "three card", "3 box", "three box", "triple",
        "3 section", "three section",
    ],
    "exec_pg_industries_2x2": [
        # exec aliases — already declared above
        # no legacy mapping (industries was a brand-new pattern)
    ],
    "exec_pg_sovereignty_dark": [
        # exec aliases — already declared above
        # legacy two_columns / process / timeline / comparison / org_hierarchy
        "two_columns", "two column", "2 column", "side by side", "two_column",
        "comparison", "compare", "versus", "vs", "pros cons", "before after",
        "process_steps", "process", "steps", "flow", "workflow", "stages",
        "phases", "step by step", "process diagram", "lifecycle", "pipeline",
        "timeline", "milestones", "history", "roadmap", "chronological", "journey",
        "image_left", "image_right", "image left", "image right",
        "picture left", "picture right", "photo left", "photo right",
        "org_hierarchy", "hierarchy", "org chart", "organization chart",
        "reporting structure", "team structure", "taxonomy", "tree diagram",
        "decision tree",
        "infographic_diagram", "infographic", "diagram", "visual breakdown",
        "concept diagram", "anatomy", "cycle diagram", "venn", "funnel diagram",
        "system diagram",
        "full_bleed_image", "full image", "full bleed", "background image", "cinematic",
        "resume_header_photo", "resume", "cv", "curriculum vitae", "resume with photo",
        "resume_two_column", "two column resume", "sidebar resume",
        "blank_freeflow", "blank", "empty", "freeform", "custom",
    ],
    "exec_pg_closing_dark": [
        # exec aliases — already declared above
        "closing", "end", "thank you", "thanks", "conclusion", "final", "contact",
    ],
}


# ============================================================================
# Deck profiles — three operating modes for the A4 matcher.
# ============================================================================
# Mirrors the slides side: corporate_boardroom shows only exec_pg_* templates;
# corporate_with_visuals exposes chart / data / diagram legacy A4 templates;
# general_with_images opens up everything (full-bleed, photo-rich layouts).
# ============================================================================

# Two A4 profiles as of 2026-05-19:
#   - "corporate" (merged executive + visuals catalog, always emits a
#     deck-coherent background image on every page so the document reads
#     as one artefact)
#   - "general"   (free-style: full template library, AI decides bg per page)
#
# Old names kept as aliases for backward-compat with any client still
# sending the previous three-profile values.
DECK_PROFILE_CORPORATE = "corporate"
DECK_PROFILE_GENERAL = "general"
DECK_PROFILE_CORPORATE_BOARDROOM = "corporate_boardroom"          # alias → corporate
DECK_PROFILE_CORPORATE_WITH_VISUALS = "corporate_with_visuals"    # alias → corporate
DECK_PROFILE_GENERAL_WITH_IMAGES = "general_with_images"          # alias → general

_EXEC_PG_TEMPLATE_IDS = [
    "exec_pg_cover", "exec_pg_argument", "exec_pg_stat_grid",
    "exec_pg_features_2x2", "exec_pg_industries_2x2",
    "exec_pg_sovereignty_dark", "exec_pg_closing_dark",
]

# Chart / data / diagram / selective-hero-image A4 templates that round
# out the corporate catalog. Photo-rich full-bleed layouts stay in general.
#
# Pruned from corporate (and the rationale):
#   - chart_left / chart_right         → image_left/image_right with has_chart
#                                         cover the same split-with-chart shape.
#   - data_dashboard                   → exec_pg_stat_grid is the canonical
#                                         4-metric corporate page; chart_focus
#                                         + chart_and_image cover the rest.
#   - report_chart_focus               → duplicate of chart_focus on A4.
#   - report_multi_column              → two_columns + three_cards already
#                                         provide multi-column layout.
#   - report_executive_summary         → exec_pg_argument + exec_pg_stat_grid
#                                         deliver the same "key highlights"
#                                         shape in the executive family.
_CORPORATE_VISUAL_PG_EXTRAS = [
    # Chart-focused (kept: single big chart + chart-paired-with-image)
    "chart_focus", "chart_and_image",
    "stats_highlight", "big_number",
    # Diagrams + structure
    "process_steps", "org_hierarchy", "infographic_diagram", "timeline",
    # Selective hero image
    "title_image", "image_left", "image_right",
    # Neutral non-image layouts that complement exec
    "two_columns", "three_cards", "four_cards", "comparison",
    "section_break", "quote",
]

_CORPORATE_PG_TEMPLATE_IDS = list(_EXEC_PG_TEMPLATE_IDS) + list(_CORPORATE_VISUAL_PG_EXTRAS)

_CORPORATE_PG_PROFILE = {
    "label": "Corporate",
    "description": (
        "Unified executive A4 document — typography-led layouts, strategic "
        "charts, diagrams, and a deck-coherent photographic background on "
        "every page (the storyboard pass derives a single bg motif so the "
        "document reads as one artefact)."
    ),
    "template_ids": _CORPORATE_PG_TEMPLATE_IDS,
    "always_background_image": True,
}

# General-profile A4 catalog — explicit allowlist matching the presentation
# side. Dropped redundant or legacy templates so the matcher has fewer near-
# duplicates to choose between (see the corporate prune notes above for the
# same rationale). Resume / blank-freeflow are also out — they're standalone
# tools, not general-purpose document pages.
_GENERAL_PG_TEMPLATE_IDS = [
    # Title / cover
    "title_hero", "title_image", "full_bleed_image", "report_title_page",
    # Body / content
    "two_columns", "three_cards", "four_cards", "modern_geometric",
    "image_left", "image_right",
    # Charts (kept: single big chart + chart-paired-with-image)
    "chart_focus", "chart_and_image",
    # Stats
    "stats_highlight", "big_number",
    # Structural / narrative
    "process_steps", "org_hierarchy", "infographic_diagram",
    "comparison", "timeline", "section_break", "quote",
    # Closing
    "closing",
]

_GENERAL_PG_PROFILE = {
    "label": "General",
    "description": (
        "Photo-rich A4 template library — covers, image splits, narrative "
        "and chart layouts. Best for marketing, training, newsletters, "
        "casual documents. AI decides per-page whether to add a background "
        "image."
    ),
    "template_ids": _GENERAL_PG_TEMPLATE_IDS,
    "always_background_image": False,
}

DECK_PROFILES: Dict[str, Dict[str, Any]] = {
    DECK_PROFILE_CORPORATE: _CORPORATE_PG_PROFILE,
    DECK_PROFILE_GENERAL:   _GENERAL_PG_PROFILE,
    # ---- legacy aliases ----
    DECK_PROFILE_CORPORATE_BOARDROOM:    _CORPORATE_PG_PROFILE,
    DECK_PROFILE_CORPORATE_WITH_VISUALS: _CORPORATE_PG_PROFILE,
    DECK_PROFILE_GENERAL_WITH_IMAGES:    _GENERAL_PG_PROFILE,
}


def profile_always_emits_background(profile: Optional[str]) -> bool:
    """Returns True when the profile requires a background image on every
    page. Mirrors slide_templates.profile_always_emits_background."""
    p = DECK_PROFILES.get(profile or "") or DECK_PROFILES.get(DECK_PROFILE_CORPORATE, {})
    return bool(p.get("always_background_image"))


def get_profile_template_catalog(profile: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Return the subset of PAGE_TEMPLATES visible to ``profile``."""
    profile_key = profile if profile in DECK_PROFILES else DECK_PROFILE_CORPORATE_BOARDROOM
    allowed = DECK_PROFILES[profile_key].get("template_ids")
    if allowed is None:
        return dict(PAGE_TEMPLATES)
    return {tid: PAGE_TEMPLATES[tid] for tid in allowed if tid in PAGE_TEMPLATES}


def template_in_profile(template_id: str, profile: Optional[str]) -> bool:
    profile_key = profile if profile in DECK_PROFILES else DECK_PROFILE_CORPORATE_BOARDROOM
    allowed = DECK_PROFILES[profile_key].get("template_ids")
    if allowed is None:
        return template_id in PAGE_TEMPLATES
    return template_id in allowed


def match_template_from_instruction(instruction: str) -> Optional[str]:
    """
    Match user instruction to a template ID based on keywords.
    """
    instruction_lower = instruction.lower()
    
    for template_id, keywords in TEMPLATE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in instruction_lower:
                return template_id
    
    return None


# ==================== Helper Functions ====================

def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    """Get template by ID."""
    return PAGE_TEMPLATES.get(template_id)


def get_template_list() -> List[Dict[str, Any]]:
    """Get all templates as a list."""
    return list(PAGE_TEMPLATES.values())


def get_templates_by_category(category: str) -> List[Dict[str, Any]]:
    """Get templates filtered by category."""
    return [t for t in PAGE_TEMPLATES.values() if t.get("category") == category]


def compute_slot_max_chars(slot_def: Dict[str, Any]) -> Dict[str, int]:
    """
    Compute the maximum characters that fit in a text slot based on pixel dimensions.
    
    Formula:
      chars_per_line = floor(width / (fontSize * 0.55))
      max_lines = floor(height / (fontSize * lineHeight))
      max_chars = chars_per_line * max_lines
    
    Returns dict with: maxChars, maxLines, charsPerLine
    """
    width = slot_def.get("width", 400)
    height = slot_def.get("height", 100)
    font_size = slot_def.get("fontSize", 16)
    line_height = slot_def.get("lineHeight", 1.4)
    
    chars_per_line = max(1, int(width / (font_size * 0.55)))
    max_lines = max(1, int(height / (font_size * line_height)))
    max_chars = chars_per_line * max_lines
    
    return {
        "maxChars": max_chars,
        "maxLines": max_lines,
        "charsPerLine": chars_per_line,
    }


def compute_all_slot_limits(template_id: str) -> Dict[str, Dict[str, int]]:
    """
    Compute character limits for all text slots in a template.
    Returns {slot_name: {maxChars, maxLines, charsPerLine}} for text slots only.
    """
    template = PAGE_TEMPLATES.get(template_id)
    if not template:
        return {}
    
    result = {}
    for slot_name, slot_def in template.get("slots", {}).items():
        if slot_def.get("type") == "text":
            result[slot_name] = compute_slot_max_chars(slot_def)
    return result


# ==================== Icon Catalog for AI ====================

ICON_CATALOG = """ICON REFERENCE (use kebab-case Lucide icon names):
  Business: briefcase, chart-bar, trending-up, dollar-sign, building-2, landmark, calculator, receipt, wallet, piggy-bank
  Science: flask-conical, microscope, atom, dna, beaker, test-tube, leaf, earth, thermometer, stethoscope
  Technology: cpu, code, server, cloud, shield-check, wifi, monitor, database, hard-drive, smartphone
  People: users, user-check, heart, brain, hand-helping, graduation-cap, baby, person-standing, smile, eye
  Communication: mail, message-square, phone, megaphone, share-2, send, rss, bell, at-sign, radio
  General: lightbulb, target, rocket, star, check-circle, award, flag, bookmark, zap, compass
  Charts: chart-bar, chart-line, chart-pie, chart-area, chart-column, chart-spline, activity, trending-up
  Arrows: arrow-right, arrow-up, arrow-down, move, corner-down-right, external-link, refresh-cw
  Files: file-text, folder, clipboard, archive, download, upload, printer, image, camera
  Time: clock, calendar, timer, hourglass, alarm-clock, history, watch, sunset
Choose icons that DIRECTLY relate to the card/section content — not generic decorative icons."""


def get_slot_prompt_format(template_id: str) -> str:
    """
    Generate a prompt format showing which slots the AI needs to fill,
    with precise per-slot character limits computed from pixel dimensions.
    """
    template = PAGE_TEMPLATES.get(template_id)
    if not template:
        return ""
    
    slot_limits = compute_all_slot_limits(template_id)
    
    lines = [f"TEMPLATE: {template['name']} ({template['description']})"]
    lines.append("SLOTS TO FILL (you MUST provide content for EVERY slot listed below):")
    lines.append("")
    
    for slot_name, slot_def in template["slots"].items():
        slot_type = slot_def["type"]
        is_required = slot_name in template.get("required_slots", [])
        is_optional = slot_name in template.get("optional_slots", [])
        req_marker = "(REQUIRED)" if is_required else "(OPTIONAL)" if is_optional else "(MUST FILL)"
        
        if slot_type == "text":
            limits = slot_limits.get(slot_name, {})
            max_chars = limits.get("maxChars", 200)
            max_lines = limits.get("maxLines", 5)
            chars_per_line = limits.get("charsPerLine", 40)
            
            text_type = slot_def.get("textType", "body")
            font_size = slot_def.get("fontSize", 16)
            
            # ------------ Exec-template slot patterns FIRST ------------
            # These are checked before the generic text_type rules below so
            # that small card slots (stat value, card title, pillar/feature/
            # closing-card body, pills) don't accidentally inherit the
            # "8-N words" subtitle hint that guarantees overflow.
            import re as _re_inline
            if (_re_inline.match(r'(stat|s|r)\d+_value$', slot_name)
                    or _re_inline.match(r'right_(before|after)_value$', slot_name)):
                hint = f"ONLY a short number or symbol ('29%', '$1.2M', '100+'). NO words. Max {max_chars} chars in {chars_per_line}px-wide box."
            elif _re_inline.match(r'c\d+_number$', slot_name):
                hint = "ONLY a 2-character step number ('01', '02', '03', '04'). NO words, NO punctuation."
            elif (_re_inline.match(r'(stat|s|r)\d+_label$', slot_name)
                    or _re_inline.match(r'right_(before|after)_label$', slot_name)):
                word_limit = max(2, min(max_chars // 8, 5))
                hint = f"1-{word_limit} words MAX, concise label (e.g. 'Active Users'). NO sentences. Max {max_chars} chars."
            elif _re_inline.match(r'right_(before|after)_unit$', slot_name):
                hint = f"1-3 words MAX, unit only (e.g. '/ month', 'per quarter'). Max {max_chars} chars."
            elif (_re_inline.match(r'(p|c|f|z|d)\d+_title$', slot_name)
                    or _re_inline.match(r'i\d+_name$', slot_name)):
                word_limit = max(2, min(max_chars // 7, 5))
                hint = f"2-{word_limit} words MAX, concise card heading. NO articles like 'The' or 'A'. Max {max_chars} chars."
            elif (_re_inline.match(r'(p|c|f|z|d)\d+_body$', slot_name)
                    or _re_inline.match(r'i\d+_uses$', slot_name)):
                max_sentences = 1 if max_chars < 110 else 2
                hint = f"{max_sentences} short {'sentence' if max_sentences == 1 else 'sentences'} MAX (~{max_chars} chars, ≤14 words per sentence). MUST fit — DO NOT exceed."
            elif _re_inline.match(r'(p|f|z|c)\d+_label$', slot_name):
                hint = f"1-3 words MAX, UPPERCASE category tag (e.g. 'GROWTH'). Max {max_chars} chars."
            elif _re_inline.match(r'g\d+_title$', slot_name):
                hint = f"1-2 words MAX. Max {max_chars} chars."
            elif _re_inline.match(r'g\d+_body$', slot_name):
                hint = f"1 SHORT phrase MAX (~{max_chars} chars). NOT a full sentence."
            elif _re_inline.match(r'pill_\d+$', slot_name):
                hint = f"1-4 words MAX, a concept tag (e.g. 'Emerging Markets'). Max {max_chars} chars."
            elif slot_name == "brand_chip":
                hint = f"2-4 words MAX, the document's brand identifier. Max {max_chars} chars."
            elif slot_name in ("left_title", "right_title"):
                word_limit = max(2, min(max_chars // 7, 5))
                hint = f"2-{word_limit} words MAX, concise section title. Max {max_chars} chars."
            elif slot_name in ("right_kicker", "chat_kicker", "right_list_label"):
                hint = f"3-7 words MAX, short label/lead-in. Max {max_chars} chars."
            elif slot_name in ("cta_text", "takeaway"):
                word_limit = max(8, min(max_chars // 5, 18))
                hint = f"1 SHORT impactful sentence ({word_limit} words MAX, ~{max_chars} chars). Single line."
            elif slot_name in ("banner", "banner_text"):
                hint = f"1 short sentence MAX (~{max_chars} chars). Footer band."
            elif slot_name in ("detail_heading", "gov_heading"):
                hint = f"1 short sentence MAX (~{max_chars} chars, ≤14 words)."
            elif text_type == "kicker" and slot_name == "kicker":
                word_limit = max(3, min(max_chars // 10, 8))
                hint = f"3-{word_limit} words MAX, UPPERCASE category tag (e.g. 'STRATEGIC OUTLOOK 2026'). NEVER a sentence. Max {max_chars} chars."
            elif slot_name == "subhead":
                word_limit = max(8, min(max_chars // 5, 20))
                hint = f"1 sentence MAX ({word_limit} words, ~{max_chars} chars). Single line — never two sentences."
            # ------------ Generic fallbacks ------------
            elif text_type == "title":
                word_limit = max(5, min(max_chars // 5, 15))  # ~5 chars per word avg, generous limit
                if max_chars < 50:
                    hint = f"max {max_chars} chars ({max_lines} lines), up to {word_limit} words MAX — short box, keep it tight."
                else:
                    hint = f"max {max_chars} chars ({max_lines} lines of {chars_per_line} chars), up to {word_limit} words, impactful heading — write a complete title, no ellipses."
            elif text_type == "subtitle":
                word_limit = max(5, min(max_chars // 5, 20))
                hint = f"max {max_chars} chars ({max_lines} lines), up to {word_limit} words MAX, supporting context. No ellipses."
            elif "bullet" in slot_name:
                # For bullet slots, compute how many bullets fit
                line_per_bullet = 2  # each bullet ~2 lines (prefix + content)
                max_bullets = max(3, min(max_lines // line_per_bullet, 10))
                chars_per_bullet = chars_per_line * line_per_bullet - 4  # subtract bullet prefix
                hint = f"max {max_bullets} bullet points, each max {chars_per_bullet} chars. Total max {max_chars} chars"
            elif "key_takeaway" in slot_name or "insight" in slot_name:
                sentence_count = max(1, min(max_lines // 2, 3))
                hint = f"max {max_chars} chars ({max_lines} lines), {sentence_count} impactful sentences"
            elif "quote" in slot_name and "mark" not in slot_name:
                hint = f"max {max_chars} chars ({max_lines} lines of {chars_per_line} chars), memorable quote text"
            elif "stat" in slot_name and "value" in slot_name:
                hint = f"max {max_chars} chars, single prominent number/metric (e.g. '94%', '$2.4M', '10x')"
            elif "stat" in slot_name and "label" in slot_name:
                hint = f"max {max_chars} chars ({max_lines} lines), short metric label"
            elif "metric" in slot_name:
                hint = f"max {max_chars} chars, single number with brief label (e.g. '+34%\\nGrowth Rate')"
            elif "name" in slot_name:
                hint = f"max {max_chars} chars, full name"
            elif "contact" in slot_name:
                hint = f"max {max_chars} chars, contact details: email, phone, location"
            elif "summary" in slot_name:
                sentence_count = max(2, min(max_lines // 2, 6))
                hint = f"max {max_chars} chars ({max_lines} lines), {sentence_count} sentences, professional summary"
            elif "experience" in slot_name or "skills" in slot_name:
                hint = f"max {max_chars} chars ({max_lines} lines), detailed list with descriptions"
            elif "detail" in slot_name or "description" in slot_name or "tagline" in slot_name:
                sentence_count = max(1, min(max_lines // 2, 4))
                hint = f"max {max_chars} chars ({max_lines} lines), {sentence_count} sentences of context"
            elif "source" in slot_name or "context" in slot_name or "footnote" in slot_name:
                hint = f"max {max_chars} chars ({max_lines} lines), attribution or background context"
            elif "caption" in slot_name:
                hint = f"max {max_chars} chars ({max_lines} lines), concise caption"
            elif "date" in slot_name:
                hint = f"max {max_chars} chars, date or time period"
            elif "attribution" in slot_name:
                hint = f"max {max_chars} chars, author name and credentials"
            elif "conclusion" in slot_name or "reflection" in slot_name or "analysis" in slot_name:
                sentence_count = max(2, min(max_lines // 2, 8))
                hint = f"max {max_chars} chars ({max_lines} lines), {sentence_count} sentences of substantive analysis"
            elif "column" in slot_name or "content" in slot_name:
                sentence_count = max(3, min(max_lines // 2, 10))
                hint = f"max {max_chars} chars ({max_lines} lines), {sentence_count} sentences of detailed content"
            elif "cta" in slot_name:
                hint = f"max {max_chars} chars ({max_lines} lines), call-to-action text"
            else:
                sentence_count = max(2, min(max_lines // 2, 8))
                hint = f"max {max_chars} chars ({max_lines} lines), {sentence_count} sentences of substantive content for A4 document"
            
            lines.append(f'  - {slot_name} [fontSize={font_size}px]: {{ "content": "{hint}", "fill": "#RRGGBB" (optional) }} {req_marker}')
        elif slot_type == "icon":
            lines.append(f'  - {slot_name}: {{ "iconName": "lucide-icon-name", "fill": "#RRGGBB" (optional) }} {req_marker}')
        elif slot_type == "image_placeholder":
            if is_optional:
                lines.append(f'  - {slot_name}: {{ "imageDescription": "Small contextual/decorative photo (15+ words: subject, style, mood)", "imageType": "photo" }} (OPTIONAL — include only if a small accent image would visually enrich this page)')
            else:
                lines.append(f'  - {slot_name}: {{ "imageDescription": "Detailed photo description (15+ words: subject, composition, lighting, color palette, mood, perspective — NEVER include text/words/labels in the image)", "imageType": "photo" }} {req_marker}')
        elif slot_type == "chart":
            lines.append(f'  - {slot_name}: {{ "chartConfig": {{ "type": "bar|line|pie|doughnut|radar|polarArea|scatter|bubble", "data": {{ "labels": ["Label1","Label2",...], "datasets": [{{ "label": "Series", "data": [val1,val2,...], "backgroundColor": ["#hex1",...] }}] }} }} }} {req_marker}')
        elif slot_type == "visual":
            lines.append(f'  - {slot_name}: VISUAL SLOT — provide EITHER {{ "type": "chart", "chartConfig": {{ "type": "bar|line|pie|doughnut|radar|polarArea|scatter|bubble", "data": {{ "labels": [...], "datasets": [{{...}}] }} }} }} (for data/stats/trends) OR {{ "type": "image_placeholder", "imageDescription": "Detailed description (15+ words, PHOTO ONLY, no text/labels)", "imageType": "photo" }} (for photos/illustrations). Choose chart when page has numeric data; choose image for narrative content. {req_marker}')
        elif slot_type == "svg_diagram":
            kind = slot_def.get("diagramKind", "diagram")
            sw = slot_def.get("width", 694)
            sh = slot_def.get("height", 760)
            # Aspect-aware orientation hint only — we do NOT cap element count.
            # The LLM is free to choose its illustration vocabulary (boxes,
            # organic shapes, anatomical sketch, molecular structure, etc.)
            # and adapt to the slot's shape.
            _aspect = (sw / sh) if sh else 1.0
            if _aspect >= 1.8:
                _orient_hint = (
                    f"WIDE-SHORT SLOT ({sw}x{sh}, aspect ≈ {_aspect:.1f}:1). Prefer a horizontal composition (single row / left-to-right flow). "
                    f"DO NOT stack into multiple rows — the slot is short and content will get clipped."
                )
            elif _aspect <= 0.9:
                _orient_hint = f"TALL-NARROW SLOT ({sw}x{sh}, aspect ≈ {_aspect:.1f}:1). Prefer a vertical composition (top-to-bottom flow / stacked structure)."
            else:
                _orient_hint = f"BALANCED SLOT ({sw}x{sh}, aspect ≈ {_aspect:.1f}:1). Either orientation works; choose whatever best fits the topic."

            lines.append(f'  - {slot_name}: DIAGRAM / ILLUSTRATION SVG SLOT (kind="{kind}"). This is a printable A4 page (794x1123px); your SVG occupies a {sw}x{sh}px area on the page. Sibling text slots (`intro`, `takeaways`/`caption`) render the prose around it — DO NOT embed paragraphs of body text inside the SVG. Return {{ "svgContent": "<svg width=\\"{sw}\\" height=\\"{sh}\\" viewBox=\\"0 0 {sw} {sh}\\" preserveAspectRatio=\\"xMidYMid meet\\" xmlns=\\"http://www.w3.org/2000/svg\\">…</svg>", "fillColor": "#RRGGBB" (optional accent override) }}. {req_marker}')
            lines.append(f'      DESIGN INTENT (CRITICAL — KEEP IT SIMPLE & CRISP):')
            lines.append(f'        - {_orient_hint}')
            lines.append(f'        - This is the VISUAL ONLY. Sibling `intro` and `takeaways`/`caption` text slots carry the explanatory prose — DO NOT duplicate that text inside the SVG.')
            lines.append(f'        - The SVG can be ANYTHING that best illustrates the topic in {sw}x{sh}px: a node-and-arrow diagram, a tree, a cycle, a funnel, a venn, an anatomical sketch, a molecular/biological structure (e.g. protein folding, cell, neuron), an architectural cross-section, a flowing organic illustration, etc. Pick whatever shape language communicates the idea most clearly. You are NOT required to use boxes/nodes.')
            lines.append(f'        - Aim for a SIMPLE, CLEAN, editorial illustration. Fewer, well-placed elements beat many crammed ones. NO clutter.')
            lines.append(f'        - TEXT IS MINIMAL: at most a handful of short labels (1-3 words preferred, ≤5 words hard max) for the few key parts. NO long sentences, NO arrow annotations, NO callouts, NO legends, NO paragraph blocks.')
            lines.append(f'        - TEXT MUST FIT: if a label is wider than the shape it sits on, SHORTEN the label or move it adjacent — never let text overflow or get clipped at the edge. Keep ≥12px clear space inside any container shape.')
            lines.append(f'        - HARD BOUNDS: every drawn point (x,y) must satisfy 20 ≤ x ≤ {sw - 20} and 20 ≤ y ≤ {sh - 20}. NEVER cross those edges.')
            lines.append(f'        - FILL THE CANVAS — DO NOT cluster everything in one corner or leave a wide empty margin. The leftmost element must anchor near x≈20-40, the rightmost near x≈{sw - 40}-{sw - 20}, the topmost near y≈20-40, and the bottommost near y≈{sh - 40}-{sh - 20}. Distribute elements to span the FULL {sw}x{sh} area.')
            lines.append(f'        - The root <svg> MUST use viewBox="0 0 {sw} {sh}" with width="{sw}" and height="{sh}". DO NOT pick a different viewBox — the slot is exactly {sw}x{sh}px and any other viewBox will displace your content.')
            lines.append(f'        - USE the {sw}x{sh}px area, but CENTER and BALANCE. Leave breathing room.')
            lines.append(f'        - DO NOT add unrelated decorative shapes (random triangles, wedges, blobs, background bands). Every shape must serve the illustration. NO red/orange error indicators unless the topic is explicitly about errors/failures.')
            lines.append(f'        - BACKGROUND MUST BE TRANSPARENT. Do NOT emit a full-canvas background <rect> (e.g. covering 0,0 to {sw},{sh}) or set a `background` style on the root <svg>. The SVG renders over the printable page — any opaque backdrop will clash with the page.')
            lines.append(f'        - Establish visual hierarchy via SIZE and COLOR: a hero element larger and gradient-filled, supporting elements smaller and solid-filled.')
            lines.append(f'      SVG TECHNICAL RULES:')
            lines.append(f'        - The <svg> root MUST set width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}" preserveAspectRatio="xMidYMid meet".')
            lines.append(f'        - <circle> / <ellipse> use cx and cy (NEVER x/y). <rect> / <text> use x/y. Mixing these places elements at (0,0).')
            lines.append(f'        - Use `currentColor` for primary fills/strokes; the UI substitutes the theme accent color.')
            lines.append(f'        - May use up to 4 explicit hex colors for emphasis, category coding, and contrast; everything else uses `currentColor`.')
            lines.append(f'        - LOOK POLISHED BUT RESTRAINED: define 1 inline <linearGradient> in <defs> and apply it to the HERO element only. Pick gradient stops from a vibrant modern palette (indigo #6366F1, violet #8B5CF6, sky #0EA5E9, teal #14B8A6, emerald #10B981, amber #F59E0B). Use 2-4 distinct colors total across the whole illustration — not a rainbow. Ensure white/near-white text on saturated fills.')
            lines.append(f'        - Allowed primitives: <rect>, <circle>, <ellipse>, <line>, <path>, <polyline>, <polygon>, <text>, <tspan>, <g>, inline <defs><marker>/<linearGradient>. NO <foreignObject>, NO <script>, NO external <image href>, NO <style> blocks, NO class= attributes.')
            lines.append(f'        - For arrows/flows: simple <line>/<path> with one arrowhead marker. NO text on connector lines.')
            lines.append(f'        - NEVER draw an arrow that points into empty space. EVERY arrow MUST start at one node and end exactly at another node — the arrowhead must touch a real, drawn shape. If you have N nodes, finish drawing all N before adding any connectors. Do NOT leave dangling/orphan arrows.')
            lines.append(f'        - ARROWS MUST STOP AT SHAPE BOUNDARIES, NEVER AT THE CENTER. The arrow\'s start and end points must lie ON the BORDER (outer edge) of each connected shape, not inside it. For a circle radius `r` at (cx,cy), end the arrow on the circumference (offset by r from the center, along the line toward the source). For a rectangle, end at the relevant edge. Leave ~4-6px of breathing room between the arrowhead tip and the shape\'s border so the arrowhead is visible OUTSIDE the shape and never overlaps any label text inside it.')
            lines.append(f'        - CONNECTOR ENDPOINT MATH (CRITICAL — 2-pass plan): PASS 1: Before drawing any connector, write down each shape\'s exact bounding box. For <rect x="X" y="Y" width="W" height="H">: top-center=(X+W/2, Y), bottom-center=(X+W/2, Y+H), left-center=(X, Y+H/2), right-center=(X+W, Y+H/2). For <circle cx="CX" cy="CY" r="R"> the edge point toward (PX,PY) is (CX + R*dx/len, CY + R*dy/len) where dx=PX-CX, dy=PY-CY, len=sqrt(dx*dx+dy*dy). PASS 2: Compute every <line>/<path> connector\'s (x1,y1) and (x2,y2) from those anchor formulas — NEVER eyeball them. For a VERTICAL connector between two stacked rects, x1 MUST equal x2 (the column center-x), y1 MUST equal sourceRect.bottom, y2 MUST equal targetRect.top minus 4-6px (arrowhead breathing room). For a HORIZONTAL connector, y1 MUST equal y2 (the row center-y). SELF-CHECK each connector before emitting: (x1,y1) must be an exact anchor of the source shape, (x2,y2) must be an exact anchor of the target shape with the small inset. Endpoints that do not match any shape\'s edge coordinate make lines look DETACHED / FLOATING / DISCONNECTED — the #1 SVG failure mode. REWORK any connector that fails this check.')
            lines.append(f'        - Labels: <text font-family="Inter, Arial" font-size="13-16" fill="currentColor"> with inline style. Single line per label; an optional second sub-label line via <tspan> (≤3 words, opacity 0.7) is fine.')
            lines.append(f'        - Keep markup under ~10 KB (~30 elements max). Simpler always wins.')
            if kind == "process":
                lines.append(f'        - kind="process": show a clear sequence — could be a linear stage flow with arrows, an arc, a spiral, or a stylized pipeline. Each stage gets a SHORT name (1-3 words). Detailed descriptions go in the sibling `takeaways` text slot.')
            elif kind == "hierarchy":
                lines.append(f'        - kind="hierarchy": show a tree / org-style relationship. Could be classic boxes-and-lines, a radial tree, or a layered structure. Each item: ONE short NAME (bold), optional sub-line for role (≤3 words, opacity 0.7). Detailed descriptions go in the sibling `caption` text slot.')
            elif kind == "infographic":
                lines.append(f'        - kind="infographic": pick whatever metaphor or illustration fits the topic — cycle, venn, funnel, pyramid, anatomical sketch, molecular/biological structure (e.g. protein folding, cell, neuron), architectural cross-section, organic flowing illustration, etc. Each labeled region gets ONE short NAME (1-3 words). Detailed explanation goes in the sibling `caption` text slot.')
            lines.append(f'        - DO NOT include the page title inside the SVG — the title slot above renders it separately.')
    
    lines.append('  - backgroundColor: "#RRGGBB" (optional, to override PAGE background)')
    lines.append('  - background_image: { "imageDescription": "Abstract artistic background (15+ words, PHOTO ONLY — no text, no labels, no captions. Describe a scenic, textural, or thematic photograph: composition, lighting, color palette, mood)" } (optional)')
    
    lines.append('')
    lines.append('TEXT SPACE CONSTRAINTS (CRITICAL — text that exceeds these limits will be TRUNCATED):')
    lines.append('  Each slot above has a FIXED pixel area on the A4 page (794x1123px).')
    lines.append('  The "max N chars" limit is computed from the slot\'s actual width, height, and font size.')
    lines.append('  If you write MORE text than the max, it WILL overflow and overlap other elements.')
    lines.append('  ALWAYS stay WITHIN the character limit for each slot. Shorter is better than overflow.')
    lines.append('')
    lines.append('BODY TEXT COLOR RULE (CRITICAL): For ALL body, detail, description, bullets, content, tagline text slots:')
    lines.append('  - Dark background page  → fill MUST be white/near-white ONLY: #FFFFFF, #F9FAFB, or #F3F4F6')
    lines.append('  - Light background page → fill MUST be black/near-black ONLY: #111827, #1F2937, or #374151')
    lines.append('  NEVER use grey (#6B7280, #9CA3AF, #94A3B8, #475569, etc.) for body text — grey is invisible on dark backgrounds.')
    lines.append('')
    lines.append('IMPORTANT: Every text slot above MUST be filled with meaningful content. Do NOT skip any slot. The page should look complete with no empty text areas.')
    lines.append('')
    lines.append(ICON_CATALOG)
    lines.append('')
    lines.append('CHART GUIDELINES (when using chart slots):')
    lines.append('  - Use 3-8 data points (labels). More than 8 makes charts unreadable at A4 print size.')
    lines.append('  - Labels must be concise: max 15 characters each.')
    lines.append('  - Always include backgroundColor array matching data length.')
    lines.append('  - Supported types: bar, line, pie, doughnut, radar, polarArea, scatter, bubble.')
    lines.append('  - Use ONLY real data from context. Never fabricate chart data.')
    lines.append('  - If a `=== COMPUTED DATA ===` block is present in the prompt, copy the matching aggregation\'s `value` (already shaped as `{"labels":[...],"data":[...]}`) directly into `chartConfig.data`. Choose `chartConfig.type` to match its `chart_type`. Do NOT rename labels, do NOT round, do NOT invent extra series.')
    lines.append('  - The schema preview shows only column names + 3 samples per column — it is NOT enough to compute aggregates. NEVER author labels/datasets from those samples.')
    lines.append('  - For a single number text slot, paste the matching aggregation\'s `value` (a number) verbatim — only adjust units/commas, never magnitude.')
    lines.append('  - If no matching aggregation exists in COMPUTED DATA, omit the chart/stat or describe qualitatively. Do NOT fabricate. (Legacy fallback: as a last resort you may emit `chartConfig: {}` with a sibling `"_data_request": {"kind":"chart|stat|list", ...}` and a post-processing pass may resolve it.)')
    lines.append('')
    lines.append('IMAGE DESCRIPTION GUIDELINES (STRICT — applies to BOTH `imageDescription` slots AND `background_image.imageDescription`):')
    lines.append('  - ABSOLUTELY NO text, words, letters, numbers, labels, captions, titles, headlines, watermarks, signage, typography, logos with text, infographic-style writing, or characters of any language anywhere in the image.')
    lines.append('  - DO NOT use phrases like "with the text…", "labeled …", "titled …", "reading …", "saying …", "inscribed …", "with caption …", "with sign that reads …", "containing the words …" — these instruct the image model to render text and MUST be omitted.')
    lines.append('  - DO NOT include ANY quoted strings ("…", \'…\') in the description — quoted phrases get rendered as literal text in the image.')
    lines.append('  - For `imageDescription` (foreground image): NAME CONCRETE PHYSICAL SUBJECTS DIRECTLY (animal, plant, object, person, place, food, vehicle, building, body part, weather, landscape). Diffusion models render concrete physical nouns accurately and do NOT leak them as text. Euphemisms produce wrong subjects. USE VISUAL ANALOGUES ONLY for ABSTRACT / NON-VISUAL concepts that have no physical form: technical jargon ("OAuth", "Kubernetes"), scientific processes ("Krebs cycle", "mitosis", "glycolysis", "DNA", "ATP"), business metrics ("Q3 revenue"), brand/product names, acronyms — replace those with generic analogues (e.g. "interconnected organic structures with glowing nodes" instead of "Krebs cycle").')
    lines.append('  - For `background_image.imageDescription`: keep it ABSTRACT and TEXTURAL only — soft gradients, blurred organic shapes, abstract patterns, bokeh, atmospheric lighting. NO recognisable subjects, no scenes that suggest a named concept. Backgrounds must not compete with page text.')
    lines.append('  - For foreground `imageDescription`: pattern is <concrete subject>, <action/pose>, <setting>, <lighting>, <composition>, <colour/mood>.')
    lines.append('  - For backgrounds: use abstract/textural photos that complement (not compete with) the page text.')
    lines.append('  - Good: "Aerial view of turquoise ocean waves meeting white sandy beach, soft natural lighting, warm tropical color palette, serene and expansive mood"')
    lines.append('  - Good: "Close-up of neural network-like structure with glowing blue connections on dark background, futuristic and elegant, shallow depth of field"')
    lines.append('  - Bad: "Chart showing revenue growth" (never describe charts as images)')
    lines.append('  - Bad: "Image with the text Quality Report" (NEVER include text or quoted phrases in images)')
    lines.append('  - Bad: "A poster titled \'Annual Review\'" (never describe titles, signs, posters, or banners with words)')
    lines.append('  - Bad: "Diagram of the Krebs cycle" (NEVER name concepts — they get rendered as text. Use "abstract organic structures with glowing connections" instead)')
    
    return "\n".join(lines)


def get_example_json_for_template(template_id: str) -> str:
    """
    Generate an example JSON output for a specific template.
    """
    import json
    template = PAGE_TEMPLATES.get(template_id)
    if not template:
        return "{}"
    
    example = {
        "template": template_id,
        "slots": {}
    }
    
    for slot_name, slot_def in template["slots"].items():
        slot_type = slot_def["type"]
        
        if slot_type == "text":
            if "title" in slot_name and slot_name == "title":
                example["slots"][slot_name] = {"content": "Comprehensive Analysis of Market Trends"}
            elif "subtitle" in slot_name:
                example["slots"][slot_name] = {"content": "An in-depth exploration of emerging opportunities and strategic considerations for the coming fiscal year"}
            elif "title" in slot_name:
                example["slots"][slot_name] = {"content": f"Key Highlights: {slot_name.replace('_title', '').replace('_', ' ').title()}"}
            elif "desc" in slot_name:
                example["slots"][slot_name] = {"content": "This section provides a detailed examination of the underlying factors driving performance improvements. The analysis incorporates both quantitative metrics and qualitative assessments from industry experts."}
            elif "content" in slot_name:
                example["slots"][slot_name] = {"content": "Our comprehensive research reveals several key findings that warrant attention. First, market conditions have shifted significantly over the past quarter, creating new opportunities for strategic positioning. Second, customer behavior data indicates a strong preference for integrated solutions. These insights suggest a clear path forward for sustainable growth."}
            elif "bullets" in slot_name:
                example["slots"][slot_name] = {"content": "• Market analysis reveals 34% growth in the target segment with accelerating adoption rates\n• Customer satisfaction scores improved by 18 points following implementation of new service protocols\n• Strategic partnerships with three industry leaders have opened access to untapped segments\n• Technology infrastructure upgrades reduced operational costs by $2.3M annually\n• Talent acquisition strategy successfully attracted 45 high-caliber professionals\n• Regulatory compliance framework now covers all major jurisdictions"}
            elif "quote" in slot_name:
                example["slots"][slot_name] = {"content": "The measure of intelligence is the ability to change. In times of transformation, those who embrace innovation will emerge as the leaders of tomorrow."}
            elif "attribution" in slot_name:
                example["slots"][slot_name] = {"content": "— Dr. Maria Chen, Director of Strategic Innovation, Global Research Institute, 2024"}
            elif "key_takeaway" in slot_name or "insight" in slot_name:
                example["slots"][slot_name] = {"content": "The most significant finding is that organizations investing in early-stage digital transformation are achieving 3.2x returns within 24 months, far exceeding traditional investment benchmarks."}
            elif "detail" in slot_name or "description" in slot_name:
                example["slots"][slot_name] = {"content": "This methodology has been rigorously tested across 50+ enterprise deployments in diverse industries. Results consistently demonstrate performance improvements of 25-40% above established benchmarks."}
            elif "tagline" in slot_name:
                example["slots"][slot_name] = {"content": "Transforming organizational challenges into measurable competitive advantages through evidence-based strategies"}
            elif "source" in slot_name or "context" in slot_name:
                example["slots"][slot_name] = {"content": "Based on comprehensive longitudinal analysis of 200+ organizations across 15 industry verticals, 2023-2024"}
            elif "name" in slot_name:
                example["slots"][slot_name] = {"content": "Alexandra M. Richardson"}
            elif "contact" in slot_name:
                example["slots"][slot_name] = {"content": "alexandra.richardson@email.com | +1 (555) 234-5678 | San Francisco, CA"}
            elif "summary" in slot_name:
                example["slots"][slot_name] = {"content": "Results-driven professional with 12+ years of experience in strategic planning and operational excellence. Proven track record of delivering measurable business outcomes through innovative solutions and cross-functional team leadership."}
            elif "experience" in slot_name:
                example["slots"][slot_name] = {"content": "**TechCorp International** — Senior Director of Operations\nJan 2020 – Present\n• Led transformation initiative resulting in $4.2M annual cost savings\n• Managed cross-functional team of 35 professionals across 4 regions\n• Implemented data-driven decision framework adopted company-wide"}
            elif "skills" in slot_name:
                example["slots"][slot_name] = {"content": "• Strategic Planning & Execution\n• Data Analytics & Business Intelligence\n• Cross-functional Leadership\n• Financial Modeling & Forecasting\n• Stakeholder Management"}
            else:
                example["slots"][slot_name] = {"content": f"Detailed and substantive content for {slot_name} that provides real value and contributes meaningfully to the document's purpose."}
        elif slot_type == "icon":
            example["slots"][slot_name] = {"iconName": "circle"}
        elif slot_type == "image_placeholder":
            if slot_name in template.get("optional_slots", []):
                continue  # Skip optional image placeholders in example
            example["slots"][slot_name] = {"imageDescription": "Professional corporate environment with modern architecture, warm natural lighting through floor-to-ceiling windows, clean minimalist composition with empty unbranded surfaces", "imageType": "photo"}
        elif slot_type == "chart":
            example["slots"][slot_name] = {"chartConfig": {"type": "bar", "data": {"labels": ["Q1", "Q2", "Q3", "Q4"], "datasets": [{"data": [45, 62, 78, 91], "label": "Revenue Growth (%)", "backgroundColor": ["#3B82F6", "#10B981", "#F59E0B", "#EF4444"]}]}}}
        elif slot_type == "visual":
            example["slots"][slot_name] = {"type": "image_placeholder", "imageDescription": "Abstract visualization of interconnected glowing data points and flowing gradient lines on dark background, modern futuristic mood, no words", "imageType": "photo"}
        elif slot_type == "svg_diagram":
            kind = slot_def.get("diagramKind", "diagram")
            sw = slot_def.get("width", 694)
            sh = slot_def.get("height", 760)
            if kind == "hierarchy":
                svg_example = (
                    f'<svg width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}" xmlns="http://www.w3.org/2000/svg">'
                    f'<defs><style>.node{{fill:none;stroke:currentColor;stroke-width:2}}.lbl{{font-family:Inter,Arial;font-size:14;fill:currentColor;text-anchor:middle}}.edge{{stroke:currentColor;stroke-width:1.5;fill:none}}</style></defs>'
                    f'<rect class="node" x="277" y="30" width="140" height="56" rx="6"/><text class="lbl" x="347" y="62">CEO</text>'
                    f'<line class="edge" x1="347" y1="86" x2="347" y2="120"/><line class="edge" x1="120" y1="120" x2="574" y2="120"/>'
                    f'<line class="edge" x1="120" y1="120" x2="120" y2="160"/><line class="edge" x1="347" y1="120" x2="347" y2="160"/><line class="edge" x1="574" y1="120" x2="574" y2="160"/>'
                    f'<rect class="node" x="50" y="160" width="140" height="56" rx="6"/><text class="lbl" x="120" y="192">CTO</text>'
                    f'<rect class="node" x="277" y="160" width="140" height="56" rx="6"/><text class="lbl" x="347" y="192">CFO</text>'
                    f'<rect class="node" x="504" y="160" width="140" height="56" rx="6"/><text class="lbl" x="574" y="192">COO</text>'
                    f'</svg>'
                )
            elif kind == "process":
                svg_example = (
                    f'<svg width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}" xmlns="http://www.w3.org/2000/svg">'
                    f'<defs><marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker><style>.box{{fill:none;stroke:currentColor;stroke-width:2}}.num{{font-family:Inter,Arial;font-size:18;font-weight:700;fill:currentColor;text-anchor:middle}}.lbl{{font-family:Inter,Arial;font-size:14;fill:currentColor;text-anchor:middle}}.edge{{stroke:currentColor;stroke-width:2;fill:none}}</style></defs>'
                    f'<rect class="box" x="200" y="40"  width="290" height="100" rx="10"/><text class="num" x="240" y="80">1</text><text class="lbl" x="345" y="95">Transcription</text>'
                    f'<line class="edge" x1="345" y1="140" x2="345" y2="180" marker-end="url(#arr)"/>'
                    f'<rect class="box" x="200" y="190" width="290" height="100" rx="10"/><text class="num" x="240" y="230">2</text><text class="lbl" x="345" y="245">RNA processing</text>'
                    f'<line class="edge" x1="345" y1="290" x2="345" y2="330" marker-end="url(#arr)"/>'
                    f'<rect class="box" x="200" y="340" width="290" height="100" rx="10"/><text class="num" x="240" y="380">3</text><text class="lbl" x="345" y="395">Translation</text>'
                    f'<line class="edge" x1="345" y1="440" x2="345" y2="480" marker-end="url(#arr)"/>'
                    f'<rect class="box" x="200" y="490" width="290" height="100" rx="10"/><text class="num" x="240" y="530">4</text><text class="lbl" x="345" y="545">Folding</text>'
                    f'</svg>'
                )
            else:
                svg_example = (
                    f'<svg width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}" xmlns="http://www.w3.org/2000/svg">'
                    f'<defs><style>.ring{{fill:none;stroke:currentColor;stroke-width:3}}.lbl{{font-family:Inter,Arial;font-size:16;fill:currentColor;text-anchor:middle}}</style></defs>'
                    f'<circle class="ring" cx="{sw//2}" cy="{sh//2}" r="{min(sw,sh)//3}"/>'
                    f'<text class="lbl" x="{sw//2}" y="{sh//2}">Concept Diagram</text>'
                    f'</svg>'
                )
            example["slots"][slot_name] = {"svgContent": svg_example}
    
    return json.dumps(example, indent=2)


def apply_style_to_template(template: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply style colors to a template definition.
    """
    if not template or not style:
        return template
    
    import copy
    styled = copy.deepcopy(template)
    
    accent_color = style.get("accentColor", "#3B82F6")
    card_bg = style.get("cardBackground", "#f8fafc")
    card_border = style.get("cardBorder", "#e5e7eb")
    text_primary = style.get("textPrimary", style.get("textStyles", {}).get("title", {}).get("color", "#111827"))
    text_secondary = style.get("textSecondary", style.get("textStyles", {}).get("body", {}).get("color", "#374151"))
    # Background resolution: template's own `backgroundColor` (executive
    # `_dark` templates) is authoritative unless caller explicitly overrides
    # with a non-default style. Prevents `exec_pg_cover` and `exec_pg_*_dark`
    # from rendering on white and silencing all white-on-dark text.
    template_bg = (template.get("backgroundColor") or "").strip() if isinstance(template.get("backgroundColor"), str) else ""
    explicit_style_bg = style.get("PAGEBackground")
    if explicit_style_bg and explicit_style_bg.lower() not in ("", "#ffffff", "#fff", "white"):
        PAGE_bg = explicit_style_bg
    elif template_bg:
        PAGE_bg = template_bg
    else:
        PAGE_bg = explicit_style_bg or "#ffffff"

    # Helper: detect dark background for strict body-text contrast enforcement
    def _is_dark(hex_c: str) -> bool:
        try:
            h = hex_c.lstrip('#')
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5
        except Exception:
            return False

    bg_is_dark = _is_dark(PAGE_bg)

    # INSTRUCTION for each body/detail text slot:
    # - Dark background theme  → strictly use white shades (#FFFFFF, #F9FAFB, #F3F4F6)
    # - Light background theme → strictly use black shades (#111827, #1F2937, #374151)
    # NEVER use grey for body text — grey is invisible on dark and low-contrast on light.
    strict_body_color = "#FFFFFF" if bg_is_dark else "#1F2937"
    color_instruction = (
        "dark_bg: use white/near-white (#FFFFFF, #F3F4F6) only"
        if bg_is_dark else
        "light_bg: use black/near-black (#111827, #1F2937) only"
    )

    # Title/subtitle: validate text_primary against bg; fix if bad contrast
    strict_title_color = text_primary
    if bg_is_dark and _is_dark(text_primary):
        strict_title_color = "#FFFFFF"
    elif not bg_is_dark and not _is_dark(text_primary):
        strict_title_color = "#111827"

    for slot_name, slot_def in styled.get("slots", {}).items():
        if slot_def.get("type") == "text":
            if slot_def.get("useWhiteText"):
                slot_def["fill"] = "#ffffff"
            elif slot_def.get("textType") in ["title", "subtitle"]:
                slot_def["fill"] = strict_title_color
            else:
                # Body / detail text: strictly enforce contrast color
                slot_def["fill"] = strict_body_color
                slot_def["colorInstruction"] = color_instruction
        elif slot_def.get("type") == "icon":
            slot_def["fill"] = accent_color
    
    for dec in styled.get("decorations", []):
        if dec.get("useAccentColor"):
            dec["fill"] = accent_color
        if dec.get("useCardBackground"):
            dec["fill"] = card_bg
            dec["stroke"] = card_border
    
    styled["backgroundColor"] = PAGE_bg
    
    return styled


def _validate_chart_config(config, fallback):
    """Validate chartConfig structure, apply deterministic fixes, flag for AI repair if still invalid.
    Returns config if valid, or fallback with _ai_fix_needed=True if data is structurally broken."""
    if not isinstance(config, dict) or not config:
        return {**fallback, "_ai_fix_needed": True}
    # Normalize chart type — AI sometimes returns icon names (e.g. "chart-bar") instead of Chart.js types ("bar")
    VALID_CHART_TYPES = {"bar", "line", "pie", "doughnut", "radar", "polarArea", "scatter", "bubble"}
    chart_type = config.get("type", "bar")
    if chart_type not in VALID_CHART_TYPES:
        # Strip common prefixes: "chart-bar" → "bar", "chart-line" → "line"
        stripped = chart_type.replace("chart-", "").replace("chart_", "")
        config["type"] = stripped if stripped in VALID_CHART_TYPES else "bar"
    # Fix misplaced labels/datasets (should be inside config.data, not config root)
    if "data" not in config and ("labels" in config or "datasets" in config):
        config["data"] = {"labels": config.pop("labels", []), "datasets": config.pop("datasets", [])}
    data = config.get("data")
    if not isinstance(data, dict) or not data:
        return {**fallback, "_ai_fix_needed": True}
    labels = data.get("labels")
    datasets = data.get("datasets")
    if not isinstance(labels, list) or len(labels) == 0:
        return {**fallback, "_ai_fix_needed": True}
    if not isinstance(datasets, list) or len(datasets) == 0:
        return {**fallback, "_ai_fix_needed": True}
    first_ds = datasets[0]
    if not isinstance(first_ds, dict) or not isinstance(first_ds.get("data"), list) or len(first_ds.get("data", [])) == 0:
        return {**fallback, "_ai_fix_needed": True}
    return config


def build_elements_from_template(template: Dict[str, Any], slot_data: Dict[str, Any], style: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build final elements list from template + AI slot content + style.
    """
    import time
    
    styled = apply_style_to_template(template, style)
    elements = []
    element_idx = 0
    
    # Add decorations first
    for dec in styled.get("decorations", []):
        el = {
            "id": f"dec_{int(time.time() * 1000)}_{element_idx}",
            **dec,
        }
        el.pop("useAccentColor", None)
        el.pop("useCardBackground", None)
        
        if "stepNumber" in el:
            step_num = el.pop("stepNumber")
            elements.append(el)
            element_idx += 1
            elements.append({
                "id": f"step_num_{int(time.time() * 1000)}_{element_idx}",
                "type": "text",
                "textType": "body",
                "content": str(step_num),
                "x": el["x"],
                "y": el["y"] + 5,
                "width": el["width"],
                "height": el["height"] - 10,
                "fontSize": 28,
                "fontWeight": "bold",
                "textAlign": "center",
                "fill": "#ffffff",
                "zIndex": el.get("zIndex", 15) + 5,
            })
            element_idx += 1
            continue
        
        elements.append(el)
        element_idx += 1
    
    # Add slot elements with AI content
    for slot_name, slot_def in styled.get("slots", {}).items():
        ai_content = slot_data.get(slot_name, {})
        
        if isinstance(ai_content, str):
            ai_content = {"content": ai_content}
        
        is_optional = slot_name in template.get("optional_slots", [])
        has_content = ai_content.get("content") or ai_content.get("iconName") or ai_content.get("imageDescription") or ai_content.get("chartConfig")
        
        if is_optional and not has_content:
            continue
        
        is_required = slot_name in template.get("required_slots", [])
        if is_required and not has_content:
            import logging
            logging.warning(f"[TEMPLATE] Required slot '{slot_name}' has no content from AI")
        
        el = {
            "id": f"slot_{slot_name}_{int(time.time() * 1000)}_{element_idx}",
            "type": ai_content.get("type", slot_def["type"]),
            "x": slot_def["x"],
            "y": slot_def["y"],
            "width": slot_def.get("width", 100),
            "height": slot_def.get("height", 50),
            "zIndex": slot_def.get("zIndex", 50),
        }
        
        current_type = el["type"]
        
        if current_type == "text":
            el["textType"] = slot_def.get("textType", "body")
            content = ai_content.get("content", "")
            if not content and is_required:
                content = slot_name.replace("_", " ").title()
            
            # Truncate content that exceeds slot capacity
            # NEVER truncate titles/subtitles — let them overflow naturally
            text_type = slot_def.get("textType", "body")
            if text_type not in ("title", "subtitle"):
                limits = compute_slot_max_chars(slot_def)
                max_chars = limits["maxChars"]
                if len(content) > max_chars:
                    # Try to truncate at sentence boundary
                    truncated = content[:max_chars]
                    for sep in ['. ', '! ', '? ']:
                        last_sep = truncated.rfind(sep)
                        if last_sep > max_chars * 0.5:
                            truncated = truncated[:last_sep + 1]
                            break
                    else:
                        # No sentence boundary — cut at last space, no ellipsis
                        last_space = truncated.rfind(' ')
                        if last_space > max_chars * 0.5:
                            truncated = truncated[:last_space]
                    content = truncated
            
            el["content"] = content
            el["fontSize"] = slot_def.get("fontSize", 20)
            el["fontWeight"] = slot_def.get("fontWeight", "normal")
            el["fontStyle"] = slot_def.get("fontStyle", "normal")
            el["textAlign"] = slot_def.get("textAlign", "left")

            text_type = slot_def.get("textType", "body")
            # For body/detail text: enforce strict contrast; do not allow AI grey to slip through
            STRICT_CONTRAST_TYPES = {"body", "detail", "description", "bullets", "content", "tagline", "small"}
            computed_fill = slot_def.get("fill", "#111827")  # pre-set by apply_style_to_template
            if text_type in STRICT_CONTRAST_TYPES:
                ai_fill = (ai_content.get("fill") or "").strip()
                if ai_fill:
                    # Accept AI fill only if it has good contrast against the PAGE background
                    PAGE_bg = style.get("PAGEBackground", "#ffffff")
                    def _fill_has_contrast(tc: str, bc: str) -> bool:
                        try:
                            def lum(h: str) -> float:
                                h = h.lstrip('#')
                                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                                return (0.299 * r + 0.587 * g + 0.114 * b) / 255
                            return abs(lum(tc) - lum(bc)) > 0.35
                        except Exception:
                            return True
                    el["fill"] = ai_fill if _fill_has_contrast(ai_fill, PAGE_bg) else computed_fill
                else:
                    el["fill"] = computed_fill
            else:
                el["fill"] = ai_content.get("fill") or computed_fill
        
        elif current_type == "icon":
            el["iconName"] = ai_content.get("iconName", "circle")
            el["size"] = slot_def.get("size", 56)
            el["fill"] = ai_content.get("fill") or slot_def.get("fill", "#3B82F6")

        elif current_type == "bullets":
            # Bullets slot: emit as a text element with bullet glyphs baked
            # into the string. The frontend canvas has no `bullets` type
            # (logs `Unknown element type: bullets` and returns null), so we
            # let the existing text renderer handle it. See matching branch
            # in slide_templates.py.
            raw = ai_content.get("content", "")
            if isinstance(raw, list):
                _lines = []
                for item in raw:
                    s = str(item).strip().lstrip("•").lstrip("-").lstrip("*").strip()
                    if s:
                        _lines.append(f"• {s}")
                content = "\n".join(_lines)
            elif isinstance(raw, str):
                content = raw
                if content and "•" not in content:
                    _normalized = []
                    for line in content.split("\n"):
                        s = line.strip().lstrip("-").lstrip("*").strip()
                        if s:
                            _normalized.append(f"• {s}")
                    if _normalized:
                        content = "\n".join(_normalized)
            else:
                content = str(raw or "")
            el["type"] = "text"
            el["textType"] = "bullets"
            el["content"] = content
            el["fontSize"] = slot_def.get("fontSize", 15)
            el["fontWeight"] = slot_def.get("fontWeight", "normal")
            el["fontStyle"] = slot_def.get("fontStyle", "normal")
            el["lineHeight"] = slot_def.get("lineHeight", 1.7)
            el["textAlign"] = slot_def.get("textAlign", "left")
            el["bulletStyle"] = slot_def.get("bulletStyle", "dot")
            el["bulletColor"] = ai_content.get("bulletColor") or slot_def.get("bulletColor", "#2563EB")
            el["fill"] = ai_content.get("fill") or slot_def.get("color", slot_def.get("fill", "#1F2937"))

        elif current_type == "image_placeholder":
            el["imageDescription"] = ai_content.get("imageDescription", "")
            el["imageType"] = ai_content.get("imageType", "photo")

        elif current_type == "svg_diagram":
            svg_content = ai_content.get("svgContent") or ai_content.get("svg") or ""
            if isinstance(svg_content, str) and svg_content.strip():
                # Auto-fix common LLM mistakes: <circle y="N"> → <circle cy="N">,
                # bare `&` → `&amp;`, etc. Failure leaves the original markup
                # untouched so the UI's fallback render path can still handle it.
                try:
                    from svg_diagram_prompts import sanitize_svg as _sanitize_svg
                    _ok, _cleaned, _err = _sanitize_svg(
                        svg_content,
                        expected_width=int(slot_def.get("width") or 0) or None,
                        expected_height=int(slot_def.get("height") or 0) or None,
                    )
                    if _ok and _cleaned:
                        svg_content = _cleaned
                    elif _err:
                        logging.warning(f"[TEMPLATE] svg_diagram sanitize failed: {_err}")
                except Exception as _e:
                    logging.warning(f"[TEMPLATE] svg_diagram sanitize error: {_e}")
            el["svgContent"] = svg_content if isinstance(svg_content, str) else ""
            el["fillColor"] = ai_content.get("fillColor") or style.get("accentColor", "#3B82F6")
            el["diagramKind"] = slot_def.get("diagramKind", "diagram")
            # Capture metadata that lets the user reopen the AI Diagram modal pre-filled
            # with the original prompt + title. Fall back to slot/page context so the
            # regenerate flow is always functional even if the LLM omits these fields.
            _diagram_title = ai_content.get("diagramTitle") or ai_content.get("title") or ""
            _diagram_prompt = ai_content.get("diagramPrompt") or ai_content.get("prompt") or ""
            if not _diagram_prompt:
                _slot_desc = slot_def.get("description") or slot_def.get("hint") or ""
                _title_slot = slot_data.get("title") if isinstance(slot_data, dict) else None
                _page_title = ""
                if isinstance(_title_slot, dict):
                    _page_title = _title_slot.get("text") or _title_slot.get("content") or ""
                elif isinstance(_title_slot, str):
                    _page_title = _title_slot
                _kind_label = el["diagramKind"]
                _diagram_prompt = (
                    f"{_kind_label.capitalize()} diagram for: {_page_title or _slot_desc or slot_name}"
                ).strip()
            el["diagramTitle"] = _diagram_title.strip() if isinstance(_diagram_title, str) else ""
            el["prompt"] = _diagram_prompt.strip() if isinstance(_diagram_prompt, str) else ""

        elif current_type == "chart":
            _chart_fallback = {
                "type": "bar",
                "data": {
                    "labels": ["Item 1", "Item 2", "Item 3"],
                    "datasets": [{
                        "label": "Demo Data",
                        "data": [10, 20, 15],
                        "backgroundColor": ["#3B82F6", "#10B981", "#F59E0B"]
                    }]
                },
                "options": {
                    "plugins": {
                        "legend": {"display": True}
                    }
                }
            }
            el["chartConfig"] = _validate_chart_config(ai_content.get("chartConfig"), _chart_fallback)
        
        elif current_type == "visual":
            # Resolve visual to chart or image_placeholder based on AI content
            raw_chart = ai_content.get("chartConfig")
            if raw_chart:
                el["type"] = "chart"
                _visual_chart_fallback = {
                    "type": "bar",
                    "data": {"labels": ["A", "B", "C"], "datasets": [{"data": [10, 20, 15], "label": "Data", "backgroundColor": ["#3B82F6", "#10B981", "#F59E0B"]}]}
                }
                el["chartConfig"] = _validate_chart_config(raw_chart, _visual_chart_fallback)
            elif ai_content.get("imageDescription"):
                el["type"] = "image_placeholder"
                el["imageDescription"] = ai_content.get("imageDescription", "")
                el["imageType"] = ai_content.get("imageType", "photo")
            else:
                el["type"] = "image_placeholder"
                el["imageDescription"] = "Relevant visual for this topic"
                el["imageType"] = "photo"

        elif current_type == "shape":
            # Shape slots (card backgrounds, accent bars, vertical side-rules,
            # CTA straps in executive A4 templates) carry visual properties on
            # the slot definition itself. The base element constructor only
            # copies geometry + zIndex, so without this branch the renderer
            # receives a shape with no fill / no shapeType / no rounded
            # corners and falls back to its default blue rectangle — visible
            # as the broken blue card on `exec_pg_argument` where the white
            # content card disappeared.
            for prop in (
                "shapeType", "fill", "stroke", "strokeWidth", "rx", "ry",
                "opacity", "shadow", "borderRadius", "borderColor",
            ):
                if prop in slot_def:
                    el[prop] = slot_def[prop]
            if isinstance(ai_content, dict):
                for prop in ("fill", "stroke", "shapeType"):
                    v = ai_content.get(prop)
                    if v:
                        el[prop] = v

        elements.append(el)
        element_idx += 1

    return elements


def get_all_template_names_for_prompt() -> str:
    """Get formatted list of template names for AI prompt."""
    lines = []
    for tid, t in PAGE_TEMPLATES.items():
        lines.append(f"- {tid}: {t['description']}")
    return "\n".join(lines)


def _word_match(keyword: str, text: str) -> bool:
    """Check if keyword matches as a whole word/phrase in text (not substring)."""
    import re
    if " " in keyword or len(keyword) > 6:
        return keyword in text
    return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text))


def auto_match_template(page_title: str, page_instruction: str, page_index: int, total_pages: int, layout: str = "", image_prompt: str = "", has_structured_data: bool = False, deck_profile: Optional[str] = None) -> str:
    """Locally match best template for a printable page based on keywords, position, and image hints.

    ``deck_profile`` ensures FIRST/LAST positional fallbacks point at IDs that
    actually exist in the chosen profile's catalog (corporate uses
    exec_pg_cover / exec_pg_closing_dark; general uses title_hero / closing).
    """
    import logging
    title_lower = (page_title or "").lower()
    instr_lower = (page_instruction or "").lower()
    combined = f"{title_lower} {instr_lower}"
    layout_lower = (layout or "").lower()
    _profile_key = deck_profile if deck_profile in DECK_PROFILES else DECK_PROFILE_CORPORATE
    _is_corp = _profile_key in (
        DECK_PROFILE_CORPORATE,
        DECK_PROFILE_CORPORATE_BOARDROOM,
        DECK_PROFILE_CORPORATE_WITH_VISUALS,
    )

    # Direct layout hint → template mapping (from outline generation)
    LAYOUT_TO_TEMPLATE = {
        "title": "title_hero",
        "title_content": "bullets",
        "two_column": "two_columns",
        "image_focus": "image_left",
        "bullet_points": "bullets",
        "quote": "quote",
        "comparison": "comparison",
        "chart": "chart_focus",
        "data": "stats_highlight",
        "timeline": "timeline",
        "process": "process_steps",
        "process_diagram": "process_steps",
        "flow": "process_steps",
        "lifecycle": "process_steps",
        "hierarchy": "org_hierarchy",
        "org_chart": "org_hierarchy",
        "tree": "org_hierarchy",
        "infographic": "infographic_diagram",
        "diagram": "infographic_diagram",
    }

    # Determine if the page explicitly wants an image (from outline layout/image_prompt)
    wants_image = bool(image_prompt) or any(
        kw in layout_lower for kw in ["image", "photo", "visual", "picture"]
    )

    # Position-based rules
    if page_index == 0:
        if _is_corp:
            # Corporate cover is the dark exec_pg_cover — storyboard supplies
            # the deck-coherent background image separately.
            return "exec_pg_cover"
        if wants_image or any(kw in combined for kw in ["image", "photo", "visual"]):
            return "title_image"
        if any(kw in combined for kw in ["report", "document", "cover"]):
            return "report_title_page"
        return "title_hero"
    if page_index == total_pages - 1:
        if _is_corp:
            return "exec_pg_closing_dark"
        if any(kw in combined for kw in ["closing", "end", "thank", "contact", "conclusion"]):
            return "closing"

    # LAYOUT HINT PRIORITY: Use outline layout value for direct matching
    if layout_lower and layout_lower in LAYOUT_TO_TEMPLATE:
        matched = LAYOUT_TO_TEMPLATE[layout_lower]
        # Corporate has no `bullets` / `title_hero` — remap layout-hint matches
        # that name general-only IDs to the corporate equivalent.
        if _is_corp:
            _CORP_REMAP = {
                "title_hero": "exec_pg_cover",
                "bullets": "exec_pg_argument",
            }
            if matched in _CORP_REMAP:
                matched = _CORP_REMAP[matched]
        else:
            # Upgrade text-only templates to image variants for visual richness
            if matched == "bullets":
                if wants_image:
                    matched = "image_right" if page_index % 2 == 0 else "image_left"
                elif page_index != 0 and page_index != total_pages - 1:
                    # Even without explicit image_prompt, upgrade bullets for content pages
                    matched = "image_right" if page_index % 2 == 0 else "image_left"
        logging.info(f"🎯 [AUTO_MATCH_PRINTABLE] Layout hint '{layout_lower}' → {matched}")
        return matched

    # STRUCTURED DATA PRIORITY: When structured data context is present,
    # prefer chart templates to render real data visualizations instead of images
    if has_structured_data:
        data_keywords = ["data", "stats", "statistics", "numbers", "metrics", "trends",
                        "growth", "revenue", "sales", "percentage", "increase", "decrease",
                        "comparison", "analysis", "performance", "results", "chart", "graph"]
        has_data_content = any(kw in combined for kw in data_keywords)

        if has_data_content:
            if wants_image:
                logging.info(f"🎯 [AUTO_MATCH_PRINTABLE] Structured data + image → chart_and_image")
                return "chart_and_image"
            if any(kw in combined for kw in ["dashboard", "overview", "kpi"]):
                return "data_dashboard"
            if any(kw in combined for kw in ["compare", "versus", "vs"]):
                return "data_dashboard"
            pick = "chart_right" if page_index % 2 == 0 else "chart_left"
            logging.info(f"🎯 [AUTO_MATCH_PRINTABLE] Structured data + data content → {pick}")
            return pick

    # IMAGE PRIORITY: When layout or image_prompt explicitly requests images,
    # always select an image template for foreground visual impact
    if wants_image:
        if any(kw in combined for kw in ["bullet", "list", "point", "feature"]):
            logging.info(f"🎯 [AUTO_MATCH_PRINTABLE] Image requested + bullet content → image_right")
            return "image_right"
        if any(kw in combined for kw in ["cinematic", "dramatic", "scenic", "full"]):
            logging.info(f"🎯 [AUTO_MATCH_PRINTABLE] Image requested + cinematic → full_bleed_image")
            return "full_bleed_image"
        pick = "image_right" if page_index % 2 == 0 else "image_left"
        logging.info(f"🎯 [AUTO_MATCH_PRINTABLE] Image requested → {pick}")
        return pick

    # CHART PRIORITY: When content explicitly mentions charts/graphs with other elements
    wants_chart = any(kw in combined for kw in ["chart", "graph", "visualization", "bar chart", "pie chart", "line chart"])
    if wants_chart:
        if any(kw in combined for kw in ["image", "photo", "picture"]):
            logging.info(f"🎯 [AUTO_MATCH_PRINTABLE] Chart + image requested → chart_and_image")
            return "chart_and_image"
        if any(kw in combined for kw in ["dashboard", "metric", "kpi", "analytics"]):
            return "data_dashboard"
        # Alternate chart_left / chart_right for variety
        pick = "chart_right" if page_index % 2 == 0 else "chart_left"
        logging.info(f"🎯 [AUTO_MATCH_PRINTABLE] Chart requested → {pick}")
        return pick

    # Keyword matching against TEMPLATE_KEYWORDS (with word boundary protection)
    best_template = None
    best_score = 0
    for template_id, keywords in TEMPLATE_KEYWORDS.items():
        if template_id in ("title_hero", "title_image", "blank_freeflow"):
            continue
        score = sum(1 for kw in keywords if _word_match(kw.lower(), combined))
        if score > best_score:
            best_score = score
            best_template = template_id

    if best_template and best_score > 0:
        return best_template

    # Tag-based fallback (with word boundary protection)
    for template_id, tpl in PAGE_TEMPLATES.items():
        if template_id in ("title_hero", "title_image", "blank_freeflow"):
            continue
        tags = tpl.get("tags", [])
        if any(_word_match(tag, combined) for tag in tags):
            return template_id

    # Visual diversity fallback: alternate image templates for visual variety.
    # Corporate has no `bullets`; rotate through corporate-safe workhorse IDs.
    middle_position = page_index - 1
    if _is_corp:
        _corp_rotation = [
            "exec_pg_argument",
            "exec_pg_stat_grid",
            "exec_pg_features_2x2",
            "exec_pg_industries_2x2",
        ]
        pick = _corp_rotation[max(0, middle_position) % len(_corp_rotation)]
        logging.info(f"🎯 [AUTO_MATCH_PRINTABLE] Corporate diversity rotation → {pick}")
        return pick
    if middle_position % 3 == 0:
        pick = "image_right" if page_index % 2 == 0 else "image_left"
        logging.info(f"🎯 [AUTO_MATCH_PRINTABLE] Diversity fallback → {pick}")
        return pick

    return "bullets"


def llm_match_template(
    page_title: str,
    page_instruction: str = "",
    page_index: int = 0,
    total_pages: int = 1,
    layout: str = "",
    image_prompt: str = "",
    has_structured_data: bool = False,
    user_id: Optional[str] = None,
    deck_profile: Optional[str] = None,
) -> Optional[str]:
    """
    LLM-based printable-page template matching using a large-tier model.

    ``deck_profile`` filters the candidate catalog. Defaults to
    ``corporate_boardroom`` — only exec_pg_* templates considered.
    """
    import json as _json
    import os as _os
    try:
        from llm_oss import llm_call  # local import to avoid circular import at module load
    except Exception as e:
        logging.warning(f"🎯 [LLM_MATCH_PRINTABLE] llm_oss unavailable, skipping LLM matching: {e}")
        return None
    # Printable stays on GLM-5.1 even though the large tier defaults to
    # deepseek-v4-pro. Pin via PRINTABLE_LLM_MODEL (base_url/api_key still from
    # LLM_LARGE_*).
    _surface_model = (
        _os.getenv("PRINTABLE_LLM_MODEL", "").strip()
        or _os.getenv("PRESENTATION_LLM_MODEL", "").strip()
        or "z-ai/glm-5.1"
    )

    profile_catalog = get_profile_template_catalog(deck_profile)
    profile_key = deck_profile if deck_profile in DECK_PROFILES else DECK_PROFILE_CORPORATE
    profile_label = DECK_PROFILES[profile_key]["label"]
    profile_desc = DECK_PROFILES[profile_key]["description"]
    is_corporate = profile_key in (
        DECK_PROFILE_CORPORATE,
        DECK_PROFILE_CORPORATE_BOARDROOM,
        DECK_PROFILE_CORPORATE_WITH_VISUALS,
    )

    # Build catalog lines with the same signal as presentation:
    #   description / best_for / flags / tags + required_slots cardinality.
    catalog_lines = []
    valid_ids = []
    for tid, t in profile_catalog.items():
        valid_ids.append(tid)
        entry = f"- {tid}: {t.get('description', '')}"
        meta = t.get("metadata", {})
        if meta.get("best_for"):
            entry += f" | Best for: {', '.join(meta['best_for'])}"
        flags = []
        if t.get("has_image"):
            flags.append("HAS_IMAGE")
        if t.get("has_chart"):
            flags.append("HAS_CHART")
        if t.get("has_diagram"):
            flags.append("HAS_DIAGRAM")
        if flags:
            entry += f" [{', '.join(flags)}]"
        req_count = len(t.get("required_slots") or [])
        if req_count:
            entry += f" | required_slots={req_count}"
        tags = meta.get("tags") or t.get("tags") or []
        if tags:
            entry += f" | Tags: {', '.join(tags[:8])}"
        catalog_lines.append(entry)
    catalog_str = "\n".join(catalog_lines)
    valid_ids_set = set(valid_ids)

    pos = "FIRST" if page_index == 0 else (
        "LAST" if page_index == total_pages - 1 else f"MIDDLE ({page_index + 1}/{total_pages})"
    )

    # Normalize layout aliases coming from the outline prompt so the matcher
    # sees the actual catalog IDs (outline prompt may use shorthand like
    # "exec_cover" / "exec_closing" that don't match the *_pg_* suffixed IDs).
    _PG_LAYOUT_ALIASES = {
        "exec_cover": "exec_pg_cover",
        "exec_title": "exec_pg_cover",
        "exec_argument": "exec_pg_argument",
        "exec_stat_grid": "exec_pg_stat_grid",
        "exec_features": "exec_pg_features_2x2",
        "exec_industries": "exec_pg_industries_2x2",
        "exec_sovereignty": "exec_pg_sovereignty_dark",
        "exec_closing": "exec_pg_closing_dark",
    }
    normalized_layout = _PG_LAYOUT_ALIASES.get((layout or "").strip(), layout or "")

    if is_corporate:
        rules_block = """RULES (apply in order — choose ONE template_id that EXISTS in the catalog above):
- FIRST page → exec_pg_cover.
- LAST page → exec_pg_closing_dark.
- 4 KPIs / "by the numbers" / business impact → exec_pg_stat_grid (needs 4 stats — for a single headline metric use big_number).
- 4 capabilities / value props / 2x2 feature grid → exec_pg_features_2x2.
- 4 verticals / use-cases / industries grid → exec_pg_industries_2x2.
- Architecture / security / governance / data residency / trust posture → exec_pg_sovereignty_dark.
- Default body page (one claim + 4-5 bullets) → exec_pg_argument. This is the workhorse — prefer it over generic `bullets`.
- PROCESS / WORKFLOW / LIFECYCLE / PIPELINE / PHASES / step-by-step → process_steps. Overrides image hints.
- HIERARCHY / ORG CHART / TAXONOMY / TREE → org_hierarchy.
- INFOGRAPHIC / VENN / FUNNEL / CYCLE / ANATOMY → infographic_diagram.
- Comparing two options head-to-head → comparison.
- Single hero number → big_number. Three headline stats → stats_highlight.
- Chronological events / roadmap / milestones → timeline.
- Real structured data + data-heavy content → chart_focus / chart_left / chart_right / chart_and_image.
- ONE photo earns its place → title_image / image_left / image_right. Use sparingly — corporate is typography-first.
- Pick from the catalog list above ONLY. Do not invent IDs."""
    else:
        rules_block = """RULES (apply in order — choose ONE template_id that EXISTS in the catalog above):
- FIRST page → a title template (title_hero or title_image).
- LAST page → closing.
- PROCESS / WORKFLOW / LIFECYCLE / PIPELINE / PHASES / step-by-step → process_steps. Overrides image hints.
- HIERARCHY / ORG CHART / TAXONOMY / TREE → org_hierarchy.
- INFOGRAPHIC / VENN / FUNNEL / CYCLE / ANATOMY → infographic_diagram.
- Comparing two options → comparison.
- Key stats / numbers → stats_highlight (three) or big_number (one).
- Real structured data + data-heavy content → chart_focus / chart_left / chart_right / chart_and_image.
- Photo-rich content → image_left / image_right.
- Generic prose body → bullets.
- Pick from the catalog list above ONLY. Do not invent IDs."""

    system_prompt = (
        "You are a document design expert. Pick the single BEST page template "
        f"from a {profile_label.upper()} document profile catalog. {profile_desc} "
        "Return ONLY a minimal JSON object: {\"template_id\": \"<id>\"}. "
        "No reasoning, no prose, no markdown."
    )
    user_prompt = f"""DOCUMENT PROFILE: {profile_label}
{profile_desc}

TEMPLATE CATALOG ({len(valid_ids)} options — pick exactly one ID from this list):
{catalog_str}

PAGE TO MATCH:
- Position: {pos}
- Title: {page_title}
- Outline / content_hint: {page_instruction}
- Layout hint from outline (advisory only — content type takes priority): {normalized_layout or '(none)'}
- Image prompt present: {bool(image_prompt)}
- Structured data available: {has_structured_data}

{rules_block}

Return ONLY this JSON (no other text, no markdown, no reasoning): {{"template_id": "<one_id_from_catalog>"}}"""

    try:
        ai_response = llm_call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=_surface_model,
            user_id=user_id,
            max_tokens=4096,
            temperature=0.0,
            top_p=0.9,
            json_mode=True,
            tier="large",
        )
    except Exception as e:
        logging.warning(f"🎯 [LLM_MATCH_PRINTABLE] LLM call failed: {e}")
        return None

    try:
        raw = (ai_response or "").strip()
        if not raw:
            logging.warning("🎯 [LLM_MATCH_PRINTABLE] Empty response from LLM")
            return None
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            raw = raw[start:end + 1]
        try:
            data = _json.loads(raw)
            template_id = (data.get("template_id") or "").strip()
        except Exception:
            import re as _re
            m = _re.search(r'"template_id"\s*:\s*"([a-zA-Z0-9_]+)"', raw)
            template_id = m.group(1) if m else ""
        # Validate against the PROFILE-FILTERED catalog (not the full library)
        # — same reasoning as presentation: `bullets` is in PAGE_TEMPLATES but
        # not in the corporate profile, so an LLM-returned `bullets` for a
        # corporate document must be rejected so the caller falls back to the
        # keyword matcher and picks `exec_pg_argument` instead.
        if template_id in valid_ids_set:
            logging.info(f"🎯 [LLM_MATCH_PRINTABLE] '{page_title[:60]}' → {template_id} (profile={profile_label})")
            return template_id
        if template_id in PAGE_TEMPLATES:
            logging.warning(
                f"🎯 [LLM_MATCH_PRINTABLE] Returned id '{template_id}' exists but is OUT-OF-PROFILE "
                f"({profile_label}); rejecting so caller falls back to keyword matcher"
            )
            return None
        logging.warning(f"🎯 [LLM_MATCH_PRINTABLE] Returned id '{template_id}' not in catalog; raw={raw[:200]}")
        return None
    except Exception as e:
        logging.warning(f"🎯 [LLM_MATCH_PRINTABLE] JSON parse failed: {e}; raw={(ai_response or '')[:200]}")
        return None


def get_template_matching_prompt(pages: list, profile: Optional[str] = None) -> str:
    """Generate LLM prompt for batch template matching across all pages.

    ``profile`` controls which templates are visible. Defaults to
    ``corporate_boardroom`` — exec_pg_* only.
    """
    profile_key = profile if profile in DECK_PROFILES else DECK_PROFILE_CORPORATE_BOARDROOM
    profile_label = DECK_PROFILES[profile_key]["label"]
    profile_description = DECK_PROFILES[profile_key]["description"]
    catalog = get_profile_template_catalog(profile_key)

    template_catalog = []
    for tid, t in catalog.items():
        meta = t.get("metadata", {})
        entry = f"- {tid}: {t['description']}"
        if meta.get("best_for"):
            entry += f" | Best for: {', '.join(meta['best_for'])}"
        if meta.get("has_image"):
            entry += " | Has image slot"
        if meta.get("has_chart"):
            entry += " | Has chart slot"
        template_catalog.append(entry)

    pages_list = []
    for i, page in enumerate(pages):
        title = page.get("title", page.get("pageTitle", f"Page {i+1}"))
        instruction = page.get("instruction", page.get("description", ""))
        pages_list.append(f"  Page {i+1}: \"{title}\" — {instruction}")

    return f"""You are a document design expert. Match each page to the BEST template from the catalog below.

DOCUMENT PROFILE: {profile_label}
{profile_description}
(Only templates that fit this profile appear in the catalog below — do not invent template IDs.)

TEMPLATE CATALOG:
{chr(10).join(template_catalog)}

PAGES TO MATCH:
{chr(10).join(pages_list)}

EXECUTIVE A4 FAMILY (the DEFAULT for every Citra report — legacy templates are deprecated and hidden):
- FIRST page → `exec_pg_cover` (dark navy cover, two-tone headline, three pillar pills)
- Standard body page with one claim + bullets → `exec_pg_argument` (the workhorse — kicker + action title + subhead + heading + intro paragraph + bullets + optional takeaway)
- Business-impact / KPI / "by the numbers" → `exec_pg_stat_grid` (2x2 stat grid + optional explainer block)
- Capabilities / features in a 2x2 → `exec_pg_features_2x2` (white cards with coloured icon circles)
- Industries / use cases / verticals → `exec_pg_industries_2x2` (vertical coloured side-rules + checkmark bullets)
- Architecture / sovereignty / security / governance → `exec_pg_sovereignty_dark` (dark page, 4 dark cards + light governance panel)
- LAST page / "why buy" / asks → `exec_pg_closing_dark` (dark navy, 2x2 numbered reason cards + cyan CTA strap)

RHYTHM RULES (apply across the document):
- Dark book-ends: first page and last page are dark navy; sovereignty pages can also be dark for emphasis. Everything else is light. Don't fight this.
- Coherent family: once you've started in the exec_pg_* family, do NOT mix with legacy templates on the same document. Pick exec_pg_argument for any body page that doesn't fit a more specific exec_pg_* template.
- Variety within the family: avoid two consecutive `exec_pg_argument` pages if a more specific template fits the content.

Return a JSON array of objects with "page_number" and "template_id" for each page.
Example: [{{"page_number": 1, "template_id": "exec_pg_cover"}}, {{"page_number": 2, "template_id": "exec_pg_argument"}}]

Return ONLY the JSON array, no other text."""
