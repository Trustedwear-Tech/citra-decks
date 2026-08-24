# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
End-to-end test of the visual-critique path.

Layers exercised:
  1. Screenshot parsing (data URL / raw base64 / oversize / garbage)
  2. Patch applier (set / delete / add / field-allowlist / unknown actions)
  3. Post-patch position clamp (vision LLM moves elements off-canvas)
  4. Full critique_and_patch flow with a MOCKED vision client
  5. (optional) LIVE call to the configured z-ai/glm-4.6v endpoint with a
     synthetic broken slide — guarded by CRITIQUE_LIVE_TEST=1 so it doesn't
     spend credits on every run.

Run from Citra-Service repo root:
    python tests/test_critique_path.py
    CRITIQUE_LIVE_TEST=1 python tests/test_critique_path.py    # adds live call
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
from pathlib import Path

# Add repo root to sys.path so `services.visual_critique` resolves
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Load .env so VISION_* are picked up for the live test
try:
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────
# Layer 1 — screenshot parser
# ─────────────────────────────────────────────────────────────────────────
def test_parse_screenshot():
    from services.visual_critique import _parse_screenshot
    print("\n=== Layer 1: _parse_screenshot ===")

    # Tiny valid 1x1 PNG (transparent)
    tiny_png_b64 = base64.b64encode(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63000100000005000100c4dd7a4a0000000049454e44ae426082"
    )).decode()

    cases = [
        ("data URL",             f"data:image/png;base64,{tiny_png_b64}",     True,  "image/png"),
        ("data URL jpeg",        f"data:image/jpeg;base64,{tiny_png_b64}",    True,  "image/jpeg"),
        ("raw base64",           tiny_png_b64,                                True,  "image/png"),
        ("empty",                "",                                          False, None),
        ("whitespace",           "   ",                                       False, None),
        ("None-style",           None,                                        False, None),
        ("malformed data URL",   "data:notbase64,xxx",                        False, None),
        ("oversize",             "data:image/png;base64," + ("A" * 2_500_000), False, None),
    ]
    pass_ct, fail_ct = 0, 0
    for label, inp, expect_ok, expect_mime in cases:
        result = _parse_screenshot(inp)
        if expect_ok:
            ok = result is not None and result[0] == expect_mime
        else:
            ok = result is None
        status = "✓" if ok else "✗ FAIL"
        if ok:
            pass_ct += 1
        else:
            fail_ct += 1
        rdesc = "None" if result is None else f"({result[0]}, {len(result[1])} chars)"
        print(f"  {status:8s} {label:20s} → {rdesc}")
    print(f"  -> {pass_ct} pass, {fail_ct} fail")
    return fail_ct == 0


