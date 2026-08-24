"""Open a deck's data store from the toolbar and photograph what it offers.

The README claims documents "stay until you delete them", so the delete has to
exist and be reachable -- a claim about retention is only half a claim without
the other half.

The control is the folder icon in the toolbar (tooltip: "View data source
folder"), which opens FolderDetailModal against this deck's folder. Toolbar
icons carry no text or accessibilityLabel, so it is found by hovering until its
tooltip appears -- the same approach the Save button needs.
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

sys.path.insert(0, str(Path(__file__).parent))
from capture_screens import HELPERS, shot, tap  # noqa: E402

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def hover_toolbar(page, tooltip: str):
    """Return the toolbar control whose tooltip matches."""
    for h in page.query_selector_all("div"):
        try:
            box = h.bounding_box()
        except Exception:
            continue
        if not box or box["y"] > 120 or not (20 < box["width"] < 60):
            continue
        try:
            h.hover(timeout=1200)
            page.wait_for_timeout(300)
        except Exception:
            continue
        if tooltip in page.inner_text("body"):
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

        page.goto(UI, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)
        tap(page, "Sign in to start")
        page.wait_for_timeout(2500)
        page.evaluate("([e,p]) => { window.__setField('email',e); window.__setField('password',p); }",
                      [EMAIL, PW])
        tap(page, "Sign In")
        page.wait_for_timeout(6000)

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
            print("  [!!] no saved deck to open", file=sys.stderr)
            br.close(); return 1
        try:
            page.wait_for_function(
                "() => /Slide \\d+ of \\d+/.test(document.body.innerText)", timeout=60000)
        except Exception:
            print("  [!!] the deck did not open", file=sys.stderr)
        page.wait_for_timeout(6000)

        ctl = hover_toolbar(page, "View data source folder")
        if not ctl:
            print("  [!!] the data-store control is not in the toolbar", file=sys.stderr)
            br.close(); return 1
        ctl.click()
        page.wait_for_timeout(7000)
        shot(page, "32-vault", "the deck's data store: what it has read, and delete")

        body = " ".join(page.inner_text("body").split())
        for word in ("Delete", "delete"):
            if word in body:
                print(f"  delete control present ({word!r} on screen)")
                break
        else:
            print("  [!!] no delete control visible in the data store",
                  file=sys.stderr)
        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
