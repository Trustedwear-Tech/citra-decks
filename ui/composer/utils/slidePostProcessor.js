// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

/**
 * Slide Post-Processor
 * 
 * Transforms AI-generated slide data into renderable elements for Fabric.js.
 * Handles:
 * - Cards: Expands into shape + icon + text elements
 * - Icons: Maps semantic names to SVG paths
 * - Numbered Steps: Creates circle + number + label
 * - Validation: Ensures positions and sizes are within canvas bounds
 */

import { mapIconToPath, mapIconToPathAsync, prefetchIcons, getIconSVG } from './iconMapper';

// Monotonic counter for generating unique element IDs (avoids Date.now() collisions)
let _elementIdCounter = 0;
function uniqueId(prefix = 'auto') {
    return `${prefix}_${Date.now()}_${_elementIdCounter++}`;
}

const CANVAS_WIDTH = 960;
const CANVAS_HEIGHT = 540;



// ==================== Z-Index Defaults ====================
const Z_INDEX_DEFAULTS = {
    shape: 5,           // Background shapes
    group: 10,          // Groups (containers)
    card: 15,           // Card backgrounds  
    image: 20,          // Images
    image_placeholder: 20,
    video: 25,          // Videos
    chart: 30,          // Charts
    icon: 35,           // Icons
    numbered_step: 40,  // Step indicators
    text: 50,           // Text (Always on top)
};

/**
 * Assign z-index to element based on type (fallback if AI didn't specify)
 */
function assignZIndex(element) {
    if (element.zIndex !== undefined) return element.zIndex;
    return Z_INDEX_DEFAULTS[element.type] ?? 50;
}

// ==================== Color Contrast ====================
/**
 * Parse any CSS color format (hex, rgb, rgba) into {r, g, b} or null.
 */
function parseColorRGB(color) {
    if (!color || typeof color !== 'string') return null;

    // Match rgba(r, g, b, a) or rgb(r, g, b)
    const rgbaMatch = color.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
    if (rgbaMatch) {
        return { r: parseInt(rgbaMatch[1], 10), g: parseInt(rgbaMatch[2], 10), b: parseInt(rgbaMatch[3], 10) };
    }

    // Hex format
    const hex = color.replace('#', '');
    if (hex.length >= 6) {
        const r = parseInt(hex.substr(0, 2), 16);
        const g = parseInt(hex.substr(2, 2), 16);
        const b = parseInt(hex.substr(4, 2), 16);
        if (!isNaN(r) && !isNaN(g) && !isNaN(b)) return { r, g, b };
    }
    // 3-char hex shorthand (#abc → #aabbcc)
    if (hex.length === 3) {
        const r = parseInt(hex[0] + hex[0], 16);
        const g = parseInt(hex[1] + hex[1], 16);
        const b = parseInt(hex[2] + hex[2], 16);
        if (!isNaN(r) && !isNaN(g) && !isNaN(b)) return { r, g, b };
    }

    return null;
}

/**
 * Check if a color is dark (for contrast calculation)
 */
function isColorDark(color) {
    const rgb = parseColorRGB(color);
    if (!rgb) return false;

    const luminance = (0.299 * rgb.r + 0.587 * rgb.g + 0.114 * rgb.b) / 255;
    return luminance < 0.5;
}

/**
 * Check if two colors are nearly identical (invisible text detection).
 * Uses RGB euclidean distance with a tight threshold.
 * NOT the old broad "both dark / both light" logic — only catches truly identical colors.
 */
function areColorsSimilar(color1, color2, threshold = 35) {
    const c1 = parseColorRGB(color1);
    const c2 = parseColorRGB(color2);
    if (!c1 || !c2) return false;
    const distance = Math.sqrt((c1.r - c2.r) ** 2 + (c1.g - c2.g) ** 2 + (c1.b - c2.b) ** 2);
    return distance < threshold;
}

/**
 * Check if text color has low contrast against a background color.
 * Catches BOTH "nearly identical" colors AND "both dark / both light" combos
 * that areColorsSimilar() misses (e.g., dark navy text on dark gray background).
 */
function hasLowContrast(textColor, bgColor) {
    const tc = parseColorRGB(textColor);
    const bc = parseColorRGB(bgColor);
    if (!tc || !bc) return false;

    // Check 1: RGB distance — catches nearly identical colors
    const distance = Math.sqrt((tc.r - bc.r) ** 2 + (tc.g - bc.g) ** 2 + (tc.b - bc.b) ** 2);
    if (distance < 60) return true;

    // Check 2: Both on same luminance side with small gap — catches "both dark" or "both light"
    const textLum = (0.299 * tc.r + 0.587 * tc.g + 0.114 * tc.b) / 255;
    const bgLum = (0.299 * bc.r + 0.587 * bc.g + 0.114 * bc.b) / 255;
    const bothDark = textLum < 0.4 && bgLum < 0.4;
    const bothLight = textLum > 0.6 && bgLum > 0.6;
    if ((bothDark || bothLight) && Math.abs(textLum - bgLum) < 0.15) return true;

    return false;
}

/**
 * Ensure text has good contrast with background
 */
function ensureColorContrast(element, backgroundColor) {
    if (element.type !== 'text' && element.textType === undefined) {
        return element;
    }

    const bgIsDark = isColorDark(backgroundColor);

    // If no fill color set, pick a high-contrast default based on background
    if (!element.fill) {
        element.fill = bgIsDark ? '#FFFFFF' : '#000000';
        console.log(`[ColorContrast] No fill set, using contrast default: ${element.fill}`);
        return element;
    }

    const textIsDark = isColorDark(element.fill);

    // If both are dark or both are light, fix the text color
    if (bgIsDark && textIsDark) {
        console.log(`[ColorContrast] Fixing dark text on dark bg: ${element.fill} -> #FFFFFF`);
        element.fill = '#FFFFFF';
    } else if (!bgIsDark && !textIsDark) {
        console.log(`[ColorContrast] Fixing light text on light bg: ${element.fill} -> #111827`);
        element.fill = '#111827';
    }

    return element;
}

/**
 * Recursive function to flatten hierarchical elements (Parent -> Children)
 * Converts relative coordinates (child.x) to absolute coordinates (parent.x + child.x)
 * Propagates parent dimensions to restrain children
 */
function flattenHierarchy(elements, parentX = 0, parentY = 0, parentZ = 0, parentId = null, parentWidth = null, parentHeight = null, parentBgColor = null) {
    let result = [];
    if (!elements || !Array.isArray(elements)) return result;

    elements.forEach((el, index) => {
        // Calculate absolute position
        // If element has no x/y, default to 0 (relative to parent)
        const absX = (el.x || 0) + parentX;
        const absY = (el.y || 0) + parentY;

        // Ensure ID exists (Critical for Sync/Diffing)
        // If missing, generate deterministic ID based on parent
        let elementId = el.id;
        if (!elementId) {
            elementId = parentId ? `${parentId}_child_${index}` : uniqueId('auto');
            console.warn(`[SlideProcessor] ⚠️ Missing ID for element type '${el.type}', generated: ${elementId}`);
        }

        // Z-Index Logic (Critical for Visibility)
        // FIX: Default to 50 (Text level) if unknown, rather than 0
        // This ensures text inside cards (which lacks explicit zIndex) sits ABOVE shapes (zIndex 5)
        const intrinsicZ = el.zIndex !== undefined ? el.zIndex : (Z_INDEX_DEFAULTS[el.type] ?? 50);
        const absZ = intrinsicZ + parentZ;

        // Dimension Inheritance Logic (New Feature)
        // If element lacks explicit width/height, and belongs to a sized container, inherit constraints.
        // This prevents children from exploding to full screen width (1024px) when inside a Column (e.g. 400px).
        let effectiveWidth = el.width;
        let effectiveHeight = el.height;

        if (parentWidth && (effectiveWidth === undefined || effectiveWidth === null)) {
            // Child width = Parent Width - Child's Relative X (padding logic)
            // Ensure strictly positive
            const calculatedWidth = Math.max(10, parentWidth - (el.x || 0));
            effectiveWidth = calculatedWidth;
            console.log(`[SlideProcessor] 📏 Inheriting width for ${elementId}: Parent=${parentWidth}, AbsX=${absX} -> NewWidth=${effectiveWidth}`);
        }

        // Create flattened clone with resolved dimensions
        const flatEl = {
            ...el,
            id: elementId,
            x: absX,
            y: absY,
            width: effectiveWidth, // Patched width
            zIndex: absZ,
            // Inherit parentId if not set, or chain them? 
            // For now, if we are inside a hierarchy, the immediate parent is the parentId
            parentId: parentId || el.parentId,
            // CRITICAL: Normalize AI's 'text' property -> 'content' for canvas renderer
            // AI sends {text: "..."} but Fabric.js canvas expects {content: "..."}
            // Without this, canvas falls back to 'Click to edit' placeholder
            ...(el.type === 'text' && !el.content && el.text ? { content: el.text } : {}),
        };

        // Determine this element's background color (for child propagation)
        // IMPORTANT: "transparent" and "none" are not real background colors —
        // children inside transparent shapes should inherit the PARENT's bg, not "transparent"
        const rawFill = (el.type === 'shape' || el.type === 'card') ? el.fill : null;
        const validFill = rawFill && rawFill !== 'transparent' && rawFill !== 'none' ? rawFill : null;
        const elementBgColor = el.backgroundColor || validFill;

        // Parent-aware text visibility fix (during flattening)
        // Only fixes truly invisible text — NOT the old broad ensureColorContrast logic
        // Case 1: Text with NO fill at all -> derive readable default from parent background
        // Case 2: Text fill nearly identical to parent bg -> flip to contrasting color
        if (parentBgColor && (flatEl.type === 'text' || flatEl.textType)) {
            const textFill = flatEl.fill || flatEl.color;
            if (!textFill) {
                flatEl.fill = isColorDark(parentBgColor) ? '#FFFFFF' : '#111827';
                console.log(`[SlideProcessor] \u{1F3A8} No fill on text ${elementId}, parent bg=${parentBgColor} -> ${flatEl.fill}`);
            } else if (hasLowContrast(textFill, parentBgColor)) {
                flatEl.fill = isColorDark(parentBgColor) ? '#FFFFFF' : '#111827';
                console.log(`[SlideProcessor] \u{1F3A8} Low-contrast text fix ${elementId}: ${textFill} vs ${parentBgColor} -> ${flatEl.fill}`);
            }
        }

        // Remove children from the flat copy to avoid duplication/recursion issues in renderer
        delete flatEl.children;

        result.push(flatEl);

        // Process children recursively
        if (el.children && Array.isArray(el.children) && el.children.length > 0) {
            // Pass THIS element's effective width as the NEW parent width
            // Propagate bg color: use this element's bg if it has one, otherwise inherit parent's
            const childBgColor = elementBgColor || parentBgColor;
            result.push(...flattenHierarchy(el.children, absX, absY, absZ, elementId, effectiveWidth, effectiveHeight, childBgColor));
        }
    });

    return result;
}

