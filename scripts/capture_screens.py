# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""Capture the citra-decks flow end to end, in the order a user meets it.

Landing -> sign in -> your decks -> describe the goal -> outline -> template ->
generating -> the composer with real slides -> present. The shots are numbered
in that order so the README can read as one path rather than a gallery.

Two things this has to work around, both from the UI being React Native Web:

  * Pressables render as role-less <div>s that ignore page.click(). Every tap
    walks up to the nearest element carrying RNW's cursor-pointer class and
    dispatches a full pointer sequence.
  * TextInput ignores synthetic typing; values go through the native setter
    plus an input event, which is what React listens for.

Generation is a real model call per slide and takes minutes, so the waits here
are long on purpose. A shot that cannot be taken is reported and skipped -- a
missing screenshot beats one of a half-rendered screen.
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

GOAL = ("Explain how a mid-sized manufacturer should approach predictive "
        "maintenance: what it is, which machines are worth instrumenting first, "
        "the data needed, a realistic 12-month rollout, and how to measure "
        "whether it paid for itself.")

HELPERS = """
window.__tapEl = (el) => {
  const r = el.getBoundingClientRect();
  const o = {bubbles:true, cancelable:true, clientX:r.x+r.width/2,
             clientY:r.y+r.height/2, button:0, pointerId:1, isPrimary:true};
  for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
    el.dispatchEvent(t.startsWith('pointer') ? new PointerEvent(t,o) : new MouseEvent(t,o));
  return true;
};
// Index PRESSABLES, not text nodes: a label often appears twice (a heading and
// the control) and only one of them has a handler.
window.__pressables = (txt) => {
  // r-1loqt21 is RNW's marker for an actual Pressable. Matching on
  // cursor:pointer instead pulls in headings that merely sit inside one -- on
  // the sign-in card that meant tapping the "Sign In" TITLE and silently not
  // submitting. Prefer the real marker; fall back only if nothing carries it.
  const strict = [], loose = [];
  for (const e of document.querySelectorAll('*')) {
    if ((e.textContent||'').trim() !== txt || e.children.length !== 0) continue;
    let p = e, hit = null;
    for (let i = 0; i < 8 && p; i++) {
      if (/r-1loqt21/.test((p.className||'').toString()) || p.tagName === 'BUTTON') { hit = p; break; }
      p = p.parentElement;
    }
    if (hit) { if (!strict.includes(hit)) strict.push(hit); continue; }
    let q = e;
    for (let i = 0; i < 8 && q; i++) {
      if (getComputedStyle(q).cursor === 'pointer') { if (!loose.includes(q)) loose.push(q); break; }
      q = q.parentElement;
    }
  }
  return strict.length ? strict : loose;
};
window.__tap = (txt, nth) => {
  const p = window.__pressables(txt)[nth||0];
  if (!p) return false;
  window.__tapEl(p);
  return true;
};
// Address fields by what they ARE, never by index. The create-deck wizard has
// a file input for "Upload Project Files" sitting before the goal box, and
// setting .value on a file input throws outright -- indexing found it first.
window.__setField = (kind, value) => {
  const els = [...document.querySelectorAll('input,textarea')]
    .filter(e => e.type !== 'file' && !e.disabled && e.offsetParent !== null);
  const byPh = (re) => els.find(e => re.test(e.placeholder || ''));
  let el = null;
  if (kind === 'email')    el = els.find(e => e.type === 'email') || byPh(/mail/i);
  if (kind === 'password') el = els.find(e => e.type === 'password') || byPh(/pass/i);
  if (kind === 'goal')     el = byPh(/create a presentation|goal|describe/i)
                             || els.find(e => e.tagName === 'TEXTAREA');
  if (!el) return false;
  const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement : window.HTMLInputElement;
  el.focus();
  Object.getOwnPropertyDescriptor(proto.prototype, 'value').set.call(el, value);
  el.dispatchEvent(new Event('input', {bubbles:true}));
  el.dispatchEvent(new Event('change', {bubbles:true}));
  return true;
};
"""


def shot(page, name: str, note: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"{name}.png"))
    print(f"  captured {name:<24} {note}")


def tap(page, label: str, nth: int = 0, timeout: int = 30000) -> bool:
    """Tap once the control exists. A fixed sleep before a tap is a guess."""
    try:
        page.wait_for_function(
            "([t,n]) => window.__pressables && window.__pressables(t).length > n",
            arg=[label, nth], timeout=timeout)
    except Exception:
        return False
    return bool(page.evaluate("([t,n]) => window.__tap(t,n)", [label, nth]))



