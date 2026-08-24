# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""Open a SAVED deck, edit it with the AI panel, and save the result.

Split out from capture_edit_flow.py deliberately: that one regenerates a deck
every run (five real model calls, ~8 minutes) before it can get anywhere near
the assistant. Once a deck is saved, the interesting loop -- open it, ask for a
change, watch what it proposes, apply, save -- costs one model call and proves
LOAD at the same time, because the deck has to come back off disk first.

Two things worth knowing before reading the code:

  * "Enhance" is the SEND button for the AI panel. It does not look like one,
    and pressing Enter in the box does nothing -- an earlier pass typed a
    perfectly good instruction, pressed Enter, screenshotted, and captured the
    text still sitting unsent in the textarea while the panel showed its
    default suggestions. Nothing said it had failed.

  * Nothing autosaves. The save at the end is what makes the edit outlive the
    tab, and the toolbar's Save carries no text or accessibilityLabel, so it is
    found by hovering the toolbar until its tooltip appears.
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
EDIT = os.getenv("EDIT", "Add a summary slide at the end with the three things to do first.")

sys.path.insert(0, str(Path(__file__).parent))
from capture_screens import HELPERS, shot, tap, real_click  # noqa: E402
from capture_edit_flow import find_save  # noqa: E402

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def main() -> int:
    if not (EMAIL and PW):
        print("  DECK_EMAIL / DECK_PW not set", file=sys.stderr)
        return 1

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=os.getenv("HEADED") != "1",
                                slow_mo=300 if os.getenv("HEADED") == "1" else 0)
        page = br.new_page(viewport={"width": 1440, "height": 900},
                           device_scale_factor=2)
        page.add_init_script(HELPERS)

        page.goto(UI, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)
        tap(page, "Sign in to start")
        page.wait_for_timeout(2500)
        page.evaluate("([e,p]) => { window.__setField('email',e); window.__setField('password',p); }",
                      [EMAIL, PW])
        tap(page, "Sign In")
        page.wait_for_timeout(6000)
        shot(page, "16-list", "the saved deck, listed after a full reload")

        # ── LOAD: open the saved deck ───────────────────────────────────────
        # Click the CARD, not its title. The title is a text node inside the
        # tile; the handler is on the tile. Clicking the words did nothing and
        # the run then reported "AI chat box not found", which described the
        # consequence rather than the cause.
        # The card is a real TouchableOpacity (PresentationListModal.js:335,
        # onPress -> handleLoadPresentation), so DISPATCH to the pressable
        # rather than clicking coordinates. Two earlier attempts aimed the
        # mouse at the title and then at the "N slides" badge; both landed on
        # the modal backdrop, closed the list, and left the run on the landing
        # page -- which then reported "AI chat box not found".
        opened = page.evaluate("""() => {
          const want = /mid-sized manufacturer|Predictive|Untitled presentation/i;
          for (const e of document.querySelectorAll('*')) {
            if (e.children.length !== 0) continue;
            if (!want.test(e.textContent || '')) continue;
            let p = e;
            for (let i = 0; i < 8 && p; i++) {
              if (/r-1loqt21/.test((p.className||'').toString())) {
                const r = p.getBoundingClientRect();
                const o = {bubbles:true, cancelable:true,
                           clientX:r.x+r.width/2, clientY:r.y+r.height/2,
                           button:0, pointerId:1, isPrimary:true};
                for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
                  p.dispatchEvent(t.startsWith('pointer')
                    ? new PointerEvent(t,o) : new MouseEvent(t,o));
                return {t: (e.textContent||'').trim(),
                        w: Math.round(r.width), h: Math.round(r.height)};
              }
              p = p.parentElement;
            }
          }
          return null;
        }""")
        try:
            page.wait_for_function(
                "() => /Slide \\d+ of \\d+/.test(document.body.innerText)", timeout=60000)
        except Exception:
            print("  [!!] the deck did not open", file=sys.stderr)
        page.wait_for_timeout(6000)
        shot(page, "17-loaded", "the deck reopened from storage, slides intact")

        # ── ASK ─────────────────────────────────────────────────────────────
        # Type with REAL key events. Setting .value + an input event is enough
        # for the login fields, but this box is a controlled RNW TextInput: the
        # text appeared in the DOM while React's state stayed empty, so
        # "Enhance" sent nothing and the backend never saw a request. The only
        # symptom was a panel that never answered.
        box = page.locator("textarea").filter(has_not=page.locator("[disabled]")).last
        try:
            box = page.get_by_placeholder("Ask anything", exact=False)
            box.click(timeout=10000)
            box.fill(EDIT, timeout=10000)
        except Exception as exc:
            print(f"  [!!] could not type into the AI chat box ({exc.__class__.__name__})",
                  file=sys.stderr)
            br.close(); return 1
        page.wait_for_timeout(600)
        shot(page, "18-ask", "the change, asked for in plain English")

        # "Enhance" is the send button (PresentationComposer.js:5968 ->
        # handleAgentEdit), and it is DISABLED while chatInput is empty -- which
        # is why setting the textarea's .value achieved nothing: the DOM showed
        # the text, React's state did not, and the button never enabled.
        #
        # Pressed with a real click rather than a dispatched pointer sequence.
        # The synthetic one enabled-and-visible button still did not fire; a
        # trusted event does.
        try:
            page.get_by_text("Enhance", exact=True).last.click(timeout=10000)
        except Exception as exc:
            print(f"  [!!] could not press Enhance ({exc.__class__.__name__})",
                  file=sys.stderr)
            br.close(); return 1
        print("  waiting for the assistant...")
        # The send button is the progress indicator: it reads "Stop" while the
        # agent loop runs and returns to "Enhance" when it finishes. Waiting on
        # text appearing in the panel is not enough -- the model's reasoning
        # streams in long before the slide lands, and capturing then shows a
        # half-applied deck with the button still on Stop.
        try:
            page.wait_for_function(
                "() => document.body.innerText.includes('Stop')", timeout=60000)
        except Exception:
            print("  [!!] the agent never started", file=sys.stderr)
            br.close(); return 1
        print("  agent running...")
        try:
            page.wait_for_function(
                "() => !document.body.innerText.includes('Stop')", timeout=420000)
        except Exception:
            print("  [!!] agent still running after 7 min -- capturing anyway",
                  file=sys.stderr)
        page.wait_for_timeout(6000)
        shot(page, "19-answer", "the request, and what it decided to do")

        for label in ("Apply to Canvas", "Apply"):
            if tap(page, label, timeout=6000):
                print(f"  applied via {label!r}")
                break
        page.wait_for_timeout(9000)
        shot(page, "20-applied", "the edit on the canvas")

        save = find_save(page)
        if save:
            save.click()
            page.wait_for_timeout(6000)
            shot(page, "21-saved", "saved again — the edit outlives the tab")
        else:
            print("  [!!] Save control not found after the edit", file=sys.stderr)

        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