/**
 * Pre-extract children content onto card/numbered_step elements BEFORE flattening.
 * 
 * Problem: flattenHierarchy() strips `children` from elements (delete flatEl.children),
 * then STEP 0.5 drops the flattened children of expandable parents.
 * This means expandCard() receives a card with no title/description/iconName — only a _bg rect renders.
 * 
 * Solution: Walk the raw element tree BEFORE flattening. For each card/numbered_step that has
 * children but is missing title/description, extract content from children:
 *   - First bold text child → card.title
 *   - Remaining text children → card.description (joined with newlines)
 *   - First icon child → card.iconName
 */

/**
 * Rescue orphaned icon/text elements near empty cards.
 * 
 * Problem: The LLM sometimes generates a card element without title/description/iconName
 * and puts the actual content as separate sibling elements nearby. expandCard() then
 * creates only an empty background rectangle, while the icon/text float freely.
 * 
 * Solution: Before any other processing, scan for empty cards and adopt nearby
 * standalone icon/text elements that spatially overlap the card's bounds.
 */
function rescueOrphanedCardContent(elements) {
    if (!elements || !Array.isArray(elements)) return elements;

    // Find cards that are empty: no title, description, iconName, and no useful children
    const emptyCards = elements.filter(el => {
        if (el.type !== 'card') return false;
        if (el.title || el.description || el.iconName) return false;
        // If children contain text/icon, preExtractCardContent will handle it — not orphaned
        if (el.children && el.children.length > 0) {
            const hasContent = el.children.some(c => c.type === 'text' || c.type === 'icon');
            if (hasContent) return false;
        }
        return true;
    });

    if (emptyCards.length === 0) return elements;

    const adopted = new Set();

    for (const card of emptyCards) {
        const cardLeft = card.x || 0;
        const cardRight = cardLeft + (card.width || 280);
        const cardTop = card.y || 0;
        const cardBottom = cardTop + (card.height || 280);

        // Find standalone text elements that overlap with or are near the card bounds
        const nearbyTexts = elements.filter(el => {
            if (el.type !== 'text' || adopted.has(el)) return false;
            // Skip elements already inside another card/group
            if (el.parentId) return false;
            const elX = el.x || 0;
            const elY = el.y || 0;
            // Within card bounds + small margin (30px sides, 50px below for elements just outside)
            return elX >= cardLeft - 30 && elX <= cardRight + 30 &&
                   elY >= cardTop - 30 && elY <= cardBottom + 50;
        });

        // Find standalone icon elements near card bounds
        const nearbyIcons = elements.filter(el => {
            if (el.type !== 'icon' || adopted.has(el)) return false;
            if (el.parentId) return false;
            const elX = el.x || 0;
            const elY = el.y || 0;
            return elX >= cardLeft - 30 && elX <= cardRight + 30 &&
                   elY >= cardTop - 30 && elY <= cardBottom + 50;
        });

        if (nearbyTexts.length === 0 && nearbyIcons.length === 0) continue;

        // Adopt: first bold/large text as title, remaining as description
        if (nearbyTexts.length > 0) {
            nearbyTexts.sort((a, b) => (a.y || 0) - (b.y || 0));
            const titleEl = nearbyTexts.find(t =>
                t.fontWeight === 'bold' || (t.fontSize && t.fontSize >= 18)
            ) || nearbyTexts[0];

            card.title = titleEl.content || titleEl.text || '';
            if (titleEl.fill || titleEl.color) card.titleColor = titleEl.fill || titleEl.color;
            adopted.add(titleEl);

            const descTexts = nearbyTexts.filter(t => t !== titleEl);
            if (descTexts.length > 0) {
                card.description = descTexts.map(t => t.content || t.text || '').join('\n');
                if (descTexts[0].fill || descTexts[0].color) {
                    card.descriptionColor = descTexts[0].fill || descTexts[0].color;
                }
                descTexts.forEach(t => adopted.add(t));
            }
        }

        if (nearbyIcons.length > 0) {
            card.iconName = nearbyIcons[0].iconName;
            if (nearbyIcons[0].fill || nearbyIcons[0].color) {
                card.iconColor = nearbyIcons[0].fill || nearbyIcons[0].color;
            }
            adopted.add(nearbyIcons[0]);
        }

        console.log(`[SlideProcessor] 🔄 Rescued orphaned content for empty card ${card.id}: title="${card.title?.substring(0, 30)}", icon=${card.iconName}`);
    }

    // Remove adopted elements from the array
    if (adopted.size > 0) {
        return elements.filter(el => !adopted.has(el));
    }
    return elements;
}

function preExtractCardContent(elements) {
    if (!elements || !Array.isArray(elements)) return;

    for (const el of elements) {
        if ((el.type === 'card' || el.type === 'numbered_step') && el.children && Array.isArray(el.children) && el.children.length > 0) {
            const textChildren = el.children.filter(c => c.type === 'text');
            const iconChildren = el.children.filter(c => c.type === 'icon');

            // Extract title if missing — first bold/subtitle text child, or first text child
            if (!el.title && textChildren.length > 0) {
                const boldChild = textChildren.find(c =>
                    c.fontWeight === 'bold' || c.textType === 'subtitle' || c.textType === 'title'
                ) || textChildren[0];
                el.title = boldChild.content || boldChild.text || '';
                console.log(`[SlideProcessor] 📋 Pre-extracted title for ${el.id || el.type}: "${el.title.substring(0, 40)}..."`);

                // Also extract title color if missing — preserves AI-specified text color
                if (!el.titleColor) {
                    el.titleColor = boldChild.color || boldChild.fill;
                    if (el.titleColor) {
                        console.log(`[SlideProcessor] 🎨 Pre-extracted titleColor for ${el.id || el.type}: ${el.titleColor}`);
                    }
                }
            }

            // Extract description if missing — remaining text children (skip the one used as title)
            if (!el.description && textChildren.length > 0) {
                const titleContent = el.title || '';
                const descChildren = textChildren.filter(c => {
                    const content = c.content || c.text || '';
                    return content !== titleContent;
                });
                if (descChildren.length > 0) {
                    el.description = descChildren.map(c => c.content || c.text || '').join('\n');
                    console.log(`[SlideProcessor] 📋 Pre-extracted description for ${el.id || el.type}: "${el.description.substring(0, 40)}..."`);

                    // Also extract description color if missing
                    if (!el.descriptionColor) {
                        el.descriptionColor = descChildren[0].color || descChildren[0].fill;
                        if (el.descriptionColor) {
                            console.log(`[SlideProcessor] 🎨 Pre-extracted descriptionColor for ${el.id || el.type}: ${el.descriptionColor}`);
                        }
                    }
                }
            }

            // Extract icon if missing
            if (!el.iconName && iconChildren.length > 0) {
                el.iconName = iconChildren[0].iconName || iconChildren[0].name;
                console.log(`[SlideProcessor] 📋 Pre-extracted icon for ${el.id || el.type}: ${el.iconName}`);
            }

            // Extract icon color if missing — AI sends color on icon children (e.g., "color": "#C5A059")
            if (!el.iconColor && iconChildren.length > 0) {
                el.iconColor = iconChildren[0].color || iconChildren[0].fill;
                if (el.iconColor) {
                    console.log(`[SlideProcessor] 🎨 Pre-extracted iconColor for ${el.id || el.type}: ${el.iconColor}`);
                }
            }
        }

        // Recurse into children to handle nested structures
        if (el.children && Array.isArray(el.children)) {
            preExtractCardContent(el.children);
        }
    }
}

/**
 * Main processing function for slide data
 */
// Resolve the slide's EFFECTIVE background. Dark themes often ship
// backgroundColor undefined (or white) while a full-bleed dark rect at the
// back provides the real background — assuming '#FFFFFF' then makes the
// contrast passes flip perfectly-readable white text to near-black, i.e.
// invisible on the actually-dark slide ("text disappeared" bug). Prefer a
// non-white explicit backgroundColor; else the fill of a shape covering ~the
// whole canvas at the lowest z; else fall back to white as before.
function resolveEffectiveBackground(slideData) {
    const explicit = slideData.backgroundColor;
    if (explicit && typeof explicit === 'string' && explicit.toUpperCase() !== '#FFFFFF' && explicit.toLowerCase() !== 'white') {
        return explicit;
    }
    let best = null;
    for (const el of (slideData.elements || [])) {
        if (!el || typeof el !== 'object') continue;
        if (el.type !== 'shape' && el.type !== 'rect') continue;
        const fill = el.fill || el.backgroundColor;
        if (!fill || typeof fill !== 'string' || !fill.startsWith('#')) continue;
        const w = Number(el.width) || 0, h = Number(el.height) || 0;
        const x = Number(el.x) || 0, y = Number(el.y) || 0;
        if (w >= CANVAS_WIDTH * 0.9 && h >= CANVAS_HEIGHT * 0.9 && x <= CANVAS_WIDTH * 0.05 && y <= CANVAS_HEIGHT * 0.05) {
            const z = Number(el.zIndex) || 0;
            if (!best || z < best.z) best = { fill, z };
        }
    }
    if (best) return best.fill;
    return explicit || '#FFFFFF';
}

