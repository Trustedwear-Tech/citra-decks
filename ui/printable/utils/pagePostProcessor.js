// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

/**
 * Page Post-Processor for Printables (A4 Format)
 * 
 * Transforms AI-generated page data into renderable elements for Fabric.js.
 * Optimized for A4 portrait format (794x1123 pixels at 96 DPI)
 * 
 * Handles:
 * - Cards: Expands into shape + icon + text elements
 * - Icons: Maps semantic names to SVG paths
 * - Numbered Steps: Creates circle + number + label
 * - Validation: Ensures positions and sizes are within A4 page bounds
 */

import { mapIconToPath, mapIconToPathAsync, prefetchIcons, getIconSVG } from '../../composer/utils/iconMapper';

// Monotonic counter for generating unique element IDs (avoids Date.now() collisions)
let _elementIdCounter = 0;
function uniqueId(prefix = 'auto') {
    return `${prefix}_${Date.now()}_${_elementIdCounter++}`;
}

// A4 at 96 DPI dimensions (portrait orientation)
const PAGE_WIDTH = 794;
const PAGE_HEIGHT = 1123;

// Scale factor from 16:9 slide (540px height) to A4 (1123px height)
const A4_SCALE_FACTOR = PAGE_HEIGHT / 540; // ~2.08

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
            console.warn(`[PageProcessor] ⚠️ Missing ID for element type '${el.type}', generated: ${elementId}`);
        }

        // Z-Index Logic (Critical for Visibility)
        // FIX: Default to 50 (Text level) if unknown, rather than 0
        // This ensures text inside cards (which lacks explicit zIndex) sits ABOVE shapes (zIndex 5)
        const intrinsicZ = el.zIndex !== undefined ? el.zIndex : (Z_INDEX_DEFAULTS[el.type] ?? 50);
        const absZ = intrinsicZ + parentZ;

        // Dimension Inheritance Logic (New Feature)
        // If element lacks explicit width/height, and belongs to a sized container, inherit constraints.
        // This prevents children from exploding to full page width (794px) when inside a Column (e.g. 400px).
        let effectiveWidth = el.width;
        let effectiveHeight = el.height;

        if (parentWidth && (effectiveWidth === undefined || effectiveWidth === null)) {
            // Child width = Parent Width - Child's Relative X (padding logic)
            // Ensure strictly positive
            const calculatedWidth = Math.max(10, parentWidth - (el.x || 0));
            effectiveWidth = calculatedWidth;
            console.log(`[PageProcessor] 📏 Inheriting width for ${elementId}: Parent=${parentWidth}, AbsX=${absX} -> NewWidth=${effectiveWidth}`);
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
                console.log(`[PageProcessor] \u{1F3A8} No fill on text ${elementId}, parent bg=${parentBgColor} -> ${flatEl.fill}`);
            } else if (hasLowContrast(textFill, parentBgColor)) {
                flatEl.fill = isColorDark(parentBgColor) ? '#FFFFFF' : '#111827';
                console.log(`[PageProcessor] \u{1F3A8} Low-contrast text fix ${elementId}: ${textFill} vs ${parentBgColor} -> ${flatEl.fill}`);
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
                console.log(`[PageProcessor] 📋 Pre-extracted title for ${el.id || el.type}: "${el.title.substring(0, 40)}..."`);

                // Also extract title color if missing — preserves AI-specified text color
                if (!el.titleColor) {
                    el.titleColor = boldChild.color || boldChild.fill;
                    if (el.titleColor) {
                        console.log(`[PageProcessor] 🎨 Pre-extracted titleColor for ${el.id || el.type}: ${el.titleColor}`);
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
                    console.log(`[PageProcessor] 📋 Pre-extracted description for ${el.id || el.type}: "${el.description.substring(0, 40)}..."`);

                    // Also extract description color if missing
                    if (!el.descriptionColor) {
                        el.descriptionColor = descChildren[0].color || descChildren[0].fill;
                        if (el.descriptionColor) {
                            console.log(`[PageProcessor] 🎨 Pre-extracted descriptionColor for ${el.id || el.type}: ${el.descriptionColor}`);
                        }
                    }
                }
            }

            // Extract icon if missing
            if (!el.iconName && iconChildren.length > 0) {
                el.iconName = iconChildren[0].iconName || iconChildren[0].name;
                console.log(`[PageProcessor] 📋 Pre-extracted icon for ${el.id || el.type}: ${el.iconName}`);
            }

            // Extract icon color if missing — AI sends color on icon children (e.g., "color": "#C5A059")
            if (!el.iconColor && iconChildren.length > 0) {
                el.iconColor = iconChildren[0].color || iconChildren[0].fill;
                if (el.iconColor) {
                    console.log(`[PageProcessor] 🎨 Pre-extracted iconColor for ${el.id || el.type}: ${el.iconColor}`);
                }
            }
        }

        // Recurse into children to handle nested structures
        if (el.children && Array.isArray(el.children)) {
            preExtractCardContent(el.children);
        }
    }
}

