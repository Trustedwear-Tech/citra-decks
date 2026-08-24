// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

/**
 * Slide Templates - Predefined layouts with fixed slot positions
 * 
 * Each template defines:
 * - name: Display name for UI
 * - description: Short description
 * - thumbnail: Mini preview layout type
 * - slots: Named slots with predefined x, y, width, height, type
 * 
 * AI fills content into slots, positions are FIXED for pixel-perfect rendering.
 */

const CANVAS_WIDTH = 960;
const CANVAS_HEIGHT = 540;

// ==================== Template Definitions ====================

export const SLIDE_TEMPLATES = {
    // -------------------- Title Slides --------------------
    title_hero: {
        id: 'title_hero',
        name: 'Title Hero',
        description: 'Bold centered title with subtitle and decorative accents',
        category: 'title',
        thumbnail: 'title',
        slots: {
            title: {
                x: 50, y: 160, width: 580, height: 110,
                type: 'text', textType: 'title',
                fontSize: 52, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 50, y: 280, width: 520, height: 60,
                type: 'text', textType: 'subtitle',
                fontSize: 26, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            tagline: {
                x: 50, y: 350, width: 480, height: 35,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            accent_image: {
                x: 660, y: 150, width: 260, height: 280,
                type: 'image_placeholder',
                rx: 14,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.12)', blur: 14, offsetX: 0, offsetY: 4 },
            },
        },
        optionalSlots: ['subtitle', 'tagline', 'accent_image'],
    },

    title_image: {
        id: 'title_image',
        name: 'Title with Image',
        description: 'Centered title with hero image below',
        category: 'title',
        thumbnail: 'title_image',
        slots: {
            title: {
                x: 50, y: 30, width: 860, height: 70,
                type: 'text', textType: 'title',
                fontSize: 42, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            subtitle: {
                x: 120, y: 105, width: 720, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 22, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            tagline: {
                x: 140, y: 150, width: 680, height: 30,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'normal', textAlign: 'center',
                opacity: 0.7,
                zIndex: 55,
            },
            image: {
                x: 180, y: 195, width: 600, height: 320,
                type: 'image_placeholder',
                zIndex: 20,
            },
        },
        optionalSlots: ['subtitle', 'tagline'],
    },

    // -------------------- Content Slides --------------------
    bullets: {
        id: 'bullets',
        name: 'Bullet Points',
        description: 'Title with bullet list - classic content slide',
        category: 'content',
        thumbnail: 'bullets',
        slots: {
            title: {
                x: 50, y: 40, width: 860, height: 60,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 50, y: 108, width: 700, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            divider: {
                x: 50, y: 145, width: 860, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            bullets: {
                x: 70, y: 155, width: 560, height: 310,
                type: 'text', textType: 'body',
                fontSize: 22, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            accent_image: {
                x: 660, y: 160, width: 260, height: 260,
                type: 'image_placeholder',
                rx: 12,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.12)', blur: 14, offsetX: 0, offsetY: 4 },
            },
            key_takeaway: {
                x: 70, y: 480, width: 820, height: 35,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'bold', textAlign: 'left',
                opacity: 0.8,
                zIndex: 55,
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
                x: 50, y: 40, width: 860, height: 60,
                type: 'text', textType: 'title',
                fontSize: 40, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            divider: {
                x: 50, y: 105, width: 860, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            // Left column card
            left_card: {
                x: 50, y: 130, width: 420, height: 370,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 16,
                zIndex: 8,
            },
            left_icon: {
                x: 70, y: 150, width: 56, height: 56,
                type: 'icon', size: 56,
                useAccentColor: true,
                zIndex: 35,
            },
            left_title: {
                x: 140, y: 155, width: 310, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 22, fontWeight: 'bold', textAlign: 'left',
                lineHeight: 1.2,
                zIndex: 60,
            },
            left_content: {
                x: 70, y: 250, width: 380, height: 230,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
            // Right column card
            right_card: {
                x: 490, y: 130, width: 420, height: 370,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 16,
                zIndex: 8,
            },
            right_icon: {
                x: 510, y: 150, width: 56, height: 56,
                type: 'icon', size: 56,
                useAccentColor: true,
                zIndex: 35,
            },
            right_title: {
                x: 580, y: 155, width: 310, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 22, fontWeight: 'bold', textAlign: 'left',
                lineHeight: 1.2,
                zIndex: 60,
            },
            right_content: {
                x: 510, y: 250, width: 380, height: 230,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
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
                x: 50, y: 40, width: 860, height: 60,
                type: 'text', textType: 'title',
                fontSize: 40, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            // Card 1
            card1_bg: {
                x: 50, y: 120, width: 280, height: 380,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 16,
                zIndex: 8,
            },
            card1_icon: {
                x: 150, y: 145, width: 64, height: 64,
                type: 'icon', size: 64,
                useAccentColor: true,
                zIndex: 35,
            },
            card1_title: {
                x: 70, y: 235, width: 240, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card1_desc: {
                x: 70, y: 300, width: 240, height: 170,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            // Card 2
            card2_bg: {
                x: 340, y: 120, width: 280, height: 380,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 16,
                zIndex: 8,
            },
            card2_icon: {
                x: 440, y: 145, width: 64, height: 64,
                type: 'icon', size: 64,
                useAccentColor: true,
                zIndex: 35,
            },
            card2_title: {
                x: 360, y: 235, width: 240, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card2_desc: {
                x: 360, y: 300, width: 240, height: 170,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            // Card 3
            card3_bg: {
                x: 630, y: 120, width: 280, height: 380,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 16,
                zIndex: 8,
            },
            card3_icon: {
                x: 730, y: 145, width: 64, height: 64,
                type: 'icon', size: 64,
                useAccentColor: true,
                zIndex: 35,
            },
            card3_title: {
                x: 650, y: 235, width: 240, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card3_desc: {
                x: 650, y: 300, width: 240, height: 170,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
        },
        optionalSlots: [],
    },

    image_left: {
        id: 'image_left',
        name: 'Image Left',
        description: 'Large image on left with text content on right',
        category: 'media',
        thumbnail: 'image_left',
        slots: {
            title: {
                x: 50, y: 30, width: 860, height: 50,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 50, y: 82, width: 500, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            image: {
                x: 50, y: 120, width: 420, height: 380,
                type: 'image_placeholder',
                zIndex: 20,
            },
            content_title: {
                x: 500, y: 130, width: 410, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 26, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            content: {
                x: 500, y: 195, width: 410, height: 290,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
        },
        optionalSlots: ['content_title', 'subtitle'],
    },

    image_right: {
        id: 'image_right',
        name: 'Image Right',
        description: 'Text content on left with large image on right',
        category: 'media',
        thumbnail: 'image_right',
        slots: {
            title: {
                x: 50, y: 30, width: 860, height: 50,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 50, y: 82, width: 500, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            content_title: {
                x: 50, y: 130, width: 410, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 26, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            content: {
                x: 50, y: 195, width: 410, height: 290,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            image: {
                x: 490, y: 120, width: 420, height: 380,
                type: 'image_placeholder',
                zIndex: 20,
            },
        },
        optionalSlots: ['content_title', 'subtitle'],
    },

    process_steps: {
        id: 'process_steps',
        name: 'Process Flow Diagram',
        description: 'Full-slide blank canvas where the LLM emits a complete inline SVG diagram (process flows, lifecycles, pipelines)',
        category: 'advanced',
        thumbnail: 'diagram',
        slots: {
            title: {
                x: 50, y: 28, width: 860, height: 50,
                type: 'text', textType: 'title',
                fontSize: 30, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            diagram: {
                x: 20, y: 90, width: 920, height: 440,
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
        description: 'Full-slide SVG diagram for organizational charts, reporting structures, taxonomies, or trees',
        category: 'advanced',
        thumbnail: 'diagram',
        slots: {
            title: {
                x: 50, y: 30, width: 860, height: 50,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            diagram: {
                x: 30, y: 90, width: 900, height: 410,
                type: 'svg_diagram',
                diagramKind: 'hierarchy',
                zIndex: 50,
            },
            caption: {
                x: 50, y: 505, width: 860, height: 28,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
        },
        optionalSlots: ['caption'],
    },

    infographic_diagram: {
        id: 'infographic_diagram',
        name: 'Infographic Diagram',
        description: 'Full-slide SVG infographic for concepts, anatomies, cycles, venn/funnel, or any custom diagram',
        category: 'advanced',
        thumbnail: 'diagram',
        slots: {
            title: {
                x: 50, y: 25, width: 860, height: 45,
                type: 'text', textType: 'title',
                fontSize: 28, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            diagram: {
                x: 20, y: 80, width: 920, height: 440,
                type: 'svg_diagram',
                diagramKind: 'infographic',
                zIndex: 50,
            },
        },
        optionalSlots: [],
    },

    quote: {
        id: 'quote',
        name: 'Quote',
        description: 'Highlighted quote with attribution and context',
        category: 'content',
        thumbnail: 'quote',
        slots: {
            title: {
                x: 100, y: 40, width: 600, height: 50,
                type: 'text', textType: 'title',
                fontSize: 30, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            quote_mark_left: {
                x: 50, y: 90, width: 80, height: 80,
                type: 'text', textType: 'body',
                content: '\u201C',
                fontSize: 120, fontWeight: 'bold', textAlign: 'left',
                useAccentColor: true, opacity: 0.3,
                zIndex: 5,
            },
            quote_text: {
                x: 80, y: 150, width: 600, height: 180,
                type: 'text', textType: 'body',
                fontSize: 32, fontWeight: 'normal', textAlign: 'center',
                fontStyle: 'italic',
                zIndex: 60,
            },
            attribution: {
                x: 80, y: 350, width: 600, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            context_text: {
                x: 100, y: 400, width: 520, height: 50,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'normal', textAlign: 'center',
                opacity: 0.6,
                zIndex: 55,
            },
            quote_mark_right: {
                x: 650, y: 270, width: 80, height: 80,
                type: 'text', textType: 'body',
                content: '\u201D',
                fontSize: 120, fontWeight: 'bold', textAlign: 'right',
                useAccentColor: true, opacity: 0.3,
                zIndex: 5,
            },
            accent_image: {
                x: 720, y: 150, width: 200, height: 260,
                type: 'image_placeholder',
                rx: 12,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.15)', blur: 12, offsetX: 0, offsetY: 3 },
            },
        },
        optionalSlots: ['quote_mark_left', 'quote_mark_right', 'title', 'context_text', 'accent_image'],
    },

    // -------------------- Advanced Layouts --------------------
    modern_geometric: {
        id: 'modern_geometric',
        name: 'Modern Geometric',
        description: 'Dynamic layout with abstract shapes and offset content',
        category: 'advanced',
        thumbnail: 'modern',
        slots: {
            bg_rect: {
                x: 0, y: 0, width: 20, height: 540,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            triangle_top: {
                x: 800, y: -50, width: 200, height: 200,
                type: 'shape', shapeType: 'triangle',
                useAccentColor: true, opacity: 0.2,
                zIndex: 5,
            },
            circle_bottom: {
                x: 450, y: 450, width: 100, height: 100,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true, opacity: 0.1,
                zIndex: 5,
            },
            title: {
                x: 60, y: 50, width: 400, height: 70,
                type: 'text', textType: 'title',
                fontSize: 42, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 60, y: 125, width: 400, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'bold', textAlign: 'left',
                opacity: 0.8,
                zIndex: 58,
            },
            content: {
                x: 60, y: 170, width: 400, height: 260,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            detail: {
                x: 60, y: 445, width: 400, height: 50,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.6,
                zIndex: 55,
            },
            image: {
                x: 500, y: 60, width: 400, height: 420,
                type: 'image_placeholder',
                zIndex: 20,
            },
        },
        optionalSlots: ['image', 'subtitle', 'detail'],
    },

    title_split: {
        id: 'title_split',
        name: 'Title Split',
        description: 'Title on left with full-height image on right',
        category: 'title',
        thumbnail: 'title_split',
        slots: {
            title: {
                x: 50, y: 120, width: 410, height: 120,
                type: 'text', textType: 'title',
                fontSize: 46, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 50, y: 260, width: 410, height: 60,
                type: 'text', textType: 'subtitle',
                fontSize: 22, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            tagline: {
                x: 50, y: 340, width: 410, height: 35,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            image: {
                x: 500, y: 0, width: 460, height: 540,
                type: 'image_placeholder',
                zIndex: 15,
            },
        },
        optionalSlots: ['subtitle', 'tagline'],
    },

    bullets_with_image: {
        id: 'bullets_with_image',
        name: 'Bullets + Image',
        description: 'Bullet points on left with supporting image on right',
        category: 'content',
        thumbnail: 'bullets_image',
        slots: {
            title: {
                x: 50, y: 35, width: 860, height: 60,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            bullets: {
                x: 60, y: 130, width: 420, height: 370,
                type: 'text', textType: 'body',
                fontSize: 19, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.6,
                zIndex: 60,
            },
            image: {
                x: 510, y: 120, width: 400, height: 380,
                type: 'image_placeholder',
                rx: 12,
                zIndex: 20,
            },
        },
        optionalSlots: [],
    },

    four_cards: {
        id: 'four_cards',
        name: 'Four Cards',
        description: 'Four feature cards with icons for broader overviews',
        category: 'content',
        thumbnail: 'four_cards',
        slots: {
            title: {
                x: 50, y: 30, width: 860, height: 55,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            card1_icon: {
                x: 118, y: 135, width: 44, height: 44,
                type: 'icon', size: 44,
                useAccentColor: true,
                zIndex: 35,
            },
            card1_title: {
                x: 65, y: 200, width: 170, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 17, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card1_desc: {
                x: 60, y: 250, width: 180, height: 220,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            card2_icon: {
                x: 338, y: 135, width: 44, height: 44,
                type: 'icon', size: 44,
                useAccentColor: true,
                zIndex: 35,
            },
            card2_title: {
                x: 285, y: 200, width: 170, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 17, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card2_desc: {
                x: 280, y: 250, width: 180, height: 220,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            card3_icon: {
                x: 558, y: 135, width: 44, height: 44,
                type: 'icon', size: 44,
                useAccentColor: true,
                zIndex: 35,
            },
            card3_title: {
                x: 505, y: 200, width: 170, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 17, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card3_desc: {
                x: 500, y: 250, width: 180, height: 220,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            card4_icon: {
                x: 778, y: 135, width: 44, height: 44,
                type: 'icon', size: 44,
                useAccentColor: true,
                zIndex: 35,
            },
            card4_title: {
                x: 725, y: 200, width: 170, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 17, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card4_desc: {
                x: 720, y: 250, width: 180, height: 220,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
        },
        optionalSlots: ['card1_icon', 'card2_icon', 'card3_icon', 'card4_icon'],
    },

    full_bleed_image: {
        id: 'full_bleed_image',
        name: 'Full Bleed Image',
        description: 'Full-screen background image with text overlay at bottom',
        category: 'media',
        thumbnail: 'full_bleed',
        suggestBackgroundImage: true,
        slots: {
            image: {
                x: 0, y: 0, width: 960, height: 540,
                type: 'image_placeholder',
                zIndex: 5,
            },
            title: {
                x: 60, y: 340, width: 840, height: 80,
                type: 'text', textType: 'title',
                fontSize: 46, fontWeight: 'bold', textAlign: 'left',
                fill: '#ffffff',
                zIndex: 60,
            },
            subtitle: {
                x: 60, y: 420, width: 700, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 22, fontWeight: 'normal', textAlign: 'left',
                fill: '#ffffffcc',
                zIndex: 60,
            },
            tagline: {
                x: 60, y: 470, width: 500, height: 30,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                fill: '#ffffff99',
                zIndex: 55,
            },
        },
        optionalSlots: ['subtitle', 'tagline'],
    },

    timeline: {
        id: 'timeline',
        name: 'Timeline',
        description: 'Horizontal timeline with 4 events and descriptions',
        category: 'content',
        thumbnail: 'timeline',
        slots: {
            title: {
                x: 50, y: 30, width: 700, height: 55,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            event1_date: {
                x: 50, y: 135, width: 180, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            event1_title: {
                x: 50, y: 230, width: 180, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 17, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            event1_desc: {
                x: 50, y: 280, width: 180, height: 200,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            event2_date: {
                x: 260, y: 135, width: 180, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            event2_title: {
                x: 260, y: 230, width: 180, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 17, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            event2_desc: {
                x: 260, y: 280, width: 180, height: 200,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            event3_date: {
                x: 470, y: 135, width: 180, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            event3_title: {
                x: 470, y: 230, width: 180, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 17, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            event3_desc: {
                x: 470, y: 280, width: 180, height: 200,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            event4_date: {
                x: 680, y: 135, width: 180, height: 30,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            event4_title: {
                x: 680, y: 230, width: 180, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 17, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            event4_desc: {
                x: 680, y: 280, width: 180, height: 200,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            accent_image: {
                x: 790, y: 25, width: 140, height: 85,
                type: 'image_placeholder',
                rx: 10,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.10)', blur: 10, offsetX: 0, offsetY: 3 },
            },
        },
        optionalSlots: ['event1_date', 'event1_desc', 'event2_date', 'event2_desc', 'event3_date', 'event3_desc', 'event4_date', 'event4_desc', 'accent_image'],
    },

    chart_focus: {
        id: 'chart_focus',
        name: 'Chart Focus',
        description: 'Large chart taking most of the slide with title and insights',
        category: 'data',
        thumbnail: 'chart',
        slots: {
            title: {
                x: 50, y: 30, width: 640, height: 55,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            key_insight: {
                x: 700, y: 35, width: 250, height: 45,
                type: 'text', textType: 'body',
                fontSize: 15, fontWeight: 'bold', textAlign: 'right',
                opacity: 0.8,
                zIndex: 55,
            },
            description: {
                x: 50, y: 90, width: 500, height: 35,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            chart: {
                x: 50, y: 140, width: 860, height: 340,
                type: 'chart',
                zIndex: 50,
            },
            source_note: {
                x: 50, y: 490, width: 860, height: 25,
                type: 'text', textType: 'body',
                fontSize: 12, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.5,
                zIndex: 50,
            },
        },
        optionalSlots: ['description', 'key_insight', 'source_note'],
    },

    stats_highlight: {
        id: 'stats_highlight',
        name: 'Stats Highlight',
        description: 'Three prominent statistics with labels and descriptions',
        category: 'data',
        thumbnail: 'stats',
        slots: {
            title: {
                x: 50, y: 35, width: 700, height: 55,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            stat1_value: {
                x: 40, y: 170, width: 210, height: 80,
                type: 'text', textType: 'title',
                fontSize: 56, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            stat1_label: {
                x: 40, y: 260, width: 210, height: 50,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            stat1_desc: {
                x: 45, y: 315, width: 200, height: 100,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'center',
                opacity: 0.7,
                zIndex: 55,
            },
            stat2_value: {
                x: 270, y: 170, width: 210, height: 80,
                type: 'text', textType: 'title',
                fontSize: 56, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            stat2_label: {
                x: 270, y: 260, width: 210, height: 50,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            stat2_desc: {
                x: 275, y: 315, width: 200, height: 100,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'center',
                opacity: 0.7,
                zIndex: 55,
            },
            stat3_value: {
                x: 500, y: 170, width: 210, height: 80,
                type: 'text', textType: 'title',
                fontSize: 56, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            stat3_label: {
                x: 500, y: 260, width: 210, height: 50,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            stat3_desc: {
                x: 505, y: 315, width: 200, height: 100,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'center',
                opacity: 0.7,
                zIndex: 55,
            },
            accent_image: {
                x: 730, y: 130, width: 200, height: 290,
                type: 'image_placeholder',
                rx: 12,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.10)', blur: 12, offsetX: 0, offsetY: 3 },
            },
        },
        optionalSlots: ['stat1_desc', 'stat2_desc', 'stat3_desc', 'accent_image'],
    },

    big_number: {
        id: 'big_number',
        name: 'Big Number',
        description: 'Single prominent statistic with context',
        category: 'data',
        thumbnail: 'big_number',
        suggestBackgroundImage: true,
        slots: {
            metric: {
                x: 100, y: 100, width: 760, height: 130,
                type: 'text', textType: 'title',
                fontSize: 96, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            label: {
                x: 80, y: 250, width: 540, height: 60,
                type: 'text', textType: 'subtitle',
                fontSize: 30, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            context: {
                x: 80, y: 330, width: 480, height: 80,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.8,
                zIndex: 55,
            },
            accent_image: {
                x: 690, y: 240, width: 230, height: 220,
                type: 'image_placeholder',
                rx: 12,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.15)', blur: 14, offsetX: 0, offsetY: 4 },
            },
        },
        optionalSlots: ['context', 'accent_image'],
    },

    comparison: {
        id: 'comparison',
        name: 'Comparison',
        description: 'Side-by-side comparison with distinct headers and content',
        category: 'content',
        thumbnail: 'comparison',
        slots: {
            title: {
                x: 50, y: 30, width: 690, height: 55,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            left_header: {
                x: 60, y: 120, width: 400, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 24, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            left_content: {
                x: 70, y: 185, width: 380, height: 310,
                type: 'text', textType: 'body',
                fontSize: 17, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            right_header: {
                x: 500, y: 120, width: 400, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 24, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            right_content: {
                x: 510, y: 185, width: 380, height: 310,
                type: 'text', textType: 'body',
                fontSize: 17, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 60,
            },
            accent_image: {
                x: 770, y: 25, width: 160, height: 80,
                type: 'image_placeholder',
                rx: 10,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.10)', blur: 10, offsetX: 0, offsetY: 3 },
            },
        },
        optionalSlots: ['accent_image'],
    },

    section_break: {
        id: 'section_break',
        name: 'Section Break',
        description: 'Clean section divider with centered heading and context',
        category: 'title',
        thumbnail: 'section',
        suggestBackgroundImage: true,
        slots: {
            section_title: {
                x: 50, y: 150, width: 560, height: 90,
                type: 'text', textType: 'title',
                fontSize: 48, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 50, y: 260, width: 520, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 22, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            description: {
                x: 50, y: 330, width: 480, height: 80,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.5,
                zIndex: 50,
            },
            accent_image: {
                x: 650, y: 150, width: 270, height: 260,
                type: 'image_placeholder',
                rx: 14,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.15)', blur: 14, offsetX: 0, offsetY: 4 },
            },
        },
        optionalSlots: ['subtitle', 'description', 'accent_image'],
    },

    closing: {
        id: 'closing',
        name: 'Closing',
        description: 'Closing slide with call-to-action',
        category: 'title',
        thumbnail: 'closing',
        suggestBackgroundImage: true,
        slots: {
            title: {
                x: 50, y: 140, width: 560, height: 100,
                type: 'text', textType: 'title',
                fontSize: 48, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 50, y: 260, width: 520, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 24, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            cta_text: {
                x: 50, y: 340, width: 480, height: 45,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            description: {
                x: 50, y: 400, width: 520, height: 80,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 55,
            },
            accent_image: {
                x: 650, y: 150, width: 270, height: 250,
                type: 'image_placeholder',
                rx: 14,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.15)', blur: 14, offsetX: 0, offsetY: 4 },
            },
        },
        optionalSlots: ['subtitle', 'cta_text', 'description', 'accent_image'],
        decorations: [
            { type: 'shape', shapeType: 'rectangle', x: 330, y: 490, width: 300, height: 4, useAccentColor: true, rx: 2, zIndex: 10 },
            { type: 'shape', shapeType: 'circle', x: -30, y: -30, width: 200, height: 200, useAccentColor: true, opacity: 0.1, zIndex: 5 },
            { type: 'shape', shapeType: 'circle', x: 790, y: 380, width: 200, height: 200, useAccentColor: true, opacity: 0.1, zIndex: 5 },
        ],
    },

    data_dashboard: {
        id: 'data_dashboard',
        name: 'Data Dashboard',
        description: 'Four-quadrant layout for metrics and charts',
        category: 'data',
        thumbnail: 'dashboard',
        slots: {
            title: {
                x: 50, y: 30, width: 860, height: 50,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            // Top Left - Metric 1
            metric1_value: {
                x: 70, y: 115, width: 180, height: 50,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            metric1_label: {
                x: 70, y: 170, width: 180, height: 30,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            // Top Right - Metric 2
            metric2_value: {
                x: 280, y: 115, width: 180, height: 50,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            metric2_label: {
                x: 280, y: 170, width: 180, height: 30,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            // Bottom Row - Stats
            stat1_value: {
                x: 70, y: 240, width: 180, height: 50,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            stat1_label: {
                x: 70, y: 295, width: 180, height: 60,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            stat2_value: {
                x: 280, y: 240, width: 180, height: 50,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            stat2_label: {
                x: 280, y: 295, width: 180, height: 60,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            // Right side - Chart
            chart: {
                x: 500, y: 100, width: 410, height: 380,
                type: 'chart',
                zIndex: 50,
            },
        },
        optionalSlots: ['metric2_value', 'metric2_label', 'stat1_value', 'stat1_label', 'stat2_value', 'stat2_label', 'chart'],
    },
};

// ==================== Template Categories ====================

export const TEMPLATE_CATEGORIES = [
    { id: 'title', name: 'Title & Closing', icon: 'layout' },
    { id: 'content', name: 'Content', icon: 'file-text' },
    { id: 'media', name: 'With Images', icon: 'image' },
    { id: 'data', name: 'Data & Charts', icon: 'bar-chart' },
    { id: 'advanced', name: 'Advanced', icon: 'star' },
];

// ==================== Helper Functions ====================

/**
 * Get all templates as array
 */
export function getTemplateList() {
    return Object.values(SLIDE_TEMPLATES);
}

/**
 * Get templates by category
 */
export function getTemplatesByCategory(category) {
    return Object.values(SLIDE_TEMPLATES).filter(t => t.category === category);
}

/**
 * Get template by ID
 */
export function getTemplate(templateId) {
    return SLIDE_TEMPLATES[templateId] || null;
}

/**
 * Apply style colors to a template
 * @param {Object} template - Template definition
 * @param {Object} style - Presentation style with colors
 * @returns {Object} - Template with colors applied
 */
/**
 * Detect whether a hex color is perceptually dark.
 * Used to enforce strict body-text contrast: white on dark bg, near-black on light bg.
 */
function _isColorDarkForContrast(hex) {
    try {
        const h = (hex || '').replace('#', '');
        if (h.length < 6) return false;
        const r = parseInt(h.slice(0, 2), 16);
        const g = parseInt(h.slice(2, 4), 16);
        const b = parseInt(h.slice(4, 6), 16);
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5;
    } catch (e) { return false; }
}

export function applyStyleToTemplate(template, style) {
    if (!template || !style) return template;

    const styledSlots = {};
    const accentColor = style.accentColor || '#3B82F6';
    const cardBg = style.cardBackground || '#f8fafc';
    const textPrimary = style.textPrimary || style.textStyles?.title?.color || '#111827';
    const textSecondary = style.textSecondary || style.textStyles?.body?.color || '#374151';
    const slideBackground = style.slideBackground || '#ffffff';

    // Determine if the slide background is dark — drives strict body text color.
    // INSTRUCTION: body/detail text MUST use white shades on dark backgrounds,
    // black shades on light backgrounds. Never use grey for readable body text.
    const bgIsDark = _isColorDarkForContrast(slideBackground);
    // Strict body text color: white on dark bg, near-black on light bg
    const strictBodyTextColor = bgIsDark ? '#FFFFFF' : '#1F2937';
    // Title color: validate textPrimary against bg; fallback to strict if bad contrast
    const strictTitleColor = (bgIsDark && _isColorDarkForContrast(textPrimary))
        ? '#FFFFFF'
        : (!bgIsDark && !_isColorDarkForContrast(textPrimary))
            ? '#111827'
            : textPrimary;
    const colorInstruction = bgIsDark
        ? 'Use white or near-white shades only (#FFFFFF, #F9FAFB, #F3F4F6) — dark background theme'
        : 'Use black or near-black shades only (#111827, #1F2937, #374151) — light background theme';

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
        // STRICT RULE: body/detail text must always use high-contrast colors
        // based on background — white shades on dark bg, black shades on light bg.
        if (slot.type === 'text') {
            if (slot.useWhiteText) {
                styledSlot.fill = '#ffffff';
            } else if (slot.textType === 'title' || slot.textType === 'subtitle') {
                styledSlot.fill = strictTitleColor;
            } else {
                // Body / detail text: strictly enforce contrast color
                styledSlot.fill = strictBodyTextColor;
                // Embed the color instruction so renderers and the AI know the rule
                styledSlot.colorInstruction = colorInstruction;
            }
        }

        styledSlots[slotName] = styledSlot;
    }

    return {
        ...template,
        slots: styledSlots,
        backgroundColor: slideBackground,
    };
}

/**
 * Get template names list for AI prompt
 */
export function getTemplateNamesForPrompt() {
    return Object.entries(SLIDE_TEMPLATES).map(([id, t]) =>
        `- ${id}: ${t.description}`
    ).join('\n');
}

/**
 * Get slot structure for a template (for AI prompt)
 */
export function getTemplateSlotsForPrompt(templateId) {
    const template = SLIDE_TEMPLATES[templateId];
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
 * Create a new slide object from a template ID
 * @param {string} templateId - Template ID
 * @param {Object} style - Presentation style
 * @returns {Object} - New slide object with elements
 */
export function createSlideFromTemplate(templateId, style) {
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
            // Text elements MUST be fully opaque so their fill color renders at full strength.
            // Opacity on text makes the text semi-transparent regardless of fill, producing
            // grey-looking text on dark backgrounds. Non-text elements keep their slot opacity.
            opacity: slot.type === 'text' ? 1 : (slot.opacity || 1),
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
            // Blank SVG diagram placeholder — UI shows a dashed-rect placeholder
            // until the LLM (or user) supplies svgContent. fillColor seeds currentColor.
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
        id: `slide_${timestamp}`,
        elements,
        background: styledTemplate.backgroundColor,
        notes: '',
    };
}

export default SLIDE_TEMPLATES;