export function processSlide(slideData) {
    if (!slideData || !slideData.elements) {
        console.warn('[SlideProcessor] Invalid slide data');
        return slideData;
    }

    // STEP -2: Rescue orphaned content near empty cards
    // If LLM placed icon/text as standalone siblings instead of card properties or children,
    // detect and adopt them onto the empty card so expandCard() can render them properly.
    slideData.elements = rescueOrphanedCardContent(slideData.elements);

    // STEP -1: Pre-extract children content onto cards BEFORE flattening
    // This ensures card title/description/iconName survive the flatten + dedup pipeline
    preExtractCardContent(slideData.elements);

    // STEP 0: Flatten Hierarchy (with parent-aware text visibility fix)
    const backgroundColor = resolveEffectiveBackground(slideData);
    const flatElements = flattenHierarchy(slideData.elements, 0, 0, 0, null, null, null, backgroundColor);

    console.log(`[SlideProcessor] Hierarchy Flattened: ${slideData.elements.length} root -> ${flatElements.length} flat elements`);

    // STEP 0.5: Deduplicate — if AI sent card/numbered_step with BOTH top-level title/description
    // AND children text, flattenHierarchy extracted the children AND expandCard will create more.
    // Remove flattened children of cards/numbered_steps to let the expander handle layout.
    const expandableParentIds = new Set(
        flatElements
            .filter(el => el.type === 'card' || el.type === 'numbered_step')
            .map(el => el.id)
    );
    const elementsToProcess = flatElements.filter(el => {
        // Keep element if it's NOT a child of an expandable parent
        if (el.parentId && expandableParentIds.has(el.parentId)) {
            console.log(`[SlideProcessor] 🗑️ Dropping flattened child ${el.id} (parent ${el.parentId} will be expanded)`);
            return false;
        }
        return true;
    });

    // STEP 0.6: Geometric containment contrast correction.
    // The inline fix inside flattenHierarchy only sees PARENT-CHILD relationships.
    // Templates like exec_action_card / exec_chat_example / exec_sovereignty_dark
    // use FLAT slot layouts where the card_bg shape is a sibling of the "child"
    // text elements — not a parent. The inline fix therefore sees only the slide
    // background and (wrongly) flips white text on a dark card to dark, leaving
    // the text invisible. This pass walks every text element, finds the topmost
    // shape that geometrically contains it (zIndex below text's zIndex), and
    // re-runs the contrast rule against that shape's actual fill.
    try {
        const overlapShapes = elementsToProcess.filter(el =>
            (el.type === 'shape' || el.type === 'card') &&
            el.fill && el.fill !== 'transparent' && el.fill !== 'none' &&
            typeof el.x === 'number' && typeof el.y === 'number' &&
            typeof el.width === 'number' && typeof el.height === 'number'
        );
        if (overlapShapes.length > 0) {
            elementsToProcess.forEach(el => {
                if (!(el.type === 'text' || el.textType)) return;
                if (typeof el.x !== 'number' || typeof el.y !== 'number') return;
                const textW = el.width || 0;
                const textH = el.height || 0;
                const tCenterX = el.x + textW / 2;
                const tCenterY = el.y + textH / 2;
                let bestShape = null;
                let bestZ = -Infinity;
                const textZ = el.zIndex !== undefined ? el.zIndex : 50;
                overlapShapes.forEach(shape => {
                    if (shape.id === el.id) return;
                    if (tCenterX < shape.x || tCenterX > shape.x + shape.width) return;
                    if (tCenterY < shape.y || tCenterY > shape.y + shape.height) return;
                    const shapeZ = shape.zIndex !== undefined ? shape.zIndex : 0;
                    if (shapeZ >= textZ) return;
                    if (shapeZ > bestZ) {
                        bestZ = shapeZ;
                        bestShape = shape;
                    }
                });
                if (!bestShape) return;
                const effectiveBg = bestShape.fill;
                const textFill = el.fill || el.color;
                if (!textFill) {
                    el.fill = isColorDark(effectiveBg) ? '#FFFFFF' : '#111827';
                    console.log(`[SlideProcessor] 🎨 Geometric no-fill text ${el.id}: on shape ${bestShape.id} (${effectiveBg}) -> ${el.fill}`);
                    return;
                }
                if (hasLowContrast(textFill, effectiveBg)) {
                    const newFill = isColorDark(effectiveBg) ? '#FFFFFF' : '#111827';
                    if (newFill.toLowerCase() !== textFill.toLowerCase()) {
                        console.log(`[SlideProcessor] 🎨 Geometric contrast fix ${el.id}: ${textFill} on shape ${bestShape.id} (${effectiveBg}) -> ${newFill}`);
                        el.fill = newFill;
                    }
                }
            });
        }
    } catch (err) {
        console.warn('[SlideProcessor] Geometric contrast pass failed (non-fatal):', err);
    }

    const processedElements = [];

    for (const element of elementsToProcess) {
        let processed = processElement(element, backgroundColor);
        if (Array.isArray(processed)) {
            // Element was expanded (e.g., card → multiple elements)
            // FIX: Run validateTextElement on expanded text children for height correction & autoAdjustFontSize
            processed = processed.map(el => {
                if (el.type === 'text' && el.parentId) {
                    // Expanded card/step text — validate it for height correction
                    return validateTextElement(el);
                }
                return el;
            });
            processed = processed.map(el => ({
                ...el,
                zIndex: assignZIndex(el),
            }));
            // Apply color contrast to text elements (ONLY if they are top-level and don't belong to a card/group)
            // Elements with parentId (like card text) have their colors handled by the expander
            processed = processed.map(el => {
                if (el.parentId) return el;
                // return ensureColorContrast(el, backgroundColor); // DISABLED
                return el;
            });
            processedElements.push(...processed);
        } else if (processed) {
            processed.zIndex = assignZIndex(processed);
            // processed = ensureColorContrast(processed, backgroundColor); // DISABLED
            processedElements.push(processed);
        }
    }

    // Log raw text positions for debugging
    const textDebug = processedElements.filter(e => e.type === 'text').map(e => ({ id: e.id, y: e.y, text: e.content?.substring(0, 10) }));
    console.log('🔍 [SlideProcessor] Text positions (Pre-Fix):', JSON.stringify(textDebug));

    // Fix overlapping text elements (text vs text)
    // ENABLED (Smart Mode): Fixes loose lists but respects text inside Cards/Shapes
    fixTextOverlaps(processedElements);

    // Fix intra-group overlaps (text within same parent card/shape)
    fixIntraGroupOverlaps(processedElements);

    // Fix text overlaps inside decoration shapes (e.g. stats_highlight card columns)
    // These are top-level text elements (no parentId) that sit inside a decoration shape.
    // fixTextOverlaps() skips them (isProtected=true), fixIntraGroupOverlaps() ignores them (no parentId).
    fixIntraShapeTextOverlaps(processedElements);

    // Fix overlaps between expanded numbered_step groups.
    // fixTextOverlaps() skips parentId elements; fixIntraGroupOverlaps() only handles same-group.
    // This pass catches cross-step overlaps (e.g. step 2 desc bleeding into step 3 circle/title).
    fixInterStepOverlaps(processedElements);

    // Fix invisible top-level text (text color same as slide background)
    fixInvisibleTopLevelText(processedElements, backgroundColor);

    // Sort by z-index (painter's algorithm - low to high)
    processedElements.sort((a, b) => (a.zIndex ?? 50) - (b.zIndex ?? 50));

    return {
        ...slideData,
        elements: processedElements,
    };
}

/**
 * Check if two elements overlap horizontally
 */
function elementsOverlapHorizontally(el1, el2) {
    const el1Left = el1.x || 0;
    const el1Right = el1Left + (el1.width || 100);
    const el2Left = el2.x || 0;
    const el2Right = el2Left + (el2.width || 100);

    // Elements overlap if one starts before the other ends
    return el1Left < el2Right && el2Left < el1Right;
}

/**
 * Detect and fix overlapping text elements by adjusting Y positions.
 * Only fixes elements that actually overlap both vertically AND horizontally.
 */
function fixTextOverlaps(elements) {
    // Get only text elements, sorted by Y position
    const textElements = elements
        .filter(el => el.type === 'text')
        .sort((a, b) => (a.y || 0) - (b.y || 0));

    // Helper: Check if element is visually strictly inside any shape
    const isElementInsideAnyShape = (textEl, allElements) => {
        const shapes = allElements.filter(el => el.type === 'shape' || el.shapeType === 'rectangle');
        return shapes.some(shape => {
            // Strict containment check
            const shapeLeft = shape.x || 0;
            const shapeRight = shapeLeft + (shape.width || 0);
            const shapeTop = shape.y || 0;
            const shapeBottom = shapeTop + (shape.height || 0);

            const textLeft = textEl.x || 0;
            const textRight = textLeft + (textEl.width || 0);
            const textTop = textEl.y || 0;
            const textBottom = textTop + (textEl.height || 0);

            return (
                textLeft >= shapeLeft &&
                textRight <= shapeRight &&
                textTop >= shapeTop &&
                textBottom <= shapeBottom
            );
        });
    };

    if (textElements.length < 2) return;

    const MIN_GAP = 10;
    const SAFE_BOTTOM = CANVAS_HEIGHT - 40; // Don't push text below y=500 on 540px canvas

    // Check each element against ALL previous elements (not just consecutive)
    // The old consecutive-pair check missed overlaps when non-overlapping elements
    // (at different X positions) separated overlapping ones in Y-sorted order.
    for (let i = 1; i < textElements.length; i++) {
        const curr = textElements[i];

        // [SMART FIX] Check if "curr" text is protected (inside a shape or has parent)
        // If so, we trust the container's layout and DO NOT move it.
        const isProtected = curr.parentId || isElementInsideAnyShape(curr, elements);
        if (isProtected) {
            continue;
        }

        for (let j = 0; j < i; j++) {
            const prev = textElements[j];

            // Only check elements that overlap horizontally
            if (!elementsOverlapHorizontally(prev, curr)) {
                continue;
            }

            const prevBottom = (prev.y || 0) + (prev.height || 50);
            const currTop = curr.y || 0;

            // Check for overlap or insufficient gap
            if (currTop < prevBottom + MIN_GAP) {
                const newY = Math.round(Math.min(prevBottom + MIN_GAP, SAFE_BOTTOM));
                if (newY > currTop) {
                    console.log(`[SlideProcessor] ⚠️ Fixing text overlap: ${curr.id} moved from y:${currTop} to y:${newY}`);
                    curr.y = newY;
                }
            }
        }
    }
}

/**
 * Fix overlapping text elements within the same parent group.
 * fixTextOverlaps() skips protected elements (those with parentId).
 * This function handles those intra-group overlaps specifically.
 */
