# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""Capture the two places you can put your own documents into a deck.

This is the thing that separates citra-decks from a generic slide generator:
the deck is written FROM your files, not from the model's general knowledge.
There are two entry points and they serve different moments --

  * the goal step, before anything exists: "here is the material, now write me
    a deck from it";
  * the paperclip beside the AI chat, once the deck is open: "here is one more
    document, use it for the change I am about to ask for".

Both land in the same per-artifact data store (a folder, one per deck) and are
embedded into Milvus, where they stay until you delete them.

Run with an existing saved deck present -- the chat attach only exists inside a
composer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

UI = os.getenv("UI", "http://localhost:8094")
EMAIL = os.environ.get("DECK_EMAIL", "")
PW = os.environ.get("DECK_PW", "")
OUT = Path(os.getenv("OUT", r"C:\Github\citra-decks\assets\screens"))
DOC = os.getenv("DOC", r"C:\Users\rohit\AppData\Local\Temp\deckdocs\plant-maintenance-review-2026.md")

sys.path.insert(0, str(Path(__file__).parent))
from capture_screens import HELPERS, shot, tap, real_click  # noqa: E402

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def sign_in(page) -> None:
    page.goto(UI, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2500)
    tap(page, "Sign in to start")
    page.wait_for_timeout(2500)
    page.evaluate("([e,p]) => { window.__setField('email',e); window.__setField('password',p); }",
                  [EMAIL, PW])
    tap(page, "Sign In")
    page.wait_for_timeout(6000)


def main() -> int:
    if not (EMAIL and PW):
        print("  DECK_EMAIL / DECK_PW not set", file=sys.stderr)
        return 1
    if not Path(DOC).exists():
        print(f"  no such document: {DOC}", file=sys.stderr)
        return 1

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=os.getenv("HEADED") != "1",
                                slow_mo=300 if os.getenv("HEADED") == "1" else 0)
        page = br.new_page(viewport={"width": 1440, "height": 900},
                           device_scale_factor=2)
        page.add_init_script(HELPERS)
        sign_in(page)

        # ── 1. the goal step, before the deck exists ────────────────────────
        for label in ("Create New Presentation", "Start from scratch", "+"):
            if not (real_click(page, label) or tap(page, label, timeout=5000)):
                continue
            try:
                page.wait_for_function(
                    "() => [...document.querySelectorAll('textarea')]"
                    ".some(e => /create a presentation|goal|describe/i.test(e.placeholder||'')"
                    " && e.offsetParent !== null)", timeout=12000)
                break
            except Exception:
                continue

        # The file input is hidden behind a styled control; set_input_files on
        # the input itself is both more reliable than clicking and closer to
        # what the control ends up doing.
        try:
            page.set_input_files("input[type=file]", DOC, timeout=15000)
            print(f"  goal step: attached {Path(DOC).name}")
        except Exception as exc:
            print(f"  [!!] goal-step upload not available ({exc.__class__.__name__})",
                  file=sys.stderr)
        page.wait_for_timeout(6000)
        shot(page, "30-upload-goal",
             "attaching source documents before the deck is written")

        # ── 2. the paperclip inside the composer ───────────────────────────
        page.goto(UI, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        sign_in(page)
        opened = page.evaluate("""() => {
          const want = /mid-sized manufacturer|Predictive|Untitled presentation/i;
          for (const e of document.querySelectorAll('*')) {
            if (e.children.length !== 0 || !want.test(e.textContent||'')) continue;
            let p = e;
            for (let i=0;i<8&&p;i++) {
              if (/r-1loqt21/.test((p.className||'').toString())) {
                const r = p.getBoundingClientRect();
                const o = {bubbles:true,cancelable:true,clientX:r.x+r.width/2,
                           clientY:r.y+r.height/2,button:0,pointerId:1,isPrimary:true};
                for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
                  p.dispatchEvent(t.startsWith('pointer')?new PointerEvent(t,o):new MouseEvent(t,o));
                return true;
              }
              p = p.parentElement;
            }
          }
          return false;
        }""")
        if not opened:
            print("  [!!] no saved deck to open -- skipping the chat attach",
                  file=sys.stderr)
            br.close(); return 1
        try:
            page.wait_for_function(
                "() => /Slide \\d+ of \\d+/.test(document.body.innerText)", timeout=60000)
        except Exception:
            print("  [!!] the deck did not open", file=sys.stderr)
        page.wait_for_timeout(6000)

        # Click the paperclip so the upload UI is actually on screen. Setting
        # the hidden input directly attaches the file but shows nothing, which
        # makes for a screenshot of a button rather than of the feature.
        clicked = page.evaluate("""() => {
          // the paperclip sits just above the chat box, bottom of the AI panel
          const ta = [...document.querySelectorAll('textarea')]
            .find(e => /ask anything/i.test(e.placeholder||'') && e.offsetParent !== null);
          if (!ta) return false;
          const tr = ta.getBoundingClientRect();
          const cands = [...document.querySelectorAll('*')].filter(e => {
            const r = e.getBoundingClientRect();
            return r.width > 24 && r.width < 70 && r.height > 24 && r.height < 70
                && r.bottom < tr.top && r.bottom > tr.top - 120 && r.left > tr.left - 60;
          });
          const el = cands[cands.length - 1];
          if (!el) return false;
          const r = el.getBoundingClientRect();
          const o = {bubbles:true,cancelable:true,clientX:r.x+r.width/2,
                     clientY:r.y+r.height/2,button:0,pointerId:1,isPrimary:true};
          for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
            el.dispatchEvent(t.startsWith('pointer')?new PointerEvent(t,o):new MouseEvent(t,o));
          return true;
        }""")
        print(f"  chat attach: paperclip {'clicked' if clicked else 'NOT FOUND'}")
        page.wait_for_timeout(4000)
        try:
            page.set_input_files("input[type=file]", DOC, timeout=8000)
            print(f"  chat attach: attached {Path(DOC).name}")
        except Exception as exc:
            print(f"  [--] file input not reachable ({exc.__class__.__name__})")
        page.wait_for_timeout(7000)
        shot(page, "31-upload-chat",
             "attaching one more document to an open deck, from the AI panel")

        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
