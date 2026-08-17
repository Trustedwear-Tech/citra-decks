# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: BUSL-1.1
#
# Licensed under the Business Source License 1.1. Non-production use is granted;
# production use requires a commercial licence until the Change Date, after
# which this file converts to Apache-2.0. See LICENSE at the repository root.

"""
Slide Templates - Predefined layouts with fixed slot positions

Each template defines named slots with exact x, y, width, height positions.
AI fills content into slots, positions are FIXED for pixel-perfect rendering.

Canvas: 960×540 (16:9 landscape)

Templates include:
- metadata: tags, best_for, content_type flags for AI matching
- fabric.js properties: shadow, rx/ry, opacity, gradient hints
- Photo/chart/background image slots where appropriate
"""

from typing import Dict, Any, List, Optional
import json
import logging

logger = logging.getLogger(__name__)

CANVAS_WIDTH = 960
CANVAS_HEIGHT = 540

# ==================== Template Definitions ====================

SLIDE_TEMPLATES: Dict[str, Dict[str, Any]] = {

    # ================== TITLE SLIDES ==================

    "title_hero": {
        "id": "title_hero",
        "deprecated": True,
        "name": "Title Hero",
        "description": "Bold centered title with subtitle and decorative accents",
        "category": "title",
        "tags": ["intro", "opening", "cover", "first slide", "welcome"],
        "best_for": "Opening slides, presentation covers, section openers",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 160, "width": 580, "height": 110,
                "type": "text", "textType": "title",
                "fontSize": 52, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 50, "y": 280, "width": 520, "height": 60,
                "type": "text", "textType": "subtitle",
                "fontSize": 26, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
            "tagline": {
                "x": 50, "y": 350, "width": 480, "height": 35,
                "type": "text", "textType": "body",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7,
                "zIndex": 55,
            },
            "accent_image": {
                "x": 660, "y": 150, "width": 260, "height": 280,
                "type": "image_placeholder",
                "rx": 14,
                "zIndex": 20,
                "shadow": {"color": "rgba(0,0,0,0.12)", "blur": 14, "offsetX": 0, "offsetY": 4},
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "circle", "x": 40, "y": 400, "width": 110, "height": 110, "useAccentColor": True, "opacity": 0.25, "zIndex": 5, "shadow": {"color": "rgba(0,0,0,0.1)", "blur": 15, "offsetX": 0, "offsetY": 4}},
            {"type": "shape", "shapeType": "circle", "x": 810, "y": 370, "width": 130, "height": 130, "useAccentColor": True, "opacity": 0.18, "zIndex": 5},
            {"type": "shape", "shapeType": "rectangle", "x": 380, "y": 440, "width": 200, "height": 4, "useAccentColor": True, "opacity": 0.4, "rx": 2, "zIndex": 6},
        ],
        "required_slots": ["title"],
        "optional_slots": ["subtitle", "tagline", "accent_image"],
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
                "x": 50, "y": 30, "width": 860, "height": 70,
                "type": "text", "textType": "title",
                "fontSize": 42, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 120, "y": 105, "width": 720, "height": 40,
                "type": "text", "textType": "subtitle",
                "fontSize": 22, "fontWeight": "normal", "textAlign": "center",
                "zIndex": 60,
            },
            "tagline": {
                "x": 140, "y": 150, "width": 680, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "normal", "textAlign": "center",
                "opacity": 0.7,
                "zIndex": 55,
            },
            "image": {
                "x": 180, "y": 195, "width": 600, "height": 320,
                "type": "image_placeholder",
                "zIndex": 20,
                "rx": 16,
                "shadow": {"color": "rgba(0,0,0,0.15)", "blur": 20, "offsetX": 0, "offsetY": 6},
            },
        },
        "decorations": [],
        "required_slots": ["title", "image"],
        "optional_slots": ["subtitle", "tagline"],
    },

    "title_split": {
        "id": "title_split",
        "deprecated": True,
        "name": "Title Split",
        "description": "Title on left with full-height image on right",
        "category": "title",
        "tags": ["intro", "cover", "split", "visual", "photo", "modern"],
        "best_for": "Modern title slides with strong visual impact",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 120, "width": 410, "height": 120,
                "type": "text", "textType": "title",
                "fontSize": 46, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 50, "y": 260, "width": 410, "height": 60,
                "type": "text", "textType": "subtitle",
                "fontSize": 22, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
            "tagline": {
                "x": 50, "y": 340, "width": 410, "height": 35,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7,
                "zIndex": 55,
            },
            "image": {
                "x": 500, "y": 0, "width": 460, "height": 540,
                "type": "image_placeholder",
                "zIndex": 15,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 410, "width": 120, "height": 4, "useAccentColor": True, "rx": 2, "zIndex": 10},
        ],
        "required_slots": ["title", "image"],
        "optional_slots": ["subtitle", "tagline"],
    },

    # ================== CONTENT SLIDES ==================

    "bullets": {
        "id": "bullets",
        "deprecated": True,
        "name": "Bullet Points",
        "description": "Title with bullet list — classic content slide",
        "category": "content",
        "tags": ["list", "points", "key points", "overview", "summary", "text"],
        "best_for": "Key points, agendas, feature lists, any list-based content",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 35, "width": 860, "height": 65,
                "type": "text", "textType": "title",
                "fontSize": 38, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 50, "y": 108, "width": 700, "height": 30,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7,
                "zIndex": 55,
            },
            "bullets": {
                "x": 70, "y": 155, "width": 560, "height": 310,
                "type": "text", "textType": "body",
                "fontSize": 21, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.6,
                "zIndex": 60,
            },
            "accent_image": {
                "x": 660, "y": 160, "width": 260, "height": 260,
                "type": "image_placeholder",
                "rx": 12,
                "zIndex": 20,
                "shadow": {"color": "rgba(0,0,0,0.12)", "blur": 14, "offsetX": 0, "offsetY": 4},
            },
            "key_takeaway": {
                "x": 70, "y": 480, "width": 820, "height": 35,
                "type": "text", "textType": "body",
                "fontSize": 16, "fontWeight": "bold", "textAlign": "left",
                "opacity": 0.8,
                "zIndex": 55,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 145, "width": 860, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "bullets", "accent_image"],
        "optional_slots": ["subtitle", "key_takeaway"],
    },

    "bullets_with_image": {
        "id": "bullets_with_image",
        "deprecated": True,
        "name": "Bullets + Visual",
        "description": "Bullet points on left with supporting visual (image or chart) on right",
        "category": "content",
        "tags": ["list", "points", "photo", "visual", "text and image", "chart", "data"],
        "best_for": "Feature lists with visual support, product highlights, data-backed points",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 35, "width": 860, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "bullets": {
                "x": 60, "y": 130, "width": 420, "height": 370,
                "type": "text", "textType": "body",
                "fontSize": 19, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.6,
                "zIndex": 60,
            },
            "visual": {
                "x": 510, "y": 120, "width": 400, "height": 380,
                "type": "visual",
                "zIndex": 20,
                "rx": 12,
                "shadow": {"color": "rgba(0,0,0,0.12)", "blur": 16, "offsetX": 0, "offsetY": 4},
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 103, "width": 860, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "bullets", "visual"],
        "optional_slots": [],
    },

    "two_columns": {
        "id": "two_columns",
        "deprecated": True,
        "name": "Two Columns",
        "description": "Side-by-side comparison or dual content areas",
        "category": "content",
        "tags": ["comparison", "two column", "side by side", "pros cons", "dual", "versus"],
        "best_for": "Comparing two topics, pros/cons, dual content areas",
        "has_image": False, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 860, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 40, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            # Left column - icon at y=150, height=56, bottom at y=206
            "left_icon": {
                "x": 70, "y": 150, "width": 56, "height": 56,
                "type": "icon", "size": 56,
                "zIndex": 35,
            },
            "left_title": {
                "x": 140, "y": 155, "width": 310, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 22, "fontWeight": "bold", "textAlign": "left",
                "lineHeight": 1.2,
                "zIndex": 60,
            },
            "left_content": {
                "x": 70, "y": 250, "width": 380, "height": 230,
                "type": "text", "textType": "body",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            # Right column
            "right_icon": {
                "x": 510, "y": 150, "width": 56, "height": 56,
                "type": "icon", "size": 56,
                "zIndex": 35,
            },
            "right_title": {
                "x": 580, "y": 155, "width": 310, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 22, "fontWeight": "bold", "textAlign": "left",
                "lineHeight": 1.2,
                "zIndex": 60,
            },
            "right_content": {
                "x": 510, "y": 250, "width": 380, "height": 230,
                "type": "text", "textType": "body",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 105, "width": 860, "height": 3, "useAccentColor": True, "zIndex": 10},
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
        "tags": ["cards", "features", "three", "grid", "highlights", "benefits"],
        "best_for": "Feature highlights, key benefits, service offerings with 3 items",
        "has_image": False, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 40, "width": 860, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 40, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            # Card 1 - icon at y=145, height=64, bottom at y=209
            "card1_icon": {
                "x": 150, "y": 145, "width": 64, "height": 64,
                "type": "icon", "size": 64,
                "zIndex": 35,
            },
            "card1_title": {
                "x": 70, "y": 235, "width": 240, "height": 40,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "center",
                "lineHeight": 1.2,
                "zIndex": 60,
            },
            "card1_desc": {
                "x": 70, "y": 300, "width": 240, "height": 170,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "normal", "textAlign": "center",
                "lineHeight": 1.3,
                "zIndex": 60,
            },
            # Card 2
            "card2_icon": {
                "x": 440, "y": 145, "width": 64, "height": 64,
                "type": "icon", "size": 64,
                "zIndex": 35,
            },
            "card2_title": {
                "x": 360, "y": 235, "width": 240, "height": 40,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "center",
                "lineHeight": 1.2,
                "zIndex": 60,
            },
            "card2_desc": {
                "x": 360, "y": 300, "width": 240, "height": 170,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "normal", "textAlign": "center",
                "lineHeight": 1.3,
                "zIndex": 60,
            },
            # Card 3
            "card3_icon": {
                "x": 730, "y": 145, "width": 64, "height": 64,
                "type": "icon", "size": 64,
                "zIndex": 35,
            },
            "card3_title": {
                "x": 650, "y": 235, "width": 240, "height": 40,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "center",
                "lineHeight": 1.2,
                "zIndex": 60,
            },
            "card3_desc": {
                "x": 650, "y": 300, "width": 240, "height": 170,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "normal", "textAlign": "center",
                "lineHeight": 1.3,
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["title", "card1_title", "card1_desc", "card2_title", "card2_desc", "card3_title", "card3_desc"],
        "optional_slots": ["card1_icon", "card2_icon", "card3_icon"],
    },

    "image_left": {
        "id": "image_left",
        "deprecated": True,
        "name": "Image Left",
        "description": "Large visual (image or chart) on left with text content on right",
        "category": "media",
        "tags": ["image", "photo", "visual", "split", "media", "picture", "chart", "data"],
        "best_for": "Visual content with explanatory text, product showcases, data with commentary",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 860, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 50, "y": 82, "width": 500, "height": 30,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7, "zIndex": 55,
            },
            "visual": {
                "x": 50, "y": 120, "width": 420, "height": 380,
                "type": "visual",
                "zIndex": 20,
                "rx": 12,
                "shadow": {"color": "rgba(0,0,0,0.12)", "blur": 16, "offsetX": 0, "offsetY": 4},
            },
            "content_title": {
                "x": 500, "y": 130, "width": 410, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 26, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "content": {
                "x": 500, "y": 195, "width": 410, "height": 290,
                "type": "text", "textType": "body",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 490, "y": 130, "width": 4, "height": 350, "useAccentColor": True, "opacity": 0.3, "rx": 2, "zIndex": 6},
        ],
        "required_slots": ["title", "content", "visual"],
        "optional_slots": ["content_title", "subtitle"],
    },

    "image_right": {
        "id": "image_right",
        "deprecated": True,
        "name": "Image Right",
        "description": "Text content on left with large visual (image or chart) on right",
        "category": "media",
        "tags": ["image", "photo", "visual", "split", "media", "picture", "chart", "data"],
        "best_for": "Explanatory text with visual support, data with commentary, tutorials",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 860, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 50, "y": 82, "width": 500, "height": 30,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7, "zIndex": 55,
            },
            "content_title": {
                "x": 50, "y": 130, "width": 410, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 26, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "content": {
                "x": 50, "y": 195, "width": 410, "height": 290,
                "type": "text", "textType": "body",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
            "visual": {
                "x": 490, "y": 120, "width": 420, "height": 380,
                "type": "visual",
                "zIndex": 20,
                "rx": 12,
                "shadow": {"color": "rgba(0,0,0,0.12)", "blur": 16, "offsetX": 0, "offsetY": 4},
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 470, "y": 130, "width": 4, "height": 350, "useAccentColor": True, "opacity": 0.3, "rx": 2, "zIndex": 6},
        ],
        "required_slots": ["title", "content", "visual"],
        "optional_slots": ["content_title", "subtitle"],
    },

    # ================== SVG DIAGRAM TEMPLATES (full-slide vector diagrams) ==================
    # `svg_diagram` slots tell the LLM to emit a full inline SVG sized to the slot.
    # The UI renders these via fabric.loadSVGFromString (same path used for icons).

    "process_steps": {
        "id": "process_steps",
        "deprecated": True,
        "name": "Process Flow Diagram",
        "description": "Process flow slide: short intro, side-by-side diagram (left SVG, right foreground image), and a takeaway line below",
        "category": "diagram",
        "tags": ["process", "flow", "workflow", "steps", "phases", "lifecycle", "pipeline", "diagram", "how to", "methodology", "process diagram", "protein synthesis"],
        "best_for": "Step-by-step processes, lifecycles, scientific/biological/engineering flows, multi-stage pipelines",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 28, "width": 860, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 30, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "intro": {
                "x": 50, "y": 82, "width": 860, "height": 42,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            "diagram": {
                "x": 20, "y": 130, "width": 450, "height": 320,
                "type": "svg_diagram",
                "diagramKind": "process",
                "zIndex": 50,
            },
            "image": {
                "x": 490, "y": 130, "width": 450, "height": 320,
                "type": "image_placeholder",
                "zIndex": 20,
            },
            "takeaway": {
                "x": 50, "y": 460, "width": 860, "height": 60,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["title", "intro", "diagram", "image"],
        "optional_slots": ["takeaway"],
    },

    "org_hierarchy": {
        "id": "org_hierarchy",
        "deprecated": True,
        "name": "Org Hierarchy Diagram",
        "description": "Hierarchy slide: optional intro, side-by-side diagram (left SVG, right foreground image), and a short caption summarizing the structure",
        "category": "diagram",
        "tags": ["hierarchy", "org chart", "organization", "team", "reporting", "structure", "tree", "taxonomy", "departments", "diagram"],
        "best_for": "Org charts, team structures, reporting lines, taxonomies, decision trees",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 860, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "intro": {
                "x": 50, "y": 82, "width": 860, "height": 38,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            "diagram": {
                "x": 30, "y": 128, "width": 440, "height": 340,
                "type": "svg_diagram",
                "diagramKind": "hierarchy",
                "zIndex": 50,
            },
            "image": {
                "x": 490, "y": 128, "width": 440, "height": 340,
                "type": "image_placeholder",
                "zIndex": 20,
            },
            "caption": {
                "x": 50, "y": 478, "width": 860, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "center",
                "lineHeight": 1.3,
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["title", "diagram", "image"],
        "optional_slots": ["intro", "caption"],
    },

    "infographic_diagram": {
        "id": "infographic_diagram",
        "deprecated": True,
        "name": "Infographic Diagram",
        "description": "Infographic slide: short intro, side-by-side diagram (left SVG cycle/venn/funnel/anatomy, right foreground image), and a takeaway line below",
        "category": "diagram",
        "tags": ["infographic", "diagram", "visual breakdown", "concept", "anatomy", "cycle", "venn", "funnel", "system"],
        "best_for": "Concept diagrams, anatomies, cycles, venn diagrams, funnels, system overviews",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 25, "width": 860, "height": 45,
                "type": "text", "textType": "title",
                "fontSize": 28, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "intro": {
                "x": 50, "y": 75, "width": 860, "height": 38,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
            "diagram": {
                "x": 20, "y": 120, "width": 450, "height": 340,
                "type": "svg_diagram",
                "diagramKind": "infographic",
                "zIndex": 50,
            },
            "image": {
                "x": 490, "y": 120, "width": 450, "height": 340,
                "type": "image_placeholder",
                "zIndex": 20,
            },
            "takeaway": {
                "x": 50, "y": 470, "width": 860, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.4,
                "zIndex": 60,
            },
        },
        "decorations": [],
        "required_slots": ["title", "intro", "diagram", "image"],
        "optional_slots": ["takeaway"],
    },

    "quote": {
        "id": "quote",
        "deprecated": True,
        "name": "Quote",
        "description": "Highlighted quote with attribution and context",
        "category": "content",
        "tags": ["quote", "testimonial", "citation", "saying", "inspiration"],
        "best_for": "Testimonials, inspirational quotes, key takeaways, notable statements",
        "has_image": True, "has_chart": False,
        "suggest_background_image": True,
        "slots": {
            "title": {
                "x": 100, "y": 40, "width": 760, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 30, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "quote_text": {
                "x": 100, "y": 150, "width": 760, "height": 180,
                "type": "text", "textType": "body",
                "fontSize": 32, "fontWeight": "normal", "textAlign": "center",
                "fontStyle": "italic",
                "zIndex": 60,
            },
            "attribution": {
                "x": 100, "y": 350, "width": 760, "height": 40,
                "type": "text", "textType": "subtitle",
                "fontSize": 20, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "context_text": {
                "x": 150, "y": 400, "width": 660, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "normal", "textAlign": "center",
                "opacity": 0.6, "zIndex": 55,
            },
            "accent_image": {
                "x": 50, "y": 400, "width": 140, "height": 110,
                "type": "image_placeholder",
                "rx": 10,
                "zIndex": 20,
                "shadow": {"color": "rgba(0,0,0,0.15)", "blur": 12, "offsetX": 0, "offsetY": 3},
            },
        },
        "decorations": [
            {"type": "text", "content": '"', "x": 50, "y": 90, "width": 80, "height": 80, "fontSize": 120, "fontWeight": "bold", "textAlign": "left", "useAccentColor": True, "opacity": 0.3, "zIndex": 5},
            {"type": "text", "content": '"', "x": 830, "y": 270, "width": 80, "height": 80, "fontSize": 120, "fontWeight": "bold", "textAlign": "right", "useAccentColor": True, "opacity": 0.3, "zIndex": 5},
        ],
        "required_slots": ["quote_text"],
        "optional_slots": ["title", "attribution", "context_text", "accent_image"],
    },

    # -------------------- Advanced Layouts --------------------
    "modern_geometric": {
        "id": "modern_geometric",
        "deprecated": True,
        "name": "Modern Geometric",
        "description": "Dynamic layout with abstract shapes and offset content",
        "category": "advanced",
        "tags": ["modern", "creative", "abstract", "dynamic", "geometric", "artistic"],
        "best_for": "Creative content, standout slides, artistic layouts, bold statements",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 60, "y": 50, "width": 400, "height": 70,
                "type": "text", "textType": "title",
                "fontSize": 42, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 60, "y": 125, "width": 400, "height": 35,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "bold", "textAlign": "left",
                "opacity": 0.8, "zIndex": 58,
            },
            "content": {
                "x": 60, "y": 170, "width": 400, "height": 260,
                "type": "text", "textType": "body",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
            "detail": {
                "x": 60, "y": 445, "width": 400, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.6, "zIndex": 55,
            },
            "visual": {
                "x": 500, "y": 60, "width": 400, "height": 420,
                "type": "visual",
                "zIndex": 20,
            }
        },
        "decorations": [
            {"type": "shape", "shapeType": "triangle", "x": 800, "y": -50, "width": 200, "height": 200, "useAccentColor": True, "opacity": 0.2, "zIndex": 5},
            {"type": "shape", "shapeType": "circle", "x": 450, "y": 450, "width": 100, "height": 100, "useAccentColor": True, "opacity": 0.1, "zIndex": 5},
            {"type": "shape", "shapeType": "rectangle", "x": 0, "y": 0, "width": 20, "height": 540, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "content", "visual"],
        "optional_slots": ["subtitle", "detail"],
    },

    "data_dashboard": {
        "id": "data_dashboard",
        "deprecated": True,
        "name": "Data Dashboard",
        "description": "Four-quadrant layout for metrics and charts",
        "category": "data",
        "tags": ["data", "dashboard", "metrics", "analytics", "stats", "chart", "KPI"],
        "best_for": "Data presentations, KPI summaries, analytics overviews",
        "has_image": False, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 860, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            # Top Left - Metric 1 (value + label)
            "metric1_value": {
                "x": 70, "y": 115, "width": 180, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "metric1_label": {
                "x": 70, "y": 170, "width": 180, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "center",
                "zIndex": 60,
            },
            # Top Right - Metric 2
            "metric2_value": {
                "x": 280, "y": 115, "width": 180, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "metric2_label": {
                "x": 280, "y": 170, "width": 180, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "center",
                "zIndex": 60,
            },
            # Bottom Row - Larger stats with descriptions
            "stat1_value": {
                "x": 70, "y": 240, "width": 180, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "stat1_label": {
                "x": 70, "y": 295, "width": 180, "height": 60,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "center",
                "lineHeight": 1.3,
                "zIndex": 60,
            },
            "stat2_value": {
                "x": 280, "y": 240, "width": 180, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 32, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "stat2_label": {
                "x": 280, "y": 295, "width": 180, "height": 60,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "center",
                "lineHeight": 1.3,
                "zIndex": 60,
            },
            # Right side - Charts (top and bottom)
            "chart_1": {
                "x": 500, "y": 100, "width": 410, "height": 180,
                "type": "chart",
                "zIndex": 50,
            },
            "chart_2": {
                "x": 500, "y": 295, "width": 410, "height": 180,
                "type": "chart",
                "zIndex": 50,
            },
        },
        "decorations": [
            # Title underline
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 85, "width": 860, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "metric1_value", "metric1_label"],
        "optional_slots": ["metric2_value", "metric2_label", "stat1_value", "stat1_label", "stat2_value", "stat2_label", "chart_1", "chart_2"],
    },

    # ================== NEW TEMPLATES ==================

    "full_bleed_image": {
        "id": "full_bleed_image",
        "deprecated": True,
        "name": "Full Bleed Image",
        "description": "Full-screen background image with text overlay at bottom",
        "category": "media",
        "tags": ["visual", "photo", "full image", "background", "cinematic", "impactful"],
        "best_for": "Visual impact slides, chapter openers, mood-setting slides",
        "has_image": True, "has_chart": False,
        "suggest_background_image": True,
        "slots": {
            "image": {
                "x": 0, "y": 0, "width": 960, "height": 540,
                "type": "image_placeholder",
                "zIndex": 5,
            },
            "title": {
                "x": 60, "y": 340, "width": 840, "height": 80,
                "type": "text", "textType": "title",
                "fontSize": 46, "fontWeight": "bold", "textAlign": "left",
                "fill": "#ffffff",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 60, "y": 420, "width": 700, "height": 40,
                "type": "text", "textType": "subtitle",
                "fontSize": 22, "fontWeight": "normal", "textAlign": "left",
                "fill": "#ffffffcc",
                "zIndex": 60,
            },
            "tagline": {
                "x": 60, "y": 470, "width": 500, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "fill": "#ffffff99",
                "zIndex": 55,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 0, "y": 270, "width": 960, "height": 270, "fill": "rgba(0,0,0,0.5)", "zIndex": 10},
        ],
        "required_slots": ["title", "image"],
        "optional_slots": ["subtitle", "tagline"],
    },

    "four_cards": {
        "id": "four_cards",
        "deprecated": True,
        "name": "Four Cards",
        "description": "Four feature cards with icons for broader overviews",
        "category": "content",
        "tags": ["cards", "four", "features", "grid", "4 column", "overview"],
        "best_for": "Feature overviews, service listings, benefit highlights with 4 items",
        "has_image": False, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 860, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "card1_icon": {"x": 118, "y": 135, "width": 44, "height": 44, "type": "icon", "size": 44, "zIndex": 35},
            "card1_title": {"x": 65, "y": 200, "width": 170, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 17, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "card1_desc": {"x": 60, "y": 250, "width": 180, "height": 220, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
            "card2_icon": {"x": 338, "y": 135, "width": 44, "height": 44, "type": "icon", "size": 44, "zIndex": 35},
            "card2_title": {"x": 285, "y": 200, "width": 170, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 17, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "card2_desc": {"x": 280, "y": 250, "width": 180, "height": 220, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
            "card3_icon": {"x": 558, "y": 135, "width": 44, "height": 44, "type": "icon", "size": 44, "zIndex": 35},
            "card3_title": {"x": 505, "y": 200, "width": 170, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 17, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "card3_desc": {"x": 500, "y": 250, "width": 180, "height": 220, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
            "card4_icon": {"x": 778, "y": 135, "width": 44, "height": 44, "type": "icon", "size": 44, "zIndex": 35},
            "card4_title": {"x": 725, "y": 200, "width": 170, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 17, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "card4_desc": {"x": 720, "y": 250, "width": 180, "height": 220, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
        },
        "decorations": [],
        "required_slots": ["title", "card1_title", "card1_desc", "card2_title", "card2_desc", "card3_title", "card3_desc", "card4_title", "card4_desc"],
        "optional_slots": ["card1_icon", "card2_icon", "card3_icon", "card4_icon"],
    },

    "stats_highlight": {
        "id": "stats_highlight",
        "deprecated": True,
        "name": "Stats Highlight",
        "description": "Three prominent statistics with labels and descriptions. NOTE: stat_value slots must contain ONLY a short number/symbol (e.g. '100+', '3B', '29%') — NEVER words. Put descriptive words in stat_label. Stat values, labels, and descriptions sit on WHITE cards — always use DARK/BLACK text colors (#111827 or similar) for all text inside the cards, never white or light colors.",
        "category": "data",
        "tags": ["stats", "numbers", "metrics", "highlights", "KPI", "achievements"],
        "best_for": "Key metrics, achievements, impact numbers, KPI highlights",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 35, "width": 700, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "stat1_value": {
                "x": 40, "y": 170, "width": 210, "height": 80,
                "type": "text", "textType": "title",
                "fontSize": 56, "fontWeight": "bold", "textAlign": "center",
                "fill": "#111827",
                "zIndex": 60,
            },
            "stat1_label": {
                "x": 40, "y": 260, "width": 210, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "center",
                "fill": "#111827",
                "zIndex": 60,
            },
            "stat1_desc": {
                "x": 45, "y": 315, "width": 200, "height": 100,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "center",
                "fill": "#6b7280",
                "zIndex": 55,
            },
            "stat2_value": {
                "x": 270, "y": 170, "width": 210, "height": 80,
                "type": "text", "textType": "title",
                "fontSize": 56, "fontWeight": "bold", "textAlign": "center",
                "fill": "#111827",
                "zIndex": 60,
            },
            "stat2_label": {
                "x": 270, "y": 260, "width": 210, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "center",
                "fill": "#111827",
                "zIndex": 60,
            },
            "stat2_desc": {
                "x": 275, "y": 315, "width": 200, "height": 100,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "center",
                "fill": "#6b7280",
                "zIndex": 55,
            },
            "stat3_value": {
                "x": 500, "y": 170, "width": 210, "height": 80,
                "type": "text", "textType": "title",
                "fontSize": 56, "fontWeight": "bold", "textAlign": "center",
                "fill": "#111827",
                "zIndex": 60,
            },
            "stat3_label": {
                "x": 500, "y": 260, "width": 210, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "center",
                "fill": "#111827",
                "zIndex": 60,
            },
            "stat3_desc": {
                "x": 505, "y": 315, "width": 200, "height": 100,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "center",
                "fill": "#6b7280",
                "zIndex": 55,
            },
            "accent_image": {
                "x": 730, "y": 130, "width": 200, "height": 290,
                "type": "image_placeholder",
                "rx": 12,
                "zIndex": 20,
                "shadow": {"color": "rgba(0,0,0,0.10)", "blur": 12, "offsetX": 0, "offsetY": 3},
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 100, "width": 860, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "stat1_value", "stat1_label", "stat2_value", "stat2_label", "stat3_value", "stat3_label"],
        "optional_slots": ["stat1_desc", "stat2_desc", "stat3_desc", "accent_image"],
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
            "metric": {
                "x": 100, "y": 100, "width": 760, "height": 130,
                "type": "text", "textType": "title",
                "fontSize": 96, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "label": {
                "x": 80, "y": 250, "width": 540, "height": 60,
                "type": "text", "textType": "subtitle",
                "fontSize": 30, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "context": {
                "x": 80, "y": 330, "width": 480, "height": 80,
                "type": "text", "textType": "body",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.8, "zIndex": 55,
            },
            "accent_image": {
                "x": 690, "y": 240, "width": 230, "height": 220,
                "type": "image_placeholder",
                "rx": 12,
                "zIndex": 20,
                "shadow": {"color": "rgba(0,0,0,0.15)", "blur": 14, "offsetX": 0, "offsetY": 4},
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "circle", "x": 60, "y": 380, "width": 80, "height": 80, "useAccentColor": True, "opacity": 0.15, "zIndex": 5},
            {"type": "shape", "shapeType": "circle", "x": 820, "y": 50, "width": 100, "height": 100, "useAccentColor": True, "opacity": 0.12, "zIndex": 5},
        ],
        "required_slots": ["metric", "label"],
        "optional_slots": ["context", "accent_image"],
    },

    "chart_focus": {
        "id": "chart_focus",
        "deprecated": True,
        "name": "Chart Focus",
        "description": "Large chart taking most of the slide with title and insights",
        "category": "data",
        "tags": ["chart", "graph", "data", "visualization", "bar chart", "line chart", "pie chart"],
        "best_for": "Data visualization, trend analysis, chart-focused presentations",
        "has_image": False, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 640, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "key_insight": {
                "x": 700, "y": 35, "width": 250, "height": 45,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "bold", "textAlign": "right",
                "opacity": 0.8, "zIndex": 55,
            },
            "description": {
                "x": 50, "y": 90, "width": 500, "height": 35,
                "type": "text", "textType": "body",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7, "zIndex": 55,
            },
            "chart": {
                "x": 50, "y": 140, "width": 860, "height": 340,
                "type": "chart",
                "zIndex": 50,
            },
            "source_note": {
                "x": 50, "y": 490, "width": 860, "height": 25,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.5, "zIndex": 50,
            },
        },
        "decorations": [],
        "required_slots": ["title", "chart"],
        "optional_slots": ["description", "key_insight", "source_note"],
    },

    "chart_left": {
        "id": "chart_left",
        "deprecated": True,
        "name": "Chart Left",
        "description": "Visual (chart or image) on left with text content on right",
        "category": "data",
        "tags": ["chart", "graph", "data", "split", "visualization", "analysis", "image"],
        "best_for": "Data visualization with explanatory text, trend analysis with commentary",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 860, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "visual": {
                "x": 50, "y": 110, "width": 420, "height": 380,
                "type": "visual",
                "zIndex": 50,
            },
            "content_title": {
                "x": 500, "y": 120, "width": 410, "height": 45,
                "type": "text", "textType": "subtitle",
                "fontSize": 24, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "content": {
                "x": 500, "y": 180, "width": 410, "height": 250,
                "type": "text", "textType": "body",
                "fontSize": 17, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "key_insight": {
                "x": 500, "y": 445, "width": 410, "height": 40,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "bold", "textAlign": "left",
                "opacity": 0.7, "zIndex": 55,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 490, "y": 120, "width": 4, "height": 360, "useAccentColor": True, "opacity": 0.3, "rx": 2, "zIndex": 6},
        ],
        "required_slots": ["title", "visual", "content"],
        "optional_slots": ["content_title", "key_insight"],
    },

    "chart_right": {
        "id": "chart_right",
        "deprecated": True,
        "name": "Chart Right",
        "description": "Text content on left with visual (chart or image) on right",
        "category": "data",
        "tags": ["chart", "graph", "data", "split", "visualization", "analysis", "image"],
        "best_for": "Commentary with supporting data visualization, analysis presentations",
        "has_image": True, "has_chart": True,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 860, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "content_title": {
                "x": 50, "y": 120, "width": 410, "height": 45,
                "type": "text", "textType": "subtitle",
                "fontSize": 24, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "content": {
                "x": 50, "y": 180, "width": 410, "height": 250,
                "type": "text", "textType": "body",
                "fontSize": 17, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5,
                "zIndex": 60,
            },
            "visual": {
                "x": 490, "y": 110, "width": 420, "height": 380,
                "type": "visual",
                "zIndex": 50,
            },
            "key_insight": {
                "x": 50, "y": 445, "width": 410, "height": 40,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "bold", "textAlign": "left",
                "opacity": 0.7, "zIndex": 55,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 470, "y": 100, "width": 4, "height": 400, "useAccentColor": True, "opacity": 0.3, "rx": 2, "zIndex": 6},
        ],
        "required_slots": ["title", "visual", "content"],
        "optional_slots": ["content_title", "key_insight"],
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
                "x": 50, "y": 25, "width": 650, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 34, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 50, "y": 78, "width": 500, "height": 30,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7, "zIndex": 55,
            },
            "chart": {
                "x": 50, "y": 120, "width": 420, "height": 320,
                "type": "chart",
                "zIndex": 50,
            },
            "image": {
                "x": 490, "y": 120, "width": 420, "height": 320,
                "type": "image_placeholder",
                "zIndex": 20,
                "rx": 12,
                "shadow": {"color": "rgba(0,0,0,0.1)", "blur": 14, "offsetX": 0, "offsetY": 4},
            },
            "insight": {
                "x": 50, "y": 455, "width": 560, "height": 40,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "bold", "textAlign": "left",
                "opacity": 0.85, "zIndex": 55,
            },
            "caption": {
                "x": 630, "y": 455, "width": 280, "height": 40,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "right",
                "opacity": 0.6, "zIndex": 55,
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 110, "width": 860, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "chart", "image"],
        "optional_slots": ["subtitle", "insight", "caption"],
    },

    "comparison": {
        "id": "comparison",
        "deprecated": True,
        "name": "Comparison",
        "description": "Side-by-side comparison with distinct headers and content",
        "category": "content",
        "tags": ["compare", "versus", "vs", "pros cons", "before after", "option"],
        "best_for": "Product comparisons, before/after, option evaluation, pros/cons",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 690, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "left_header": {
                "x": 60, "y": 120, "width": 400, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 24, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "left_content": {
                "x": 70, "y": 185, "width": 380, "height": 310,
                "type": "text", "textType": "body",
                "fontSize": 17, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5, "zIndex": 60,
            },
            "right_header": {
                "x": 500, "y": 120, "width": 400, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 24, "fontWeight": "bold", "textAlign": "center",
                "zIndex": 60,
            },
            "right_content": {
                "x": 510, "y": 185, "width": 380, "height": 310,
                "type": "text", "textType": "body",
                "fontSize": 17, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5, "zIndex": 60,
            },
            "accent_image": {
                "x": 770, "y": 25, "width": 160, "height": 80,
                "type": "image_placeholder",
                "rx": 10,
                "zIndex": 20,
                "shadow": {"color": "rgba(0,0,0,0.10)", "blur": 10, "offsetX": 0, "offsetY": 3},
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 95, "width": 860, "height": 3, "useAccentColor": True, "zIndex": 10},
        ],
        "required_slots": ["title", "left_header", "left_content", "right_header", "right_content"],
        "optional_slots": ["accent_image"],
    },

    "timeline": {
        "id": "timeline",
        "deprecated": True,
        "name": "Timeline",
        "description": "Horizontal timeline with 4 events and descriptions",
        "category": "content",
        "tags": ["timeline", "history", "milestones", "events", "chronological", "journey", "roadmap"],
        "best_for": "Project timelines, company history, milestones, roadmaps",
        "has_image": True, "has_chart": False,
        "slots": {
            "title": {
                "x": 50, "y": 30, "width": 700, "height": 55,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "event1_date": {"x": 50, "y": 135, "width": 180, "height": 30, "type": "text", "textType": "subtitle", "fontSize": 16, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "event1_title": {"x": 50, "y": 230, "width": 180, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 17, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "event1_desc": {"x": 50, "y": 280, "width": 180, "height": 200, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
            "event2_date": {"x": 260, "y": 135, "width": 180, "height": 30, "type": "text", "textType": "subtitle", "fontSize": 16, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "event2_title": {"x": 260, "y": 230, "width": 180, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 17, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "event2_desc": {"x": 260, "y": 280, "width": 180, "height": 200, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
            "event3_date": {"x": 470, "y": 135, "width": 180, "height": 30, "type": "text", "textType": "subtitle", "fontSize": 16, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "event3_title": {"x": 470, "y": 230, "width": 180, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 17, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "event3_desc": {"x": 470, "y": 280, "width": 180, "height": 200, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
            "event4_date": {"x": 680, "y": 135, "width": 180, "height": 30, "type": "text", "textType": "subtitle", "fontSize": 16, "fontWeight": "bold", "textAlign": "center", "zIndex": 60},
            "event4_title": {"x": 680, "y": 230, "width": 180, "height": 40, "type": "text", "textType": "subtitle", "fontSize": 17, "fontWeight": "bold", "textAlign": "center", "lineHeight": 1.2, "zIndex": 60},
            "event4_desc": {"x": 680, "y": 280, "width": 180, "height": 200, "type": "text", "textType": "body", "fontSize": 13, "fontWeight": "normal", "textAlign": "center", "lineHeight": 1.3, "zIndex": 60},
            "accent_image": {"x": 790, "y": 25, "width": 140, "height": 85, "type": "image_placeholder", "rx": 10, "zIndex": 20, "shadow": {"color": "rgba(0,0,0,0.10)", "blur": 10, "offsetX": 0, "offsetY": 3}},
        },
        "decorations": [
            # Timeline line
            {"type": "shape", "shapeType": "rectangle", "x": 50, "y": 190, "width": 860, "height": 4, "useAccentColor": True, "opacity": 0.4, "zIndex": 10},
            # Timeline dots
            {"type": "shape", "shapeType": "circle", "x": 126, "y": 178, "width": 28, "height": 28, "useAccentColor": True, "zIndex": 15},
            {"type": "shape", "shapeType": "circle", "x": 336, "y": 178, "width": 28, "height": 28, "useAccentColor": True, "zIndex": 15},
            {"type": "shape", "shapeType": "circle", "x": 546, "y": 178, "width": 28, "height": 28, "useAccentColor": True, "zIndex": 15},
            {"type": "shape", "shapeType": "circle", "x": 756, "y": 178, "width": 28, "height": 28, "useAccentColor": True, "zIndex": 15},
        ],
        "required_slots": ["title", "event1_title", "event2_title", "event3_title", "event4_title"],
        "optional_slots": ["event1_date", "event1_desc", "event2_date", "event2_desc", "event3_date", "event3_desc", "event4_date", "event4_desc", "accent_image"],
    },

    "section_break": {
        "id": "section_break",
        "deprecated": True,
        "name": "Section Break",
        "description": "Clean section divider with centered heading and context",
        "category": "title",
        "tags": ["section", "divider", "break", "chapter", "transition"],
        "best_for": "Section transitions, chapter breaks, topic changes",
        "has_image": True, "has_chart": False,
        "suggest_background_image": True,
        "slots": {
            "section_title": {
                "x": 50, "y": 150, "width": 560, "height": 90,
                "type": "text", "textType": "title",
                "fontSize": 48, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 50, "y": 260, "width": 520, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 22, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7, "zIndex": 55,
            },
            "description": {
                "x": 50, "y": 330, "width": 480, "height": 80,
                "type": "text", "textType": "body",
                "fontSize": 16, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.5, "zIndex": 50,
            },
            "accent_image": {
                "x": 650, "y": 150, "width": 270, "height": 260,
                "type": "image_placeholder",
                "rx": 14,
                "zIndex": 20,
                "shadow": {"color": "rgba(0,0,0,0.15)", "blur": 14, "offsetX": 0, "offsetY": 4},
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 380, "y": 425, "width": 200, "height": 4, "useAccentColor": True, "rx": 2, "zIndex": 10},
            {"type": "shape", "shapeType": "circle", "x": 30, "y": 30, "width": 160, "height": 160, "useAccentColor": True, "opacity": 0.08, "zIndex": 5},
            {"type": "shape", "shapeType": "circle", "x": 770, "y": 370, "width": 180, "height": 180, "useAccentColor": True, "opacity": 0.06, "zIndex": 5},
        ],
        "required_slots": ["section_title"],
        "optional_slots": ["subtitle", "description", "accent_image"],
    },

    "closing": {
        "id": "closing",
        "deprecated": True,
        "name": "Closing",
        "description": "Closing slide with call-to-action",
        "category": "title",
        "tags": ["closing", "end", "thank you", "cta", "contact", "final", "conclusion"],
        "best_for": "Final slides, thank you slides, contact info, calls to action",
        "has_image": True, "has_chart": False,
        "suggest_background_image": True,
        "slots": {
            "title": {
                "x": 50, "y": 140, "width": 560, "height": 100,
                "type": "text", "textType": "title",
                "fontSize": 48, "fontWeight": "bold", "textAlign": "left",
                "zIndex": 60,
            },
            "subtitle": {
                "x": 50, "y": 260, "width": 520, "height": 50,
                "type": "text", "textType": "subtitle",
                "fontSize": 24, "fontWeight": "normal", "textAlign": "left",
                "zIndex": 60,
            },
            "cta_text": {
                "x": 50, "y": 340, "width": 480, "height": 45,
                "type": "text", "textType": "body",
                "fontSize": 18, "fontWeight": "normal", "textAlign": "left",
                "opacity": 0.7, "zIndex": 55,
            },
            "description": {
                "x": 50, "y": 400, "width": 520, "height": 80,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "lineHeight": 1.5, "zIndex": 55,
            },
            "accent_image": {
                "x": 650, "y": 150, "width": 270, "height": 250,
                "type": "image_placeholder",
                "rx": 14,
                "zIndex": 20,
                "shadow": {"color": "rgba(0,0,0,0.15)", "blur": 14, "offsetX": 0, "offsetY": 4},
            },
        },
        "decorations": [
            {"type": "shape", "shapeType": "rectangle", "x": 330, "y": 490, "width": 300, "height": 4, "useAccentColor": True, "rx": 2, "zIndex": 10},
            {"type": "shape", "shapeType": "circle", "x": -30, "y": -30, "width": 200, "height": 200, "useAccentColor": True, "opacity": 0.1, "zIndex": 5},
            {"type": "shape", "shapeType": "circle", "x": 790, "y": 380, "width": 200, "height": 200, "useAccentColor": True, "opacity": 0.1, "zIndex": 5},
        ],
        "required_slots": ["title", "accent_image"],
        "optional_slots": ["subtitle", "cta_text", "description"],
    },

    # ================== CITRA EXECUTIVE (consultant-deck family) ==================
    # Modelled on the McKinsey/BCG executive-overview aesthetic: dark book-end
    # covers + light body, kicker → action-title → subhead spine on every body
    # slide, no filler photography, footer discipline, section-coloured cards.
    # Picked when the deck profile is "executive" (board / investor / pitch /
    # overview / strategic-review). The renderer fills `useAccentColor` with
    # the section's chosen accent from the theme palette.

    "exec_title_dark": {
        "id": "exec_title_dark",
        "name": "Executive Title (Dark)",
        "description": "Cover slide for executive overviews: small logo top-left, kicker (date/audience), massive two-tone headline (part white + part accent), supporting subhead, three pill labels naming the deck's pillars. Dark navy background. No content image — typography-led.",
        "category": "title",
        "tags": ["executive", "cover", "board deck", "investor deck", "pitch", "intro", "title"],
        "best_for": "Cover slides for executive overviews, board / investor / pitch decks, strategic reviews",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#0B1020",
        "slots": {
            "brand_chip": {
                "x": 48, "y": 56, "width": 170, "height": 38,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "center",
                "letterSpacing": 3, "color": "#FFFFFF",
                "zIndex": 60,
            },
            "kicker": {
                "x": 48, "y": 200, "width": 600, "height": 22,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 4, "color": "#22D3EE",
                "zIndex": 60,
            },
            "title_a": {
                "x": 48, "y": 232, "width": 860, "height": 96,
                "type": "text", "textType": "title",
                "fontSize": 60, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.05,
                "zIndex": 60,
            },
            "title_b": {
                "x": 48, "y": 332, "width": 860, "height": 96,
                "type": "text", "textType": "title",
                "fontSize": 60, "fontWeight": "bold", "textAlign": "left",
                "color": "#22D3EE", "lineHeight": 1.05,
                "zIndex": 60,
            },
            "subhead": {
                "x": 48, "y": 438, "width": 760, "height": 50,
                "type": "text", "textType": "body",
                "fontSize": 15, "fontWeight": "normal", "textAlign": "left",
                "color": "#CBD5E1", "lineHeight": 1.5,
                "zIndex": 60,
            },
            "pill_1": {
                "x": 48, "y": 500, "width": 260, "height": 28,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "center",
                "color": "#FFFFFF", "backgroundColor": "#1E293B", "rx": 14,
                "zIndex": 60,
            },
            "pill_2": {
                "x": 350, "y": 500, "width": 260, "height": 28,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "center",
                "color": "#FFFFFF", "backgroundColor": "#1E293B", "rx": 14,
                "zIndex": 60,
            },
            "pill_3": {
                "x": 652, "y": 500, "width": 260, "height": 28,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "center",
                "color": "#FFFFFF", "backgroundColor": "#1E293B", "rx": 14,
                "zIndex": 60,
            },
        },
        "decorations": [
            # Brand-chip outline (drawn as a rounded rectangle behind the brand_chip text)
            {"type": "shape", "shapeType": "rectangle", "x": 48, "y": 56, "width": 170, "height": 38, "rx": 4, "stroke": "#475569", "strokeWidth": 1, "fill": "transparent", "zIndex": 5},
        ],
        "required_slots": ["title_a", "title_b"],
        "optional_slots": ["brand_chip", "kicker", "subhead", "pill_1", "pill_2", "pill_3"],
    },

    "exec_three_pillars": {
        "id": "exec_three_pillars",
        "name": "Executive Three Pillars",
        "description": "Three-pillar overview slide on light background. Kicker + bold action-title + single-line subhead, then three side-by-side pillar cards — each has a coloured top half (icon + 'PILLAR N' kicker + title) and a white bottom half with description. Bottom navy banner carries the supporting claim. No content images — colour-block + typography only.",
        "category": "content",
        "tags": ["executive", "three pillars", "overview", "framework", "what is", "pillars", "three", "3-up"],
        "best_for": "What-is-the-product slides, three-pillar overviews, framework introductions in executive decks",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#F8FAFC",
        "slots": {
            "kicker": {
                "x": 48, "y": 36, "width": 600, "height": 20,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#2563EB",
                "zIndex": 60,
            },
            "title": {
                "x": 48, "y": 62, "width": 880, "height": 90,
                "type": "text", "textType": "title",
                "fontSize": 38, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.15,
                "zIndex": 60,
            },
            "subhead": {
                "x": 48, "y": 156, "width": 880, "height": 36,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 60,
            },
            # Pillar 1 — blue top
            "p1_top_bg": {
                "x": 48, "y": 210, "width": 280, "height": 110,
                "type": "shape", "shapeType": "rectangle", "fill": "#2563EB", "rx": 8,
                "zIndex": 10,
            },
            "p1_icon": {
                "x": 70, "y": 232, "width": 36, "height": 36,
                "type": "icon", "fill": "#FFFFFF",
                "zIndex": 20,
            },
            "p1_label": {
                "x": 124, "y": 230, "width": 184, "height": 18,
                "type": "text", "textType": "kicker",
                "fontSize": 11, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#BFDBFE",
                "zIndex": 20,
            },
            "p1_title": {
                "x": 124, "y": 254, "width": 184, "height": 56,
                "type": "text", "textType": "subtitle",
                "fontSize": 17, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.25,
                "zIndex": 20,
            },
            "p1_body": {
                "x": 48, "y": 330, "width": 280, "height": 150,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#334155", "lineHeight": 1.55,
                "backgroundColor": "#FFFFFF", "rx": 8,
                "padding": 18,
                "zIndex": 10,
            },
            # Pillar 2 — cyan top
            "p2_top_bg": {
                "x": 340, "y": 210, "width": 280, "height": 110,
                "type": "shape", "shapeType": "rectangle", "fill": "#06B6D4", "rx": 8,
                "zIndex": 10,
            },
            "p2_icon": {
                "x": 362, "y": 232, "width": 36, "height": 36,
                "type": "icon", "fill": "#FFFFFF",
                "zIndex": 20,
            },
            "p2_label": {
                "x": 416, "y": 230, "width": 184, "height": 18,
                "type": "text", "textType": "kicker",
                "fontSize": 11, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#CFFAFE",
                "zIndex": 20,
            },
            "p2_title": {
                "x": 416, "y": 254, "width": 184, "height": 56,
                "type": "text", "textType": "subtitle",
                "fontSize": 17, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.25,
                "zIndex": 20,
            },
            "p2_body": {
                "x": 340, "y": 330, "width": 280, "height": 150,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#334155", "lineHeight": 1.55,
                "backgroundColor": "#FFFFFF", "rx": 8,
                "padding": 18,
                "zIndex": 10,
            },
            # Pillar 3 — purple top
            "p3_top_bg": {
                "x": 632, "y": 210, "width": 280, "height": 110,
                "type": "shape", "shapeType": "rectangle", "fill": "#8B5CF6", "rx": 8,
                "zIndex": 10,
            },
            "p3_icon": {
                "x": 654, "y": 232, "width": 36, "height": 36,
                "type": "icon", "fill": "#FFFFFF",
                "zIndex": 20,
            },
            "p3_label": {
                "x": 708, "y": 230, "width": 184, "height": 18,
                "type": "text", "textType": "kicker",
                "fontSize": 11, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#DDD6FE",
                "zIndex": 20,
            },
            "p3_title": {
                "x": 708, "y": 254, "width": 184, "height": 56,
                "type": "text", "textType": "subtitle",
                "fontSize": 17, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.25,
                "zIndex": 20,
            },
            "p3_body": {
                "x": 632, "y": 330, "width": 280, "height": 150,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#334155", "lineHeight": 1.55,
                "backgroundColor": "#FFFFFF", "rx": 8,
                "padding": 18,
                "zIndex": 10,
            },
            # Bottom claim banner
            "banner": {
                "x": 48, "y": 498, "width": 864, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "center",
                "letterSpacing": 2, "color": "#2563EB",
                "zIndex": 10,
            },
        },
        "decorations": [],
        "required_slots": ["title", "p1_title", "p1_body", "p2_title", "p2_body", "p3_title", "p3_body"],
        "optional_slots": ["kicker", "subhead", "p1_label", "p1_icon", "p2_label", "p2_icon", "p3_label", "p3_icon", "banner"],
    },

    "exec_action_card": {
        "id": "exec_action_card",
        "name": "Executive Action Card",
        "description": "Per-pillar detail slide on light background. Kicker (which pillar) + action-title + subhead, then two side-by-side cards: a white 'how it works' card on the left (numbered steps or bullets) and a dark navy stat/example card on the right (big before/after numbers or a list of examples).",
        "category": "content",
        "tags": ["executive", "pillar detail", "argument", "how it works", "before after", "stat", "two column", "action card"],
        "best_for": "Pillar deep-dives, before/after stat slides, how-it-works + examples in executive decks",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#F8FAFC",
        "slots": {
            "kicker": {
                "x": 48, "y": 36, "width": 700, "height": 20,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#2563EB",
                "zIndex": 60,
            },
            "title": {
                "x": 48, "y": 62, "width": 880, "height": 60,
                "type": "text", "textType": "title",
                "fontSize": 34, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.15,
                "zIndex": 60,
            },
            "subhead": {
                "x": 48, "y": 128, "width": 880, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 60,
            },
            "left_card_bg": {
                "x": 48, "y": 180, "width": 430, "height": 320,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 10,
                "shadow": {"color": "rgba(15,23,42,0.06)", "blur": 18, "offsetX": 0, "offsetY": 4},
                "zIndex": 10,
            },
            "left_title": {
                "x": 72, "y": 204, "width": 380, "height": 28,
                "type": "text", "textType": "subtitle",
                "fontSize": 17, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "left_steps": {
                "x": 72, "y": 244, "width": 380, "height": 240,
                "type": "numbered_steps",
                "fontSize": 13, "color": "#334155", "lineHeight": 1.55,
                "accentColor": "#2563EB",
                "zIndex": 20,
            },
            "right_card_bg": {
                "x": 502, "y": 180, "width": 410, "height": 320,
                "type": "shape", "shapeType": "rectangle", "fill": "#0B1020", "rx": 10,
                "zIndex": 10,
            },
            "right_kicker": {
                "x": 526, "y": 204, "width": 360, "height": 18,
                "type": "text", "textType": "kicker",
                "fontSize": 11, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#22D3EE",
                "zIndex": 20,
            },
            "right_before_label": {
                "x": 526, "y": 234, "width": 160, "height": 18,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#22D3EE",
                "zIndex": 20,
            },
            "right_after_label": {
                "x": 702, "y": 234, "width": 160, "height": 18,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#22D3EE",
                "zIndex": 20,
            },
            "right_before_value": {
                "x": 526, "y": 256, "width": 160, "height": 56,
                "type": "text", "textType": "title",
                "fontSize": 44, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF",
                "zIndex": 20,
            },
            "right_after_value": {
                "x": 702, "y": 256, "width": 160, "height": 56,
                "type": "text", "textType": "title",
                "fontSize": 44, "fontWeight": "bold", "textAlign": "left",
                "color": "#22D3EE",
                "zIndex": 20,
            },
            "right_before_unit": {
                "x": 526, "y": 316, "width": 160, "height": 18,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#94A3B8",
                "zIndex": 20,
            },
            "right_after_unit": {
                "x": 702, "y": 316, "width": 160, "height": 18,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#94A3B8",
                "zIndex": 20,
            },
            "right_divider": {
                "x": 526, "y": 348, "width": 360, "height": 1,
                "type": "shape", "shapeType": "rectangle", "fill": "#1E293B",
                "zIndex": 20,
            },
            "right_list_label": {
                "x": 526, "y": 360, "width": 360, "height": 18,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#CBD5E1",
                "zIndex": 20,
            },
            "right_list": {
                "x": 526, "y": 384, "width": 360, "height": 100,
                "type": "bullets",
                "fontSize": 13, "color": "#FFFFFF", "lineHeight": 1.7,
                "bulletStyle": "dot", "bulletColor": "#22D3EE",
                "zIndex": 20,
            },
        },
        "decorations": [],
        "required_slots": ["title", "left_title", "left_steps", "right_before_value", "right_after_value"],
        "optional_slots": [
            "kicker", "subhead",
            "right_kicker", "right_before_label", "right_after_label",
            "right_before_unit", "right_after_unit",
            "right_list_label", "right_list",
        ],
    },

    "exec_argument": {
        "id": "exec_argument",
        "name": "Executive Argument",
        "description": "Workhorse body slide on light background. Kicker + action-title + single-sentence subhead, then a single full-width white content card with 4-5 bullets (sentence case, ≤14 words each). Optional one-line takeaway strap at the bottom in accent colour. No images.",
        "category": "content",
        "tags": ["executive", "argument", "bullets", "claim", "body", "default body", "evidence"],
        "best_for": "Standard body slide making one claim supported by 4-5 bullets — the executive deck's workhorse",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#F8FAFC",
        "slots": {
            "kicker": {
                "x": 48, "y": 36, "width": 700, "height": 20,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#2563EB",
                "zIndex": 60,
            },
            "title": {
                "x": 48, "y": 62, "width": 880, "height": 80,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.15,
                "zIndex": 60,
            },
            "subhead": {
                "x": 48, "y": 152, "width": 880, "height": 36,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 60,
            },
            "content_card_bg": {
                "x": 48, "y": 210, "width": 864, "height": 270,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 10,
                "shadow": {"color": "rgba(15,23,42,0.06)", "blur": 18, "offsetX": 0, "offsetY": 4},
                "zIndex": 10,
            },
            "bullets": {
                "x": 72, "y": 234, "width": 816, "height": 222,
                "type": "bullets",
                "fontSize": 15, "color": "#1F2937", "lineHeight": 1.7,
                "bulletStyle": "dot", "bulletColor": "#2563EB",
                "zIndex": 20,
            },
            "takeaway": {
                "x": 48, "y": 496, "width": 864, "height": 28,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "center",
                "letterSpacing": 2, "color": "#2563EB",
                "zIndex": 10,
            },
        },
        "decorations": [],
        "required_slots": ["title", "bullets"],
        "optional_slots": ["kicker", "subhead", "takeaway"],
    },

    "exec_stat_grid_4": {
        "id": "exec_stat_grid_4",
        "name": "Executive Stat Grid (4 cards)",
        "description": "Business-impact slide on light background. Kicker + action-title + subhead, then 4 stat cards in a row — each with a thin coloured accent bar across the top, a giant number (90pt), and a one-line label below. Different accent per card (blue/cyan/purple/green). Optional 3-up icon-cards row at the bottom for 'where the savings come from' style supporting detail.",
        "category": "data",
        "tags": ["executive", "stats", "metrics", "kpi", "business impact", "four stats", "stat grid"],
        "best_for": "Business-impact / KPI / 'by the numbers' slides in executive decks — 4 headline metrics",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#F8FAFC",
        "slots": {
            "kicker": {
                "x": 48, "y": 36, "width": 700, "height": 20,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#2563EB",
                "zIndex": 60,
            },
            "title": {
                "x": 48, "y": 62, "width": 880, "height": 72,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.15,
                "zIndex": 60,
            },
            "subhead": {
                "x": 48, "y": 142, "width": 880, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 60,
            },
            # Stat card 1 (blue)
            "s1_accent": {
                "x": 48, "y": 200, "width": 208, "height": 4,
                "type": "shape", "shapeType": "rectangle", "fill": "#2563EB", "rx": 2,
                "zIndex": 20,
            },
            "s1_bg": {
                "x": 48, "y": 204, "width": 208, "height": 144,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2},
                "zIndex": 10,
            },
            "s1_value": {
                "x": 68, "y": 222, "width": 168, "height": 70,
                "type": "text", "textType": "title",
                "fontSize": 48, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.0,
                "zIndex": 20,
            },
            "s1_label": {
                "x": 68, "y": 298, "width": 168, "height": 38,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.45,
                "zIndex": 20,
            },
            # Stat card 2 (cyan)
            "s2_accent": {
                "x": 274, "y": 200, "width": 208, "height": 4,
                "type": "shape", "shapeType": "rectangle", "fill": "#06B6D4", "rx": 2,
                "zIndex": 20,
            },
            "s2_bg": {
                "x": 274, "y": 204, "width": 208, "height": 144,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2},
                "zIndex": 10,
            },
            "s2_value": {
                "x": 294, "y": 222, "width": 168, "height": 70,
                "type": "text", "textType": "title",
                "fontSize": 48, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.0,
                "zIndex": 20,
            },
            "s2_label": {
                "x": 294, "y": 298, "width": 168, "height": 38,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.45,
                "zIndex": 20,
            },
            # Stat card 3 (purple)
            "s3_accent": {
                "x": 500, "y": 200, "width": 208, "height": 4,
                "type": "shape", "shapeType": "rectangle", "fill": "#8B5CF6", "rx": 2,
                "zIndex": 20,
            },
            "s3_bg": {
                "x": 500, "y": 204, "width": 208, "height": 144,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2},
                "zIndex": 10,
            },
            "s3_value": {
                "x": 520, "y": 222, "width": 168, "height": 70,
                "type": "text", "textType": "title",
                "fontSize": 48, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.0,
                "zIndex": 20,
            },
            "s3_label": {
                "x": 520, "y": 298, "width": 168, "height": 38,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.45,
                "zIndex": 20,
            },
            # Stat card 4 (green)
            "s4_accent": {
                "x": 726, "y": 200, "width": 186, "height": 4,
                "type": "shape", "shapeType": "rectangle", "fill": "#10B981", "rx": 2,
                "zIndex": 20,
            },
            "s4_bg": {
                "x": 726, "y": 204, "width": 186, "height": 144,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2},
                "zIndex": 10,
            },
            "s4_value": {
                "x": 746, "y": 222, "width": 146, "height": 70,
                "type": "text", "textType": "title",
                "fontSize": 48, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.0,
                "zIndex": 20,
            },
            "s4_label": {
                "x": 746, "y": 298, "width": 146, "height": 38,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.45,
                "zIndex": 20,
            },
            # Optional "where the savings come from" 3-up icon strip
            "detail_heading": {
                "x": 48, "y": 372, "width": 880, "height": 26,
                "type": "text", "textType": "subtitle",
                "fontSize": 15, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "d1_icon": {
                "x": 68, "y": 416, "width": 28, "height": 28,
                "type": "icon", "fill": "#2563EB",
                "zIndex": 20,
            },
            "d1_title": {
                "x": 110, "y": 414, "width": 200, "height": 22,
                "type": "text", "textType": "subtitle",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "d1_body": {
                "x": 110, "y": 438, "width": 200, "height": 60,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 20,
            },
            "d2_icon": {
                "x": 354, "y": 416, "width": 28, "height": 28,
                "type": "icon", "fill": "#06B6D4",
                "zIndex": 20,
            },
            "d2_title": {
                "x": 396, "y": 414, "width": 200, "height": 22,
                "type": "text", "textType": "subtitle",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "d2_body": {
                "x": 396, "y": 438, "width": 200, "height": 60,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 20,
            },
            "d3_icon": {
                "x": 640, "y": 416, "width": 28, "height": 28,
                "type": "icon", "fill": "#8B5CF6",
                "zIndex": 20,
            },
            "d3_title": {
                "x": 682, "y": 414, "width": 200, "height": 22,
                "type": "text", "textType": "subtitle",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "d3_body": {
                "x": 682, "y": 438, "width": 200, "height": 60,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 20,
            },
        },
        "decorations": [],
        "required_slots": [
            "title",
            "s1_value", "s1_label", "s2_value", "s2_label",
            "s3_value", "s3_label", "s4_value", "s4_label",
        ],
        "optional_slots": [
            "kicker", "subhead",
            "detail_heading",
            "d1_icon", "d1_title", "d1_body",
            "d2_icon", "d2_title", "d2_body",
            "d3_icon", "d3_title", "d3_body",
        ],
    },

    "exec_features_2x2": {
        "id": "exec_features_2x2",
        "name": "Executive Features 2×2",
        "description": "Two-by-two feature grid on light background. Kicker + action-title + subhead, then four white feature cards each with a coloured icon circle (blue/cyan/purple/green) + bold title + 2-line description. Optional dark banner at the bottom carrying a tag-line claim.",
        "category": "content",
        "tags": ["executive", "features", "capabilities", "four features", "2x2", "feature grid"],
        "best_for": "Capabilities / features slides — show four distinct value props in a balanced 2x2",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#F8FAFC",
        "slots": {
            "kicker": {
                "x": 48, "y": 36, "width": 700, "height": 20,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#8B5CF6",
                "zIndex": 60,
            },
            "title": {
                "x": 48, "y": 62, "width": 880, "height": 72,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.15,
                "zIndex": 60,
            },
            "subhead": {
                "x": 48, "y": 142, "width": 880, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 60,
            },
            # Card 1 — top-left (blue)
            "f1_bg": {
                "x": 48, "y": 196, "width": 430, "height": 152,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 10,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 14, "offsetX": 0, "offsetY": 3},
                "zIndex": 10,
            },
            "f1_icon_bg": {
                "x": 70, "y": 220, "width": 56, "height": 56,
                "type": "shape", "shapeType": "circle", "fill": "#2563EB",
                "zIndex": 15,
            },
            "f1_icon": {
                "x": 84, "y": 234, "width": 28, "height": 28,
                "type": "icon", "fill": "#FFFFFF",
                "zIndex": 20,
            },
            "f1_title": {
                "x": 150, "y": 226, "width": 308, "height": 28,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "f1_body": {
                "x": 150, "y": 258, "width": 308, "height": 76,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.55,
                "zIndex": 20,
            },
            # Card 2 — top-right (cyan)
            "f2_bg": {
                "x": 498, "y": 196, "width": 414, "height": 152,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 10,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 14, "offsetX": 0, "offsetY": 3},
                "zIndex": 10,
            },
            "f2_icon_bg": {
                "x": 520, "y": 220, "width": 56, "height": 56,
                "type": "shape", "shapeType": "circle", "fill": "#06B6D4",
                "zIndex": 15,
            },
            "f2_icon": {
                "x": 534, "y": 234, "width": 28, "height": 28,
                "type": "icon", "fill": "#FFFFFF",
                "zIndex": 20,
            },
            "f2_title": {
                "x": 600, "y": 226, "width": 292, "height": 28,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "f2_body": {
                "x": 600, "y": 258, "width": 292, "height": 76,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.55,
                "zIndex": 20,
            },
            # Card 3 — bottom-left (purple)
            "f3_bg": {
                "x": 48, "y": 356, "width": 430, "height": 132,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 10,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 14, "offsetX": 0, "offsetY": 3},
                "zIndex": 10,
            },
            "f3_icon_bg": {
                "x": 70, "y": 380, "width": 56, "height": 56,
                "type": "shape", "shapeType": "circle", "fill": "#8B5CF6",
                "zIndex": 15,
            },
            "f3_icon": {
                "x": 84, "y": 394, "width": 28, "height": 28,
                "type": "icon", "fill": "#FFFFFF",
                "zIndex": 20,
            },
            "f3_title": {
                "x": 150, "y": 386, "width": 308, "height": 28,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "f3_body": {
                "x": 150, "y": 418, "width": 308, "height": 60,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.55,
                "zIndex": 20,
            },
            # Card 4 — bottom-right (green)
            "f4_bg": {
                "x": 498, "y": 356, "width": 414, "height": 132,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 10,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 14, "offsetX": 0, "offsetY": 3},
                "zIndex": 10,
            },
            "f4_icon_bg": {
                "x": 520, "y": 380, "width": 56, "height": 56,
                "type": "shape", "shapeType": "circle", "fill": "#10B981",
                "zIndex": 15,
            },
            "f4_icon": {
                "x": 534, "y": 394, "width": 28, "height": 28,
                "type": "icon", "fill": "#FFFFFF",
                "zIndex": 20,
            },
            "f4_title": {
                "x": 600, "y": 386, "width": 292, "height": 28,
                "type": "text", "textType": "subtitle",
                "fontSize": 18, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "f4_body": {
                "x": 600, "y": 418, "width": 292, "height": 60,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.55,
                "zIndex": 20,
            },
            # Optional dark banner across the bottom
            "banner_bg": {
                "x": 48, "y": 502, "width": 864, "height": 26,
                "type": "shape", "shapeType": "rectangle", "fill": "#0B1020", "rx": 4,
                "zIndex": 10,
            },
            "banner_text": {
                "x": 48, "y": 502, "width": 864, "height": 26,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "center",
                "letterSpacing": 1, "color": "#22D3EE",
                "zIndex": 20,
            },
        },
        "decorations": [],
        "required_slots": [
            "title",
            "f1_title", "f1_body",
            "f2_title", "f2_body",
            "f3_title", "f3_body",
            "f4_title", "f4_body",
        ],
        "optional_slots": [
            "kicker", "subhead",
            "f1_icon", "f2_icon", "f3_icon", "f4_icon",
            "banner_text",
        ],
    },

    "exec_industries_2x2": {
        "id": "exec_industries_2x2",
        "name": "Executive Industries 2×2",
        "description": "Industries / use-cases slide on light background. Kicker + action-title + subhead, then 2×2 grid of industry cards. Each card has a vertical coloured side-rule (blue/green/orange/purple), a coloured icon circle + industry name, and 4 check-marked use-case bullets in two columns.",
        "category": "content",
        "tags": ["executive", "industries", "use cases", "verticals", "applications", "where it's used"],
        "best_for": "Industries / verticals / use-cases slide — show 4 verticals each with 4 use cases",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#F8FAFC",
        "slots": {
            "kicker": {
                "x": 48, "y": 36, "width": 700, "height": 20,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#2563EB",
                "zIndex": 60,
            },
            "title": {
                "x": 48, "y": 62, "width": 880, "height": 72,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.15,
                "zIndex": 60,
            },
            "subhead": {
                "x": 48, "y": 142, "width": 880, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 60,
            },
            # Card 1 — top-left (blue)
            "i1_rule": {
                "x": 48, "y": 196, "width": 4, "height": 152,
                "type": "shape", "shapeType": "rectangle", "fill": "#2563EB",
                "zIndex": 20,
            },
            "i1_bg": {
                "x": 52, "y": 196, "width": 426, "height": 152,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2},
                "zIndex": 10,
            },
            "i1_icon_bg": {
                "x": 76, "y": 216, "width": 40, "height": 40,
                "type": "shape", "shapeType": "circle", "fill": "#2563EB",
                "zIndex": 15,
            },
            "i1_icon": {
                "x": 86, "y": 226, "width": 20, "height": 20,
                "type": "icon", "fill": "#FFFFFF",
                "zIndex": 20,
            },
            "i1_name": {
                "x": 130, "y": 220, "width": 330, "height": 32,
                "type": "text", "textType": "subtitle",
                "fontSize": 19, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "i1_uses": {
                "x": 76, "y": 270, "width": 396, "height": 72,
                "type": "bullets",
                "fontSize": 12, "color": "#334155", "lineHeight": 1.7,
                "bulletStyle": "check", "bulletColor": "#10B981",
                "columns": 2,
                "zIndex": 20,
            },
            # Card 2 — top-right (green)
            "i2_rule": {
                "x": 488, "y": 196, "width": 4, "height": 152,
                "type": "shape", "shapeType": "rectangle", "fill": "#10B981",
                "zIndex": 20,
            },
            "i2_bg": {
                "x": 492, "y": 196, "width": 420, "height": 152,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2},
                "zIndex": 10,
            },
            "i2_icon_bg": {
                "x": 516, "y": 216, "width": 40, "height": 40,
                "type": "shape", "shapeType": "circle", "fill": "#10B981",
                "zIndex": 15,
            },
            "i2_icon": {
                "x": 526, "y": 226, "width": 20, "height": 20,
                "type": "icon", "fill": "#FFFFFF",
                "zIndex": 20,
            },
            "i2_name": {
                "x": 570, "y": 220, "width": 330, "height": 32,
                "type": "text", "textType": "subtitle",
                "fontSize": 19, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "i2_uses": {
                "x": 516, "y": 270, "width": 390, "height": 72,
                "type": "bullets",
                "fontSize": 12, "color": "#334155", "lineHeight": 1.7,
                "bulletStyle": "check", "bulletColor": "#10B981",
                "columns": 2,
                "zIndex": 20,
            },
            # Card 3 — bottom-left (orange)
            "i3_rule": {
                "x": 48, "y": 360, "width": 4, "height": 152,
                "type": "shape", "shapeType": "rectangle", "fill": "#F59E0B",
                "zIndex": 20,
            },
            "i3_bg": {
                "x": 52, "y": 360, "width": 426, "height": 152,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2},
                "zIndex": 10,
            },
            "i3_icon_bg": {
                "x": 76, "y": 380, "width": 40, "height": 40,
                "type": "shape", "shapeType": "circle", "fill": "#F59E0B",
                "zIndex": 15,
            },
            "i3_icon": {
                "x": 86, "y": 390, "width": 20, "height": 20,
                "type": "icon", "fill": "#FFFFFF",
                "zIndex": 20,
            },
            "i3_name": {
                "x": 130, "y": 384, "width": 330, "height": 32,
                "type": "text", "textType": "subtitle",
                "fontSize": 19, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "i3_uses": {
                "x": 76, "y": 434, "width": 396, "height": 72,
                "type": "bullets",
                "fontSize": 12, "color": "#334155", "lineHeight": 1.7,
                "bulletStyle": "check", "bulletColor": "#10B981",
                "columns": 2,
                "zIndex": 20,
            },
            # Card 4 — bottom-right (purple)
            "i4_rule": {
                "x": 488, "y": 360, "width": 4, "height": 152,
                "type": "shape", "shapeType": "rectangle", "fill": "#8B5CF6",
                "zIndex": 20,
            },
            "i4_bg": {
                "x": 492, "y": 360, "width": 420, "height": 152,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 12, "offsetX": 0, "offsetY": 2},
                "zIndex": 10,
            },
            "i4_icon_bg": {
                "x": 516, "y": 380, "width": 40, "height": 40,
                "type": "shape", "shapeType": "circle", "fill": "#8B5CF6",
                "zIndex": 15,
            },
            "i4_icon": {
                "x": 526, "y": 390, "width": 20, "height": 20,
                "type": "icon", "fill": "#FFFFFF",
                "zIndex": 20,
            },
            "i4_name": {
                "x": 570, "y": 384, "width": 330, "height": 32,
                "type": "text", "textType": "subtitle",
                "fontSize": 19, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "i4_uses": {
                "x": 516, "y": 434, "width": 390, "height": 72,
                "type": "bullets",
                "fontSize": 12, "color": "#334155", "lineHeight": 1.7,
                "bulletStyle": "check", "bulletColor": "#10B981",
                "columns": 2,
                "zIndex": 20,
            },
        },
        "decorations": [],
        "required_slots": [
            "title",
            "i1_name", "i1_uses",
            "i2_name", "i2_uses",
            "i3_name", "i3_uses",
            "i4_name", "i4_uses",
        ],
        "optional_slots": [
            "kicker", "subhead",
            "i1_icon", "i2_icon", "i3_icon", "i4_icon",
        ],
    },

    "exec_sovereignty_dark": {
        "id": "exec_sovereignty_dark",
        "name": "Executive Architecture / Sovereignty (Dark)",
        "description": "Architecture / sovereignty slide on dark navy. Kicker + action-title + subhead, then four equal-width dark cards in a row (cyan title + white body — 'Zero Copy / Zero ETL / Zero Egress / Zero Lock-in' style), with an optional bottom 'Governance & deployment' panel of 4 light-coloured checkmarked items.",
        "category": "content",
        "tags": ["executive", "architecture", "sovereignty", "governance", "security", "four pillars dark", "trust"],
        "best_for": "Architecture / sovereignty / security / governance slides — communicate trust posture on dark background",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#0B1020",
        "slots": {
            "kicker": {
                "x": 48, "y": 36, "width": 700, "height": 20,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#22D3EE",
                "zIndex": 60,
            },
            "title": {
                "x": 48, "y": 62, "width": 880, "height": 72,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.15,
                "zIndex": 60,
            },
            "subhead": {
                "x": 48, "y": 142, "width": 880, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "color": "#CBD5E1", "lineHeight": 1.5,
                "zIndex": 60,
            },
            # Card 1
            "z1_bg": {
                "x": 48, "y": 196, "width": 208, "height": 192,
                "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8,
                "stroke": "#1E293B", "strokeWidth": 1,
                "zIndex": 10,
            },
            "z1_title": {
                "x": 68, "y": 220, "width": 168, "height": 32,
                "type": "text", "textType": "subtitle",
                "fontSize": 22, "fontWeight": "bold", "textAlign": "left",
                "color": "#22D3EE",
                "zIndex": 20,
            },
            "z1_body": {
                "x": 68, "y": 280, "width": 168, "height": 96,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.55,
                "zIndex": 20,
            },
            # Card 2
            "z2_bg": {
                "x": 274, "y": 196, "width": 208, "height": 192,
                "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8,
                "stroke": "#1E293B", "strokeWidth": 1,
                "zIndex": 10,
            },
            "z2_title": {
                "x": 294, "y": 220, "width": 168, "height": 32,
                "type": "text", "textType": "subtitle",
                "fontSize": 22, "fontWeight": "bold", "textAlign": "left",
                "color": "#22D3EE",
                "zIndex": 20,
            },
            "z2_body": {
                "x": 294, "y": 280, "width": 168, "height": 96,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.55,
                "zIndex": 20,
            },
            # Card 3
            "z3_bg": {
                "x": 500, "y": 196, "width": 208, "height": 192,
                "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8,
                "stroke": "#1E293B", "strokeWidth": 1,
                "zIndex": 10,
            },
            "z3_title": {
                "x": 520, "y": 220, "width": 168, "height": 32,
                "type": "text", "textType": "subtitle",
                "fontSize": 22, "fontWeight": "bold", "textAlign": "left",
                "color": "#22D3EE",
                "zIndex": 20,
            },
            "z3_body": {
                "x": 520, "y": 280, "width": 168, "height": 96,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.55,
                "zIndex": 20,
            },
            # Card 4
            "z4_bg": {
                "x": 726, "y": 196, "width": 186, "height": 192,
                "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8,
                "stroke": "#1E293B", "strokeWidth": 1,
                "zIndex": 10,
            },
            "z4_title": {
                "x": 746, "y": 220, "width": 146, "height": 32,
                "type": "text", "textType": "subtitle",
                "fontSize": 22, "fontWeight": "bold", "textAlign": "left",
                "color": "#22D3EE",
                "zIndex": 20,
            },
            "z4_body": {
                "x": 746, "y": 280, "width": 146, "height": 96,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "normal", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.55,
                "zIndex": 20,
            },
            # Bottom governance panel
            "gov_bg": {
                "x": 48, "y": 408, "width": 864, "height": 96,
                "type": "shape", "shapeType": "rectangle", "fill": "#F8FAFC", "rx": 8,
                "zIndex": 10,
            },
            "gov_heading": {
                "x": 68, "y": 422, "width": 824, "height": 22,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#2563EB",
                "zIndex": 20,
            },
            "g1_check": {
                "x": 68, "y": 452, "width": 16, "height": 16,
                "type": "icon", "iconName": "checkmark-circle", "fill": "#10B981",
                "zIndex": 20,
            },
            "g1_title": {
                "x": 92, "y": 450, "width": 180, "height": 20,
                "type": "text", "textType": "subtitle",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "g1_body": {
                "x": 92, "y": 472, "width": 180, "height": 24,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569",
                "zIndex": 20,
            },
            "g2_check": {
                "x": 280, "y": 452, "width": 16, "height": 16,
                "type": "icon", "iconName": "checkmark-circle", "fill": "#10B981",
                "zIndex": 20,
            },
            "g2_title": {
                "x": 304, "y": 450, "width": 180, "height": 20,
                "type": "text", "textType": "subtitle",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "g2_body": {
                "x": 304, "y": 472, "width": 180, "height": 24,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569",
                "zIndex": 20,
            },
            "g3_check": {
                "x": 492, "y": 452, "width": 16, "height": 16,
                "type": "icon", "iconName": "checkmark-circle", "fill": "#10B981",
                "zIndex": 20,
            },
            "g3_title": {
                "x": 516, "y": 450, "width": 180, "height": 20,
                "type": "text", "textType": "subtitle",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "g3_body": {
                "x": 516, "y": 472, "width": 180, "height": 24,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569",
                "zIndex": 20,
            },
            "g4_check": {
                "x": 704, "y": 452, "width": 16, "height": 16,
                "type": "icon", "iconName": "checkmark-circle", "fill": "#10B981",
                "zIndex": 20,
            },
            "g4_title": {
                "x": 728, "y": 450, "width": 180, "height": 20,
                "type": "text", "textType": "subtitle",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "g4_body": {
                "x": 728, "y": 472, "width": 180, "height": 24,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569",
                "zIndex": 20,
            },
        },
        "decorations": [],
        "required_slots": [
            "title",
            "z1_title", "z1_body", "z2_title", "z2_body",
            "z3_title", "z3_body", "z4_title", "z4_body",
        ],
        "optional_slots": [
            "kicker", "subhead",
            "gov_heading",
            "g1_title", "g1_body", "g2_title", "g2_body",
            "g3_title", "g3_body", "g4_title", "g4_body",
        ],
    },

    "exec_chat_example": {
        "id": "exec_chat_example",
        "name": "Executive Chat Example",
        "description": "Product-example slide on light background. Kicker + action-title + subhead, then a live chat example card on the left (user blue bubble + response card with bullets + green source pill) and three stat blocks on the right (vertical cyan accent bar + headline figure + label + sub-description).",
        "category": "content",
        "tags": ["executive", "chat example", "live example", "product demo", "qa", "ask example", "deep research"],
        "best_for": "Product-example slides — show a live Q&A in chat shape plus 3 supporting metrics",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#F8FAFC",
        "slots": {
            "kicker": {
                "x": 48, "y": 36, "width": 700, "height": 20,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#06B6D4",
                "zIndex": 60,
            },
            "title": {
                "x": 48, "y": 62, "width": 880, "height": 72,
                "type": "text", "textType": "title",
                "fontSize": 36, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.15,
                "zIndex": 60,
            },
            "subhead": {
                "x": 48, "y": 142, "width": 880, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 14, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 60,
            },
            # Left: chat example card
            "chat_bg": {
                "x": 48, "y": 200, "width": 510, "height": 308,
                "type": "shape", "shapeType": "rectangle", "fill": "#EEF2F7", "rx": 10,
                "zIndex": 10,
            },
            "chat_kicker": {
                "x": 72, "y": 220, "width": 460, "height": 18,
                "type": "text", "textType": "kicker",
                "fontSize": 11, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 3, "color": "#475569",
                "zIndex": 20,
            },
            "user_bubble_bg": {
                "x": 92, "y": 252, "width": 446, "height": 50,
                "type": "shape", "shapeType": "rectangle", "fill": "#2563EB", "rx": 8,
                "zIndex": 15,
            },
            "user_question": {
                "x": 108, "y": 264, "width": 414, "height": 30,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#FFFFFF",
                "zIndex": 20,
            },
            "answer_bg": {
                "x": 72, "y": 314, "width": 462, "height": 144,
                "type": "shape", "shapeType": "rectangle", "fill": "#FFFFFF", "rx": 8,
                "shadow": {"color": "rgba(15,23,42,0.05)", "blur": 10, "offsetX": 0, "offsetY": 2},
                "zIndex": 15,
            },
            "answer_headline": {
                "x": 92, "y": 330, "width": 422, "height": 22,
                "type": "text", "textType": "subtitle",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "answer_subline": {
                "x": 92, "y": 354, "width": 422, "height": 20,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569",
                "zIndex": 20,
            },
            "answer_bullets": {
                "x": 92, "y": 382, "width": 422, "height": 68,
                "type": "bullets",
                "fontSize": 11, "color": "#334155", "lineHeight": 1.6,
                "bulletStyle": "dot", "bulletColor": "#475569",
                "zIndex": 20,
            },
            "source_pill_bg": {
                "x": 72, "y": 472, "width": 220, "height": 22,
                "type": "shape", "shapeType": "rectangle", "fill": "#DCFCE7", "rx": 11,
                "zIndex": 15,
            },
            "source_text": {
                "x": 72, "y": 472, "width": 220, "height": 22,
                "type": "text", "textType": "body",
                "fontSize": 10, "fontWeight": "bold", "textAlign": "center",
                "color": "#065F46",
                "zIndex": 20,
            },
            # Right: 3 stat blocks with vertical cyan rule
            "r1_rule": {
                "x": 580, "y": 200, "width": 4, "height": 90,
                "type": "shape", "shapeType": "rectangle", "fill": "#06B6D4",
                "zIndex": 20,
            },
            "r1_value": {
                "x": 596, "y": 200, "width": 200, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 38, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.0,
                "zIndex": 20,
            },
            "r1_label": {
                "x": 800, "y": 206, "width": 112, "height": 20,
                "type": "text", "textType": "subtitle",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "r1_sub": {
                "x": 800, "y": 230, "width": 112, "height": 40,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 20,
            },
            "r2_rule": {
                "x": 580, "y": 308, "width": 4, "height": 90,
                "type": "shape", "shapeType": "rectangle", "fill": "#06B6D4",
                "zIndex": 20,
            },
            "r2_value": {
                "x": 596, "y": 308, "width": 200, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 38, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.0,
                "zIndex": 20,
            },
            "r2_label": {
                "x": 800, "y": 314, "width": 112, "height": 20,
                "type": "text", "textType": "subtitle",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "r2_sub": {
                "x": 800, "y": 338, "width": 112, "height": 40,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 20,
            },
            "r3_rule": {
                "x": 580, "y": 416, "width": 4, "height": 90,
                "type": "shape", "shapeType": "rectangle", "fill": "#06B6D4",
                "zIndex": 20,
            },
            "r3_value": {
                "x": 596, "y": 416, "width": 200, "height": 50,
                "type": "text", "textType": "title",
                "fontSize": 38, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A", "lineHeight": 1.0,
                "zIndex": 20,
            },
            "r3_label": {
                "x": 800, "y": 422, "width": 112, "height": 20,
                "type": "text", "textType": "subtitle",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "left",
                "color": "#0F172A",
                "zIndex": 20,
            },
            "r3_sub": {
                "x": 800, "y": 446, "width": 112, "height": 40,
                "type": "text", "textType": "body",
                "fontSize": 11, "fontWeight": "normal", "textAlign": "left",
                "color": "#475569", "lineHeight": 1.5,
                "zIndex": 20,
            },
        },
        "decorations": [],
        "required_slots": [
            "title",
            "user_question", "answer_headline",
            "r1_value", "r1_label",
        ],
        "optional_slots": [
            "kicker", "subhead",
            "chat_kicker", "answer_subline", "answer_bullets", "source_text",
            "r1_sub", "r2_value", "r2_label", "r2_sub", "r3_value", "r3_label", "r3_sub",
        ],
    },

    "exec_closing_dark": {
        "id": "exec_closing_dark",
        "name": "Executive Closing — Strategic Reasons",
        "description": "Closing / 'Why buy' slide on dark navy. Kicker + headline at top, then 2x2 grid of dark feature cards each carrying a giant cyan numeral (01/02/03/04), a bold reason title, and a one-line description. Cyan CTA banner spans the full width at the bottom.",
        "category": "closing",
        "tags": ["executive", "closing", "why buy", "strategic reasons", "cta", "ask", "next steps", "summary"],
        "best_for": "Closing slides for executive decks — recommendations, strategic reasons to buy, asks of the audience",
        "has_image": False, "has_chart": False,
        "backgroundColor": "#0B1020",
        "slots": {
            "kicker": {
                "x": 48, "y": 56, "width": 600, "height": 22,
                "type": "text", "textType": "kicker",
                "fontSize": 12, "fontWeight": "bold", "textAlign": "left",
                "letterSpacing": 4, "color": "#22D3EE",
                "zIndex": 60,
            },
            "title": {
                "x": 48, "y": 92, "width": 880, "height": 68,
                "type": "text", "textType": "title",
                "fontSize": 44, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF",
                "zIndex": 60,
            },
            # Card 01
            "c1_bg": {
                "x": 48, "y": 196, "width": 430, "height": 144,
                "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8,
                "stroke": "#1E293B", "strokeWidth": 1,
                "zIndex": 10,
            },
            "c1_number": {
                "x": 70, "y": 212, "width": 100, "height": 66,
                "type": "text", "textType": "title",
                "fontSize": 44, "fontWeight": "bold", "textAlign": "left",
                "color": "#22D3EE",
                "zIndex": 20,
            },
            "c1_title": {
                # Title slot is sized for TWO lines (h=52) so titles like
                # "Energy Security Reshapes Nations" wrap cleanly inside the
                # card instead of bleeding down into the body / number area.
                # fontSize 16 (was 18) trades a touch of presence for one
                # extra char-per-line and reliable single-card containment.
                "x": 178, "y": 218, "width": 280, "height": 52,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.25,
                "zIndex": 20,
            },
            "c1_body": {
                # Body shifted down to match new title height; height shrunk
                # from 80 → 64 so the bottom of the body stays inside the
                # 144px-tall card (276 + 64 = 340 = card bottom).
                "x": 178, "y": 276, "width": 280, "height": 64,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#CBD5E1", "lineHeight": 1.5,
                "zIndex": 20,
            },
            # Card 02
            "c2_bg": {
                "x": 502, "y": 196, "width": 410, "height": 144,
                "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8,
                "stroke": "#1E293B", "strokeWidth": 1,
                "zIndex": 10,
            },
            "c2_number": {
                "x": 524, "y": 212, "width": 100, "height": 66,
                "type": "text", "textType": "title",
                "fontSize": 44, "fontWeight": "bold", "textAlign": "left",
                "color": "#22D3EE",
                "zIndex": 20,
            },
            "c2_title": {
                "x": 632, "y": 218, "width": 260, "height": 52,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.25,
                "zIndex": 20,
            },
            "c2_body": {
                "x": 632, "y": 276, "width": 260, "height": 64,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#CBD5E1", "lineHeight": 1.5,
                "zIndex": 20,
            },
            # Card 03
            "c3_bg": {
                "x": 48, "y": 356, "width": 430, "height": 144,
                "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8,
                "stroke": "#1E293B", "strokeWidth": 1,
                "zIndex": 10,
            },
            "c3_number": {
                "x": 70, "y": 372, "width": 100, "height": 66,
                "type": "text", "textType": "title",
                "fontSize": 44, "fontWeight": "bold", "textAlign": "left",
                "color": "#22D3EE",
                "zIndex": 20,
            },
            "c3_title": {
                "x": 178, "y": 378, "width": 280, "height": 52,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.25,
                "zIndex": 20,
            },
            "c3_body": {
                "x": 178, "y": 436, "width": 280, "height": 64,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#CBD5E1", "lineHeight": 1.5,
                "zIndex": 20,
            },
            # Card 04
            "c4_bg": {
                "x": 502, "y": 356, "width": 410, "height": 144,
                "type": "shape", "shapeType": "rectangle", "fill": "#111827", "rx": 8,
                "stroke": "#1E293B", "strokeWidth": 1,
                "zIndex": 10,
            },
            "c4_number": {
                "x": 524, "y": 372, "width": 100, "height": 66,
                "type": "text", "textType": "title",
                "fontSize": 44, "fontWeight": "bold", "textAlign": "left",
                "color": "#22D3EE",
                "zIndex": 20,
            },
            "c4_title": {
                "x": 632, "y": 378, "width": 260, "height": 52,
                "type": "text", "textType": "subtitle",
                "fontSize": 16, "fontWeight": "bold", "textAlign": "left",
                "color": "#FFFFFF", "lineHeight": 1.25,
                "zIndex": 20,
            },
            "c4_body": {
                "x": 632, "y": 436, "width": 260, "height": 64,
                "type": "text", "textType": "body",
                "fontSize": 12, "fontWeight": "normal", "textAlign": "left",
                "color": "#CBD5E1", "lineHeight": 1.5,
                "zIndex": 20,
            },
            # CTA banner across the bottom
            "cta_bg": {
                "x": 48, "y": 504, "width": 864, "height": 24,
                "type": "shape", "shapeType": "rectangle", "fill": "#22D3EE", "rx": 14,
                "zIndex": 10,
            },
            "cta_text": {
                "x": 48, "y": 504, "width": 864, "height": 24,
                "type": "text", "textType": "body",
                "fontSize": 13, "fontWeight": "bold", "textAlign": "center",
                "color": "#0B1020",
                "zIndex": 20,
            },
        },
        "decorations": [],
        "required_slots": ["title", "c1_number", "c1_title", "c1_body", "c2_number", "c2_title", "c2_body"],
        "optional_slots": [
            "kicker",
            "c3_number", "c3_title", "c3_body",
            "c4_number", "c4_title", "c4_body",
            "cta_text",
        ],
    },
}


# ==================== Template Matching ======================================

# Keywords/phrases that map to specific templates
TEMPLATE_KEYWORDS = {
    # Executive consultant-deck family — matched on intent words, not layout.
    # The bare `exec_*` keys are the outline-emitted layout strings; the
    # heuristic falls back to these when the LLM matcher is skipped.
    # Citra is enterprise-only. Every layout name a legacy outline might emit
    # is migrated into the matching exec_* template below, so a stale outline
    # never silently routes to a deprecated template. Deprecated templates
    # stay in SLIDE_TEMPLATES (for rendering pre-cutover decks) but they're
    # not reachable through this keyword fallback.
    "exec_title_dark": [
        # exec aliases
        "exec_title", "executive cover", "board cover", "investor cover",
        "pitch cover", "exec title", "executive title",
        # legacy title layouts → all route to the dark exec cover
        "title_hero", "title_image", "title_split",
        "title slide", "hero", "intro slide", "opening slide", "cover slide",
        "title with image", "hero image", "cover with image",
        "split title", "title split", "half image title",
    ],
    "exec_three_pillars": [
        # exec aliases
        "exec_pillars", "three pillars", "what is", "product overview",
        "framework", "platform overview", "three pillar",
        # legacy three-up layouts
        "three_cards", "3 card", "three card", "3 box", "three box",
        "triple", "3 section", "three section",
    ],
    "exec_action_card": [
        # exec aliases
        "exec_pillar_detail", "before after", "how it works detail",
        "pillar detail", "deep dive", "stat card", "time to value", "before/after",
        # legacy two-column / comparison / process / timeline layouts
        "two_columns", "two column", "2 column", "side by side", "two_column",
        "comparison", "compare", "versus", "vs", "pros cons", "option a option b",
        "process_steps", "process", "steps", "flow", "workflow", "stages",
        "phases", "step by step", "process diagram", "lifecycle", "pipeline",
        "timeline", "milestones", "history", "roadmap", "chronological", "journey",
        "image_left", "image_right",
    ],
    "exec_argument": [
        # exec aliases — the workhorse, catches every generic body-slide layout
        "exec_argument", "argument", "body slide", "claim with bullets",
        "default body", "default content", "generic body", "evidence",
        # legacy bullets / quote / section_break — all become the workhorse
        "bullets", "bullets_with_image", "bullet", "bullet points", "list",
        "points", "bullet list", "bullet_points", "title_content",
        "bullets image", "list image", "points with photo",
        "quote", "quotation", "testimonial", "citation",
        "section_break", "section", "divider", "chapter", "break", "transition",
        "modern_geometric", "modern", "geometric", "abstract", "creative", "dynamic",
        "image_focus",  # legacy outline alias — no images in exec; route to argument
    ],
    "exec_stat_grid_4": [
        # exec aliases
        "exec_stat_grid", "exec_stats", "business impact", "four stats",
        "stat grid", "kpi grid", "by the numbers", "savings",
        # legacy stats / big-number / 4-card / data-dashboard / chart layouts
        "four_cards", "4 card", "four card", "4 box", "four box", "quadruple", "4 section",
        "stats_highlight", "3 stats", "three numbers", "key metrics", "3 metrics",
        "big_number", "big number", "single stat", "one number", "hero metric", "main stat",
        "data_dashboard", "dashboard", "analytics", "data",
        "chart_focus", "chart_left", "chart_right", "chart_and_image",
        "chart", "graph", "bar chart", "pie chart", "visualization",
        "chart left", "chart right", "chart with text", "text with chart",
        "chart and image", "chart with image",
    ],
    "exec_features_2x2": [
        "exec_features", "features 2x2", "four features", "capabilities",
        "feature grid", "value props", "2x2",
    ],
    "exec_industries_2x2": [
        "exec_industries", "industries", "use cases grid", "verticals",
        "where it works", "applications", "industries 2x2",
    ],
    "exec_sovereignty_dark": [
        "exec_sovereignty", "architecture", "sovereignty", "security",
        "governance", "trust", "zero copy", "zero etl", "data residency",
    ],
    "exec_chat_example": [
        "exec_chat_example", "exec_chat", "chat example", "live example",
        "product demo", "qa example", "ask example", "deep research example",
        # legacy diagram-ish layouts that don't fit elsewhere
        "infographic_diagram", "infographic", "diagram", "visual breakdown",
        "concept diagram", "anatomy", "cycle diagram", "venn", "funnel diagram",
        "system diagram", "full_bleed_image", "full image", "full bleed",
        "background image", "cinematic", "full screen image",
        "org_hierarchy", "hierarchy", "org chart", "organization chart",
        "reporting structure", "team structure", "taxonomy", "tree diagram",
        "decision tree",
    ],
    "exec_closing_dark": [
        # exec aliases
        "exec_closing", "why buy", "strategic reasons", "executive closing",
        "four reasons", "next steps cta", "ask slide",
        # legacy closing
        "closing", "end", "thank you", "thanks", "conclusion", "final", "contact",
    ],
}


# ============================================================================
# Deck profiles — three operating modes for the matcher.
# ============================================================================
# The user picks ONE profile per deck at the goal-setting step. The matcher
# (LLM + keyword fallback) only considers templates listed in that profile.
# Default is ``corporate_boardroom`` — matches the Cowork executive aesthetic.
# Other profiles open up legacy templates that are otherwise hidden.
# ============================================================================

# Deck profiles — TWO only as of 2026-05-19:
#   - "corporate" (merged executive + visuals catalog, always emits a
#     deck-coherent background image so every slide reads as part of one
#     book)
#   - "general"   (free-style: full template library, AI decides bg per slide)
#
# The previous three-profile split (corporate_boardroom / corporate_with_visuals
# / general_with_images) is preserved as aliases so any client still sending
# the old strings keeps working.
DECK_PROFILE_CORPORATE = "corporate"
DECK_PROFILE_GENERAL = "general"

# Legacy aliases (kept so older requests/UIs don't break).
DECK_PROFILE_CORPORATE_BOARDROOM = "corporate_boardroom"          # alias → corporate
DECK_PROFILE_CORPORATE_WITH_VISUALS = "corporate_with_visuals"    # alias → corporate
DECK_PROFILE_GENERAL_WITH_IMAGES = "general_with_images"          # alias → general

_EXEC_TEMPLATE_IDS = [
    "exec_title_dark", "exec_three_pillars", "exec_argument",
    "exec_action_card", "exec_stat_grid_4", "exec_features_2x2",
    "exec_industries_2x2", "exec_sovereignty_dark", "exec_chat_example",
    "exec_closing_dark",
]

# Chart / data-viz / diagram / selective-hero-image legacy templates that
# round out the unified corporate catalog. Photo-rich full-bleed layouts
# stay in the general profile.
#
# Pruned from corporate (and the rationale):
#   - chart_left / chart_right → image_left/image_right cover the split layout
#                                 with charts (has_chart=True). Two extra IDs
#                                 with the same shape just confused the matcher.
#   - data_dashboard           → exec_stat_grid_4 is the canonical 4-metric
#                                 layout for corporate; chart_focus + chart_and_image
#                                 cover the other chart use cases. data_dashboard
#                                 added a 4-quadrant variant that rarely won.
_CORPORATE_VISUAL_EXTRAS = [
    # Chart-focused (kept: single big chart + chart-paired-with-image)
    "chart_focus", "chart_and_image",
    "stats_highlight", "big_number",
    # Diagrams (org / process / timeline / infographic)
    "process_steps", "org_hierarchy", "infographic_diagram", "timeline",
    # Selective single-hero image (title only — no full-bleed)
    "title_image", "image_left", "image_right",
    # Neutral non-image layouts that complement exec
    "two_columns", "three_cards", "four_cards", "comparison",
    "section_break", "quote",
]

# Shared catalog used by both the canonical "corporate" key and its legacy
# aliases. Building once keeps the alias entries identical.
_CORPORATE_TEMPLATE_IDS = list(_EXEC_TEMPLATE_IDS) + list(_CORPORATE_VISUAL_EXTRAS)

_CORPORATE_PROFILE = {
    "label": "Corporate",
    "description": (
        "Unified executive deck — typography-led layouts, strategic charts, "
        "diagrams, and a deck-coherent photographic background on every "
        "slide (the storyboard pass derives a single bg motif so the deck "
        "reads as one artefact). Best for board / investor / pitch / sales "
        "/ customer-facing / product / strategic-review decks."
    ),
    "template_ids": _CORPORATE_TEMPLATE_IDS,
    "always_background_image": True,   # storyboard derives the bg style; every slide gets one.
}

# General-profile catalog — explicit allowlist (not None) so we can drop
# templates that are redundant with cleaner alternatives. The originals stay
# in SLIDE_TEMPLATES for back-compat (any saved deck referencing them still
# renders) but the matcher no longer offers them for NEW generations.
#
# Dropped from general (and the rationale):
#   - chart_left / chart_right   → image_left / image_right already declare
#                                   has_chart=True and render charts identically.
#                                   Two extra IDs added noise to the matcher
#                                   without offering a distinct visual.
#   - data_dashboard             → a four-quadrant chart grid that competed
#                                   with chart_focus (single big chart) and
#                                   chart_and_image. Rarely the right pick.
#   - bullets                    → bullets_with_image always wins (matcher
#                                   already upgraded bullets→bullets_with_image
#                                   everywhere). Keeping both bloats choices.
#   - exec_* family              → corporate-only; general profile pulls from
#                                   the broader photo-rich library, not the
#                                   typography-led exec catalog.
_GENERAL_TEMPLATE_IDS = [
    # Title / cover
    "title_hero", "title_image", "title_split", "full_bleed_image",
    # Body / content
    "bullets_with_image", "two_columns", "three_cards", "four_cards",
    "modern_geometric",
    # Image-rich split layouts
    "image_left", "image_right",
    # Charts (kept: chart_focus + chart_and_image cover the two distinct shapes)
    "chart_focus", "chart_and_image",
    # Stats
    "stats_highlight", "big_number",
    # Structural / narrative
    "process_steps", "org_hierarchy", "infographic_diagram",
    "comparison", "timeline", "section_break", "quote",
    # Closing
    "closing",
]

_GENERAL_PROFILE = {
    "label": "General",
    "description": (
        "Photo-rich, free-form template library — title covers, full-bleed "
        "imagery, image+text splits, and the core narrative layouts (stats, "
        "comparison, process, timeline). Best for marketing, training, or "
        "casual decks where strong imagery matters. The AI decides per-slide "
        "whether to add a background image."
    ),
    "template_ids": _GENERAL_TEMPLATE_IDS,
    "always_background_image": False,     # AI per-slide call
}

DECK_PROFILES: Dict[str, Dict[str, Any]] = {
    DECK_PROFILE_CORPORATE: _CORPORATE_PROFILE,
    DECK_PROFILE_GENERAL:   _GENERAL_PROFILE,
    # ---- legacy aliases ----
    DECK_PROFILE_CORPORATE_BOARDROOM:    _CORPORATE_PROFILE,
    DECK_PROFILE_CORPORATE_WITH_VISUALS: _CORPORATE_PROFILE,
    DECK_PROFILE_GENERAL_WITH_IMAGES:    _GENERAL_PROFILE,
}


def profile_always_emits_background(profile: Optional[str]) -> bool:
    """Returns True when the profile requires a background image on every
    slide/page. Used by per-slide/page generation to decide whether the
    bg_image_rule says "DO NOT EMIT" vs "REQUIRED — use the deck's shared
    background style from the storyboard"."""
    p = DECK_PROFILES.get(profile or "") or DECK_PROFILES.get(DECK_PROFILE_CORPORATE, {})
    return bool(p.get("always_background_image"))


def get_profile_template_catalog(profile: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Return the subset of SLIDE_TEMPLATES visible to ``profile``.

    Unknown / missing profile defaults to Corporate Boardroom. Profile
    with ``template_ids = None`` returns the whole catalog.
    """
    profile_key = profile if profile in DECK_PROFILES else DECK_PROFILE_CORPORATE_BOARDROOM
    allowed = DECK_PROFILES[profile_key].get("template_ids")
    if allowed is None:
        return dict(SLIDE_TEMPLATES)
    return {tid: SLIDE_TEMPLATES[tid] for tid in allowed if tid in SLIDE_TEMPLATES}


def template_in_profile(template_id: str, profile: Optional[str]) -> bool:
    """Cheap check used by the keyword fallback to skip out-of-profile hits."""
    profile_key = profile if profile in DECK_PROFILES else DECK_PROFILE_CORPORATE_BOARDROOM
    allowed = DECK_PROFILES[profile_key].get("template_ids")
    if allowed is None:
        return template_id in SLIDE_TEMPLATES
    return template_id in allowed


def match_template_from_instruction(instruction: str) -> Optional[str]:
    """
    Match user instruction to a template ID based on keywords.
    
    Args:
        instruction: User's layout/structural change request
        
    Returns:
        Template ID if matched, None otherwise
    """
    instruction_lower = instruction.lower()
    
    # Check each template's keywords
    for template_id, keywords in TEMPLATE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in instruction_lower:
                return template_id
    
    return None


# ==================== Helper Functions ====================

def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    """Get template by ID."""
    return SLIDE_TEMPLATES.get(template_id)


def get_template_list() -> List[Dict[str, Any]]:
    """Get all templates as a list."""
    return list(SLIDE_TEMPLATES.values())


def get_templates_by_category(category: str) -> List[Dict[str, Any]]:
    """Get templates filtered by category."""
    return [t for t in SLIDE_TEMPLATES.values() if t.get("category") == category]


def _compute_slot_content_hint(slot_name: str, slot_def: dict) -> str:
    """
    Generate a dimension-aware content hint for an AI slot.
    Computes approximate max characters from slot pixel dimensions and fontSize,
    then produces a concise hint that prevents text overflow.
    """
    import re
    text_type = slot_def.get("textType", "body")
    width = slot_def.get("width", 400)
    height = slot_def.get("height", 100)
    font_size = slot_def.get("fontSize", 20)
    line_height = slot_def.get("lineHeight", 1.4 if text_type == "body" else 1.2)
    
    # Estimate capacity: how many chars fit in this box
    char_width_ratio = 0.48  # average char width as fraction of fontSize
    chars_per_line = max(1, int(width / (font_size * char_width_ratio)))
    max_lines = max(1, int(height / (font_size * line_height)))
    max_chars = chars_per_line * max_lines

    # --- Pattern-based hints for known slot types ---

    # stat_value slots: large bold numbers ONLY (e.g. "3B", "29%", "100+").
    # Covers both `stat\d*_value` (legacy templates) AND `s\d+_value` /
    # `r\d+_value` / `right_(before|after)_value` (exec_* templates) — the
    # generic title hint was telling them "write 4-5 words" which guarantees
    # overflow in a 168x70 box at 48px.
    if (re.match(r'stat\d*_value$', slot_name)
            or re.match(r's\d+_value$', slot_name)
            or re.match(r'r\d+_value$', slot_name)
            or re.match(r'right_(before|after)_value$', slot_name)):
        return f"ONLY a short number or symbol (e.g. '3B', '29%', '$1.2M', '100+'). NO words — put descriptive words like 'Days', 'Users', 'Stages' in the corresponding *_label slot. STRICTLY max {max_chars} chars — this is {font_size}px bold in a {width}x{height}px box, anything longer WILL overflow and render as garbled text."

    # metric slot (big_number template) and metric#_value slots (data_dashboard): hero stat, very large font
    if slot_name == "metric" or re.match(r'metric\d*_value$', slot_name):
        return f"ONLY a short number or symbol (e.g. '$1.2B', '42%', '10M+'). NO words — put descriptive words in the label slot. STRICTLY max {max_chars} chars — this is {font_size}px bold in a {width}x{height}px box, anything longer WILL overflow and render as garbled text."

    # closing-card step numbers ('01', '02', '03', '04') in exec_closing_dark.
    # 44px bold in a 100x66 box, hint was "write FULL title 4-5 words" — those
    # 4-5 words ended up overlapping the title text next to the number.
    if re.match(r'c\d+_number$', slot_name):
        return "ONLY a 2-character step number ('01', '02', '03', '04'). NO words, NO punctuation. Anything else WILL overlap the card title."

    # stat / result / right-side LABEL slots (concise label below a value).
    if (re.match(r'stat\d*_label$', slot_name)
            or re.match(r's\d+_label$', slot_name)
            or re.match(r'r\d+_label$', slot_name)
            or re.match(r'right_(before|after)_label$', slot_name)):
        max_words = max(2, min(5, max_chars // 8))
        return f"1-{max_words} words MAX, concise label (e.g. 'Active Users', 'Q4 Growth'). NO sentences. Max {max_chars} chars in {width}px box."

    # right_*_unit slots in exec_action_card — short unit text like '/ month'.
    if re.match(r'right_(before|after)_unit$', slot_name):
        return f"1-3 words MAX, unit only (e.g. '/ month', 'per quarter', 'million users'). Max {max_chars} chars."

    # stat_desc / r#_sub slots: brief descriptions inside narrow cards
    if re.match(r'stat\d*_desc$', slot_name) or re.match(r'r\d+_sub$', slot_name):
        return f"1 short sentence MAX (~{max_chars} chars). Fits in {width}x{height}px at {font_size}px"

    # CARD-TITLE patterns inside exec templates — `p\d+_title` (pillars),
    # `c\d+_title` (closing), `f\d+_title` (features), `z\d+_title` (sovereignty),
    # `i\d+_name` (industries), `d\d+_title` (stat-grid detail). Default hint
    # was treating these as full subtitles (8+ words) and they overflowed.
    if (re.match(r'(p|c|f|z|d)\d+_title$', slot_name)
            or re.match(r'i\d+_name$', slot_name)):
        max_words = max(2, min(5, max_chars // 7))
        return f"2-{max_words} words MAX, concise card heading. NO articles like 'The' or 'A'. Max {max_chars} chars in {width}px."

    # CARD-BODY patterns inside exec templates — short descriptive paragraph
    # in a narrow card. Was getting "1-2 sentences ~144 chars" but the LLM
    # often produced 2-3 sentences that overflowed.
    if (re.match(r'(p|c|f|z|d)\d+_body$', slot_name)
            or re.match(r'i\d+_uses$', slot_name)):
        # ~14 words ≈ 84 chars per sentence. Cap by box capacity.
        max_sentences = 1 if max_chars < 110 else 2
        return f"{max_sentences} short {'sentence' if max_sentences == 1 else 'sentences'} MAX (~{max_chars} chars total, ≤14 words per sentence). MUST fit in {width}x{height}px at {font_size}px — DO NOT exceed."

    # Pillar/feature LABEL slots (small kicker above the card title).
    if re.match(r'(p|f|z|c)\d+_label$', slot_name):
        return f"1-3 words MAX, an UPPERCASE category tag (e.g. 'GROWTH', 'OPERATIONS'). Max {max_chars} chars."

    # Governance / inline-detail mini text (g\d+_title / g\d+_body).
    if re.match(r'g\d+_title$', slot_name):
        return f"1-2 words MAX. Max {max_chars} chars in {width}px."
    if re.match(r'g\d+_body$', slot_name):
        return f"1 SHORT phrase MAX (~{max_chars} chars). NOT a full sentence."

    # Pills (exec_title_dark) — three-up nav-style chips. ~13px bold, 260x28.
    if re.match(r'pill_\d+$', slot_name):
        return f"1-4 words MAX, a concept tag (e.g. 'Emerging Markets'). Max {max_chars} chars."

    # brand_chip (exec_title_dark) — top-left brand badge.
    if slot_name == "brand_chip":
        return f"2-4 words MAX, the deck's brand identifier (e.g. 'bp Energy Outlook 2025'). Max {max_chars} chars."

    # Action-card titles (left_title / right_title in exec_action_card).
    if slot_name in ("left_title", "right_title"):
        max_words = max(2, min(5, max_chars // 7))
        return f"2-{max_words} words MAX, concise section title. Max {max_chars} chars in {width}px."

    # right_kicker / chat_kicker / right_list_label — short label rows.
    if slot_name in ("right_kicker", "chat_kicker", "right_list_label"):
        return f"3-7 words MAX, short label/lead-in. Max {max_chars} chars."

    # Chat-example specifics (exec_chat_example).
    if slot_name == "user_question":
        return f"1 SHORT question MAX (~{max_chars} chars, ≤12 words). Must read like a user typed it — no formal punctuation."
    if slot_name == "answer_headline":
        return f"1 short headline MAX (~{max_chars} chars). NO trailing period."
    if slot_name == "answer_subline":
        return f"1 SHORT supporting line MAX (~{max_chars} chars)."
    if slot_name == "source_text":
        return f"1 short citation (~{max_chars} chars, e.g. 'Source: bp Outlook 2025')."

    # CTA / takeaway / banner — single-line bottom strip text.
    if slot_name in ("cta_text", "takeaway"):
        max_words = max(8, min(18, max_chars // 5))
        return f"1 SHORT impactful sentence ({max_words} words MAX, ~{max_chars} chars). Single line — overflow makes the bottom strip unreadable."
    if slot_name in ("banner", "banner_text"):
        return f"1 short sentence MAX (~{max_chars} chars). Footer band — overflow breaks the slide rhythm."

    # Section heading inside data-dashboard / stat_grid detail row.
    if slot_name in ("detail_heading", "gov_heading"):
        return f"1 short sentence MAX (~{max_chars} chars, ≤14 words). Section lead-in only."

    # step_title slots: short step names in narrow columns
    if re.match(r'step\d*_title$', slot_name):
        max_words = max(2, min(5, max_chars // 6))
        return f"2-{max_words} words, concise step name. Max {max_chars} chars in {width}px box"

    # step_desc slots: brief descriptions in narrow columns
    if re.match(r'step\d*_desc$', slot_name):
        max_sentences = max(1, min(3, max_lines // 3))
        return f"1-{max_sentences} concise sentences (~{max_chars} chars). Fits in {width}x{height}px at {font_size}px"

    # card_title, card_desc patterns
    if re.match(r'card\d*_title$', slot_name):
        max_words = max(2, min(6, max_chars // 6))
        return f"2-{max_words} words, concise card heading. Max {max_chars} chars"

    if re.match(r'card\d*_desc$', slot_name):
        return f"1-2 short sentences (~{max_chars} chars). Fits in {width}x{height}px"
    
    # --- Generic hints based on textType ---

    # Top-level slide kicker — short uppercase tag above the title.
    # Previously got "1-2 sentences ~104 chars" via fallback, encouraging
    # paragraph-length kickers that overflow the 20-22px-tall strip.
    if text_type == "kicker" and slot_name == "kicker":
        max_words = max(3, min(8, max_chars // 10))
        return f"3-{max_words} words MAX, an UPPERCASE category tag (e.g. 'STRATEGIC OUTLOOK 2026'). Max {max_chars} chars. NEVER write a sentence here."

    # Top-level slide subhead — single sentence under the title.
    if slot_name == "subhead":
        max_words = max(8, min(20, max_chars // 5))
        return f"1 sentence MAX (~{max_words} words, {max_chars} chars). Single line of supporting context — never two sentences."

    if text_type == "title":
        # Titles: dimension-aware word count. Removed the "NEVER truncate"
        # pressure for small boxes — that wording was inflating titles in
        # constrained card slots.
        max_words = max(4, min(12, max_chars // 5))
        if max_chars < 50:
            return f"4-{max_words} words MAX, impactful heading (~{max_chars} chars). Short box — keep it tight."
        return f"4-{max_words} words, impactful heading (~{max_chars} chars). Write a complete title — no ellipses."

    if text_type == "subtitle":
        # Was "8-N words" universally — but inside narrow cards this is
        # already covered by the card-title pattern above. By here we're
        # only at the generic subtitle, so cap at the box capacity.
        max_words = max(5, min(20, max_chars // 5))
        return f"{max_words} words MAX, supporting context (~{max_chars} chars). No ellipses."
    
    # Bullet slots
    if "bullet" in slot_name:
        # Estimate bullet count from available lines
        lines_per_bullet = 2  # each bullet wraps to ~2 lines
        max_bullets = max(3, min(6, max_lines // lines_per_bullet))
        chars_per_bullet = chars_per_line * lines_per_bullet
        return f"{max_bullets} bullet points, each ~{chars_per_bullet} chars max. Total must fit in {width}x{height}px"
    
    if "key_takeaway" in slot_name or "insight" in slot_name:
        return f"1 impactful sentence (~{max_chars} chars max)"
    
    if "detail" in slot_name or "description" in slot_name or "tagline" in slot_name:
        return f"1-2 sentences (~{max_chars} chars max)"
    
    if "source" in slot_name or "context" in slot_name:
        return f"1 sentence with attribution (~{max_chars} chars max)"
    
    # Fallback: compute from dimensions
    if max_chars < 80:
        return f"1 short sentence (~{max_chars} chars max). Small text box: {width}x{height}px"
    elif max_chars < 200:
        return f"1-2 sentences (~{max_chars} chars max)"
    else:
        return f"2-3 sentences (~{max_chars} chars max). Fits in {width}x{height}px"


def get_slot_prompt_format(template_id: str) -> str:
    """
    Generate a prompt format showing which slots the AI needs to fill.
    Used in the system prompt to guide AI output.
    """
    template = SLIDE_TEMPLATES.get(template_id)
    if not template:
        return ""
    
    lines = [f"TEMPLATE: {template['name']} ({template['description']})"]
    lines.append("SLOTS TO FILL (you MUST provide content for EVERY slot listed below):")
    lines.append("CRITICAL: Each text slot has a FIXED pixel box. Content MUST fit within it or text will overlap. Follow the character limits strictly.")
    
    for slot_name, slot_def in template["slots"].items():
        slot_type = slot_def["type"]
        is_required = slot_name in template.get("required_slots", [])
        is_optional = slot_name in template.get("optional_slots", [])
        req_marker = "(REQUIRED)" if is_required else "(OPTIONAL)" if is_optional else "(MUST FILL)"
        
        if slot_type == "text":
            hint = _compute_slot_content_hint(slot_name, slot_def)
            lines.append(f'  - {slot_name}: {{ "content": "{hint}", "fill": "#RRGGBB" (optional) }} {req_marker}')
        elif slot_type == "icon":
            lines.append(f'  - {slot_name}: {{ "iconName": "lucide-icon-name", "fill": "#RRGGBB" (optional) }} {req_marker}')
        elif slot_type == "image_placeholder":
            if is_optional:
                lines.append(f'  - {slot_name}: {{ "imageDescription": "Small contextual/decorative photo (15+ words: subject, style, mood)", "imageType": "photo" }} (OPTIONAL — include only if a small accent image would visually enrich this slide)')
            else:
                lines.append(f'  - {slot_name}: {{ "imageDescription": "Detailed photo description (15+ words: subject, style, mood, lighting)", "imageType": "photo" }} {req_marker}')
        elif slot_type == "chart":
            lines.append(f'  - {slot_name}: {{ "chartConfig": {{ "type": "bar|line|pie|doughnut|radar|polarArea|scatter|bubble", "data": {{ "labels": ["Label1","Label2",...], "datasets": [{{ "label": "Series", "data": [val1,val2,...], "backgroundColor": ["#hex1",...] }}] }} }} }} {req_marker}')
        elif slot_type == "visual":
            lines.append(f'  - {slot_name}: VISUAL SLOT — AI decides: return EITHER {{ "type": "chart", "chartConfig": {{ "type": "bar|line|pie|doughnut|radar|polarArea|scatter|bubble", "data": {{ "labels": [...], "datasets": [{{...}}] }} }} }} for data visualizations, OR {{ "type": "image_placeholder", "imageDescription": "Detailed photo description (15+ words)", "imageType": "photo" }} for illustrative images. Choose chart when slide content involves data/stats/numbers/trends; choose image when content is narrative/conceptual/visual. {req_marker}')
        elif slot_type == "svg_diagram":
            kind = slot_def.get("diagramKind", "diagram")
            sw = slot_def.get("width", 900)
            sh = slot_def.get("height", 410)
            lines.append(f'  - {slot_name}: DIAGRAM / ILLUSTRATION SVG SLOT (kind="{kind}"). The slide is 960x540 (16:9); your SVG occupies a {sw}x{sh}px area. Sibling text slots (`intro`, `takeaway`/`caption`) handle the prose around it — DO NOT embed paragraphs of body text inside the SVG. Return {{ "svgContent": "<svg width=\\"{sw}\\" height=\\"{sh}\\" viewBox=\\"0 0 {sw} {sh}\\" preserveAspectRatio=\\"xMidYMid meet\\" xmlns=\\"http://www.w3.org/2000/svg\\">…</svg>", "fillColor": "#RRGGBB" (optional accent override) }}. {req_marker}')
            lines.append(f'      DESIGN INTENT (CRITICAL — KEEP IT SIMPLE & CRISP):')
            lines.append(f'        - This is the VISUAL ONLY. Sibling `intro` and `takeaway`/`caption` text slots carry the explanation — DO NOT duplicate that text inside the SVG.')
            lines.append(f'        - The SVG can be ANYTHING that best illustrates the topic in {sw}x{sh}px: a node-and-arrow diagram, a tree, a cycle, a funnel, a venn, an anatomical sketch, a molecular/biological structure (e.g. protein folding, cell, neuron), an architectural cross-section, a flowing organic illustration, etc. Pick whatever shape language communicates the idea most clearly. You are NOT required to use boxes/nodes.')
            lines.append(f'        - Aim for a SIMPLE, CLEAN, editorial illustration. Fewer, well-placed elements beat many crammed ones. NO clutter.')
            lines.append(f'        - TEXT IS MINIMAL: at most a handful of short labels (1-3 words preferred, ≤5 words hard max) for the few key parts. NO long sentences, NO arrow annotations, NO callouts, NO legends, NO paragraph blocks.')
            lines.append(f'        - TEXT MUST FIT: if a label is wider than the shape it sits on, SHORTEN the label or move it adjacent — never let text overflow or get clipped at the edge. Keep ≥12px clear space inside any container shape.')
            lines.append(f'        - HARD BOUNDS: every drawn point (x,y) must satisfy 20 ≤ x ≤ {sw - 20} and 20 ≤ y ≤ {sh - 20}. NEVER cross those edges.')
            lines.append(f'        - FILL THE CANVAS — DO NOT cluster everything in one corner or leave a wide empty margin. The leftmost element must anchor near x≈20-40, the rightmost near x≈{sw - 40}-{sw - 20}, the topmost near y≈20-40, and the bottommost near y≈{sh - 40}-{sh - 20}. Distribute elements to span the FULL {sw}x{sh} area.')
            lines.append(f'        - The root <svg> MUST use viewBox="0 0 {sw} {sh}" with width="{sw}" and height="{sh}". DO NOT pick a different viewBox (e.g. 920x320) — the slot is exactly {sw}x{sh}px and any other viewBox will displace your content.')
            lines.append(f'        - USE the {sw}x{sh}px area, but CENTER and BALANCE. Leave breathing room.')
            lines.append(f'        - DO NOT add unrelated decorative shapes (random triangles, wedges, blobs, background bands). Every shape must serve the illustration. NO red/orange error indicators unless the topic is explicitly about errors/failures.')
            lines.append(f'        - BACKGROUND MUST BE TRANSPARENT. Do NOT emit a full-canvas background <rect> (e.g. covering 0,0 to {sw},{sh}) or set a `background` style on the root <svg>. The SVG renders over a themed slide background — any opaque backdrop will clash with the slide.')
            lines.append(f'        - Establish visual hierarchy via SIZE and COLOR: a hero element larger and gradient-filled, supporting elements smaller and solid-filled.')
            lines.append(f'      SVG TECHNICAL RULES:')
            lines.append(f'        - The <svg> root MUST set width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}" preserveAspectRatio="xMidYMid meet".')
            lines.append(f'        - <circle> / <ellipse> use cx and cy (NEVER x/y). <rect> / <text> use x/y. Mixing these places elements at (0,0).')
            lines.append(f'        - Use `currentColor` for primary fills/strokes. The UI substitutes it with the theme accent color before rendering.')
            lines.append(f'        - You MAY use a small palette (up to 4 explicit hex colors) for emphasis, category coding, or contrast; everything else should use `currentColor`.')
            lines.append(f'        - LOOK POLISHED BUT RESTRAINED: define 1 inline <linearGradient> in <defs> and apply it to the HERO element only. Pick gradient stops from a vibrant modern palette (indigo #6366F1, violet #8B5CF6, sky #0EA5E9, teal #14B8A6, emerald #10B981, amber #F59E0B). Use 2-4 distinct colors total — not a rainbow. White/near-white text on saturated fills.')
            lines.append(f'        - Allowed primitives: <rect>, <circle>, <ellipse>, <line>, <path>, <polyline>, <polygon>, <text>, <tspan>, <g>, inline <defs><marker>/<linearGradient>. NO <foreignObject>, NO <script>, NO external <image href>, NO <style> blocks, NO class= attributes.')
            lines.append(f'        - For arrows/flows: simple <line>/<path> with one arrowhead marker. NO text on connector lines.')
            lines.append(f'        - NEVER draw an arrow that points into empty space. EVERY arrow MUST start at one node and end exactly at another node — the arrowhead must touch a real, drawn shape. If you have N nodes, finish drawing all N before adding any connectors. Do NOT leave dangling/orphan arrows.')
            lines.append(f'        - ARROWS MUST STOP AT SHAPE BOUNDARIES, NEVER AT THE CENTER. The arrow\'s start and end points must lie ON the BORDER (outer edge) of each connected shape, not inside it. For a circle radius `r` at (cx,cy), end the arrow on the circumference (offset by r from the center, along the line toward the source). For a rectangle, end at the relevant edge. Leave ~4-6px of breathing room between the arrowhead tip and the shape\'s border so the arrowhead is visible OUTSIDE the shape and never overlaps any label text inside it.')
            lines.append(f'        - CONNECTOR ENDPOINT MATH (CRITICAL — 2-pass plan): PASS 1: Before drawing any connector, write down each shape\'s exact bounding box. For <rect x="X" y="Y" width="W" height="H">: top-center=(X+W/2, Y), bottom-center=(X+W/2, Y+H), left-center=(X, Y+H/2), right-center=(X+W, Y+H/2). For <circle cx="CX" cy="CY" r="R"> the edge point toward (PX,PY) is (CX + R*dx/len, CY + R*dy/len) where dx=PX-CX, dy=PY-CY, len=sqrt(dx*dx+dy*dy). PASS 2: Compute every <line>/<path> connector\'s (x1,y1) and (x2,y2) from those anchor formulas — NEVER eyeball them. For a VERTICAL connector between two stacked rects, x1 MUST equal x2 (the column center-x), y1 MUST equal sourceRect.bottom, y2 MUST equal targetRect.top minus 4-6px (arrowhead breathing room). For a HORIZONTAL connector, y1 MUST equal y2 (the row center-y). SELF-CHECK each connector before emitting: (x1,y1) must be an exact anchor of the source shape, (x2,y2) must be an exact anchor of the target shape with the small inset. Endpoints that do not match any shape\'s edge coordinate make lines look DETACHED / FLOATING / DISCONNECTED — the #1 SVG failure mode. REWORK any connector that fails this check.')
            lines.append(f'        - Labels: <text font-family="Inter, Arial" font-size="14-18" fill="currentColor"> with inline style. Single line per label; an optional second sub-label line via <tspan> (≤3 words, opacity 0.7) is fine.')
            lines.append(f'        - Keep markup under ~8 KB (~25 elements max). Simpler always wins.')
            if kind == "process":
                lines.append(f'        - kind="process": show a clear sequence — could be linear stage shapes connected by arrows, an arc, a spiral, or a stylized pipeline. Each stage gets a SHORT name (1-3 words). Detailed descriptions go in the sibling `takeaway` text slot.')
            elif kind == "hierarchy":
                lines.append(f'        - kind="hierarchy": show a tree / org-style relationship. Could be classic boxes-and-lines, a radial tree, or a layered structure. Each item: ONE short NAME (bold), optional sub-line for role (≤3 words, opacity 0.7). Detailed descriptions go in the sibling `caption` text slot.')
            elif kind == "infographic":
                lines.append(f'        - kind="infographic": pick whatever metaphor or illustration fits the topic — cycle, venn, funnel, pyramid, anatomical sketch, molecular/biological structure, architectural cross-section, organic flowing illustration, etc. Each labeled region gets ONE short NAME (1-3 words). Detailed explanation goes in the sibling `caption` text slot.')
            lines.append(f'        - DO NOT include the slide title inside the SVG — the title slot above renders it separately.')
    
    lines.append('  - backgroundColor: "#RRGGBB" (optional, to override slide background)')
    lines.append('  - background_image: { "imageDescription": "Abstract artistic background description (15+ words, PHOTO ONLY, no text/labels)" } (optional, AI decides if a decorative background image would enhance this slide.)')
    lines.append('')
    lines.append('IMAGE DESCRIPTION RULES (CRITICAL — applies to BOTH `imageDescription` slots AND `background_image.imageDescription`):')
    lines.append('  - ABSOLUTELY NO text, words, letters, numbers, labels, captions, titles, headlines, watermarks, signage, typography, logos with text, infographic-style writing, or characters of any language anywhere in the image.')
    lines.append('  - DO NOT use phrases like "with the text…", "labeled …", "titled …", "reading …", "saying …", "inscribed …", "with caption …", "with sign that reads …" — these instruct the image model to render text and MUST be omitted.')
    lines.append('  - DO NOT include ANY quoted strings ("…", \'…\') in the description — quoted phrases get rendered as literal text in the image.')
    lines.append('  - For `imageDescription` (foreground image): NAME CONCRETE PHYSICAL SUBJECTS DIRECTLY (animal, plant, object, person, place, food, vehicle, building, body part, weather, landscape). Diffusion models render concrete physical nouns accurately and do NOT leak them as text. Euphemisms produce wrong subjects (e.g. "small elongated crawling creature with striped patterns" renders a lizard instead of the intended caterpillar). USE VISUAL ANALOGUES ONLY for ABSTRACT / NON-VISUAL concepts that have no physical form: technical jargon ("OAuth", "Kubernetes"), scientific processes ("Krebs cycle", "mitosis", "glycolysis", "DNA", "ATP"), business metrics ("Q3 revenue"), brand/product names — replace those with generic analogues (e.g. "interconnected organic structures with glowing nodes" instead of "Krebs cycle"). Acronyms and brand names still render as text and stay forbidden.')
    lines.append('  - For `background_image.imageDescription`: keep it ABSTRACT and TEXTURAL only — soft gradients, blurred organic shapes, abstract patterns, bokeh, atmospheric lighting. NO recognisable subjects, no scenes that suggest a named concept. This rule is stricter than the foreground rule because the background must not compete with slide content.')
    lines.append('  - For foreground `imageDescription`: pattern is <concrete subject>, <action/pose>, <setting>, <lighting>, <composition>, <colour/mood>.')
    lines.append('')
    lines.append('BODY TEXT COLOR RULE (CRITICAL): For ALL body, detail, description, bullets, content, tagline text slots:')
    lines.append('  - Dark background slide  → fill MUST be white/near-white ONLY: #FFFFFF, #F9FAFB, or #F3F4F6')
    lines.append('  - Light background slide → fill MUST be black/near-black ONLY: #111827, #1F2937, or #374151')
    lines.append('  NEVER use grey (#6B7280, #9CA3AF, #94A3B8, #475569, etc.) for body text — grey is invisible on dark backgrounds.')
    lines.append('')
    lines.append('IMPORTANT: Every text slot above MUST be filled with meaningful content. Do NOT skip any slot. The slide should look complete with no empty text areas.')
    
    return "\n".join(lines)


def get_example_json_for_template(template_id: str) -> str:
    """
    Generate an example JSON output for a specific template.
    This helps the AI understand exactly what format to produce.
    """
    import json
    template = SLIDE_TEMPLATES.get(template_id)
    if not template:
        return "{}"
    
    example = {
        "template": template_id,
        "slots": {}
    }
    
    for slot_name, slot_def in template["slots"].items():
        slot_type = slot_def["type"]
        is_required = slot_name in template.get("required_slots", [])
        
        if slot_type == "text":
            # Generate descriptive example based on slot name
            if "title" in slot_name and slot_name == "title":
                example["slots"][slot_name] = {"content": "Strategic Growth Initiatives for 2025"}
            elif "subtitle" in slot_name:
                example["slots"][slot_name] = {"content": "Exploring market opportunities and competitive advantages in the evolving landscape"}
            elif "title" in slot_name:
                example["slots"][slot_name] = {"content": f"Key Highlights for {slot_name.replace('_title', '').replace('_', ' ').title()}"}
            elif "desc" in slot_name:
                example["slots"][slot_name] = {"content": "This approach enables organizations to streamline operations and achieve measurable improvements in efficiency and performance metrics."}
            elif "content" in slot_name:
                example["slots"][slot_name] = {"content": "Our comprehensive analysis reveals significant opportunities for growth. The data indicates a 23% improvement in key performance indicators, driven by strategic investments in technology and talent development."}
            elif "bullets" in slot_name:
                example["slots"][slot_name] = {"content": "• First key point with supporting detail and context\n• Second important finding based on research data\n• Third strategic recommendation for stakeholders\n• Fourth actionable insight for implementation\n• Fifth consideration for long-term planning"}
            elif "quote" in slot_name:
                example["slots"][slot_name] = {"content": "Innovation distinguishes between a leader and a follower. The best way to predict the future is to create it."}
            elif "attribution" in slot_name:
                example["slots"][slot_name] = {"content": "— Dr. Sarah Johnson, Chief Innovation Officer, TechCorp 2024"}
            elif "key_takeaway" in slot_name or "insight" in slot_name:
                example["slots"][slot_name] = {"content": "The critical insight is that early adoption of these strategies can yield a 3x return on investment within the first 18 months of implementation."}
            elif "detail" in slot_name or "description" in slot_name:
                example["slots"][slot_name] = {"content": "This methodology has been validated across 50+ enterprise deployments, consistently delivering results above industry benchmarks."}
            elif "tagline" in slot_name:
                example["slots"][slot_name] = {"content": "Transforming challenges into competitive advantages through data-driven decisions"}
            elif "source" in slot_name or "context" in slot_name:
                example["slots"][slot_name] = {"content": "Based on comprehensive industry analysis and validated market research from 2024"}
            else:
                example["slots"][slot_name] = {"content": f"Substantive content for {slot_name} providing real value and meaningful information for the audience."}
        elif slot_type == "icon":
            example["slots"][slot_name] = {"iconName": "circle"}
        elif slot_type == "image_placeholder":
            if slot_name in template.get("optional_slots", []):
                continue  # Skip optional image placeholders in example
            example["slots"][slot_name] = {"imageDescription": "Professional corporate team collaborating around a modern conference table, warm natural lighting, glass windows with city skyline view, clean minimalist office design", "imageType": "photo"}
        elif slot_type == "chart":
            example["slots"][slot_name] = {"chartConfig": {"type": "bar", "data": {"labels": ["Q1", "Q2", "Q3", "Q4"], "datasets": [{"data": [45, 62, 78, 91], "label": "Revenue Growth (%)", "backgroundColor": ["#3B82F6", "#10B981", "#F59E0B", "#EF4444"]}]}}}
        elif slot_type == "visual":
            # For visual slots, show chart example (AI will decide based on content)
            example["slots"][slot_name] = {"type": "chart", "chartConfig": {"type": "bar", "data": {"labels": ["Q1", "Q2", "Q3", "Q4"], "datasets": [{"data": [45, 62, 78, 91], "label": "Performance Metrics"}]}}}
        elif slot_type == "svg_diagram":
            kind = slot_def.get("diagramKind", "diagram")
            sw = slot_def.get("width", 900)
            sh = slot_def.get("height", 410)
            if kind == "hierarchy":
                svg_example = (
                    f'<svg width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}" xmlns="http://www.w3.org/2000/svg">'
                    f'<defs><style>.node{{fill:none;stroke:currentColor;stroke-width:2}}.lbl{{font-family:Inter,Arial;font-size:14;fill:currentColor;text-anchor:middle}}.role{{font-size:11;opacity:0.7}}.edge{{stroke:currentColor;stroke-width:1.5;fill:none}}</style></defs>'
                    f'<rect class="node" x="380" y="20" width="140" height="50" rx="6"/><text class="lbl" x="450" y="42">CEO</text><text class="lbl role" x="450" y="58">Alex Carter</text>'
                    f'<line class="edge" x1="450" y1="70" x2="450" y2="100"/><line class="edge" x1="180" y1="100" x2="720" y2="100"/>'
                    f'<line class="edge" x1="180" y1="100" x2="180" y2="130"/><line class="edge" x1="450" y1="100" x2="450" y2="130"/><line class="edge" x1="720" y1="100" x2="720" y2="130"/>'
                    f'<rect class="node" x="110" y="130" width="140" height="50" rx="6"/><text class="lbl" x="180" y="152">CTO</text><text class="lbl role" x="180" y="168">Engineering</text>'
                    f'<rect class="node" x="380" y="130" width="140" height="50" rx="6"/><text class="lbl" x="450" y="152">CFO</text><text class="lbl role" x="450" y="168">Finance</text>'
                    f'<rect class="node" x="650" y="130" width="140" height="50" rx="6"/><text class="lbl" x="720" y="152">COO</text><text class="lbl role" x="720" y="168">Operations</text>'
                    f'</svg>'
                )
            elif kind == "process":
                svg_example = (
                    f'<svg width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}" xmlns="http://www.w3.org/2000/svg">'
                    f'<defs><marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker><style>.box{{fill:none;stroke:currentColor;stroke-width:2}}.num{{font-family:Inter,Arial;font-size:18;font-weight:700;fill:currentColor;text-anchor:middle}}.lbl{{font-family:Inter,Arial;font-size:13;fill:currentColor;text-anchor:middle}}.edge{{stroke:currentColor;stroke-width:2;fill:none}}</style></defs>'
                    f'<rect class="box" x="40"  y="140" width="180" height="120" rx="10"/><text class="num" x="130" y="180">1</text><text class="lbl" x="130" y="210">Transcription</text><text class="lbl" x="130" y="230">DNA → mRNA</text>'
                    f'<rect class="box" x="260" y="140" width="180" height="120" rx="10"/><text class="num" x="350" y="180">2</text><text class="lbl" x="350" y="210">Processing</text><text class="lbl" x="350" y="230">Splicing &amp; capping</text>'
                    f'<rect class="box" x="480" y="140" width="180" height="120" rx="10"/><text class="num" x="570" y="180">3</text><text class="lbl" x="570" y="210">Translation</text><text class="lbl" x="570" y="230">mRNA → protein</text>'
                    f'<rect class="box" x="700" y="140" width="180" height="120" rx="10"/><text class="num" x="790" y="180">4</text><text class="lbl" x="790" y="210">Folding</text><text class="lbl" x="790" y="230">Active 3D structure</text>'
                    f'<line class="edge" x1="220" y1="200" x2="260" y2="200" marker-end="url(#arr)"/>'
                    f'<line class="edge" x1="440" y1="200" x2="480" y2="200" marker-end="url(#arr)"/>'
                    f'<line class="edge" x1="660" y1="200" x2="700" y2="200" marker-end="url(#arr)"/>'
                    f'</svg>'
                )
            else:
                svg_example = (
                    f'<svg width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}" xmlns="http://www.w3.org/2000/svg">'
                    f'<defs><style>.ring{{fill:none;stroke:currentColor;stroke-width:3}}.lbl{{font-family:Inter,Arial;font-size:14;fill:currentColor;text-anchor:middle}}</style></defs>'
                    f'<circle class="ring" cx="{sw//2}" cy="{sh//2}" r="{min(sw,sh)//3}"/>'
                    f'<text class="lbl" x="{sw//2}" y="{sh//2}">Concept Diagram</text>'
                    f'</svg>'
                )
            example["slots"][slot_name] = {"svgContent": svg_example}
    
    return json.dumps(example, indent=2)


def apply_style_to_template(template: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply style colors to a template definition.
    Returns a copy of the template with colors resolved.
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
    # Background resolution: a template that declares its own `backgroundColor`
    # (executive `_dark` templates do — they are typography-led designs that
    # require a specific dark canvas) is authoritative. Only an explicit
    # caller-supplied style override (something other than the default white)
    # is allowed to override the template's design intent. This prevents
    # ai-auto styles or unset palettes from rendering `exec_*_dark` slides
    # on white, which silences every white-on-dark text element.
    template_bg = (template.get("backgroundColor") or "").strip() if isinstance(template.get("backgroundColor"), str) else ""
    explicit_style_bg = style.get("slideBackground")
    if explicit_style_bg and explicit_style_bg.lower() not in ("", "#ffffff", "#fff", "white"):
        slide_bg = explicit_style_bg
    elif template_bg:
        slide_bg = template_bg
    else:
        slide_bg = explicit_style_bg or "#ffffff"

    # Helper: detect dark background for strict body-text contrast enforcement
    def _is_dark(hex_c: str) -> bool:
        try:
            h = hex_c.lstrip('#')
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5
        except Exception:
            return False

    bg_is_dark = _is_dark(slide_bg)

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

    # Apply to slots
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
    
    # Apply to decorations
    for dec in styled.get("decorations", []):
        if dec.get("useAccentColor"):
            dec["fill"] = accent_color
        if dec.get("useCardBackground"):
            dec["fill"] = card_bg
            dec["stroke"] = card_border
    
    styled["backgroundColor"] = slide_bg
    
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
    
    Args:
        template: Template definition with slots and decorations
        slot_data: AI-generated content for each slot
        style: Presentation style with colors
        
    Returns:
        List of positioned elements ready for rendering
    """
    import time
    
    # Apply style to template
    styled = apply_style_to_template(template, style)
    elements = []
    element_idx = 0
    
    # Add decorations first (background elements)
    for dec in styled.get("decorations", []):
        el = {
            "id": f"dec_{int(time.time() * 1000)}_{element_idx}",
            **dec,
        }
        # Remove template-specific flags
        el.pop("useAccentColor", None)
        el.pop("useCardBackground", None)
        
        # Handle step numbers in decorations
        if "stepNumber" in el:
            step_num = el.pop("stepNumber")
            # Add number text overlay
            elements.append(el)
            element_idx += 1
            # Add number text
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

        # Handle case where AI returns content directly as string instead of object
        if isinstance(ai_content, str):
            ai_content = {"content": ai_content}
        # bullets/list slots: AI sometimes returns a raw list (["a","b",...])
        # instead of {"content": "..."}. Wrap so downstream .get() calls work.
        elif isinstance(ai_content, list):
            ai_content = {"content": ai_content}
        elif not isinstance(ai_content, dict):
            ai_content = {"content": str(ai_content) if ai_content is not None else ""}
        
        # Skip optional slots without content
        is_optional = slot_name in template.get("optional_slots", [])
        has_content = ai_content.get("content") or ai_content.get("iconName") or ai_content.get("imageDescription") or ai_content.get("chartConfig")
        
        if is_optional and not has_content:
            continue
        
        # Log warning for required slots without content
        is_required = slot_name in template.get("required_slots", [])
        if is_required and not has_content:
            import logging
            logging.warning(f"[TEMPLATE] Required slot '{slot_name}' has no content from AI")
        
        el = {
            "id": f"slot_{slot_name}_{int(time.time() * 1000)}_{element_idx}",
            "type": ai_content.get("type", slot_def["type"]), # Allow AI to override type
            "x": slot_def["x"],
            "y": slot_def["y"],
            "width": slot_def.get("width", 100),
            "height": slot_def.get("height", 50),
            "zIndex": slot_def.get("zIndex", 50),
        }
        
        # Use overridden type for logic
        current_type = el["type"]
        
        if current_type == "text":
            el["textType"] = slot_def.get("textType", "body")
            # Use AI content, or generate placeholder if required slot is empty
            content = ai_content.get("content", "")
            if not content and is_required:
                # Generate a sensible default based on slot name
                content = slot_name.replace("_", " ").title()
            el["content"] = content
            el["fontSize"] = slot_def.get("fontSize", 20)
            el["fontWeight"] = slot_def.get("fontWeight", "normal")
            el["fontStyle"] = slot_def.get("fontStyle", "normal")
            el["textAlign"] = slot_def.get("textAlign", "left")

            text_type = el["textType"]
            # For body/detail text: enforce strict contrast; do not allow AI grey to slip through
            STRICT_CONTRAST_TYPES = {"body", "detail", "description", "bullets", "content", "tagline", "small"}
            computed_fill = slot_def.get("fill", "#111827")  # pre-set by apply_style_to_template
            if text_type in STRICT_CONTRAST_TYPES:
                ai_fill = (ai_content.get("fill") or "").strip()
                if ai_fill:
                    # Accept AI fill only if it has good contrast against the slide background
                    slide_bg = style.get("slideBackground", "#ffffff")
                    def _fill_has_contrast(tc: str, bc: str) -> bool:
                        try:
                            def lum(h: str) -> float:
                                h = h.lstrip('#')
                                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                                return (0.299 * r + 0.587 * g + 0.114 * b) / 255
                            return abs(lum(tc) - lum(bc)) > 0.35
                        except Exception:
                            return True
                    el["fill"] = ai_fill if _fill_has_contrast(ai_fill, slide_bg) else computed_fill
                else:
                    el["fill"] = computed_fill
            else:
                el["fill"] = ai_content.get("fill") or computed_fill
        
        elif current_type == "icon":
            el["iconName"] = ai_content.get("iconName", "circle")
            el["size"] = slot_def.get("size", 56)
            el["fill"] = ai_content.get("fill") or slot_def.get("fill", "#3B82F6")

        elif current_type == "bullets":
            # Bullets slot: carry over the AI's content + styling. The
            # frontend canvas has no dedicated `bullets` renderer (it logs
            # `Unknown element type: bullets`), so we EMIT THIS AS A TEXT
            # element with bullet glyphs already baked into the string.
            # The existing text renderer then displays it correctly with
            # one bullet per line. `bulletStyle` / `bulletColor` slot
            # attributes are preserved for the day a real bullets renderer
            # gets added — they're harmless extras on a text element.
            raw = ai_content.get("content", "")
            if isinstance(raw, list):
                # Normalize list → bullet-prefixed string. Strip any leading
                # bullet markers the model may have already added.
                _lines = []
                for item in raw:
                    s = str(item).strip().lstrip("•").lstrip("-").lstrip("*").strip()
                    if s:
                        _lines.append(f"• {s}")
                content = "\n".join(_lines)
            elif isinstance(raw, str):
                content = raw
                # Defensive: ensure every non-blank line starts with a bullet
                # glyph. LLMs sometimes return plain prose for the slot.
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
            # Switch the element type to plain text so the canvas renders it.
            # textType="bullets" tags the element semantically without changing
            # how Fabric.js draws it.
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
            el["imageType"] = ai_content.get("imageType", "photo") # Default to photo

        elif current_type == "svg_diagram":
            # Full-slot inline SVG diagram (org charts, process flows, infographics).
            # AI returns inline SVG markup; UI renders via fabric.loadSVGFromString.
            svg_content = ai_content.get("svgContent") or ai_content.get("svg") or ""
            if isinstance(svg_content, str) and svg_content.strip():
                # Auto-fix common LLM mistakes: <circle y="N"> → <circle cy="N">,
                # bare `&` → `&amp;`, force preserveAspectRatio + canonical
                # viewBox/width/height so a stale layout (e.g. 920x320) does
                # not displace content inside the new slot dims.
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
                        logging.warning(f"[SLIDE] svg_diagram sanitize failed: {_err}")
                except Exception as _e:
                    logging.warning(f"[SLIDE] svg_diagram sanitize error: {_e}")
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
                _slide_title = ""
                if isinstance(_title_slot, dict):
                    _slide_title = _title_slot.get("text") or _title_slot.get("content") or ""
                elif isinstance(_title_slot, str):
                    _slide_title = _title_slot
                _kind_label = el["diagramKind"]
                _diagram_prompt = (
                    f"{_kind_label.capitalize()} diagram for: {_slide_title or _slot_desc or slot_name}"
                ).strip()
            el["diagramTitle"] = _diagram_title.strip() if isinstance(_diagram_title, str) else ""
            el["prompt"] = _diagram_prompt.strip() if isinstance(_diagram_prompt, str) else ""

        elif current_type == "chart":
            # Pass full chart data structure
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
                        "legend": { "display": True }
                    }
                }
            }
            el["chartConfig"] = _validate_chart_config(ai_content.get("chartConfig"), _chart_fallback)
        
        elif current_type == "visual":
            # Visual slot: AI decides chart vs image. Resolve to concrete type based on AI response.
            ai_decided_type = ai_content.get("type", "")
            raw_chart = ai_content.get("chartConfig")
            if ai_decided_type == "chart" or raw_chart:
                el["type"] = "chart"
                _visual_chart_fallback = {
                    "type": "bar",
                    "data": {"labels": ["A", "B", "C"], "datasets": [{"data": [10, 20, 15], "label": "Data", "backgroundColor": ["#3B82F6", "#10B981", "#F59E0B"]}]}
                }
                el["chartConfig"] = _validate_chart_config(raw_chart, _visual_chart_fallback)
            else:
                el["type"] = "image_placeholder"
                el["imageDescription"] = ai_content.get("imageDescription", "")
                el["imageType"] = ai_content.get("imageType", "photo")

        elif current_type == "shape":
            # Shape slots (card backgrounds, accent bars, colored side-rules,
            # rounded panels in executive templates) carry their visual
            # properties on the slot definition itself. The base element
            # constructor only copies geometry + zIndex, so without this
            # branch the renderer receives a shape with no fill / no
            # shapeType / no rounded corners and falls back to its default
            # blue-fill rectangle — visible as the broken blue card on the
            # `exec_argument` slide where the white content card disappeared.
            for prop in (
                "shapeType", "fill", "stroke", "strokeWidth", "rx", "ry",
                "opacity", "shadow", "borderRadius", "borderColor",
            ):
                if prop in slot_def:
                    el[prop] = slot_def[prop]
            # The AI may purposefully override fill / stroke / shapeType for
            # accent or emphasis, but only when it actually sends a value.
            if isinstance(ai_content, dict):
                for prop in ("fill", "stroke", "shapeType"):
                    v = ai_content.get(prop)
                    if v:
                        el[prop] = v

        elements.append(el)
        element_idx += 1

    return elements


# ============================================================================
# Executive footer auto-injection
# ============================================================================
# Every exec_* template gets a consistent footer baked in at composition
# time so the deck reads as a single coherent artefact:
#
#     CITRA  |  <DECK_TITLE_OR_SECTION>                      <PAGE> / <TOTAL>
#
# Footer text colour adapts to the slide's background (light text on dark
# slides, muted dark text on light slides) so it stays readable without a
# runtime contrast check. Callers invoke this AFTER
# build_elements_from_template and the deterministic position-validator —
# the elements are appended at zIndex 1 so they never block content.
# ============================================================================

# Templates that carry a footer. We include both 16:9 exec_* slide templates
# and A4 exec_pg_* printable templates so the same helper serves both
# surfaces. To opt a template in explicitly, set "footerStyle": "exec" on it.
_EXEC_FOOTER_TEMPLATE_PREFIXES = ("exec_", "exec_pg_")


def _is_dark_background(bg: Optional[str]) -> bool:
    """Cheap brightness check — returns True if the bg looks dark."""
    if not bg or not isinstance(bg, str) or not bg.startswith("#") or len(bg) < 7:
        return False
    try:
        r = int(bg[1:3], 16)
        g = int(bg[3:5], 16)
        b = int(bg[5:7], 16)
    except (ValueError, IndexError):
        return False
    yiq = (r * 299 + g * 587 + b * 114) / 1000.0
    return yiq < 110


def inject_exec_footer(
    elements: List[Dict[str, Any]],
    template: Dict[str, Any],
    *,
    deck_title: str = "",
    page: int = 1,
    total: int = 1,
    canvas_width: int = 960,
    canvas_height: int = 540,
    section_label: str = "",
) -> List[Dict[str, Any]]:
    """Append the standard executive footer to ``elements``.

    Idempotent — calling twice would duplicate the footer; callers should
    invoke once per slide composition. Returns the same list mutated in
    place (also returned for chaining).

    ``deck_title`` and ``section_label`` are both optional:
      - if both provided: footer reads ``CITRA  |  <DECK>  ·  <SECTION>``
      - if only deck:     ``CITRA  |  <DECK>``
      - if only section:  ``CITRA  |  <SECTION>``
      - if neither:       ``CITRA  |  EXECUTIVE OVERVIEW``  (default)
    """
    tid = (template or {}).get("id", "")
    explicit_opt_in = (template or {}).get("footerStyle") == "exec"
    name_match = tid.startswith(_EXEC_FOOTER_TEMPLATE_PREFIXES)
    if not (explicit_opt_in or name_match):
        return elements

    # Pick light/dark footer colours based on the slide bg.
    bg = (template or {}).get("backgroundColor")
    dark = _is_dark_background(bg)
    color = "#475569" if dark else "#94A3B8"

    # Build the left label.
    parts: list[str] = ["CITRA"]
    deck_clean = (deck_title or "").strip().upper()
    section_clean = (section_label or "").strip().upper()
    if deck_clean and section_clean:
        parts.append(deck_clean)
        parts.append(section_clean)
    elif deck_clean:
        parts.append(deck_clean)
    elif section_clean:
        parts.append(section_clean)
    else:
        parts.append("EXECUTIVE OVERVIEW")
    left_text = "  |  ".join(parts)

    # Right page-of-N. We avoid emitting "1 / 1" for single-slide decks.
    right_text = f"{int(page)} / {int(total)}" if total and total > 1 else ""

    # Footer y-position lives ~24px above the canvas bottom. For A4 portrait
    # (canvas_height 1123) and 16:9 slides (540) the same offset works.
    y = max(0, canvas_height - 24)
    margin_x = 40

    import time
    base_id = int(time.time() * 1000)

    # Left footer — small uppercase letter-spaced label
    elements.append({
        "id": f"footer_l_{base_id}",
        "type": "text",
        "textType": "footnote",
        "content": left_text,
        "x": margin_x,
        "y": y,
        "width": int((canvas_width / 2) - margin_x),
        "height": 16,
        "fontSize": 9,
        "fontWeight": "normal",
        "textAlign": "left",
        "fill": color,
        "letterSpacing": 2,
        "opacity": 0.85,
        "zIndex": 1,
        "_auto_footer": True,
    })

    if right_text:
        elements.append({
            "id": f"footer_r_{base_id}",
            "type": "text",
            "textType": "footnote",
            "content": right_text,
            "x": int(canvas_width / 2),
            "y": y,
            "width": int((canvas_width / 2) - margin_x),
            "height": 16,
            "fontSize": 9,
            "fontWeight": "normal",
            "textAlign": "right",
            "fill": color,
            "letterSpacing": 2,
            "opacity": 0.85,
            "zIndex": 1,
            "_auto_footer": True,
        })

    return elements


def get_all_template_names_for_prompt() -> str:
    """Get formatted list of template names for AI prompt."""
    lines = []
    for tid, t in SLIDE_TEMPLATES.items():
        lines.append(f"- {tid}: {t['description']}")
    return "\n".join(lines)


# ==================== AI Template Auto-Matching ====================

def _word_match(keyword: str, text: str) -> bool:
    """Check if keyword matches as a whole word/phrase in text (not substring)."""
    import re
    # Multi-word keywords: exact phrase match
    # Single-word keywords (<=6 chars): word boundary match to avoid false positives
    # Longer single words: substring is fine (specific enough)
    if " " in keyword or len(keyword) > 6:
        return keyword in text
    return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text))


def auto_match_template(slide_title: str, slide_instruction: str = "", slide_index: int = 0, total_slides: int = 1, layout: str = "", image_prompt: str = "", has_structured_data: bool = False, deck_profile: Optional[str] = None) -> str:
    """
    Auto-match the best template for a slide based on its title, instruction, position,
    layout hint, and image prompt.
    Uses keyword matching against template tags and position heuristics.
    Returns the matched template_id.

    ``deck_profile`` ensures FIRST/LAST positional fallbacks point at IDs that
    actually exist in the chosen profile's catalog (corporate uses
    exec_title_dark / exec_closing_dark, general uses title_hero / closing).
    """
    import logging
    text = f"{slide_title} {slide_instruction}".lower()
    layout_lower = (layout or "").lower()
    _profile_key = deck_profile if deck_profile in DECK_PROFILES else DECK_PROFILE_CORPORATE
    _is_corp = _profile_key in (
        DECK_PROFILE_CORPORATE,
        DECK_PROFILE_CORPORATE_BOARDROOM,
        DECK_PROFILE_CORPORATE_WITH_VISUALS,
    )

    # Determine if the slide explicitly wants an image (from outline layout/image_prompt)
    wants_image = bool(image_prompt) or any(
        kw in layout_lower for kw in ["image", "photo", "visual", "picture"]
    )

    # LAYOUT-BASED DIRECT MAPPING: When outline provides a layout hint, map it
    # directly to a template before falling through to heuristics
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

    # Position-based heuristics
    is_first = slide_index == 0
    is_last = slide_index == total_slides - 1

    if is_first:
        if _is_corp:
            # Corporate cover is the dark exec_title — even when the outline
            # asks for an image, exec_title_dark is the right call (the
            # storyboard supplies a deck-coherent background image separately).
            return "exec_title_dark"
        if wants_image or any(kw in text for kw in ["image", "photo", "visual", "picture"]):
            return "title_image"
        if any(kw in text for kw in ["split", "modern"]):
            return "title_split"
        return "title_hero"

    if is_last:
        if _is_corp:
            # Corporate closing is the dark exec_closing — recap/summary still
            # uses the same closing template (the 2x2 numbered reason cards
            # work for both "thank you / CTA" and "key takeaways").
            return "exec_closing_dark"
        if any(kw in text for kw in ["thank", "closing", "end", "contact", "question"]):
            return "closing"
        if any(kw in text for kw in ["summary", "recap", "key takeaway"]):
            return "stats_highlight"
        return "closing"

    # LAYOUT HINT MATCHING: If outline provided a layout hint, use it (with image override)
    if layout_lower and layout_lower in LAYOUT_TO_TEMPLATE:
        matched = LAYOUT_TO_TEMPLATE[layout_lower]
        # Corporate has no `bullets` / `bullets_with_image` / `title_hero` —
        # remap layout-hint matches that name general-only IDs to the
        # equivalent corporate template.
        if _is_corp:
            _CORP_REMAP = {
                "title_hero": "exec_title_dark",
                "bullets": "exec_argument",
            }
            if matched in _CORP_REMAP:
                matched = _CORP_REMAP[matched]
        else:
            # Upgrade text-only templates to image variants for visual richness
            if matched in ("bullets",):
                if wants_image:
                    matched = "bullets_with_image"
                else:
                    # Even without explicit image_prompt, upgrade bullets to image variant
                    # for content slides (not first/last) to ensure right-side image space is used
                    if not is_first and not is_last:
                        matched = "bullets_with_image"
            elif wants_image and matched in ("quote", "comparison", "stats_highlight"):
                matched = "image_right" if slide_index % 2 == 0 else "image_left"
        logging.info(f"\U0001f3af [AUTO_MATCH] Layout hint '{layout_lower}' → {matched}")
        return matched

    # STRUCTURED DATA PRIORITY: When structured data context is present,
    # prefer chart templates to render real data visualizations instead of images
    if has_structured_data:
        data_keywords = ["data", "stats", "statistics", "numbers", "metrics", "trends",
                        "growth", "revenue", "sales", "percentage", "increase", "decrease",
                        "comparison", "analysis", "performance", "results", "chart", "graph"]
        has_data_content = any(kw in text for kw in data_keywords)

        if has_data_content:
            if wants_image:
                logging.info(f"\U0001f3af [AUTO_MATCH] Structured data + image \u2192 chart_and_image")
                return "chart_and_image"
            if any(kw in text for kw in ["dashboard", "overview", "kpi"]):
                return "data_dashboard"
            if any(kw in text for kw in ["compare", "versus", "vs"]):
                return "data_dashboard"
            pick = "chart_right" if slide_index % 2 == 0 else "chart_left"
            logging.info(f"\U0001f3af [AUTO_MATCH] Structured data + data content \u2192 {pick}")
            return pick

    # IMAGE PRIORITY: When layout or image_prompt explicitly requests images,
    # always select an image template for foreground visual impact.
    # Corporate has no bullets_with_image / full_bleed_image — those are
    # general-only photo-rich layouts. For corporate, fall through to the
    # exec_argument workhorse (storyboard supplies a deck bg image anyway)
    # or image_left/image_right when a single hero photo is warranted.
    if wants_image:
        if _is_corp:
            # Corporate is typography-led; a single hero image goes on the side.
            pick = "image_right" if slide_index % 2 == 0 else "image_left"
            logging.info(f"🎯 [AUTO_MATCH] Corporate image requested → {pick}")
            return pick
        # Smart selection based on content type
        if any(kw in text for kw in ["bullet", "list", "point", "feature", "highlight"]):
            logging.info(f"🎯 [AUTO_MATCH] Image requested + bullet content → bullets_with_image")
            return "bullets_with_image"
        if any(kw in text for kw in ["cinematic", "dramatic", "scenic", "landscape", "full"]):
            logging.info(f"🎯 [AUTO_MATCH] Image requested + cinematic content → full_bleed_image")
            return "full_bleed_image"
        # Alternate between image_left and image_right for variety
        pick = "image_right" if slide_index % 2 == 0 else "image_left"
        logging.info(f"🎯 [AUTO_MATCH] Image requested → {pick}")
        return pick

    # CHART PRIORITY: When content explicitly mentions charts/graphs with other elements
    wants_chart = any(kw in text for kw in ["chart", "graph", "visualization", "bar chart", "pie chart", "line chart"])
    if wants_chart:
        if any(kw in text for kw in ["image", "photo", "picture"]):
            logging.info(f"🎯 [AUTO_MATCH] Chart + image requested → chart_and_image")
            return "chart_and_image"
        if any(kw in text for kw in ["dashboard", "metric", "kpi", "analytics"]):
            return "data_dashboard"
        # Alternate chart_left / chart_right for variety
        pick = "chart_right" if slide_index % 2 == 0 else "chart_left"
        logging.info(f"🎯 [AUTO_MATCH] Chart requested → {pick}")
        return pick

    # Keyword matching against TEMPLATE_KEYWORDS (with word boundary protection)
    best_match = None
    best_score = 0

    for template_id, keywords in TEMPLATE_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if _word_match(keyword, text):
                score += len(keyword)  # Longer keyword match = more specific
        if score > best_score:
            best_score = score
            best_match = template_id

    if best_match and best_score > 0:
        return best_match

    # Tag-based matching against template metadata
    for tid, tdef in SLIDE_TEMPLATES.items():
        tags = tdef.get("tags", [])
        for tag in tags:
            if _word_match(tag, text):
                return tid

    # Content-hint fallbacks
    if any(kw in text for kw in ["data", "number", "metric", "stat", "percent", "%"]):
        return "stats_highlight"
    if any(kw in text for kw in ["hierarchy", "org chart", "reporting structure", "tree diagram", "taxonomy"]):
        return "org_hierarchy"
    if any(kw in text for kw in ["step", "process", "how", "method", "lifecycle", "pipeline", "workflow"]):
        return "process_steps"
    if any(kw in text for kw in ["infographic", "visual breakdown", "anatomy", "venn", "funnel"]):
        return "infographic_diagram"
    if any(kw in text for kw in ["compare", "vs", "versus", "differ"]):
        return "comparison"
    if any(kw in text for kw in ["image", "photo", "picture", "visual"]):
        return "image_right"

    # Visual diversity fallback: for middle content slides without strong keyword
    # matches, alternate between text-only and image templates to avoid dull decks.
    # Corporate has no `bullets` / `bullets_with_image` in its catalog, so the
    # diversity pick rotates through corporate-safe IDs instead.
    middle_position = slide_index - 1  # 0-based among middle slides
    if _is_corp:
        # Workhorse body alternation across stat / pillar-detail / features /
        # argument so consecutive slides aren't visually identical.
        _corp_rotation = [
            "exec_argument",
            "exec_stat_grid_4",
            "exec_action_card",
            "exec_features_2x2",
        ]
        pick = _corp_rotation[max(0, middle_position) % len(_corp_rotation)]
        logging.info(f"🎯 [AUTO_MATCH] Corporate diversity rotation → {pick}")
        return pick
    if middle_position % 3 == 0:
        # Every 3rd middle slide gets an image template for visual variety
        pick = "image_right" if slide_index % 2 == 0 else "bullets_with_image"
        logging.info(f"🎯 [AUTO_MATCH] Diversity fallback → {pick}")
        return pick

    # Generic fallback - bullets is always safe (general profile only)
    return "exec_argument" if _is_corp else "bullets"


def llm_match_template(
    slide_title: str,
    slide_instruction: str = "",
    slide_index: int = 0,
    total_slides: int = 1,
    layout: str = "",
    image_prompt: str = "",
    has_structured_data: bool = False,
    user_id: Optional[str] = None,
    deck_profile: Optional[str] = None,
) -> Optional[str]:
    """
    LLM-based template matching using a large-tier model.

    ``deck_profile`` filters the candidate catalog. Defaults to
    ``corporate_boardroom`` — only exec_* templates are considered. Other
    profiles open up legacy chart / diagram / image templates.

    Returns the matched template_id, or None on any failure (caller should
    fall back to keyword-based `auto_match_template`).
    """
    try:
        from llm_oss import llm_call  # local import to avoid circular import at module load
    except Exception as e:
        logger.warning(f"🎯 [LLM_MATCH] llm_oss unavailable, skipping LLM matching: {e}")
        return None

    # Profile-filtered catalog. The LLM only sees templates relevant to
    # the user's chosen deck profile.
    profile_catalog = get_profile_template_catalog(deck_profile)
    profile_key = deck_profile if deck_profile in DECK_PROFILES else DECK_PROFILE_CORPORATE
    profile_label = DECK_PROFILES[profile_key]["label"]
    profile_desc = DECK_PROFILES[profile_key]["description"]
    is_corporate = profile_key in (
        DECK_PROFILE_CORPORATE,
        DECK_PROFILE_CORPORATE_BOARDROOM,
        DECK_PROFILE_CORPORATE_WITH_VISUALS,
    )

    # Build catalog lines with richer per-template signal:
    #   - description / best_for / flags / tags (existing)
    #   - required_slots COUNT — important cardinality cue so the LLM doesn't
    #     pick `exec_stat_grid_4` (needs 4 stats) when the slide only has one
    #     headline number (use `big_number` instead).
    catalog_lines = []
    valid_ids = []
    for tid, t in profile_catalog.items():
        valid_ids.append(tid)
        entry = f"- {tid}: {t.get('description', '')}"
        if t.get("best_for"):
            entry += f" | Best for: {t['best_for']}"
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
        tags = t.get("tags", [])
        if tags:
            entry += f" | Tags: {', '.join(tags[:8])}"
        catalog_lines.append(entry)
    catalog_str = "\n".join(catalog_lines)

    valid_ids_set = set(valid_ids)

    pos = "FIRST" if slide_index == 0 else (
        "LAST" if slide_index == total_slides - 1 else f"MIDDLE ({slide_index + 1}/{total_slides})"
    )

    # Normalize common layout aliases coming from the outline prompt so the
    # matcher sees the same ID space as the catalog (the outline prompt
    # writes shorthand like "exec_title" / "exec_stat_grid" / "exec_pillars"
    # / "exec_features" / "exec_industries" / "exec_sovereignty" /
    # "exec_closing" but the catalog IDs carry the suffix variant).
    _LAYOUT_ALIASES = {
        "exec_title": "exec_title_dark",
        "exec_pillars": "exec_three_pillars",
        "exec_pillar_detail": "exec_action_card",
        "exec_stat_grid": "exec_stat_grid_4",
        "exec_features": "exec_features_2x2",
        "exec_industries": "exec_industries_2x2",
        "exec_sovereignty": "exec_sovereignty_dark",
        "exec_closing": "exec_closing_dark",
    }
    normalized_layout = _LAYOUT_ALIASES.get((layout or "").strip(), layout or "")

    # Profile-aware rule blocks. Corporate names exec_* IDs explicitly; general
    # uses the legacy bullets / image / chart vocabulary.
    if is_corporate:
        rules_block = """RULES (apply in order — choose ONE template_id that EXISTS in the catalog above):
- FIRST slide → exec_title_dark.
- LAST slide → exec_closing_dark.
- "What is X" / framework intro / three pillars → exec_three_pillars.
- Pillar deep-dive / before-after stat / how-it-works steps → exec_action_card.
- 4 KPIs / "by the numbers" / business impact → exec_stat_grid_4 (needs exactly 4 stats — for a single headline metric use big_number).
- 4 capabilities / value props / 2x2 feature grid → exec_features_2x2.
- 4 verticals / use-cases / industries grid → exec_industries_2x2.
- Architecture / security / governance / data residency / trust posture → exec_sovereignty_dark.
- Live product example / chat Q&A demo → exec_chat_example.
- Default body slide (one claim + 4-5 bullets) → exec_argument. This is the workhorse — prefer it over generic `bullets`.
- PROCESS / WORKFLOW / LIFECYCLE / PIPELINE / PHASES / step-by-step → process_steps. Overrides image hints.
- HIERARCHY / ORG CHART / TAXONOMY / TREE → org_hierarchy.
- INFOGRAPHIC / VENN / FUNNEL / CYCLE / ANATOMY → infographic_diagram.
- Comparing two options head-to-head → comparison.
- Single hero number → big_number. Three headline stats → stats_highlight.
- Chronological events / roadmap / milestones → timeline.
- Real structured data + data-heavy content → chart_focus / chart_left / chart_right / chart_and_image / data_dashboard.
- ONE photo earns its place (hero/cover with imagery) → title_image / image_left / image_right. Use sparingly — corporate decks lean typography-first.
- Pick from the catalog list above ONLY. Do not invent IDs."""
    else:
        rules_block = """RULES (apply in order — choose ONE template_id that EXISTS in the catalog above):
- FIRST slide → a title template (title_hero, title_image, or title_split).
- LAST slide → closing.
- PROCESS / WORKFLOW / LIFECYCLE / PIPELINE / PHASES / step-by-step → process_steps. Overrides image hints.
- HIERARCHY / ORG CHART / TAXONOMY / TREE → org_hierarchy.
- INFOGRAPHIC / VENN / FUNNEL / CYCLE / ANATOMY → infographic_diagram.
- Comparing two options → comparison.
- Key stats / numbers → stats_highlight (three) or big_number (one).
- Real structured data + data-heavy content → chart_left / chart_right / chart_and_image / data_dashboard.
- Photo-rich content → image_left / image_right / bullets_with_image.
- Generic prose body → bullets.
- Pick from the catalog list above ONLY. Do not invent IDs."""

    system_prompt = (
        "You are a presentation design expert. Pick the single BEST slide template "
        f"from a {profile_label.upper()} deck profile catalog. {profile_desc} "
        "Return ONLY a minimal JSON object: {\"template_id\": \"<id>\"}. "
        "No reasoning, no prose, no markdown."
    )
    user_prompt = f"""DECK PROFILE: {profile_label}
{profile_desc}

TEMPLATE CATALOG ({len(valid_ids)} options — pick exactly one ID from this list):
{catalog_str}

SLIDE TO MATCH:
- Position: {pos}
- Title: {slide_title}
- Outline / content_hint: {slide_instruction}
- Layout hint from outline (advisory only — content type takes priority): {normalized_layout or '(none)'}
- Image prompt present: {bool(image_prompt)}
- Structured data available: {has_structured_data}

{rules_block}

Return ONLY this JSON (no other text, no markdown, no reasoning): {{"template_id": "<one_id_from_catalog>"}}"""

    try:
        ai_response = llm_call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=None,
            user_id=user_id,
            max_tokens=4096,
            temperature=0.0,
            top_p=0.9,
            json_mode=True,
            tier="large",
        )
    except Exception as e:
        logger.warning(f"🎯 [LLM_MATCH] LLM call failed: {e}")
        return None

    # Parse JSON robustly
    try:
        raw = (ai_response or "").strip()
        if not raw:
            logger.warning("🎯 [LLM_MATCH] Empty response from LLM")
            return None
        # Strip code fences if present
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        # Slice to outermost braces
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            raw = raw[start:end + 1]
        try:
            data = json.loads(raw)
            template_id = (data.get("template_id") or "").strip()
        except Exception:
            # Fallback: regex-extract template_id even if JSON is malformed/truncated
            import re as _re
            m = _re.search(r'"template_id"\s*:\s*"([a-zA-Z0-9_]+)"', raw)
            template_id = m.group(1) if m else ""
        # Validate against the PROFILE-FILTERED catalog, not the full library —
        # otherwise the LLM could return `bullets` for a corporate deck (it
        # exists in SLIDE_TEMPLATES but isn't in the corporate profile_catalog)
        # and we'd silently render it.
        if template_id in valid_ids_set:
            logger.info(f"🎯 [LLM_MATCH] '{slide_title[:60]}' → {template_id} (profile={profile_label})")
            return template_id
        if template_id in SLIDE_TEMPLATES:
            logger.warning(
                f"🎯 [LLM_MATCH] Returned id '{template_id}' exists but is OUT-OF-PROFILE "
                f"({profile_label}); rejecting so caller falls back to keyword matcher"
            )
            return None
        logger.warning(f"🎯 [LLM_MATCH] Returned id '{template_id}' not in catalog; raw={raw[:200]}")
        return None
    except Exception as e:
        logger.warning(f"🎯 [LLM_MATCH] JSON parse failed: {e}; raw={(ai_response or '')[:200]}")
        return None


def get_template_matching_prompt(slides: list, profile: Optional[str] = None) -> str:
    """
    Generate a prompt for LLM-based template matching.
    The LLM returns a JSON mapping of slide index to template_id.

    ``profile`` controls which templates are visible to the LLM. When None
    or unknown, defaults to ``corporate_boardroom`` (the strict executive
    family). Pass ``corporate_with_visuals`` to expose chart / diagram /
    selective-image legacy templates; pass ``general_with_images`` for the
    full library.
    """
    profile_key = profile if profile in DECK_PROFILES else DECK_PROFILE_CORPORATE_BOARDROOM
    profile_label = DECK_PROFILES[profile_key]["label"]
    profile_description = DECK_PROFILES[profile_key]["description"]
    catalog = get_profile_template_catalog(profile_key)

    template_catalog = []
    for tid, t in catalog.items():
        entry = f"- {tid}: {t['description']}"
        if t.get("best_for"):
            entry += f" (Best for: {t['best_for']})"
        if t.get("has_image"):
            entry += " [HAS IMAGE]"
        if t.get("has_chart"):
            entry += " [HAS CHART]"
        template_catalog.append(entry)

    catalog_str = "\n".join(template_catalog)

    slide_list = []
    for i, slide in enumerate(slides):
        title = slide.get("title", slide.get("slideTitle", f"Slide {i+1}"))
        instruction = slide.get("instruction", slide.get("content", ""))
        pos = "FIRST" if i == 0 else ("LAST" if i == len(slides) - 1 else f"MIDDLE ({i+1}/{len(slides)})")
        slide_list.append(f"  Slide {i}: [{pos}] \"{title}\" — {instruction[:120]}")

    slides_str = "\n".join(slide_list)

    return f"""You are a presentation design expert. Match each slide to the BEST template from the catalog below.

DECK PROFILE: {profile_label}
{profile_description}
(Only templates that fit this profile appear in the catalog below — do not invent template IDs.)

TEMPLATE CATALOG:
{catalog_str}

SLIDES TO MATCH:
{slides_str}

RULES:
- First slide should use a title template (title_hero, title_image, title_split, exec_title_dark)
- Last slide should use a closing template (exec_closing_dark for executive decks)
- Vary templates across slides — avoid using the same template consecutively
- Match based on content type: data slides → data templates, process slides → process_steps/timeline, etc.
- If a slide discusses comparing options, use comparison template
- If a slide has key stats/numbers, use stats_highlight or big_number
- For general content with bullet points, use bullets or bullets_with_image

EXECUTIVE-DECK FAMILY (the DEFAULT for every Citra deck — Citra is an enterprise platform; old generic templates are deprecated):
- FIRST slide → `exec_title_dark` (dark navy cover, two-tone headline, three pill labels naming the deck's pillars)
- Standard body slide making one claim with 4-5 bullets → `exec_argument` (the workhorse — light bg, kicker + action-title + subhead + single content card with bullets + optional takeaway strap)
- "Three pillars" / "what is X" / "product overview" / "framework introduction" → `exec_three_pillars` (light bg, three coloured pillar cards, bottom claim banner)
- Per-pillar deep dive with before/after numbers OR how-it-works + examples → `exec_action_card` (light bg, left "how it works" card + right navy stat/example card)
- Business-impact / KPI / "by the numbers" — 4 headline metrics → `exec_stat_grid_4` (light bg, 4 stat cards with coloured accent bars, optional 3-up icon strip below)
- Capabilities / features — 4 distinct value props → `exec_features_2x2` (light bg, 2x2 white feature cards with coloured icon circles)
- Industries / use cases / verticals — 4 industries each with checkmark uses → `exec_industries_2x2` (light bg, 2x2 with vertical coloured side-rules + checkmark bullets)
- Architecture / sovereignty / security / governance / trust posture → `exec_sovereignty_dark` (dark navy bg, 4 dark cards in a row + light governance panel)
- Product example / live Q&A / chat demo → `exec_chat_example` (light bg, chat bubble example + 3 supporting stat blocks)
- LAST slide / "why buy" / "strategic reasons" / "asks" → `exec_closing_dark` (dark navy, 2x2 numbered reason cards, cyan CTA banner)

RHYTHM RULES (apply across the deck):
- Dark book-ends: first slide and last slide are dark navy; sovereignty/architecture slides can also be dark for emphasis. Everything else is light. Don't fight this — it's the deck's pulse.
- Coherent family: once you've started in the exec family, do NOT mix with legacy templates (bullets, three_cards, bullets_with_image, image_focus, etc.) on the same deck. Pick exec_argument for any body slide that doesn't fit a more specific exec_* template.
- Variety within the family: avoid two consecutive `exec_argument` slides if a more specific template fits the content (stat_grid for numbers, features_2x2 for capabilities, etc.).

Return ONLY a JSON object mapping slide index to template_id:
{{"0": "title_hero", "1": "bullets_with_image", "2": "three_cards", ...}}"""