function fixIntraGroupOverlaps(elements) {
    // Group elements by parentId
    const groups = {};
    for (const el of elements) {
        if (el.parentId && el.type === 'text') {
            if (!groups[el.parentId]) groups[el.parentId] = [];
            groups[el.parentId].push(el);
        }
    }

    // Also find parent shape/bg elements to know container bounds
    const parentBgs = {};
    for (const el of elements) {
        if (el.id && el.id.endsWith('_bg') && el.type === 'shape') {
            const parentId = el.parentId || el.id.replace('_bg', '');
            parentBgs[parentId] = el;
        }
    }

    const MIN_GAP = 6; // Tighter gap for 16:9 slides (less vertical space)

    for (const [parentId, groupElements] of Object.entries(groups)) {
        if (groupElements.length < 2) continue;

        // Sort by Y position
        groupElements.sort((a, b) => (a.y || 0) - (b.y || 0));

        const parentBg = parentBgs[parentId];
        const parentBottom = parentBg ? (parentBg.y || 0) + (parentBg.height || 9999) : CANVAS_HEIGHT;

        for (let i = 1; i < groupElements.length; i++) {
            const prev = groupElements[i - 1];
            const curr = groupElements[i];

            // Only fix if they overlap horizontally
            if (!elementsOverlapHorizontally(prev, curr)) continue;

            const prevBottom = (prev.y || 0) + (prev.height || 30);
            const currTop = curr.y || 0;

            if (currTop < prevBottom + MIN_GAP) {
                const newY = prevBottom + MIN_GAP;
                // Don't push beyond parent bounds
                if (newY + 20 <= parentBottom) {
                    console.log(`[SlideProcessor] 🔧 Intra-group fix: ${curr.id} y:${currTop} → y:${newY} (parent: ${parentId})`);
                    curr.y = newY;
                } else {
                    // Can't move down — shrink font instead
                    const availableHeight = Math.max(20, parentBottom - currTop - 10);
                    if (curr.height && curr.height > availableHeight) {
                        const ratio = availableHeight / curr.height;
                        const newFontSize = Math.max(9, Math.floor((curr.fontSize || 16) * Math.sqrt(ratio)));
                        console.log(`[SlideProcessor] 🔧 Intra-group font shrink: ${curr.id} ${curr.fontSize}px → ${newFontSize}px`);
                        curr.fontSize = newFontSize;
                    }
                }
            }
        }
    }
}

/**
 * Fix overlapping text elements that sit inside the same decoration shape
 * but have no parentId (e.g. stats_highlight template where stat_value,
 * stat_label, stat_desc are top-level text inside card rectangles).
 * 
 * fixTextOverlaps() skips these (isProtected=true because they're inside a shape).
 * fixIntraGroupOverlaps() skips them (no parentId).
 * This function finds text elements sharing the same container shape and
 * shrinks fonts / adjusts positions to prevent overflow.
 */
function fixIntraShapeTextOverlaps(elements) {
    const shapes = elements.filter(el =>
        el.type === 'shape' && el.shapeType === 'rectangle' &&
        (el.width || 0) > 50 && (el.height || 0) > 50
    );
    const textElements = elements.filter(el => el.type === 'text' && !el.parentId);

    if (shapes.length === 0 || textElements.length === 0) return;

    // For each shape, find text elements fully contained within it
    for (const shape of shapes) {
        const sx = shape.x || 0;
        const sy = shape.y || 0;
        const sw = shape.width || 0;
        const sh = shape.height || 0;
        const shapeBottom = sy + sh;

        const contained = textElements.filter(t => {
            const tx = t.x || 0;
            const ty = t.y || 0;
            const tw = t.width || 0;
            return tx >= sx && (tx + tw) <= (sx + sw) && ty >= sy && ty < shapeBottom;
        });

        if (contained.length < 2) continue;

        // Sort by Y position
        contained.sort((a, b) => (a.y || 0) - (b.y || 0));

        const MIN_GAP = 4;

        for (let i = 0; i < contained.length; i++) {
            const curr = contained[i];
            const currFontSize = curr.fontSize || 16;
            const currLineHeight = curr.lineHeight || 1.4;
            const currWidth = curr.width || 200;

            // Estimate actual rendered height
            const content = curr.content || '';
            const charWidthRatio = 0.48;
            const charsPerLine = Math.max(1, Math.floor(currWidth / (currFontSize * charWidthRatio)));
            const contentLines = content.split('\n');
            let totalLines = 0;
            for (const line of contentLines) {
                totalLines += Math.max(1, Math.ceil((line.length || 1) / charsPerLine));
            }
            const estimatedHeight = Math.ceil(totalLines * currFontSize * currLineHeight);

            // Check if this element's rendered content overflows the shape bottom
            const currY = curr.y || 0;
            const currBottom = currY + estimatedHeight;

            if (currBottom > shapeBottom - MIN_GAP) {
                // Shrink font to fit within shape
                let newFs = currFontSize;
                const minFs = 9;
                const availableHeight = Math.max(20, shapeBottom - currY - MIN_GAP);

                while (newFs > minFs) {
                    const cpl = Math.max(1, Math.floor(currWidth / (newFs * charWidthRatio)));
                    let lines = 0;
                    for (const line of contentLines) {
                        lines += Math.max(1, Math.ceil((line.length || 1) / cpl));
                    }
                    const h = Math.ceil(lines * newFs * currLineHeight);
                    if (h <= availableHeight) break;
                    newFs--;
                }

                if (newFs < currFontSize) {
                    console.log(`[SlideProcessor] 🔧 Intra-shape font shrink: ${curr.id} ${currFontSize}px → ${newFs}px (shape ${shape.id})`);
                    curr.fontSize = newFs;
                }
            }

            // Check overlap with next element in same shape
            if (i < contained.length - 1) {
                const next = contained[i + 1];
                const nextY = next.y || 0;

                // Recalculate height after potential font shrink
                const fs = curr.fontSize || 16;
                const cpl = Math.max(1, Math.floor(currWidth / (fs * charWidthRatio)));
                let lines = 0;
                for (const line of contentLines) {
                    lines += Math.max(1, Math.ceil((line.length || 1) / cpl));
                }
                const actualHeight = Math.ceil(lines * fs * currLineHeight);
                const actualBottom = currY + actualHeight;

                if (nextY < actualBottom + MIN_GAP) {
                    const newNextY = Math.min(actualBottom + MIN_GAP, shapeBottom - 20);
                    if (newNextY > nextY) {
                        console.log(`[SlideProcessor] 🔧 Intra-shape push: ${next.id} y:${nextY} → y:${newNextY} (shape ${shape.id})`);
                        next.y = newNextY;
                    }
                }
            }
        }
    }
}

/**
 * Fix invisible top-level text where text fill is nearly identical to the slide background.
 * flattenHierarchy handles parent-aware fixes for children inside cards/groups,
 * but top-level text (no parentId) can still be invisible if AI picks a fill
 * that matches the slide backgroundColor.
 */
function fixInvisibleTopLevelText(elements, backgroundColor) {
    if (!backgroundColor) return;

    const bgIsDark = isColorDark(backgroundColor);

    for (const el of elements) {
        // Only check top-level text elements (no parentId = not inside a card/group)
        if (el.type !== 'text' || el.parentId) continue;

        const textFill = el.fill || el.color;

        // STRICT RULE for body/detail text: always use white on dark bg, near-black on light bg.
        // Grey text (e.g. #6B7280, #9CA3AF) on dark backgrounds is not acceptable.
        // White text on light backgrounds is not acceptable either.
        const isBodyText = el.textType === 'body' || el.textType === 'detail'
            || (!el.textType && el.fontSize && el.fontSize <= 24);

        if (isBodyText) {
            // Body text: strictly enforce contrast regardless of current fill
            const correctFill = bgIsDark ? '#FFFFFF' : '#1F2937';
            if (el.fill !== correctFill || el.color !== correctFill) {
                el.fill = correctFill;
                el.color = correctFill;
            }
            continue;
        }

        if (!textFill) {
            // No fill at all — derive from background
            el.fill = bgIsDark ? '#FFFFFF' : '#111827';
            el.color = el.fill;
            console.log(`[SlideProcessor] 🎨 No fill on top-level text ${el.id}, bg=${backgroundColor} → ${el.fill}`);
        } else if (hasLowContrast(textFill, backgroundColor)) {
            // Text color has low contrast with slide background — flip
            el.fill = bgIsDark ? '#FFFFFF' : '#111827';
            el.color = el.fill;
            console.log(`[SlideProcessor] 🎨 Low-contrast top-level text fix ${el.id}: ${textFill} vs ${backgroundColor} → ${el.fill}`);
        }
    }
}

/**
 * Check if two bounding boxes overlap (with optional buffer)
 */
function boundingBoxesOverlap(el1, el2, buffer = 0) {
    const el1Left = (el1.x || 0) - buffer;
    const el1Right = el1Left + (el1.width || el1.size || 50) + buffer * 2;
    const el1Top = (el1.y || 0) - buffer;
    const el1Bottom = el1Top + (el1.height || el1.size || 50) + buffer * 2;

    const el2Left = el2.x || 0;
    const el2Right = el2Left + (el2.width || el2.size || 50);
    const el2Top = el2.y || 0;
    const el2Bottom = el2Top + (el2.height || el2.size || 50);

    // Check if rectangles overlap
    return el1Left < el2Right && el1Right > el2Left &&
        el1Top < el2Bottom && el1Bottom > el2Top;
}

/**
 * Fix overlaps BETWEEN different expanded numbered_step groups.
 *
 * Problem: fixTextOverlaps() skips all elements with a parentId, and
 * fixIntraGroupOverlaps() only operates within the same parentId group.
 * Neither catches cases where step N's description text bleeds into the
 * circle or title of step N+1 — producing the visible overlap in the screenshot.
 *
 * Strategy:
 *  1. Collect all elements that belong to a numbered_step group (have parentId).
 *  2. Compute the actual bounding box (minY … maxY) for each group.
 *  3. Sort groups by their minY.
 *  4. If group[i].minY < group[i-1].maxY + MIN_GAP, shift ALL of group[i]'s
 *     elements down by the required amount (cascading to subsequent groups too).
 */
function fixInterStepOverlaps(elements) {
    const MIN_GAP = 12;
    const SAFE_BOTTOM = CANVAS_HEIGHT - 40; // Don't push groups past y=500

    // Identify all unique step/card group parent IDs
    const groupMap = {};
    for (const el of elements) {
        if (!el.parentId) continue;
        if (!groupMap[el.parentId]) groupMap[el.parentId] = [];
        groupMap[el.parentId].push(el);
    }

    if (Object.keys(groupMap).length < 2) return;

    // Compute bounding box for each group
    // Use the _bg shape's bounds as the authoritative group height.
    // validateTextElement inflates text heights for text-vs-text overlap detection,
    // but using those inflated heights here causes cascading pushdowns that push
    // subsequent card groups off-canvas.
    const groups = Object.entries(groupMap).map(([parentId, children]) => {
        const bgEl = children.find(c => c.id?.endsWith('_bg') && c.type === 'shape');
        const minX = Math.min(...children.map(c => c.x || 0));
        const maxX = Math.max(...children.map(c => (c.x || 0) + (c.width || 100)));
        const minY = Math.min(...children.map(c => c.y || 0));
        // maxY: prefer _bg shape bounds over inflated text heights
        const maxY = bgEl
            ? (bgEl.y || 0) + (bgEl.height || 30)
            : Math.max(...children.map(c => (c.y || 0) + (c.height || 30)));
        return { parentId, children, minX, maxX, minY, maxY };
    });

    // Sort by top Y position
    groups.sort((a, b) => a.minY - b.minY);

    for (let i = 1; i < groups.length; i++) {
        const prev = groups[i - 1];
        const curr = groups[i];

        // Skip groups in different columns (no horizontal overlap)
        // e.g., left-side cards vs right-side cards should not push each other down
        if (prev.maxX <= curr.minX || curr.maxX <= prev.minX) continue;

        if (curr.minY < prev.maxY + MIN_GAP) {
            let shift = (prev.maxY + MIN_GAP) - curr.minY;

            // Cap shift so no element goes past SAFE_BOTTOM
            const wouldMaxY = curr.maxY + shift;
            if (wouldMaxY > SAFE_BOTTOM) {
                const cappedShift = Math.max(0, SAFE_BOTTOM - curr.maxY);
                if (cappedShift < shift) {
                    console.log(`[SlideProcessor] ⚠️ Inter-step shift capped: ${shift}px → ${cappedShift}px (canvas bounds)`);
                    shift = cappedShift;
                }
            }

            if (shift > 0) {
                console.log(`[SlideProcessor] 🔧 Inter-step overlap: group ${curr.parentId} shifted down by ${shift}px`);
                for (const el of curr.children) {
                    el.y = (el.y || 0) + shift;
                }
                curr.minY += shift;
                curr.maxY += shift;
            }
        }
    }
}

