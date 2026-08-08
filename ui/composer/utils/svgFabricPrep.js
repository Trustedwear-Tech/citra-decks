/**
 * svgFabricPrep — preprocess SVG strings before handing them to fabric.js.
 *
 * fabric.js's SVG parser does NOT evaluate CSS class selectors inside <style>
 * blocks. Diagrams emitted by older prompts (or by an LLM that ignores rules)
 * may use `<style>.node{fill:#fff}</style>` + `class="node"`, which results in
 * fabric returning zero objects or unstyled shapes (e.g. invisible lines).
 *
 * This util:
 *   1. Strips HTML comments (<!-- ... -->) which can confuse the parser.
 *   2. Parses rules from inline <style> blocks for the selectors we support
 *      and inlines them onto matching elements as a `style="..."` attribute.
 *      Existing inline `style=""` declarations win on conflict.
 *   3. Removes the now-empty <style> blocks and dangling `class=""` attrs.
 *
 * Supported selectors (covers ~all LLM-emitted SVG):
 *   - `tag` (e.g. `line`, `text`, `rect`)
 *   - `.cls`
 *   - `tag.cls`
 *   - Comma-separated lists of any of the above (`.a, .b, line { ... }`).
 *
 * NOT supported (silently dropped — extremely rare in LLM output):
 *   - Descendant / child / sibling combinators (`.a .b`, `.a > b`)
 *   - Pseudo-classes / pseudo-elements (`:hover`, `::before`)
 *   - Attribute selectors (`[fill="red"]`)
 *   - `@media`, `@font-face`, `@keyframes`
 *
 * Pure string-level transform — safe to run before `fabric.loadSVGFromString`.
 */

/**
 * Parse all <style> bodies into two maps:
 *   - byTag:        Map<tagName, declarations>
 *   - byClass:      Map<className, declarations>
 *   - byTagClass:   Map<`${tag}.${class}`, declarations>
 * Selectors we don't recognize are skipped.
 */
function parseStyleRules(cssText) {
  const byTag = new Map();
  const byClass = new Map();
  const byTagClass = new Map();
  if (!cssText) return { byTag, byClass, byTagClass };

  // Strip CSS comments first.
  const clean = cssText.replace(/\/\*[\s\S]*?\*\//g, '');

  // Match `selectorList { body }`. We grab everything up to `{` as the
  // selector list, then the body. Skip @-rules entirely.
  const blockRe = /([^{}@]+)\{([^}]*)\}/g;
  let m;
  while ((m = blockRe.exec(clean)) !== null) {
    const selectorList = m[1].trim();
    const decl = m[2].trim().replace(/\s+/g, ' ');
    if (!selectorList || !decl) continue;
    const normalized = decl.endsWith(';') ? decl : decl + ';';

    const selectors = selectorList.split(',').map((s) => s.trim()).filter(Boolean);
    for (const sel of selectors) {
      // tag.class
      let mm = sel.match(/^([A-Za-z][\w:-]*)\.([A-Za-z_][\w-]*)$/);
      if (mm) {
        const key = `${mm[1].toLowerCase()}.${mm[2]}`;
        byTagClass.set(key, (byTagClass.get(key) || '') + ' ' + normalized);
        continue;
      }
      // .class
      mm = sel.match(/^\.([A-Za-z_][\w-]*)$/);
      if (mm) {
        byClass.set(mm[1], (byClass.get(mm[1]) || '') + ' ' + normalized);
        continue;
      }
      // tag (must not contain combinators / pseudo / attr selectors)
      mm = sel.match(/^([A-Za-z][\w:-]*)$/);
      if (mm) {
        const tag = mm[1].toLowerCase();
        byTag.set(tag, (byTag.get(tag) || '') + ' ' + normalized);
        continue;
      }
      // Unsupported selector — skip.
    }
  }
  return { byTag, byClass, byTagClass };
}

/**
 * Inline collected rules onto every renderable element. Precedence (low→high):
 *   1. tag rules
 *   2. .class rules
 *   3. tag.class rules
 *   4. existing inline style=""
 *   5. existing presentation attributes (fill="...", stroke="...", etc.)
 *
 * We achieve 1-4 by prepending in order to the existing style attr; CSS
 * cascade then resolves the rest. Inline presentation attrs (5) always win
 * over `style` in SVG, so we leave those untouched.
 */
