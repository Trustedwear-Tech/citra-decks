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
        description: 'Centered title with optional subtitle and decorative accents',
        category: 'title',
        thumbnail: 'title',
        slots: {
            title: {
                x: 60, y: 400, width: 674, height: 80,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            subtitle: {
                x: 100, y: 500, width: 594, height: 60,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'normal', textAlign: 'center',
                zIndex: 60,
            },
            tagline: {
                x: 100, y: 580, width: 594, height: 40,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'center',
                opacity: 0.7,
                zIndex: 55,
            },
            description: {
                x: 100, y: 650, width: 594, height: 120,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.5,
                zIndex: 55,
            },
            accent_circle_1: {
                x: 60, y: 900, width: 80, height: 80,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true, opacity: 0.3,
                zIndex: 5,
            },
            accent_circle_2: {
                x: 654, y: 880, width: 100, height: 100,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true, opacity: 0.2,
                zIndex: 5,
            },
        },
        optionalSlots: ['subtitle', 'tagline', 'description', 'accent_circle_1', 'accent_circle_2'],
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
        optionalSlots: ['subtitle', 'image', 'highlights_title', 'highlight_1', 'highlight_2', 'description'],
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
                x: 50, y: 40, width: 694, height: 70,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            divider: {
                x: 50, y: 115, width: 694, height: 3,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true,
                zIndex: 10,
            },
            bullets: {
                x: 60, y: 140, width: 674, height: 900,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
        },
        optionalSlots: ['divider'],
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
            // Card 1 (218px wide with 20px gaps)
            card1_bg: {
                x: 50, y: 120, width: 218, height: 400,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 12,
                zIndex: 8,
            },
            card1_icon: {
                x: 127, y: 145, width: 48, height: 48,
                type: 'icon', size: 48,
                useAccentColor: true,
                zIndex: 35,
            },
            card1_title: {
                x: 60, y: 215, width: 198, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card1_desc: {
                x: 60, y: 270, width: 198, height: 230,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            // Card 2
            card2_bg: {
                x: 288, y: 120, width: 218, height: 400,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 12,
                zIndex: 8,
            },
            card2_icon: {
                x: 365, y: 145, width: 48, height: 48,
                type: 'icon', size: 48,
                useAccentColor: true,
                zIndex: 35,
            },
            card2_title: {
                x: 298, y: 215, width: 198, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card2_desc: {
                x: 298, y: 270, width: 198, height: 230,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
                lineHeight: 1.3,
                zIndex: 60,
            },
            // Card 3
            card3_bg: {
                x: 526, y: 120, width: 218, height: 400,
                type: 'shape', shapeType: 'rectangle',
                useCardBackground: true, rx: 12,
                zIndex: 8,
            },
            card3_icon: {
                x: 603, y: 145, width: 48, height: 48,
                type: 'icon', size: 48,
                useAccentColor: true,
                zIndex: 35,
            },
            card3_title: {
                x: 536, y: 215, width: 198, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 16, fontWeight: 'bold', textAlign: 'center',
                lineHeight: 1.2,
                zIndex: 60,
            },
            card3_desc: {
                x: 536, y: 270, width: 198, height: 230,
                type: 'text', textType: 'body',
                fontSize: 13, fontWeight: 'normal', textAlign: 'center',
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
                x: 50, y: 40, width: 694, height: 60,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            image: {
                x: 50, y: 120, width: 327, height: 400,
                type: 'image_placeholder',
                zIndex: 20,
            },
            content_title: {
                x: 397, y: 130, width: 347, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 22, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            content: {
                x: 397, y: 195, width: 347, height: 320,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
        },
        optionalSlots: ['content_title'],
    },

    image_right: {
        id: 'image_right',
        name: 'Image Right',
        description: 'Text content on left with large image on right',
        category: 'media',
        thumbnail: 'image_right',
        slots: {
            title: {
                x: 50, y: 40, width: 694, height: 60,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            content_title: {
                x: 50, y: 130, width: 327, height: 50,
                type: 'text', textType: 'subtitle',
                fontSize: 22, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            content: {
                x: 50, y: 195, width: 327, height: 320,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            image: {
                x: 397, y: 120, width: 347, height: 400,
                type: 'image_placeholder',
                zIndex: 20,
            },
        },
        optionalSlots: ['content_title'],
    },

    process_steps: {
        id: 'process_steps',
        name: 'Process Steps',
        description: 'Numbered steps for workflows or timelines - vertical layout for A4',
        category: 'content',
        thumbnail: 'process',
        slots: {
            title: {
                x: 50, y: 40, width: 694, height: 60,
                type: 'text', textType: 'title',
                fontSize: 32, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            // Step 1 - Vertical layout
            step1_circle: {
                x: 60, y: 130, width: 50, height: 50,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true,
                zIndex: 15,
            },
            step1_number: {
                x: 60, y: 135, width: 50, height: 40,
                type: 'text', textType: 'body',
                fontSize: 24, fontWeight: 'bold', textAlign: 'center',
                useWhiteText: true,
                zIndex: 60,
            },
            step1_title: {
                x: 130, y: 130, width: 614, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'bold', textAlign: 'left',
                lineHeight: 1.2,
                zIndex: 60,
            },
            step1_desc: {
                x: 130, y: 165, width: 614, height: 60,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
            // Connector 1-2
            connector1: {
                x: 83, y: 185, width: 4, height: 50,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.5,
                zIndex: 10,
            },
            // Step 2
            step2_circle: {
                x: 60, y: 245, width: 50, height: 50,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true,
                zIndex: 15,
            },
            step2_number: {
                x: 60, y: 250, width: 50, height: 40,
                type: 'text', textType: 'body',
                fontSize: 24, fontWeight: 'bold', textAlign: 'center',
                useWhiteText: true,
                zIndex: 60,
            },
            step2_title: {
                x: 130, y: 245, width: 614, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'bold', textAlign: 'left',
                lineHeight: 1.2,
                zIndex: 60,
            },
            step2_desc: {
                x: 130, y: 280, width: 614, height: 60,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
            // Connector 2-3
            connector2: {
                x: 83, y: 300, width: 4, height: 50,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.5,
                zIndex: 10,
            },
            // Step 3
            step3_circle: {
                x: 60, y: 360, width: 50, height: 50,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true,
                zIndex: 15,
            },
            step3_number: {
                x: 60, y: 365, width: 50, height: 40,
                type: 'text', textType: 'body',
                fontSize: 24, fontWeight: 'bold', textAlign: 'center',
                useWhiteText: true,
                zIndex: 60,
            },
            step3_title: {
                x: 130, y: 360, width: 614, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'bold', textAlign: 'left',
                lineHeight: 1.2,
                zIndex: 60,
            },
            step3_desc: {
                x: 130, y: 395, width: 614, height: 60,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
            // Connector 3-4
            connector3: {
                x: 83, y: 415, width: 4, height: 50,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.5,
                zIndex: 10,
            },
            // Step 4
            step4_circle: {
                x: 60, y: 475, width: 50, height: 50,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true,
                zIndex: 15,
            },
            step4_number: {
                x: 60, y: 480, width: 50, height: 40,
                type: 'text', textType: 'body',
                fontSize: 24, fontWeight: 'bold', textAlign: 'center',
                useWhiteText: true,
                zIndex: 60,
            },
            step4_title: {
                x: 130, y: 475, width: 614, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'bold', textAlign: 'left',
                lineHeight: 1.2,
                zIndex: 60,
            },
            step4_desc: {
                x: 130, y: 510, width: 614, height: 60,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
            // Connector 4-5 (optional)
            connector4: {
                x: 83, y: 530, width: 4, height: 50,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, opacity: 0.5,
                zIndex: 10,
            },
            // Step 5 (optional)
            step5_circle: {
                x: 60, y: 590, width: 50, height: 50,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true,
                zIndex: 15,
            },
            step5_number: {
                x: 60, y: 595, width: 50, height: 40,
                type: 'text', textType: 'body',
                fontSize: 24, fontWeight: 'bold', textAlign: 'center',
                useWhiteText: true,
                zIndex: 60,
            },
            step5_title: {
                x: 130, y: 590, width: 614, height: 35,
                type: 'text', textType: 'subtitle',
                fontSize: 18, fontWeight: 'bold', textAlign: 'left',
                lineHeight: 1.2,
                zIndex: 60,
            },
            step5_desc: {
                x: 130, y: 625, width: 614, height: 60,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.4,
                zIndex: 60,
            },
        },
        optionalSlots: ['step5_circle', 'step5_number', 'step5_title', 'step5_desc', 'connector4'],
    },

    quote: {
        id: 'quote',
        name: 'Quote',
        description: 'Highlighted quote with attribution',
        category: 'content',
        thumbnail: 'quote',
        slots: {
            quote_mark_left: {
                x: 50, y: 120, width: 80, height: 80,
                type: 'text', textType: 'body',
                content: '"', // Fixed content
                fontSize: 120, fontWeight: 'bold', textAlign: 'left',
                useAccentColor: true, opacity: 0.3,
                zIndex: 5,
            },
            quote_text: {
                x: 100, y: 180, width: 760, height: 200,
                type: 'text', textType: 'body',
                fontSize: 32, fontWeight: 'normal', textAlign: 'center',
                fontStyle: 'italic',
                zIndex: 60,
            },
            attribution: {
                x: 100, y: 400, width: 760, height: 40,
                type: 'text', textType: 'subtitle',
                fontSize: 20, fontWeight: 'bold', textAlign: 'center',
                zIndex: 60,
            },
            quote_mark_right: {
                x: 664, y: 320, width: 80, height: 80,
                type: 'text', textType: 'body',
                content: '"', // Fixed content
                fontSize: 100, fontWeight: 'bold', textAlign: 'right',
                useAccentColor: true, opacity: 0.3,
                zIndex: 5,
            },
        },
        optionalSlots: ['quote_mark_left', 'quote_mark_right'],
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
                x: 60, y: 60, width: 350, height: 100,
                type: 'text', textType: 'title',
                fontSize: 36, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            content: {
                x: 60, y: 180, width: 350, height: 500,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            image: {
                x: 420, y: 60, width: 324, height: 420,
                type: 'image_placeholder',
                zIndex: 20,
            },
        },
        optionalSlots: ['image'],
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
        },
        optionalSlots: ['metric_2'],
    },

    // ==================== SECTION / CLOSING PAGES ====================

    section_break: {
        id: 'section_break',
        name: 'Section Break',
        description: 'Clean section divider with centered heading',
        category: 'title',
        thumbnail: 'section_break',
        slots: {
            section_title: {
                x: 60, y: 370, width: 440, height: 100,
                type: 'text', textType: 'title',
                fontSize: 44, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 60, y: 490, width: 420, height: 60,
                type: 'text', textType: 'subtitle',
                fontSize: 22, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            description: {
                x: 60, y: 570, width: 400, height: 80,
                type: 'text', textType: 'body',
                fontSize: 16, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.5,
                zIndex: 50,
            },
            accent_line: {
                x: 60, y: 680, width: 200, height: 4,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, rx: 2,
                zIndex: 10,
            },
            accent_circle_1: {
                x: 30, y: 30, width: 160, height: 160,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true, opacity: 0.08,
                zIndex: 5,
            },
            accent_circle_2: {
                x: 604, y: 900, width: 180, height: 180,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true, opacity: 0.06,
                zIndex: 5,
            },
            accent_image: {
                x: 520, y: 370, width: 240, height: 260,
                type: 'image_placeholder', rx: 14,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.15)', blur: 14, offsetX: 0, offsetY: 4 },
            },
        },
        optionalSlots: ['subtitle', 'description', 'accent_line', 'accent_circle_1', 'accent_circle_2', 'accent_image'],
    },

    closing: {
        id: 'closing',
        name: 'Closing',
        description: 'Closing page with call-to-action',
        category: 'title',
        thumbnail: 'closing',
        slots: {
            title: {
                x: 60, y: 350, width: 440, height: 120,
                type: 'text', textType: 'title',
                fontSize: 44, fontWeight: 'bold', textAlign: 'left',
                zIndex: 60,
            },
            subtitle: {
                x: 60, y: 490, width: 420, height: 60,
                type: 'text', textType: 'subtitle',
                fontSize: 24, fontWeight: 'normal', textAlign: 'left',
                zIndex: 60,
            },
            cta_text: {
                x: 60, y: 580, width: 400, height: 50,
                type: 'text', textType: 'body',
                fontSize: 18, fontWeight: 'normal', textAlign: 'left',
                opacity: 0.7,
                zIndex: 55,
            },
            description: {
                x: 60, y: 660, width: 420, height: 130,
                type: 'text', textType: 'body',
                fontSize: 14, fontWeight: 'normal', textAlign: 'left',
                lineHeight: 1.5,
                zIndex: 55,
            },
            accent_line: {
                x: 60, y: 830, width: 300, height: 4,
                type: 'shape', shapeType: 'rectangle',
                useAccentColor: true, rx: 2,
                zIndex: 10,
            },
            accent_circle_1: {
                x: -30, y: -30, width: 200, height: 200,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true, opacity: 0.1,
                zIndex: 5,
            },
            accent_circle_2: {
                x: 624, y: 950, width: 200, height: 200,
                type: 'shape', shapeType: 'circle',
                useAccentColor: true, opacity: 0.1,
                zIndex: 5,
            },
            accent_image: {
                x: 520, y: 350, width: 240, height: 280,
                type: 'image_placeholder', rx: 14,
                zIndex: 20,
                shadow: { color: 'rgba(0,0,0,0.15)', blur: 14, offsetX: 0, offsetY: 4 },
            },
        },
        optionalSlots: ['subtitle', 'cta_text', 'description', 'accent_line', 'accent_circle_1', 'accent_circle_2', 'accent_image'],
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

    // Determine if the page background is dark — drives strict body text color.
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
 * Create a new slide object from a template ID
 * @param {string} templateId - Template ID
 * @param {Object} style - Presentation style
 * @returns {Object} - New slide object with elements
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

// Backward compatibility alias
export const SLIDE_TEMPLATES = PAGE_TEMPLATES;
export default PAGE_TEMPLATES;