/**
 * Detect and fix text elements overlapping with shapes/icons.
 * Adjusts text position or reduces font size to prevent overlap.
 */
function fixTextShapeOverlaps(elements) {
    const textElements = elements.filter(el => el.type === 'text');
    const shapeElements = elements.filter(el =>
        el.type === 'shape' || el.type === 'icon' || el.type === 'numbered_step'
    );

    if (textElements.length === 0 || shapeElements.length === 0) return;

    const SAFE_GAP = 20; // Minimum safe distance from shapes
    const MIN_FONT_SIZE = 12;

    for (const text of textElements) {
        for (const shape of shapeElements) {
            // Skip check if elements belong to same parent (e.g. text inside card/numbered step)
            // This prevents the fixer from ejecting text that is INTENDED to be on top of a shape
            if (text.parentId && shape.parentId && text.parentId === shape.parentId) {
                continue;
            }

            // Check if text overlaps with shape (including buffer zone)
            if (boundingBoxesOverlap(shape, text, SAFE_GAP)) {
                const shapeBottom = (shape.y || 0) + (shape.height || shape.size || 50);
                const shapeRight = (shape.x || 0) + (shape.width || shape.size || 50);
                const textTop = text.y || 0;
                const textLeft = text.x || 0;

                // Determine if text is below the shape (vertical overlap)
                const isTextBelow = textTop >= (shape.y || 0);
                // Determine if text is to the right of shape (horizontal overlap)  
                const isTextRight = textLeft >= (shape.x || 0);

                // Try to move text down if it's below the shape
                if (isTextBelow && textTop < shapeBottom + SAFE_GAP) {
                    const newY = shapeBottom + SAFE_GAP;
                    // Only move if it won't push text off canvas
                    if (newY + (text.height || 50) <= CANVAS_HEIGHT) {
                        console.log(`[SlideProcessor] ⚠️ Fixing text-shape overlap: ${text.id} moved from y:${textTop} to y:${newY}`);
                        text.y = newY;
                        continue; // Fixed, move to next shape
                    }
                }

                // If can't move, try reducing font size
                const currentFontSize = text.fontSize || 20;
                if (currentFontSize > MIN_FONT_SIZE) {
                    const newFontSize = Math.max(MIN_FONT_SIZE, currentFontSize - 2);
                    // Proportionally reduce height
                    const heightRatio = newFontSize / currentFontSize;
                    const newHeight = Math.ceil((text.height || 50) * heightRatio);

                    console.log(`[SlideProcessor] ⚠️ Reducing font to avoid overlap: ${text.id} fontSize ${currentFontSize}px -> ${newFontSize}px`);
                    text.fontSize = newFontSize;
                    text.height = newHeight;
                }
            }
        }
    }
}

/**
 * Auto-expand text width to fit content instead of wrapping early
 * ONLY applies to main slide titles (large font, near top of slide, NOT inside cards)
 * Keeps sub-headers, card text, and body text at their original width
 */
function autoExpandTextWidth(element) {
    if (element.type !== 'text' || !element.content) return element;

    // NEVER expand text inside cards - they have parentId set during flattening
    if (element.parentId) return element;

    const fontSize = element.fontSize || 20;
    const y = element.y || 0;
    
    // Only expand main slide titles: large font (>= 24px) AND at very top (y < 100)
    // Sub-headers and body text should keep their defined width for proper layout
    const isTitle = fontSize >= 24 && y < 100;
    if (!isTitle) return element;

    const content = element.content;
    const x = element.x || 0;
    
    // Find the longest line in multi-line content (preserve \n)
    const lines = content.split('\n');
    const longestLine = lines.reduce((a, b) => a.length > b.length ? a : b, '');
    
    // Estimate width needed for the longest line
    // Average character width is roughly 0.55-0.6 of font size for most fonts
    const charWidthRatio = 0.6;
    const estimatedWidthNeeded = longestLine.length * fontSize * charWidthRatio;
    
    // Calculate maximum available width from x position to canvas edge (with padding)
    const rightPadding = 50; // Leave some padding from right edge
    const maxAvailableWidth = CANVAS_WIDTH - x - rightPadding;
    
    // Current width from AI
    const currentWidth = element.width || 200;
    
    // If estimated width exceeds current width, expand to fit (up to max available)
    if (estimatedWidthNeeded > currentWidth) {
        const newWidth = Math.min(estimatedWidthNeeded + 20, maxAvailableWidth); // +20 for safety margin
        
        if (newWidth > currentWidth) {
            console.log(`[SlideProcessor] 📐 Auto-expanding TITLE width for ${element.id}: ${currentWidth}px -> ${newWidth}px (content needs ~${Math.round(estimatedWidthNeeded)}px)`);
            return {
                ...element,
                width: newWidth
            };
        }
    }
    
    return element;
}

/**
 * Auto-adjust font size based on content length to prevent overflow
 */
function autoAdjustFontSize(element) {
    if (element.type !== 'text' || !element.content) return element;

    const content = element.content;
    const contentLength = content.length;
    const width = element.width || 200;
    const height = element.height || 50;
    const textType = element.textType || 'body';

    // Character limits by text type
    const limits = {
        title: { maxChars: 60, defaultSize: 32, minSize: 22 },
        subtitle: { maxChars: 100, defaultSize: 22, minSize: 16 },
        body: { maxChars: 250, defaultSize: 16, minSize: 12 },
        bullet: { maxChars: 300, defaultSize: 16, minSize: 12 },
        caption: { maxChars: 150, defaultSize: 12, minSize: 10 },
    };

    const config = limits[textType] || limits.body;
    let fontSize = element.fontSize || config.defaultSize;
    const lineHeight = element.lineHeight || 1.4;

    // If content exceeds recommended length, reduce font size proportionally
    if (contentLength > config.maxChars) {
        const overflowRatio = config.maxChars / contentLength;
        const proposedSize = Math.floor(fontSize * Math.sqrt(overflowRatio));
        fontSize = Math.max(config.minSize, proposedSize);

        console.log(`[SlideProcessor] 📏 Auto-adjusting font: ${element.id} has ${contentLength} chars (max ${config.maxChars}), reducing ${element.fontSize || config.defaultSize}px -> ${fontSize}px`);
    }

    // Estimate required height based on content
    const charsPerLine = Math.floor(width / (fontSize * 0.6));
    const estimatedLines = Math.ceil(contentLength / charsPerLine);
    const estimatedHeight = estimatedLines * fontSize * lineHeight;

    // If estimated height exceeds allocated height, reduce font size
    if (estimatedHeight > height && fontSize > config.minSize) {
        const heightRatio = height / estimatedHeight;
        const proposedSize = Math.floor(fontSize * Math.sqrt(heightRatio));
        fontSize = Math.max(config.minSize, proposedSize);

        console.log(`[SlideProcessor] 📏 Height overflow: ${element.id} needs ${estimatedHeight}px but has ${height}px, reducing to ${fontSize}px`);
    }

    return {
        ...element,
        fontSize: fontSize,
        lineHeight: element.lineHeight || lineHeight,
    };
}

/**
 * Process a slide with async icon fetching (use for initial load)
 * @param {Object} slideData - Raw slide data from AI
 * @returns {Promise<Object>} - Processed slide with icons prefetched
 */
export async function processSlideAsync(slideData) {
    if (!slideData || !slideData.elements) {
        console.warn('[SlideProcessor] Invalid slide data');
        return slideData;
    }

    // Collect all icon names for prefetching
    // FIX: AI may send icon name in 'iconName', 'name', or 'content' property
    const iconNames = [];
    for (const element of slideData.elements) {
        if (element.type === 'icon') {
            const iconName = element.iconName || element.name || element.icon || element.content;
            if (iconName) iconNames.push(iconName);
        }
        if (element.type === 'card') {
            const iconName = element.iconName || element.name || element.icon || element.content;
            if (iconName) iconNames.push(iconName);
            // Also check children for icons
            if (element.children) {
                for (const child of element.children) {
                    if (child.type === 'icon') {
                        const childIconName = child.iconName || child.name || child.icon || child.content;
                        if (childIconName) iconNames.push(childIconName);
                    }
                }
            }
        }
    }

    // Prefetch all icons in parallel
    if (iconNames.length > 0) {
        await prefetchIcons(iconNames);
    }

    // Now process synchronously (icons are cached)
    return processSlide(slideData);
}

/**
 * Process a single element, expanding complex types
 */
function processElement(element, slideBgColor) {
    if (!element || !element.type) return null;

    switch (element.type) {
        case 'card':
            return expandCard(element);
        case 'numbered_step':
            return expandNumberedStep(element, slideBgColor);
        case 'icon':
            return processIcon(element);
        case 'text':
            return validateTextElement(element);
        case 'shape':
            return validateShapeElement(element);
        case 'image':
            return validateImageElement(element);
        case 'image_placeholder':
            return validateImagePlaceholder(element);
        case 'chart':
        case 'group':
        case 'svg_diagram':
            return element;
        default:
            console.warn(`[SlideProcessor] Unknown element type: ${element.type}`);
            return element;
    }
}

/**
 * Expand a card element into its component parts
 * Card = Background shape + Icon + Title text + Description text
 */
