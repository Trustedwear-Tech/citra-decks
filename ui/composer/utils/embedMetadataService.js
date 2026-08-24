// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

/**
 * Embed Metadata Service
 * 
 * Fetches oEmbed/metadata for any URL using a cascade:
 * 1. NoEmbed (free, CORS-friendly)
 * 2. Iframely (paid, comprehensive) 
 * 3. Manual regex-based fallback
 */

const IFRAMELY_KEY = '202c86afc166ce8c29a1d5cc1e3adec8';

/**
 * Extract iframe src from raw HTML
 * @param {string} html - Raw HTML string containing iframe
 * @returns {string|null} - Extracted src URL or null
 */
function extractIframeSrc(html) {
    // Match iframe src attribute (handles both single and double quotes)
    const srcMatch = html.match(/<iframe[^>]+src=["']([^"']+)["']/i);
    return srcMatch ? srcMatch[1] : null;
}

/**
 * Main entry point - fetches embed metadata for any URL
 * @param {string} url - The URL to fetch metadata for (or raw iframe HTML)
 * @returns {Promise<Object>} Metadata object with type, provider, title, thumbnail, etc.
 */
export async function fetchEmbedMetadata(url) {
    console.log('🔍 [EMBED_SERVICE] Fetching metadata for:', url);
    console.log('🔍 [EMBED_SERVICE] URL type:', typeof url);
    console.log('🔍 [EMBED_SERVICE] URL length:', url?.length);

    // Check if user pasted raw iframe HTML instead of URL
    if (url.trim().startsWith('<iframe')) {
        console.log('🎬 [EMBED_SERVICE] Detected iframe HTML in service');
        const extractedSrc = extractIframeSrc(url);
        if (extractedSrc) {
            console.log('✅ [EMBED_SERVICE] Extracted iframe src:', extractedSrc);
            url = extractedSrc; // Use extracted URL instead
        } else {
            console.error('❌ [EMBED_SERVICE] Failed to extract src from iframe HTML');
            throw new Error('Could not extract URL from iframe code. Please paste the URL directly.');
        }
    }

    // FAST PATH: For providers where our manual fallback is better than oEmbed
    // (e.g., Miro - oEmbed omits autoplay, uses different share links)
    const urlLower = url.toLowerCase();
    if (urlLower.includes('miro.com') || urlLower.includes('figma.com')) {
        console.log('⚡ [EMBED_SERVICE] Using direct fallback for known provider (skipping oEmbed)');
        const fallbackResult = manualFallback(url);
        console.log('📦 [EMBED_SERVICE] Direct fallback result:', fallbackResult);
        return fallbackResult;
    }

    // 1. Try NoEmbed first (free, CORS-friendly)
    try {
        console.log('🌐 [EMBED_SERVICE] Trying NoEmbed...');
        const noembedResult = await tryNoembed(url);
        console.log('📦 [EMBED_SERVICE] Raw NoEmbed response:', noembedResult);
        if (noembedResult && !noembedResult.error) {
            console.log('✅ [EMBED_SERVICE] NoEmbed success:', noembedResult.provider_name);
            const normalized = normalizeMetadata(noembedResult, 'noembed');
            console.log('📦 [EMBED_SERVICE] Normalized metadata:', normalized);
            return normalized;
        }
    } catch (err) {
        console.warn('⚠️ [EMBED_SERVICE] NoEmbed failed:', err.message);
    }

    // 2. Fallback to Iframely (paid, comprehensive)
    try {
        console.log('🌐 [EMBED_SERVICE] Trying Iframely...');
        const iframelyResult = await tryIframely(url);
        if (iframelyResult && !iframelyResult.error) {
            console.log('✅ [EMBED_SERVICE] Iframely success:', iframelyResult.meta?.site);
            return normalizeMetadata(iframelyResult, 'iframely');
        }
    } catch (err) {
        console.warn('⚠️ [EMBED_SERVICE] Iframely failed:', err.message);
    }

    // 3. Manual fallback (regex-based detection)
    console.log('🔧 [EMBED_SERVICE] Using manual fallback for:', url);
    const fallbackResult = manualFallback(url);
    console.log('📦 [EMBED_SERVICE] Manual fallback result:', fallbackResult);
    return fallbackResult;
}

/**
 * Try fetching from NoEmbed
 */
async function tryNoembed(url) {
    const response = await fetch(`https://noembed.com/embed?url=${encodeURIComponent(url)}`);
    if (!response.ok) throw new Error(`NoEmbed HTTP ${response.status}`);
    return await response.json();
}

/**
 * Try fetching from Iframely
 */
async function tryIframely(url) {
    const endpoint = `https://iframe.ly/api/iframely?url=${encodeURIComponent(url)}&key=${IFRAMELY_KEY}`;
    const response = await fetch(endpoint);
    if (!response.ok) throw new Error(`Iframely HTTP ${response.status}`);
    return await response.json();
}

/**
 * Extract YouTube video ID from URL
 */
function getYoutubeId(url) {
    const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
    const match = url.match(regExp);
    return (match && match[2].length === 11) ? match[2] : null;
}

