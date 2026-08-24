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


// Default slide dimensions (16:9 aspect ratio)
export const SLIDE_WIDTH = 960;
export const SLIDE_HEIGHT = 540;

// Default slide element types
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
  width: position.width || SLIDE_WIDTH - 100,
  height: position.height || (type === 'title' ? 80 : type === 'subtitle' ? 50 : 300),
  zIndex: position.zIndex || 1, // Fix: Accept zIndex
  fontSize: type === 'title' ? 32 : type === 'subtitle' ? 22 : 16,
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
  x: position.x || (SLIDE_WIDTH / 2 - 240), // Center by default if not specified
  y: position.y || (SLIDE_HEIGHT / 2 - 160),
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
  x: position.x || (SLIDE_WIDTH / 2 - 200),
  y: position.y || (SLIDE_HEIGHT / 2 - 150),
  width: position.width || 400,
  height: position.height || 300,
  zIndex: position.zIndex || 50,
  locked: false,
});

// Create a default SVG diagram element (AI-generated inline SVG).
// Field naming matches the existing svg_diagram renderer in PresentationCanvas
// (uses element.svgContent + element.fillColor for currentColor substitution).
const createDefaultSvgDiagramElement = (options = {}) => ({
  id: uuidv4(),
  type: ELEMENT_TYPES.SVG_DIAGRAM,
  svgContent: options.svgContent || options.svg || '',
  prompt: options.prompt || '',
  diagramKind: options.diagramKind || 'flowchart',
  diagramTitle: options.diagramTitle || options.title || '',
  fillColor: options.fillColor || '#3B82F6',
  x: options.position?.x ?? options.x ?? 150,
  y: options.position?.y ?? options.y ?? 100,
  width: options.position?.width ?? options.width ?? 660,
  height: options.position?.height ?? options.height ?? 340,
  zIndex: options.position?.zIndex ?? options.zIndex ?? 1,
  opacity: 1,
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

// Default slide templates
export const SLIDE_LAYOUTS = {
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
    case SLIDE_LAYOUTS.TITLE:
      return [
        createDefaultTextElement('title', title, { y: 200, width: SLIDE_WIDTH - 100 }),
        createDefaultTextElement('subtitle', subtitle, { y: 280, width: SLIDE_WIDTH - 100 }),
      ];

    case SLIDE_LAYOUTS.TITLE_CONTENT:
      return [
        createDefaultTextElement('title', title, { y: 40, height: 60 }),
        createDefaultTextElement('body', content, { y: 120, height: 380 }),
      ];

    case SLIDE_LAYOUTS.TITLE_TWO_COLUMN:
      return [
        createDefaultTextElement('title', title, { y: 40, height: 60 }),
        createDefaultTextElement('body', '', { x: 50, y: 120, width: 420, height: 380 }),
        createDefaultTextElement('body', '', { x: 490, y: 120, width: 420, height: 380 }),
      ];

    case SLIDE_LAYOUTS.TITLE_IMAGE_LEFT:
      return [
        createDefaultTextElement('title', title, { y: 40, height: 60 }),
        createDefaultImageElement('', { x: 50, y: 120, width: 400, height: 350 }),
        createDefaultTextElement('body', content, { x: 480, y: 120, width: 430, height: 350 }),
      ];

    case SLIDE_LAYOUTS.TITLE_IMAGE_RIGHT:
      return [
        createDefaultTextElement('title', title, { y: 40, height: 60 }),
        createDefaultTextElement('body', content, { x: 50, y: 120, width: 430, height: 350 }),
        createDefaultImageElement('', { x: 510, y: 120, width: 400, height: 350 }),
      ];

    case SLIDE_LAYOUTS.IMAGE_FULL:
      return [
        createDefaultImageElement('', { x: 0, y: 0, width: SLIDE_WIDTH, height: SLIDE_HEIGHT }),
        createDefaultTextElement('title', title, { y: SLIDE_HEIGHT - 100, color: '#ffffff' }),
      ];

    case SLIDE_LAYOUTS.BLANK:
    default:
      return [];
  }
};

export const usePresentationSlides = (initialPresentation = null, collaboration = null) => {
  // Initialize state from existing presentation or create new
  const [slides, setSlides] = useState(() => {
    if (initialPresentation?.slides?.length > 0) {
      return initialPresentation.slides;
    }
    // Create default title slide
    return [{
      id: uuidv4(),
      order: 1,
      title: 'Title Slide',
      layout: SLIDE_LAYOUTS.TITLE,
      elements: createLayoutElements(SLIDE_LAYOUTS.TITLE, 'Presentation Title', 'Subtitle or Author Name'),
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

  const [currentSlideId, setCurrentSlideId] = useState(() => {
    return initialPresentation?.currentSlideId || slides[0]?.id;
  });

  const [presentationMetadata, setPresentationMetadata] = useState(() => ({
    id: initialPresentation?.id || uuidv4(),
    title: initialPresentation?.title || 'Untitled Presentation',
    description: initialPresentation?.description || '',
    created_at: initialPresentation?.created_at || new Date().toISOString(),
    updated_at: new Date().toISOString(),
    overall_goal: initialPresentation?.overall_goal || '',
    target_audience: initialPresentation?.target_audience || '',
    style: initialPresentation?.style || null, // Will hold the selected style theme
    aspectRatio: initialPresentation?.aspectRatio || '16:9',
  }));

  // Selected element on current slide
  const [selectedElementId, setSelectedElementId] = useState(null);

  // Refs mirroring the latest state so imperative handlers (delete/duplicate)
  // can compute neighbor selection from a guaranteed-fresh snapshot (no stale
  // closures), and so the heal-effect can remember where the cursor was.
  const slidesRef = useRef(slides);
  const currentSlideIdRef = useRef(currentSlideId);
  const lastValidIndexRef = useRef(0);
  useEffect(() => { slidesRef.current = slides; }, [slides]);
  useEffect(() => { currentSlideIdRef.current = currentSlideId; }, [currentSlideId]);

  // Handle initialPresentation changes (when loading an existing presentation)
  useEffect(() => {
    if (initialPresentation?.slides?.length > 0) {
      const loadedSlides = initialPresentation.slides.map((slide, index) => ({
        id: slide.id || uuidv4(),
        order: slide.order || index + 1,
        title: slide.title || `Slide ${index + 1}`,
        layout: slide.layout || SLIDE_LAYOUTS.BLANK,
        elements: slide.elements || [],
        notes: slide.notes || '',
        backgroundColor: slide.backgroundColor || '#ffffff',
        backgroundImage: slide.backgroundImage || null,
        transition: slide.transition || 'fade',
        created_at: slide.created_at || new Date().toISOString(),
        updated_at: slide.updated_at || new Date().toISOString(),
        hasUnsavedChanges: false,
        hidden: slide.hidden || false,
      }));

      setSlides(loadedSlides);

      if (loadedSlides.length > 0) {
        setCurrentSlideId(loadedSlides[0].id);
      }

      // Update metadata from loaded presentation
      setPresentationMetadata(prev => ({
        ...prev,
        id: initialPresentation.id || prev.id,
        title: initialPresentation.title || prev.title,
        description: initialPresentation.description || prev.description,
        overall_goal: initialPresentation.goal || initialPresentation.overall_goal || prev.overall_goal,
        style: initialPresentation.style || prev.style,
        updated_at: new Date().toISOString(),
      }));
    } else if (initialPresentation === null) {
      // Reset to default for new presentation
      const defaultSlide = {
        id: uuidv4(),
        order: 1,
        title: 'Title Slide',
        layout: SLIDE_LAYOUTS.TITLE,
        elements: createLayoutElements(SLIDE_LAYOUTS.TITLE, 'Presentation Title', 'Subtitle or Author Name'),
        notes: '',
        backgroundColor: '#ffffff',
        backgroundImage: null,
        transition: 'fade',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        hasUnsavedChanges: false,
      };
      setSlides([defaultSlide]);
      setCurrentSlideId(defaultSlide.id);
      setPresentationMetadata({
        id: null,
        title: 'Untitled Presentation',
        description: '',
        overall_goal: '',
        target_audience: '',
        style: null,
        aspectRatio: '16:9',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    }
  }, [initialPresentation]);

  // ==================== Yjs Synchronization ====================
  const isRemoteUpdate = useRef(false);
  const isLocalUpdate = useRef(false); // Track when local updates are in progress to prevent observer overwrite

  useEffect(() => {
    if (!collaboration || !collaboration.doc) return;

    const doc = collaboration.doc;
    const ySlides = doc.getArray('slides');

    // Initial Sync: Yjs -> Local OR Local -> Yjs
    if (ySlides.length === 0 && slides.length > 0) {
      // Initialize Yjs from local
      doc.transact(() => {
        slides.forEach(slide => {
          const ySlide = new Y.Map();
          // Copy all properties
          Object.keys(slide).forEach(key => {
            if (key === 'elements') {
              const yElements = new Y.Array();
              slide.elements.forEach(el => {
                const yEl = new Y.Map();
                Object.keys(el).forEach(k => yEl.set(k, el[k]));
                yElements.push([yEl]);
              });
              ySlide.set('elements', yElements);
            } else {
              ySlide.set(key, slide[key]);
            }
          });
          ySlides.push([ySlide]);
        });
      });
    } else if (ySlides.length > 0) {
      // Initialize local from Yjs
      setSlides(ySlides.toJSON());
    }

    // Observer
    const observer = (events) => {
      // Skip observer if we're in the middle of a local update
      // This prevents Y.js from overwriting our local changes before they sync
      if (isLocalUpdate.current) {
        console.log('🔔 [YJS_OBSERVER] Skipping - local update in progress');
        return;
      }
      
      console.log('🔔 [YJS_OBSERVER] Deep observer fired, events:', events?.length || 0);
      isRemoteUpdate.current = true;
      const newSlides = ySlides.toJSON();
      console.log('🔔 [YJS_OBSERVER] Setting slides from Y.js, slides count:', newSlides?.length || 0);
      
      // DEBUG: Log first slide's first element content to track data flow
      if (newSlides[0]?.elements?.[0]) {
        console.log('🔔 [YJS_OBSERVER] First element content preview:', newSlides[0].elements[0].content?.substring(0, 50));
      }
      
      setSlides(newSlides);
      // Simple JSON conversion handles nested elements correctly if consistent
      setTimeout(() => { isRemoteUpdate.current = false; }, 0);
    };

    ySlides.observeDeep(observer);

    return () => {
      ySlides.unobserveDeep(observer);
    };
  }, [collaboration, slides.length]); // Depend on slides.length only for initial check

  // Helper to get Yjs object for a slide
  const getYSlide = useCallback((slideId) => {
    if (!collaboration?.doc) return null;
    const ySlides = collaboration.doc.getArray('slides');
    // Find index - Yjs arrays don't support .find returning the Y.Map directly easily without index
    // But we can iterate.
    // Optimization: Maintain ID->Index map if needed, but linear scan is fine for < 100 slides
    let foundIndex = -1;
    let foundSlide = null;

    // ySlides.forEach is (item, index)
    ySlides.forEach((ySlide, index) => {
      if (ySlide.get('id') === slideId) {
        foundIndex = index;
        foundSlide = ySlide;
      }
    });

    return { ySlide: foundSlide, index: foundIndex, ySlides };
  }, [collaboration]);

  // Add new slide
  const addSlide = useCallback((insertIndex = slides.length, layout = SLIDE_LAYOUTS.TITLE_CONTENT, customElements = null, customSlideData = null) => {
    const newSlide = customSlideData || {
      id: uuidv4(),
      order: insertIndex + 1,
      title: `Slide ${insertIndex + 1}`,
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

    // If collaborative and connected, write to Yjs first
    const isCollabConnected = collaboration?.doc && collaboration?.status === 'connected';
    if (isCollabConnected) {
      const ySlides = collaboration.doc.getArray('slides');
      collaboration.doc.transact(() => {
        const ySlide = new Y.Map();
        // Copy all properties
        Object.keys(newSlide).forEach(key => {
          if (key === 'elements') {
            const yElements = new Y.Array();
            (newSlide.elements || []).forEach(el => {
              const yEl = new Y.Map();
              Object.keys(el).forEach(k => yEl.set(k, el[k]));
              yElements.push([yEl]);
            });
            ySlide.set('elements', yElements);
          } else {
            ySlide.set(key, newSlide[key]);
          }
        });
        
        // Insert at correct position
        if (insertIndex >= ySlides.length) {
          ySlides.push([ySlide]);
        } else {
          ySlides.insert(insertIndex, [ySlide]);
        }
        
        // Reorder all slides in Yjs
        ySlides.forEach((ys, idx) => {
          ys.set('order', idx + 1);
        });
      });
      console.log(`📊 [YJS] Added new slide to Yjs at index ${insertIndex}, total slides: ${ySlides.length}`);
    } else {
      // No collaboration, update local state directly
      setSlides(currentSlides => {
        const updatedSlides = [...currentSlides];
        updatedSlides.splice(insertIndex, 0, newSlide);

        // Reorder all slides
        return updatedSlides.map((slide, index) => ({
          ...slide,
          order: index + 1,
        }));
      });
    }

    // Set the new slide as current
    setCurrentSlideId(newSlide.id);
    setSelectedElementId(null);

    // Update presentation metadata
    setPresentationMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));

    return newSlide.id;
  }, [slides.length, collaboration]);

  // Delete slide
  const deleteSlide = useCallback((slideId) => {
    // Read a fresh snapshot from refs — no side effects inside the state
    // updater (those can double-run under React 18 and corrupt the neighbor
    // pick), and no stale closure on `slides`.
    const cur = slidesRef.current;
    if (cur.length <= 1) {
      console.warn('[PRESENTATION_COMPOSER] Cannot delete the last remaining slide');
      return;
    }
    const idx = cur.findIndex(s => s.id === slideId);
    if (idx < 0) return;

    // Fix selection FIRST, from the pre-delete snapshot: if we're deleting the
    // ACTIVE slide, move to the next one (or the previous if it was last).
    // Deleting a non-active slide must leave the selection exactly where it is.
    if (currentSlideIdRef.current === slideId) {
      const neighbor = cur[idx + 1] || cur[idx - 1] || null;
      setCurrentSlideId(neighbor ? neighbor.id : null);
    }

    setSlides(currentSlides =>
      currentSlides.filter(s => s.id !== slideId).map((slide, index) => ({
        ...slide,
        order: index + 1,
      }))
    );

    setSelectedElementId(null);

    // Update presentation metadata
    setPresentationMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));
  }, []);

  // Insert slide at specific index
  const insertSlide = useCallback((insertIndex, layout = SLIDE_LAYOUTS.TITLE_CONTENT) => {
    return addSlide(insertIndex, layout);
  }, [addSlide]);

  // Duplicate slide
  const duplicateSlide = useCallback((slideId) => {
    const slideIndex = slides.findIndex(s => s.id === slideId);
    if (slideIndex === -1) return null;

    const originalSlide = slides[slideIndex];
    const duplicatedSlide = {
      ...originalSlide,
      id: uuidv4(),
      title: `${originalSlide.title} (Copy)`,
      elements: originalSlide.elements.map(el => ({ ...el, id: uuidv4() })),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      hasUnsavedChanges: true,
    };

    setSlides(currentSlides => {
      const updatedSlides = [...currentSlides];
      updatedSlides.splice(slideIndex + 1, 0, duplicatedSlide);

      return updatedSlides.map((slide, index) => ({
        ...slide,
        order: index + 1,
      }));
    });

    setCurrentSlideId(duplicatedSlide.id);
    return duplicatedSlide.id;
  }, [slides]);

  // Reorder slides
  const reorderSlides = useCallback((fromIndex, toIndex) => {
    setSlides(currentSlides => {
      const reorderedSlides = [...currentSlides];
      const [movedSlide] = reorderedSlides.splice(fromIndex, 1);
      reorderedSlides.splice(toIndex, 0, movedSlide);

      // Update order numbers
      return reorderedSlides.map((slide, index) => ({
        ...slide,
        order: index + 1,
        updated_at: new Date().toISOString(),
      }));
    });

    // Update presentation metadata
    setPresentationMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));
  }, []);

  // Update slide properties
  const updateSlide = useCallback((slideId, updates) => {
    // If collaborative, write to Yjs (EXCEPT if it's a legacy recursive call loop)
    // We handle ELEMENTS separately in updateElement/addElement/deleteElement to be granular.
    // So if 'updates' contains 'elements', we assume it's a full replace (Layout/Undo) or legacy call.
    const isCollabConnected = collaboration?.doc && collaboration?.status === 'connected';
    if (isCollabConnected && !isRemoteUpdate.current) {
      const { ySlide } = getYSlide(slideId);
      if (ySlide) {
        collaboration.doc.transact(() => {
          Object.keys(updates).forEach(key => {
            if (key === 'elements') {
              // Full elements replace (Careful!)
              const yElements = ySlide.get('elements');
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
              ySlide.set(key, updates[key]);
            }
          });
          ySlide.set('updated_at', new Date().toISOString());
          ySlide.set('hasUnsavedChanges', true);
        });
      }
      return;
    }

    setSlides(currentSlides =>
      currentSlides.map(slide =>
        slide.id === slideId
          ? {
            ...slide,
            ...updates,
            updated_at: new Date().toISOString(),
            hasUnsavedChanges: true,
          }
          : slide
      )
    );

    setPresentationMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));
  }, [getYSlide, collaboration]);

  // Update slide title
  const updateSlideTitle = useCallback((slideId, title) => {
    updateSlide(slideId, { title: title.trim() || 'Untitled Slide' });
  }, [updateSlide]);

  // Update slide notes
  const updateSlideNotes = useCallback((slideId, notes) => {
    updateSlide(slideId, { notes });
  }, [updateSlide]);

  // Toggle slide hidden state
  const toggleSlideHidden = useCallback((slideId) => {
    setSlides(prev => prev.map(s => s.id === slideId ? { ...s, hidden: !s.hidden } : s));
  }, []);

  // Update slide background
  const updateSlideBackground = useCallback((slideId, { backgroundColor, backgroundImage, backgroundOpacity, removeBackgroundImage }) => {
    const updates = {};
    if (backgroundColor !== undefined) updates.backgroundColor = backgroundColor;
    if (backgroundImage !== undefined) updates.backgroundImage = backgroundImage;

    // Update opacity on background image element(s)
    if (backgroundOpacity !== undefined) {
      const slide = slides.find(s => s.id === slideId);
      if (slide) {
        updates.elements = slide.elements.map(el =>
          el.imageType === 'background' ? { ...el, opacity: backgroundOpacity } : el
        );
      }
    }

    // Remove background image element(s)
    if (removeBackgroundImage) {
      const slide = slides.find(s => s.id === slideId);
      if (slide) {
        updates.elements = (updates.elements || slide.elements).filter(el => el.imageType !== 'background');
        updates.backgroundImage = null;
      }
    }

    updateSlide(slideId, updates);
  }, [updateSlide, slides]);

  // Update slide layout
  const updateSlideLayout = useCallback((slideId, layout) => {
    const slide = slides.find(s => s.id === slideId);
    if (!slide) return;

    // Preserve existing text content when changing layout
    const existingTitle = slide.elements.find(el => el.textType === 'title')?.content || '';
    const existingSubtitle = slide.elements.find(el => el.textType === 'subtitle')?.content || '';
    const existingBody = slide.elements.find(el => el.textType === 'body')?.content || '';

    const newElements = createLayoutElements(layout, existingTitle, existingSubtitle, existingBody);
    updateSlide(slideId, { layout, elements: newElements });
  }, [slides, updateSlide]);

  // Add element to slide
  const addElement = useCallback((slideId, elementType, options = {}) => {
    const slide = slides.find(s => s.id === slideId);
    if (!slide) return null;

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
        // The original code was only passing options.position, but PresentationCanvas passes flat options
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
      const { ySlide } = getYSlide(slideId);
      if (ySlide) {
        const yElements = ySlide.get('elements');
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

    updateSlide(slideId, { elements: [...slide.elements, newElement] });
    setSelectedElementId(newElement.id);
    return newElement.id;
  }, [slides, updateSlide, getYSlide, collaboration]);

  // Update element on slide
  const updateElement = useCallback((slideId, elementId, updates) => {
    const isCollabConnected = collaboration?.doc && collaboration?.status === 'connected';
    console.log(`🔄 [UPDATE_ELEMENT] Called for slideId: ${slideId}, elementId: ${elementId}, hasCollab: ${!!collaboration?.doc}, isConnected: ${isCollabConnected}`);
    
    // Collaborative Granular Update - only use Y.js path if actually connected
    if (isCollabConnected && !isRemoteUpdate.current) {
      if (elementId === null && updates.elements !== undefined) {
        // Full replace logic handled by updateSlide
        updateSlide(slideId, { elements: updates.elements });
        return;
      }

      const { ySlide } = getYSlide(slideId);
      console.log(`🔄 [UPDATE_ELEMENT] Y.js path: ySlide found: ${!!ySlide}`);
      
      if (ySlide) {
        const yElements = ySlide.get('elements'); // Y.Array
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
            // FIX: Also update local React state immediately to ensure persistence
            // Don't rely solely on Y.js observer - it may have timing issues
            // The observer will still fire and keep things in sync for collaboration
          } else {
            console.warn('[YJS] Element not found or not Y.Map:', elementId, '- falling back to local update');
            // Fall through to local state update below
          }
        }
      }
      // ALWAYS update local state as well (removed early return)
    }

    // Special case: if elementId is null and updates.elements is provided,
    // this is a full slide restoration (used by Undo/Redo)
    if (elementId === null && updates.elements !== undefined) {
      console.log('🔄 [UPDATE_ELEMENT] Full elements replacement for Undo/Redo');
      updateSlide(slideId, { elements: updates.elements });
      return;
    }

    // Use functional update to avoid stale closure issues when multiple updates happen quickly
    console.log(`📝 [UPDATE_ELEMENT] Local update for ${elementId}, updates:`, JSON.stringify(updates));
    
    // Set flag to prevent Y.js observer from overwriting our changes
    isLocalUpdate.current = true;
    
    setSlides(currentSlides => {
      const slideToUpdate = currentSlides.find(s => s.id === slideId);
      console.log(`📝 [UPDATE_ELEMENT] Found slide: ${!!slideToUpdate}, elements count: ${slideToUpdate?.elements?.length}`);
      
      return currentSlides.map(slide => {
        if (slide.id !== slideId) return slide;
        
        const elementExists = slide.elements.some(el => el.id === elementId);
        if (!elementExists) {
          console.warn(`[UPDATE_ELEMENT] Element ${elementId} not found in slide ${slideId}`);
          return slide;
        }
        
        const updatedElements = slide.elements.map(el =>
          el.id === elementId ? { ...el, ...updates } : el
        );
        
        const updatedSlide = {
          ...slide,
          elements: updatedElements,
          updated_at: new Date().toISOString(),
          hasUnsavedChanges: true,
        };
        
        console.log(`📝 [UPDATE_ELEMENT] Updated element ${elementId} in slide ${slideId}. New content preview:`, 
          updatedElements.find(e => e.id === elementId)?.content?.substring(0, 50));
        
        return updatedSlide;
      });
    });
    
    // Clear flag after a delay to allow Y.js to sync, then allow observer updates again
    setTimeout(() => {
      isLocalUpdate.current = false;
    }, 100);
    
    setPresentationMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));
  }, [getYSlide, collaboration]);

  // Update multiple elements in a slide atomically (batch update for AI multi-select edits)
  const updateMultipleElements = useCallback((slideId, elementUpdates) => {
    // elementUpdates is an array of { elementId, updates } objects
    if (!elementUpdates || elementUpdates.length === 0) {
      console.log('[UPDATE_MULTIPLE_ELEMENTS] No updates provided');
      return;
    }

    console.log(`🔄 [UPDATE_MULTIPLE_ELEMENTS] Batch updating ${elementUpdates.length} elements in slide ${slideId}`);

    // Y.js collaborative batch update - only use Y.js path if actually connected
    const isCollabConnected = collaboration?.doc && collaboration?.status === 'connected';
    if (isCollabConnected && !isRemoteUpdate.current) {
      const { ySlide } = getYSlide(slideId);
      if (ySlide) {
        const yElements = ySlide.get('elements');
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
    setSlides(currentSlides => {
      return currentSlides.map(slide => {
        if (slide.id !== slideId) return slide;

        const updatedElements = slide.elements.map(el => {
          const updateItem = elementUpdates.find(u => u.elementId === el.id);
          if (updateItem) {
            return { ...el, ...updateItem.updates };
          }
          return el;
        });

        const updatedCount = elementUpdates.filter(u => 
          slide.elements.some(el => el.id === u.elementId)
        ).length;
        console.log(`📝 [UPDATE_MULTIPLE_ELEMENTS] Updated ${updatedCount}/${elementUpdates.length} elements`);

        return {
          ...slide,
          elements: updatedElements,
          updated_at: new Date().toISOString(),
          hasUnsavedChanges: true,
        };
      });
    });

    setPresentationMetadata(prev => ({
      ...prev,
      updated_at: new Date().toISOString(),
    }));
  }, [getYSlide, collaboration]);

  // Delete element from slide
  const deleteElement = useCallback((slideId, elementId) => {
    // Collaborative Granular Delete - only use Y.js path if actually connected
    const isCollabConnected = collaboration?.doc && collaboration?.status === 'connected';
    if (isCollabConnected && !isRemoteUpdate.current) {
      const { ySlide } = getYSlide(slideId);
      if (ySlide) {
        const yElements = ySlide.get('elements');
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

    const slide = slides.find(s => s.id === slideId);
    if (!slide) return;

    const filteredElements = slide.elements.filter(el => el.id !== elementId);
    updateSlide(slideId, { elements: filteredElements });

    if (selectedElementId === elementId) {
      setSelectedElementId(null);
    }
  }, [slides, updateSlide, selectedElementId, getYSlide, collaboration]);

  // Delete multiple elements from slide (atomic batch delete)
  const deleteMultipleElements = useCallback((slideId, elementIds) => {
    const slide = slides.find(s => s.id === slideId);
    if (!slide || !elementIds || elementIds.length === 0) return;

    const idsToDelete = new Set(elementIds);
    const filteredElements = slide.elements.filter(el => !idsToDelete.has(el.id));
    updateSlide(slideId, { elements: filteredElements });

    // Clear selection if any selected element was deleted
    if (selectedElementId && idsToDelete.has(selectedElementId)) {
      setSelectedElementId(null);
    }
  }, [slides, updateSlide, selectedElementId]);

  // Reorder elements (bring to front/back)
  const reorderElement = useCallback((slideId, elementId, direction) => {
    const slide = slides.find(s => s.id === slideId);
    if (!slide) return;

    const elementIndex = slide.elements.findIndex(el => el.id === elementId);
    if (elementIndex === -1) return;

    const elements = [...slide.elements];
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

    updateSlide(slideId, { elements });
  }, [slides, updateSlide]);

  // Update presentation metadata
  const updatePresentationMetadata = useCallback((updates) => {
    setPresentationMetadata(prev => ({
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

  // Apply style theme to all slides
  const applyStyleToAllSlides = useCallback((style) => {
    setPresentationMetadata(prev => ({
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
    const surface = normalizedStyle.surface || normalizedStyle.slideBackground || '#ffffff';
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

    // Apply style to each slide's elements
    setSlides(currentSlides =>
      currentSlides.map(slide => {
        let slideChanged = false;

        // Update background if needed
        const newBackgroundColor = normalizedStyle.slideBackground || slide.backgroundColor;
        if (newBackgroundColor !== slide.backgroundColor) {
          slideChanged = true;
        }

        // Identify potential background containers (Shapes, Cards) sorted by Z-index (highest first logic?)
        // We want the *top-most* container that is *below* the text.
        const containers = slide.elements.filter(el =>
          el.type === ELEMENT_TYPES.SHAPE ||
          el.type === 'card'
        ).sort((a, b) => (b.zIndex || 0) - (a.zIndex || 0));

        const newElements = slide.elements.map(el => {
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
            slideChanged = true;
            return newEl;
          }
          return el; // Return original reference if no change
        });

        if (slideChanged) {
          return {
            ...slide,
            backgroundColor: newBackgroundColor,
            elements: newElements,
            updated_at: new Date().toISOString(),
            hasUnsavedChanges: true,
          };
        }
        return slide; // Return original reference if no change
      })
    );
  }, []);

  // Mark slide as saved
  const markSlideAsSaved = useCallback((slideId) => {
    setSlides(currentSlides =>
      currentSlides.map(slide =>
        slide.id === slideId
          ? { ...slide, hasUnsavedChanges: false }
          : slide
      )
    );
  }, []);

  // Mark all slides as saved
  const markAllSlidesSaved = useCallback(() => {
    setSlides(currentSlides =>
      currentSlides.map(slide => ({
        ...slide,
        hasUnsavedChanges: false,
      }))
    );
  }, []);

  // Get slide by ID
  const getSlideById = useCallback((slideId) => {
    return slides.find(slide => slide.id === slideId);
  }, [slides]);

  // Get current slide
  const getCurrentSlide = useCallback(() => {
    return slides.find(slide => slide.id === currentSlideId);
  }, [slides, currentSlideId]);

  // Get selected element
  const getSelectedElement = useCallback(() => {
    const slide = getCurrentSlide();
    if (!slide || !selectedElementId) return null;
    return slide.elements.find(el => el.id === selectedElementId);
  }, [getCurrentSlide, selectedElementId]);

  // Get slides summary for AI context
  const getSlidesSummary = useCallback(() => {
    return slides.map(slide => ({
      id: slide.id,
      title: slide.title,
      layout: slide.layout,
      order: slide.order,
      elementCount: slide.elements.length,
      textContent: slide.elements
        .filter(el => el.type === ELEMENT_TYPES.TEXT)
        .map(el => el.content)
        .join(' ')
        .substring(0, 200),
    }));
  }, [slides]);

  // Keep the current-slide pointer VALID and POSITIONALLY STABLE.
  //
  // While the active slide still exists, remember its index. If it ever
  // disappears — deleted here, removed by the AI agent's operations, or by a
  // collaborator — snap to the slide now occupying the CLOSEST position
  // (clamped to the new length), never blindly to slide 0. Resetting to the
  // first slide on every structural change was the "list view jumps to another
  // slide number" bug.
  useEffect(() => {
    const idx = slides.findIndex(s => s.id === currentSlideId);
    if (idx >= 0) {
      lastValidIndexRef.current = idx;
      return;
    }
    if (slides.length === 0) {
      if (currentSlideId !== null) setCurrentSlideId(null);
      return;
    }
    const target = slides[Math.min(lastValidIndexRef.current, slides.length - 1)];
    if (target && target.id !== currentSlideId) {
      setCurrentSlideId(target.id);
    }
  }, [slides, currentSlideId]);

  // Clear element selection when changing slides
  useEffect(() => {
    setSelectedElementId(null);
  }, [currentSlideId]);

  return {
    // State
    slides,
    setSlides, // Direct setter for bulk updates
    currentSlideId,
    selectedElementId,
    presentationMetadata,

    // Slide management
    addSlide,
    deleteSlide,
    insertSlide,
    duplicateSlide,
    reorderSlides,
    updateSlide,
    updateSlideTitle,
    updateSlideNotes,
    updateSlideBackground,
    updateSlideLayout,

    // Element management
    addElement,
    updateElement,
    updateMultipleElements,
    deleteElement,
    deleteMultipleElements,
    reorderElement,
    setSelectedElementId,

    // Style management
    applyStyleToAllSlides,
    updatePresentationMetadata,

    // Navigation
    setCurrentSlideId,

    // Visibility
    toggleSlideHidden,

    // Utilities
    getSlideById,
    getCurrentSlide,
    getSelectedElement,
    getSlidesSummary,
    markSlideAsSaved,
    markAllSlidesSaved,

    // Computed values
    hasUnsavedChanges: slides.some(slide => slide.hasUnsavedChanges),
    totalSlides: slides.length,

    // Constants
    SLIDE_LAYOUTS,
    ELEMENT_TYPES,
    SLIDE_WIDTH,
    SLIDE_HEIGHT,
  };
};

export default usePresentationSlides;
