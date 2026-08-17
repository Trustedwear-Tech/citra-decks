// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

/**
 * DeckChromeOverlay — renders deck-level header / footer / slide-number "chrome"
 * as a non-interactive overlay positioned over a slide/page canvas.
 *
 * These settings are deck-level (not per-element) and are agentic-editable via
 * chat (update_header_footer / update_slide_numbers operations) as well as the
 * manual DeckChromeModal. Rendering as an overlay (pointerEvents="none") keeps
 * the underlying Fabric canvas fully interactive and avoids polluting the slide
 * element list.
 *
 * Shared by PresentationComposer (16:9) and PrintableComposer (A4).
 */

import React from 'react';
import { View, Text } from 'react-native';

const formatSlideNumber = (cfg, index, total, noun) => {
  const start = Number.isFinite(cfg.start_at) ? cfg.start_at : 1;
  const n = index + start;
  const prefix = cfg.prefix || '';
  switch (cfg.format) {
    case 'n':
      return `${prefix}${n}`;
    case 'slide_n':
    case 'page_n':
      return `${prefix}${noun} ${n}`;
    case 'n_of_total':
    default:
      return `${prefix}${n} / ${total - 1 + start}`;
  }
};

const positionStyle = (position) => {
  // position like "bottom-right" | "bottom-center" | "bottom-left"
  const [vert, horiz] = (position || 'bottom-right').split('-');
  const style = { position: 'absolute' };
  if (vert === 'top') style.top = 8; else style.bottom = 8;
  if (horiz === 'left') { style.left = 12; }
  else if (horiz === 'center') { style.left = 0; style.right = 0; }
  else { style.right = 12; }
  return { style, align: horiz === 'center' ? 'center' : (horiz === 'left' ? 'left' : 'right') };
};

const DeckChromeOverlay = ({
  width,            // displayed canvas width (px)
  height,           // displayed canvas height (px)
  headerFooter,     // { show_header, header_text, show_footer, footer_text, align, color, font_size, show_logo }
  slideNumbers,     // { show, format, position, prefix, color, font_size, start_at }
  index = 0,        // zero-based slide/page index
  total = 1,        // total slides/pages
  noun = 'Slide',   // 'Slide' | 'Page'
}) => {
  const hf = headerFooter || {};
  const sn = slideNumbers || {};
  if (!hf.show_header && !hf.show_footer && !sn.show) return null;

  const hfColor = hf.color || '#64748b';
  const hfSize = hf.font_size || 12;
  const hfAlign = hf.align || 'center';
  const textAlignToFlex = hfAlign === 'left' ? 'flex-start' : hfAlign === 'right' ? 'flex-end' : 'center';

  const snInfo = positionStyle(sn.position);

  return (
    <View
      pointerEvents="none"
      style={{ position: 'absolute', top: 0, left: 0, width, height, overflow: 'hidden' }}
    >
      {hf.show_header && !!hf.header_text && (
        <View style={{ position: 'absolute', top: 6, left: 16, right: 16, alignItems: textAlignToFlex }}>
          <Text numberOfLines={1} style={{ color: hfColor, fontSize: hfSize, fontWeight: '500' }}>
            {hf.header_text}
          </Text>
        </View>
      )}

      {hf.show_footer && !!hf.footer_text && (
        <View style={{ position: 'absolute', bottom: 6, left: 16, right: 16, alignItems: textAlignToFlex }}>
          <Text numberOfLines={1} style={{ color: hfColor, fontSize: hfSize }}>
            {hf.footer_text}
          </Text>
        </View>
      )}

      {sn.show && (
        <View style={snInfo.style}>
          <Text style={{ color: sn.color || '#94a3b8', fontSize: sn.font_size || 12, textAlign: snInfo.align }}>
            {formatSlideNumber(sn, index, total, noun)}
          </Text>
        </View>
      )}
    </View>
  );
};

export default React.memo(DeckChromeOverlay);