# ─────────────────────────────────────────────────────────────────────────
# Layer 2 — patch applier
# ─────────────────────────────────────────────────────────────────────────
def test_apply_patches():
    from services.visual_critique import _apply_patches
    print("\n=== Layer 2: _apply_patches ===")

    base_elements = [
        {"id": "title", "type": "text", "x": 50, "y": 30, "width": 800, "height": 60,
         "content": "Hello", "fill": "#000000", "fontSize": 36},
        {"id": "card",  "type": "shape", "x": 50, "y": 100, "width": 860, "height": 200,
         "fill": "#FFFFFF", "shapeType": "rectangle"},
        {"id": "bullets", "type": "text", "x": 60, "y": 110, "width": 840, "height": 180,
         "content": "• one\n• two", "fill": "#1F2937", "fontSize": 14},
    ]

    # --- 2a. set with allowed fields ---
    print("\n  2a. set with allowed fields (x, fill, fontSize)")
    patches = [{"action": "set", "id": "title",
                "fields": {"x": 100, "fill": "#FFFFFF", "fontSize": 40}}]
    new, n = _apply_patches([dict(e) for e in base_elements], patches)
    title = [e for e in new if e["id"] == "title"][0]
    assert title["x"] == 100 and title["fill"] == "#FFFFFF" and title["fontSize"] == 40, title
    print(f"    ✓ x=100, fill=#FFFFFF, fontSize=40, applied={n}")

    # --- 2b. set with disallowed field (type, content not in allowlist for set...) ---
    # Actually content IS allowed. Use `chartConfig` and `type` which aren't.
    print("\n  2b. set with disallowed fields silently dropped")
    patches = [{"action": "set", "id": "title",
                "fields": {"type": "image_placeholder", "chartConfig": {"foo": 1}, "fill": "#FF0000"}}]
    new, n = _apply_patches([dict(e) for e in base_elements], patches)
    title = [e for e in new if e["id"] == "title"][0]
    assert title["type"] == "text", "type should NOT be mutated by `set`"
    assert "chartConfig" not in title, "chartConfig should NOT be added by `set`"
    assert title["fill"] == "#FF0000", "fill should be applied"
    print(f"    ✓ type unchanged, chartConfig blocked, fill applied")

    # --- 2c. set targeting nonexistent id is dropped ---
    print("\n  2c. set targeting nonexistent id")
    patches = [{"action": "set", "id": "ghost", "fields": {"x": 999}}]
    new, n = _apply_patches([dict(e) for e in base_elements], patches)
    assert n == 0
    print(f"    ✓ no patches applied (n={n})")

    # --- 2d. delete ---
    print("\n  2d. delete")
    patches = [{"action": "delete", "id": "card"}]
    new, n = _apply_patches([dict(e) for e in base_elements], patches)
    ids = [e["id"] for e in new]
    assert "card" not in ids and len(new) == 2
    print(f"    ✓ card removed, ids={ids}")

    # --- 2e. add with all required fields ---
    print("\n  2e. add new element with full geometry")
    patches = [{"action": "add", "element": {
        "type": "shape", "x": 0, "y": 500, "width": 960, "height": 4, "fill": "#0EA5E9",
    }}]
    new, n = _apply_patches([dict(e) for e in base_elements], patches)
    added = [e for e in new if e.get("id", "").startswith("critique_add_")]
    assert len(added) == 1 and added[0]["zIndex"] == 25
    print(f"    ✓ added: id={added[0]['id']}, auto-zIndex=25")

    # --- 2f. add missing geometry is dropped ---
    print("\n  2f. add missing width/height is dropped")
    patches = [{"action": "add", "element": {"type": "shape", "x": 0, "y": 0}}]
    new, n = _apply_patches([dict(e) for e in base_elements], patches)
    assert n == 0
    print(f"    ✓ no patches applied (n={n})")

    # --- 2g. add unknown type is dropped ---
    print("\n  2g. add unknown type is dropped")
    patches = [{"action": "add", "element": {
        "type": "magical_unicorn", "x": 0, "y": 0, "width": 10, "height": 10,
    }}]
    new, n = _apply_patches([dict(e) for e in base_elements], patches)
    assert n == 0
    print(f"    ✓ no patches applied (n={n})")

    # --- 2h. unknown action is dropped ---
    print("\n  2h. unknown action ignored")
    patches = [{"action": "transform", "id": "title", "fields": {"x": 0}}]
    new, n = _apply_patches([dict(e) for e in base_elements], patches)
    assert n == 0
    print(f"    ✓ no patches applied (n={n})")

    # --- 2i. malformed patches array ---
    print("\n  2i. malformed patches input")
    new, n = _apply_patches(list(base_elements), "not-a-list")
    assert n == 0 and new == list(base_elements)
    new, n = _apply_patches(list(base_elements), [None, "string", 42, {}])
    assert n == 0
    print(f"    ✓ all malformed entries ignored")

    # --- 2j. mixed batch ---
    print("\n  2j. mixed batch: set + delete + add")
    patches = [
        {"action": "set",    "id": "title", "fields": {"fill": "#FF0000"}},
        {"action": "delete", "id": "bullets"},
        {"action": "add",    "element": {"type": "icon", "x": 10, "y": 10,
                                          "width": 24, "height": 24, "iconName": "check"}},
    ]
    new, n = _apply_patches([dict(e) for e in base_elements], patches)
    assert n == 3
    ids = [e["id"] for e in new]
    assert "bullets" not in ids
    assert "title" in ids
    assert any(e.get("iconName") == "check" for e in new)
    print(f"    ✓ all 3 applied, final ids={ids}")
    return True


