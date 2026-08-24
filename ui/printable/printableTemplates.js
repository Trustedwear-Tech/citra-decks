// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

/**
 * Page Templates for Printables - Predefined layouts with fixed slot positions
 * Optimized for A4 portrait format (794x1123 pixels at 96 DPI)
 * 
 * Each template defines:
 * - name: Display name for UI
 * - description: Short description
 * - thumbnail: Mini preview layout type
 * - slots: Named slots with predefined x, y, width, height, type
 * 
 * AI fills content into slots, positions are FIXED for pixel-perfect rendering.
 */

// A4 at 96 DPI dimensions
const PAGE_WIDTH = 794;
const PAGE_HEIGHT = 1123;
// Backward compatibility aliases
const CANVAS_WIDTH = PAGE_WIDTH;
const CANVAS_HEIGHT = PAGE_HEIGHT;

// ==================== Template Definitions ====================

export const PAGE_TEMPLATES = {
    // -------------------- Title Pages --------------------
    title_hero: {
        id: 'title_hero',
        name: 'Title Hero',
        description: 'Report cover with title, image, and executive overview',
        category: 'title',
        thumbnail: 'title',
        slots: {
            title: {
                x: 60, y: 60, width: 440, height: 80,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 60, y: 150, width: 420, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            accent_image: {
                x: 520, y: 50, width: 220, height: 200,
                type: 'image_placeholder', rx: 14,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.12)', blur: 12, offsetX: 0, offsetY: 4 },
            },
            tagline: {
                x: 60, y: 220, width: 420, height: 40,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7, zIndex: 55,
            },
            accent_line: {
                x: 60, y: 280, width: 674, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            overview_title: {
                x: 60, y: 300, width: 674, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            overview_col1: {
                x: 60, y: 350, width: 327, height: 400,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5, zIndex: 60,
            },
            overview_col2: {
                x: 417, y: 350, width: 327, height: 400,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5, zIndex: 60,
            },
            description: {
                x: 60, y: 780, width: 674, height: 180,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5, zIndex: 55,
            },
        },
        optionalSlots: ['subtitle', 'tagline', 'accent_line', 'description'],
    },

    title_image: {
        id: 'title_image',
        name: 'Title with Image',
        description: 'Centered title with hero image below',
        category: 'title',
        thumbnail: 'title_image',
        slots: {
            title: {
                x: 60, y: 60, width: 674, height: 60,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            subtitle: {
                x: 100, y: 140, width: 594, height: 55,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            image: {
                x: 147, y: 220, width: 500, height: 400,
                type: 'image_placeholder',
                zIndex: 20,
            },
            highlights_title: {
                x: 60, y: 660, width: 674, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            highlight_1: {
                x: 60, y: 710, width: 327, height: 150,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            highlight_2: {
                x: 417, y: 710, width: 327, height: 150,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            description: {
                x: 60, y: 890, width: 674, height: 160,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
        },
        optionalSlots: ['subtitle'],
    },

    // -------------------- Content PAGES --------------------
    bullets: {
        id: 'bullets',
        name: 'Bullet Points',
        description: 'Title with bullet list - classic content PAGE',
        category: 'content',
        thumbnail: 'bullets',
        slots: {
            title: {
                x: 50, y: 40, width: 694, height: 60,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 50, y: 108, width: 500, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 60,
            },
            divider: {
                x: 50, y: 105, width: 694, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            bullets: {
                x: 60, y: 155, width: 480, height: 830,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            key_takeaway: {
                x: 70, y: 1010, width: 654, height: 50,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'bold', textAlign: 'left',
                opacity: 0.8,
                zIndex: 60,
            },
            accent_image: {
                x: 560, y: 180, width: 200, height: 280,
                type: 'image_placeholder', rx: 12,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.12)', blur: 12, offsetX: 0, offsetY: 4 },
            },
        },
        optionalSlots: ['divider', 'subtitle', 'key_takeaway', 'accent_image'],
    },

    two_columns: {
        id: 'two_columns',
        name: 'Two Columns',
        description: 'Side-by-side comparison or dual content areas',
        category: 'content',
        thumbnail: 'two_column',
        slots: {
            title: {
                x: 50, y: 40, width: 694, height: 60,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            divider: {
                x: 50, y: 105, width: 694, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            // Left column card (327px wide with 40px gap)
            left_card: {
                x: 50, y: 130, width: 327, height: 900,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 16,
                zIndex: 8,
            },
            left_icon: {
                x: 70, y: 150, width: 48, height: 48,
                type: 'icon', size: 48,
                useAccentColor: true,
                zIndex: 35,
            },
            left_title: {
                x: 130, y: 155, width: 227, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'bold', textAlign: 'left',
                lineHeight: 1.2,
                zIndex: 60,
            },
            left_content: {
                x: 70, y: 230, width: 287, height: 780,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
            // Right column card
            right_card: {
                x: 417, y: 130, width: 327, height: 900,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 16,
                zIndex: 8,
            },
            right_icon: {
                x: 437, y: 150, width: 48, height: 48,
                type: 'icon', size: 48,
                useAccentColor: true,
                zIndex: 35,
            },
            right_title: {
                x: 497, y: 155, width: 227, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'bold', textAlign: 'left',
                lineHeight: 1.2,
                zIndex: 60,
            },
            right_content: {
                x: 437, y: 230, width: 287, height: 780,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
        },
        optionalSlots: ['divider', 'left_icon', 'right_icon'],
    },

    three_cards: {
        id: 'three_cards',
        name: 'Three Cards',
        description: 'Three feature cards with icons - great for key points',
        category: 'content',
        thumbnail: 'three_cards',
        slots: {
            title: {
                x: 50, y: 40, width: 694, height: 60,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            subtitle: {
                x: 80, y: 108, width: 634, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'normal', textAlign: 'center',
                opacity: 0.7,
                zIndex: 55,
            },
            // Card 1 (218px wide with 20px gaps)
            card1_bg: {
                x: 50, y: 155, width: 218, height: 580,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 14,
                zIndex: 8,
            },
            card1_icon: {
                x: 127, y: 180, width: 48, height: 48,
                type: 'icon', size: 48,
                useAccentColor: true,
                zIndex: 35,
            },
            card1_title: {
                x: 60, y: 245, width: 198, height: 45,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card1_desc: {
                x: 60, y: 300, width: 198, height: 400,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.4,
                zIndex: 60,
            },
            // Card 2
            card2_bg: {
                x: 288, y: 155, width: 218, height: 580,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 14,
                zIndex: 8,
            },
            card2_icon: {
                x: 365, y: 180, width: 48, height: 48,
                type: 'icon', size: 48,
                useAccentColor: true,
                zIndex: 35,
            },
            card2_title: {
                x: 298, y: 245, width: 198, height: 45,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card2_desc: {
                x: 298, y: 300, width: 198, height: 400,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.4,
                zIndex: 60,
            },
            // Card 3
            card3_bg: {
                x: 526, y: 155, width: 218, height: 580,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 14,
                zIndex: 8,
            },
            card3_icon: {
                x: 603, y: 180, width: 48, height: 48,
                type: 'icon', size: 48,
                useAccentColor: true,
                zIndex: 35,
            },
            card3_title: {
                x: 536, y: 245, width: 198, height: 45,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card3_desc: {
                x: 536, y: 300, width: 198, height: 400,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.4,
                zIndex: 60,
            },
            // Conclusion below cards
            conclusion: {
                x: 50, y: 760, width: 694, height: 250,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
        },
        optionalSlots: ['subtitle', 'card1_icon', 'card2_icon', 'card3_icon', 'conclusion'],
    },

    image_left: {
        id: 'image_left',
        name: 'Image Left',
        description: 'Large image on left with text content on right',
        category: 'media',
        thumbnail: 'image_left',
        slots: {
            title: {
                x: 50, y: 30, width: 694, height: 50,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 50, y: 82, width: 500, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            image: {
                x: 50, y: 120, width: 327, height: 400,
                type: 'image_placeholder',
                zIndex: 20,
            },
            content_title: {
                x: 397, y: 130, width: 347, height: 80,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'left',
                lineHeight: 1.3,
                zIndex: 60,
            },
            content: {
                x: 397, y: 220, width: 347, height: 295,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            // Divider line
            divider: {
                x: 50, y: 540, width: 694, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.3,
                zIndex: 10,
            },
            analysis_title: {
                x: 50, y: 555, width: 694, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            analysis_col1: {
                x: 50, y: 600, width: 327, height: 430,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            analysis_col2: {
                x: 417, y: 600, width: 327, height: 430,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
        },
        optionalSlots: ['content_title', 'subtitle', 'analysis_title', 'analysis_col1', 'analysis_col2'],
    },

    image_right: {
        id: 'image_right',
        name: 'Image Right',
        description: 'Text content on left with large image on right',
        category: 'media',
        thumbnail: 'image_right',
        slots: {
            title: {
                x: 50, y: 30, width: 694, height: 50,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 50, y: 82, width: 500, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            content_title: {
                x: 50, y: 130, width: 327, height: 80,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'left',
                lineHeight: 1.3,
                zIndex: 60,
            },
            content: {
                x: 50, y: 220, width: 327, height: 295,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            image: {
                x: 397, y: 120, width: 347, height: 400,
                type: 'image_placeholder',
                zIndex: 20,
            },
            // Divider line
            divider: {
                x: 50, y: 540, width: 694, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.3,
                zIndex: 10,
            },
            analysis_title: {
                x: 50, y: 555, width: 694, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            analysis_col1: {
                x: 50, y: 600, width: 327, height: 430,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            analysis_col2: {
                x: 417, y: 600, width: 327, height: 430,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
        },
        optionalSlots: ['content_title', 'subtitle', 'analysis_title', 'analysis_col1', 'analysis_col2'],
    },

    process_steps: {
        id: 'process_steps',
        name: 'Process Flow Diagram',
        description: 'Full-page blank canvas where the LLM emits a complete inline SVG diagram (process flows, lifecycles, pipelines)',
        category: 'content',
        thumbnail: 'diagram',
        slots: {
            title: {
                x: 50, y: 40, width: 694, height: 60,
                type: 'text', textType: 'title',
                fontSize: 30, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            diagram: {
                x: 30, y: 110, width: 734, height: 970,
                type: 'svg_diagram',
                diagramKind: 'process',
                zIndex: 50,
            },
        },
        optionalSlots: [],
    },

    org_hierarchy: {
        id: 'org_hierarchy',
        name: 'Org Hierarchy Diagram',
        description: 'Full-page SVG diagram for organizational charts, reporting structures, taxonomies, or trees',
        category: 'content',
        thumbnail: 'diagram',
        slots: {
            title: {
                x: 50, y: 40, width: 694, height: 60,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            diagram: {
                x: 50, y: 120, width: 694, height: 820,
                type: 'svg_diagram',
                diagramKind: 'hierarchy',
                zIndex: 50,
            },
            caption: {
                x: 50, y: 960, width: 694, height: 100,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
        },
        optionalSlots: ['caption'],
    },

    infographic_diagram: {
        id: 'infographic_diagram',
        name: 'Infographic Diagram',
        description: 'Full-page SVG infographic for concepts, anatomies, cycles, venn/funnel, or any custom visual breakdown',
        category: 'content',
        thumbnail: 'diagram',
        slots: {
            title: {
                x: 50, y: 40, width: 694, height: 50,
                type: 'text', textType: 'title',
                fontSize: 28, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            diagram: {
                x: 30, y: 100, width: 734, height: 880,
                type: 'svg_diagram',
                diagramKind: 'infographic',
                zIndex: 50,
            },
            caption: {
                x: 50, y: 1000, width: 694, height: 60,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
        },
        optionalSlots: ['caption'],
    },

    quote: {
        id: 'quote',
        name: 'Quote',
        description: 'Highlighted quote with attribution',
        category: 'content',
        thumbnail: 'quote',
        slots: {
            title: {
                x: 100, y: 200, width: 594, height: 60,
                type: 'text', textType: 'title',
                fontSize: 30, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            quote_mark_left: {
                x: 50, y: 210, width: 80, height: 80,
                type: 'text', textType: 'body',
                content: '\u201c', // Fixed content
                fontSize: 120, fontWeight: 'bold', textAlign: 'left',
                useAccentColor: true, opacity: 0.3,
                zIndex: 5,
            },
            quote_text: {
                x: 80, y: 300, width: 450, height: 230,
                type: 'text', textType: 'body',
                fontSize: 32, fontWeight: 'normal', textAlign: 'center',
                fontStyle: 'italic',
                lineHeight: 1.5,
                zIndex: 60,
            },
            attribution: {
                x: 80, y: 560, width: 450, height: 45,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            context_text: {
                x: 100, y: 630, width: 400, height: 50,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'center',
                opacity: 0.6,
                zIndex: 60,
            },
            context: {
                x: 100, y: 710, width: 400, height: 60,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                opacity: 0.6,
                zIndex: 55,
            },
            quote_mark_right: {
                x: 510, y: 420, width: 80, height: 80,
                type: 'text', textType: 'body',
                content: '\u201d', // Fixed content
                fontSize: 100, fontWeight: 'bold', textAlign: 'right',
                useAccentColor: true, opacity: 0.3,
                zIndex: 5,
            },
            reflection: {
                x: 100, y: 810, width: 450, height: 230,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            accent_image: {
                x: 570, y: 300, width: 190, height: 280,
                type: 'image_placeholder', rx: 12,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.12)', blur: 12, offsetX: 0, offsetY: 3 },
            },
        },
        optionalSlots: ['title', 'quote_mark_left', 'quote_mark_right', 'attribution', 'context_text', 'context', 'reflection', 'accent_image'],
    },

    // -------------------- Advanced Layouts --------------------
    modern_geometric: {
        id: 'modern_geometric',
        name: 'Modern Geometric',
        description: 'Dynamic layout with abstract shapes and offset content',
        category: 'advanced',
        thumbnail: 'modern',
        slots: {
            // Decorations as slots
            bg_rect: {
                x: 0, y: 0, width: 20, height: 1123,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            triangle_top: {
                x: 644, y: -50, width: 150, height: 150,
                type: 'shape', shapeType: 'triangle',
                useAccentColor: true, opacity: 0.2,
                zIndex: 5,
            },
            circle_bottom: {
                x: 350, y: 900, width: 100, height: 100,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true, opacity: 0.1,
                zIndex: 5,
            },
            // Content
            title: {
                x: 60, y: 50, width: 350, height: 70,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 60, y: 125, width: 350, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            content: {
                x: 60, y: 170, width: 350, height: 440,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            detail: {
                x: 60, y: 630, width: 350, height: 50,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.6,
                zIndex: 60,
            },
            image: {
                x: 420, y: 60, width: 324, height: 420,
                type: 'image_placeholder',
                zIndex: 20,
            },
        },
        optionalSlots: ['image', 'subtitle', 'detail'],
    },

    data_dashboard: {
        id: 'data_dashboard',
        name: 'Data Dashboard',
        description: 'Four-quadrant layout for metrics and charts',
        category: 'data',
        thumbnail: 'dashboard',
        slots: {
            title: {
                x: 50, y: 30, width: 694, height: 50,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            // Charts (two columns, 327px each with gap)
            chart_1: {
                x: 50, y: 100, width: 327, height: 200,
                type: 'chart',
                zIndex: 50,
            },
            chart_2: {
                x: 417, y: 100, width: 327, height: 200,
                type: 'chart',
                zIndex: 50,
            },
            // Stats
            stat_1: {
                x: 50, y: 320, width: 327, height: 180,
                type: 'text', textType: 'body',
                content: 'Key Statistic\n+15%',
                fontSize: 16, textAlign: 'center',
                zIndex: 60,
            },
            stat_2: {
                x: 417, y: 320, width: 327, height: 180,
                type: 'text', textType: 'body',
                content: 'Growth Rate\n2.4x',
                fontSize: 16, textAlign: 'center',
                zIndex: 60,
            },
        },
        optionalSlots: [],
    },

    // ==================== RESUME TEMPLATES ====================
    
    resume_header_photo: {
        id: 'resume_header_photo',
        name: 'Resume - Header with Photo',
        description: 'Professional header with photo, name, and contact info',
        category: 'resume',
        thumbnail: 'resume_photo',
        slots: {
            photo: {
                x: 60, y: 60, width: 150, height: 150,
                type: 'image_placeholder',
                zIndex: 20,
                borderRadius: 75, // Circular
            },
            name: {
                x: 240, y: 70, width: 494, height: 50,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            title_role: {
                x: 240, y: 130, width: 494, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            contact: {
                x: 240, y: 175, width: 494, height: 30,
                type: 'text', textType: 'body',
                fontSize: 11, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            summary: {
                x: 60, y: 250, width: 674, height: 100,
                type: 'text', textType: 'body',
                fontSize: 11, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            experience_section: {
                x: 60, y: 380, width: 674, height: 400,
                type: 'text', textType: 'body',
                fontSize: 11, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
            skills_section: {
                x: 60, y: 810, width: 674, height: 250,
                type: 'text', textType: 'body',
                fontSize: 11, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
        },
        optionalSlots: ['photo', 'summary'],
    },

    resume_two_column: {
        id: 'resume_two_column',
        name: 'Resume - Two Column',
        description: 'Sidebar with skills, main area for experience',
        category: 'resume',
        thumbnail: 'resume_2col',
        slots: {
            name: {
                x: 60, y: 50, width: 674, height: 45,
                type: 'text', textType: 'title',
                fontSize: 28, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            title_role: {
                x: 60, y: 100, width: 674, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            contact: {
                x: 60, y: 135, width: 674, height: 25,
                type: 'text', textType: 'body',
                fontSize: 10, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            // Left sidebar - Skills & Education
            sidebar_title: {
                x: 60, y: 190, width: 200, height: 25,
                type: 'text', textType: 'subtitle',
                fontSize: 14, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            sidebar_content: {
                x: 60, y: 220, width: 200, height: 850,
                type: 'text', textType: 'body',
                fontSize: 10, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
            // Main content - Experience
            main_title: {
                x: 290, y: 190, width: 444, height: 25,
                type: 'text', textType: 'subtitle',
                fontSize: 14, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            main_content: {
                x: 290, y: 220, width: 444, height: 850,
                type: 'text', textType: 'body',
                fontSize: 10, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
        },
        optionalSlots: [],
    },

    // ==================== REPORT TEMPLATES ====================
    
    report_title_page: {
        id: 'report_title_page',
        name: 'Report - Title Page',
        description: 'Professional report cover with logo and title',
        category: 'report',
        thumbnail: 'report_title',
        slots: {
            logo: {
                x: 297, y: 150, width: 200, height: 100,
                type: 'image_placeholder',
                zIndex: 20,
            },
            title: {
                x: 60, y: 380, width: 674, height: 80,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            subtitle: {
                x: 100, y: 480, width: 594, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            date: {
                x: 60, y: 950, width: 674, height: 30,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            author: {
                x: 60, y: 990, width: 674, height: 30,
                type: 'text', textType: 'body',
                fontSize: 12, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
        },
        optionalSlots: ['logo', 'subtitle', 'date', 'author'],
    },

    report_chart_focus: {
        id: 'report_chart_focus',
        name: 'Report - Chart Focus',
        description: 'Large chart with title and annotations',
        category: 'report',
        thumbnail: 'report_chart',
        slots: {
            title: {
                x: 60, y: 50, width: 674, height: 45,
                type: 'text', textType: 'title',
                fontSize: 24, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            chart: {
                x: 60, y: 120, width: 674, height: 500,
                type: 'chart',
                zIndex: 50,
            },
            caption: {
                x: 60, y: 640, width: 674, height: 30,
                type: 'text', textType: 'body',
                fontSize: 10, fontWeight: 'italic', textAlign: 'center',
                zIndex: 60,
            },
            analysis: {
                x: 60, y: 700, width: 674, height: 380,
                type: 'text', textType: 'body',
                fontSize: 11, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
        },
        optionalSlots: ['caption'],
    },

    report_multi_column: {
        id: 'report_multi_column',
        name: 'Report - Multi Column',
        description: 'Two or three column text layout for reports',
        category: 'report',
        thumbnail: 'report_columns',
        slots: {
            title: {
                x: 60, y: 50, width: 674, height: 45,
                type: 'text', textType: 'title',
                fontSize: 24, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            column_1: {
                x: 60, y: 120, width: 220, height: 950,
                type: 'text', textType: 'body',
                fontSize: 10, fontWeight: 'normal', textAlign: 'justify',
                lineHeight: 1.4,
                zIndex: 60,
            },
            column_2: {
                x: 297, y: 120, width: 220, height: 950,
                type: 'text', textType: 'body',
                fontSize: 10, fontWeight: 'normal', textAlign: 'justify',
                lineHeight: 1.4,
                zIndex: 60,
            },
            column_3: {
                x: 534, y: 120, width: 200, height: 950,
                type: 'text', textType: 'body',
                fontSize: 10, fontWeight: 'normal', textAlign: 'justify',
                lineHeight: 1.4,
                zIndex: 60,
            },
        },
        optionalSlots: ['column_3'], // Can use 2 or 3 columns
    },

    report_executive_summary: {
        id: 'report_executive_summary',
        name: 'Report - Executive Summary',
        description: 'Key highlights with bullet points and metrics',
        category: 'report',
        thumbnail: 'report_summary',
        slots: {
            title: {
                x: 60, y: 50, width: 674, height: 45,
                type: 'text', textType: 'title',
                fontSize: 24, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            highlights_title: {
                x: 60, y: 120, width: 300, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            highlights: {
                x: 60, y: 160, width: 300, height: 400,
                type: 'text', textType: 'body',
                fontSize: 11, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            metrics_title: {
                x: 400, y: 120, width: 334, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            metric_1: {
                x: 400, y: 160, width: 150, height: 100,
                type: 'text', textType: 'body',
                fontSize: 28, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            metric_2: {
                x: 560, y: 160, width: 150, height: 100,
                type: 'text', textType: 'body',
                fontSize: 28, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            conclusion: {
                x: 60, y: 600, width: 674, height: 480,
                type: 'text', textType: 'body',
                fontSize: 11, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            accent_image: {
                x: 560, y: 290, width: 170, height: 160,
                type: 'image_placeholder', rx: 10,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.10)', blur: 10, offsetX: 0, offsetY: 3 },
            },
        },
        optionalSlots: ['metric_2', 'accent_image'],
    },

    // ==================== SECTION / CLOSING PAGES ====================

    section_break: {
        id: 'section_break',
        name: 'Section Break',
        description: 'Section opener with overview content and image',
        category: 'title',
        thumbnail: 'section_break',
        slots: {
            section_title: {
                x: 60, y: 60, width: 440, height: 80,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 60, y: 150, width: 420, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            accent_image: {
                x: 520, y: 50, width: 220, height: 200,
                type: 'image_placeholder', rx: 14,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.12)', blur: 12, offsetX: 0, offsetY: 4 },
            },
            accent_line_1: {
                x: 60, y: 220, width: 674, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, rx: 2,
                zIndex: 10,
            },
            overview: {
                x: 60, y: 240, width: 674, height: 250,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.6,
                zIndex: 60,
            },
            accent_line_2: {
                x: 60, y: 505, width: 674, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.5, rx: 2,
                zIndex: 10,
            },
            highlights_title: {
                x: 60, y: 520, width: 674, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            highlights_col1: {
                x: 60, y: 570, width: 327, height: 380,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            highlights_col2: {
                x: 417, y: 570, width: 327, height: 380,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
        },
        optionalSlots: ['subtitle', 'accent_line_1', 'accent_line_2', 'highlights_title', 'highlights_col1', 'highlights_col2'],
    },

    closing: {
        id: 'closing',
        name: 'Closing',
        description: 'Closing page with summary, key takeaways, and call-to-action',
        category: 'title',
        thumbnail: 'closing',
        slots: {
            title: {
                x: 60, y: 50, width: 674, height: 70,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 60, y: 130, width: 420, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            accent_image: {
                x: 520, y: 50, width: 220, height: 200,
                type: 'image_placeholder', rx: 14,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.12)', blur: 12, offsetX: 0, offsetY: 4 },
            },
            accent_line_1: {
                x: 60, y: 195, width: 674, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            summary_title: {
                x: 60, y: 210, width: 674, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            summary: {
                x: 60, y: 255, width: 674, height: 280,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.6,
                zIndex: 60,
            },
            accent_line_2: {
                x: 60, y: 555, width: 674, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.5,
                zIndex: 10,
            },
            cta_text: {
                x: 60, y: 565, width: 674, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            next_steps_col1: {
                x: 60, y: 620, width: 327, height: 350,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            next_steps_col2: {
                x: 417, y: 620, width: 327, height: 350,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            footer_note: {
                x: 60, y: 1000, width: 674, height: 60,
                type: 'text', textType: 'body',
                fontSize: 12, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.6, lineHeight: 1.4,
                zIndex: 55,
            },
        },
        optionalSlots: ['subtitle', 'accent_line_1', 'accent_line_2', 'cta_text', 'next_steps_col1', 'next_steps_col2', 'footer_note'],
    },

    // ==================== CONTENT GRID PAGES ====================

    four_cards: {
        id: 'four_cards',
        name: 'Four Cards',
        description: 'Four feature cards in 2x2 grid for A4 portrait',
        category: 'content',
        thumbnail: 'four_cards',
        slots: {
            title: {
                x: 50, y: 40, width: 694, height: 55,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            card1_icon: { x: 167, y: 145, width: 44, height: 44, type: 'icon', size: 44, zIndex: 35 },
            card1_title: { x: 70, y: 210, width: 280, height: 40, type: 'text', textType: 'subtitle', fontSize: 18, fontWeight: 'bold', textAlign: 'center', lineHeight: 1.2, zIndex: 60 },
            card1_desc: { x: 70, y: 260, width: 280, height: 200, type: 'text', textType: 'body', fontSize: 14, fontWeight: 'normal', textAlign: 'center', lineHeight: 1.3, zIndex: 60 },
            card2_icon: { x: 527, y: 145, width: 44, height: 44, type: 'icon', size: 44, zIndex: 35 },
            card2_title: { x: 430, y: 210, width: 280, height: 40, type: 'text', textType: 'subtitle', fontSize: 18, fontWeight: 'bold', textAlign: 'center', lineHeight: 1.2, zIndex: 60 },
            card2_desc: { x: 430, y: 260, width: 280, height: 200, type: 'text', textType: 'body', fontSize: 14, fontWeight: 'normal', textAlign: 'center', lineHeight: 1.3, zIndex: 60 },
            card3_icon: { x: 167, y: 530, width: 44, height: 44, type: 'icon', size: 44, zIndex: 35 },
            card3_title: { x: 70, y: 595, width: 280, height: 40, type: 'text', textType: 'subtitle', fontSize: 18, fontWeight: 'bold', textAlign: 'center', lineHeight: 1.2, zIndex: 60 },
            card3_desc: { x: 70, y: 645, width: 280, height: 200, type: 'text', textType: 'body', fontSize: 14, fontWeight: 'normal', textAlign: 'center', lineHeight: 1.3, zIndex: 60 },
            card4_icon: { x: 527, y: 530, width: 44, height: 44, type: 'icon', size: 44, zIndex: 35 },
            card4_title: { x: 430, y: 595, width: 280, height: 40, type: 'text', textType: 'subtitle', fontSize: 18, fontWeight: 'bold', textAlign: 'center', lineHeight: 1.2, zIndex: 60 },
            card4_desc: { x: 430, y: 645, width: 280, height: 200, type: 'text', textType: 'body', fontSize: 14, fontWeight: 'normal', textAlign: 'center', lineHeight: 1.3, zIndex: 60 },
            summary: {
                x: 50, y: 900, width: 694, height: 150,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            divider: {
                x: 50, y: 885, width: 694, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.3,
                zIndex: 10,
            },
        },
        optionalSlots: ['card1_icon', 'card2_icon', 'card3_icon', 'card4_icon', 'summary', 'divider'],
    },

    timeline: {
        id: 'timeline',
        name: 'Timeline',
        description: 'Vertical timeline with events and descriptions for A4',
        category: 'content',
        thumbnail: 'timeline',
        slots: {
            title: {
                x: 50, y: 40, width: 530, height: 55,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            event1_date: { x: 130, y: 140, width: 614, height: 30, type: 'text', textType: 'subtitle', fontSize: 15, fontWeight: 'bold', textAlign: 'left', zIndex: 60 },
            event1_title: { x: 130, y: 175, width: 614, height: 35, type: 'text', textType: 'subtitle', fontSize: 18, fontWeight: 'bold', textAlign: 'left', lineHeight: 1.2, zIndex: 60 },
            event1_desc: { x: 130, y: 215, width: 614, height: 80, type: 'text', textType: 'body', fontSize: 14, fontWeight: 'normal', textAlign: 'left', lineHeight: 1.4, zIndex: 60 },
            event2_date: { x: 130, y: 340, width: 614, height: 30, type: 'text', textType: 'subtitle', fontSize: 15, fontWeight: 'bold', textAlign: 'left', zIndex: 60 },
            event2_title: { x: 130, y: 375, width: 614, height: 35, type: 'text', textType: 'subtitle', fontSize: 18, fontWeight: 'bold', textAlign: 'left', lineHeight: 1.2, zIndex: 60 },
            event2_desc: { x: 130, y: 415, width: 614, height: 80, type: 'text', textType: 'body', fontSize: 14, fontWeight: 'normal', textAlign: 'left', lineHeight: 1.4, zIndex: 60 },
            event3_date: { x: 130, y: 540, width: 614, height: 30, type: 'text', textType: 'subtitle', fontSize: 15, fontWeight: 'bold', textAlign: 'left', zIndex: 60 },
            event3_title: { x: 130, y: 575, width: 614, height: 35, type: 'text', textType: 'subtitle', fontSize: 18, fontWeight: 'bold', textAlign: 'left', lineHeight: 1.2, zIndex: 60 },
            event3_desc: { x: 130, y: 615, width: 614, height: 80, type: 'text', textType: 'body', fontSize: 14, fontWeight: 'normal', textAlign: 'left', lineHeight: 1.4, zIndex: 60 },
            event4_date: { x: 130, y: 740, width: 614, height: 30, type: 'text', textType: 'subtitle', fontSize: 15, fontWeight: 'bold', textAlign: 'left', zIndex: 60 },
            event4_title: { x: 130, y: 775, width: 614, height: 35, type: 'text', textType: 'subtitle', fontSize: 18, fontWeight: 'bold', textAlign: 'left', lineHeight: 1.2, zIndex: 60 },
            event4_desc: { x: 130, y: 815, width: 614, height: 80, type: 'text', textType: 'body', fontSize: 14, fontWeight: 'normal', textAlign: 'left', lineHeight: 1.4, zIndex: 60 },
            conclusion: {
                x: 50, y: 940, width: 694, height: 120,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            timeline_line: {
                x: 83, y: 130, width: 4, height: 770,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.4,
                zIndex: 10,
            },
            dot_1: { x: 71, y: 155, width: 28, height: 28, type: 'shape', shapeType: 'circle', useAccentColor: true, zIndex: 15 },
            dot_2: { x: 71, y: 355, width: 28, height: 28, type: 'shape', shapeType: 'circle', useAccentColor: true, zIndex: 15 },
            dot_3: { x: 71, y: 555, width: 28, height: 28, type: 'shape', shapeType: 'circle', useAccentColor: true, zIndex: 15 },
            dot_4: { x: 71, y: 755, width: 28, height: 28, type: 'shape', shapeType: 'circle', useAccentColor: true, zIndex: 15 },
            footer_line: {
                x: 50, y: 925, width: 694, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.3,
                zIndex: 10,
            },
            accent_image: {
                x: 610, y: 40, width: 150, height: 70,
                type: 'image_placeholder', rx: 10,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.10)', blur: 10, offsetX: 0, offsetY: 3 },
            },
        },
        optionalSlots: ['event1_date', 'event1_desc', 'event2_date', 'event2_desc', 'event3_date', 'event3_desc', 'event4_date', 'event4_desc', 'conclusion', 'timeline_line', 'dot_1', 'dot_2', 'dot_3', 'dot_4', 'footer_line', 'accent_image'],
    },

    comparison: {
        id: 'comparison',
        name: 'Comparison',
        description: 'Side-by-side comparison with headers and content',
        category: 'content',
        thumbnail: 'comparison',
        slots: {
            title: {
                x: 50, y: 40, width: 694, height: 55,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            left_header: {
                x: 60, y: 130, width: 320, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 22, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            left_content: {
                x: 70, y: 195, width: 300, height: 800,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            right_header: {
                x: 414, y: 130, width: 320, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 22, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            right_content: {
                x: 424, y: 195, width: 300, height: 800,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            divider: {
                x: 50, y: 105, width: 694, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            accent_image: {
                x: 300, y: 1010, width: 200, height: 90,
                type: 'image_placeholder', rx: 10,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.10)', blur: 10, offsetX: 0, offsetY: 3 },
            },
        },
        optionalSlots: ['divider', 'accent_image'],
    },

    // ==================== DATA / CHART PAGES ====================

    chart_focus: {
        id: 'chart_focus',
        name: 'Chart Focus',
        description: 'Large chart taking most of the page',
        category: 'data',
        thumbnail: 'chart_focus',
        slots: {
            title: {
                x: 50, y: 40, width: 694, height: 50,
                type: 'text', textType: 'title',
                fontSize: 30, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            description: {
                x: 50, y: 100, width: 400, height: 35,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            chart: {
                x: 50, y: 150, width: 694, height: 550,
                type: 'chart',
                zIndex: 50,
            },
            analysis: {
                x: 50, y: 730, width: 694, height: 320,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.6,
                zIndex: 60,
            },
            divider: {
                x: 50, y: 720, width: 694, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.3,
                zIndex: 10,
            },
        },
        optionalSlots: ['description', 'analysis', 'divider'],
    },

    stats_highlight: {
        id: 'stats_highlight',
        name: 'Stats Highlight',
        description: 'Three prominent statistics with labels and descriptions',
        category: 'data',
        thumbnail: 'stats_highlight',
        slots: {
            title: {
                x: 50, y: 50, width: 530, height: 60,
                type: 'text', textType: 'title',
                fontSize: 34, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            stat1_value: { x: 50, y: 200, width: 218, height: 100, type: 'text', textType: 'title', fontSize: 56, fontWeight: 'bold', textAlign: 'center', zIndex: 60 },
            stat1_label: { x: 50, y: 310, width: 218, height: 55, type: 'text', textType: 'body', fontSize: 18, fontWeight: 'bold', textAlign: 'center', zIndex: 60 },
            stat1_desc: { x: 55, y: 380, width: 208, height: 300, type: 'text', textType: 'body', fontSize: 14, fontWeight: 'normal', textAlign: 'center', lineHeight: 1.5, opacity: 0.7, zIndex: 55 },
            stat2_value: { x: 288, y: 200, width: 218, height: 100, type: 'text', textType: 'title', fontSize: 56, fontWeight: 'bold', textAlign: 'center', zIndex: 60 },
            stat2_label: { x: 288, y: 310, width: 218, height: 55, type: 'text', textType: 'body', fontSize: 18, fontWeight: 'bold', textAlign: 'center', zIndex: 60 },
            stat2_desc: { x: 293, y: 380, width: 208, height: 300, type: 'text', textType: 'body', fontSize: 14, fontWeight: 'normal', textAlign: 'center', lineHeight: 1.5, opacity: 0.7, zIndex: 55 },
            stat3_value: { x: 526, y: 200, width: 218, height: 100, type: 'text', textType: 'title', fontSize: 56, fontWeight: 'bold', textAlign: 'center', zIndex: 60 },
            stat3_label: { x: 526, y: 310, width: 218, height: 55, type: 'text', textType: 'body', fontSize: 18, fontWeight: 'bold', textAlign: 'center', zIndex: 60 },
            stat3_desc: { x: 531, y: 380, width: 208, height: 300, type: 'text', textType: 'body', fontSize: 14, fontWeight: 'normal', textAlign: 'center', lineHeight: 1.5, opacity: 0.7, zIndex: 55 },
            summary: {
                x: 50, y: 740, width: 480, height: 280,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.6,
                zIndex: 60,
            },
            divider: {
                x: 50, y: 130, width: 694, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            accent_image: {
                x: 560, y: 740, width: 200, height: 270,
                type: 'image_placeholder', rx: 12,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.10)', blur: 12, offsetX: 0, offsetY: 3 },
            },
        },
        optionalSlots: ['stat1_desc', 'stat2_desc', 'stat3_desc', 'summary', 'divider', 'accent_image'],
    },

    big_number: {
        id: 'big_number',
        name: 'Big Number',
        description: 'Single prominent statistic with context',
        category: 'data',
        thumbnail: 'big_number',
        slots: {
            metric: {
                x: 60, y: 300, width: 674, height: 180,
                type: 'text', textType: 'title',
                fontSize: 110, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            label: {
                x: 80, y: 500, width: 440, height: 80,
                type: 'text', textType: 'subtitle',
                fontSize: 34, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            context: {
                x: 80, y: 610, width: 400, height: 200,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.6, opacity: 0.8,
                zIndex: 55,
            },
            footnote: {
                x: 80, y: 830, width: 400, height: 80,
                type: 'text', textType: 'body',
                fontSize: 12, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.5,
                zIndex: 50,
            },
            trend_note: {
                x: 80, y: 930, width: 400, height: 100,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5, opacity: 0.7,
                zIndex: 55,
            },
            accent_circle_1: {
                x: 50, y: 880, width: 120, height: 120,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true, opacity: 0.15,
                zIndex: 5,
            },
            accent_circle_2: {
                x: 624, y: 100, width: 140, height: 140,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true, opacity: 0.12,
                zIndex: 5,
            },
            accent_line: {
                x: 297, y: 800, width: 200, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.3,
                zIndex: 6,
            },
            accent_image: {
                x: 540, y: 490, width: 220, height: 300,
                type: 'image_placeholder', rx: 12,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.12)', blur: 12, offsetX: 0, offsetY: 4 },
            },
        },
        optionalSlots: ['context', 'footnote', 'trend_note', 'accent_circle_1', 'accent_circle_2', 'accent_line', 'accent_image'],
    },

    // ==================== MEDIA PAGES ====================

    full_bleed_image: {
        id: 'full_bleed_image',
        name: 'Full Bleed Image',
        description: 'Hero image top half with rich content analysis below',
        category: 'media',
        thumbnail: 'full_bleed_image',
        slots: {
            image: {
                x: 0, y: 0, width: 794, height: 420,
                type: 'image_placeholder',
                zIndex: 5,
            },
            title: {
                x: 50, y: 340, width: 694, height: 70,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                fill: '#ffffff',
                zIndex: 60,
            },
            overlay: {
                x: 0, y: 300, width: 794, height: 130,
                type: 'shape', shapeType: 'rectangle',
                fill: 'rgba(0,0,0,0.45)',
                zIndex: 10,
            },
            accent_line: {
                x: 60, y: 435, width: 674, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            subtitle: {
                x: 60, y: 450, width: 674, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            content_col1: {
                x: 60, y: 510, width: 327, height: 440,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            content_col2: {
                x: 417, y: 510, width: 327, height: 440,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            key_takeaway: {
                x: 60, y: 980, width: 674, height: 80,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'bold', textAlign: 'left',
                opacity: 0.8, lineHeight: 1.4,
                zIndex: 55,
            },
        },
        optionalSlots: ['subtitle', 'overlay', 'accent_line', 'key_takeaway'],
    },

    // ==================== BLANK TEMPLATE ====================
    
    blank_freeflow: {
        id: 'blank_freeflow',
        name: 'Blank Page',
        description: 'Empty canvas for free-form design',
        category: 'blank',
        thumbnail: 'blank',
        slots: {},
        optionalSlots: [],
    },
};

// ==================== Template Categories ====================

export const TEMPLATE_CATEGORIES = [
    { id: 'resume', name: 'Resume', icon: 'person' },
    { id: 'report', name: 'Report', icon: 'document-text' },
    { id: 'title', name: 'Title Pages', icon: 'layout' },
    { id: 'content', name: 'Content', icon: 'file-text' },
    { id: 'data', name: 'Data & Charts', icon: 'bar-chart' },
    { id: 'media', name: 'Media', icon: 'image' },
    { id: 'blank', name: 'Blank', icon: 'square-outline' },
];

// ==================== Helper Functions ====================

/**
 * Get all templates as array
 */
export function getTemplateList() {
    return Object.values(PAGE_TEMPLATES);
}

/**
 * Get templates by category
 */
export function getTemplatesByCategory(category) {
    return Object.values(PAGE_TEMPLATES).filter(t => t.category === category);
}

/**
 * Get template by ID
 */
export function getTemplate(templateId) {
    return PAGE_TEMPLATES[templateId] || null;
}

/**
 * Apply style colors to a template
 * @param {Object} template - Template definition
 * @param {Object} style - Presentation style with colors
 * @returns {Object} - Template with colors applied
 */
export function applyStyleToTemplate(template, style) {
    if (!template || !style) return template;

    const styledSlots = {};
    const accentColor = style.accentColor || '#3B82F6';
    const cardBg = style.cardBackground || '#f8fafc';
    const textPrimary = style.textPrimary || style.textStyles?.title?.color || '#111827';
    const textSecondary = style.textSecondary || style.textStyles?.body?.color || '#374151';
    const PAGEBackground = style.PAGEBackground || '#ffffff';

    for (const [slotName, slot] of Object.entries(template.slots)) {
        const styledSlot = { ...slot };

        // Apply accent color
        if (slot.useAccentColor) {
            styledSlot.fill = accentColor;
        }

        // Apply card background
        if (slot.useCardBackground) {
            styledSlot.fill = cardBg;
            styledSlot.stroke = style.cardBorder || '#e5e7eb';
        }

        // Apply text colors based on type
        if (slot.type === 'text') {
            if (slot.useWhiteText) {
                styledSlot.fill = '#ffffff';
            } else if (slot.textType === 'title' || slot.textType === 'subtitle') {
                styledSlot.fill = textPrimary;
            } else {
                styledSlot.fill = textSecondary;
            }
        }

        styledSlots[slotName] = styledSlot;
    }

    return {
        ...template,
        slots: styledSlots,
        backgroundColor: PAGEBackground,
    };
}

/**
 * Get template names list for AI prompt
 */
export function getTemplateNamesForPrompt() {
    return Object.entries(PAGE_TEMPLATES).map(([id, t]) =>
        `- ${id}: ${t.description}`
    ).join('\n');
}

/**
 * Get slot structure for a template (for AI prompt)
 */
export function getTemplateSlotsForPrompt(templateId) {
    const template = PAGE_TEMPLATES[templateId];
    if (!template) return '';

    const contentSlots = Object.entries(template.slots)
        .filter(([name, slot]) =>
            slot.type === 'text' ||
            slot.type === 'icon' ||
            slot.type === 'image_placeholder'
        )
        .map(([name, slot]) => {
            if (slot.type === 'text') {
                return `  ${name}: { content: "Your text here" }`;
            } else if (slot.type === 'icon') {
                return `  ${name}: { iconName: "icon-name" }`;
            } else if (slot.type === 'image_placeholder') {
                return `  ${name}: { imageDescription: "Description for AI image" }`;
            }
            return '';
        })
        .filter(Boolean);

    return contentSlots.join('\n');
}

/**
 * Create a new PAGE object from a template ID
 * @param {string} templateId - Template ID
 * @param {Object} style - Presentation style
 * @returns {Object} - New PAGE object with elements
 */
export function createPageFromTemplate(templateId, style) {
    const template = getTemplate(templateId);
    if (!template) return null;

    const styledTemplate = applyStyleToTemplate(template, style);
    const elements = [];
    const timestamp = Date.now();

    // Convert slots to elements
    Object.entries(styledTemplate.slots).forEach(([slotName, slot], index) => {
        // Skip hidden slots? No, all slots in template are visible initial state

        const element = {
            id: `el_${timestamp}_${index}`,
            type: slot.type,
            x: slot.x,
            y: slot.y,
            width: slot.width,
            height: slot.height,
            zIndex: slot.zIndex || 10,
            rotation: 0,
            opacity: slot.opacity || 1,
        };

        // Specific property mapping based on type
        if (slot.type === 'text') {
            element.text = slot.content || (slot.textType === 'title' ? 'Click to add title' : 'Click to add text');
            element.fontSize = slot.fontSize;
            element.fontWeight = slot.fontWeight;
            element.fontFamily = style?.fontFamily || 'Inter';
            element.fill = slot.fill;
            element.textAlign = slot.textAlign;
            element.fontStyle = slot.fontStyle;
        } else if (slot.type === 'shape') {
            element.shapeType = slot.shapeType;
            element.fill = slot.fill;
            element.stroke = slot.stroke;
            element.strokeWidth = slot.stroke ? 1 : 0;
            element.rx = slot.rx;
        } else if (slot.type === 'icon') {
            element.iconName = slot.iconName || 'circle';
            element.fill = slot.fill;
            element.size = slot.size;
        } else if (slot.type === 'image_placeholder') {
            element.src = null; // Placeholder state
            element.imageDescription = slot.imageDescription;
            if (slot.rx) element.rx = slot.rx;
            if (slot.shadow) element.shadow = slot.shadow;
        } else if (slot.type === 'svg_diagram') {
            // Blank SVG diagram placeholder; UI shows a dashed-rect placeholder
            // until svgContent is supplied (by LLM or manual paste).
            element.svgContent = null;
            element.diagramKind = slot.diagramKind || 'diagram';
            element.fillColor = style?.accentColor || '#3B82F6';
        } else if (slot.type === 'chart') {
            // Default chart data
            element.chartConfig = {
                type: 'bar',
                data: {
                    labels: ['Q1', 'Q2', 'Q3', 'Q4'],
                    datasets: [{
                        label: 'Sales',
                        data: [12, 19, 3, 5],
                        backgroundColor: [
                            'rgba(255, 99, 132, 0.2)',
                            'rgba(54, 162, 235, 0.2)',
                            'rgba(255, 206, 86, 0.2)',
                            'rgba(75, 192, 192, 0.2)'
                        ],
                        borderColor: [
                            'rgba(255, 99, 132, 1)',
                            'rgba(54, 162, 235, 1)',
                            'rgba(255, 206, 86, 1)',
                            'rgba(75, 192, 192, 1)'
                        ],
                        borderWidth: 1
                    }]
                },
                options: {
                    scales: {
                        y: { beginAtZero: true }
                    }
                }
            };
        }

        elements.push(element);
    });

    return {
        id: `page_${timestamp}`,
        elements,
        background: styledTemplate.backgroundColor,
        notes: '',
    };
}

export default PAGE_TEMPLATES;