// Resolve the page's EFFECTIVE background. Dark themes often ship
// backgroundColor undefined (or white) while a full-bleed dark rect at the
// back provides the real background — assuming '#FFFFFF' then makes the
// contrast passes flip perfectly-readable white text to near-black, i.e.
// invisible on the actually-dark page ("text disappeared" bug). Prefer a
// non-white explicit backgroundColor; else the fill of a shape covering ~the
// whole page at the lowest z; else fall back to white as before.
function resolveEffectiveBackground(pageData) {
    const explicit = pageData.backgroundColor;
    if (explicit && typeof explicit === 'string' && explicit.toUpperCase() !== '#FFFFFF' && explicit.toLowerCase() !== 'white') {
        return explicit;
    }
    let best = null;
    for (const el of (pageData.elements || [])) {
        if (!el || typeof el !== 'object') continue;
        if (el.type !== 'shape' && el.type !== 'rect') continue;
        const fill = el.fill || el.backgroundColor;
        if (!fill || typeof fill !== 'string' || !fill.startsWith('#')) continue;
        const w = Number(el.width) || 0, h = Number(el.height) || 0;
        const x = Number(el.x) || 0, y = Number(el.y) || 0;
        if (w >= PAGE_WIDTH * 0.9 && h >= PAGE_HEIGHT * 0.9 && x <= PAGE_WIDTH * 0.05 && y <= PAGE_HEIGHT * 0.05) {
            const z = Number(el.zIndex) || 0;
            if (!best || z < best.z) best = { fill, z };
        }
    }
    if (best) return best.fill;
    return explicit || '#FFFFFF';
}

/**
 * Main processing function for page data (A4 format)
 */