function expandCard(card) {
    const elements = [];
    const baseId = card.id || uniqueId('card');

    // Use card's zIndex as base, or default
    const baseZIndex = card.zIndex ?? Z_INDEX_DEFAULTS.card;

    // Determine if card background is light or dark for text contrast
    const cardBg = card.backgroundColor || '#1f2937';
    const bgIsLight = !isColorDark(cardBg);

    // Use high contrast colors based on card background
    const defaultTitleColor = bgIsLight ? '#111827' : '#ffffff';
    const defaultDescColor = bgIsLight ? '#374151' : '#d1d5db';
    const defaultIconColor = bgIsLight ? '#3B82F6' : '#FFFFFF';

    // Safety: If AI explicitly sent titleColor/descriptionColor with low contrast
    // against the card background, override with the safe default (AI mistake)
    // Also check card.color / card.fontColor as fallback (AI sometimes uses these instead)
    const rawTitleColor = card.titleColor || card.color || card.fontColor;
    const safeTitleColor = (rawTitleColor && !hasLowContrast(rawTitleColor, cardBg))
        ? rawTitleColor : defaultTitleColor;
    const rawDescColor = card.descriptionColor || card.color || card.fontColor;
    const safeDescColor = (rawDescColor && !hasLowContrast(rawDescColor, cardBg))
        ? rawDescColor : defaultDescColor;

    // Layout Mode Decision
    // If card is short (< 180px) OR wide (> 300px), prefer horizontal layout
    const cardHeight = parseInt(card.height || 280, 10);
    const cardWidth = parseInt(card.width || 280, 10);
    const cardX = parseInt(card.x || 50, 10);
    const cardY = parseInt(card.y || 150, 10);

    const isCompactHeight = cardHeight < 180;
    const isWide = cardWidth > 350;
    const useHorizontalLayout = isCompactHeight || isWide;

    console.log(`[SlideProcessor] Expanding card ${baseId}: ${cardWidth}x${cardHeight} at (${cardX}, ${cardY}) (Horizontal: ${useHorizontalLayout}) keys: ${Object.keys(card).join(',')}`);
    if (!card.title) console.warn(`[SlideProcessor] ⚠️ Card ${baseId} missing title!`);
    if (!card.description) console.warn(`[SlideProcessor] ⚠️ Card ${baseId} missing description!`);

    // Card background shape (lowest z-index within card)
    elements.push({
        id: `${baseId}_bg`,
        type: 'shape',
        shapeType: 'rectangle',
        x: card.x || 50,
        y: card.y || 150,
        width: card.width || 280,
        height: card.height || 280,
        fill: cardBg,
        stroke: card.borderColor || (bgIsLight ? '#e5e7eb' : '#374151'),
        strokeWidth: 1,
        rx: card.borderRadius || 12,
        ry: card.borderRadius || 12,
        opacity: card.opacity || 1,
        zIndex: baseZIndex,  // Background at base z-index
        parentId: baseId,
    });

    // Adaptive font sizing: estimate desc lines and shrink if needed
    const descText = card.description || '';
    const titleText = card.title || '';

    if (useHorizontalLayout) {
        // === Horizontal Layout (Icon Left | Text Right) ===
        const padding = 16;
        const iconSize = Math.min(40, cardHeight - padding * 2); // Fit icon within card
        const iconX = (card.x || 50) + padding;
        const iconY = (card.y || 150) + padding; // Top-aligned icon

        // Card icon
        if (card.iconName) {
            elements.push({
                id: `${baseId}_icon`,
                type: 'icon',
                iconName: card.iconName,
                x: iconX,
                y: iconY,
                size: iconSize,
                fill: card.iconColor || defaultIconColor,
                zIndex: baseZIndex + 20,
                parentId: baseId,
            });
        }

        const textStartX = iconX + iconSize + padding;
        const textWidth = (card.width || 280) - (textStartX - (card.x || 50)) - padding;

        let currentTextY = iconY;

        // Adaptive title font: default 18px, min 12px for compact cards
        const hTitleFontSize = card.titleFontSize || Math.min(18, Math.max(12, Math.floor(cardHeight * 0.12)));
        const hTitleLineH = 1.2;
        const hTitleHeight = Math.ceil(hTitleFontSize * hTitleLineH) + 4;

        // Card title
        if (card.title) {
            elements.push({
                id: `${baseId}_title`,
                type: 'text',
                textType: 'subtitle',
                content: card.title,
                x: textStartX,
                y: currentTextY,
                width: textWidth,
                height: hTitleHeight,
                fontSize: hTitleFontSize,
                fontWeight: card.titleFontWeight || 'bold',
                fill: safeTitleColor,
                textAlign: 'left',
                lineHeight: hTitleLineH,
                zIndex: baseZIndex + 40,
                parentId: baseId,
            });
            currentTextY += hTitleHeight + 4;
        }

        // Card description — adaptive font to fit remaining space
        if (card.description) {
            const availableDescH = (card.height || 280) - (currentTextY - (card.y || 150)) - padding;
            let hDescFontSize = card.descriptionFontSize || 14;
            const hDescLineH = 1.35;
            // Estimate lines and shrink if needed
            const charsPerLine = Math.max(1, Math.floor(textWidth / (hDescFontSize * 0.55)));
            const estLines = Math.ceil(descText.length / charsPerLine);
            const estHeight = estLines * hDescFontSize * hDescLineH;
            if (estHeight > availableDescH && availableDescH > 0) {
                hDescFontSize = Math.max(10, Math.floor(hDescFontSize * Math.sqrt(availableDescH / estHeight)));
            }

            elements.push({
                id: `${baseId}_desc`,
                type: 'text',
                textType: 'body',
                content: card.description,
                x: textStartX,
                y: currentTextY,
                width: textWidth,
                height: availableDescH,
                fontSize: hDescFontSize,
                fontWeight: 'normal',
                fill: safeDescColor,
                textAlign: 'left',
                lineHeight: hDescLineH,
                zIndex: baseZIndex + 45,
                parentId: baseId,
            });
        }

    } else {
        // === Vertical Layout (Icon Top | Title | Desc) ===
        const vPadding = 15;
        const iconY = (card.y || 150) + vPadding;
        // Adaptive icon size: scale with card height, max 40px
        const iconSize = Math.min(40, Math.floor(cardHeight * 0.22));
        const iconBottom = iconY + iconSize;
        const titleY = iconBottom + 10;

        // Adaptive title font: scale with card height
        const vTitleFontSize = card.titleFontSize || Math.min(18, Math.max(12, Math.floor(cardHeight * 0.09)));
        const vTitleLineH = 1.2;
        // Estimate title height (may wrap)
        const titleTextWidth = (card.width || 280) - (vPadding * 2);
        const titleCharsPerLine = Math.max(1, Math.floor(titleTextWidth / (vTitleFontSize * 0.55)));
        const titleLines = Math.max(1, Math.ceil(titleText.length / titleCharsPerLine));
        const titleHeight = Math.ceil(titleLines * vTitleFontSize * vTitleLineH) + 4;
        const descY = titleY + titleHeight + 4;

        // Card icon (above background)
        if (card.iconName) {
            elements.push({
                id: `${baseId}_icon`,
                type: 'icon',
                iconName: card.iconName,
                x: (card.x || 50) + vPadding,
                y: iconY,
                size: iconSize,
                fill: card.iconColor || defaultIconColor,
                zIndex: baseZIndex + 20,  // Icons above background
                parentId: baseId,
            });
        }

        // Card title - use high contrast color
        if (card.title) {
            elements.push({
                id: `${baseId}_title`,
                type: 'text',
                textType: 'subtitle',
                content: card.title,
                x: (card.x || 50) + vPadding,
                y: titleY,
                width: titleTextWidth,
                height: titleHeight,
                fontSize: vTitleFontSize,
                fontWeight: card.titleFontWeight || 'bold',
                fill: safeTitleColor,
                textAlign: 'left',
                lineHeight: vTitleLineH,
                zIndex: baseZIndex + 40,  // Text above icons
                parentId: baseId,
            });
        }

        // Card description — adaptive font to fit remaining card space
        if (card.description) {
            const availableDescH = cardHeight - (descY - (card.y || 150)) - vPadding;
            let vDescFontSize = card.descriptionFontSize || 14;
            const vDescLineH = 1.3;
            // Estimate lines and shrink if needed
            const descCharsPerLine = Math.max(1, Math.floor(titleTextWidth / (vDescFontSize * 0.55)));
            const descLines = Math.ceil(descText.length / descCharsPerLine);
            const estDescH = descLines * vDescFontSize * vDescLineH;
            if (estDescH > availableDescH && availableDescH > 0) {
                vDescFontSize = Math.max(10, Math.floor(vDescFontSize * Math.sqrt(availableDescH / estDescH)));
            }

            elements.push({
                id: `${baseId}_desc`,
                type: 'text',
                textType: 'body',
                content: card.description,
                x: (card.x || 50) + vPadding,
                y: descY,
                width: titleTextWidth,
                height: Math.max(20, availableDescH),
                fontSize: vDescFontSize,
                fontWeight: 'normal',
                fill: safeDescColor,
                textAlign: 'left',
                lineHeight: vDescLineH,
                zIndex: baseZIndex + 45,  // Description just above title
                parentId: baseId,
            });
        }
    }

    // Tag all expanded elements with the card's background for canvas-level contrast safety net
    return elements.map(el => el.type === 'text' ? { ...el, parentBgColor: cardBg } : el);
}

/**
 * Expand a numbered step into circle + number + label
 */
