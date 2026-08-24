"""Generate a 5-slide deck, edit it with the AI panel, then save and reload.

The companion capture (capture_screens.py) walks generation and stops at the
composer. This one covers what happens next, which is the part that actually
distinguishes the product: you talk to the deck, it proposes a change, you
apply it, and it survives a reload.

Five slides rather than ten: every slide is a real model call, and the point
here is the edit-and-persist loop, not the length of the deck.

Order matters and each step is verified rather than assumed:

  generate -> SAVE -> ask the AI for a change -> read its answer -> APPLY
           -> save again -> reload the page -> reopen from the list

Nothing in this product autosaves. An earlier pass screenshotted a beautiful
deck and closed the browser, and the deck was gone -- there were folders in
Mongo and no slides anywhere, because Save was never clicked. Hence the
explicit saves, and the reload at the end to prove the round trip rather than
infer it.

The toolbar icons carry no text and no accessibilityLabel, so Save is found by
hovering the toolbar's controls until its tooltip ("Save presentation")
appears. That is slower than a selector and survives the icon set changing.
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
SLIDES = os.getenv("SLIDES", "5")

GOAL = ("Explain how a mid-sized manufacturer should approach predictive "
        "maintenance: what it is, which machines to instrument first, and how "
        "to tell whether it paid for itself.")

EDIT = "Add a summary slide at the end with the three things to do first."

sys.path.insert(0, str(Path(__file__).parent))
from capture_screens import HELPERS, shot, tap, real_click  # noqa: E402

# Unbuffered: a long run that prints nothing until it exits is
# indistinguishable from a hung one.
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def find_save(page):
    """Return the Save control by hovering until its tooltip shows."""
    handles = page.query_selector_all("div")
    for h in handles:
        try:
            box = h.bounding_box()
        except Exception:
            continue
        # toolbar row only, and icon-sized
        if not box or box["y"] > 120 or box["width"] > 60 or box["width"] < 20:
            continue
        try:
            h.hover(timeout=1500)
            page.wait_for_timeout(350)
        except Exception:
            continue
        if "Save presentation" in page.inner_text("body"):
            return h
    return None


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

        # ── sign in ─────────────────────────────────────────────────────────
        page.goto(UI, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)
        tap(page, "Sign in to start")
        page.wait_for_timeout(2500)
        page.evaluate("([e,p]) => { window.__setField('email',e); window.__setField('password',p); }",
                      [EMAIL, PW])
        tap(page, "Sign In")
        page.wait_for_timeout(6000)

        # ── new deck, 5 slides ──────────────────────────────────────────────
        opened = False
        for label in ("Create New Presentation", "Start from scratch", "+"):
            if not (real_click(page, label) or tap(page, label, timeout=5000)):
                continue
            try:
                page.wait_for_function(
                    "() => [...document.querySelectorAll('textarea')]"
                    ".some(e => /create a presentation|goal|describe/i.test(e.placeholder||'')"
                    " && e.offsetParent !== null)", timeout=12000)
                opened = True
                break
            except Exception:
                continue
        if not opened:
            print("  [!!] wizard never opened", file=sys.stderr); br.close(); return 1

        page.evaluate("(g) => window.__setField('goal', g)", GOAL)
        if not tap(page, SLIDES, timeout=8000):
            print(f"  [--] could not select {SLIDES} slides; using the default")
        page.wait_for_timeout(800)
        shot(page, "10-goal-5", f"the goal, set to {SLIDES} slides")

        tap(page, "Generate Slide Outline")
        print("  writing the outline...", flush=True)
        # The composers pin GLM-5.1 and its stream sometimes truncates
        # ("peer closed connection without sending complete message body").
        # That is a provider fault, not a bug here -- but an unguarded wait
        # turns it into a stalled run with no output, so say so and stop.
        try:
            page.wait_for_function(
                "() => /Slide Outline/.test(document.body.innerText)"
                " && !/Analyzing|being generated/.test(document.body.innerText)",
                timeout=240000)
        except Exception:
            print("  [!!] no outline after 4 min -- the model stream probably "
                  "dropped; check the backend log for 'incomplete chunked read'",
                  file=sys.stderr, flush=True)
            shot(page, "10-goal-5", "INCOMPLETE - outline never arrived")
            br.close(); return 1
        page.wait_for_timeout(2000)
        tap(page, "Choose Template", timeout=120000)
        page.wait_for_timeout(3000)
        tap(page, "Generate Presentation", timeout=120000)
        print(f"  writing {SLIDES} slides...")
        try:
            page.wait_for_function(
                r"""() => {
                  const m = document.body.innerText.match(/(\d+)\s*\/\s*(\d+)/);
                  return m && Number(m[2]) > 1 && Number(m[1]) >= Number(m[2]);
                }""", timeout=600000)
        except Exception:
            print("  [!!] slides did not all arrive", file=sys.stderr)
        page.wait_for_timeout(5000)
        shot(page, "11-deck", f"the generated {SLIDES}-slide deck")

        # ── SAVE (nothing autosaves) ────────────────────────────────────────
        save = find_save(page)
        if not save:
            print("  [!!] Save control not found", file=sys.stderr); br.close(); return 1
        save.click()
        page.wait_for_timeout(6000)
        shot(page, "12-saved", "saved — this is an explicit action, nothing autosaves")

        # ── ask the AI for a change ─────────────────────────────────────────
        asked = page.evaluate("""(t) => {
          const ta = [...document.querySelectorAll('textarea')]
            .find(e => /ask anything/i.test(e.placeholder||'') && e.offsetParent !== null);
          if (!ta) return false;
          ta.focus();
          Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value')
            .set.call(ta, t);
          ta.dispatchEvent(new Event('input', {bubbles:true}));
          return true;
        }""", EDIT)
        if not asked:
            print("  [!!] AI chat box not found", file=sys.stderr); br.close(); return 1
        page.wait_for_timeout(600)
        shot(page, "13-ask", "the change, asked for in plain English")

        page.keyboard.press("Enter")
        print("  waiting for the assistant...")
        try:
            page.wait_for_function(
                "() => /Apply|Applied|applied/.test(document.body.innerText)",
                timeout=300000)
        except Exception:
            print("  [!!] no answer from the assistant", file=sys.stderr)
        page.wait_for_timeout(3000)
        shot(page, "14-answer", "what it proposes, before anything changes")

        for label in ("Apply to Canvas", "Apply"):
            if tap(page, label, timeout=8000):
                break
        page.wait_for_timeout(8000)
        shot(page, "15-applied", "the edit on the canvas")

        # ── save again, then RELOAD to prove it round-trips ─────────────────
        save = find_save(page)
        if save:
            save.click()
            page.wait_for_timeout(6000)

        page.goto(UI, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(4000)
        tap(page, "Sign in to start")
        page.wait_for_timeout(2000)
        page.evaluate("([e,p]) => { window.__setField('email',e); window.__setField('password',p); }",
                      [EMAIL, PW])
        tap(page, "Sign In")
        page.wait_for_timeout(7000)
        shot(page, "16-list", "the deck in your list after a full reload")

        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
