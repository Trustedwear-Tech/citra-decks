// useClipboard.js - Hook for managing copy/paste/format painter clipboard state
// OS clipboard is the primary (first-citizen) clipboard for all element/slide operations.
// Format painter remains in-memory (same-tab tool).
import { useState, useCallback, useRef } from 'react';

export const useClipboard = () => {
    // Format painter needs in-memory state (same-tab only tool)
    const [formatPainterData, setFormatPainterData] = useState(null);
    const pasteCountRef = useRef(0);
    const lastCopyTimestampRef = useRef(0);

    const deepClone = useCallback((obj) => {
        if (obj === null || typeof obj !== 'object') return obj;
        if (obj instanceof Date) return new Date(obj.getTime());
        if (Array.isArray(obj)) return obj.map(item => deepClone(item));
        const cloned = {};
        for (const key in obj) {
            if (Object.prototype.hasOwnProperty.call(obj, key)) {
                cloned[key] = deepClone(obj[key]);
            }
        }
        return cloned;
    }, []);

    const generateNewId = useCallback((originalId) => {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substr(2, 9);
        if (originalId && originalId.includes('_')) {
            const prefix = originalId.split('_')[0];
            return `${prefix}_${timestamp}_${random}`;
        }
        return `element_${timestamp}_${random}`;
    }, []);

    /**
     * Copy single or multiple elements to OS clipboard (full serialization)
     */
    const copyElements = useCallback(async (elements, sourceSlideId) => {
        if (!elements || (Array.isArray(elements) && elements.length === 0)) return false;

        const elementsArray = Array.isArray(elements) ? elements : [elements];
        const clonedElements = elementsArray.map(el => deepClone(el));
        const timestamp = Date.now();
        lastCopyTimestampRef.current = timestamp;
        pasteCountRef.current = 0;

        try {
            const payload = JSON.stringify({
                __citraAIClipboard: true,
                type: 'elements',
                data: clonedElements,
                sourceSlideId,
                timestamp,
            });
            await navigator.clipboard.writeText(payload);
            console.log(`📋 [CLIPBOARD] Copied ${clonedElements.length} element(s) to OS clipboard`);
        } catch (err) {
            console.warn('📋 [CLIPBOARD] Could not write to OS clipboard:', err);
            return false;
        }
        return true;
    }, [deepClone]);

    /**
     * Copy an entire slide to OS clipboard (full serialization)
     */
    const copySlide = useCallback(async (slide) => {
        if (!slide) return false;

        const clonedSlide = deepClone(slide);
        const timestamp = Date.now();
        lastCopyTimestampRef.current = timestamp;
        pasteCountRef.current = 0;

        try {
            const payload = JSON.stringify({
                __citraAIClipboard: true,
                type: 'slide',
                data: clonedSlide,
                sourceSlideId: slide.id,
                timestamp,
            });
            await navigator.clipboard.writeText(payload);
            console.log(`📋 [CLIPBOARD] Copied slide to OS clipboard: ${slide.title || slide.id}`);
        } catch (err) {
            console.warn('📋 [CLIPBOARD] Could not write slide to OS clipboard:', err);
            return false;
        }
        return true;
    }, [deepClone]);

    /**
     * Parse pasted Citra clipboard text data. Returns { type, data, sourceSlideId } or null.
     * Generates new IDs and applies paste offset for elements.
     */
    const parsePastedElements = useCallback((clipboardText) => {
        try {
            const parsed = JSON.parse(clipboardText);
            if (!parsed.__citraAIClipboard) return null;

            // Track paste offset — increment for same data, reset for different data
            if (parsed.timestamp === lastCopyTimestampRef.current) {
                pasteCountRef.current += 1;
            } else {
                lastCopyTimestampRef.current = parsed.timestamp || 0;
                pasteCountRef.current = 1;
            }
            const offset = pasteCountRef.current * 15;

            if (parsed.type === 'elements' && parsed.data) {
                const pastedElements = parsed.data.map(el => ({
                    ...deepClone(el),
                    id: generateNewId(el.id),
                    x: (el.x || 0) + offset,
                    y: (el.y || 0) + offset,
                }));
                console.log(`📋 [CLIPBOARD] Parsed ${pastedElements.length} element(s) with offset ${offset}px`);
                return { type: parsed.type, data: pastedElements, sourceSlideId: parsed.sourceSlideId };
            }

            if (parsed.type === 'slide' && parsed.data) {
                const ts = Date.now();
                const random = Math.random().toString(36).substr(2, 9);
                const pastedSlide = {
                    ...deepClone(parsed.data),
                    id: `slide_${ts}_${random}`,
                    title: `${parsed.data.title || 'Slide'} (Copy)`,
                    elements: parsed.data.elements?.map(el => ({
                        ...el,
                        id: generateNewId(el.id),
                    })) || [],
                    hasUnsavedChanges: true,
                };
                console.log(`📋 [CLIPBOARD] Parsed slide: ${pastedSlide.title}`);
                return { type: 'slide', data: pastedSlide, sourceSlideId: parsed.sourceSlideId };
            }

            return null;
        } catch {
            return null;
        }
    }, [deepClone, generateNewId]);

    // --- Format Painter (in-memory, same-tab only) ---

    const copyFormat = useCallback((element) => {
        if (!element) return false;

        let fData = { type: element.type };

        if (element.type === 'text') {
            fData = {
                ...fData,
                fontSize: element.fontSize,
                fontWeight: element.fontWeight,
                fontFamily: element.fontFamily,
                fill: element.fill,
                color: element.color,
                textAlign: element.textAlign,
                lineHeight: element.lineHeight,
                fontStyle: element.fontStyle,
                textDecoration: element.textDecoration,
            };
        } else if (element.type === 'shape') {
            fData = {
                ...fData,
                fill: element.fill,
                stroke: element.stroke,
                strokeWidth: element.strokeWidth,
                rx: element.rx,
                ry: element.ry,
                opacity: element.opacity,
            };
        } else if (element.type === 'icon') {
            fData = {
                ...fData,
                fill: element.fill,
                size: element.size,
                opacity: element.opacity,
            };
        }

        setFormatPainterData(fData);
        console.log(`🎨 [CLIPBOARD] Copied format from ${element.type} element`);
        return true;
    }, []);

    const canApplyFormat = useCallback((fData, targetElement) => {
        if (!fData || !targetElement) return false;
        if (fData.type === targetElement.type) return true;
        const compatibleTypes = ['shape', 'icon'];
        return compatibleTypes.includes(fData.type) && compatibleTypes.includes(targetElement.type);
    }, []);

    const getApplicableFormat = useCallback((fData, targetType) => {
        if (!fData) return null;
        if (fData.type === targetType) {
            const { type, ...properties } = fData;
            return properties;
        }
        if (['shape', 'icon'].includes(fData.type) && ['shape', 'icon'].includes(targetType)) {
            return { fill: fData.fill };
        }
        return null;
    }, []);

    return {
        copyElements,
        copySlide,
        copyFormat,
        parsePastedElements,
        canApplyFormat,
        getApplicableFormat,
        formatPainterData,
    };
};

export default useClipboard;