function expandNumberedStep(step, slideBgColor) {
    const elements = [];
    const baseId = step.id || uniqueId('step');
    // FIX: Cap circle size to fit within step's declared height (prevents circle overflow)
    const stepHeight = step.height || 80;
    const maxCircleSize = Math.min(stepHeight * 0.7, 50); // 70% of height or 50px max (smaller for 16:9)
    const size = step.size || maxCircleSize;
    const x = step.x || 100;
    const y = step.y || 170;

    // Heuristic: If width is significantly larger than size, assume horizontal layout (Circle | Text)
    // Otherwise assume vertical stack (Circle / Text)
    const isWide = (step.width || size) > (size * 2);

    // Determine circle color: prefer explicit circleColor, then backgroundColor (AI sends this for step bg),
    // then a safe accent. NEVER use step.color — AI sends that as text color (often white/light).
    const circleColor = step.circleColor || step.backgroundColor || '#3B82F6'; // Accent blue fallback
    const circleIsDark = isColorDark(circleColor);
    const numberColor = step.numberColor || (circleIsDark ? '#FFFFFF' : '#111827');

    // Determine effective background color for TEXT contrast
    // The circle has its own background (circleColor), but the title/desc text sits OUTSIDE
    // the circle, on whatever background is behind the step element (slide bg or parent shape bg)
    const effectiveBg = slideBgColor || '#1E293B'; // Assume dark if unknown
    const bgIsLight = !isColorDark(effectiveBg);
    const defaultTitleColor = bgIsLight ? '#111827' : '#ffffff';
    const defaultDescColor = bgIsLight ? '#374151' : '#d1d5db';

    // Safety: If AI-extracted colors have low contrast against the background, override with safe defaults
    // Also check step.color / step.fontColor as fallback (AI sometimes uses generic color prop)
    const rawTitleColor = step.labelColor || step.titleColor || step.color || step.fontColor;
    const safeTitleColor = rawTitleColor && !hasLowContrast(rawTitleColor, effectiveBg)
        ? rawTitleColor : defaultTitleColor;
    const rawDescColor = step.descriptionColor || step.color || step.fontColor;
    const safeDescColor = rawDescColor && !hasLowContrast(rawDescColor, effectiveBg)
        ? rawDescColor : defaultDescColor;

    // Circle background
    elements.push({
        id: `${baseId}_circle`,
        type: 'shape',
        shapeType: 'circle',
        x: x,
        y: y,
        width: size,
        height: size,
        fill: circleColor,
        stroke: 'none',
        strokeWidth: 0,
        opacity: 1,
        parentId: baseId,
    });

    // Number text (AI may use 'number' or 'index', fallback to 1)
    elements.push({
        id: `${baseId}_number`,
        type: 'text',
        textType: 'title',
        content: String(step.number || step.index || 1),
        x: x,
        y: y + (size * 0.15),
        width: size,
        height: size * 0.7,
        fontSize: size * 0.5,
        fontWeight: 'bold',
        fill: numberColor,
        color: numberColor,
        textAlign: 'center',
        parentId: baseId,
    });

    // Resolve Text Content
    // AI may send content as a single string (with newline separating title and description)
    // or as separate title/label and description fields
    let titleContent = step.title || step.label;
    let descContent = step.description;

    // Handle AI-generated 'content' field: split first line as title, rest as description
    if (!titleContent && step.content) {
        const lines = step.content.split('\n');
        titleContent = lines[0];
        if (lines.length > 1) {
            descContent = descContent || lines.slice(1).join('\n');
        }
    }

    if (isWide) {
        // === Horizontal Layout: Circle | Title / Desc ===
        const textX = x + size + 20;
        // Dynamic width: Use provided width OR remaining canvas space (minus padding)
        const defaultWidth = CANVAS_WIDTH - textX - 50;
        const availableWidth = step.width ? (step.width - size - 20) : defaultWidth;

        // Adaptive title font: scale with step height, max 20px
        const sTitleFontSize = step.labelFontSize || Math.min(20, Math.max(13, Math.floor(stepHeight * 0.2)));
        const sTitleLineH = 1.2;
        const sTitleHeight = Math.ceil(sTitleFontSize * sTitleLineH) + 4;

        let currentY = y + 10; // Slight top padding relative to circle

        if (titleContent) {
            elements.push({
                id: `${baseId}_title`,
                type: 'text',
                textType: 'subtitle',
                content: titleContent,
                x: textX,
                y: currentY,
                width: availableWidth,
                height: sTitleHeight,
                fontSize: sTitleFontSize,
                fontWeight: step.labelFontWeight || 'bold',
                fill: safeTitleColor,
                textAlign: 'left',
                lineHeight: sTitleLineH,
                parentId: baseId,
            });
            currentY += sTitleHeight + 4;
        }

        if (descContent) {
            // Adaptive desc font: fit within remaining step height
            const availableDescH = Math.max(30, stepHeight - (currentY - y) - 8);
            let sDescFontSize = step.descriptionFontSize || 14;
            const sDescLineH = 1.35;
            const descCharsPerLine = Math.max(1, Math.floor(availableWidth / (sDescFontSize * 0.55)));
            const descLines = Math.ceil((descContent.length || 1) / descCharsPerLine);
            const estDescH = descLines * sDescFontSize * sDescLineH;
            if (estDescH > availableDescH && availableDescH > 0) {
                sDescFontSize = Math.max(10, Math.floor(sDescFontSize * Math.sqrt(availableDescH / estDescH)));
            }

            elements.push({
                id: `${baseId}_desc`,
                type: 'text',
                textType: 'body',
                content: descContent,
                x: textX,
                y: currentY,
                width: availableWidth,
                height: availableDescH,
                fontSize: sDescFontSize,
                fontWeight: 'normal',
                fill: safeDescColor,
                textAlign: 'left',
                lineHeight: sDescLineH,
                parentId: baseId,
            });
        }
    } else {
        // === Vertical Layout: Circle / Label ===
        // Only supports Label/Title below circle
        if (titleContent) {
            // Center the text relative to the circle (x + size/2)
            // But allow it to expand wide.
            const centerX = x + (size / 2);
            // Default to a generous width (e.g., 400px or remaining space)
            const textWidth = step.width || Math.min(400, CANVAS_WIDTH - x);
            const textX = centerX - (textWidth / 2);

            elements.push({
                id: `${baseId}_label`,
                type: 'text',
                textType: 'subtitle',
                content: titleContent,
                x: textX,
                y: y + size + 25, // Safe 25px gap from circle
                width: textWidth,
                height: 35,
                fontSize: step.labelFontSize || 18,
                fontWeight: step.labelFontWeight || 'bold',
                fill: safeTitleColor,
                textAlign: 'center',
                lineHeight: 1.2,
                parentId: baseId,
            });
        }
        // Description ignored in vertical layout to prevent massive overlap, 
        // or could be added below label if needed.
    }

    // Tag all expanded step elements with the effective background for canvas-level contrast safety net
    return elements.map(el => el.type === 'text' ? { ...el, parentBgColor: effectiveBg } : el);
}

function processIcon(icon) {
    // FIX: AI JSON may send icon name in different properties:
    // - 'iconName' (internal code convention)
    // - 'name' (some AI formats)
    // - 'icon' (AI frequently uses this, e.g. {"icon": "lightbulb"})
    // - 'content' (card children icons use this)
    // Support all by checking in order of preference
    const iconNameToResolve = icon.iconName || icon.name || icon.icon || icon.content;
    
    if (!iconNameToResolve) {
        console.warn('[SlideProcessor] ⚠️ Icon element missing name/iconName/content:', icon);
    }
    
    const { path, name } = mapIconToPath(iconNameToResolve);

    // FIX: Normalize icon size — AI sometimes sends width/height instead of size
    const iconSize = icon.size || icon.width || icon.height || 32;

    return {
        ...icon,
        // FIX: Normalize to 'iconName' for internal use while preserving 'name' from AI
        iconName: iconNameToResolve,
        resolvedIconName: name,
        svgPath: path,
        // Ensure required properties
        x: clamp(icon.x || 0, 0, CANVAS_WIDTH),
        y: clamp(icon.y || 0, 0, CANVAS_HEIGHT),
        size: iconSize,
        width: iconSize, // Normalize for bounding box calculations
        height: iconSize,
        // FIX: AI JSON uses 'color' property, internal code uses 'fill'
        fill: icon.fill || icon.color || '#ffffff',
    };
}

/**
 * Validate and normalize a text element
 */
function validateTextElement(text) {
    // Determine appropriate font size based on textType if not provided
    let fontSize = text.fontSize;

    // Use smaller defaults for elements inside cards/groups (parentId set)
    const isInsideGroup = !!text.parentId;

    if (!fontSize || fontSize < 8) {
        // Use sensible defaults based on textType
        // Elements inside cards/groups get smaller defaults to prevent overflow
        switch (text.textType) {
            case 'title':
                fontSize = isInsideGroup ? 24 : 32;
                break;
            case 'subtitle':
                fontSize = isInsideGroup ? 16 : 22;
                break;
            case 'body':
                fontSize = isInsideGroup ? 13 : 16;
                break;
            case 'caption':
                fontSize = isInsideGroup ? 11 : 12;
                break;
            default:
                fontSize = isInsideGroup ? 14 : 16; // Default body text size
        }

        if (text.fontSize && text.fontSize < 8) {
            console.warn(`[SlideProcessor] Font size too small (${text.fontSize}px), using ${fontSize}px for ${text.textType || 'text'}`);
        }
    }

    // Honor AI-specified lineHeight or use sensible default based on textType
    let lineHeight = text.lineHeight;
    if (!lineHeight || lineHeight < 1 || lineHeight > 2) {
        // Default lineHeight based on textType
        switch (text.textType) {
            case 'title':
                lineHeight = 1.2; // Tighter for titles
                break;
            case 'subtitle':
                lineHeight = 1.3;
                break;
            case 'body':
            case 'bullet':
                lineHeight = 1.4;
                break;
            default:
                lineHeight = 1.4;
        }
    }

    let validatedText = {
        ...text,
        // CRITICAL: Normalize text content for canvas renderer
        // AI sends 'text' field, expandCard/expandNumberedStep send 'content' field
        // Canvas renderer reads 'content' — fallback to 'text' prop if content missing
        content: text.content || text.text || '',
        x: clamp(text.x || 0, 0, CANVAS_WIDTH),
        y: clamp(text.y || 0, 0, CANVAS_HEIGHT),
        // Default width logic:
        // 1. If width is provided, use it (clamped to canvas edge).
        // 2. If NOT provided, default to remaining space (Canvas Width - X - Padding).
        //    Previously defaulted to 200px, which caused titles to wrap aggressively.
        width: Math.min(
            text.width || (CANVAS_WIDTH - (text.x || 50) - 50),
            CANVAS_WIDTH - (text.x || 0)
        ),
        height: Math.min(text.height || 50, CANVAS_HEIGHT - (text.y || 0)),
        fontSize: clamp(fontSize, isInsideGroup ? 9 : 10, 72), // Allow smaller for card children
        fontWeight: text.fontWeight || 'normal',
        // COLOR NORMALIZATION: 
        // AI sometimes sends 'fontColor', 'color', or 'fill'.
        // We normalize to 'fill' (Fabric default) AND 'color' (our convention)
        // Default to #1f2937 (dark gray) if absolutely no color is provided to prevent warnings
        fill: text.fill || text.color || text.fontColor || '#1f2937',
        color: text.color || text.fontColor || text.fill || '#1f2937',
        textAlign: text.textAlign || 'left',
        lineHeight: lineHeight,
        opacity: clamp(text.opacity ?? 1, 0, 1),
    };

    if (!validatedText.fill) {
        console.warn(`[SlideProcessor] ⚠️ Text element ${validatedText.id} has NO COLOR! (Input: ${JSON.stringify({ fill: text.fill, color: text.color, fontColor: text.fontColor })})`);
    } else if (text.fontColor || text.color) {
        console.log(`[SlideProcessor] 🎨 Normalized text color for ${validatedText.id}: ${validatedText.fill}`);
    }

    // Auto-expand width for text that doesn't fit
    // Instead of shrinking font, expand the textbox width to fit content
    validatedText = autoExpandTextWidth(validatedText);

    // ROOT CAUSE FIX: Compute accurate rendered height matching Fabric.js Textbox behavior
    // AI often sends height that is too small (or omits it → defaults to 50px).
    // Fabric.Textbox ignores height and grows vertically as needed, so the stored
    // height must reflect actual render size or fixTextOverlaps makes wrong decisions.
    const content = validatedText.content || '';
    if (content.length > 0) {
        const charWidthRatio = 0.48; // Average char width as fraction of fontSize (proportional fonts avg ~0.45-0.50)
        const declaredHeight = text.height || 50; // original AI-specified height (before clamping)
        const isConstrainedSlot = validatedText.width <= 300 && declaredHeight <= 200 && text.height;
        
        const estimateHeight = (fs) => {
            const cpl = Math.max(1, Math.floor(validatedText.width / (fs * charWidthRatio)));
            const contentLines = content.split('\n');
            let lines = 0;
            for (const line of contentLines) {
                lines += Math.max(1, Math.ceil((line.length || 1) / cpl));
            }
            return Math.ceil(lines * fs * validatedText.lineHeight);
        };
        
        const estimatedRenderHeight = estimateHeight(validatedText.fontSize);
        
        if (estimatedRenderHeight > validatedText.height) {
            if (isConstrainedSlot) {
                // CONSTRAINED SLOT: Shrink font to fit instead of expanding height.
                // These are small boxes (stat cards, step columns) where expanding height
                // would cause text to visually overflow into neighboring elements.
                let newFs = validatedText.fontSize;
                const minFs = validatedText.textType === 'title' ? 18 : 9;
                while (newFs > minFs && estimateHeight(newFs) > declaredHeight) {
                    newFs--;
                }
                if (newFs < validatedText.fontSize) {
                    console.log(`[SlideProcessor] 📐 Constrained slot font shrink for ${validatedText.id}: ${validatedText.fontSize}px → ${newFs}px to fit ${validatedText.width}x${declaredHeight}px`);
                    validatedText.fontSize = newFs;
                    // Recalculate height with new font size
                    validatedText.height = Math.max(declaredHeight, estimateHeight(newFs));
                } else {
                    validatedText.height = estimatedRenderHeight;
                }
            } else {
                // UNCONSTRAINED: Expand height as before (wide text boxes, full-width content)
                console.log(`[SlideProcessor] 📐 Height correction for ${validatedText.id}: ${validatedText.height}px → ${estimatedRenderHeight}px`);
                validatedText.height = estimatedRenderHeight;
            }
        }
    }

    return validatedText;
}