function inlineRules(svg, rules) {
  const { byTag, byClass, byTagClass } = rules;
  if (!byTag.size && !byClass.size && !byTagClass.size) return svg;

  // Match opening tags (self-closing or not) of any element.
  const tagRe = /<([A-Za-z][\w:-]*)\b([^>]*?)(\/?)>/g;
  return svg.replace(tagRe, (full, tag, attrsRaw, selfClose) => {
    const lowerTag = tag.toLowerCase();
    // Skip non-renderable / structural tags where injecting style is pointless.
    if (lowerTag === 'svg' || lowerTag === 'defs' || lowerTag === 'style'
        || lowerTag === 'metadata' || lowerTag === 'title' || lowerTag === 'desc') {
      return full;
    }

    let attrs = attrsRaw;

    // Read class="..." (do not strip yet; we'll drop it once styles inlined).
    const classMatch = attrs.match(/\sclass="([^"]*)"/);
    const classes = classMatch
      ? classMatch[1].trim().split(/\s+/).filter(Boolean)
      : [];

    // Build the cascade string in order: tag → .class → tag.class.
    let cascade = '';
    if (byTag.has(lowerTag)) cascade += byTag.get(lowerTag);
    for (const c of classes) {
      if (byClass.has(c)) cascade += ' ' + byClass.get(c);
    }
    for (const c of classes) {
      const key = `${lowerTag}.${c}`;
      if (byTagClass.has(key)) cascade += ' ' + byTagClass.get(key);
    }
    cascade = cascade.trim();

    // Strip the class attr now (fabric ignores it; clean output).
    if (classMatch) {
      attrs = attrs.replace(/\sclass="[^"]*"/, '');
    }

    if (!cascade) return `<${tag}${attrs}${selfClose}>`;

    // Merge cascade with any existing style attr. Cascade has lower precedence
    // than existing inline style.
    const styleMatch = attrs.match(/\sstyle="([^"]*)"/);
    if (styleMatch) {
      const existing = styleMatch[1].trim();
      const merged = (cascade + (cascade.endsWith(';') ? ' ' : '; ') + existing).trim();
      attrs = attrs.replace(/\sstyle="[^"]*"/, ` style="${merged}"`);
    } else {
      attrs = attrs + ` style="${cascade}"`;
    }
    return `<${tag}${attrs}${selfClose}>`;
  });
}

/**
 * Ensure the root <svg> tag has explicit width/height attributes. When an SVG
 * is loaded via `<img src="data:image/svg+xml,...">` (our primary render path
 * in PresentationCanvas), browsers need intrinsic dimensions — a viewBox alone
 * is not always enough. Chrome may fall back to a 0×0 natural size and the
 * resulting fabric.Image renders invisibly with no error. Pull width/height
 * from the viewBox when missing.
 */
function ensureSvgIntrinsicDims(svg) {
  const tagMatch = svg.match(/<svg\b([^>]*)>/i);
  if (!tagMatch) return svg;
  const attrs = tagMatch[1];
  const hasWidth = /\swidth\s*=\s*["'][^"']+["']/i.test(attrs);
  const hasHeight = /\sheight\s*=\s*["'][^"']+["']/i.test(attrs);
  if (hasWidth && hasHeight) return svg;

  const vbMatch = attrs.match(/\sviewBox\s*=\s*["']\s*[-\d.]+\s+[-\d.]+\s+([-\d.]+)\s+([-\d.]+)\s*["']/i);
  if (!vbMatch) return svg;
  const vbW = parseFloat(vbMatch[1]);
  const vbH = parseFloat(vbMatch[2]);
  if (!isFinite(vbW) || !isFinite(vbH) || vbW <= 0 || vbH <= 0) return svg;

  let newAttrs = attrs;
  if (!hasWidth) newAttrs = ` width="${vbW}"` + newAttrs;
  if (!hasHeight) newAttrs = ` height="${vbH}"` + newAttrs;
  return svg.replace(tagMatch[0], `<svg${newAttrs}>`);
}

/**
 * Main entry. Returns a cleaned SVG string ready for fabric.loadSVGFromString.
 */
export function preprocessSvgForFabric(svg) {
  if (!svg || typeof svg !== 'string') return svg;
  let out = svg;

  // 1. Strip HTML comments (safe — they have no rendering meaning).
  out = out.replace(/<!--[\s\S]*?-->/g, '');

  // 1a. Ensure intrinsic width/height on the root <svg>. Without these, the
  // browser may render the SVG at 0×0 when loaded as an <img>, producing a
  // silently empty fabric.Image with no error/log to diagnose.
  out = ensureSvgIntrinsicDims(out);

  // 1b. Escape bare ampersands. SVG is XML, so `&` MUST be `&amp;` (or part of
  // a valid entity / numeric reference). LLMs frequently emit text like
  // "Mass Loss & Transition" which makes the entire SVG fail to load when
  // rendered via `<img src="data:image/svg+xml,...">` (the browser's strict
  // XML parser rejects it). Convert `&` to `&amp;` unless it already starts
  // a recognized entity reference.
  out = out.replace(
    /&(?!(?:[A-Za-z][A-Za-z0-9]{1,30}|#\d{1,7}|#x[0-9A-Fa-f]{1,6});)/g,
    '&amp;'
  );

  // 2. Collect rules from every <style> block, then drop the blocks.
  const all = { byTag: new Map(), byClass: new Map(), byTagClass: new Map() };
  out = out.replace(/<style\b[^>]*>([\s\S]*?)<\/style>/gi, (_, body) => {
    const r = parseStyleRules(body);
    for (const [k, v] of r.byTag)      all.byTag.set(k,      (all.byTag.get(k)      || '') + ' ' + v);
    for (const [k, v] of r.byClass)    all.byClass.set(k,    (all.byClass.get(k)    || '') + ' ' + v);
    for (const [k, v] of r.byTagClass) all.byTagClass.set(k, (all.byTagClass.get(k) || '') + ' ' + v);
    return ''; // remove the style block from the SVG
  });

  // 3. Inline rules onto matching elements.
  if (all.byTag.size || all.byClass.size || all.byTagClass.size) {
    out = inlineRules(out, all);
  } else {
    // No rules collected — still drop class="..." since fabric ignores it.
    out = out.replace(/\sclass="[^"]*"/g, '');
  }

  return out;
}

export default preprocessSvgForFabric;
