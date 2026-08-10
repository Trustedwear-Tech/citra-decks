"""
svg_diagram_prompts.py
======================

Builds system + user prompts for the LLM-powered SVG diagram generator
used by the composer (presentation + printable). Also provides a sanitizer
that strips unsafe / non-renderable SVG features before the markup is
returned to the client.

Three diagram kinds are supported:
    - flowchart   : process / decision flow with arrows
    - infographic : 3-6 stat cards / icon clusters
    - org_chart   : hierarchy with orthogonal connectors

The LLM is asked (json_mode=True) to return:
    {"svg": "<svg ...>...</svg>", "title": "<short title>"}

The sanitizer enforces:
    - markup must start with <svg
    - byte-size cap
    - removes <script>, on*= handlers, javascript: URLs, <foreignObject>,
      <filter>, <pattern>, <mask>, remote href / xlink:href references
"""

from __future__ import annotations

import re
from typing import Tuple

ALLOWED_KINDS = ("flowchart", "infographic", "org_chart")
DEFAULT_KIND = "flowchart"

# Hard byte cap — generous but stops absurd payloads.
MAX_SVG_BYTES = 200_000


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_DESIGN_MISSION = """\
DESIGN MISSION:
Produce a SIMPLE, CRISP, editorial-clean SVG illustration. The SVG can be
ANYTHING that best communicates the user's request — a node-and-arrow flow,
a tree, a cycle, a venn, a funnel, an anatomical sketch, a molecular or
biological structure (e.g. cell, neuron, protein folding), an architectural
cross-section, a stylized character, an organic flowing illustration, an
icon-like symbol, or any combination of these. You are NOT required to use
boxes/nodes — let the topic decide the shape language.

Think of a polished Figma export with restraint: minimal text, generous
whitespace, a small refined palette, and a clear focal point. Fewer
elements is always better than more. NO clutter, NO legends, NO callouts,
NO decorative stray shapes. Aim for: SIMPLE, CLEAR, AND CRISP.
"""