/**
 * Validate and normalize a shape element
 */
function validateShapeElement(shape) {
    return {
        ...shape,
        x: clamp(shape.x || 0, 0, CANVAS_WIDTH),
        y: clamp(shape.y || 0, 0, CANVAS_HEIGHT),
        width: Math.min(shape.width || 100, CANVAS_WIDTH - (shape.x || 0)),
        height: Math.min(shape.height || 100, CANVAS_HEIGHT - (shape.y || 0)),
        fill: shape.fill || '#3B82F6',
        stroke: shape.stroke || 'none',
        strokeWidth: shape.strokeWidth || 0,
        rx: shape.rx || 0,
        ry: shape.ry || shape.rx || 0,
        opacity: clamp(shape.opacity ?? 1, 0, 1),
    };
}

/**
 * Validate and normalize an image placeholder
 */
function validateImagePlaceholder(img) {
    return {
        ...img,
        x: clamp(img.x || 0, 0, CANVAS_WIDTH),
        y: clamp(img.y || 0, 0, CANVAS_HEIGHT),
        width: Math.min(img.width || 300, CANVAS_WIDTH - (img.x || 0)),
        height: Math.min(img.height || 200, CANVAS_HEIGHT - (img.y || 0)),
        zIndex: img.zIndex ?? 20,
        opacity: clamp(img.opacity ?? 1, 0, 1),
    };
}

/**
 * Validate and normalize an image element
 */
function validateImageElement(img) {
    return {
        ...img,
        x: clamp(img.x || 0, 0, CANVAS_WIDTH),
        y: clamp(img.y || 0, 0, CANVAS_HEIGHT),
        width: Math.min(img.width || 300, CANVAS_WIDTH - (img.x || 0)),
        height: Math.min(img.height || 200, CANVAS_HEIGHT - (img.y || 0)),
        zIndex: img.zIndex ?? 20,
        opacity: clamp(img.opacity ?? 1, 0, 1),
    };
}

/**
 * Utility: Clamp a value between min and max
 */
function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

/**
 * Process multiple slides (e.g., entire presentation)
 */
export function processSlides(slides) {
    if (!Array.isArray(slides)) return slides;
    return slides.map(processSlide);
}

/**
 * Quick validation check for AI output
 */
export function validateAIOutput(aiOutput) {
    const errors = [];

    if (!aiOutput) {
        errors.push('Empty AI output');
        return { valid: false, errors };
    }

    if (!aiOutput.elements || !Array.isArray(aiOutput.elements)) {
        errors.push('Missing or invalid elements array');
    }

    if (!aiOutput.backgroundColor) {
        errors.push('Missing backgroundColor');
    }

    return {
        valid: errors.length === 0,
        errors,
    };
}

// ==================== TEMPLATE-BASED PROCESSING ====================

import { SLIDE_TEMPLATES, applyStyleToTemplate } from './slideTemplates';

/**
 * Process a slide using template-based slot system
 * AI provides slot content, positions come from template
 * 
 * @param {Object} aiSlotData - AI output with { template: 'three_cards', slots: { card1_title: { content: 'text' }, ... } }
 * @param {Object} style - Presentation style with colors
 * @returns {Object} - Complete slide with positioned elements
 */
export function processTemplateSlide(aiSlotData, style) {
    if (!aiSlotData || !aiSlotData.template) {
        console.warn('[TemplateProcessor] No template specified, falling back to legacy processing');
        return processSlide(aiSlotData);
    }

    const templateId = aiSlotData.template;
    const template = SLIDE_TEMPLATES[templateId];

    if (!template) {
        console.warn(`[TemplateProcessor] Template "${templateId}" not found, falling back to three_cards`);
        return processTemplateSlide({ ...aiSlotData, template: 'three_cards' }, style);
    }

    console.log(`[TemplateProcessor] Processing slide with template: ${templateId}`);

    // Apply style colors to template
    const styledTemplate = applyStyleToTemplate(template, style);
    const slotData = aiSlotData.slots || {};

    const elements = [];

    // Process each slot in template
    for (const [slotName, slot] of Object.entries(styledTemplate.slots)) {
        const aiContent = slotData[slotName] || {};
        const elementId = uniqueId('el');

        // Skip optional slots that have no content
        if (template.optionalSlots?.includes(slotName) && !aiContent.content && !aiContent.iconName && !aiContent.imageDescription) {
            // Only render if explicitly provided by AI or if it's a shape/decoration
            if (slot.type !== 'shape') continue;
        }

        switch (slot.type) {
            case 'text':
                elements.push(createTextFromSlot(slot, aiContent, elementId, slotName));
                break;

            case 'icon':
                if (aiContent.iconName) {
                    elements.push(createIconFromSlot(slot, aiContent, elementId));
                }
                break;

            case 'shape':
                elements.push(createShapeFromSlot(slot, elementId));
                break;

            case 'image_placeholder':
                elements.push(createImagePlaceholderFromSlot(slot, aiContent, elementId));
                break;
        }
    }

    return {
        template: templateId,
        backgroundColor: styledTemplate.backgroundColor || style?.slideBackground || '#ffffff',
        elements: elements,
    };
}

/**
 * Create text element from template slot + AI content
 */
function createTextFromSlot(slot, aiContent, id, slotName) {
    return {
        id,
        type: 'text',
        textType: slot.textType || 'body',
        content: aiContent.content || slot.content || '',
        x: slot.x,
        y: slot.y,
        width: slot.width,
        height: slot.height,
        fontSize: slot.fontSize || 20,
        fontWeight: slot.fontWeight || 'normal',
        fontStyle: slot.fontStyle || 'normal',
        textAlign: slot.textAlign || 'left',
        fill: slot.fill || '#111827',
        zIndex: slot.zIndex || 60,
    };
}

/**
 * Create icon element from template slot + AI content
 */
function createIconFromSlot(slot, aiContent, id) {
    return {
        id,
        type: 'icon',
        iconName: aiContent.iconName,
        x: slot.x,
        y: slot.y,
        width: slot.width || 56,
        height: slot.height || 56,
        size: slot.size || 56,
        fill: slot.fill || '#3B82F6',
        zIndex: slot.zIndex || 35,
    };
}

/**
 * Create shape element from template slot
 */
function createShapeFromSlot(slot, id) {
    return {
        id,
        type: 'shape',
        shapeType: slot.shapeType || 'rectangle',
        x: slot.x,
        y: slot.y,
        width: slot.width,
        height: slot.height,
        fill: slot.fill || '#f8fafc',
        stroke: slot.stroke,
        rx: slot.rx || 0,
        opacity: slot.opacity ?? 1,
        zIndex: slot.zIndex || 8,
    };
}

/**
 * Create image placeholder from template slot + AI content
 */
function createImagePlaceholderFromSlot(slot, aiContent, id) {
    return {
        id,
        type: 'image_placeholder',
        imageDescription: aiContent.imageDescription || 'Professional image',
        x: slot.x,
        y: slot.y,
        width: slot.width,
        height: slot.height,
        zIndex: slot.zIndex || 20,
    };
}

/**
 * Process slide with template (async version for icon prefetching)
 */
export async function processTemplateSlideAsync(aiSlotData, style) {
    const result = processTemplateSlide(aiSlotData, style);

    // Collect icon names for prefetching
    const iconNames = result.elements
        .filter(el => el.type === 'icon' && el.iconName)
        .map(el => el.iconName);

    if (iconNames.length > 0) {
        await prefetchIcons(iconNames);
    }

    // Re-process icons to add SVG paths
    for (const element of result.elements) {
        if (element.type === 'icon') {
            const iconName = element.iconName || element.name || element.icon || element.content;
            if (iconName) {
                const svg = await mapIconToPathAsync(iconName);
                element.svgPath = svg;
            }
        }
    }

    return result;
}

export default {
    processSlide,
    processSlideAsync,
    processSlides,
    processTemplateSlide,
    processTemplateSlideAsync,
    validateAIOutput,
};