/**
 * Extract Vimeo video ID from URL
 */
function getVimeoId(url) {
    const regExp = /vimeo\.com\/(?:channels\/(?:\w+\/)?|groups\/(?:[^\/]*)\/videos\/|album\/(?:\d+)\/video\/|video\/|)(\d+)(?:$|\/|\?)/;
    const match = url.match(regExp);
    return match ? match[1] : null;
}

/**
 * Extract Loom video ID from URL
 */
function getLoomId(url) {
    const regExp = /loom\.com\/(?:share|embed)\/([a-zA-Z0-9]+)/;
    const match = url.match(regExp);
    return match ? match[1] : null;
}

/**
 * Manual fallback for common providers
 */
function manualFallback(url) {
    const urlLower = url.toLowerCase();

    // YouTube
    if (urlLower.includes('youtube.com') || urlLower.includes('youtu.be')) {
        const id = getYoutubeId(url);
        return {
            type: 'video',
            provider: 'YouTube',
            videoType: 'youtube',
            videoId: id,
            title: 'YouTube Video',
            thumbnail_url: id ? `https://img.youtube.com/vi/${id}/maxresdefault.jpg` : null,
            url: url,
            html: id ? `<iframe src="https://www.youtube.com/embed/${id}" frameborder="0" allowfullscreen></iframe>` : null
        };
    }

    // Vimeo
    if (urlLower.includes('vimeo.com')) {
        const id = getVimeoId(url);
        return {
            type: 'video',
            provider: 'Vimeo',
            videoType: 'vimeo',
            videoId: id,
            title: 'Vimeo Video',
            thumbnail_url: null, // Vimeo needs API call for thumbnail
            url: url,
            html: id ? `<iframe src="https://player.vimeo.com/video/${id}" frameborder="0" allowfullscreen></iframe>` : null
        };
    }

    // Loom
    if (urlLower.includes('loom.com')) {
        const id = getLoomId(url);
        return {
            type: 'video',
            provider: 'Loom',
            videoType: 'loom',
            videoId: id,
            title: 'Loom Recording',
            thumbnail_url: id ? `https://cdn.loom.com/sessions/thumbnails/${id}-with-play.gif` : null,
            url: url,
            html: id ? `<iframe src="https://www.loom.com/embed/${id}" frameborder="0" allowfullscreen></iframe>` : null
        };
    }

    // Spotify
    if (urlLower.includes('spotify.com')) {
        // Extract Spotify URI path (track, album, playlist, episode)
        const match = url.match(/spotify\.com\/(track|album|playlist|episode)\/([a-zA-Z0-9]+)/);
        const type = match ? match[1] : 'track';
        const id = match ? match[2] : null;
        return {
            type: 'audio',
            provider: 'Spotify',
            videoType: 'spotify',
            videoId: id,
            title: `Spotify ${type.charAt(0).toUpperCase() + type.slice(1)}`,
            thumbnail_url: null,
            url: url,
            html: id ? `<iframe src="https://open.spotify.com/embed/${type}/${id}" frameborder="0" allow="encrypted-media"></iframe>` : null
        };
    }

    // Figma
    if (urlLower.includes('figma.com')) {
        return {
            type: 'rich',
            provider: 'Figma',
            videoType: 'figma',
            title: 'Figma Design',
            thumbnail_url: null,
            url: url,
            html: `<iframe src="https://www.figma.com/embed?embed_host=memory-assist&url=${encodeURIComponent(url)}" allowfullscreen></iframe>`
        };
    }

    // Google Drive / Docs / Sheets / Slides
    if (urlLower.includes('docs.google.com') || urlLower.includes('drive.google.com')) {
        let embedUrl = url;
        if (url.includes('/edit')) embedUrl = url.replace('/edit', '/preview');
        if (url.includes('/view')) embedUrl = url.replace('/view', '/preview');
        return {
            type: 'rich',
            provider: 'Google',
            videoType: 'google',
            title: 'Google Document',
            thumbnail_url: null,
            url: url,
            html: `<iframe src="${embedUrl}" frameborder="0" allowfullscreen></iframe>`
        };
    }

    // Miro
    if (urlLower.includes('miro.com')) {
        console.log('🎨 [EMBED_SERVICE] Detected Miro URL');
        let embedUrl = url;
        let boardId = null;

        // Extract board ID from various URL formats
        const boardMatch = url.match(/miro\.com\/(?:app\/)?(?:board|embed|live-embed)\/([^\/\?#]+)/);
        if (boardMatch) {
            boardId = boardMatch[1];
            console.log('✅ [EMBED_SERVICE] Extracted Miro board ID:', boardId);
        }

        // Preserve share_link_id and other query parameters from original URL
        let extraParams = '';
        try {
            const parsedUrl = new URL(url);
            const shareId = parsedUrl.searchParams.get('share_link_id');
            if (shareId) {
                extraParams = `&share_link_id=${shareId}`;
                console.log('🔗 [EMBED_SERVICE] Preserving share_link_id:', shareId);
            }
        } catch (e) {
            console.warn('⚠️ [EMBED_SERVICE] Could not parse Miro URL params');
        }

        // If it's already a live-embed URL, use it directly
        if (url.includes('/live-embed/')) {
            console.log('✅ [EMBED_SERVICE] Using live-embed URL as-is');
            embedUrl = url;
        }
        // Convert to live-embed format (modern Miro embed)
        else if (boardId) {
            embedUrl = `https://miro.com/app/live-embed/${boardId}/?embedMode=view_only_without_ui&autoplay=yep${extraParams}`;
            console.log('🔄 [EMBED_SERVICE] Converted to live-embed:', embedUrl);
        }
        // Fallback: simple embed conversion
        else if (url.includes('/board/')) {
            embedUrl = url.replace('/board/', '/app/live-embed/') + `?embedMode=view_only_without_ui&autoplay=yep${extraParams}`;
            console.log('🔄 [EMBED_SERVICE] Fallback board URL conversion:', embedUrl);
        }

        const result = {
            type: 'rich',
            provider: 'Miro',
            videoType: 'miro',
            title: 'Miro Board',
            thumbnail_url: null,
            url: url,
            html: `<iframe src="${embedUrl}" frameborder="0" allowfullscreen allow="fullscreen; clipboard-read; clipboard-write"></iframe>`
        };
        console.log('📦 [EMBED_SERVICE] Miro result:', result);
        return result;
    }

    // Airtable
    if (urlLower.includes('airtable.com')) {
        return {
            type: 'rich',
            provider: 'Airtable',
            videoType: 'airtable',
            title: 'Airtable Base',
            thumbnail_url: null,
            url: url,
            html: `<iframe src="${url.replace('airtable.com/', 'airtable.com/embed/')}" frameborder="0"></iframe>`
        };
    }

    // Calendly
    if (urlLower.includes('calendly.com')) {
        return {
            type: 'form',
            provider: 'Calendly',
            videoType: 'calendly',
            title: 'Calendly Scheduler',
            thumbnail_url: null,
            url: url,
            html: `<iframe src="${url}" frameborder="0"></iframe>`
        };
    }

    // Typeform
    if (urlLower.includes('typeform.com')) {
        return {
            type: 'form',
            provider: 'Typeform',
            videoType: 'typeform',
            title: 'Typeform',
            thumbnail_url: null,
            url: url,
            html: `<iframe src="${url}" frameborder="0"></iframe>`
        };
    }

    // Google Forms
    if (urlLower.includes('forms.gle') || urlLower.includes('docs.google.com/forms')) {
        let embedUrl = url;
        if (!url.includes('embedded=true')) {
            embedUrl = url.includes('?') ? `${url}&embedded=true` : `${url}?embedded=true`;
        }
        return {
            type: 'form',
            provider: 'Google Forms',
            videoType: 'googleform',
            title: 'Google Form',
            thumbnail_url: null,
            url: url,
            html: `<iframe src="${embedUrl}" frameborder="0"></iframe>`
        };
    }

    // Tally
    if (urlLower.includes('tally.so')) {
        return {
            type: 'form',
            provider: 'Tally',
            videoType: 'tally',
            title: 'Tally Form',
            thumbnail_url: null,
            url: url,
            html: `<iframe src="${url}" frameborder="0"></iframe>`
        };
    }

    // Generic webpage fallback
    return {
        type: 'link',
        provider: 'Web',
        videoType: 'webpage',
        title: new URL(url).hostname,
        thumbnail_url: null,
        url: url,
        html: `<iframe src="${url}" frameborder="0"></iframe>`
    };
}

/**
 * Normalize metadata from different providers into a consistent format
 */
function normalizeMetadata(data, source) {
    if (source === 'noembed') {
        return {
            type: data.type || 'video',
            provider: data.provider_name || 'Unknown',
            videoType: (data.provider_name || '').toLowerCase(),
            videoId: extractVideoId(data.url, data.provider_name),
            title: data.title || 'Untitled',
            thumbnail_url: data.thumbnail_url,
            url: data.url,
            html: data.html,
            width: data.width,
            height: data.height
        };
    }

    if (source === 'iframely') {
        // Normalize site name to short provider ID (e.g., 'miro.com' -> 'miro')
        const rawSite = (data.meta?.site || '').toLowerCase().replace(/\s+/g, '');
        const normalizedType = rawSite.replace(/\.com$|\.io$|\.co$|\.org$|\.net$/, '');
        return {
            type: data.type || 'rich',
            provider: data.meta?.site || 'Unknown',
            videoType: normalizedType,
            videoId: null,
            title: data.meta?.title || 'Untitled',
            thumbnail_url: data.links?.thumbnail?.[0]?.href || data.meta?.canonical,
            url: data.url,
            html: data.html,
            width: data.meta?.width,
            height: data.meta?.height
        };
    }

    return data;
}

/**
 * Extract video ID based on provider
 */
function extractVideoId(url, provider) {
    if (!url) return null;
    const p = (provider || '').toLowerCase();
    if (p === 'youtube') return getYoutubeId(url);
    if (p === 'vimeo') return getVimeoId(url);
    if (p === 'loom') return getLoomId(url);
    return null;
}

export default { fetchEmbedMetadata };