# ─────────────────────────────────────────────────────────────────────────
# Layer 3 — end-to-end with mocked vision client
# ─────────────────────────────────────────────────────────────────────────
def _mock_vision_response(content_str):
    """Build a fake OpenAI-style ChatCompletion response."""
    class _Msg:
        def __init__(self, c): self.content = c
    class _Choice:
        def __init__(self, c):
            self.message = _Msg(c)
            self.finish_reason = "stop"
    class _R:
        def __init__(self, c):
            self.choices = [_Choice(c)]
            self.usage = type("U", (), {"prompt_tokens": 100, "completion_tokens": 50, "prompt_tokens_details": None})()
    return _R(content_str)


def _install_mock_vision(response_content: str):
    class _Completions:
        def create(self, **kw): return _mock_vision_response(response_content)
    class _Chat:
        def __init__(self): self.completions = _Completions()
    class _Client:
        def __init__(self): self.chat = _Chat()
    import citra_llm
    citra_llm.get_vision_client = lambda: _Client()
    citra_llm.get_vision_model = lambda: "mock/test"


_TINY_PNG = "data:image/png;base64," + base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63000100000005000100c4dd7a4a0000000049454e44ae426082"
)).decode()


def test_end_to_end_mocked():
    from services.visual_critique import critique_and_patch
    print("\n=== Layer 3: end-to-end with MOCKED vision client ===")

    elements = [
        {"id": "title", "type": "text", "x": 50, "y": 30, "width": 800, "height": 60,
         "content": "Hello world", "fill": "#FFFFFF", "fontSize": 36},
        {"id": "card", "type": "shape", "x": 0, "y": 100, "width": 960, "height": 200,
         "fill": "#FFFFFF", "shapeType": "rectangle"},
    ]

    # 3a. Clean JSON response with one off-canvas set
    print("\n  3a. clean JSON response + post-patch clamp")
    _install_mock_vision(json.dumps({
        "issues": [{"id": "title", "kind": "invisible", "desc": "white text on white card"}],
        "patches": [
            {"action": "set", "id": "title", "fields": {"fill": "#111827", "x": 2000}},
        ],
    }))
    result = asyncio.run(critique_and_patch(
        elements=elements, screenshot=_TINY_PNG, canvas={"width": 960, "height": 540},
    ))
    title = [e for e in result["elements"] if e["id"] == "title"][0]
    assert title["fill"] == "#111827", f"fill patch failed: {title}"
    assert title["x"] < 960, f"post-clamp didn't run, x={title['x']}"
    print(f"    ✓ fill applied (#111827), x clamped from 2000 → {title['x']}")
    print(f"    issues: {result['issues']}")
    print(f"    patches_applied: {result['patches_applied']}")

    # 3b. Markdown-fenced JSON (some models wrap in ```json ... ```)
    print("\n  3b. markdown-fenced response is parsed")
    fenced = "Here is my critique:\n```json\n" + json.dumps({
        "issues": [], "patches": [{"action": "set", "id": "title", "fields": {"fontSize": 48}}],
    }) + "\n```\nLet me know if you need more."
    _install_mock_vision(fenced)
    result = asyncio.run(critique_and_patch(
        elements=elements, screenshot=_TINY_PNG, canvas={"width": 960, "height": 540},
    ))
    title = [e for e in result["elements"] if e["id"] == "title"][0]
    assert title["fontSize"] == 48, f"fence-strip parser failed: {title}"
    print(f"    ✓ parsed through ```json fence, fontSize=48")

    # 3c. Surrounded by prose (no fences) — outermost-brace extraction
    print("\n  3c. prose-wrapped JSON parsed via outermost-brace fallback")
    proseless = 'Looking at this slide, I notice: {"issues":[],"patches":[{"action":"delete","id":"card"}]} Hope that helps.'
    _install_mock_vision(proseless)
    result = asyncio.run(critique_and_patch(
        elements=elements, screenshot=_TINY_PNG, canvas={"width": 960, "height": 540},
    ))
    ids = [e["id"] for e in result["elements"]]
    assert "card" not in ids
    print(f"    ✓ outermost-brace parse worked, card deleted, final ids={ids}")

    # 3d. Garbage response → safe fallback (original elements returned)
    print("\n  3d. garbage response → safe fallback")
    _install_mock_vision("I refuse to help with this image.")
    result = asyncio.run(critique_and_patch(
        elements=elements, screenshot=_TINY_PNG, canvas={"width": 960, "height": 540},
    ))
    assert result["patches_applied"] == 0
    assert len(result["elements"]) == len(elements)
    assert "non-JSON" in result.get("note", "")
    print(f"    ✓ original elements preserved, note='{result['note']}'")

    # 3e. Empty issues + empty patches → no-op
    print("\n  3e. empty issues + empty patches → no-op")
    _install_mock_vision('{"issues":[],"patches":[]}')
    result = asyncio.run(critique_and_patch(
        elements=elements, screenshot=_TINY_PNG, canvas={"width": 960, "height": 540},
    ))
    assert result["patches_applied"] == 0
    assert len(result["elements"]) == len(elements)
    print(f"    ✓ no patches applied, no issues, elements unchanged")

    # 3f. Oversized screenshot → safe fallback
    print("\n  3f. oversized screenshot → safe fallback")
    huge = "data:image/png;base64," + ("A" * 2_500_000)
    result = asyncio.run(critique_and_patch(
        elements=elements, screenshot=huge, canvas={"width": 960, "height": 540},
    ))
    assert "oversized" in result.get("note", "") or "invalid" in result.get("note", "")
    assert result["patches_applied"] == 0
    print(f"    ✓ rejected early, note='{result['note']}'")

    return True