_SHARED_RULES = _DESIGN_MISSION + """
HARD OUTPUT RULES:
1. Respond with VALID JSON ONLY in the form: {{"svg": "<svg ...>...</svg>", "title": "..."}}
   - No markdown fences. No commentary. No prose outside the JSON.
2. The "svg" value must be a single complete <svg> element with:
   - viewBox="0 0 {width} {height}"
   - xmlns="http://www.w3.org/2000/svg"
   - width and height attributes set to {width} and {height}
3. Use ONLY these SVG features: <g>, <rect>, <circle>, <ellipse>, <line>, <polyline>,
   <polygon>, <path>, <text>, <tspan>, <defs>, <marker>, <linearGradient>, <stop>, <title>.
4. STRICTLY FORBIDDEN: <script>, <foreignObject>, <filter>, <pattern>, <mask>,
   <image>, <use href="...">, on*= event handlers, javascript: URLs,
   any href / xlink:href pointing outside the SVG.
   ALSO FORBIDDEN: <style> blocks, class="..." attributes, HTML comments
   (<!-- ... -->), and the keyword `currentColor` anywhere in the SVG.

   STYLING IS INLINE-ONLY. Our renderer does NOT evaluate CSS class selectors
   (`.cls`), tag selectors, descendant combinators, or `currentColor`. Every
   visible element MUST carry its own resolved colors and stroke directly
   via presentation attributes:
     - fill="#RRGGBB"           (or fill="none" for outline-only)
     - stroke="#RRGGBB"
     - stroke-width="..."
     - font-size="..."
     - font-family="Inter, Arial, sans-serif"
     - font-weight="..."
     - text-anchor="..."
   Equivalently they may use a single inline `style="fill:#...;stroke:#...;"`,
   but NEVER rely on a parent <g> or a <style> block to provide them.

   IMPORTANT — the most common silent-failure cases to avoid:
     * Every <line> MUST have stroke="#RRGGBB" AND stroke-width="..." inline.
       A <line> without these renders invisible.
     * Every <text> MUST have fill="#RRGGBB", font-size, font-family inline.
     * Every <path> used as a connector/arrow MUST have stroke="#RRGGBB" and
       stroke-width inline; if it's a filled icon, also fill="#RRGGBB".
     * Gradient fills are allowed (`fill="url(#myGrad)"`) but the gradient
       MUST be declared in <defs> in the SAME SVG — never reference an
       external id.
     * <circle> uses `cx` and `cy` (NEVER `x`/`y`). <ellipse> uses `cx`/`cy`/`rx`/`ry`.
       <rect>/<text>/<image> use `x`/`y`. Mixing these makes elements default to
       position (0,0) and stack at the top-left corner — a common LLM mistake.
     * Use real “&amp;” in text content (or alternative wording). A bare `&` makes
       the entire SVG invalid XML and it will fail to render.
5. All text must be rendered with <text> elements (NEVER <foreignObject>).
6. Text rules — KEEP IT MINIMAL:
   - Use real, correctly-spelled English. Never garble or invent words.
   - Font size 13-16px for primary labels, 11-12px for optional sub-labels.
   - Use font-family="Inter, Arial, sans-serif".
   - At most a handful of short labels total (1-3 words preferred, ≤5 words
     HARD MAX per label). Many illustrations need NO labels at all — only
     label the few elements that genuinely need naming.
   - NO arrow annotations, NO callout text, NO legends, NO axis text, NO
     paragraphs, NO sentences — short labels only.
   - When a label sits inside a saturated container, use white (#FFFFFF)
     for text. On light tints / outside containers, use a near-black
     (#0F172A).
   - TEXT MUST FIT: estimate width as ~0.6em per char × font-size. If a
     label would be wider than the shape it sits on (or the SVG edge),
     SHORTEN the label or move it adjacent — never let text overflow.
7. Visual style — RESTRAINED PALETTE:
   - Use 2-4 distinct colors total across the whole illustration — NOT a
     rainbow.
   - Pick from this modern palette (choose 2-4): indigo #6366F1, violet
     #8B5CF6, sky #0EA5E9, teal #14B8A6, emerald #10B981, amber #F59E0B,
     slate #64748B.
   - Define exactly 1 inline <linearGradient> in <defs> and apply it to the
     ONE hero element (the focal subject). Other elements use solid fills
     from the chosen palette.
   - DO NOT add tinted background bands, soft accent panels, or decorative
     stray shapes. Keep the canvas clean.
   - BACKGROUND MUST BE TRANSPARENT. Do NOT emit a full-canvas background
     <rect> (e.g. one covering 0,0 to width,height) or set a `background`
     style on the root <svg>. The SVG renders over a themed slide/page
     background, so any opaque backdrop will clash. Every drawn shape must
     belong to the actual illustration content.
   - Stroke width 1.5-2px. Stroke color may match the fill or be a darker
     palette tone.
   - NO drop-shadows, NO <filter>, NO blur effects.
8. Layout:
   - The <svg> is exactly {width}x{height}px. Keep ≥20px clear space
     between any element and the SVG edge.
   - FILL THE CANVAS — distribute elements to span the full {width}x{height}
     area. Do NOT cluster everything in one corner or leave a wide empty
     margin.
   - No element may overflow the viewBox. NO OVERLAPPING text.
   - If labels are present, leave ≥12px clear space inside any container
     shape between its border and the text.
   - If a label is too long, SHORTEN it — do not let text spill outside.
   - NEVER draw an arrow that points into empty space. EVERY connector
     arrowhead must terminate at a real, drawn shape.
   - ARROWS MUST STOP AT SHAPE BOUNDARIES, NEVER AT THE CENTER. When
     connecting two shapes, the connector's start and end points must lie
     ON the BORDER of each shape (the outer edge), not inside it. For a
     circle of radius `r` centered at (cx,cy), end the arrow at the point
     on the circumference along the line toward the source shape (i.e.
     offset by r from the center, away from the connector direction). For
     a rectangle, end the arrow at the relevant edge — not past it. The
     arrowhead marker must be visible OUTSIDE the target shape's fill so
     the connection reads cleanly. Add ~4-6px of breathing room between
     the arrowhead tip and the shape's border so the arrow is not buried
     under the shape's stroke.
   - CONNECTOR ENDPOINT MATH (CRITICAL — follow this 2-pass procedure):
     PASS 1 — LAYOUT: First decide and write down the bounding box / center
     of EVERY shape you intend to draw. For a <rect x="X" y="Y" width="W"
     height="H">, its anchor points are:
       top-center    = (X + W/2, Y)
       bottom-center = (X + W/2, Y + H)
       left-center   = (X,        Y + H/2)
       right-center  = (X + W,    Y + H/2)
     For a <circle cx="CX" cy="CY" r="R">, its anchor points on the
     circumference toward another point (PX, PY) are:
       dx = PX - CX; dy = PY - CY; len = sqrt(dx*dx + dy*dy)
       edge_x = CX + (dx/len) * R
       edge_y = CY + (dy/len) * R
     PASS 2 — CONNECT: Draw EVERY <line>/<path> connector by computing its
     x1,y1 from the source shape's anchor and its x2,y2 from the target
     shape's anchor using the formulas above. For a vertical connector
     between two stacked rectangles, x1 MUST equal x2 (both use the
     center-x of the column) and y1 MUST equal sourceRect.bottom while y2
     MUST equal targetRect.top — then subtract 4-6px from y2 to leave
     breathing room for the arrowhead. Lines that fail to share the same
     x (or y) with their anchors will look detached / floating — NEVER
     allow that.
     SELF-CHECK BEFORE EMITTING: For every connector, verify
       (x1,y1) == an anchor of the source shape  AND
       (x2,y2) == (anchor of the target shape) ± a small inset toward source.
     If a connector's endpoints do not match any drawn shape's edge
     coordinates exactly, REWORK it before emitting the SVG. Floating /
     misaligned / disconnected lines are the most common SVG failure —
     they make the diagram look broken even when the rest is correct.
9. The <svg> must be self-contained — no external fonts, images, or stylesheets.
"""