export function processPage(pageData) {
    if (!pageData || !pageData.elements) {
        console.warn('[PageProcessor] Invalid page data');
        return pageData;
    }

    // STEP -1: Pre-extract children content onto cards BEFORE flattening
    // This ensures card title/description/iconName survive the flatten + dedup pipeline
    preExtractCardContent(pageData.elements);

    // STEP 0: Flatten Hierarchy (with parent-aware text visibility fix)
    const backgroundColor = resolveEffectiveBackground(pageData);
    const flatElements = flattenHierarchy(pageData.elements, 0, 0, 0, null, null, null, backgroundColor);

    console.log(`[PageProcessor] Hierarchy Flattened: ${pageData.elements.length} root -> ${flatElements.length} flat elements`);

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
            console.log(`[PageProcessor] 🗑️ Dropping flattened child ${el.id} (parent ${el.parentId} will be expanded)`);
            return false;
        }
        return true;
    });

    // STEP 0.6: Geometric containment contrast correction.
    // See slidePostProcessor.js for the rationale — same applies to A4 templates
    // like exec_pg_cover / exec_pg_sovereignty_dark / exec_pg_closing_dark
    // where flat sibling layouts hide dark card bg's from the parent-child
    // inline contrast fix and leave white text invisible on a dark card.
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
                    console.log(`[PageProcessor] 🎨 Geometric no-fill text ${el.id}: on shape ${bestShape.id} (${effectiveBg}) -> ${el.fill}`);
                    return;
                }
                if (hasLowContrast(textFill, effectiveBg)) {
                    const newFill = isColorDark(effectiveBg) ? '#FFFFFF' : '#111827';
                    if (newFill.toLowerCase() !== textFill.toLowerCase()) {
                        console.log(`[PageProcessor] 🎨 Geometric contrast fix ${el.id}: ${textFill} on shape ${bestShape.id} (${effectiveBg}) -> ${newFill}`);
                        el.fill = newFill;
                    }
                }
            });
        }
    } catch (err) {
        console.warn('[PageProcessor] Geometric contrast pass failed (non-fatal):', err);
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
    console.log('🔍 [PageProcessor] Text positions (Pre-Fix):', JSON.stringify(textDebug));

    // Fix overlapping text elements (text vs text)
    // ENABLED (Smart Mode): Fixes loose lists but respects text inside Cards/Shapes
    fixTextOverlaps(processedElements);

    // Fix intra-group overlaps (text within same parent card/shape)
    fixIntraGroupOverlaps(processedElements);

    // Fix overlaps between expanded numbered_step / card groups.
    // fixTextOverlaps() skips parentId elements; fixIntraGroupOverlaps() only handles same-group.
    // This pass catches cross-step overlaps (e.g. step 2 desc bleeding into step 3 circle/title).
    fixInterStepOverlaps(processedElements);

    // Fix invisible top-level text (text color same as page background)
    fixInvisibleTopLevelText(processedElements, backgroundColor);

    // Sort by z-index (painter's algorithm - low to high)
    processedElements.sort((a, b) => (a.zIndex ?? 50) - (b.zIndex ?? 50));

    return {
        ...pageData,
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

    const MIN_GAP = 10; // Moderate gap for A4 format (was 15 — caused cascading ~100px shifts)
    const SAFE_BOTTOM = PAGE_HEIGHT - 43; // Don't push text below safe zone on A4 page

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
                    console.log(`[PageProcessor] ⚠️ Fixing text overlap: ${curr.id} moved from y:${currTop} to y:${newY}`);
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

    const MIN_GAP = 8;

    for (const [parentId, groupElements] of Object.entries(groups)) {
        if (groupElements.length < 2) continue;

        // Sort by Y position
        groupElements.sort((a, b) => (a.y || 0) - (b.y || 0));

        const parentBg = parentBgs[parentId];
        const parentBottom = parentBg ? (parentBg.y || 0) + (parentBg.height || 9999) : PAGE_HEIGHT;

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
                    console.log(`[PageProcessor] 🔧 Intra-group fix: ${curr.id} y:${currTop} → y:${newY} (parent: ${parentId})`);
                    curr.y = newY;
                } else {
                    // Can't move down — shrink font instead
                    const availableHeight = Math.max(20, parentBottom - currTop - 10);
                    if (curr.height && curr.height > availableHeight) {
                        const ratio = availableHeight / curr.height;
                        const newFontSize = Math.max(10, Math.floor((curr.fontSize || 16) * Math.sqrt(ratio)));
                        console.log(`[PageProcessor] 🔧 Intra-group font shrink: ${curr.id} ${curr.fontSize}px → ${newFontSize}px`);
                        curr.fontSize = newFontSize;
                    }
                }
            }
        }
    }
}

/**
 * Fix overlaps between different expanded step/card groups.
 * fixTextOverlaps() skips elements with parentId (protected).
 * fixIntraGroupOverlaps() only handles elements within the SAME parent.
 * This function catches cross-group overlaps, e.g. step 2's description
 * bleeding into step 3's circle/title after height expansion.
 */
