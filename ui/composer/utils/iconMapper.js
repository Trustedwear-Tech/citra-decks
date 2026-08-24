// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

/**
 * Icon Mapper - Optimized Iconify API Integration
 * 
 * OPTIMIZATIONS:
 * 1. Try direct Lucide lookup first (no search needed)
 * 2. Limit search to 1 result (faster response)
 * 3. Parallel fetching with Promise.all
 * 4. Aggressive caching
 */

// ==================== Local Icon Cache ====================
export const ICON_PATHS = {
    // Fallbacks
    'circle': 'M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0-20 0',
    'square': 'M3 3h18v18H3z',
    'plus': 'M12 5v14 M5 12h14',
    'minus': 'M5 12h14',
    'check': 'M20 6L9 17l-5-5',
    'x': 'M18 6L6 18 M6 6l12 12',
    'star': 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z',
};

// Runtime cache for fetched icons
const iconCache = new Map();

// Pending fetches to avoid duplicates
const pendingFetches = new Map();

// ==================== Iconify API ====================

const ICONIFY_API = 'https://api.iconify.design';

// Preferred icon sets (try direct lookup in order)
const DIRECT_LOOKUP_SETS = ['lucide', 'ion', 'tabler', 'mdi', 'ph', 'heroicons'];

// Current preferred set (dynamic)
let currentPreferredSet = 'lucide';

export function setPreferredIconSet(set) {
    if (set && DIRECT_LOOKUP_SETS.includes(set)) {
        currentPreferredSet = set;
        console.log(`[Iconify] Set preference to: ${set}`);
    }
}

/**
 * Simplify icon name for better matching
 * "building-office-2" -> "building", "office"
 */
function getSimplifiedNames(iconName) {
    const names = [iconName];
    // Remove numbers and suffixes
    const simplified = iconName.replace(/-\d+$/, '').replace(/-outline$/, '').replace(/-solid$/, '');
    if (simplified !== iconName) names.push(simplified);
    // Get first word
    const firstWord = iconName.split('-')[0];
    if (firstWord !== iconName && firstWord.length > 2) names.push(firstWord);
    return [...new Set(names)];
}

/**
 * Try direct icon fetch from preferred sets (NO search API call)
 * Much faster than search - just tries lucide:iconName, tabler:iconName, etc.
 */
async function tryDirectFetch(iconName) {
    // PRIORITY 0: Check if name already has prefix (e.g. ion:home)
    if (iconName.includes(':')) {
        const [prefix, name] = iconName.split(':');
        try {
            const url = `${ICONIFY_API}/${prefix}/${name}.svg`;
            const response = await fetch(url);
            if (response.ok) return { svg: await response.text(), name: iconName };
        } catch (e) { }
    }

    // PRIORITY 1: Try preferred set first
    if (currentPreferredSet) {
        try {
            const url = `${ICONIFY_API}/${currentPreferredSet}/${iconName}.svg`;
            const response = await fetch(url);
            if (response.ok) {
                return { svg: await response.text(), name: `${currentPreferredSet}:${iconName}` };
            }
        } catch (e) { }
    }

    // PRIORITY 2: Try other sets
    for (const prefix of DIRECT_LOOKUP_SETS) {
        if (prefix === currentPreferredSet) continue; // Already tried
        try {
            const url = `${ICONIFY_API}/${prefix}/${iconName}.svg`;
            const response = await fetch(url);
            if (response.ok) {
                return { svg: await response.text(), name: `${prefix}:${iconName}` };
            }
        } catch (e) { }
    }

    // PRIORITY 2: Try simplified names (fuzzy match)
    const namesToTry = getSimplifiedNames(iconName);
    for (const name of namesToTry) {
        if (name === iconName) continue; // Skip if already tried

        for (const prefix of DIRECT_LOOKUP_SETS) {
            try {
                const url = `${ICONIFY_API}/${prefix}/${name}.svg`;
                const response = await fetch(url);
                if (response.ok) {
                    const svgText = await response.text();
                    return { svg: svgText, name: `${prefix}:${name}` };
                }
            } catch (e) {
                // Continue
            }
        }
    }
    return null;
}

/**
 * Search Iconify (fallback, limit=3 for broader results)
 */
