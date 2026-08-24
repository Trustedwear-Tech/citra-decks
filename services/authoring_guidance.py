# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
authoring_guidance.py
=====================
Single source of truth for the *common* authoring guidance that goes into
the system prompt of every slide / page generation call — for ALL three
deck/document profiles (corporate_boardroom, corporate_with_visuals,
general_with_images) across BOTH presentation and printable surfaces.

Philosophy
----------
Claude already knows how to render SVG, structure a Chart.js config,
write effective image prompts, pick contrasting colours, and design a
slide. Don't teach it any of that. Only document what it CAN'T know
from training:

1. Our custom output protocol: `slots` + `extra_elements` + `backgroundColor`.
2. The fact that the matched template is GUIDANCE, not enforcement.
3. The exact canvas dimensions and the `extra_elements` JSON shape.

That's it. ~600 chars, no teaching.

Public API
----------
- :data:`COMMON_AUTHORING_GUIDANCE_PRESENTATION` — for 16:9 slides
- :data:`COMMON_AUTHORING_GUIDANCE_PRINTABLE` — for A4 pages
- :func:`build_common_guidance(surface, canvas_w, canvas_h)` — builder.
"""

from __future__ import annotations

from typing import Literal


def build_common_guidance(
    surface: Literal["presentation", "printable"] = "presentation",
    canvas_w: int = 960,
    canvas_h: int = 540,
) -> str:
    """Return the unified authoring-guidance block — protocol only, no teaching."""
    surface_word = "slide" if surface == "presentation" else "page"

    return f"""
The matched template below is GUIDANCE, not a contract. Fill its slots,
tweak them, extend with `extra_elements`, or ignore it entirely and build
the whole {surface_word} from `extra_elements` — your call. Use whatever mix
of text, shapes, images, charts, icons, and inline SVG best serves the
message. Canvas is {canvas_w}×{canvas_h}px.

Output:
{{
  "slots": {{ ...partial fills ok... }},
  "extra_elements": [           // free-form, fully positioned
    {{"type":"text|shape|image_placeholder|chart|icon|svg_diagram",
     "x":..,"y":..,"width":..,"height":..,"zIndex":..,
     ...type-specific fields (content/fill/shapeType/imageDescription/chartConfig/iconName/svgContent)...}}
  ],
  "backgroundColor": "#RRGGBB"  // optional
}}

Keep extra_elements inside the canvas and avoid overlapping template slots.
Use ONLY verifiable facts from the supplied context — never fabricate.
""".strip()


COMMON_AUTHORING_GUIDANCE_PRESENTATION: str = build_common_guidance(
    surface="presentation",
    canvas_w=960,
    canvas_h=540,
)

COMMON_AUTHORING_GUIDANCE_PRINTABLE: str = build_common_guidance(
    surface="printable",
    canvas_w=794,
    canvas_h=1123,
)


def build_freeform_guidance(
    surface: Literal["presentation", "printable"] = "presentation",
    canvas_w: int = 960,
    canvas_h: int = 540,
) -> str:
    """Authoring guidance for the legacy free-form path (general profile).

    No template. The LLM designs the whole {surface} from scratch with one
    flat ``elements`` array — every element carries its own x/y/width/height.
    """
    surface_word = "slide" if surface == "presentation" else "page"
    return f"""
You are designing a {surface_word} from scratch — no template, no slot grid.
Compose ALL content as a flat `elements` array; every element carries its
own x/y/width/height/zIndex. Canvas is {canvas_w}×{canvas_h}px (margin 40px).

Element toolbox:
- text                — titles, headings, body, captions
- shape               — rectangle / circle / line (dividers, accent bars, cards)
- icon                — small visual marker; field `iconName` (kebab-case)
- image_placeholder   — photograph rendered downstream; field `imageDescription`
                        (scene only — NO text/labels/numbers/words in the image)
- chart               — Chart.js config; field `chartConfig` with type + data
- svg_diagram         — inline SVG for org/process/cycle/venn/funnel/anatomy;
                        fields: `svgContent` (raw SVG string), `fillColor`,
                        `diagramKind`, `diagramTitle`. Use when a structural
                        diagram beats prose or a chart.

Output shape:
{{
  "title": "<slide title text>",
  "elements": [ {{...positioned element...}}, ... ],
  "background_image": {{"imageDescription":"..."}},  // optional, root-level
  "backgroundColor": "#RRGGBB"
}}

Rules:
- Every element must fit inside the canvas. No two element bounding boxes
  intersect (≥8px gap).
- ONE clear intent per {surface_word}. Vary visual rhythm vs the previous {surface_word}s.
- Use ONLY verifiable facts from the supplied context — never fabricate.
- JSON only, no markdown.
""".strip()


FREEFORM_AUTHORING_GUIDANCE_PRESENTATION: str = build_freeform_guidance(
    surface="presentation",
    canvas_w=960,
    canvas_h=540,
)

FREEFORM_AUTHORING_GUIDANCE_PRINTABLE: str = build_freeform_guidance(
    surface="printable",
    canvas_w=794,
    canvas_h=1123,
)


__all__ = [
    "build_common_guidance",
    "COMMON_AUTHORING_GUIDANCE_PRESENTATION",
    "COMMON_AUTHORING_GUIDANCE_PRINTABLE",
    "build_freeform_guidance",
    "FREEFORM_AUTHORING_GUIDANCE_PRESENTATION",
    "FREEFORM_AUTHORING_GUIDANCE_PRINTABLE",
]