function fixInterStepOverlaps(elements) {
    const MIN_GAP = 15; // Slightly larger gap for A4 pages
    const SAFE_BOTTOM = PAGE_HEIGHT - 53; // Don't push groups past safe zone

    // Identify all unique step/card group parent IDs
    const groupMap = {};
    for (const el of elements) {
        if (!el.parentId) continue;
        if (!groupMap[el.parentId]) groupMap[el.parentId] = [];
        groupMap[el.parentId].push(el);
    }

    if (Object.keys(groupMap).length < 2) return;

    // Compute bounding box for each group.
    // Use the _bg shape's bounds as the authoritative group height.
    // validateTextElement inflates text heights for text-vs-text overlap detection,
    // but using those inflated heights here causes cascading pushdowns that push
    // subsequent card groups off-page.
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
        if (prev.maxX <= curr.minX || curr.maxX <= prev.minX) continue;

        if (curr.minY < prev.maxY + MIN_GAP) {
            let shift = (prev.maxY + MIN_GAP) - curr.minY;

            // Cap shift so no element goes past SAFE_BOTTOM
            const wouldMaxY = curr.maxY + shift;
            if (wouldMaxY > SAFE_BOTTOM) {
                const cappedShift = Math.max(0, SAFE_BOTTOM - curr.maxY);
                if (cappedShift < shift) {
                    console.log(`[PageProcessor] \u26a0\ufe0f Inter-step shift capped: ${shift}px \u2192 ${cappedShift}px (page bounds)`);
                    shift = cappedShift;
                }
            }

            if (shift > 0) {
                console.log(`[PageProcessor] \ud83d\udd27 Inter-step overlap: group ${curr.parentId} shifted down by ${shift}px`);
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
 * Fix invisible top-level text where text fill is nearly identical to the page background.
 * flattenHierarchy handles parent-aware fixes for children inside cards/groups,
 * but top-level text (no parentId) can still be invisible if AI picks a fill
 * that matches the page backgroundColor.
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
            console.log(`[PageProcessor] 🎨 No fill on top-level text ${el.id}, bg=${backgroundColor} → ${el.fill}`);
        } else if (hasLowContrast(textFill, backgroundColor)) {
            // Text color has low contrast with page background — flip
            el.fill = bgIsDark ? '#FFFFFF' : '#111827';
            el.color = el.fill;
            console.log(`[PageProcessor] 🎨 Low-contrast top-level text fix ${el.id}: ${textFill} vs ${backgroundColor} → ${el.fill}`);
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
 * Detect and fix text elements overlapping with shapes/icons.
 * Adjusts text position or reduces font size to prevent overlap.
 */
function fixTextShapeOverlaps(elements) {
    const textElements = elements.filter(el => el.type === 'text');
    const shapeElements = elements.filter(el =>
        el.type === 'shape' || el.type === 'icon' || el.type === 'numbered_step'
    );

    if (textElements.length === 0 || shapeElements.length === 0) return;

    const SAFE_GAP = 25; // Larger gap for A4 format
    const MIN_FONT_SIZE = 14; // Slightly larger min for A4 readability

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
                    // Only move if it won't push text off page
                    if (newY + (text.height || 50) <= PAGE_HEIGHT) {
                        console.log(`[PageProcessor] ⚠️ Fixing text-shape overlap: ${text.id} moved from y:${textTop} to y:${newY}`);
                        text.y = newY;
                        continue; // Fixed, move to next shape
                    }
                }

                // If can't move, try reducing font size
                const currentFontSize = text.fontSize || 22;
                if (currentFontSize > MIN_FONT_SIZE) {
                    const newFontSize = Math.max(MIN_FONT_SIZE, currentFontSize - 2);
                    // Proportionally reduce height
                    const heightRatio = newFontSize / currentFontSize;
                    const newHeight = Math.ceil((text.height || 50) * heightRatio);

                    console.log(`[PageProcessor] ⚠️ Reducing font to avoid overlap: ${text.id} fontSize ${currentFontSize}px -> ${newFontSize}px`);
                    text.fontSize = newFontSize;
                    text.height = newHeight;
                }
            }
        }
    }
}

/**
 * Auto-expand text width to fit content instead of wrapping early
 * ONLY applies to main page titles (large font, near top of page, NOT inside cards)
 * Keeps sub-headers, card text, and body text at their original width
 */