async function searchIconify(query) {
    try {
        // Use simplified query for better matches
        const simplifiedQuery = query.replace(/-\d+$/, '').replace(/-/g, ' ');

        const response = await fetch(
            `${ICONIFY_API}/search?query=${encodeURIComponent(simplifiedQuery)}&limit=3`
        );

        if (!response.ok) return null;

        const data = await response.json();
        if (!data.icons || data.icons.length === 0) return null;

        // Prefer lucide/tabler/mdi if available
        for (const preferred of DIRECT_LOOKUP_SETS) {
            const match = data.icons.find(icon => icon.startsWith(preferred + ':'));
            if (match) {
                const [prefix, name] = match.split(':');
                return { prefix, name };
            }
        }

        // Use first result
        const [prefix, name] = data.icons[0].split(':');
        return { prefix, name };

    } catch (error) {
        console.error(`[Iconify] Search error:`, error);
        return null;
    }
}

/**
 * Fetch SVG from Iconify
 */
async function fetchIconSVG(prefix, name) {
    try {
        const response = await fetch(`${ICONIFY_API}/${prefix}/${name}.svg`);
        if (!response.ok) return null;
        return await response.text();
    } catch (error) {
        return null;
    }
}

/**
 * Extract path data from SVG string
 */
function extractPathFromSVG(svgText) {
    const pathMatch = svgText.match(/d="([^"]+)"/g);
    if (pathMatch && pathMatch.length > 0) {
        return pathMatch.map(p => p.replace(/d="([^"]+)"/, '$1')).join(' ');
    }
    return null;
}

/**
 * Fetch single icon (with deduplication)
 */
async function fetchIcon(iconName) {
    // Preserve colons for prefixed icons (e.g., "lucide:brain")
    const normalized = iconName.toLowerCase().trim().replace(/[^a-z0-9:-]/g, '');

    // Already cached?
    if (iconCache.has(normalized)) {
        return iconCache.get(normalized);
    }

    // Already fetching?
    if (pendingFetches.has(normalized)) {
        return pendingFetches.get(normalized);
    }

    const fetchPromise = (async () => {
        try {
            // STEP 1: Try direct fetch (fastest - no search)
            const directResult = await tryDirectFetch(normalized);
            if (directResult) {
                iconCache.set(normalized, directResult);
                console.log(`[Iconify] ✅ Direct: ${normalized} -> ${directResult.name}`);
                return directResult;
            }

            // STEP 2: Fallback to search (limit=1)
            const searchResult = await searchIconify(normalized);
            if (searchResult) {
                const svgText = await fetchIconSVG(searchResult.prefix, searchResult.name);
                if (svgText) {
                    const result = { svg: svgText, name: `${searchResult.prefix}:${searchResult.name}` };
                    iconCache.set(normalized, result);
                    console.log(`[Iconify] ✅ Search: ${normalized} -> ${result.name}`);
                    return result;
                }
            }

            // STEP 3: Fallback to circle
            console.warn(`[Iconify] ⚠️ No icon found for "${normalized}", using circle fallback`);
            return { path: ICON_PATHS['circle'], name: 'circle' };

        } catch (error) {
            console.error(`[Iconify] Error fetching "${normalized}":`, error);
            return { path: ICON_PATHS['circle'], name: 'circle' };
        } finally {
            pendingFetches.delete(normalized);
        }
    })();

    pendingFetches.set(normalized, fetchPromise);
    return fetchPromise;
}

// ==================== Public API ====================

/**
 * Sync lookup (cache only, triggers async fetch if missing)
 * Returns {path, svg, name, isPlaceholder} where isPlaceholder=true means icon not yet loaded
 */
export function mapIconToPath(iconName) {
    if (!iconName) return { path: ICON_PATHS['circle'], name: 'circle', isPlaceholder: false };

    // Preserve colons for prefixed icons (e.g., "lucide:brain")
    const normalized = iconName.toLowerCase().trim().replace(/[^a-z0-9:-]/g, '');

    // Local cache
    if (ICON_PATHS[normalized]) {
        return { path: ICON_PATHS[normalized], name: normalized, isPlaceholder: false };
    }

    // Runtime cache
    if (iconCache.has(normalized)) {
        return iconCache.get(normalized);
    }

    // Trigger async fetch for next render
    fetchIcon(iconName).catch(() => { });
    // Return placeholder circle but mark it as placeholder so save logic doesn't persist "circle" as resolvedIconName
    return { path: ICON_PATHS['circle'], name: 'circle', isPlaceholder: true };
}

/**
 * Async lookup (fetches if needed)
 */
