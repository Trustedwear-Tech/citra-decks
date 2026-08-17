// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

/**
 * EmbedNode.js - Custom TipTap extension for embedding videos and external content
 * 
 * Supports: YouTube, Vimeo, Loom, Spotify, Figma, Google Drive, Miro, Airtable, 
 * PowerBI, Calendly, Typeform, Google Forms, Tally, and generic webpages
 */

import { Node, mergeAttributes } from '@tiptap/core';
import { ReactNodeViewRenderer } from '@tiptap/react';
import EmbedComponent from './EmbedComponent';

export const EmbedNode = Node.create({
    name: 'embed',
    group: 'block',
    atom: true, // Treated as a single unit, not editable internally
    draggable: true,

    addAttributes() {
        return {
            src: {
                default: null,
            },
            embedType: {
                default: 'webpage', // youtube, vimeo, loom, spotify, figma, google, miro, etc.
            },
            provider: {
                default: 'Unknown',
            },
            title: {
                default: '',
            },
            thumbnail: {
                default: null,
            },
            html: {
                default: null, // Original embed HTML from oEmbed
            },
            videoId: {
                default: null, // Platform-specific ID (for YouTube, Vimeo, etc.)
            },
            width: {
                default: 640,
            },
            height: {
                default: 360,
            },
        };
    },

    parseHTML() {
        return [
            {
                tag: 'div[data-embed-type]',
                getAttrs: (dom) => ({
                    src: dom.getAttribute('data-embed-src'),
                    embedType: dom.getAttribute('data-embed-type'),
                    provider: dom.getAttribute('data-embed-provider'),
                    title: dom.getAttribute('data-embed-title'),
                    thumbnail: dom.getAttribute('data-embed-thumbnail'),
                    html: dom.getAttribute('data-embed-html'),
                    videoId: dom.getAttribute('data-embed-video-id'),
                    width: parseInt(dom.getAttribute('data-embed-width')) || 640,
                    height: parseInt(dom.getAttribute('data-embed-height')) || 360,
                }),
            },
        ];
    },

    renderHTML({ HTMLAttributes }) {
        const { src, embedType, provider, title, thumbnail, html, videoId, width, height } = HTMLAttributes;
        
        return [
            'div',
            mergeAttributes({
                'data-embed-type': embedType,
                'data-embed-src': src,
                'data-embed-provider': provider,
                'data-embed-title': title,
                'data-embed-thumbnail': thumbnail,
                'data-embed-html': html,
                'data-embed-video-id': videoId,
                'data-embed-width': width,
                'data-embed-height': height,
                'data-user-media': 'true', // Mark as user-inserted media
                'class': 'tiptap-embed-wrapper',
            }),
        ];
    },

    addNodeView() {
        return ReactNodeViewRenderer(EmbedComponent);
    },

    addCommands() {
        return {
            insertEmbed: (options) => ({ commands }) => {
                return commands.insertContent({
                    type: this.name,
                    attrs: options,
                });
            },
            deleteEmbed: () => ({ commands }) => {
                return commands.deleteSelection();
            },
        };
    },
});

export default EmbedNode;