function autoExpandTextWidth(element) {
    if (element.type !== 'text' || !element.content) return element;

    // NEVER expand text inside cards - they have parentId set during flattening
    if (element.parentId) return element;

    const fontSize = element.fontSize || 22;
    const y = element.y || 0;
    
    // Only expand main page titles: large font (>= 32px) AND at very top (y < 150)
    // Adjusted for A4's taller format (was y < 100 for 16:9 slides)
    const isTitle = fontSize >= 32 && y < 150;
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
    
    // Calculate maximum available width from x position to page edge (with padding)
    const rightPadding = 50; // Leave some padding from right edge
    const maxAvailableWidth = PAGE_WIDTH - x - rightPadding;
    
    // Current width from AI
    const currentWidth = element.width || 200;
    
    // If estimated width exceeds current width, expand to fit (up to max available)
    if (estimatedWidthNeeded > currentWidth) {
        const newWidth = Math.min(estimatedWidthNeeded + 20, maxAvailableWidth); // +20 for safety margin
        
        if (newWidth > currentWidth) {
            console.log(`[PageProcessor] 📐 Auto-expanding TITLE width for ${element.id}: ${currentWidth}px -> ${newWidth}px (content needs ~${Math.round(estimatedWidthNeeded)}px)`);
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

    // Character limits by text type (adjusted for A4 format - more space available)
    const limits = {
        title: { maxChars: 80, defaultSize: 42, minSize: 26 },
        subtitle: { maxChars: 120, defaultSize: 26, minSize: 14 },
        body: { maxChars: 350, defaultSize: 18, minSize: 12 },
        bullet: { maxChars: 400, defaultSize: 16, minSize: 12 },
        caption: { maxChars: 200, defaultSize: 14, minSize: 11 },
    };

    const config = limits[textType] || limits.body;
    let fontSize = element.fontSize || config.defaultSize;
    const lineHeight = element.lineHeight || 1.4;

    // If content exceeds recommended length, reduce font size proportionally
    if (contentLength > config.maxChars) {
        const overflowRatio = config.maxChars / contentLength;
        const proposedSize = Math.floor(fontSize * Math.sqrt(overflowRatio));
        fontSize = Math.max(config.minSize, proposedSize);

        console.log(`[PageProcessor] 📏 Auto-adjusting font: ${element.id} has ${contentLength} chars (max ${config.maxChars}), reducing ${element.fontSize || config.defaultSize}px -> ${fontSize}px`);
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

        console.log(`[PageProcessor] 📏 Height overflow: ${element.id} needs ${estimatedHeight}px but has ${height}px, reducing to ${fontSize}px`);
    }

    return {
        ...element,
        fontSize: fontSize,
        lineHeight: element.lineHeight || lineHeight,
    };
}

/**
 * Process a page with async icon fetching (use for initial load)
 * @param {Object} pageData - Raw page data from AI
 * @returns {Promise<Object>} - Processed page with icons prefetched
 */
export async function processPageAsync(pageData) {
    if (!pageData || !pageData.elements) {
        console.warn('[PageProcessor] Invalid page data');
        return pageData;
    }

    // Collect all icon names for prefetching
    // FIX: AI may send icon name in 'iconName', 'name', or 'content' property
    const iconNames = [];
    for (const element of pageData.elements) {
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
    return processPage(pageData);
}

/**
 * Process a single element, expanding complex types
 */
function processElement(element, pageBgColor) {
    if (!element || !element.type) return null;

    switch (element.type) {
        case 'card':
            return expandCard(element);
        case 'numbered_step':
            return expandNumberedStep(element, pageBgColor);
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
            // Inline SVG drawing — handed off to the Fabric.js layer
            // unchanged. Parity with slidePostProcessor; needed so the
            // LLM can ship SVG-led layouts on the printable side too.
            return element;
        default:
            console.warn(`[PageProcessor] Unknown element type: ${element.type}`);
            return element;
    }
}

/**
 * Expand a card element into its component parts
 * Card = Background shape + Icon + Title text + Description text
 * Dimensions scaled for A4 format
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

    // Layout Mode Decision (adjusted thresholds for A4)
    // If card is short (< 220px) OR wide (> 400px), prefer horizontal layout
    const cardHeight = parseInt(card.height || 350, 10);
    const cardWidth = parseInt(card.width || 300, 10);
    const cardX = parseInt(card.x || 50, 10);
    const cardY = parseInt(card.y || 150, 10);

    const isCompactHeight = cardHeight < 220;
    const isWide = cardWidth > 400;
    const useHorizontalLayout = isCompactHeight || isWide;

    console.log(`[PageProcessor] Expanding card ${baseId}: ${cardWidth}x${cardHeight} at (${cardX}, ${cardY}) (Horizontal: ${useHorizontalLayout}) keys: ${Object.keys(card).join(',')}`);
    if (!card.title) console.warn(`[PageProcessor] ⚠️ Card ${baseId} missing title!`);
    if (!card.description) console.warn(`[PageProcessor] ⚠️ Card ${baseId} missing description!`);

    // Card background shape (lowest z-index within card)
    elements.push({
        id: `${baseId}_bg`,
        type: 'shape',
        shapeType: 'rectangle',
        x: card.x || 50,
        y: card.y || 150,
        width: card.width || 300,
        height: card.height || 350,
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
        const padding = 15;
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
        const textWidth = (card.width || 300) - (textStartX - (card.x || 50)) - padding;

        let currentTextY = iconY;

        // Adaptive title font: default 16px, min 12px for compact cards
        const hTitleFontSize = card.titleFontSize || Math.min(16, Math.max(12, Math.floor(cardHeight * 0.12)));
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
            const availableDescH = (card.height || 350) - (currentTextY - (card.y || 150)) - padding;
            let hDescFontSize = card.descriptionFontSize || 13;
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
        const vTitleFontSize = card.titleFontSize || Math.min(16, Math.max(12, Math.floor(cardHeight * 0.09)));
        const vTitleLineH = 1.2;
        // Estimate title height (may wrap)
        const titleTextWidth = (card.width || 300) - (vPadding * 2);
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
                zIndex: baseZIndex + 20,
                parentId: baseId,
            });
        }

        // Card title
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
                zIndex: baseZIndex + 40,
                parentId: baseId,
            });
        }

        // Card description — adaptive font to fit remaining card space
        if (card.description) {
            const availableDescH = cardHeight - (descY - (card.y || 150)) - vPadding;
            let vDescFontSize = card.descriptionFontSize || 12;
            const vDescLineH = 1.3;
            // Estimate lines and shrink if needed
            const descCharsPerLine = Math.max(1, Math.floor(titleTextWidth / (vDescFontSize * 0.55)));
            const descLines = Math.ceil(descText.length / descCharsPerLine);
            const estDescH = descLines * vDescFontSize * vDescLineH;
            if (estDescH > availableDescH && availableDescH > 0) {
                vDescFontSize = Math.max(9, Math.floor(vDescFontSize * Math.sqrt(availableDescH / estDescH)));
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
                zIndex: baseZIndex + 45,
                parentId: baseId,
            });
        }
    }

    // Tag all expanded elements with the card's background for canvas-level contrast safety net
    return elements.map(el => el.type === 'text' ? { ...el, parentBgColor: cardBg } : el);
}

/**
 * Expand a numbered step into circle + number + label
 * Dimensions scaled for A4 format
 */
function expandNumberedStep(step, pageBgColor) {
    const elements = [];
    const baseId = step.id || uniqueId('step');
    // FIX: Cap circle size to fit within step's declared height (prevents circle overflow)
    const stepHeight = step.height || 80;
    const maxCircleSize = Math.min(stepHeight * 0.7, 60); // 70% of height or 60px max
    const size = step.size || maxCircleSize;
    const x = step.x || 100;
    const y = step.y || 200;

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
    // the circle, on whatever background is behind the step element (page bg or parent shape bg)
    const effectiveBg = pageBgColor || '#1E293B'; // Assume dark if unknown
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
        // Dynamic width: Use provided width OR remaining page space (minus padding)
        const defaultWidth = PAGE_WIDTH - textX - 60;
        const availableWidth = step.width ? (step.width - size - 20) : defaultWidth;

        // Adaptive title font: scale with step height, max 18px
        const sTitleFontSize = step.labelFontSize || Math.min(18, Math.max(13, Math.floor(stepHeight * 0.2)));
        const sTitleLineH = 1.2;
        const sTitleHeight = Math.ceil(sTitleFontSize * sTitleLineH) + 4;

        let currentY = y + 4; // Slight top padding relative to circle

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
            let sDescFontSize = step.descriptionFontSize || 13;
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
        if (titleContent) {
            const centerX = x + (size / 2);
            const textWidth = step.width || Math.min(500, PAGE_WIDTH - x);
            const textX = centerX - (textWidth / 2);

            elements.push({
                id: `${baseId}_label`,
                type: 'text',
                textType: 'subtitle',
                content: titleContent,
                x: textX,
                y: y + size + 15,
                width: textWidth,
                height: 30,
                fontSize: step.labelFontSize || 16,
                fontWeight: step.labelFontWeight || 'bold',
                fill: safeTitleColor,
                textAlign: 'center',
                lineHeight: 1.2,
                parentId: baseId,
            });
        }
    }

    // Tag all expanded step elements with the effective background for canvas-level contrast safety net
    return elements.map(el => el.type === 'text' ? { ...el, parentBgColor: effectiveBg } : el);
}

/**
 * Process an icon element, mapping the name to a path
 */
function processIcon(icon) {
    // FIX: AI JSON may send icon name in different properties:
    // - 'iconName' (internal code convention)
    // - 'name' (some AI formats)
    // - 'icon' (AI frequently uses this, e.g. {"icon": "lightbulb"})
    // - 'content' (card children icons use this)
    // Support all by checking in order of preference
    const iconNameToResolve = icon.iconName || icon.name || icon.icon || icon.content;
    
    if (!iconNameToResolve) {
        console.warn('[PageProcessor] ⚠️ Icon element missing name/iconName/content:', icon);
    }
    
    const { path, name } = mapIconToPath(iconNameToResolve);

    // FIX: Normalize icon size — AI sometimes sends width/height instead of size
    const iconSize = icon.size || icon.width || icon.height || 36;

    return {
        ...icon,
        // FIX: Normalize to 'iconName' for internal use while preserving 'name' from AI
        iconName: iconNameToResolve,
        icon: iconNameToResolve, // Keep both for compat
        resolvedIconName: name,
        svgPath: path,
        // Ensure required properties
        x: clamp(icon.x || 0, 0, PAGE_WIDTH),
        y: clamp(icon.y || 0, 0, PAGE_HEIGHT),
        size: iconSize,
        width: iconSize, // Normalize for bounding box calculations
        height: iconSize,
        // FIX: AI JSON uses 'color' property, internal code uses 'fill'
        fill: icon.fill || icon.color || '#ffffff',
    };
}

/**
 * Validate and normalize a text element
 * Font sizes optimized for A4 format
 */
function validateTextElement(text) {
    // Determine appropriate font size based on textType if not provided
    // Font sizes scaled up for A4 format (more readable on larger page)
    let fontSize = text.fontSize;

    // Use smaller defaults for elements inside cards/groups (parentId set)
    const isInsideGroup = !!text.parentId;

    if (!fontSize || fontSize < 8) {
        // Use sensible defaults based on textType
        // Elements inside cards/groups get smaller defaults to prevent overflow
        switch (text.textType) {
            case 'title':
                fontSize = isInsideGroup ? 28 : 42;
                break;
            case 'subtitle':
                fontSize = isInsideGroup ? 16 : 26;
                break;
            case 'body':
                fontSize = isInsideGroup ? 13 : 18;
                break;
            case 'caption':
                fontSize = isInsideGroup ? 12 : 14;
                break;
            default:
                fontSize = isInsideGroup ? 14 : 18;
        }

        if (text.fontSize && text.fontSize < 8) {
            console.warn(`[PageProcessor] Font size too small (${text.fontSize}px), using ${fontSize}px for ${text.textType || 'text'}`);
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
                lineHeight = 1.5; // Slightly more for A4 readability
                break;
            default:
                lineHeight = 1.4;
        }
    }

    let validatedText = {
        ...text,
        // CRITICAL: Normalize text content property for canvas renderer
        // AI sends 'text' field, expandCard/expandNumberedStep send 'content' field
        // Canvas renderer reads 'content' — fallback to 'text' prop if content missing
        content: text.content || text.text || '',
        x: clamp(text.x || 0, 0, PAGE_WIDTH),
        y: clamp(text.y || 0, 0, PAGE_HEIGHT),
        // Default width logic:
        // 1. If width is provided, use it (clamped to page edge).
        // 2. If NOT provided, default to remaining space (Page Width - X - Padding).
        //    Previously defaulted to 200px, which caused titles to wrap aggressively.
        width: Math.min(
            text.width || (PAGE_WIDTH - (text.x || 50) - 50),
            PAGE_WIDTH - (text.x || 0)
        ),
        height: Math.min(text.height || 60, PAGE_HEIGHT - (text.y || 0)),
        fontSize: clamp(fontSize, isInsideGroup ? 9 : 12, 80), // Allow smaller for card children
        fontWeight: text.fontWeight || 'normal',
        // COLOR NORMALIZATION: 
        // AI sometimes sends 'fontColor', 'color', or 'fill'.
        // We normalize to 'fill' (Fabric default) AND 'color' (our convention)
        // Default to #1f2937 (dark gray) if absolutely no color is provided to prevent warnings
        fill: text.fill || text.color || text.fontColor || '#1f2937',
        color: text.color || text.fontColor || text.fill || '#1f2937',
        textAlign: text.textAlign || 'left',
        lineHeight: lineHeight,
    };

    if (!validatedText.fill) {
        console.warn(`[PageProcessor] ⚠️ Text element ${validatedText.id} has NO COLOR! (Input: ${JSON.stringify({ fill: text.fill, color: text.color, fontColor: text.fontColor })})`);
    } else if (text.fontColor || text.color) {
        console.log(`[PageProcessor] 🎨 Normalized text color for ${validatedText.id}: ${validatedText.fill}`);
    }

    // Auto-expand width for text that doesn't fit
    // Instead of shrinking font, expand the textbox width to fit content
    validatedText = autoExpandTextWidth(validatedText);

    // ROOT CAUSE FIX: Compute accurate rendered height matching Fabric.js Textbox behavior
    // AI often sends height that is too small (or omits it → defaults to 60px).
    // Fabric.Textbox ignores height and grows vertically as needed, so the stored
    // height must reflect actual render size or fixTextOverlaps makes wrong decisions.
    const content = validatedText.content || '';
    if (content.length > 0) {
        const charWidthRatio = 0.48; // Average char width as fraction of fontSize (proportional fonts avg ~0.45-0.50)
        const charsPerLine = Math.max(1, Math.floor(validatedText.width / (validatedText.fontSize * charWidthRatio)));
        const contentLines = content.split('\n');
        let totalLines = 0;
        for (const line of contentLines) {
            totalLines += Math.max(1, Math.ceil((line.length || 1) / charsPerLine));
        }
        const estimatedRenderHeight = Math.ceil(totalLines * validatedText.fontSize * validatedText.lineHeight);
        // Use the LARGER of AI-specified height and estimated render height
        if (estimatedRenderHeight > validatedText.height) {
            console.log(`[PageProcessor] 📐 Height correction for ${validatedText.id}: ${validatedText.height}px → ${estimatedRenderHeight}px (${totalLines} lines × ${validatedText.fontSize}px × ${validatedText.lineHeight})`);
            validatedText.height = estimatedRenderHeight;
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
        x: clamp(shape.x || 0, 0, PAGE_WIDTH),
        y: clamp(shape.y || 0, 0, PAGE_HEIGHT),
        width: Math.min(shape.width || 100, PAGE_WIDTH - (shape.x || 0)),
        height: Math.min(shape.height || 100, PAGE_HEIGHT - (shape.y || 0)),
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
        x: clamp(img.x || 0, 0, PAGE_WIDTH),
        y: clamp(img.y || 0, 0, PAGE_HEIGHT),
        width: Math.min(img.width || 400, PAGE_WIDTH - (img.x || 0)),
        height: Math.min(img.height || 300, PAGE_HEIGHT - (img.y || 0)),
        zIndex: img.zIndex ?? 20,
    };
}

/**
 * Validate and normalize an image element
 */
function validateImageElement(img) {
    return {
        ...img,
        x: clamp(img.x || 0, 0, PAGE_WIDTH),
        y: clamp(img.y || 0, 0, PAGE_HEIGHT),
        width: Math.min(img.width || 400, PAGE_WIDTH - (img.x || 0)),
        height: Math.min(img.height || 300, PAGE_HEIGHT - (img.y || 0)),
        zIndex: img.zIndex ?? 20,
    };
}

/**
 * Utility: Clamp a value between min and max
 */
function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

/**
 * Process multiple pages (e.g., entire printable document)
 */
export function processPages(pages) {
    if (!Array.isArray(pages)) return pages;
    return pages.map(processPage);
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

import { PAGE_TEMPLATES, applyStyleToTemplate } from '../printableTemplates';

/**
 * Process a page using template-based slot system
 * AI provides slot content, positions come from template
 * 
 * @param {Object} aiSlotData - AI output with { template: 'three_cards', slots: { card1_title: { content: 'text' }, ... } }
 * @param {Object} style - Document style with colors
 * @returns {Object} - Complete page with positioned elements
 */
export function processTemplatePage(aiSlotData, style) {
    if (!aiSlotData || !aiSlotData.template) {
        console.warn('[TemplateProcessor] No template specified, falling back to legacy processing');
        return processPage(aiSlotData);
    }

    const templateId = aiSlotData.template;
    const template = PAGE_TEMPLATES[templateId];

    if (!template) {
        console.warn(`[TemplateProcessor] Template "${templateId}" not found, falling back to bullets`);
        return processTemplatePage({ ...aiSlotData, template: 'bullets' }, style);
    }

    console.log(`[TemplateProcessor] Processing page with template: ${templateId}`);

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
        backgroundColor: styledTemplate.backgroundColor || style?.pageBackground || '#ffffff',
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
        fontSize: slot.fontSize || 22,
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
        width: slot.width || 64,
        height: slot.height || 64,
        size: slot.size || 64,
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
 * Process page with template (async version for icon prefetching)
 */
export async function processTemplatePageAsync(aiSlotData, style) {
    const result = processTemplatePage(aiSlotData, style);

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
    processPage,
    processPageAsync,
    processPages,
    processTemplatePage,
    processTemplatePageAsync,
    validateAIOutput,
};
