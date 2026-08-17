// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

/**
 * svgRasterize — rasterize an `svg_diagram` element's inline SVG to a PNG data URL.
 *
 * The live editor canvas (PresentationCanvas / PrintableCanvas) renders
 * `svg_diagram` elements natively via fabric.Image. The export pipeline,
 * however, builds plain DOM / pptxgenjs / Word-HTML output — none of which
 * can render a raw SVG element reliably across PPTX, PDF, PNG and Word.
 *
 * Rasterizing to PNG up front gives a single representation that every
 * exporter can embed. We reuse `preprocessSvgForFabric` + `currentColor`
 * substitution so the exported diagram matches what the editor shows.
 */
import { preprocessSvgForFabric } from './svgFabricPrep';

/**
 * Rasterize an SVG string to a PNG data URL at the given target size.
 *
 * @param {string} svgContent - raw SVG markup (element.svgContent)
 * @param {string} fillColor  - accent color used to resolve `currentColor`
 * @param {number} width      - target width in px (element slot width)
 * @param {number} height     - target height in px (element slot height)
 * @param {number} scale      - resolution multiplier (default 2x for crisp text)
 * @returns {Promise<string|null>} PNG data URL, or null on failure
 */
export async function rasterizeSvgToPng(
  svgContent,
  fillColor = '#3B82F6',
  width = 600,
  height = 400,
  scale = 2,
) {
  if (!svgContent || typeof svgContent !== 'string') return null;

  // Match the editor canvas: inline <style> rules + resolve currentColor so
  // themed accent colors apply, and ensure intrinsic width/height on <svg>.
  const themed = preprocessSvgForFabric(svgContent).replace(/currentColor/g, fillColor || '#3B82F6');

  const encoded = encodeURIComponent(themed)
    .replace(/'/g, '%27')
    .replace(/"/g, '%22');
  const dataUrl = `data:image/svg+xml;charset=utf-8,${encoded}`;

  const img = new Image();
  img.crossOrigin = 'anonymous';
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error('svg_diagram failed to load as image'));
    img.src = dataUrl;
  });

  const pxW = Math.max(1, Math.round((width || img.width || 600) * scale));
  const pxH = Math.max(1, Math.round((height || img.height || 400) * scale));

  const canvas = document.createElement('canvas');
  canvas.width = pxW;
  canvas.height = pxH;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0, pxW, pxH);

  // A self-contained SVG data URL does not taint the canvas, so toDataURL works.
  return canvas.toDataURL('image/png');
}

/**
 * Pre-rasterize every `svg_diagram` element across a set of slides/pages.
 *
 * Returns a Map<elementId, pngDataUrl> so the synchronous element builders
 * (createElementDiv / createElementHtml) can look up the rendered PNG.
 *
 * @param {Array} slidesOrPages - slides[] (presentation) or PAGES[] (printable)
 * @returns {Promise<Map<string,string>>}
 */
export async function prerasterizeSvgDiagrams(slidesOrPages) {
  const map = new Map();
  const els = (slidesOrPages || []).flatMap((s) =>
    (s.elements || []).filter((e) => e.type === 'svg_diagram' && e.svgContent),
  );
  await Promise.all(
    els.map(async (e) => {
      try {
        const png = await rasterizeSvgToPng(
          e.svgContent,
          e.fillColor || e.fill || e.color,
          e.width,
          e.height,
        );
        if (png) map.set(e.id, png);
      } catch (err) {
        console.warn('[Export] Failed to rasterize svg_diagram, skipping:', e.id, err);
      }
    }),
  );
  return map;
}

export default rasterizeSvgToPng;