def _flowchart_prompt(width: int, height: int) -> str:
    return _SHARED_RULES.format(width=width, height=height) + """

DIAGRAM HINT: FLOWCHART / PROCESS / SEQUENCE
The user picked the "Flowchart" preset. This is a HINT, not a hard constraint.
Interpret it as: "the topic likely benefits from showing a sequence, process,
flow, lifecycle, or how-things-connect relationship." Pick whatever visual
language best fits the user's request:
  - A classic linear flow of nodes connected by arrows.
  - A cycle (circular arrangement returning to the start).
  - A spiral, an arc, a stylized pipeline, a tree of branching outcomes.
  - A scene-style illustration where the "flow" is implied by composition
    (e.g. cell mitosis: draw the actual cells in their stages spread across
    the canvas, with thin arrows or just spatial order indicating sequence).
  - A combination — labelled illustration of a process with shapes/characters.
If you do use connector arrows, every arrowhead MUST terminate at a real
drawn shape — never into empty space. Each labeled element gets ONE short
name (1-3 words). Many elements may not need labels at all.
"""


def _infographic_prompt(width: int, height: int) -> str:
    return _SHARED_RULES.format(width=width, height=height) + """

DIAGRAM HINT: INFOGRAPHIC / CONCEPT VISUAL
The user picked the "Infographic" preset. This is a HINT, not a hard
constraint. Interpret it as: "the topic benefits from a single, clear
visual that breaks the concept into a few labelled parts." Pick whatever
visual language best fits the user's request:
  - A row or grid of simple stat / category cards.
  - A venn diagram, funnel, pyramid, or layered stack.
  - An anatomical sketch, molecular / biological structure, architectural
    cross-section, or stylized character with labelled regions.
  - A central hero shape with satellites/petals around it.
  - A scene-style illustration with a few labelled focal points.
Each labelled region/part gets ONE short name (1-3 words). Many parts may
need no label at all. Distribute elements to fill the canvas — do not
cluster them in one corner.
"""


def _org_chart_prompt(width: int, height: int) -> str:
    return _SHARED_RULES.format(width=width, height=height) + """

DIAGRAM HINT: ORG CHART / HIERARCHY / TREE
The user picked the "Org Chart" preset. This is a HINT, not a hard
constraint. Interpret it as: "the topic is a hierarchy, taxonomy, decision
tree, or parent→child relationship." Pick whatever visual language best
fits the user's request:
  - Classic boxes-and-lines tree (top-down or left-right).
  - A radial / sunburst tree (root in the centre, branches outward).
  - A layered architecture stack (rows from top to bottom).
  - A taxonomy with a hero element at the top and grouped descendants below.
  - A stylized natural tree / dendrogram with branches as the relationships.
Each item gets ONE short label (1-3 words). Connect parent→child with
simple lines or orthogonal polylines (no arrowheads needed for hierarchies).
Distribute the tree across the full canvas — anchor at top/centre and span
to the edges so the lowest level reaches the bottom area.
"""