def real_click(page, label: str) -> bool:
    """Click a control's centre with a REAL mouse event.

    The synthetic dispatch above is enough for RNW Pressables, but the deck
    cards are plain views whose ancestors all report cursor:auto -- there is no
    Pressable to aim at, and dispatching to the nearest one hits something that
    ignores it. A trusted click at the coordinates works regardless of how the
    handler is attached.
    """
    box = page.evaluate("""(txt) => {
      const leaf = [...document.querySelectorAll('*')]
        .find(e => (e.textContent||'').trim() === txt && e.children.length === 0);
      if (!leaf) return null;
      const r = leaf.getBoundingClientRect();
      return r.width && r.height ? {x: r.x + r.width/2, y: r.y + r.height/2} : null;
    }""", label)
    if not box:
        return False
    page.mouse.click(box["x"], box["y"])
    return True

def main() -> int:
    if not (EMAIL and PW):
        print("  DECK_EMAIL / DECK_PW not set", file=sys.stderr)
        return 1

    with sync_playwright() as pw:
        # HEADED=1 opens a real window -- useful when someone wants to watch
        # the run rather than read about it afterwards.
        br = pw.chromium.launch(headless=os.getenv('HEADED') != '1',
                                slow_mo=400 if os.getenv('HEADED') == '1' else 0)
        page = br.new_page(viewport={"width": 1440, "height": 900},
                           device_scale_factor=2)
        page.add_init_script(HELPERS)

        # 1 ── what it is
        page.goto(UI, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        shot(page, "00-landing", "three things it makes")

        # 2 ── sign in
        if not tap(page, "Sign in to start"):
            print("  [!!] no sign-in control", file=sys.stderr); br.close(); return 1
        page.wait_for_timeout(2500)
        page.evaluate("([e,p]) => { window.__setField('email',e); window.__setField('password',p); }",
                      [EMAIL, PW])
        page.wait_for_timeout(400)
        shot(page, "01-signin", "local accounts, no external auth service")
        if not tap(page, "Sign In"):
            print("  [!!] sign-in did not submit", file=sys.stderr); br.close(); return 1
        page.wait_for_timeout(6000)
        shot(page, "02-decks", "your decks")

        # 3 ── describe the deck
        # The card exposes several tappable labels and which one carries the
        # handler is not obvious from the DOM, so try them and CHECK the wizard
        # actually opened rather than trusting the tap's return value.
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
                print(f"  create-deck wizard opened via {label!r}")
                break
            except Exception:
                continue
        if not opened:
            print("  [!!] the create-deck wizard never opened", file=sys.stderr)
            shot(page, "03-goal", "INCOMPLETE - check before use")
            br.close(); return 1
        if not page.evaluate("(g) => window.__setField('goal', g)", GOAL):
            print("  [!!] goal field not found", file=sys.stderr); br.close(); return 1
        page.wait_for_timeout(600)
        shot(page, "03-goal", "the deck described in plain English")

        # 4 ── outline
        if not tap(page, "Generate Slide Outline"):
            print("  [!!] outline step not reached", file=sys.stderr); br.close(); return 1
        print("  writing the outline...")
        try:
            page.wait_for_function(
                "() => /Slide Outline/.test(document.body.innerText)"
                " && !/Analyzing|being generated/.test(document.body.innerText)",
                timeout=240000)
        except Exception:
            print("  [!!] outline did not finish in 4 min", file=sys.stderr)
        page.wait_for_timeout(2500)
        shot(page, "04-outline", "the outline it proposes, before any slide is built")

        # The remaining steps vary with what the model returns, so each is
        # attempted and reported rather than assumed.
        # Labels taken from PresentationGoalInput.js, not guessed: the step
        # forward from the outline is "Choose Template", not "Next".
        for label, name, note in (
            ("Choose Template", "05-template", "pick a look"),
            ("Generate Presentation", "06-generating", "slides being written"),
        ):
            # Generous timeouts: each step waits on a real model call. 20s was
            # shorter than the outline takes to come back, so the control was
            # simply not rendered yet and the step reported itself missing.
            if tap(page, label, timeout=240000):
                page.wait_for_timeout(6000)
                shot(page, name, note)
            else:
                print(f"  [--] step {name}: no '{label}' control after 4 min")

        # 5 ── the composer, once slides exist
        print("  waiting for slides (up to 12 min)...")
        # Wait for the DECK, not for the composer. The composer opens
        # immediately with one blank Title Slide while slides stream in behind
        # it, so "Slide 1 of ..." is on screen within seconds -- the previous
        # condition matched that and photographed an empty deck. The sidebar's
        # n/total counter is the honest signal.
        try:
            page.wait_for_function(
                r"""() => {
                  const m = document.body.innerText.match(/(\d+)\s*\/\s*(\d+)/);
                  return m && Number(m[2]) > 1 && Number(m[1]) >= Number(m[2]);
                }""",
                timeout=720000)
        except Exception:
            print("  [!!] slides did not all arrive in time -- capturing anyway",
                  file=sys.stderr)
        page.wait_for_timeout(6000)
        shot(page, "07-composer", "the deck, editable, with the AI panel alongside")

        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
