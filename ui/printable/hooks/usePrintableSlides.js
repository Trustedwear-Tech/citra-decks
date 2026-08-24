// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

import { useState, useCallback, useEffect, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';
import * as Y from 'yjs';


// Default page dimensions (A4 portrait at 96 DPI: 794x1123 pixels)
export const PAGE_WIDTH = 794;
export const PAGE_HEIGHT = 1123;

// Default PAGE element types
export const ELEMENT_TYPES = {
  TEXT: 'text',
  IMAGE: 'image',
  SHAPE: 'shape',
  ICON: 'icon',
  CHART: 'chart',
  TABLE: 'table',
  VIDEO: 'video',
  EMBED: 'embed',
  BUTTON: 'button',
  ANIMATION: 'animation',
  SVG_DIAGRAM: 'svg_diagram',
};

// Create a default text element
const createDefaultTextElement = (type = 'body', content = '', position = {}) => ({
  id: uuidv4(),
  type: ELEMENT_TYPES.TEXT,
  textType: type, // 'title', 'subtitle', 'body', 'bullet'
  content: content,
  x: position.x || 50,
  y: position.y || (type === 'title' ? 50 : type === 'subtitle' ? 120 : 180),
  width: position.width || PAGE_WIDTH - 100,
  height: position.height || (type === 'title' ? 80 : type === 'subtitle' ? 50 : 300),
  zIndex: position.zIndex || 1, // Fix: Accept zIndex
  fontSize: type === 'title' ? 44 : type === 'subtitle' ? 28 : 20,
  fontFamily: 'Inter, system-ui, sans-serif',
  fontWeight: type === 'title' ? '700' : type === 'subtitle' ? '500' : '400',
  color: type === 'title' ? '#1a1a2e' : type === 'subtitle' ? '#4a4a6a' : '#333333',
  textAlign: type === 'title' || type === 'subtitle' ? 'center' : 'left',
  lineHeight: 1.4,
  locked: false,
});

// Create a default image element
const createDefaultImageElement = (src = '', position = {}, isUserMedia = false) => ({
  id: uuidv4(),
  type: ELEMENT_TYPES.IMAGE,
  src: src,
  x: position.x || 50,
  y: position.y || 200,
  width: position.width || 400,
  height: position.height || 300,
  zIndex: position.zIndex || 1, // Fix: Accept zIndex
  opacity: 1,
  borderRadius: 8,
  locked: false,
  alt: '',
  ...(isUserMedia ? { isUserMedia: true } : {}),
});

// Create a default video element
const createDefaultVideoElement = (src = '', options = {}) => ({
  id: uuidv4(),
  type: ELEMENT_TYPES.VIDEO,
  src: src,
  x: options.position?.x || options.x || 50,
  y: options.position?.y || options.y || 200,
  width: options.position?.width || options.width || 480,
  height: options.position?.height || options.height || 270,
  zIndex: options.position?.zIndex || options.zIndex || 1,
  opacity: 1,
  locked: false,
  isUserMedia: true, // Default true for direct uploads
  // VIDEO-SPECIFIC PROPERTIES - Critical for thumbnail display
  thumbnail: options.thumbnail || null,
  videoType: options.videoType || 'local',
  videoId: options.videoId || null,
});

// Create a default embed element (Figma, Miro, Google Drive, etc.)
const createDefaultEmbedElement = (options = {}) => ({
  id: uuidv4(),
  type: ELEMENT_TYPES.EMBED,
  src: options.src || '',
  embedType: options.embedType || 'webpage',
  provider: options.provider || 'Web',
  title: options.title || 'Embedded Content',
  thumbnail: options.thumbnail || null,
  html: options.html || null,
  x: options.position?.x || options.x || 100,
  y: options.position?.y || options.y || 100,
  width: options.position?.width || options.width || 640,
  height: options.position?.height || options.height || 480,
  zIndex: options.position?.zIndex || options.zIndex || 1,
  opacity: 1,
  locked: false,
});

// Create a default button element (CTA buttons)
const createDefaultButtonElement = (options = {}) => ({
  id: uuidv4(),
  type: ELEMENT_TYPES.BUTTON,
  label: options.label || 'Button',
  url: options.url || '#',
  style: options.style || 'primary', // 'primary' | 'secondary' | 'ghost'
  x: options.position?.x || options.x || 100,
  y: options.position?.y || options.y || 100,
  width: options.position?.width || options.width || 160,
  height: options.position?.height || options.height || 48,
  zIndex: options.position?.zIndex || options.zIndex || 1,
  opacity: 1,
  locked: false,
});

// Create a default shape element with extended shape type support
const createDefaultShapeElement = (shapeType = 'rectangle', position = {}) => {
  // Determine default dimensions based on shape type
  let defaultWidth = 200;
  let defaultHeight = 100;
  let defaultBorderRadius = 0;

  // Lines and arrows
  if (shapeType === 'line' || shapeType === 'arrow') {
    defaultWidth = 200;
    defaultHeight = 4;
  }
  // Circles, squares, stars, and polygons should be square
  else if (['circle', 'square', 'star', 'polygon'].includes(shapeType)) {
    defaultWidth = 120;
    defaultHeight = 120;
  }
  // Block arrows and chevrons
  else if (shapeType === 'block_arrow' || shapeType === 'chevron' || shapeType === 'pentagon_arrow') {
    defaultWidth = 160;
    defaultHeight = 80;
  }
  // Callouts
  else if (shapeType.startsWith('callout')) {
    defaultWidth = 200;
    defaultHeight = 120;
  }
  // Rectangles
  else if (shapeType === 'rectangle' || shapeType === 'rectangle_rounded') {
    defaultBorderRadius = shapeType === 'rectangle_rounded' ? 12 : 0;
  }

  return {
    id: uuidv4(),
    type: ELEMENT_TYPES.SHAPE,
    shapeType: shapeType,
    x: position.x || 100,
    y: position.y || 100,
    width: position.width || defaultWidth,
    height: position.height || defaultHeight,
    zIndex: position.zIndex || 1,
    fill: '#3B82F6',
    stroke: '#1E40AF',
    strokeWidth: 2,
    opacity: 1,
    borderRadius: position.borderRadius ?? defaultBorderRadius,
    // Extended shape properties
    ...(position.sides && { sides: position.sides }),           // For polygons
    ...(position.points && { points: position.points }),         // For stars
    ...(position.direction && { direction: position.direction }),// For arrows/chevrons
    ...(position.subType && { subType: position.subType }),      // For line variants
    ...(position.strokeDashArray && { strokeDashArray: position.strokeDashArray }), // For dashed/dotted lines
    locked: false,
  };
};


// Create a default icon element
const createDefaultIconElement = (iconName = 'star', position = {}) => ({
  id: uuidv4(),
  type: ELEMENT_TYPES.ICON,
  iconName: iconName,
  x: position.x || 100,
  y: position.y || 100,
  size: position.size || 48,
  zIndex: position.zIndex || 1, // Fix: Accept zIndex
  fill: position.fill || '#000000', // Fix: Default to black instead of green
  locked: false,
});

// Create a default chart element
const createDefaultChartElement = (chartConfig = null, position = {}) => ({
  id: uuidv4(),
  type: ELEMENT_TYPES.CHART,
  chartConfig: chartConfig,
  x: position.x || (PAGE_WIDTH / 2 - 240), // Center by default if not specified
  y: position.y || (PAGE_HEIGHT / 2 - 160),
  width: position.width || 480,
  height: position.height || 320,
  zIndex: position.zIndex || 1,
  locked: false,
});

// Create a default table element
const createDefaultTableElement = (tableConfig = null, position = {}) => ({
  id: uuidv4(),
  type: ELEMENT_TYPES.TABLE,
  tableConfig: tableConfig,
  x: position.x || (PAGE_WIDTH / 2 - 200),
  y: position.y || (PAGE_HEIGHT / 2 - 150),
  width: position.width || 400,
  height: position.height || 300,
  zIndex: position.zIndex || 50,
  locked: false,
});

// Create a default animation element (video converted to frame sequence)
const createDefaultAnimationElement = (options = {}) => ({
  id: uuidv4(),
  type: ELEMENT_TYPES.ANIMATION,
  videoSrc: options.videoSrc || '', // Video URL for live playback
  isPlaying: options.isPlaying !== false, // Default to playing
  loop: options.loop !== false, // Default to loop
  x: options.position?.x || options.x || 100,
  y: options.position?.y || options.y || 100,
  width: options.position?.width || options.width || 400,
  height: options.position?.height || options.height || 225,
  zIndex: options.position?.zIndex || options.zIndex || 1,
  isUserMedia: options.isUserMedia || true,
  opacity: 1,
  locked: false,
});

// Create a default SVG diagram element (AI-generated inline SVG).
// Field naming matches the existing svg_diagram renderer (uses element.svgContent
// + element.fillColor for currentColor substitution).
const createDefaultSvgDiagramElement = (options = {}) => ({
  id: uuidv4(),
  type: ELEMENT_TYPES.SVG_DIAGRAM,
  svgContent: options.svgContent || options.svg || '',
  prompt: options.prompt || '',
  diagramKind: options.diagramKind || 'flowchart',
  diagramTitle: options.diagramTitle || options.title || '',
  fillColor: options.fillColor || '#3B82F6',
  x: options.position?.x ?? options.x ?? 50,
  y: options.position?.y ?? options.y ?? 100,
  width: options.position?.width ?? options.width ?? 495,
  height: options.position?.height ?? options.height ?? 280,
  zIndex: options.position?.zIndex ?? options.zIndex ?? 1,
  opacity: 1,
  locked: false,
});

// Default PAGE templates
export const PAGE_LAYOUTS = {
  TITLE: 'title',
  TITLE_CONTENT: 'title_content',
  TITLE_TWO_COLUMN: 'title_two_column',
  TITLE_IMAGE_LEFT: 'title_image_left',
  TITLE_IMAGE_RIGHT: 'title_image_right',
  IMAGE_FULL: 'image_full',
  BLANK: 'blank',
};

// Create elements based on layout
const createLayoutElements = (layout, title = '', subtitle = '', content = '') => {
  switch (layout) {
    case PAGE_LAYOUTS.TITLE:
      return [
        createDefaultTextElement('title', title, { y: 200, width: PAGE_WIDTH - 100 }),
        createDefaultTextElement('subtitle', subtitle, { y: 280, width: PAGE_WIDTH - 100 }),
      ];

    case PAGE_LAYOUTS.TITLE_CONTENT:
      return [
        createDefaultTextElement('title', title, { y: 40, height: 60 }),
        createDefaultTextElement('body', content, { y: 120, height: 380 }),
      ];

    case PAGE_LAYOUTS.TITLE_TWO_COLUMN:
      return [
        createDefaultTextElement('title', title, { y: 40, height: 60 }),
        createDefaultTextElement('body', '', { x: 50, y: 120, width: 420, height: 380 }),
        createDefaultTextElement('body', '', { x: 490, y: 120, width: 420, height: 380 }),
      ];

    case PAGE_LAYOUTS.TITLE_IMAGE_LEFT:
      return [
        createDefaultTextElement('title', title, { y: 40, height: 60 }),
        createDefaultImageElement('', { x: 50, y: 120, width: 400, height: 350 }),
        createDefaultTextElement('body', content, { x: 480, y: 120, width: 430, height: 350 }),
      ];

    case PAGE_LAYOUTS.TITLE_IMAGE_RIGHT:
      return [
        createDefaultTextElement('title', title, { y: 40, height: 60 }),
        createDefaultTextElement('body', content, { x: 50, y: 120, width: 430, height: 350 }),
        createDefaultImageElement('', { x: 510, y: 120, width: 400, height: 350 }),
      ];

    case PAGE_LAYOUTS.IMAGE_FULL:
      return [
        createDefaultImageElement('', { x: 0, y: 0, width: PAGE_WIDTH, height: PAGE_HEIGHT }),
        createDefaultTextElement('title', title, { y: PAGE_HEIGHT - 100, color: '#ffffff' }),
      ];

    case PAGE_LAYOUTS.BLANK:
    default:
      return [];
  }
};

export const usePrintablePages = (initialprintable = null, collaboration = null) => {
  // Initialize state from existing printable or create new
  const [PAGES, setPAGES] = useState(() => {
    if (initialprintable?.PAGES?.length > 0) {
      return initialprintable.PAGES;
    }
    // Create default title PAGE
    return [{
      id: uuidv4(),
      order: 1,
      title: 'Title PAGE',
      layout: PAGE_LAYOUTS.TITLE,
      elements: createLayoutElements(PAGE_LAYOUTS.TITLE, 'printable Title', 'Subtitle or Author Name'),
      notes: '',
      backgroundColor: '#ffffff',
      backgroundImage: null,
      transition: 'fade',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      hasUnsavedChanges: false,
      hidden: false,
    }];
  });

  const [currentPAGEId, setCurrentPAGEId] = useState(() => {
    return initialprintable?.currentPAGEId || PAGES[0]?.id;
  });

  const [printableMetadata, setprintableMetadata] = useState(() => ({
    id: initialprintable?.id || uuidv4(),
    title: initialprintable?.title || 'Untitled printable',
    description: initialprintable?.description || '',
    created_at: initialprintable?.created_at || new Date().toISOString(),
    updated_at: new Date().toISOString(),
    overall_goal: initialprintable?.overall_goal || '',
    target_audience: initialprintable?.target_audience || '',
    style: initialprintable?.style || null, // Will hold the selected style theme
    aspectRatio: initialprintable?.aspectRatio || '16:9',
  }));

  // Selected element on current PAGE
  const [selectedElementId, setSelectedElementId] = useState(null);

  // Refs mirroring the latest state so imperative handlers (delete/duplicate)
  // can compute neighbor selection from a guaranteed-fresh snapshot (no stale
  // closures), and so the heal-effect can remember where the cursor was.
  const PAGESRef = useRef(PAGES);
  const currentPAGEIdRef = useRef(currentPAGEId);
  const lastValidIndexRef = useRef(0);
  useEffect(() => { PAGESRef.current = PAGES; }, [PAGES]);
  useEffect(() => { currentPAGEIdRef.current = currentPAGEId; }, [currentPAGEId]);

  // Handle initialprintable changes (when loading an existing printable)
  useEffect(() => {
    if (initialprintable?.PAGES?.length > 0) {
      const loadedPAGES = initialprintable.PAGES.map((PAGE, index) => ({
        id: PAGE.id || uuidv4(),
        order: PAGE.order || index + 1,
        title: PAGE.title || `PAGE ${index + 1}`,
        layout: PAGE.layout || PAGE_LAYOUTS.BLANK,
        elements: PAGE.elements || [],
        notes: PAGE.notes || '',
        backgroundColor: PAGE.backgroundColor || '#ffffff',
        backgroundImage: PAGE.backgroundImage || null,
        transition: PAGE.transition || 'fade',
        created_at: PAGE.created_at || new Date().toISOString(),
        updated_at: PAGE.updated_at || new Date().toISOString(),
        hasUnsavedChanges: false,
        hidden: PAGE.hidden || false,
      }));

      setPAGES(loadedPAGES);

      if (loadedPAGES.length > 0) {
        setCurrentPAGEId(loadedPAGES[0].id);
      }

      // Update metadata from loaded printable
      setprintableMetadata(prev => ({
        ...prev,
        id: initialprintable.id || prev.id,
        title: initialprintable.title || prev.title,
        description: initialprintable.description || prev.description,
        overall_goal: initialprintable.goal || initialprintable.overall_goal || prev.overall_goal,
        style: initialprintable.style || prev.style,
        updated_at: new Date().toISOString(),
      }));
    } else if (initialprintable === null) {
      // Reset to default for new printable
      const defaultPAGE = {
        id: uuidv4(),
        order: 1,
        title: 'Title PAGE',
        layout: PAGE_LAYOUTS.TITLE,
        elements: createLayoutElements(PAGE_LAYOUTS.TITLE, 'printable Title', 'Subtitle or Author Name'),
        notes: '',
        backgroundColor: '#ffffff',
        backgroundImage: null,
        transition: 'fade',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        hasUnsavedChanges: false,
      };
      setPAGES([defaultPAGE]);
      setCurrentPAGEId(defaultPAGE.id);
      setprintableMetadata({
        id: null,
        title: 'Untitled printable',
        description: '',
        overall_goal: '',
        target_audience: '',
        style: null,
        aspectRatio: '16:9',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    }
  }, [initialprintable]);

  // ==================== Yjs Synchronization ====================
  const isRemoteUpdate = useRef(false);

  useEffect(() => {
    if (!collaboration || !collaboration.doc) return;

    const doc = collaboration.doc;
    const yPAGES = doc.getArray('PAGES');

    // Initial Sync: Yjs -> Local OR Local -> Yjs
    if (yPAGES.length === 0 && PAGES.length > 0) {
      // Initialize Yjs from local
      doc.transact(() => {
        PAGES.forEach(PAGE => {
          const yPAGE = new Y.Map();
          // Copy all properties
          Object.keys(PAGE).forEach(key => {
            if (key === 'elements') {
              const yElements = new Y.Array();
              PAGE.elements.forEach(el => {
                const yEl = new Y.Map();
                Object.keys(el).forEach(k => yEl.set(k, el[k]));
                yElements.push([yEl]);
              });
              yPAGE.set('elements', yElements);
            } else {
              yPAGE.set(key, PAGE[key]);
            }
          });
          yPAGES.push([yPAGE]);
        });
      });
    } else if (yPAGES.length > 0) {
      // Initialize local from Yjs
      setPAGES(yPAGES.toJSON());
    }

    // Observer
    const observer = (events) => {
      console.log('🔔 [YJS_OBSERVER] Deep observer fired, events:', events?.length || 0);
      isRemoteUpdate.current = true;
      const newPAGES = yPAGES.toJSON();
      console.log('🔔 [YJS_OBSERVER] Setting PAGES from Y.js, PAGES count:', newPAGES?.length || 0);
      setPAGES(newPAGES);
      // Simple JSON conversion handles nested elements correctly if consistent
      setTimeout(() => { isRemoteUpdate.current = false; }, 0);
    };

    yPAGES.observeDeep(observer);

    return () => {
      yPAGES.unobserveDeep(observer);
    };
  }, [collaboration, PAGES.length]); // Depend on PAGES.length only for initial check

  // Helper to get Yjs object for a PAGE
  const getYPAGE = useCallback((PAGEId) => {
    if (!collaboration?.doc) return null;
    const yPAGES = collaboration.doc.getArray('PAGES');
    // Find index - Yjs arrays don't support .find returning the Y.Map directly easily without index
    // But we can iterate.
    // Optimization: Maintain ID->Index map if needed, but linear scan is fine for < 100 PAGES
    let foundIndex = -1;
    let foundPAGE = null;

    // yPAGES.forEach is (item, index)
    yPAGES.forEach((yPAGE, index) => {
      if (yPAGE.get('id') === PAGEId) {
        foundIndex = index;
        foundPAGE = yPAGE;
      }
    });

    return { yPAGE: foundPAGE, index: foundIndex, yPAGES };
  }, [collaboration]);

  // Add new PAGE
  const addPAGE = useCallback((insertIndex = PAGES.length, layout = PAGE_LAYOUTS.TITLE_CONTENT, customElements = null) => {
    const newPAGE = {
      id: uuidv4(),
      order: insertIndex + 1,
      title: `PAGE ${insertIndex + 1}`,
      layout: layout,
      elements: customElements || createLayoutElements(layout),
      notes: '',
      backgroundColor: '#ffffff',
      backgroundImage: null,
      transition: 'fade',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      hasUnsavedChanges: false,
      hidden: false,
    };

    setPAGES(currentPAGES => {
      const updatedPAGES = [...currentPAGES];
      updatedPAGES.splice(insertIndex, 0, newPAGE);

      // Reorder all PAGES
      return updatedPAGES.map((PAGE, index) => ({
        ...PAGE,
        order: index + 1,
      }));
    });

    // Set the new PAGE as current
    setCurrentPAGEId(newPAGE.id);
    setSelectedElementId(null);

    // Update printable metadata
    setprintableMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));

    return newPAGE.id;
  }, [PAGES.length]);

  // Delete PAGE
  const deletePAGE = useCallback((PAGEId) => {
    // Read a fresh snapshot from refs — no side effects inside the state updater
    // (those can double-run under React 18 and corrupt the neighbor pick), and
    // no stale closure on `PAGES`.
    const cur = PAGESRef.current;
    if (cur.length <= 1) {
      console.warn('[printable_COMPOSER] Cannot delete the last remaining PAGE');
      return;
    }
    const idx = cur.findIndex(s => s.id === PAGEId);
    if (idx < 0) return;

    // Fix selection FIRST, from the pre-delete snapshot: if we're deleting the
    // ACTIVE page, move to the next one (or the previous if it was last).
    // Deleting a non-active page must leave the selection exactly where it is.
    if (currentPAGEIdRef.current === PAGEId) {
      const neighbor = cur[idx + 1] || cur[idx - 1] || null;
      setCurrentPAGEId(neighbor ? neighbor.id : null);
    }

    setPAGES(currentPAGES =>
      currentPAGES.filter(s => s.id !== PAGEId).map((PAGE, index) => ({
        ...PAGE,
        order: index + 1,
      }))
    );

    setSelectedElementId(null);

    // Update printable metadata
    setprintableMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));
  }, []);

  // Insert PAGE at specific index
  const insertPAGE = useCallback((insertIndex, layout = PAGE_LAYOUTS.TITLE_CONTENT) => {
    return addPAGE(insertIndex, layout);
  }, [addPAGE]);

  // Duplicate PAGE
  const duplicatePAGE = useCallback((PAGEId) => {
    const PAGEIndex = PAGES.findIndex(s => s.id === PAGEId);
    if (PAGEIndex === -1) return null;

    const originalPAGE = PAGES[PAGEIndex];
    const duplicatedPAGE = {
      ...originalPAGE,
      id: uuidv4(),
      title: `${originalPAGE.title} (Copy)`,
      elements: originalPAGE.elements.map(el => ({ ...el, id: uuidv4() })),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      hasUnsavedChanges: true,
    };

    setPAGES(currentPAGES => {
      const updatedPAGES = [...currentPAGES];
      updatedPAGES.splice(PAGEIndex + 1, 0, duplicatedPAGE);

      return updatedPAGES.map((PAGE, index) => ({
        ...PAGE,
        order: index + 1,
      }));
    });

    setCurrentPAGEId(duplicatedPAGE.id);
    return duplicatedPAGE.id;
  }, [PAGES]);

  // Reorder PAGES
  const reorderPAGES = useCallback((fromIndex, toIndex) => {
    setPAGES(currentPAGES => {
      const reorderedPAGES = [...currentPAGES];
      const [movedPAGE] = reorderedPAGES.splice(fromIndex, 1);
      reorderedPAGES.splice(toIndex, 0, movedPAGE);

      // Update order numbers
      return reorderedPAGES.map((PAGE, index) => ({
        ...PAGE,
        order: index + 1,
        updated_at: new Date().toISOString(),
      }));
    });

    // Update printable metadata
    setprintableMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));
  }, []);

  // Update PAGE properties
  const updatePAGE = useCallback((PAGEId, updates) => {
    // If collaborative, write to Yjs (EXCEPT if it's a legacy recursive call loop)
    // We handle ELEMENTS separately in updateElement/addElement/deleteElement to be granular.
    // So if 'updates' contains 'elements', we assume it's a full replace (Layout/Undo) or legacy call.
    const isCollabConnected = collaboration?.doc && collaboration?.status === 'connected';
    if (isCollabConnected && !isRemoteUpdate.current) {
      const { yPAGE } = getYPAGE(PAGEId);
      if (yPAGE) {
        collaboration.doc.transact(() => {
          Object.keys(updates).forEach(key => {
            if (key === 'elements') {
              // Full elements replace (Careful!)
              const yElements = yPAGE.get('elements');
              if (yElements) {
                yElements.delete(0, yElements.length);
                const newEls = updates[key].map(el => {
                  const yEl = new Y.Map();
                  Object.keys(el).forEach(k => yEl.set(k, el[k]));
                  return yEl;
                });
                yElements.push(newEls);
              }
            } else {
              yPAGE.set(key, updates[key]);
            }
          });
          yPAGE.set('updated_at', new Date().toISOString());
          yPAGE.set('hasUnsavedChanges', true);
        });
      }
      return;
    }

    setPAGES(currentPAGES =>
      currentPAGES.map(PAGE =>
        PAGE.id === PAGEId
          ? {
            ...PAGE,
            ...updates,
            updated_at: new Date().toISOString(),
            hasUnsavedChanges: true,
          }
          : PAGE
      )
    );

    setprintableMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));
  }, [getYPAGE, collaboration]);

  // Update PAGE title
  const updatePAGETitle = useCallback((PAGEId, title) => {
    updatePAGE(PAGEId, { title: title.trim() || 'Untitled PAGE' });
  }, [updatePAGE]);

  // Update PAGE notes
  const updatePAGENotes = useCallback((PAGEId, notes) => {
    updatePAGE(PAGEId, { notes });
  }, [updatePAGE]);

  // Toggle PAGE hidden state
  const togglePAGEHidden = useCallback((PAGEId) => {
    setPAGES(prev => prev.map(p => p.id === PAGEId ? { ...p, hidden: !p.hidden } : p));
  }, []);

  // Update PAGE background
  const updatePAGEBackground = useCallback((PAGEId, { backgroundColor, backgroundImage, backgroundOpacity, removeBackgroundImage }) => {
    const updates = {};
    if (backgroundColor !== undefined) updates.backgroundColor = backgroundColor;
    if (backgroundImage !== undefined) updates.backgroundImage = backgroundImage;

    // Update opacity on background image element(s)
    if (backgroundOpacity !== undefined) {
      const page = PAGES.find(p => p.id === PAGEId);
      if (page) {
        updates.elements = page.elements.map(el =>
          el.imageType === 'background' ? { ...el, opacity: backgroundOpacity } : el
        );
      }
    }

    // Remove background image element(s)
    if (removeBackgroundImage) {
      const page = PAGES.find(p => p.id === PAGEId);
      if (page) {
        updates.elements = (updates.elements || page.elements).filter(el => el.imageType !== 'background');
        updates.backgroundImage = null;
      }
    }

    updatePAGE(PAGEId, updates);
  }, [updatePAGE, PAGES]);

  // Update PAGE layout
  const updatePAGELayout = useCallback((PAGEId, layout) => {
    const PAGE = PAGES.find(s => s.id === PAGEId);
    if (!PAGE) return;

    // Preserve existing text content when changing layout
    const existingTitle = PAGE.elements.find(el => el.textType === 'title')?.content || '';
    const existingSubtitle = PAGE.elements.find(el => el.textType === 'subtitle')?.content || '';
    const existingBody = PAGE.elements.find(el => el.textType === 'body')?.content || '';

    const newElements = createLayoutElements(layout, existingTitle, existingSubtitle, existingBody);
    updatePAGE(PAGEId, { layout, elements: newElements });
  }, [PAGES, updatePAGE]);

  // Add element to PAGE
  const addElement = useCallback((PAGEId, elementType, options = {}) => {
    const PAGE = PAGES.find(s => s.id === PAGEId);
    if (!PAGE) return null;

    let newElement;
    switch (elementType) {
      case ELEMENT_TYPES.TEXT:
        newElement = createDefaultTextElement(options.textType || 'body', options.content || '', options.position);
        break;
      case ELEMENT_TYPES.IMAGE:
        newElement = createDefaultImageElement(options.src || '', options.position, options.isUserMedia);
        break;
      case ELEMENT_TYPES.SHAPE:
        newElement = createDefaultShapeElement(options.shapeType || 'rectangle', options.position);
        break;
      case ELEMENT_TYPES.ICON:
        // Fix: Pass the entire options object as the second arg if it contains position props
        // The original code was only passing options.position, but printableCanvas passes flat options
        const iconPos = options.position || {
          x: options.x,
          y: options.y,
          fill: options.fill,
          size: options.size,
          zIndex: options.zIndex
        };
        newElement = createDefaultIconElement(options.iconName || 'star', iconPos);
        break;
      case ELEMENT_TYPES.CHART:
        newElement = createDefaultChartElement(options.chartConfig, options.position);
        break;
      case ELEMENT_TYPES.TABLE:
        // Pass specifically tableConfig and position
        newElement = createDefaultTableElement(options.tableConfig, options.position);
        break;
      case ELEMENT_TYPES.VIDEO:
        newElement = createDefaultVideoElement(options.src || '', options);
        break;
      case ELEMENT_TYPES.EMBED:
        newElement = createDefaultEmbedElement(options);
        break;
      case ELEMENT_TYPES.BUTTON:
        newElement = createDefaultButtonElement(options);
        break;
      case ELEMENT_TYPES.ANIMATION:
        newElement = createDefaultAnimationElement(options);
        break;
      case ELEMENT_TYPES.SVG_DIAGRAM:
        newElement = createDefaultSvgDiagramElement(options);
        break;
      default:
        return null;
    }

    // Collaborative Granular Add - only use Y.js path if actually connected
    const isCollabConnected = collaboration?.doc && collaboration?.status === 'connected';
    if (isCollabConnected && !isRemoteUpdate.current) {
      const { yPAGE } = getYPAGE(PAGEId);
      if (yPAGE) {
        const yElements = yPAGE.get('elements');
        if (yElements) {
          collaboration.doc.transact(() => {
            // Explicitly create Y.Map to ensure property-level granularity (Y.Map.set vs Y.Array JSON)
            const yEl = new Y.Map();
            Object.keys(newElement).forEach(k => yEl.set(k, newElement[k]));
            yElements.push([yEl]);
          });
        }
      }
      return newElement.id;
    }

    updatePAGE(PAGEId, { elements: [...PAGE.elements, newElement] });
    setSelectedElementId(newElement.id);
    return newElement.id;
  }, [PAGES, updatePAGE, getYPAGE, collaboration]);

  // Update element on PAGE
  const updateElement = useCallback((PAGEId, elementId, updates) => {
    const isCollabConnected = collaboration?.doc && collaboration?.status === 'connected';
    console.log(`🔄 [UPDATE_ELEMENT] Called for PAGEId: ${PAGEId}, elementId: ${elementId}, hasCollab: ${!!collaboration?.doc}, isConnected: ${isCollabConnected}`);
    
    // Collaborative Granular Update - only use Y.js path if actually connected
    if (isCollabConnected && !isRemoteUpdate.current) {
      if (elementId === null && updates.elements !== undefined) {
        // Full replace logic handled by updatePAGE
        updatePAGE(PAGEId, { elements: updates.elements });
        return;
      }

      const { yPAGE } = getYPAGE(PAGEId);
      console.log(`🔄 [UPDATE_ELEMENT] Y.js path: yPAGE found: ${!!yPAGE}`);
      
      if (yPAGE) {
        const yElements = yPAGE.get('elements'); // Y.Array
        console.log(`🔄 [UPDATE_ELEMENT] Y.js yElements found: ${!!yElements}, length: ${yElements?.length || 0}`);
        
        if (yElements) {
          // Find element in Y.Array
          // Linear search
          let targetIndex = -1;
          let targetEl = null;
          // Iterate Y.Array
          for (let i = 0; i < yElements.length; i++) {
            const el = yElements.get(i); // Should be Y.Map
            // el might be a Y.Map or plain object depending on insertion.
            // safely accessing:
            const id = el.get ? el.get('id') : el.id;
            if (id === elementId) {
              targetIndex = i;
              targetEl = el;
              break;
            }
          }

          console.log(`🔄 [UPDATE_ELEMENT] Y.js search result: targetIndex: ${targetIndex}, hasSet: ${!!targetEl?.set}`);

          if (targetEl && targetEl.set) {
            collaboration.doc.transact(() => {
              Object.keys(updates).forEach(key => {
                targetEl.set(key, updates[key]);
              });
            });
            console.log('[YJS] Element updated via Y.js:', elementId);
            return; // Success - Y.js observer will update React state
          } else {
            console.warn('[YJS] Element not found or not Y.Map:', elementId, '- falling back to local update');
            // Fall through to local state update below
          }
        }
      }
      // If Y.js update failed, fall through to local state update
    }

    // Special case: if elementId is null and updates.elements is provided,
    // this is a full PAGE restoration (used by Undo/Redo)
    if (elementId === null && updates.elements !== undefined) {
      console.log('🔄 [UPDATE_ELEMENT] Full elements replacement for Undo/Redo');
      updatePAGE(PAGEId, { elements: updates.elements });
      return;
    }

    // Use functional update to avoid stale closure issues when multiple updates happen quickly
    console.log(`📝 [UPDATE_ELEMENT] Local update for ${elementId}`);
    
    setPAGES(currentPAGES => {
      return currentPAGES.map(PAGE => {
        if (PAGE.id !== PAGEId) return PAGE;
        
        const elementExists = PAGE.elements.some(el => el.id === elementId);
        if (!elementExists) {
          console.warn(`[UPDATE_ELEMENT] Element ${elementId} not found in PAGE ${PAGEId}`);
          return PAGE;
        }
        
        const updatedElements = PAGE.elements.map(el =>
          el.id === elementId ? { ...el, ...updates } : el
        );
        
        return {
          ...PAGE,
          elements: updatedElements,
          updated_at: new Date().toISOString(),
          hasUnsavedChanges: true,
        };
      });
    });
    
    setprintableMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));
  }, [getYPAGE, collaboration]);

  // Update multiple elements in a PAGE atomically (batch update for AI multi-select edits)
  const updateMultipleElements = useCallback((PAGEId, elementUpdates) => {
    // elementUpdates is an array of { elementId, updates } objects
    if (!elementUpdates || elementUpdates.length === 0) {
      console.log('[UPDATE_MULTIPLE_ELEMENTS] No updates provided');
      return;
    }

    console.log(`🔄 [UPDATE_MULTIPLE_ELEMENTS] Batch updating ${elementUpdates.length} elements in PAGE ${PAGEId}`);

    // Y.js collaborative batch update - only use Y.js path if actually connected
    const isCollabConnected = collaboration?.doc && collaboration?.status === 'connected';
    if (isCollabConnected && !isRemoteUpdate.current) {
      const { yPAGE } = getYPAGE(PAGEId);
      if (yPAGE) {
        const yElements = yPAGE.get('elements');
        if (yElements) {
          collaboration.doc.transact(() => {
            for (let i = 0; i < yElements.length; i++) {
              const yElement = yElements.get(i);
              const elementId = yElement.get ? yElement.get('id') : yElement.id;
              const updateItem = elementUpdates.find(u => u.elementId === elementId);
              if (updateItem && yElement.set) {
                Object.entries(updateItem.updates).forEach(([key, value]) => {
                  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                    const existing = yElement.get(key) || {};
                    yElement.set(key, { ...existing, ...value });
                  } else {
                    yElement.set(key, value);
                  }
                });
              }
            }
          });
          console.log('[YJS] Batch updated elements via Y.js');
          return;
        }
      }
    }

    // Local state batch update - avoids stale closure issues
    setPAGES(currentPAGES => {
      return currentPAGES.map(PAGE => {
        if (PAGE.id !== PAGEId) return PAGE;

        const updatedElements = PAGE.elements.map(el => {
          const updateItem = elementUpdates.find(u => u.elementId === el.id);
          if (updateItem) {
            return { ...el, ...updateItem.updates };
          }
          return el;
        });

        const updatedCount = elementUpdates.filter(u => 
          PAGE.elements.some(el => el.id === u.elementId)
        ).length;
        console.log(`📝 [UPDATE_MULTIPLE_ELEMENTS] Updated ${updatedCount}/${elementUpdates.length} elements`);

        return {
          ...PAGE,
          elements: updatedElements,
          updated_at: new Date().toISOString(),
          hasUnsavedChanges: true,
        };
      });
    });

    setprintableMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));
  }, [getYPAGE, collaboration]);

  // Delete element from PAGE
  const deleteElement = useCallback((PAGEId, elementId) => {
    // Collaborative Granular Delete - only use Y.js path if actually connected
    const isCollabConnected = collaboration?.doc && collaboration?.status === 'connected';
    if (isCollabConnected && !isRemoteUpdate.current) {
      const { yPAGE } = getYPAGE(PAGEId);
      if (yPAGE) {
        const yElements = yPAGE.get('elements');
        if (yElements) {
          let targetIndex = -1;
          for (let i = 0; i < yElements.length; i++) {
            const el = yElements.get(i);
            const id = el.get ? el.get('id') : el.id;
            if (id === elementId) {
              targetIndex = i;
              break;
            }
          }
          if (targetIndex !== -1) {
            collaboration.doc.transact(() => {
              yElements.delete(targetIndex, 1);
            });
            if (selectedElementId === elementId) {
              setSelectedElementId(null);
            }
          }
        }
      }
      return;
    }

    const PAGE = PAGES.find(s => s.id === PAGEId);
    if (!PAGE) return;

    const filteredElements = PAGE.elements.filter(el => el.id !== elementId);
    updatePAGE(PAGEId, { elements: filteredElements });

    if (selectedElementId === elementId) {
      setSelectedElementId(null);
    }
  }, [PAGES, updatePAGE, selectedElementId, getYPAGE, collaboration]);

  // Delete multiple elements from PAGE (atomic batch delete)
  const deleteMultipleElements = useCallback((PAGEId, elementIds) => {
    const PAGE = PAGES.find(s => s.id === PAGEId);
    if (!PAGE || !elementIds || elementIds.length === 0) return;

    const idsToDelete = new Set(elementIds);
    const filteredElements = PAGE.elements.filter(el => !idsToDelete.has(el.id));
    updatePAGE(PAGEId, { elements: filteredElements });

    // Clear selection if any selected element was deleted
    if (selectedElementId && idsToDelete.has(selectedElementId)) {
      setSelectedElementId(null);
    }
  }, [PAGES, updatePAGE, selectedElementId]);

  // Reorder elements (bring to front/back)
  const reorderElement = useCallback((PAGEId, elementId, direction) => {
    const PAGE = PAGES.find(s => s.id === PAGEId);
    if (!PAGE) return;

    const elementIndex = PAGE.elements.findIndex(el => el.id === elementId);
    if (elementIndex === -1) return;

    const elements = [...PAGE.elements];
    const [element] = elements.splice(elementIndex, 1);

    switch (direction) {
      case 'front':
        elements.push(element);
        break;
      case 'back':
        elements.unshift(element);
        break;
      case 'forward':
        elements.splice(Math.min(elementIndex + 1, elements.length), 0, element);
        break;
      case 'backward':
        elements.splice(Math.max(elementIndex - 1, 0), 0, element);
        break;
    }

    updatePAGE(PAGEId, { elements });
  }, [PAGES, updatePAGE]);

  // Update printable metadata
  const updateprintableMetadata = useCallback((updates) => {
    setprintableMetadata(prev => ({
      ...prev,
      ...updates,
      updated_at: new Date().toISOString(),
    }));
  }, []);


  // ==================== Smart Contrast Utilities ====================
  const hexToRgb = (hex) => {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
      r: parseInt(result[1], 16),
      g: parseInt(result[2], 16),
      b: parseInt(result[3], 16)
    } : null;
  };

  const getLuminance = (hex) => {
    if (!hex) return 1; // Default to light if undefined
    const rgb = hexToRgb(hex);
    if (!rgb) return 1; // Default to light if invalid

    const [r, g, b] = [rgb.r, rgb.g, rgb.b].map(val => {
      val = val / 255;
      return val <= 0.03928 ? val / 12.92 : Math.pow((val + 0.055) / 1.055, 2.4);
    });

    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };

  const getContrastTextColor = (backgroundColor) => {
    const luminance = getLuminance(backgroundColor);
    return luminance > 0.5 ? '#111827' : '#E5E7EB';
  };

  // Helper: Check if inner element is visually contained within outer element
  const isContained = (inner, outer) => {
    if (!inner || !outer) return false;

    // padding/tolerance
    const tolerance = 10;

    return (
      inner.x >= outer.x - tolerance &&
      inner.y >= outer.y - tolerance &&
      (inner.x + inner.width) <= (outer.x + outer.width + tolerance) &&
      (inner.y + inner.height) <= (outer.y + outer.height + tolerance)
    );
  };

  // Apply style theme to all PAGES
  const applyStyleToAllPAGES = useCallback((style) => {
    setprintableMetadata(prev => ({
      ...prev,
      style: style,
      updated_at: new Date().toISOString(),
    }));

    // Normalize style object (handle flat AI response)
    const normalizedStyle = {
      ...style,
      textStyles: style.textStyles || {
        title: { fontFamily: style.fontFamily, color: style.textPrimary },
        subtitle: { fontFamily: style.fontFamily, color: style.textSecondary },
        body: { fontFamily: style.fontFamily, color: style.textPrimary || style.textSecondary },
        bullet: { fontFamily: style.fontFamily, color: style.textPrimary },
        caption: { fontFamily: style.fontFamily, color: style.textSecondary }
      }
    };

    // Helper to determine main colors
    const textPrimary = normalizedStyle.textPrimary || normalizedStyle.textStyles?.body?.color || '#333333';
    const textSecondary = normalizedStyle.textSecondary || normalizedStyle.textStyles?.subtitle?.color || '#666666';
    const surface = normalizedStyle.surface || normalizedStyle.PAGEBackground || '#ffffff';
    const accent = normalizedStyle.accentColor || normalizedStyle.preview?.accent || '#3B82F6';

    // Helper function to remap colors from old palette to new palette
    const remapColor = (oldColor) => {
      if (!oldColor) return oldColor;

      const hex = oldColor.toLowerCase();

      // Accent colors (blues, greens, bright colors)
      if (/#(3b82f6|4ade80|f59e0b|ec4899|8b5cf6|06b6d4)/.test(hex)) {
        return accent || oldColor;
      }
      // Dark text colors - Remap to main text color
      if (/#(000|111|1a1a|1f2937|0f172a|333|374151)/.test(hex)) {
        return textPrimary || oldColor;
      }
      // Light/white text
      if (/#(fff|f9f|fafafa|e5e5e5)/.test(hex)) {
        return surface || oldColor;
      }
      // Secondary/gray text
      if (/#(666|888|999|6b7280|9ca3af)/.test(hex)) {
        return textSecondary || oldColor;
      }

      return oldColor; // Keep as-is if no pattern match
    };

    // Apply style to each PAGE's elements
    setPAGES(currentPAGES =>
      currentPAGES.map(PAGE => {
        let PAGEChanged = false;

        // Update background if needed
        const newBackgroundColor = normalizedStyle.PAGEBackground || PAGE.backgroundColor;
        if (newBackgroundColor !== PAGE.backgroundColor) {
          PAGEChanged = true;
        }

        // Identify potential background containers (Shapes, Cards) sorted by Z-index (highest first logic?)
        // We want the *top-most* container that is *below* the text.
        const containers = PAGE.elements.filter(el =>
          el.type === ELEMENT_TYPES.SHAPE ||
          el.type === 'card'
        ).sort((a, b) => (b.zIndex || 0) - (a.zIndex || 0));

        const newElements = PAGE.elements.map(el => {
          let elChanged = false;
          let newEl = { ...el };

          // TEXT ELEMENTS
          if (el.type === ELEMENT_TYPES.TEXT) {
            const textStyle = normalizedStyle.textStyles?.[el.textType] || {}; // Use normalizedStyle
            const newFontFamily = textStyle.fontFamily || normalizedStyle.fontFamily || el.fontFamily;

            // SMART CONTRAST LOGIC
            // 1. Determine local background
            let localBackground = newBackgroundColor;

            // Checks if contained in any shape that is BEHIND it (lower zIndex)
            const parentContainer = containers.find(container =>
              (container.zIndex || 0) < (el.zIndex || 0) && // Must be behind
              isContained(el, container) // Must visually contain
            );

            if (parentContainer) {
              localBackground = parentContainer.fill || parentContainer.backgroundColor || newBackgroundColor;
            }

            // 2. Calculate smart color based on local background
            const smartColor = getContrastTextColor(localBackground);

            // 3. Decide: Use Theme Color OR Smart Color?
            // If the text is "Title" style, we might want to respect theme branding (e.g. Blue Title).
            // But if contrast is bad, we MUST override.

            // Default to theme color first
            let targetColor = textStyle.color || el.color;

            // Check theme contrast
            const themeLuminance = getLuminance(targetColor);
            const bgLuminance = getLuminance(localBackground);
            const contrastRatio = (Math.max(themeLuminance, bgLuminance) + 0.05) / (Math.min(themeLuminance, bgLuminance) + 0.05);

            // If theme color has poor contrast (< 3:1), force smart color
            if (contrastRatio < 3) {
              targetColor = smartColor;
            }

            // Apply changes
            if (newFontFamily !== el.fontFamily) { newEl.fontFamily = newFontFamily; elChanged = true; }
            if (targetColor !== el.color) { newEl.color = targetColor; newEl.fill = targetColor; elChanged = true; }
          }

          // SHAPE ELEMENTS
          else if (el.type === ELEMENT_TYPES.SHAPE) {
            let newFill = el.fill;
            let newStroke = el.stroke;

            // If shape was previously matching a card/surface color, map it
            // We can use the simple remapper or strict checking
            // For now, simpler remapper for shapes seems okay, but maybe we should enforce cardBackground for 'card-like' shapes?

            // Just use remapper for now
            newFill = remapColor(el.fill);
            newStroke = remapColor(el.stroke);

            // Special case: If this is a "Card" shape (often big rect), maybe apply theme.cardBackground?
            // Identify if huge? width > 400?
            if (el.width > 300 && el.height > 200) {
              if (normalizedStyle.cardBackground && newFill !== normalizedStyle.cardBackground) {
                // Only if it was 'white-ish' or 'dark-ish' before? 
                // Let's be conservative: use remapColor which handles this via palette matching.
              }
            }

            if (newFill !== el.fill) { newEl.fill = newFill; elChanged = true; }
            if (newStroke !== el.stroke) { newEl.stroke = newStroke; elChanged = true; }
          }

          // ICON ELEMENTS
          else if (el.type === ELEMENT_TYPES.ICON) {
            // Respect existing color if valid, otherwise remap or default
            // FIX: Don't force accentColor if we already have a specific color set (e.g. Black/Purple from user choice)
            const currentFill = el.fill;
            const remapped = remapColor(currentFill);

            // Only use accentColor as fallback if:
            // 1. No current color 
            // 2. Current color was explicitly the OLD accent color (so we remap it)
            // 3. We are in a "fresh" apply where everything resets

            // If simple remapping returns something, use it. if not, keep original.
            // Only if original is missing/invalid, default to accent.
            const newFill = remapped || currentFill || style.accentColor;

            if (newFill !== el.fill) { newEl.fill = newFill; elChanged = true; }
          }

          // CARD ELEMENTS
          else if (el.type === 'card') {
            const newBg = remapColor(el.backgroundColor) || normalizedStyle.cardBackground;
            const newBorder = remapColor(el.borderColor) || normalizedStyle.cardBorder;
            const newIcon = remapColor(el.iconColor) || style.accentColor;

            if (newBg !== el.backgroundColor) { newEl.backgroundColor = newBg; elChanged = true; }
            if (newBorder !== el.borderColor) { newEl.borderColor = newBorder; elChanged = true; }
            if (newIcon !== el.iconColor) { newEl.iconColor = newIcon; elChanged = true; }
          }

          if (elChanged) {
            PAGEChanged = true;
            return newEl;
          }
          return el; // Return original reference if no change
        });

        if (PAGEChanged) {
          return {
            ...PAGE,
            backgroundColor: newBackgroundColor,
            elements: newElements,
            updated_at: new Date().toISOString(),
            hasUnsavedChanges: true,
          };
        }
        return PAGE; // Return original reference if no change
      })
    );
  }, []);

  // Mark PAGE as saved
  const markPAGEAsSaved = useCallback((PAGEId) => {
    setPAGES(currentPAGES =>
      currentPAGES.map(PAGE =>
        PAGE.id === PAGEId
          ? { ...PAGE, hasUnsavedChanges: false }
          : PAGE
      )
    );
  }, []);

  // Mark all PAGES as saved
  const markAllPAGESSaved = useCallback(() => {
    setPAGES(currentPAGES =>
      currentPAGES.map(PAGE => ({
        ...PAGE,
        hasUnsavedChanges: false,
      }))
    );
  }, []);

  // Get PAGE by ID
  const getPAGEById = useCallback((PAGEId) => {
    return PAGES.find(PAGE => PAGE.id === PAGEId);
  }, [PAGES]);

  // Get current PAGE
  const getCurrentPAGE = useCallback(() => {
    return PAGES.find(PAGE => PAGE.id === currentPAGEId);
  }, [PAGES, currentPAGEId]);

  // Get selected element
  const getSelectedElement = useCallback(() => {
    const PAGE = getCurrentPAGE();
    if (!PAGE || !selectedElementId) return null;
    return PAGE.elements.find(el => el.id === selectedElementId);
  }, [getCurrentPAGE, selectedElementId]);

  // Get PAGES summary for AI context
  const getPAGESSummary = useCallback(() => {
    return PAGES.map(PAGE => ({
      id: PAGE.id,
      title: PAGE.title,
      layout: PAGE.layout,
      order: PAGE.order,
      elementCount: PAGE.elements.length,
      textContent: PAGE.elements
        .filter(el => el.type === ELEMENT_TYPES.TEXT)
        .map(el => el.content)
        .join(' ')
        .substring(0, 200),
    }));
  }, [PAGES]);

  // Keep the current-PAGE pointer VALID and POSITIONALLY STABLE.
  //
  // While the active page still exists, remember its index. If it ever
  // disappears — deleted here, removed by the AI agent's operations, or by a
  // collaborator — snap to the page now occupying the CLOSEST position
  // (clamped to the new length), never blindly to page 0. Resetting to the
  // first page on every structural change was the "list view jumps to another
  // page number" bug.
  useEffect(() => {
    const idx = PAGES.findIndex(s => s.id === currentPAGEId);
    if (idx >= 0) {
      lastValidIndexRef.current = idx;
      return;
    }
    if (PAGES.length === 0) {
      if (currentPAGEId !== null) setCurrentPAGEId(null);
      return;
    }
    const target = PAGES[Math.min(lastValidIndexRef.current, PAGES.length - 1)];
    if (target && target.id !== currentPAGEId) {
      setCurrentPAGEId(target.id);
    }
  }, [PAGES, currentPAGEId]);

  // Clear element selection when changing PAGES
  useEffect(() => {
    setSelectedElementId(null);
  }, [currentPAGEId]);

  return {
    // State
    PAGES,
    setPAGES, // Direct setter for bulk updates
    currentPAGEId,
    selectedElementId,
    printableMetadata,

    // PAGE management
    addPAGE,
    deletePAGE,
    insertPAGE,
    duplicatePAGE,
    reorderPAGES,
    updatePAGE,
    updatePAGETitle,
    updatePAGENotes,
    updatePAGEBackground,
    updatePAGELayout,

    // Element management
    addElement,
    updateElement,
    updateMultipleElements,
    deleteElement,
    deleteMultipleElements,
    reorderElement,
    setSelectedElementId,

    // Style management
    applyStyleToAllPAGES,
    updateprintableMetadata,

    // Navigation
    setCurrentPAGEId,

    // Visibility
    togglePAGEHidden,

    // Utilities
    getPAGEById,
    getCurrentPAGE,
    getSelectedElement,
    getPAGESSummary,
    markPAGEAsSaved,
    markAllPAGESSaved,

    // Computed values
    hasUnsavedChanges: PAGES.some(PAGE => PAGE.hasUnsavedChanges),
    totalPAGES: PAGES.length,

    // Constants
    PAGE_LAYOUTS,
    ELEMENT_TYPES,
    PAGE_WIDTH,
    PAGE_HEIGHT,
  };
};

export default usePrintablePages;