_KIND_BUILDERS = {
    "flowchart": _flowchart_prompt,
    "infographic": _infographic_prompt,
    "org_chart": _org_chart_prompt,
}


def normalize_kind(kind: str | None) -> str:
    """Coerce input to a valid kind, defaulting to flowchart."""
    if not kind:
        return DEFAULT_KIND
    k = str(kind).strip().lower().replace("-", "_").replace(" ", "_")
    if k in ALLOWED_KINDS:
        return k
    # Common aliases
    aliases = {
        "flow": "flowchart",
        "process": "flowchart",
        "workflow": "flowchart",
        "infograph": "infographic",
        "stats": "infographic",
        "org": "org_chart",
        "orgchart": "org_chart",
        "hierarchy": "org_chart",
    }
    return aliases.get(k, DEFAULT_KIND)


def build_system_prompt(kind: str, width: int = 920, height: int = 440) -> str:
    """Build the kind-specific system prompt for the LLM."""
    kind = normalize_kind(kind)
    builder = _KIND_BUILDERS[kind]
    return builder(width, height)


def build_user_prompt(
    user_query: str,
    page_title: str = "",
    page_snippet: str = "",
    palette_hint: str = "",
    current_svg: str = "",
) -> str:
    """Build the user prompt combining the request with page context."""
    parts = [f"USER REQUEST: {user_query.strip()}"]
    if page_title:
        parts.append(f"PAGE TITLE: {page_title.strip()}")
    if page_snippet:
        parts.append(f"PAGE CONTEXT: {page_snippet.strip()[:500]}")
    if palette_hint:
        parts.append(
            f"PALETTE HINT: anchor the composition around this accent color: {palette_hint.strip()}. "
            "Build the rest of the palette (2-4 colors total) with complementary modern hues."
        )
    if current_svg:
        # Cap the inlined SVG so we don't blow the context window. Most LLM-emitted
        # diagrams are <8 KB; we keep the first 12 KB which is plenty for revision.
        svg_for_edit = current_svg.strip()
        if len(svg_for_edit) > 12000:
            svg_for_edit = svg_for_edit[:12000] + "...<truncated>"
        parts.append(
            "EDIT MODE: the user is editing an EXISTING diagram. Below is the current\n"
            "SVG markup. Treat the USER REQUEST above as edit instructions and produce\n"
            "a REVISED SVG that:\n"
            "  - Preserves the structure, layout, and styling that still applies.\n"
            "  - Applies the requested changes (add/remove/rename nodes, recolor,\n"
            "    rewire arrows, fix typos, restyle, etc.).\n"
            "  - Stays within the same width/height/viewBox.\n"
            "  - Continues to obey every rule from the system prompt (inline styles,\n"
            "    no <style>/class=, no comments, etc.).\n\n"
            f"CURRENT SVG:\n{svg_for_edit}"
        )
    parts.append(
        "Generate the diagram now. Remember: respond with JSON only, "
        '{"svg": "...", "title": "..."}'
    )
    return "\n\n".join(parts)


def build_template_slot_instruction(
    kind: str,
    width: int,
    height: int,
    palette_hint: str = "",
) -> str:
    """
    Build the instruction text for an `svg_diagram` slot embedded inside a
    larger template-generation request (see slide_templates.py / printable_templates.py).

    Unlike `build_system_prompt`, the calling LLM is expected to return the SVG as
    a value inside a wider slots-keyed JSON object, so this returns a slot-shaped
    instruction string ending with the exact JSON shape the slot processor expects:

        {"svgContent": "<svg ...>...</svg>",
         "fillColor": "#RRGGBB",
         "diagramTitle": "Short title",
         "diagramPrompt": "One-sentence description of the diagram"}

    `diagramPrompt` is captured by the slot processor and stored on the element so
    the user can later reopen the AI Diagram modal pre-filled with that prompt.
    """
    kind = normalize_kind(kind)
    body = _KIND_BUILDERS[kind](width, height)
    palette_line = (
        f"\n   * Anchor the palette around this accent color: {palette_hint.strip()} "
        "(build 5-7 complementary saturated hues around it)."
        if palette_hint
        else ""
    )
    return (
        body.rstrip()
        + "\n\nSLOT RETURN SHAPE (this slot is embedded inside a larger JSON response):\n"
        + '   Return the slot value as: {"svgContent": "<svg ...>...</svg>", '
        + '"fillColor": "#RRGGBB", "diagramTitle": "Short title", '
        + '"diagramPrompt": "One-sentence description of what the diagram depicts"}\n'
        + "   - svgContent: the full SVG markup obeying every rule above.\n"
        + "   - fillColor: optional accent color hex used for theme coherence.\n"
        + "   - diagramTitle: 2-6 word headline for this diagram.\n"
        + "   - diagramPrompt: one concise English sentence describing the content of the\n"
        + "     diagram (what it shows / its intent). This will be reused later if the user\n"
        + "     asks to regenerate the diagram, so write it as if it were the user's request."
        + palette_line
    )