export async function mapIconToPathAsync(iconName) {
    if (!iconName) return { path: ICON_PATHS['circle'], name: 'circle' };

    // Preserve colons for prefixed icons (e.g., "lucide:brain")
    const normalized = iconName.toLowerCase().trim().replace(/[^a-z0-9:-]/g, '');

    if (ICON_PATHS[normalized]) {
        return { path: ICON_PATHS[normalized], name: normalized };
    }

    if (iconCache.has(normalized)) {
        return iconCache.get(normalized);
    }

    return fetchIcon(iconName);
}

/**
 * BATCH prefetch - fetches ALL icons in PARALLEL
 */
export async function prefetchIcons(iconNames) {
    const unique = [...new Set(iconNames.filter(Boolean))];
    const uncached = unique.filter(name => {
        const n = name.toLowerCase().trim().replace(/[^a-z0-9-]/g, '');
        return !ICON_PATHS[n] && !iconCache.has(n);
    });

    if (uncached.length === 0) {
        console.log(`[Iconify] All ${unique.length} icons already cached`);
        return;
    }

    console.log(`[Iconify] 🚀 Parallel fetch: ${uncached.length} icons...`);

    // PARALLEL FETCH - all at once!
    await Promise.all(uncached.map(name => fetchIcon(name)));

    console.log(`[Iconify] ✅ Batch complete: ${uncached.length} icons fetched`);
}

/**
 * Get available icons
 */
export function getAvailableIcons() {
    return [...Object.keys(ICON_PATHS), ...Array.from(iconCache.keys())];
}

/**
 * Get SVG for Fabric.js
 */
export function getIconSVG(iconName, options = {}) {
    const { path, svg } = mapIconToPath(iconName);
    const { fill = '#ffffff', size = 24 } = options;

    if (svg) {
        // If we have full SVG, try to inject size/fill
        // Robust regex replacement to handle hardcoded colors (black, hex) or currentColor
        // explicitly avoiding 'none' or 'transparent' to preserve structure
        let processed = svg
            .replace(/width="[^"]*"/, `width="${size}"`)
            .replace(/height="[^"]*"/, `height="${size}"`)
            .replace(/currentColor/g, fill);

        // Replace non-none fills with user color
        // Matches fill="..." where value is NOT none/transparent
        processed = processed.replace(/fill="(?!(?:none|transparent))[^"]*"/g, `fill="${fill}"`);

        // Replace non-none strokes with user color
        processed = processed.replace(/stroke="(?!(?:none|transparent))[^"]*"/g, `stroke="${fill}"`);

        // Normalize stroke-width to 1.5 for subtler, more refined icons
        processed = processed.replace(/stroke-width="[^"]*"/g, 'stroke-width="1.5"');

        // Ensure stroke is set if it looks like a line icon (no fill, or fill=none)
        if (!processed.includes('fill=') && !processed.includes('stroke=')) {
            processed = processed.replace('<svg', `<svg fill="none" stroke="${fill}"`);
        } else if (processed.includes('fill="none"') && !processed.includes('stroke=')) {
            // Commonly Lucide
            processed = processed.replace('<svg', `<svg stroke="${fill}"`);
        }

        return processed;
    }

    return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${fill}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="${path}"/></svg>`;
}

/**
 * Cache SVG content for an icon name (used after S3 fetch to avoid re-fetching)
 */
export function cacheIconSVG(iconName, svgText) {
    if (!iconName || !svgText) return;
    const normalized = iconName.toLowerCase().trim().replace(/[^a-z0-9:-]/g, '');
    if (!iconCache.has(normalized)) {
        iconCache.set(normalized, { svg: svgText, name: normalized });
        // console.log(`[Iconify] Cached S3 icon: ${normalized}`);
    }
}

/**
 * Clear cache
 */
export function clearIconCache() {
    iconCache.clear();
    console.log('[Iconify] Cache cleared');
}

/**
 * Search Iconify and return MULTIPLE results for UI picker
 */
export async function searchIcons(query, limit = 20) {
    try {
        const simplifiedQuery = query.toLowerCase().trim();
        const response = await fetch(
            `${ICONIFY_API}/search?query=${encodeURIComponent(simplifiedQuery)}&limit=${limit}`
        );

        if (!response.ok) return [];

        const data = await response.json();
        return data.icons || [];
    } catch (error) {
        console.error(`[Iconify] List search error:`, error);
        return [];
    }
}

export default {
    mapIconToPath,
    mapIconToPathAsync,
    prefetchIcons,
    getAvailableIcons,
    getIconSVG,
    cacheIconSVG,
    clearIconCache,
    searchIcons, // Export new function
    setPreferredIconSet,
    ICON_PATHS,
};