# ─────────────────────────────────────────────────────────────────────────
# Layer 4 — LIVE call to z-ai/glm-4.6v (only when CRITIQUE_LIVE_TEST=1)
# ─────────────────────────────────────────────────────────────────────────
def _build_synthetic_broken_slide():
    """Render a 960x540 PNG with deliberate visual defects:
       - Title text overflowing the right edge
       - White-on-white invisible subtitle
       - Body text overlapping a card edge
    Returns a base64 data URL."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (960, 540), (240, 244, 250))   # light bg
    draw = ImageDraw.Draw(img)

    # Card background
    draw.rectangle([40, 90, 920, 320], fill=(255, 255, 255), outline=(220, 224, 230))

    # Defect 1: title intentionally too long, overflowing past x=920
    try:
        font_title = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        font_title = ImageFont.load_default()
    draw.text((50, 30), "This Is An Excessively Long Slide Title That Runs Past The Edge", font=font_title, fill=(15, 23, 42))

    # Defect 2: subtitle white-on-white inside white card (invisible)
    try:
        font_sub = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font_sub = ImageFont.load_default()
    draw.text((60, 110), "Invisible white subtitle on white card", font=font_sub, fill=(255, 255, 255))

    # Defect 3: body text overlapping the card's bottom border + extending past right edge
    try:
        font_body = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font_body = ImageFont.load_default()
    long_body = ("Body paragraph that intentionally goes way too far to the right "
                 "and clips off the card edge because the LLM picked a width too small. "
                 "It also extends below the card's lower boundary.")
    draw.text((60, 290), long_body, font=font_body, fill=(31, 41, 55))

    # Defect 4: icon-style square overlapping the title
    draw.rectangle([200, 30, 250, 80], fill=(56, 189, 248))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}", len(buf.getvalue())


def test_live_glm_4_6v():
    print("\n=== Layer 4: LIVE call to z-ai/glm-4.6v (CRITIQUE_LIVE_TEST=1) ===")
    if os.getenv("CRITIQUE_LIVE_TEST") != "1":
        print("  (skipped — set CRITIQUE_LIVE_TEST=1 to run; costs credits)")
        return True

    # Reset the citra_llm mock so we hit the real client
    import importlib, citra_llm
    importlib.reload(citra_llm)

    vision_model = os.getenv("VISION_MODEL", "")
    vision_url = os.getenv("VISION_BASE_URL", "")
    if not vision_model or not vision_url:
        print(f"  SKIP: VISION_MODEL or VISION_BASE_URL not set")
        return True
    print(f"  Using VISION_MODEL={vision_model}")
    print(f"  Using VISION_BASE_URL={vision_url}")

    data_url, png_bytes = _build_synthetic_broken_slide()
    print(f"  Synthetic slide PNG: {png_bytes:,} bytes")

    # Element JSON describing the broken slide (the model should propose patches)
    elements = [
        {"id": "title", "type": "text", "x": 50, "y": 30, "width": 870, "height": 50,
         "content": "This Is An Excessively Long Slide Title That Runs Past The Edge",
         "fill": "#0F172A", "fontSize": 36},
        {"id": "card_bg", "type": "shape", "x": 40, "y": 90, "width": 880, "height": 230,
         "fill": "#FFFFFF", "shapeType": "rectangle"},
        {"id": "subtitle", "type": "text", "x": 60, "y": 110, "width": 800, "height": 28,
         "content": "Invisible white subtitle on white card",
         "fill": "#FFFFFF", "fontSize": 18},
        {"id": "body", "type": "text", "x": 60, "y": 290, "width": 900, "height": 40,
         "content": "Body paragraph that intentionally goes way too far to the right and clips off the card edge.",
         "fill": "#1F2937", "fontSize": 14},
        {"id": "icon", "type": "shape", "x": 200, "y": 30, "width": 50, "height": 50,
         "fill": "#38BDF8", "shapeType": "rectangle"},
    ]

    from services.visual_critique import critique_and_patch
    import time, copy
    # Deep-copy BEFORE the call — `critique_and_patch` shares dict refs with
    # the input list, so mutations propagate back unless we snapshot first.
    pre = copy.deepcopy(elements)
    t0 = time.time()
    result = asyncio.run(critique_and_patch(
        elements=elements, screenshot=data_url,
        slide_info={"title": "Synthetic Broken Slide", "content_hint": "test rig"},
        canvas={"width": 960, "height": 540},
    ))
    dt = time.time() - t0
    print(f"  Vision call returned in {dt:.1f}s")
    print(f"  Issues found: {len(result['issues'])}")
    for iss in result["issues"][:6]:
        if isinstance(iss, dict):
            print(f"    - [{iss.get('kind','?')}] on '{iss.get('id','-')}': {iss.get('desc','')}")
    print(f"  Patches applied: {result['patches_applied']}")
    if result.get("note"):
        print(f"  Note: {result['note']}")
    # Show before/after diff — compare against the DEEP-COPY snapshot
    by_id_before = {e["id"]: e for e in pre}
    print("\n  Changed elements:")
    any_changed = False
    for e in result["elements"]:
        before = by_id_before.get(e.get("id"))
        if before is None:
            print(f"    + ADDED   {e}")
            any_changed = True
            continue
        # Diff against keys in EITHER side (so post-clamp-added keys show up)
        all_keys = set(before.keys()) | set(e.keys())
        diff = {k: {"before": before.get(k), "after": e.get(k)} for k in all_keys
                if before.get(k) != e.get(k)}
        if diff:
            print(f"    ~ MUTATED {e['id']}:")
            for k, vv in diff.items():
                print(f"        {k}: {vv['before']!r} -> {vv['after']!r}")
            any_changed = True
    if not any_changed:
        print("    (no element changes — model returned only issues, no usable patches)")
    return True


def main():
    print("=" * 70)
    print("Visual-critique end-to-end test")
    print("=" * 70)
    results = [
        ("parse_screenshot",    test_parse_screenshot()),
        ("apply_patches",       test_apply_patches()),
        ("end_to_end_mocked",   test_end_to_end_mocked()),
        ("live_glm_4_6v",       test_live_glm_4_6v()),
    ]
    print("\n" + "=" * 70)
    print("Summary:")
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL':4s}  {name}")
    print("=" * 70)
    if not all(ok for _, ok in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