# ---------------------------------------------------------------------------
# Sanitizer
# ---------------------------------------------------------------------------

# Tags that are removed entirely (open + content + close).
_FORBIDDEN_BLOCK_TAGS = (
    "script",
    "foreignObject",
    "filter",
    "pattern",
    "mask",
    "style",
)

# Tags that are removed as self-closing or empty pairs.
_FORBIDDEN_VOID_TAGS = ("image", "use", "iframe", "object", "embed", "audio", "video")

_BLOCK_TAG_RE = re.compile(
    r"<\s*(" + "|".join(_FORBIDDEN_BLOCK_TAGS) + r")\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_BLOCK_TAG_OPEN_RE = re.compile(
    r"<\s*(" + "|".join(_FORBIDDEN_BLOCK_TAGS) + r")\b[^>]*/?>",
    re.IGNORECASE,
)
_VOID_TAG_RE = re.compile(
    r"<\s*(" + "|".join(_FORBIDDEN_VOID_TAGS) + r")\b[^>]*/?>",
    re.IGNORECASE,
)
_VOID_TAG_PAIR_RE = re.compile(
    r"<\s*(" + "|".join(_FORBIDDEN_VOID_TAGS) + r")\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)

# on*="..." event handlers (case-insensitive, single or double quotes).
_EVENT_HANDLER_RE = re.compile(
    r"""\s+on[a-zA-Z]+\s*=\s*("([^"]*)"|'([^']*)')""",
    re.IGNORECASE,
)

# javascript: URLs in any attribute value.
_JS_URL_RE = re.compile(
    r"""(href|xlink:href|src)\s*=\s*("|')\s*javascript:[^"']*\2""",
    re.IGNORECASE,
)

# Remote href / xlink:href (http://, https://, //, file://, ftp://).
_REMOTE_HREF_RE = re.compile(
    r"""\s+(?:xlink:)?href\s*=\s*("|')\s*(?:https?:|ftp:|file:|//)[^"']*\1""",
    re.IGNORECASE,
)


def sanitize_svg(
    svg: str,
    max_bytes: int = MAX_SVG_BYTES,
    expected_width: int | None = None,
    expected_height: int | None = None,
) -> Tuple[bool, str, str]:
    """
    Sanitize raw LLM-produced SVG markup.

    Returns (ok, cleaned_svg, error_message).
    On failure returns (False, "", reason).

    If `expected_width` / `expected_height` are provided, the root <svg>
    element's `width`, `height`, and `viewBox` attributes are forced to
    `0 0 {expected_width} {expected_height}` regardless of what the LLM
    emitted. This prevents the common failure mode where the LLM remembers
    a prior slot size (e.g. 920x320) and lays out content for that canvas,
    causing offset bands and clipping when the new slot is 450x340.
    """
    if not svg or not isinstance(svg, str):
        return False, "", "empty SVG markup"

    s = svg.strip()
    # Strip optional XML prolog or doctype.
    s = re.sub(r"^<\?xml[^>]*\?>\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^<!DOCTYPE[^>]*>\s*", "", s, flags=re.IGNORECASE)
    s = s.strip()

    # Strip surrounding markdown fences if the LLM included them despite instructions.
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        if s.endswith("```"):
            s = s[: -3].rstrip()

    if not s.lower().lstrip().startswith("<svg"):
        return False, "", "markup does not start with <svg>"

    if len(s.encode("utf-8")) > max_bytes:
        return False, "", f"SVG exceeds size cap ({max_bytes} bytes)"

    # Strip forbidden block-level tags (with content).
    s = _BLOCK_TAG_RE.sub("", s)
    # Strip leftover open / self-closing forbidden block tags.
    s = _BLOCK_TAG_OPEN_RE.sub("", s)
    # Strip forbidden void/embed tags.
    s = _VOID_TAG_PAIR_RE.sub("", s)
    s = _VOID_TAG_RE.sub("", s)
    # Strip event handlers.
    s = _EVENT_HANDLER_RE.sub("", s)
    # Strip javascript: URL attributes.
    s = _JS_URL_RE.sub("", s)
    # Strip remote href / xlink:href.
    s = _REMOTE_HREF_RE.sub("", s)

    # Final sanity: must still contain </svg>.
    if "</svg>" not in s.lower():
        return False, "", "missing closing </svg> after sanitization"

    # ---- LLM mistake auto-fixes (deterministic) ----------------------------
    # 1) <circle ... y="N" ...>  →  <circle ... cy="N" ...>
    #    Same for x="N"  →  cx="N"  on circle/ellipse.
    # SVG ignores unknown attrs, so a misnamed `y` defaults the circle to cy=0
    # and every circle stacks at the top of the canvas (observed repeatedly
    # with deepseek nitro). Only rewrite when the correct attr is absent so
    # we never overwrite a legitimate value.
    def _fix_circle_attrs(match: "re.Match[str]") -> str:
        tag = match.group(1)  # "circle" or "ellipse"
        attrs = match.group(2)
        # cx fix
        if not re.search(r"\bcx\s*=", attrs) and re.search(r"\bx\s*=", attrs):
            attrs = re.sub(r"\bx(\s*=)", r"cx\1", attrs, count=1)
        # cy fix
        if not re.search(r"\bcy\s*=", attrs) and re.search(r"\by\s*=", attrs):
            attrs = re.sub(r"\by(\s*=)", r"cy\1", attrs, count=1)
        return f"<{tag}{attrs}>"

    s = re.sub(
        r"<(circle|ellipse)\b([^>]*)>",
        _fix_circle_attrs,
        s,
        flags=re.IGNORECASE,
    )

    # 2) Escape bare `&` in text content / attribute values to keep the SVG
    #    valid XML so it renders via <img src="data:image/svg+xml,...">.
    s = re.sub(
        r"&(?!(?:[A-Za-z][A-Za-z0-9]{1,30}|#\d{1,7}|#x[0-9A-Fa-f]{1,6});)",
        "&amp;",
        s,
    )

    # 3) Force preserveAspectRatio="xMidYMid meet" on the <svg> root so any
    #    content the LLM laid out beyond the viewBox (or a slot whose aspect
    #    differs from a square assumption) scales down to fit instead of
    #    getting clipped at the slot edge. If expected dims are provided,
    #    force the outer width/height to the slot size BUT preserve the LLM's
    #    viewBox — the viewBox describes the layout's coordinate space, so
    #    rewriting it would offset every drawn element. Combined with
    #    preserveAspectRatio="xMidYMid meet", a mismatched viewBox (e.g. the
    #    LLM laid out at 920x340 for a 450x340 slot) will scale-to-fit instead
    #    of being clipped.
    def _ensure_preserve_aspect_ratio(match: "re.Match[str]") -> str:
        attrs = match.group(1)
        if expected_width and expected_height:
            # Replace ONLY width / height; leave viewBox alone.
            attrs = re.sub(r"\s+width\s*=\s*(\"[^\"]*\"|'[^']*')", "", attrs, flags=re.IGNORECASE)
            attrs = re.sub(r"\s+height\s*=\s*(\"[^\"]*\"|'[^']*')", "", attrs, flags=re.IGNORECASE)
            forced = f' width="{expected_width}" height="{expected_height}"'
            # If the LLM didn't emit a viewBox at all, supply one so scaling has
            # a defined coordinate space.
            if not re.search(r"\bviewBox\s*=", attrs, flags=re.IGNORECASE):
                forced += f' viewBox="0 0 {expected_width} {expected_height}"'
        else:
            forced = ""
        if re.search(r"\bpreserveAspectRatio\s*=", attrs, flags=re.IGNORECASE):
            return f"<svg{forced}{attrs}>"
        return f'<svg preserveAspectRatio="xMidYMid meet"{forced}{attrs}>'

    s = re.sub(r"<svg([^>]*)>", _ensure_preserve_aspect_ratio, s, count=1, flags=re.IGNORECASE)

    return True, s, ""
