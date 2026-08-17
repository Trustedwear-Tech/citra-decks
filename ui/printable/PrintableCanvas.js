// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

// printableCanvas.js - Canvas editor component for PAGE editing using Fabric.js
import React, { useRef, useEffect, useState, useCallback, forwardRef, useImperativeHandle } from 'react';
import globalImageCache from '../../utils/globalImageCache';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  Platform,
  TextInput,
  useWindowDimensions,
} from 'react-native';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';
import { Chart, registerables } from 'chart.js';

// Register Chart.js components
Chart.register(...registerables);

// Constants for page dimensions (A4 portrait at 96 DPI: 794x1123 pixels)
export const PAGE_WIDTH = 794;
export const PAGE_HEIGHT = 1123;
const CANVAS_PADDING = 0;

// Global fabric reference (loaded from CDN)
let fabricModule = null;

// Suppress known Fabric.js warnings
// Suppress known Fabric.js warnings (both warn and error levels)
const originalWarn = console.warn;
const originalError = console.error;

const shouldSuppress = (args) => {
  const msg = args[0];
  if (typeof msg === 'string' && (
    (msg.includes('alphabetical') && msg.includes('CanvasTextBaseline')) ||
    (msg.includes('not a valid enum value') && msg.includes('CanvasTextBaseline')) ||
    (msg.includes('PAGE_TEMPLATES') && msg.includes('is not defined')) // Suppress previous error logs if any flush out
  )) {
    return true;
  }
  return false;
};

console.warn = (...args) => {
  if (shouldSuppress(args)) return;
  originalWarn.apply(console, args);
};

console.error = (...args) => {
  if (shouldSuppress(args)) return;
  originalError.apply(console, args);
};

// Load Fabric.js from CDN for web
const loadFabricFromCDN = () => {
  return new Promise((resolve, reject) => {
    if (Platform.OS !== 'web') {
      reject(new Error('Fabric.js is only available on web'));
      return;
    }

    // Check if already loaded
    if (window.fabric) {
      fabricModule = window.fabric;
      console.log('✅ Fabric.js already loaded');
      resolve(window.fabric);
      return;
    }

    // Check if script is already loading
    const existingScript = document.querySelector('script[src*="fabric"]');
    if (existingScript) {
      existingScript.addEventListener('load', () => {
        fabricModule = window.fabric;
        resolve(window.fabric);
      });
      return;
    }

    // Load from CDN
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/fabric.js/5.3.1/fabric.min.js';
    script.async = true;
    script.onload = async () => {
      console.log('✅ Fabric.js loaded from CDN');
      fabricModule = window.fabric;

      // HACK: Filter out the annoying Fabric.js "alphabetical" warning
      const originalWarn = console.warn;
      console.warn = (...args) => {
        if (args[0] && typeof args[0] === 'string' && args[0].includes("'alphabetical' is not a valid enum value of type CanvasTextBaseline")) {
          return;
        }
        originalWarn(...args);
      };

      // PATCH: Fix 'alphabetical' textBaseline warning in Fabric.js 5.3.1
      // Browser standards use 'alphabetic', but Fabric sometimes uses 'alphabetical'
      // We must patch ALL text-related classes and the global Object prototype
      if (fabricModule.Text) fabricModule.Text.prototype.textBaseline = 'alphabetic';
      if (fabricModule.IText) fabricModule.IText.prototype.textBaseline = 'alphabetic';
      if (fabricModule.Textbox) fabricModule.Textbox.prototype.textBaseline = 'alphabetic';
      if (fabricModule.Object) fabricModule.Object.prototype.textBaseline = 'alphabetic';

      // Force global default if it exists
      if (fabricModule.config) {
        fabricModule.config.textBaseline = 'alphabetic';
      }

      // CRITICAL: Patch the Canvas 2D context to fix invalid 'alphabetical' values
      // This intercepts the actual canvas context setter to correct the typo
      try {
        const originalTextBaselineDescriptor = Object.getOwnPropertyDescriptor(
          CanvasRenderingContext2D.prototype, 'textBaseline'
        );
        if (originalTextBaselineDescriptor && originalTextBaselineDescriptor.set) {
          Object.defineProperty(CanvasRenderingContext2D.prototype, 'textBaseline', {
            set: function (value) {
              // Fix the typo: 'alphabetical' -> 'alphabetic'
              const correctedValue = value === 'alphabetical' ? 'alphabetic' : value;
              originalTextBaselineDescriptor.set.call(this, correctedValue);
            },
            get: originalTextBaselineDescriptor.get,
            configurable: true,
            enumerable: true
          });
          console.log('✅ Canvas textBaseline setter patched to fix alphabetical typo');
        }
      } catch (patchError) {
        console.warn('Could not patch textBaseline setter:', patchError);
      }

      console.log('✅ Fabric.js patched: textBaseline forced to alphabetic');

      // Selection controls: make grab handles and border fully opaque and visible
      fabricModule.Object.prototype.set({
        borderColor: '#2563EB',           // Blue-600 border around selected object
        cornerColor: '#2563EB',           // Blue-600 filled corner handles
        cornerStrokeColor: '#1E40AF',     // Blue-800 corner handle border
        cornerSize: 10,                   // Slightly larger grab handles
        cornerStyle: 'circle',            // Round handles
        transparentCorners: false,        // Filled (opaque) corners, not hollow
        borderScaleFactor: 2,             // Thicker selection border
        selectionBackgroundColor: 'rgba(37, 99, 235, 0.06)', // Very subtle blue fill
      });

      // Create custom fabric.Chart class for interactive charts
      // This replaces the incompatible chart-js-fabric npm package
      try {
        const fabric = fabricModule;

        // Define Chart class that extends fabric.Rect
        fabric.Chart = fabric.util.createClass(fabric.Rect, {
          type: 'chart',

          initialize: function (options) {
            options = options || {};
            this.callSuper('initialize', options);
            this.set('fill', 'transparent');
            this.set('stroke', null);
            this.set('objectCaching', false); // Disable caching to force redraw every frame
            this._chartConfig = options.chart || null;
            this._chartInstance = null;
            this._chartCanvas = null;

            // Create internal canvas for Chart.js
            if (this._chartConfig && typeof document !== 'undefined') {
              this._createChartCanvas();
            }
          },

          setChartConfig: function (newConfig) {
            console.log('📊 [FABRIC.CHART] setChartConfig called for update - FORCING RECREATION');
            this._chartConfig = newConfig || {};

            // Always destroy and recreate to ensure clean state and avoid Chart.js diffing issues
            if (this._chartInstance) {
              this._chartInstance.destroy();
              this._chartInstance = null;
            }
            if (typeof document !== 'undefined') {
              this._createChartCanvas();
            }
            this.dirty = true;
            this.set('dirty', true);
            if (this.canvas) {
              this.canvas.renderAll(); // Force synchronous render
              // Safety catch for any async Chart.js painting
              setTimeout(() => {
                this.dirty = true;
                if (this.canvas) this.canvas.renderAll();
              }, 50);
            }
          },

          _createChartCanvas: function () {
            const { Chart: ChartJS, registerables } = require('chart.js');
            ChartJS.register(...registerables);

            // Create offscreen canvas
            this._chartCanvas = document.createElement('canvas');
            this._chartCanvas.width = this.width || 400;
            this._chartCanvas.height = this.height || 300;

            // Deep clone data to prevent Chart.js from mutating the stored config
            // Chart.js adds internal _meta and tracking properties to dataset objects
            const chartData = JSON.parse(JSON.stringify(this._chartConfig.data || { labels: [], datasets: [] }));

            // Create Chart.js instance
            this._chartInstance = new ChartJS(this._chartCanvas, {
              type: this._chartConfig.type || 'bar',
              data: chartData,
              options: {
                ...this._chartConfig.options,
                responsive: false,
                maintainAspectRatio: false,
                animation: false,
              }
            });
          },

          _render: function (ctx) {
            // Call parent render for the rect outline
            this.callSuper('_render', ctx);

            // Draw the chart canvas onto the fabric canvas
            if (this._chartCanvas && this._chartInstance) {
              // Draw chart canvas
              const w = this.width;
              const h = this.height;
              ctx.drawImage(this._chartCanvas, -w / 2, -h / 2, w, h);
            }
          },

          // Update chart data — FULL REPLACEMENT (not spread merge)
          // Prevents stale data from persisting when Chart.js does partial diff updates
          set: function (key, value) {
            if (key === 'chart' && value) {
              // Full replacement instead of spread merge to prevent partial data issues
              this._chartConfig = value;
              if (this._chartInstance) {
                // Always destroy and recreate for guaranteed clean state
                this._chartInstance.destroy();
                this._chartInstance = null;
                if (typeof document !== 'undefined') {
                  this._createChartCanvas();
                }
              }
            }
            return this.callSuper('set', key, value);
          },

          // Clean up on removal
          dispose: function () {
            if (this._chartInstance) {
              this._chartInstance.destroy();
              this._chartInstance = null;
            }
            this._chartCanvas = null;
          },

          toObject: function (propertiesToInclude) {
            return fabric.util.object.extend(this.callSuper('toObject', propertiesToInclude), {
              chart: this._chartConfig
            });
          }
        });

        // Register fromObject for deserialization
        fabric.Chart.fromObject = function (object, callback) {
          return fabric.Object._fromObject('Chart', object, callback);
        };

        console.log('✅ Custom fabric.Chart class created');
      } catch (chartClassError) {
        console.warn('⚠️ Failed to create fabric.Chart class:', chartClassError);
      }

      // Create custom fabric.Table class for editable tables
      try {
        const fabric = fabricModule;

        fabric.Table = fabric.util.createClass(fabric.Group, {
          type: 'table',

          initialize: function (objects, options) {
            options = options || {};
            this._tableConfig = {
              rows: options.rows || 3,
              cols: options.cols || 3,
              cellWidth: options.cellWidth || 100,
              cellHeight: options.cellHeight || 30,
              hasHeader: options.hasHeader !== false,
              headerColor: options.headerColor || '#3B82F6',
              headerTextColor: options.headerTextColor || '#FFFFFF',
              cellColor: options.cellColor || '#FFFFFF',
              altRowColor: options.altRowColor || '#F8FAFC',
              borderColor: options.borderColor || '#E5E7EB',
              textColor: options.textColor || '#374151',
              cellData: options.cellData || null,
            };

            // If no objects passed, create them
            if (!objects || objects.length === 0) {
              objects = this._createTableObjects();
            }

            this.callSuper('initialize', objects, options);
            this.set('objectCaching', false);
          },

          _createEmptyCellData: function () {
            const cfg = this._tableConfig;
            const data = [];
            for (let r = 0; r < cfg.rows; r++) {
              const row = [];
              for (let c = 0; c < cfg.cols; c++) {
                row.push(r === 0 && cfg.hasHeader ? `Header ${c + 1}` : '');
              }
              data.push(row);
            }
            return data;
          },

          _createTableObjects: function () {
            const cfg = this._tableConfig;
            const objects = [];

            // Initialize cell data if not provided
            if (!cfg.cellData) {
              cfg.cellData = this._createEmptyCellData();
            }

            for (let r = 0; r < cfg.rows; r++) {
              for (let c = 0; c < cfg.cols; c++) {
                const x = c * cfg.cellWidth;
                const y = r * cfg.cellHeight;

                // Determine cell background
                let bgColor = cfg.cellColor;
                if (r === 0 && cfg.hasHeader) {
                  bgColor = cfg.headerColor;
                } else if (r % 2 === 0) {
                  bgColor = cfg.altRowColor;
                }

                // Cell rectangle
                const cell = new fabric.Rect({
                  left: x,
                  top: y,
                  width: cfg.cellWidth,
                  height: cfg.cellHeight,
                  fill: bgColor,
                  stroke: cfg.borderColor,
                  strokeWidth: 1,
                  selectable: false,
                  evented: false,
                  cellRow: r,
                  cellCol: c,
                });
                objects.push(cell);

                // Cell text
                const textColor = (r === 0 && cfg.hasHeader) ? cfg.headerTextColor : cfg.textColor;
                const cellText = cfg.cellData[r] ? (cfg.cellData[r][c] || '') : '';
                const text = new fabric.Textbox(cellText, {
                  left: x + 6,
                  top: y + 6,
                  width: cfg.cellWidth - 12,
                  fontSize: 12,
                  fill: textColor,
                  fontWeight: (r === 0 && cfg.hasHeader) ? 'bold' : 'normal',
                  fontFamily: 'Inter, system-ui, sans-serif',
                  selectable: false,
                  evented: false,
                  cellRow: r,
                  cellCol: c,
                  splitByGrapheme: true,
                });
                objects.push(text);
              }
            }

            return objects;
          },

          // Get table config for serialization
          getTableConfig: function () {
            // Collect current cell data from textboxes
            const cfg = this._tableConfig;
            const cellData = [];
            for (let r = 0; r < cfg.rows; r++) {
              cellData.push([]);
              for (let c = 0; c < cfg.cols; c++) {
                cellData[r].push('');
              }
            }

            this.forEachObject(obj => {
              if (obj.type === 'textbox' && obj.cellRow !== undefined && obj.cellCol !== undefined) {
                cellData[obj.cellRow][obj.cellCol] = obj.text || '';
              }
            });

            return {
              ...cfg,
              cellData: cellData,
            };
          },

          // Update cell text
          setCellText: function (row, col, value) {
            this.forEachObject(obj => {
              if (obj.type === 'textbox' && obj.cellRow === row && obj.cellCol === col) {
                obj.set('text', value);
              }
            });
            this._tableConfig.cellData[row][col] = value;
            this.dirty = true;
          },

          toObject: function (propertiesToInclude) {
            return fabric.util.object.extend(this.callSuper('toObject', propertiesToInclude), {
              tableConfig: this.getTableConfig(),
            });
          },
        });

        // Register fromObject for deserialization
        fabric.Table.fromObject = function (object, callback) {
          const tableConfig = object.tableConfig || {};
          const table = new fabric.Table([], {
            ...tableConfig,
            left: object.left,
            top: object.top,
            scaleX: object.scaleX,
            scaleY: object.scaleY,
          });
          callback && callback(table);
          return table;
        };

        console.log('✅ Custom fabric.Table class created');
      } catch (tableClassError) {
        console.warn('⚠️ Failed to create fabric.Table class:', tableClassError);
      }

      resolve(window.fabric);
    };
    script.onerror = (err) => {
      console.error('❌ Failed to load Fabric.js from CDN:', err);
      reject(err);
    };
    document.head.appendChild(script);
  });
};

// Import icon mapper for AI-generated icons
import { mapIconToPath, getIconSVG, mapIconToPathAsync, cacheIconSVG, ICON_PATHS } from '../composer/utils/iconMapper';

// Import enhanced color picker
import ColorPickerDropdown from '../composer/ColorPickerDropdown';

import IconPickerModal from '../composer/IconPickerModal';
import ShapesPickerModal from '../composer/ShapesPickerModal';
import FontCombinationPickerModal from '../composer/FontCombinationPickerModal';
import TablePickerModal from '../composer/TablePickerModal';
import VideoSourceModal from '../composer/VideoSourceModal';
import EmbedSourceModal from '../composer/EmbedSourceModal';
import FormsButtonModal from '../composer/FormsButtonModal';
import InlineVideoOverlay from '../composer/InlineVideoOverlay';
import FloatingTextToolbar from '../composer/FloatingTextToolbar';

import { ShareButton } from '../ShareManager';
import { FabricYjsBinder } from '../composer/utils/FabricYjsBinder';
import { preprocessSvgForFabric } from '../composer/utils/svgFabricPrep';
import Tooltip from '../ui/Tooltip';

// Element type constants
const ELEMENT_TYPES = {
  TEXT: 'text',
  IMAGE: 'image',
  VIDEO: 'video',
  SHAPE: 'shape',
  ICON: 'icon',
  CHART: 'chart',
  TABLE: 'table',
  EMBED: 'embed', // iframe-based embeds (Figma, Miro, etc.)
  BUTTON: 'button', // Clickable CTA button
  IMAGE_PLACEHOLDER: 'image_placeholder',
  ANIMATION: 'animation', // Video frames played as animated image loop
  SVG_DIAGRAM: 'svg_diagram', // Full-slot inline SVG diagram (org charts, process flows, infographics)
};

// A "card" in legacy / free-form documents is rarely a `card` element — the
// generator builds card-looking panels out of plain filled `shape`
// rectangles. isCardLikeShape detects those: a rectangle-ish shape with a
// real fill, large enough to be a panel (>=40x40) but not a near-full-bleed
// background. Such shapes render translucent (50%) so they read as a card
// layer over the page background.
const _CARD_LIKE_SHAPE_TYPES = new Set([
  'rectangle', 'rect', 'rectangle_rounded', 'rounded', 'round_rect', 'square',
]);
const isCardLikeShape = (el, canvasW, canvasH) => {
  if (!el || el.type !== ELEMENT_TYPES.SHAPE) return false;
  const st = String(el.shapeType || el.shape || 'rectangle').toLowerCase();
  if (!_CARD_LIKE_SHAPE_TYPES.has(st)) return false;
  const fill = el.fill;
  if (!fill || fill === 'transparent' || fill === 'none') return false;
  const w = el.width || 0, h = el.height || 0;
  if (w < 40 || h < 40) return false;                       // divider / accent bar
  if (w * h > 0.85 * canvasW * canvasH) return false;        // near-full-bleed background
  return true;
};

/**
 * PrintableCanvas - A canvas editor for creating and editing printable PAGES
 * Uses Fabric.js for web platform with fallback for native
 */
const PrintableCanvas = forwardRef(({
  theme,
  PAGE,
  isActivePage = false,
  // Set by the composer for the duration of ONE AI agent turn. External changes
  // sharing the same session id are COALESCED into a single history entry, so
  // Ctrl+Z undoes the whole agent turn atomically (PowerPoint-style) instead of
  // one step per streamed operations batch.
  externalEditSessionId = null,
  selectedElementId,
  onSelectElement,
  onUpdateElement,
  onUpdatePAGEBackground, // New prop for updating PAGE background color
  onDeleteElement,
  onDeleteMultipleElements,
  onAddElement,
  onGenerateImage, // Add prop for AI Image generation

  printableStyle,
  isEditable = true,
  scale = 1,
  onOpenStylePicker,


  onOpenChartHelp,
  onOpenDiagram,
  onCanvasFocus,
  onEditChart, // New prop for editing chart on double-click
  onEditDiagram, // Prop for regenerating an svg_diagram element on double-click
  onPlayVideo, // New prop for playing video on double-click
  // New Props for Header Integration
  printableTitle = 'Untitled printable',
  printableId, // New prop for sharing
  onUpdateTitle,
  onSave,
  onExport,
  onPresent,
  onClose,
  isGenerating = false,
  generationProgress,
  onRenderComplete, // Callback when canvas finishes rendering
  onShowAnalytics, // Callback to show analytics modal
  onShowCollaboration, // Callback to show collaboration panel
  collaborationStatus, // Collaboration connection status
  collaborators = [], // List of collaborators

  // Branding upsell props
  userType = 'free', // User plan type for export branding
  onUpgrade, // Callback to open credits/upgrade modal

  // Clipboard & Format Painter Props
  onCopyElements, // Function to copy selected elements
  onPasteElements, // Function to paste clipboard data (receives clipboardText)
  formatPainterActive = false, // Whether format painter is active
  formatPainterData = null, // Format data to apply
  onFormatPainterApply, // Callback when format is applied
  onDeactivateFormatPainter, // Callback to deactivate format painter
  onActivateFormatPainter, // Callback to activate format painter (copies format from selected element)
  awareness = null, // Collaboration Awareness
  hideToolbar = false, // Hide toolbar when mobile AI chat mode is active
  onElementSelectionChange, // Callback with toolbar state when selection changes (for shared toolbar)
  generationQuality, // Current image generation quality tier
  qualityLabel, // Display label for quality tier
  qualityColor, // Color for quality badge
  onShowQualityModal, // Callback to show quality change modal
}, ref) => {
  const canvasRef = useRef(null);
  const fabricCanvasRef = useRef(null);
  const containerRef = useRef(null);
  const fileInputRef = useRef(null); // For image file picker
  const videoInputRef = useRef(null); // For video file picker
  const animationInputRef = useRef(null); // For animation video file picker
  const animationIntervalsRef = useRef(new Map()); // Track animation intervals by element ID
  const fabricBinderRef = useRef(null); // FabricYjsBinder instance

  const [isCanvasReady, setIsCanvasReady] = useState(false);
  const [canvasScale, setCanvasScale] = useState(scale);
  const [editingTextId, setEditingTextId] = useState(null);
  const [editingTextValue, setEditingTextValue] = useState('');
  const [isTextEditing, setIsTextEditing] = useState(false);

  const { width: screenWidth } = useWindowDimensions();
  const isMobile = screenWidth < 768;

  // Toolbar state
  const [showShapesPicker, setShowShapesPicker] = useState(false);
  const [fillColor, setFillColor] = useState('#3B82F6');
  const [strokeColor, setStrokeColor] = useState('#1E40AF');
  const [fontSize, setFontSize] = useState(printableStyle?.textStyles?.body?.fontSize || 16);
  const [lineHeight, setLineHeight] = useState(1.4);

  const [selectedObjectInfo, setSelectedObjectInfo] = useState(null); // { type, fill, stroke, fontSize }

  // Icon Picker State
  const [showIconPicker, setShowIconPicker] = useState(false);

  // Font Combination Picker State
  const [showFontComboPicker, setShowFontComboPicker] = useState(false);

  // Table Picker State
  const [showTablePicker, setShowTablePicker] = useState(false);

  // Video Source Modal State
  const [showVideoModal, setShowVideoModal] = useState(false);
  // Inline Video State (for overlays)
  const [inlineVideoData, setInlineVideoData] = useState(null);

  // Animation Video Modal State (for frame extraction)
  const [showAnimationModal, setShowAnimationModal] = useState(false);

  // Embed Source Modal State (Figma, Miro, Google Drive, etc.)
  const [showEmbedModal, setShowEmbedModal] = useState(false);

  // Forms & Button Modal State (Calendly, Typeform, Buttons, etc.)
  const [showFormsModal, setShowFormsModal] = useState(false);

  // Inline text formatting toolbar state
  const [inlineToolbar, setInlineToolbar] = useState({ visible: false, x: 0, y: 0, styles: {} });
  const inlineToolbarRef = useRef({ visible: false, x: 0, y: 0, styles: {} });

  // Refs for accessing latest state inside Fabric event handlers (closured)
  // MOVED UP: These need to be defined before useImperativeHandle
  const PAGERef = useRef(PAGE);
  const handlersRef = useRef({ onUpdateElement, onDeleteElement, saveToHistory: () => { }, capturePreEditSnapshot: () => { } });
  const imageCacheRef = useRef({}); // Cache for blob URLs: { [originalSrc]: blobUrl }
  const lastBgImageRef = useRef(null); // Track last loaded background image URL to skip redundant reloads
  const scaleRef = useRef(canvasScale); // Track scale for event handlers to avoid stale closure
  const nudgeTimerRef = useRef(null); // Debounce timer for arrow key nudge history saves

  // Format Painter refs for use in event handlers (avoids stale closures)
  const formatPainterActiveRef = useRef(formatPainterActive);
  const formatPainterDataRef = useRef(formatPainterData);
  const onFormatPainterApplyRef = useRef(onFormatPainterApply);
  const onElementSelectionChangeRef = useRef(onElementSelectionChange);

  // Undo/Redo history - PER-PAGE system using Map
  // Key: PAGEId, Value: { states: [], index: number, lastSaved: string }
  const PAGEHistoriesRef = useRef(new Map());
  const currentPAGEIdRef = useRef(null); // Track current PAGE for history operations
  const hasInitialSaveRef = useRef(false); // Track if initial state was saved for current PAGE
  const renderIdRef = useRef(0); // Track render cycle to prevent race conditions
  const isDisposedRef = useRef(false); // Track if canvas has been disposed to prevent post-disposal renders
  const historyDebounceMapRef = useRef(new Map()); // Debounce timers per PAGE
  const preEditSnapshotRef = useRef(null); // Snapshot taken BEFORE an edit starts
  const prevElementsMapRef = useRef(new Map()); // Track last-known elements per PAGE to avoid cross-PAGE pollution
  const lastExternalSessionRef = useRef(new Map()); // pageId -> agent-turn session id that last pushed history (coalescing)

  // Helper to get or create history for a PAGE
  const getPAGEHistory = useCallback((PAGEId) => {
    if (!PAGEId) return null;
    if (!PAGEHistoriesRef.current.has(PAGEId)) {
      PAGEHistoriesRef.current.set(PAGEId, { states: [], index: -1, lastSaved: null, undoRedoActive: false });
    } else {
      const existing = PAGEHistoriesRef.current.get(PAGEId);
      if (existing.undoRedoActive === undefined) {
        existing.undoRedoActive = false;
      }
    }
    return PAGEHistoriesRef.current.get(PAGEId);
  }, []);

  // Collect the latest PAGE snapshot (elements + background) directly from Fabric objects to avoid stale React state
  const collectCurrentPAGEState = useCallback((PAGEId) => {
    if (!PAGEId) return null;

    const canvas = fabricCanvasRef.current;
    const baseElements = PAGERef.current?.elements || [];
    const backgroundColor = PAGERef.current?.backgroundColor;

    if (!canvas) {
      return JSON.parse(JSON.stringify({ elements: baseElements, backgroundColor }));
    }

    const objs = canvas.getObjects();
    const scale = scaleRef.current || 1;

    const merged = baseElements.map((el) => {
      const obj = objs.find((o) => o.elementId === el.id);
      if (!obj) return el;

      const next = { ...el };
      if (obj.left !== undefined) next.x = obj.left / scale;
      if (obj.top !== undefined) next.y = obj.top / scale;

      // SKIP dimension capture for complex shapes (polygon, path, group) - they don't have
      // meaningful width/height properties and are handled correctly by object:modified
      const skipDimensions = ['polygon', 'path', 'group', 'ellipse', 'circle'].includes(obj.type);

      if (!skipDimensions && obj.width !== undefined && obj.scaleX !== undefined) {
        // For textbox, rect, image - capture dimensions
        if (obj.scaleX === 1 && obj.scaleY === 1) {
          // Scale was reset by object:modified - dimensions are in canvas space
          next.width = obj.width / scale;
          next.height = obj.height / scale;
        } else {
          // Mid-resize - dimensions include the scale factor
          next.width = (obj.width * obj.scaleX) / scale;
          next.height = (obj.height * obj.scaleY) / scale;
        }
      }

      if (obj.angle !== undefined) next.rotation = obj.angle;
      if ((obj.type === 'textbox' || obj.type === 'i-text') && obj.text !== undefined) next.content = obj.text;
      // Capture font properties for text elements ONLY if element already has them set
      // (meaning they were explicitly modified via font picker or other means)
      // This prevents capturing render defaults (from printable style) as explicit values
      if ((obj.type === 'textbox' || obj.type === 'i-text')) {
        // Only update fontFamily if element already has an explicit fontFamily set
        // The element gets fontFamily set by handleApplyFontCombination calling onUpdateElement
        if (el.fontFamily !== undefined) {
          next.fontFamily = obj.fontFamily;
        }
        if (el.fontWeight !== undefined) {
          next.fontWeight = obj.fontWeight;
        }
        if (el.fontStyle !== undefined) {
          next.fontStyle = obj.fontStyle;
        }
        // Capture fontSize from Fabric (divide by scale to get logical value)
        if (el.fontSize !== undefined) {
          next.fontSize = obj.fontSize / scale;
        }
        // Capture character-level styles for undo/redo persistence
        if (obj.styles && Object.keys(obj.styles).length > 0) {
          next.styles = JSON.parse(JSON.stringify(obj.styles));
        }
      }
      // Capture chart config from fabric.Chart objects to ensure persistence
      // Chart.js config lives on the fabric object as _chartConfig and must be synced back
      if (obj.type === 'chart' && obj._chartConfig) {
        next.chartConfig = JSON.parse(JSON.stringify(obj._chartConfig));
      }
      // Capture table config from fabric.Table objects
      if (obj.type === 'table' && obj._tableConfig) {
        next.tableConfig = JSON.parse(JSON.stringify(obj._tableConfig));
      }
      return next;
    });

    return JSON.parse(JSON.stringify({ elements: merged, backgroundColor }));
  }, []);

  // Helpers for per-PAGE undo/redo activity
  const isUndoRedoActiveFor = useCallback((PAGEId) => {
    if (!PAGEId) return false;
    const history = getPAGEHistory(PAGEId);
    return !!history?.undoRedoActive;
  }, [getPAGEHistory]);

  const setUndoRedoActiveFor = useCallback((PAGEId, active) => {
    const history = getPAGEHistory(PAGEId);
    if (history) {
      history.undoRedoActive = !!active;
    }
  }, [getPAGEHistory]);

  // NOTE: All imperative methods are exposed in a SINGLE useImperativeHandle below (search for "Expose methods via ref - UNIFIED")
  // Do NOT add a second useImperativeHandle here - it would override the unified one.

  // ==================== Collaboration: FabricYjsBinder ====================
  useEffect(() => {
    if (!fabricCanvasRef.current || !awareness) return;

    // Initialize Binder if not exists
    if (!fabricBinderRef.current) {
      fabricBinderRef.current = new FabricYjsBinder(
        fabricCanvasRef.current,
        awareness,
        { name: 'Me' } // Local user info passed or defaulted in binder
      );
    }

    const binder = fabricBinderRef.current;

    // Bind
    binder.setCurrentPAGEId(PAGE?.id);
    binder.bind();

    return () => {
      binder.unbind();
    };
  }, [awareness, PAGE?.id, isCanvasReady]); // Re-bind if PAGE changes

  // Sync toolbar state with selection
  useEffect(() => {
    if (selectedElementId && PAGE?.elements) {
      const element = PAGE.elements.find(e => e.id === selectedElementId);
      if (element) {
        if (element.fill) setFillColor(element.fill);
        if (element.stroke) setStrokeColor(element.stroke);
        if (element.fontSize) setFontSize(element.fontSize);
        if (element.lineHeight) setLineHeight(element.lineHeight);
        // We could sync bold/italic here too if we had state for them in toolbar UI
      }
    }
  }, [selectedElementId, PAGE?.elements]);

  // Track PAGE changes and initialize per-PAGE history
  // Also store per-PAGE previous elements to avoid cross-PAGE pollution
  useEffect(() => {
    if (!PAGE?.id) return;

    // Detect PAGE change
    if (PAGE.id !== currentPAGEIdRef.current) {
      // console.log('🔄 [HISTORY] PAGE changed from', currentPAGEIdRef.current, 'to', PAGE.id);
      currentPAGEIdRef.current = PAGE.id;
      hasInitialSaveRef.current = false;
      preEditSnapshotRef.current = null;
      const history = getPAGEHistory(PAGE.id);
      if (history) history.undoRedoActive = false;
      // Reset per-PAGE prevElements immediately to avoid borrowing previous PAGE state
      prevElementsMapRef.current.set(PAGE.id, JSON.stringify({
        elements: PAGE.elements || [],
        backgroundColor: PAGE.backgroundColor,
      }));

      // Clear Fabric canvas selection when PAGE changes to avoid ghost selection overlay
      if (fabricCanvasRef.current) {
        // console.log('🧹 [CANVAS] Clearing selection on PAGE change');
        fabricCanvasRef.current.discardActiveObject();
        fabricCanvasRef.current.requestRenderAll();
      }

      // Clear any pending debounce for the previous PAGE
      historyDebounceMapRef.current.forEach((timer, id) => {
        clearTimeout(timer);
        historyDebounceMapRef.current.delete(id);
      });
    }

    if (!isCanvasReady) return;

    const history = getPAGEHistory(PAGE.id);
    // Seed history from PAGE snapshot (elements + background), not the current Fabric canvas
    const initialState = {
      elements: JSON.parse(JSON.stringify(PAGE.elements || [])),
      backgroundColor: PAGE.backgroundColor,
    };
    const initialStateStr = JSON.stringify(initialState);

    // Initialize history for this PAGE if needed
    if (!hasInitialSaveRef.current) {
      if (history && history.states.length === 0) {
        // console.log('📸 [HISTORY] Saving initial state for PAGE', PAGE.id, 'with', initialState.elements?.length || 0, 'elements');
        history.states = [initialState];
        history.index = 0;
        history.lastSaved = initialStateStr;
      }
      hasInitialSaveRef.current = true;
    }

    // Backfill a blank initial history once real elements arrive to avoid undoing to empty canvas
    if (history && history.states.length === 1 && history.index === 0) {
      const savedElements = history.states[0]?.elements || [];
      if (savedElements.length === 0 && (initialState.elements?.length || 0) > 0) {
        history.states[0] = initialState;
        history.lastSaved = initialStateStr;
        // console.log('📸 [HISTORY] Backfilled initial state for PAGE', PAGE.id, 'with', initialState.elements?.length || 0, 'elements');
      }
    }

    // Initialize prevElements for this PAGE to current elements
    if (history && initialStateStr && (!prevElementsMapRef.current.has(PAGE.id) || prevElementsMapRef.current.get(PAGE.id) === '[]')) {
      prevElementsMapRef.current.set(PAGE.id, initialStateStr);
    }
  }, [isCanvasReady, PAGE?.id, PAGE?.elements, getPAGEHistory, collectCurrentPAGEState]);

  // Detect external changes (AI edits) and save to history
  // This catches changes that bypass canvas event handlers
  // Uses per-PAGE tracking to avoid cross-PAGE pollution
  useEffect(() => {
    if (!PAGE?.id || !PAGE?.elements || isUndoRedoActiveFor(PAGE.id)) return;

    try {
      const currentSnapshot = { elements: PAGE.elements || [], backgroundColor: PAGE.backgroundColor };
      const currentStr = JSON.stringify(currentSnapshot);

      // Get previous elements for THIS SPECIFIC PAGE
      const prevStr = prevElementsMapRef.current.get(PAGE.id);

      // Skip if this is the initial load for this PAGE
      if (prevStr === undefined) {
        prevElementsMapRef.current.set(PAGE.id, currentStr);
        return;
      }

      const history = getPAGEHistory(PAGE.id);
      if (!history) return;

      if (currentStr !== prevStr && currentStr !== history.lastSaved) {
        // Elements changed externally (AI edit, etc.) - save both states to history
        // console.log('🤖 [HISTORY] External change detected for PAGE', PAGE.id, '(AI edit?)');

        // ATOMIC AGENT TURN: if this change belongs to the SAME agent turn that
        // already pushed history for this PAGE (and nothing else was saved in
        // between — top of history is still that turn's post-state), REPLACE the
        // post-state instead of pushing again. One agent turn = one undo step,
        // no matter how many operations batches it streamed.
        // GUARDS: index must be AT THE TOP and the top state must literally equal
        // the previous post-state. If the user pressed Ctrl+Z mid-turn, index has
        // moved off the top (or the top no longer matches) — coalescing then would
        // overwrite the pre-turn undo point, so we fall through to a normal push
        // (which also trims the redo branch), exactly like the legacy path.
        const sameAgentTurn = externalEditSessionId
          && lastExternalSessionRef.current.get(PAGE.id) === externalEditSessionId
          && history.index >= 0
          && history.index === history.states.length - 1
          && history.lastSaved === prevStr
          && JSON.stringify(history.states[history.index]) === prevStr;
        if (sameAgentTurn) {
          history.states[history.index] = JSON.parse(currentStr);
          history.lastSaved = currentStr;
          // console.log('💾 [HISTORY] Coalesced agent-turn state for PAGE', PAGE.id, 'index:', history.index);
        } else {
          // Parse the previous state for THIS PAGE
          const prevState = JSON.parse(prevStr);
          const prevStateStr = JSON.stringify(prevState);

          // Trim any redo states
          if (history.index < history.states.length - 1) {
            history.states = history.states.slice(0, history.index + 1);
          }

          // Step 1: Save the PREVIOUS state (before external change) if different from last saved
          if (prevStateStr !== history.lastSaved) {
            history.states.push(prevState);
            history.index = history.states.length - 1;
            // console.log('💾 [HISTORY] Saved pre-AI state for PAGE', PAGE.id, 'index:', history.index);
          }

          // Step 2: Save the CURRENT state (after external change) so redo works
          history.states.push(JSON.parse(currentStr));
          history.index = history.states.length - 1;
          history.lastSaved = currentStr;
          // console.log('💾 [HISTORY] Saved post-AI state for PAGE', PAGE.id, 'index:', history.index);

          // Remember which agent turn (if any) produced the top of this history.
          lastExternalSessionRef.current.set(PAGE.id, externalEditSessionId || null);

          // Limit history to 50 states
          while (history.states.length > 50) {
            history.states.shift();
            history.index -= 1;
          }
        }
      }

      // Always update the previous elements for THIS PAGE
      prevElementsMapRef.current.set(PAGE.id, currentStr);
    } catch (e) {
      // Silently handle Unicode encoding errors during text editing
      // This can happen with incomplete surrogate pairs when backspacing emoji
      console.warn('⚠️ [HISTORY] JSON encoding error (likely Unicode issue, safe to ignore):', e.message);
    }
  }, [PAGE?.id, PAGE?.elements, getPAGEHistory, externalEditSessionId]);

  // Global keyboard event handler for text editing
  useEffect(() => {
    if (Platform.OS !== 'web') return;

    const handleKeyDown = (e) => {
      const canvas = fabricCanvasRef.current;
      if (!canvas) return;

      const activeObj = canvas.getActiveObject();
      if (!activeObj || !activeObj.isEditing) return;

      const textarea = activeObj.hiddenTextarea;
      if (!textarea) return;

      // DON'T intercept these keys - let them pass through to browser/shortcuts handler:
      // 1. Function keys F1–F12 only. Must require a digit AFTER 'F' — the old
      //    check used isNaN(e.key.slice(1)), and isNaN('') is false, so a bare
      //    'F' (a normal character) was wrongly swallowed and couldn't be typed.
      if (/^F([1-9]|1[0-2])$/.test(e.key)) {
        return; // F1, F2, ..., F12
      }

      // 2. Modifier-only keys (pressing Ctrl, Alt, Shift, Meta alone)
      if (['Control', 'Alt', 'Shift', 'Meta', 'CapsLock', 'NumLock', 'ScrollLock'].includes(e.key)) {
        return;
      }

      // 3. Ctrl/Meta shortcuts - allow clipboard operations AND text formatting in text editing
      if (e.ctrlKey || e.metaKey) {
        const allowedClipboardKeys = ['c', 'C', 'v', 'V', 'x', 'X', 'a', 'A'];
        // Text formatting shortcuts: B (bold), I (italic), U (underline)
        if (e.key === 'b' || e.key === 'B') {
          e.preventDefault();
          e.stopPropagation();
          if (handlersRef.current.handleInlineToggleBold) handlersRef.current.handleInlineToggleBold();
          return;
        }
        if (e.key === 'i' || e.key === 'I') {
          e.preventDefault();
          e.stopPropagation();
          if (handlersRef.current.handleInlineToggleItalic) handlersRef.current.handleInlineToggleItalic();
          return;
        }
        if (e.key === 'u' || e.key === 'U') {
          e.preventDefault();
          e.stopPropagation();
          if (handlersRef.current.handleInlineToggleUnderline) handlersRef.current.handleInlineToggleUnderline();
          return;
        }
        // Swallow browser-hijacking combos while editing text: Ctrl+S opens the
        // browser's save-page dialog and Ctrl+D bookmarks the page. handleShortcuts
        // returns early while isEditing, so ITS preventDefault never runs — without
        // this the dialogs pop up mid-typing. (The composer-level listener still
        // receives the event and performs the app save for Ctrl+S.)
        if (['s', 'S', 'd', 'D'].includes(e.key)) {
          e.preventDefault();
          return;
        }
        if (!allowedClipboardKeys.includes(e.key)) {
          return; // Let Ctrl+Z, Ctrl+Y, etc. pass to shortcuts handler
        }
      }

      // 4. Escape key - should deselect/exit editing
      if (e.key === 'Escape') {
        return;
      }

      // 5. Clipboard keys (Ctrl+C/V/X/A) — sync textarea and let browser handle natively
      //    This ensures text copy/paste works with the OS clipboard
      if ((e.ctrlKey || e.metaKey) && ['c', 'C', 'v', 'V', 'x', 'X', 'a', 'A'].includes(e.key)) {
        // COPY: read the selection straight from Fabric's OWN state and write it
        // with the async Clipboard API — deterministic, independent of the hidden
        // textarea's value/selection/focus quirks (relying on native copy from the
        // synced hidden textarea proved unreliable for double-click selections).
        if ((e.key === 'c' || e.key === 'C') && navigator.clipboard?.writeText) {
          const selStart = activeObj.selectionStart;
          const selEnd = activeObj.selectionEnd;
          if (typeof selStart === 'number' && typeof selEnd === 'number' && selEnd > selStart) {
            const selected = (activeObj.text || '').slice(selStart, selEnd);
            e.preventDefault();
            e.stopPropagation();
            navigator.clipboard.writeText(selected).catch((err) => console.warn('📋 [COPY] clipboard write failed:', err));
            return;
          }
        }
        // V/X/A (and C fallback when Clipboard API/selection unavailable): mirror
        // the Fabric textbox's value + selection into the hidden textarea so the
        // browser's native handling operates on exactly what's selected.
        textarea.value = activeObj.text || '';
        if (activeObj.selectionStart !== undefined) {
          textarea.selectionStart = activeObj.selectionStart;
          textarea.selectionEnd = activeObj.selectionEnd !== undefined ? activeObj.selectionEnd : activeObj.selectionStart;
        }
        textarea.focus();
        return; // Let browser handle clipboard natively
      }

      // If the event target is not the Fabric textarea, forward the event
      if (e.target !== textarea) {
        console.log('🔤 [KEYBOARD] Forwarding key to Fabric textarea:', e.key);

        // Create and dispatch a new event to the textarea
        const newEvent = new KeyboardEvent(e.type, {
          key: e.key,
          code: e.code,
          keyCode: e.keyCode,
          charCode: e.charCode,
          which: e.which,
          shiftKey: e.shiftKey,
          ctrlKey: e.ctrlKey,
          altKey: e.altKey,
          metaKey: e.metaKey,
          bubbles: true,
          cancelable: true,
        });

        textarea.dispatchEvent(newEvent);

        // For printable characters, also update the textarea value directly
        if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
          const start = textarea.selectionStart;
          const end = textarea.selectionEnd;
          const value = textarea.value;
          textarea.value = value.slice(0, start) + e.key + value.slice(end);
          textarea.selectionStart = textarea.selectionEnd = start + 1;

          // Trigger input event for Fabric to pick up the change
          textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // Handle Enter
        if (e.key === 'Enter') {
          const start = textarea.selectionStart;
          const end = textarea.selectionEnd;
          const value = textarea.value;
          textarea.value = value.slice(0, start) + '\n' + value.slice(end);
          textarea.selectionStart = textarea.selectionEnd = start + 1;
          textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // Handle backspace
        if (e.key === 'Backspace') {
          const start = textarea.selectionStart;
          const end = textarea.selectionEnd;
          const value = textarea.value;
          if (start === end && start > 0) {
            textarea.value = value.slice(0, start - 1) + value.slice(end);
            textarea.selectionStart = textarea.selectionEnd = start - 1;
          } else if (start !== end) {
            textarea.value = value.slice(0, start) + value.slice(end);
            textarea.selectionStart = textarea.selectionEnd = start;
          }
          textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // Prevent default to avoid double-processing
        e.preventDefault();
        e.stopPropagation();
      }
    };

    // Add listener with capture phase to intercept before React Native Web
    document.addEventListener('keydown', handleKeyDown, true);

    return () => {
      document.removeEventListener('keydown', handleKeyDown, true);
    };
  }, [isCanvasReady]);

  // Keyboard shortcuts for Delete, Undo (Ctrl+Z), Redo (Ctrl+Y)
  useEffect(() => {
    if (Platform.OS !== 'web') return;

    const handleShortcuts = (e) => {
      const canvas = fabricCanvasRef.current;
      if (!canvas) return;

      // Skip if text is being edited
      const activeObj = canvas.getActiveObject();
      if (activeObj?.isEditing) return;

      // Skip if input/textarea is focused
      const target = e.target;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

      // Prevent browser save dialog on Ctrl+S / Cmd+S
      if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        return;
      }

      // Prevent browser select-all on Ctrl+A / Cmd+A (always prevent, regardless of which canvas)
      if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) {
        e.preventDefault();
      }

      // Only handle if canvas has selection OR event originated within canvas container
      const canvasContainer = containerRef.current;
      const isCanvasContext = activeObj || (canvasContainer && canvasContainer.contains(e.target));
      if (!isCanvasContext) {
        return;
      }

      // Select All: Ctrl+A / Cmd+A - select all canvas objects on this page
      if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) {
        console.log('🔲 [KEYBOARD] Ctrl+A pressed - selecting all selectable canvas objects on current page');
        e.stopPropagation();

        // Filter out non-selectable objects (e.g. table cell rects/textboxes)
        const selectableObjects = canvas.getObjects().filter(obj => obj.selectable !== false);
        if (selectableObjects.length > 0) {
          canvas.discardActiveObject();
          const selection = new fabric.ActiveSelection(selectableObjects, { canvas: canvas });
          canvas.setActiveObject(selection);
          canvas.requestRenderAll();
        }
        return;
      }

      // Delete selected object(s)
      if (e.key === 'Delete' || e.key === 'Backspace') {
        // FIX: Also dismiss any active video/embed overlay when deleting
        setInlineVideoData(null);

        // Handle multiple selection (ActiveSelection)
        if (activeObj && activeObj.type === 'activeSelection') {
          console.log('🗑️ [KEYBOARD] Delete pressed, removing multiple selected objects');
          // Capture snapshot before delete
          if (handlersRef.current.capturePreEditSnapshot) {
            handlersRef.current.capturePreEditSnapshot();
          }

          // Get all objects in the selection and their IDs
          const selectedObjects = activeObj.getObjects();
          const elementIds = selectedObjects.map(obj => obj.elementId).filter(id => id);

          // Store PAGE ID now to avoid stale reference during deletion
          const PAGEId = PAGERef.current?.id;
          const batchDeleteHandler = onDeleteMultipleElements;
          const saveHandler = handlersRef.current.saveToHistory;

          // Clear selection before deleting to prevent re-render issues
          canvas.discardActiveObject();
          canvas.requestRenderAll();

          if (elementIds.length > 0 && PAGEId && batchDeleteHandler) {
            console.log('🗑️ [KEYBOARD] Batch deleting', elementIds.length, 'objects:', elementIds);
            // Delete all elements atomically in one state update
            batchDeleteHandler(PAGEId, elementIds);
            // Save to history after batch delete
            if (saveHandler) {
              saveHandler();
            }
          }
          e.preventDefault();
        }
        // Handle single object
        else if (activeObj && activeObj.elementId) {
          console.log('🗑️ [KEYBOARD] Delete pressed, removing selected object:', activeObj.elementId);
          // Capture snapshot before delete
          if (handlersRef.current.capturePreEditSnapshot) {
            handlersRef.current.capturePreEditSnapshot();
          }
          // Use Fabric's active object directly instead of relying on React state
          const elementId = activeObj.elementId;
          if (elementId && PAGERef.current && handlersRef.current.onDeleteElement) {
            handlersRef.current.onDeleteElement(PAGERef.current.id, elementId);
            // Save to history after delete
            if (handlersRef.current.saveToHistory) {
              handlersRef.current.saveToHistory();
            }
          }
          e.preventDefault();
        }
      }

      // Undo: Ctrl+Z (or Cmd+Z on Mac)
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        console.log('⏪ [KEYBOARD] Ctrl+Z pressed - Undo');
        handleUndo();
        e.preventDefault();
      }

      // Redo: Ctrl+Y or Ctrl+Shift+Z (or Cmd+Shift+Z on Mac)
      if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        console.log('⏩ [KEYBOARD] Ctrl+Y/Ctrl+Shift+Z pressed - Redo');
        handleRedo();
        e.preventDefault();
      }

      // Copy: Ctrl+C (or Cmd+C on Mac)
      if ((e.ctrlKey || e.metaKey) && (e.key === 'c' || e.key === 'C')) {
        if (activeObj && onCopyElements) {
          console.log('📋 [KEYBOARD] Ctrl+C pressed - Copy element(s)');
          e.preventDefault();

          // Get selected elements
          const selectedElements = [];

          if (activeObj.type === 'activeSelection') {
            // Multiple selection
            const selectedObjects = activeObj.getObjects();
            selectedObjects.forEach(obj => {
              if (obj.elementId && PAGERef.current?.elements) {
                const element = PAGERef.current.elements.find(el => el.id === obj.elementId);
                if (element) selectedElements.push(element);
              }
            });
          } else if (activeObj.elementId && PAGERef.current?.elements) {
            // Single selection
            const element = PAGERef.current.elements.find(el => el.id === activeObj.elementId);
            if (element) selectedElements.push(element);
          }

          if (selectedElements.length > 0) {
            onCopyElements(selectedElements, PAGERef.current?.id);
            console.log(`📋 [KEYBOARD] Copied ${selectedElements.length} element(s)`);
          }
        }
        return;
      }

      // Cut: Ctrl+X / Cmd+X - copy then delete
      if ((e.ctrlKey || e.metaKey) && (e.key === 'x' || e.key === 'X')) {
        if (activeObj && onCopyElements) {
          console.log('✂️ [KEYBOARD] Ctrl+X pressed - Cut element(s)');
          e.preventDefault();

          const selectedElements = [];
          if (activeObj.type === 'activeSelection') {
            const selectedObjects = activeObj.getObjects();
            selectedObjects.forEach(obj => {
              if (obj.elementId && PAGERef.current?.elements) {
                const element = PAGERef.current.elements.find(el => el.id === obj.elementId);
                if (element) selectedElements.push(element);
              }
            });
          } else if (activeObj.elementId && PAGERef.current?.elements) {
            const element = PAGERef.current.elements.find(el => el.id === activeObj.elementId);
            if (element) selectedElements.push(element);
          }

          if (selectedElements.length > 0) {
            // Copy first
            onCopyElements(selectedElements, PAGERef.current?.id);
            // Then delete
            const PAGEId = PAGERef.current?.id;
            if (activeObj.type === 'activeSelection') {
              const elementIds = selectedElements.map(el => el.id);
              canvas.discardActiveObject();
              canvas.requestRenderAll();
              if (onDeleteMultipleElements && PAGEId) {
                onDeleteMultipleElements(PAGEId, elementIds);
              }
            } else if (activeObj.elementId && handlersRef.current.onDeleteElement && PAGEId) {
              handlersRef.current.onDeleteElement(PAGEId, activeObj.elementId);
            }
            console.log(`✂️ [KEYBOARD] Cut ${selectedElements.length} element(s)`);
          }
        }
        return;
      }

      // Duplicate: Ctrl+D / Cmd+D
      if ((e.ctrlKey || e.metaKey) && (e.key === 'd' || e.key === 'D')) {
        e.preventDefault();
        console.log('📋 [KEYBOARD] Ctrl+D pressed - Duplicate');
        if (handlersRef.current.handleDuplicate) handlersRef.current.handleDuplicate();
        return;
      }

      // Layer ordering: Ctrl+] (bring forward) / Ctrl+[ (send backward)
      if ((e.ctrlKey || e.metaKey) && e.key === ']') {
        e.preventDefault();
        console.log('⬆️ [KEYBOARD] Ctrl+] pressed - Bring Forward');
        if (handlersRef.current.handleBringForward) handlersRef.current.handleBringForward();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key === '[') {
        e.preventDefault();
        console.log('⬇️ [KEYBOARD] Ctrl+[ pressed - Send Backward');
        if (handlersRef.current.handleSendBackward) handlersRef.current.handleSendBackward();
        return;
      }

      // Arrow keys: Nudge selected element(s)
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key) && activeObj) {
        e.preventDefault();
        const step = e.shiftKey ? 10 : 1;
        let dx = 0, dy = 0;
        if (e.key === 'ArrowUp') dy = -step;
        if (e.key === 'ArrowDown') dy = step;
        if (e.key === 'ArrowLeft') dx = -step;
        if (e.key === 'ArrowRight') dx = step;

        if (activeObj.type === 'activeSelection') {
          // Nudge all selected objects
          activeObj.getObjects().forEach(obj => {
            obj.set({ left: obj.left + dx, top: obj.top + dy });
            obj.setCoords();
            // Persist each element position
            if (obj.elementId && PAGERef.current && handlersRef.current.onUpdateElement) {
              const scale = scaleRef.current || 1;
              handlersRef.current.onUpdateElement(PAGERef.current.id, obj.elementId, {
                x: Math.round(obj.left / scale),
                y: Math.round(obj.top / scale),
              });
            }
          });
          activeObj.setCoords();
        } else {
          activeObj.set({ left: activeObj.left + dx, top: activeObj.top + dy });
          activeObj.setCoords();
          // Persist element position
          if (activeObj.elementId && PAGERef.current && handlersRef.current.onUpdateElement) {
            const scale = scaleRef.current || 1;
            handlersRef.current.onUpdateElement(PAGERef.current.id, activeObj.elementId, {
              x: Math.round(activeObj.left / scale),
              y: Math.round(activeObj.top / scale),
            });
          }
        }
        canvas.requestRenderAll();

        // Debounce saving to history for nudge operations
        if (nudgeTimerRef.current) clearTimeout(nudgeTimerRef.current);
        nudgeTimerRef.current = setTimeout(() => {
          if (handlersRef.current.saveToHistory) {
            handlersRef.current.saveToHistory();
          }
        }, 300);
        return;
      }

      // Escape: Deselect all canvas objects
      if (e.key === 'Escape') {
        console.log('🔲 [KEYBOARD] Escape pressed - deselecting all canvas objects');
        canvas.discardActiveObject();
        canvas.requestRenderAll();
        e.preventDefault();
        return;
      }

      // Note: Ctrl+V paste is now handled entirely by the 'paste' event handler
      // which uses marker detection to distinguish internal elements from system clipboard
    };

    document.addEventListener('keydown', handleShortcuts, true); // Use capture phase

    return () => {
      document.removeEventListener('keydown', handleShortcuts, true);
    };
  }, [isCanvasReady, onCopyElements, onPasteElements, onDeleteElement, onDeleteMultipleElements]);

  // Handle Paste (Ctrl+V) for images and text
  useEffect(() => {
    if (Platform.OS !== 'web') return;

    const handlePaste = (e) => {
      // Only handle paste on the currently active page canvas
      if (!isActivePage) return;

      const canvas = fabricCanvasRef.current;
      if (!canvas) return;

      // Skip if editing text inside canvas (let Fabric/browser handle text paste in textarea)
      const activeObj = canvas.getActiveObject();
      if (activeObj && (activeObj.type === 'i-text' || activeObj.type === 'textbox') && activeObj.isEditing) {
        return;
      }

      // Check if event targets an input/textarea outside canvas (e.g. sidebar inputs)
      const target = e.target;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        if (!target.classList.contains('canvas-container') && !target.closest('.canvas-container')) {
          return;
        }
      }

      const items = (e.clipboardData || e.originalEvent?.clipboardData)?.items;
      if (!items) return;

      console.log(`📋 [PASTE] Found ${items.length} clipboard items`);

      // STEP 1: Check for Citra clipboard data (full element/slide data from OS clipboard)
      const textData = e.clipboardData.getData('text');

      try {
        if (textData) {
          const parsed = JSON.parse(textData);
          if (parsed.__citraAIClipboard && onPasteElements) {
            console.log('📋 [PASTE] Detected Citra clipboard data - pasting from OS clipboard');
            e.preventDefault();
            onPasteElements(textData);
            return;
          }
        }
      } catch {
        // Not JSON or not our data - proceed with normal paste
      }

      // STEP 2: Check for images in system clipboard (highest priority for external paste)
      let handled = false;

      // 1. Look for Images
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image') !== -1) {
          const blob = items[i].getAsFile();
          const reader = new FileReader();
          reader.onload = (event) => {
            const imgObj = new Image();
            imgObj.src = event.target.result;
            imgObj.onload = () => {
              const fabricImg = new fabricModule.Image(imgObj);

              // Scale down if too big
              const maxWidth = PAGE_WIDTH * 0.5;
              const scale = fabricImg.width > maxWidth ? maxWidth / fabricImg.width : 0.5;

              fabricImg.set({
                left: PAGE_WIDTH / 2 - (fabricImg.width * scale) / 2,
                top: PAGE_HEIGHT / 2 - (fabricImg.height * scale) / 2,
                scaleX: scale,
                scaleY: scale,
              });

              // Don't add manually to avoid duplicates (prop sync will handle it)
              // canvas.add(fabricImg);
              // canvas.setActiveObject(fabricImg);
              // canvas.requestRenderAll();

              // Persist with z-index so pasted content appears on top
              if (PAGE?.id) {
                const maxZ = PAGE.elements?.length > 0
                  ? Math.max(...PAGE.elements.map(e => parseInt(e.zIndex) || 0)) + 1
                  : 1;
                onAddElement(PAGE.id, 'image', {
                  src: event.target.result,
                  x: fabricImg.left,
                  y: fabricImg.top,
                  width: fabricImg.width * scale,
                  height: fabricImg.height * scale,
                  zIndex: maxZ,
                  isUserMedia: true, // Mark as user media for AI preservation
                });
              }
            };
          };
          reader.readAsDataURL(blob);
          e.preventDefault();
          handled = true;
          return;
        }
      }

      if (handled) return;

      // 2. Look for Text
      const text = e.clipboardData.getData('text');
      if (text && PAGE?.id) {
        e.preventDefault();
        console.log('📋 [PASTE] Pasting text');

        const textbox = new fabricModule.Textbox(text, {
          left: PAGE_WIDTH / 2 - 150,
          top: PAGE_HEIGHT / 2 - 20,
          width: 300,
          fontSize: fontSize || 20,
          fill: fillColor || '#000000',
          splitByGrapheme: true,
        });

        // Don't add manually to avoid duplicates (prop sync will handle it)
        // canvas.add(textbox);
        // canvas.setActiveObject(textbox);
        // canvas.requestRenderAll();

        // Calculate next z-index so pasted text appears on top
        const maxZ = PAGE.elements?.length > 0
          ? Math.max(...PAGE.elements.map(e => parseInt(e.zIndex) || 0)) + 1
          : 1;
        onAddElement(PAGE.id, 'text', {
          textType: 'text',
          content: text,
          x: textbox.left,
          y: textbox.top,
          width: 300,
          height: textbox.height,
          fill: fillColor || '#000000',
          fontSize: fontSize || 20,
          zIndex: maxZ,
        });
      }
    };

    window.addEventListener('paste', handlePaste);
    return () => window.removeEventListener('paste', handlePaste);
  }, [isActivePage, PAGE?.id, fillColor, fontSize, onAddElement, onPasteElements]);

  // SINGLE ACTIVE SELECTION ACROSS PAGES. Every page mounts its own Fabric
  // canvas, and Fabric keeps a canvas's selection when the user clicks a
  // DIFFERENT page's canvas — the stale off-screen selection then ALSO receives
  // document-level keyboard shortcuts (Delete / Ctrl+Z / arrow-nudge), hitting
  // two pages with one keystroke. PowerPoint has exactly one selection at a
  // time. Fix: broadcast on mouse:down; every other canvas instance drops its
  // own selection (committing any in-progress text edit first).
  useEffect(() => {
    if (Platform.OS !== 'web' || !isCanvasReady) return;
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const announceFocus = () => {
      try {
        window.dispatchEvent(new CustomEvent('citra-canvas-focus', { detail: { canvasId: PAGERef.current?.id } }));
      } catch { /* CustomEvent unavailable — nothing to do */ }
    };
    const onFocusElsewhere = (e) => {
      const focusedId = e?.detail?.canvasId;
      if (!focusedId || focusedId === PAGERef.current?.id) return;
      const liveCanvas = fabricCanvasRef.current; // read live ref — survives canvas re-init
      const active = liveCanvas?.getActiveObject?.();
      if (active) {
        if (active.isEditing && typeof active.exitEditing === 'function') active.exitEditing(); // commit text first
        liveCanvas.discardActiveObject();
        liveCanvas.requestRenderAll();
      }
    };

    canvas.on('mouse:down', announceFocus);
    window.addEventListener('citra-canvas-focus', onFocusElsewhere);
    return () => {
      canvas.off('mouse:down', announceFocus);
      window.removeEventListener('citra-canvas-focus', onFocusElsewhere);
    };
  }, [isCanvasReady]);

  // Initialize Fabric.js canvas (web only)
  useEffect(() => {
    if (Platform.OS !== 'web') return;

    // Reset disposed flag on (re-)initialization
    isDisposedRef.current = false;

    const initCanvas = async () => {
      try {
        // Load fabric from CDN
        const fabric = await loadFabricFromCDN();

        if (!fabric) {
          console.error('Fabric.js not available');
          return;
        }

        if (!canvasRef.current) return;

        // FIX: Disable retina scaling on mobile to prevent canvas memory overflow.
        // Mobile devices with 3x+ DPI would create canvases 3x the pixel dimensions,
        // exceeding mobile browser canvas size limits and causing images to not render.
        // A4 pages (794x1123) are especially large — at 3x DPI that's 2382x3369 internal pixels.
        const isMobileDevice = /android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent || '');

        // Create Fabric canvas
        const canvas = new fabric.Canvas(canvasRef.current, {
          width: PAGE_WIDTH * canvasScale,
          height: PAGE_HEIGHT * canvasScale,
          backgroundColor: PAGE?.backgroundColor || '#ffffff',
          preserveObjectStacking: true, // CRITICAL: Prevents active object from jumping to top on select
          selection: true, // ENABLED: Allow multi-selection of shapes
          controlsAboveOverlay: true, // render controls above everything
          enableRetinaScaling: isMobileDevice ? false : true, // Disable on mobile to avoid canvas blowup
        });

        // FIX: Explicitly set textBaseline to a valid value 'alphabetic' to prevent invalid 'alphabetical' error
        try {
          const lowerCtx = canvas.lowerCanvasEl && canvas.lowerCanvasEl.getContext && canvas.lowerCanvasEl.getContext('2d');
          if (lowerCtx) lowerCtx.textBaseline = 'alphabetic';
          const upperCtx = canvas.upperCanvasEl && canvas.upperCanvasEl.getContext && canvas.upperCanvasEl.getContext('2d');
          if (upperCtx) upperCtx.textBaseline = 'alphabetic';
        } catch (e) {
          console.warn('Canvas baseline setup skipped', e);
        }

        fabricCanvasRef.current = canvas;
        setIsCanvasReady(true);

        // Event handlers

        // Format Painter: Apply on mouse:down so clicking an ALREADY-SELECTED element
        // works too — selection:created/updated don't fire when re-clicking the same
        // object. (Parity with PresentationCanvas.)
        canvas.on('mouse:down', (e) => {
          if (formatPainterActiveRef.current && formatPainterDataRef.current && e.target && e.target.elementId) {
            const targetElementId = e.target.elementId;
            if (onFormatPainterApplyRef.current) {
              const targetElement = PAGERef.current?.elements?.find(el => el.id === targetElementId);
              if (targetElement) {
                console.log('🎨 [FORMAT_PAINTER] Applying format via mouse:down to:', targetElementId);
                onFormatPainterApplyRef.current(targetElement);
              }
            }
          }
        });

        canvas.on('selection:created', (e) => {
          const selectedObjects = e.selected || [];
          // Get all element IDs from the selection
          const selectedElementIds = selectedObjects
            .filter(obj => obj?.elementId)
            .map(obj => obj.elementId);

          if (selectedElementIds.length > 0) {
            // Check if format painter is active - apply format to first selected element
            if (formatPainterActiveRef.current && formatPainterDataRef.current && onFormatPainterApplyRef.current) {
              const targetElement = PAGERef.current?.elements?.find(el => el.id === selectedElementIds[0]);
              if (targetElement) {
                console.log('🎨 [FORMAT_PAINTER] Applying format to element:', selectedElementIds[0]);
                onFormatPainterApplyRef.current(targetElement);
              }
            }
            // Pass array if multi-select, single ID if just one
            onSelectElement(selectedElementIds.length === 1 ? selectedElementIds[0] : selectedElementIds);
            console.log('🎯 [CANVAS] Selection created:', selectedElementIds.length, 'elements');
            // Notify shared toolbar of selection state
            if (onElementSelectionChangeRef.current) {
              const obj = selectedObjects[0];
              const isText = obj?.type === 'textbox' || obj?.type === 'i-text' || obj?.type === 'text';
              const currentScale = scaleRef.current || 1;
              onElementSelectionChangeRef.current({
                hasSelection: true,
                type: obj?.type,
                fill: obj?.fill || null,
                stroke: obj?.stroke || null,
                fontSize: isText ? ((obj.fontSize || 16) / currentScale) : null,
                lineHeight: isText ? (obj.lineHeight || 1.4) : null,
                fontWeight: isText ? (obj.fontWeight || 'normal') : null,
                fontStyle: isText ? (obj.fontStyle || 'normal') : null,
                textAlign: isText ? (obj.textAlign || 'left') : null,
                fontFamily: isText ? (obj.fontFamily || '') : null,
                opacity: obj?.opacity ?? 1,
                isText,
              });
            }
          }
        });

        canvas.on('selection:updated', (e) => {
          const selectedObjects = e.selected || [];
          // Get all element IDs from the selection
          const selectedElementIds = selectedObjects
            .filter(obj => obj?.elementId)
            .map(obj => obj.elementId);

          if (selectedElementIds.length > 0) {
            // Check if format painter is active - apply format to first selected element
            if (formatPainterActiveRef.current && formatPainterDataRef.current && onFormatPainterApplyRef.current) {
              const targetElement = PAGERef.current?.elements?.find(el => el.id === selectedElementIds[0]);
              if (targetElement) {
                console.log('🎨 [FORMAT_PAINTER] Applying format to element:', selectedElementIds[0]);
                onFormatPainterApplyRef.current(targetElement);
              }
            }
            // Pass array if multi-select, single ID if just one
            onSelectElement(selectedElementIds.length === 1 ? selectedElementIds[0] : selectedElementIds);
            console.log('🎯 [CANVAS] Selection updated:', selectedElementIds.length, 'elements');
            // Notify shared toolbar of selection state
            if (onElementSelectionChangeRef.current) {
              const obj = selectedObjects[0];
              const isText = obj?.type === 'textbox' || obj?.type === 'i-text' || obj?.type === 'text';
              const currentScale = scaleRef.current || 1;
              onElementSelectionChangeRef.current({
                hasSelection: true,
                type: obj?.type,
                fill: obj?.fill || null,
                stroke: obj?.stroke || null,
                fontSize: isText ? ((obj.fontSize || 16) / currentScale) : null,
                lineHeight: isText ? (obj.lineHeight || 1.4) : null,
                fontWeight: isText ? (obj.fontWeight || 'normal') : null,
                fontStyle: isText ? (obj.fontStyle || 'normal') : null,
                textAlign: isText ? (obj.textAlign || 'left') : null,
                fontFamily: isText ? (obj.fontFamily || '') : null,
                opacity: obj?.opacity ?? 1,
                isText,
              });
            }
          }
        });

        canvas.on('selection:cleared', () => {
          onSelectElement(null);
          // Hide inline formatting toolbar
          if (handlersRef.current.setInlineToolbar) {
            handlersRef.current.setInlineToolbar({ visible: false, x: 0, y: 0, styles: {} });
          }
          // Notify shared toolbar that selection is cleared
          if (onElementSelectionChangeRef.current) {
            onElementSelectionChangeRef.current({ hasSelection: false });
          }
        });

        // Capture snapshot BEFORE any modification starts
        canvas.on('object:moving', (e) => {
          // Capture pre-edit snapshot on first move
          if (handlersRef.current.capturePreEditSnapshot) {
            handlersRef.current.capturePreEditSnapshot();
          }
        });

        canvas.on('object:scaling', (e) => {
          if (handlersRef.current.capturePreEditSnapshot) {
            handlersRef.current.capturePreEditSnapshot();
          }
        });

        canvas.on('object:rotating', (e) => {
          if (handlersRef.current.capturePreEditSnapshot) {
            handlersRef.current.capturePreEditSnapshot();
          }
        });

        canvas.on('object:modified', (e) => {
          const obj = e.target;
          if (obj?.elementId && PAGERef.current) {
            // Use scaleRef.current to get the latest scale value (avoids stale closure)
            const currentScale = scaleRef.current || 1;

            // Find the element's current state from React state
            const currentElement = PAGERef.current.elements?.find(el => el.id === obj.elementId);

            // Check if user actually scaled the object (not just moved/rotated)
            const wasScaled = obj.scaleX !== 1 || obj.scaleY !== 1;

            // For Polygon, Path, and Group objects - handle carefully to avoid drift
            const isComplexShape = obj.type === 'polygon' || obj.type === 'path' || obj.type === 'group';

            let actualWidth, actualHeight, newX, newY;

            if (isComplexShape) {
              // For complex shapes, preserve what we can from current element
              if (wasScaled) {
                // User resized - use bounding rect for dimensions
                const boundingRect = obj.getBoundingRect(true);
                actualWidth = boundingRect.width / currentScale;
                actualHeight = boundingRect.height / currentScale;

                // For rotated shapes, use the shape's actual center point (not bounding rect center)
                // getCenterPoint gives us the true transformation center
                const center = obj.getCenterPoint();
                const centerX = center.x / currentScale;
                const centerY = center.y / currentScale;

                // Store center for proper recreation - convert back to top-left for unrotated placement
                newX = centerX - (actualWidth / 2);
                newY = centerY - (actualHeight / 2);
              } else {
                // User only rotated or moved
                // Keep dimensions from React state
                actualWidth = currentElement?.width;
                actualHeight = currentElement?.height;

                // For rotated complex shapes, always use center-based position
                // obj.left/top represents bounding box corner which shifts with rotation
                if (obj.angle && obj.angle !== 0) {
                  // Shape is rotated - use center-based position calculation
                  const center = obj.getCenterPoint();
                  const centerX = center.x / currentScale;
                  const centerY = center.y / currentScale;
                  newX = centerX - ((actualWidth || 0) / 2);
                  newY = centerY - ((actualHeight || 0) / 2);
                } else {
                  // Not rotated - simple left/top works
                  newX = obj.left / currentScale;
                  newY = obj.top / currentScale;
                }
              }
            } else if (obj.type === 'ellipse') {
              actualWidth = (obj.rx * 2 * obj.scaleX) / currentScale;
              actualHeight = (obj.ry * 2 * obj.scaleY) / currentScale;
              newX = obj.left / currentScale;
              newY = obj.top / currentScale;
            } else if (obj.type === 'circle') {
              const diameter = obj.radius * 2 * obj.scaleX;
              actualWidth = diameter / currentScale;
              actualHeight = diameter / currentScale;
              newX = obj.left / currentScale;
              newY = obj.top / currentScale;
            } else {
              // For Rect, Line, Textbox - use standard calculation
              actualWidth = (obj.width * obj.scaleX) / currentScale;
              actualHeight = (obj.height * obj.scaleY) / currentScale;
              newX = obj.left / currentScale;
              newY = obj.top / currentScale;
            }

            const updates = {};

            // Only include values that are actually defined
            if (newX !== undefined) updates.x = newX;
            if (newY !== undefined) updates.y = newY;

            // For complex shapes (polygon/path/group), store scaleX/scaleY instead of dimensions
            // This allows resize to persist on save/load
            if (isComplexShape) {
              if (wasScaled) {
                updates.scaleX = obj.scaleX;
                updates.scaleY = obj.scaleY;
              }
            } else {
              if (actualWidth !== undefined) updates.width = actualWidth;
              if (actualHeight !== undefined) updates.height = actualHeight;
            }

            if (obj.angle !== undefined) updates.rotation = obj.angle;

            // Reset scale to 1 after capturing dimensions ONLY for non-polygon shapes
            // Polygons keep their scale - prevents recreation and coordinate conversion issues
            if (obj.type === 'polygon' || obj.type === 'path' || obj.type === 'group') {
              // DON'T reset scale for polygons - let them keep the Fabric scale factors
              // This prevents the recreation trigger and keeps transformations consistent
              obj.setCoords();
            } else if (obj.type === 'ellipse') {
              // For ellipse, update rx/ry to reflect scaled size and reset scale
              obj.set({
                rx: obj.rx * obj.scaleX,
                ry: obj.ry * obj.scaleY,
                scaleX: 1,
                scaleY: 1
              });
              obj.setCoords();
            } else if (obj.type === 'circle') {
              // For circle, update radius to reflect scaled size and reset scale
              obj.set({
                radius: obj.radius * obj.scaleX,
                scaleX: 1,
                scaleY: 1
              });
              obj.setCoords();
            } else if (obj.type === 'rect') {
              // For rect, update width/height to reflect scaled size and reset scale
              obj.set({
                width: obj.width * obj.scaleX,
                height: obj.height * obj.scaleY,
                scaleX: 1,
                scaleY: 1
              });
              obj.setCoords();
            } else if (obj.type === 'chart') {
              // For chart, update width/height and recreate internal Chart.js canvas at new size
              const newW = obj.width * obj.scaleX;
              const newH = obj.height * obj.scaleY;
              obj.set({
                width: newW,
                height: newH,
                scaleX: 1,
                scaleY: 1
              });
              obj.setCoords();
              // Recreate Chart.js at new dimensions so it renders crisp
              if (obj._chartConfig && obj._chartCanvas) {
                obj._chartCanvas.width = newW;
                obj._chartCanvas.height = newH;
                if (obj._chartInstance) {
                  obj._chartInstance.destroy();
                  obj._chartInstance = null;
                }
                obj._createChartCanvas();
                obj.dirty = true;
              }
              // Persist chart config alongside position/dimensions
              if (obj._chartConfig) {
                updates.chartConfig = JSON.parse(JSON.stringify(obj._chartConfig));
              }
            }



            if (handlersRef.current.onUpdateElement) {
              handlersRef.current.onUpdateElement(PAGERef.current.id, obj.elementId, updates);
              handlersRef.current.saveToHistory(); // Commit pre-edit snapshot + save new state
            }
          } else if (obj?.type === 'activeSelection' && PAGERef.current) {
            // === MULTI-SELECT: persist positions for every child in the selection ===
            const currentScale = scaleRef.current || 1;
            const children = obj.getObjects();
            if (children.length > 0 && handlersRef.current.onUpdateElement) {
              // Fabric stores child positions relative to the group center.
              // We need the group's absolute center, then offset each child.
              const groupCenter = obj.getCenterPoint();
              children.forEach(child => {
                if (!child.elementId) return;
                // Child's absolute position = group center + child offset
                const absLeft = (groupCenter.x + child.left) / currentScale;
                const absTop = (groupCenter.y + child.top) / currentScale;
                const childUpdates = { x: absLeft, y: absTop };
                // Persist dimensions if the group was scaled
                if (obj.scaleX !== 1 || obj.scaleY !== 1) {
                  childUpdates.width = (child.width * child.scaleX * obj.scaleX) / currentScale;
                  childUpdates.height = (child.height * child.scaleY * obj.scaleY) / currentScale;
                }
                handlersRef.current.onUpdateElement(PAGERef.current.id, child.elementId, childUpdates);
              });
              handlersRef.current.saveToHistory();
            }
          }
        });



        // Movement sometimes skips object:modified; backstop save on mouse up when a snapshot exists
        canvas.on('mouse:up', () => {
          if (preEditSnapshotRef.current && handlersRef.current.saveToHistory) {
            handlersRef.current.saveToHistory();
          }
        });

        // Capture snapshot before text editing starts
        canvas.on('text:editing:entered', (e) => {
          if (handlersRef.current.capturePreEditSnapshot) {
            handlersRef.current.capturePreEditSnapshot();
          }

          // Attach selection:changed listener for inline formatting toolbar
          const obj = e.target;
          if (obj && (obj.type === 'textbox' || obj.type === 'i-text')) {
            const handler = () => {
              const start = obj.selectionStart;
              const end = obj.selectionEnd;
              if (start !== end) {
                const selStyles = obj.getSelectionStyles(start, end);
                const firstStyle = selStyles[0] || {};
                const currentScale = scaleRef.current || 1;
                const boundingRect = obj.getBoundingRect();
                if (handlersRef.current.setInlineToolbar) {
                  handlersRef.current.setInlineToolbar({
                    visible: true,
                    x: boundingRect.left + boundingRect.width / 2,
                    y: boundingRect.top,
                    styles: {
                      fontWeight: firstStyle.fontWeight || obj.fontWeight || 'normal',
                      fontStyle: firstStyle.fontStyle || obj.fontStyle || 'normal',
                      underline: firstStyle.underline !== undefined ? firstStyle.underline : (obj.underline || false),
                      fill: firstStyle.fill || obj.fill || '#000000',
                      textBackgroundColor: firstStyle.textBackgroundColor || '',
                      fontFamily: firstStyle.fontFamily || obj.fontFamily || 'Inter',
                      fontSize: (firstStyle.fontSize || obj.fontSize || 16) / currentScale,
                    },
                  });
                }
              } else {
                // No selection — hide toolbar
                if (handlersRef.current.setInlineToolbar) {
                  handlersRef.current.setInlineToolbar({ visible: false, x: 0, y: 0, styles: {} });
                }
              }
            };
            obj.on('selection:changed', handler);
            obj._inlineSelectionHandler = handler;
          }
        });

        canvas.on('text:changed', (e) => {
          const obj = e.target;
          if (obj?.elementId && PAGERef.current && handlersRef.current.onUpdateElement) {
            handlersRef.current.onUpdateElement(PAGERef.current.id, obj.elementId, { content: obj.text });
            // Use debounced save for text changes (user types continuously)
            if (handlersRef.current.debouncedSaveToHistory) {
              handlersRef.current.debouncedSaveToHistory();
            }
          }
        });

        // Commit history when text editing ends
        canvas.on('text:editing:exited', (e) => {
          // Hide inline formatting toolbar
          if (handlersRef.current.setInlineToolbar) {
            handlersRef.current.setInlineToolbar({ visible: false, x: 0, y: 0, styles: {} });
          }

          // Detach selection:changed listener
          const obj = e.target;
          if (obj && obj._inlineSelectionHandler) {
            obj.off('selection:changed', obj._inlineSelectionHandler);
            delete obj._inlineSelectionHandler;
          }

          // Persist character-level styles alongside content
          if (obj && obj.elementId && PAGERef.current && handlersRef.current.onUpdateElement) {
            const updates = { content: obj.text };
            if (obj.styles && Object.keys(obj.styles).length > 0) {
              updates.styles = JSON.parse(JSON.stringify(obj.styles));
            }
            handlersRef.current.onUpdateElement(PAGERef.current.id, obj.elementId, updates);
          }

          if (handlersRef.current.saveToHistory) {
            handlersRef.current.saveToHistory();
          }
        });

        // DIAGNOSTIC: Log mouse events to confirm Fabric is receiving them
        let lastClickTime = 0;
        let lastClickTarget = null;

        canvas.on('mouse:down', (opt) => {
          console.log('🎨 [FABRIC] mouse:down received', opt.target ? `on ${opt.target.type}` : 'on canvas');

          // Format Painter: Apply on mouse:down so clicking already-selected elements works
          if (formatPainterActiveRef.current && formatPainterDataRef.current && opt.target && opt.target.elementId) {
            const targetElementId = opt.target.elementId;
            if (onFormatPainterApplyRef.current) {
              const targetElement = PAGERef.current?.elements?.find(el => el.id === targetElementId);
              if (targetElement) {
                console.log('🎨 [FORMAT_PAINTER] Applying format via mouse:down to:', targetElementId);
                onFormatPainterApplyRef.current(targetElement);
              }
            }
          }

          // Manual Double Click Detection (Backup for when native dblclick fails)
          const now = Date.now();
          if (opt.target && lastClickTarget === opt.target && (now - lastClickTime) < 500) {
            if (opt.target.type === 'chart' && opt.target.elementId) {
              console.log('🎨 [FABRIC] Manual Double Click Detected on Chart:', opt.target.elementId);
              const currentPAGE = PAGERef.current;
              const element = currentPAGE?.elements?.find(e => e.id === opt.target.elementId);
              if (element && element.chartConfig && onEditChart) {
                // Pass a deep copy to prevent mutation of state in the modal
                onEditChart(element.id, JSON.parse(JSON.stringify(element.chartConfig)));
              }
            } else if (opt.target.elementId && (() => {
              const cp = PAGERef.current;
              const el = cp?.elements?.find(e => e.id === opt.target.elementId);
              return el && el.type === ELEMENT_TYPES.SVG_DIAGRAM;
            })()) {
              const cp = PAGERef.current;
              const el = cp?.elements?.find(e => e.id === opt.target.elementId);
              if (el && onEditDiagram) {
                console.log('🎨 [FABRIC] Manual Double Click Detected on SvgDiagram:', el.id);
                onEditDiagram(el);
              }
            } else if (opt.target.type === 'table') {
              // Table Editing Logic
              console.log('🎨 [FABRIC] Manual Double Click Detected on Table');
              const table = opt.target;
              const canvas = fabricCanvasRef.current; // access canvas ref directly if needed, or use 'canvas' from closure

              try {
                // 1. Calculate pointer relative to table
                const pointer = canvas.getPointer(opt.e);
                const groupMatrix = table.calcTransformMatrix();
                // Safe access to util
                const util = fabricModule.util;
                const invertedMatrix = util.invertTransform(groupMatrix);
                const localPoint = util.transformPoint(
                  new fabricModule.Point(pointer.x, pointer.y),
                  invertedMatrix
                );

                // 2. Adjust for origin (defaulting to center for groups)
                const originXOffset = table.width / 2;
                const originYOffset = table.height / 2;
                const localX = localPoint.x + originXOffset;
                const localY = localPoint.y + originYOffset;

                // 3. Find cell coordinates
                const cfg = table._tableConfig;
                if (cfg) {
                  const col = Math.floor(localX / cfg.cellWidth);
                  const row = Math.floor(localY / cfg.cellHeight);

                  if (row >= 0 && row < cfg.rows && col >= 0 && col < cfg.cols) {
                    console.log(`✏️ [TABLE] Editing cell ${row},${col}`);

                    // 4. Create Temp Editor
                    const currentText = (cfg.cellData && cfg.cellData[row] && cfg.cellData[row][col]) || '';

                    // Calculate absolute position for proper placement
                    const cellLeftOffset = (col * cfg.cellWidth) - originXOffset;
                    const cellTopOffset = (row * cfg.cellHeight) - originYOffset;

                    // Add small padding for text
                    const padding = 6;

                    const cellPos = util.transformPoint(
                      new fabricModule.Point(cellLeftOffset, cellTopOffset),
                      groupMatrix
                    );

                    // Create overlay textbox
                    const tempInput = new fabricModule.Textbox(currentText, {
                      left: cellPos.x + (padding * table.scaleX), // adjust for padding
                      top: cellPos.y + (padding * table.scaleY),
                      width: (cfg.cellWidth - (padding * 2)) * table.scaleX, // width scaled
                      fontSize: 12, // Base font size
                      fontFamily: 'Inter, system-ui, sans-serif',
                      fill: (row === 0 && cfg.hasHeader) ? cfg.headerTextColor : cfg.textColor,
                      backgroundColor: 'rgba(255,255,255,0.9)', // slightly transparent white to see context
                      angle: table.angle,
                      scaleX: table.scaleX, // Apply table scale
                      scaleY: table.scaleY,
                      hasControls: false,
                      selectable: false,
                      evented: true,
                    });

                    canvas.add(tempInput);
                    canvas.setActiveObject(tempInput);

                    // Slight delay to ensure render
                    setTimeout(() => {
                      tempInput.enterEditing();
                      tempInput.selectAll();
                    }, 50);

                    // 5. Handle Save
                    tempInput.on('editing:exited', () => {
                      const newVal = tempInput.text;
                      // Update table internal data
                      table.setCellText(row, col, newVal);

                      // Remove editor
                      canvas.remove(tempInput);
                      canvas.requestRenderAll();

                      // Persist changes
                      if (handlersRef.current.onUpdateElement && PAGERef.current) {
                        handlersRef.current.onUpdateElement(PAGERef.current.id, table.elementId, {
                          tableConfig: table.getTableConfig()
                        });
                        if (handlersRef.current.saveToHistory) {
                          handlersRef.current.saveToHistory();
                        }
                      }
                    });
                  }
                }
              } catch (err) {
                console.error('❌ [TABLE] Edit error:', err);
              }
            }
          }
          lastClickTime = now;
          lastClickTarget = opt.target;
        });

        canvas.on('mouse:dblclick', (opt) => {
          console.log('🎨 [FABRIC] mouse:dblclick received', opt.target ? `on ${opt.target.type}` : 'on canvas');
          if (opt.target && opt.target.type === 'textbox') {
            console.log('🎨 [FABRIC] Text editing mode triggered');
          }
          // Handle chart double-click for editing
          if (opt.target && opt.target.type === 'chart' && opt.target.elementId) {
            console.log('🎨 [FABRIC] Chart editing mode triggered for:', opt.target.elementId);
            // Use PAGERef to avoid stale closure (PAGE might have changed since listener init)
            const currentPAGE = PAGERef.current;
            const element = currentPAGE?.elements?.find(e => e.id === opt.target.elementId);

            if (element && element.chartConfig && onEditChart) {
              // Pass a deep copy to prevent mutation of state in the modal
              onEditChart(element.id, JSON.parse(JSON.stringify(element.chartConfig)));
            }
          }

          // Handle svg_diagram double-click → regenerate via AI modal
          if (opt.target && opt.target.elementId && onEditDiagram) {
            const currentPAGE = PAGERef.current;
            const element = currentPAGE?.elements?.find(e => e.id === opt.target.elementId);
            if (element && element.type === ELEMENT_TYPES.SVG_DIAGRAM) {
              console.log('🎨 [FABRIC] SvgDiagram regenerate triggered for:', element.id);
              onEditDiagram(element);
            }
          }

          // Handle VIDEO double-click (Preview/Play)
          if (opt.target && opt.target.elementId) {
            // NO-OP for double click now (User requested single click)
          }
        });

        // SINGLE CLICK PLAYBACK LOGIC
        canvas.on('mouse:up', (opt) => {
          // If we dragged, ignore
          if (opt.isClick && opt.target) {
            const t = opt.target;
            // Check for videos (YouTube, Vimeo, Loom, Spotify, local, recorded)
            const isVideoOverlay = t.videoType && ['youtube', 'vimeo', 'loom', 'spotify', 'local', 'recorded'].includes(t.videoType);
            // Check for embeds (Figma, Miro, Google, etc.)
            const isEmbedOverlay = t.embedType;

            if (isVideoOverlay || isEmbedOverlay || (t.type === 'group' && (t.videoType || t.embedType))) {
              console.log('🎥 [FABRIC] Media single-click detected:', t.elementId, 'type:', t.videoType || t.embedType);

              // Calculate EXACT absolute positions for overlay
              const boundingRect = t.getBoundingRect();
              // Inset overlay by 15px to allow grabbing the fabric object backend
              const PADDING = 15;

              const layout = {
                x: boundingRect.left + PADDING,
                y: boundingRect.top + PADDING,
                width: boundingRect.width - (PADDING * 2),
                height: boundingRect.height - (PADDING * 2),
                angle: t.angle || 0
              };

              const currentPAGE = PAGERef.current;
              const element = currentPAGE?.elements?.find(e => e.id === t.elementId);

              if (element) {
                setInlineVideoData({
                  ...element,
                  layout // computed layout from fabric
                });
              }
            } else {
              // Clicked something else? Close video
              setInlineVideoData(null);
            }
          } else if (opt.isClick) {
            // Clicked empty canvas
            setInlineVideoData(null);
          }
        });

        // Hide video overlay on transform (drag/scale/rotate)
        canvas.on('object:moving', () => setInlineVideoData(null));
        canvas.on('object:scaling', () => setInlineVideoData(null));
        canvas.on('object:rotating', () => setInlineVideoData(null));

        // Cleanup on unmount
        return () => {
          canvas.dispose();
        };
      } catch (error) {
        console.error('Failed to initialize Fabric canvas:', error);
      }
    };

    initCanvas();

    return () => {
      // Mark as disposed FIRST to prevent any pending async renders from firing
      isDisposedRef.current = true;
      // Invalidate any in-flight render cycles
      renderIdRef.current++;
      if (fabricCanvasRef.current) {
        // Safely dispose: patch renderAll/requestRenderAll to no-ops before disposing
        // This prevents pending requestAnimationFrame callbacks from crashing
        // with 'Cannot read properties of undefined (reading getRetinaScaling)'
        try {
          fabricCanvasRef.current.renderAll = function () { };
          fabricCanvasRef.current.requestRenderAll = function () { };
          fabricCanvasRef.current.renderAndReset = function () { };
        } catch (e) { /* ignore */ }
        fabricCanvasRef.current.dispose();
        fabricCanvasRef.current = null;
      }
      // Cleanup all animation video elements and RAF loops
      if (animationIntervalsRef.current) {
        animationIntervalsRef.current.forEach((animData) => {
          if (animData) {
            if (animData.rafId) cancelAnimationFrame(animData.rafId);
            if (animData.video) {
              animData.video.pause();
              animData.video.src = '';
              animData.video.remove();
            }
          }
        });
        animationIntervalsRef.current.clear();
      }
    };
  }, [Platform.OS]);

  // Update canvas scale - just update dimensions and state, don't render yet
  useEffect(() => {
    if (fabricCanvasRef.current && isCanvasReady && scale > 0) {
      // Clear selection before changing scale to avoid stale coordinates (e.g., when F12 DevTools opens)
      fabricCanvasRef.current.discardActiveObject();

      fabricCanvasRef.current.setDimensions({
        width: PAGE_WIDTH * scale,
        height: PAGE_HEIGHT * scale,
      });
      setCanvasScale(scale);
      // Don't call renderPAGEElements() here - canvasScale state isn't updated yet!
      // The separate useEffect below will handle re-rendering after state updates
    }
  }, [scale, isCanvasReady]);

  // Re-render elements when canvasScale state actually updates
  useEffect(() => {
    // FIX: Skip rendering until container is measured and we have a real scale (> 0).
    // On mobile, canvasScale starts at 0 until onLayout fires. Without this guard,
    // elements would render at 0x0 or full 794x1123 size, and async image loads
    // would capture stale positions that persist after the correct scale arrives.
    if (isCanvasReady && PAGE && fabricCanvasRef.current && canvasScale > 0) {
      renderPAGEElements();
    }
  }, [canvasScale]);

  // Render PAGE elements when PAGE changes or elements are updated
  useEffect(() => {
    if (isCanvasReady && PAGE && canvasScale > 0) {
      renderPAGEElements();
    }
  }, [PAGE, PAGE?.elements, isCanvasReady, printableStyle]);

  // FIX: Clear inline video overlay when PAGE changes to prevent ghost videos
  useEffect(() => {
    setInlineVideoData(null);
  }, [PAGE?.id]);

  // FIX: Re-render canvas when browser tab becomes visible again.
  // Fabric.js canvases can go blank when the tab is inactive because
  // browsers throttle/skip rendering for hidden tabs.
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const handleVisibilityChange = () => {
      if (!document.hidden && fabricCanvasRef.current && !isDisposedRef.current && canvasScale > 0) {
        fabricCanvasRef.current.requestRenderAll();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [canvasScale]);

  // Render all elements on the canvas
  const renderPAGEElements = useCallback(async () => {
    if (!fabricCanvasRef.current || !PAGE || !fabricModule || isDisposedRef.current) return;

    // Increment render ID to invalidate previous running renders
    const currentRenderId = ++renderIdRef.current;
    // Store current PAGE ID for async callbacks to check
    const currentPAGEId = PAGE.id;

    const canvas = fabricCanvasRef.current;
    const fabric = fabricModule;

    // 1. Update Background
    const bgColor = PAGE.backgroundColor || printableStyle?.PAGEBackground || '#ffffff';
    if (canvas.backgroundColor !== bgColor) {
      canvas.backgroundColor = bgColor;
    }

    // 2. Handle Background Image — use globalImageCache and skip if URL unchanged
    if (PAGE.backgroundImage) {
      if (lastBgImageRef.current !== PAGE.backgroundImage) {
        lastBgImageRef.current = PAGE.backgroundImage;
        const loadBg = (url, useCors = true) => {
          const imgOpts = useCors ? { crossOrigin: 'anonymous' } : undefined;
          fabric.Image.fromURL(url, (img) => {
            if (isDisposedRef.current || !fabricCanvasRef.current) return;
            if (img) {
              img.set({
                scaleX: (PAGE_WIDTH * canvasScale) / img.width,
                scaleY: (PAGE_HEIGHT * canvasScale) / img.height,
                selectable: false,
                evented: false,
              });
              canvas.setBackgroundImage(img, canvas.renderAll.bind(canvas));
            } else if (useCors) {
              loadBg(url, false);
            } else {
              // Raw Image() fallback for mobile
              const rawImg = new Image();
              rawImg.onload = () => {
                if (isDisposedRef.current || !fabricCanvasRef.current) return;
                try {
                  const fImg = new fabric.Image(rawImg);
                  fImg.set({ scaleX: (PAGE_WIDTH * canvasScale) / fImg.width, scaleY: (PAGE_HEIGHT * canvasScale) / fImg.height, selectable: false, evented: false });
                  canvas.setBackgroundImage(fImg, canvas.renderAll.bind(canvas));
                } catch (e) { console.error('❌ [CANVAS] Background image raw fallback failed:', e); }
              };
              rawImg.src = url;
            }
          }, imgOpts);
        };
        const cachedBg = globalImageCache.get(PAGE.backgroundImage);
        if (cachedBg) {
          loadBg(cachedBg);
        } else {
          globalImageCache.fetchAndCache(PAGE.backgroundImage)
            .then(blobUrl => loadBg(blobUrl))
            .catch(() => loadBg(PAGE.backgroundImage));
        }
      }
    } else {
      if (lastBgImageRef.current !== null) {
        lastBgImageRef.current = null;
        canvas.setBackgroundImage(null, canvas.renderAll.bind(canvas));
      }
    }

    // 3. Diffing Logic
    // FIX: Use Map<string, fabric.Object[]> to handle duplicates and unknown IDs
    const allObjects = canvas.getObjects();
    const currentMap = new Map();

    allObjects.forEach(obj => {
      // Treat undefined elementId as 'unknown' to ensure they get cleaned up
      const id = obj.elementId || 'unknown';
      if (!currentMap.has(id)) {
        currentMap.set(id, []);
      }
      currentMap.get(id).push(obj);
    });

    const activeObj = canvas.getActiveObject();
    const activeId = activeObj?.elementId;

    // Detect all element IDs in an active multi-selection (ActiveSelection)
    // so we skip position/scale updates for grouped children — their coordinates
    // are group-relative and setting absolute values would distort them.
    const activeSelectionIds = new Set();
    if (activeObj?.type === 'activeSelection') {
      activeObj.getObjects().forEach(o => {
        if (o.elementId) activeSelectionIds.add(o.elementId);
      });
    }

    // SORT BY Z-INDEX to ensure correct stacking order for synchronous elements
    const sortedElements = [...(PAGE.elements || [])].sort((a, b) => (a.zIndex || 0) - (b.zIndex || 0));

    // console.log(`📊 [CANVAS] Syncing ${sortedElements.length} elements for PAGE ${PAGE.id}:`,
    //   sortedElements.map(e => `${e.type}:${e.id}`).join(', ')
    // );

    for (const element of sortedElements) {
      if (!element.id) continue; // Skip invalid elements from data

      const existingList = currentMap.get(element.id);
      let existing = null;

      // Reuse the first available object with this ID
      if (existingList && existingList.length > 0) {
        existing = existingList.shift();
        // Any remaining objects in the list are duplicates and will be removed in step 4
      }

      // Debug logging for video elements
      if (element.type === 'video') {
        console.log(`🎥 [OBJECT_MAP] Video element ${element.id} lookup:`, {
          elementId: element.id,
          existingListLength: existingList?.length || 0,
          foundExisting: !!existing,
          existingType: existing?.type,
          existingElementId: existing?.elementId,
          allCanvasObjects: canvas.getObjects().map(o => ({ type: o.type, elementId: o.elementId }))
        });
      }

      // If object exists and matches type (simple check), update it
      // Note: If type changed, we treat as new (fall through to else)
      if (existing) {
        // Skip position/scale updates if user is currently interacting with this object
        // This prevents the "reset" or jitter during drag
        const isActive = (activeId === element.id) || activeSelectionIds.has(element.id);

        // Check if z-index changed - if so, we need to reorder the object in the canvas stack
        const existingZ = parseInt(existing.zIndex) || 0;
        const newZ = parseInt(element.zIndex) || 0;
        if (existingZ !== newZ) {
          // Remove and re-insert at correct position
          canvas.remove(existing);
          existing.zIndex = newZ;
          addToCanvasSorted(canvas, existing, newZ);
          // console.log(`🔄 [CANVAS] Reordered element ${element.id}: z ${existingZ} → ${newZ}`);
        }

        if (renderIdRef.current !== currentRenderId) return; // Abort if stale
        await renderElement(element, canvas, fabric, currentRenderId, currentPAGEId, existing, isActive);
      } else {
        // Create new
        if (renderIdRef.current !== currentRenderId) return; // Abort if stale
        await renderElement(element, canvas, fabric, currentRenderId, currentPAGEId);
      }
    }

    // 4. Remove deleted objects (everything remaining in map)
    currentMap.forEach((list) => {
      list.forEach(obj => {
        // SAFETY: If the object being removed is currently active/selected, 
        // Deselect it first to prevent "getRetinaScaling of undefined" error during render
        if (canvas.getActiveObject() === obj) {
          console.log('🛡️ [CANVAS] Deselecting object before removal:', obj.elementId);
          canvas.discardActiveObject();
        }
        // Cleanup animation if this is an animation element
        if (obj.isAnimation && obj.elementId && animationIntervalsRef.current.has(obj.elementId)) {
          console.log(`🎬 [ANIMATION] Cleaning up animation for removed element: ${obj.elementId}`);
          const animData = animationIntervalsRef.current.get(obj.elementId);
          if (animData) {
            if (animData.rafId) cancelAnimationFrame(animData.rafId);
            if (animData.video) {
              animData.video.pause();
              animData.video.src = '';
              animData.video.remove();
            }
          }
          animationIntervalsRef.current.delete(obj.elementId);
        }
        canvas.remove(obj);
      });
    });

    if (renderIdRef.current !== currentRenderId || isDisposedRef.current) return;
    // Guard against disposed canvas context (prevents 'clearRect of null' error)
    if (canvas.contextContainer) {
      canvas.requestRenderAll();
    }
    // console.log('🎨 [CANVAS] Render sync complete for cycle', currentRenderId, 'PAGEId:', PAGE?.id, 'hasCallback:', !!onRenderComplete);

    // Notify parent that canvas has finished rendering (with small delay for paint)
    if (onRenderComplete && PAGE?.id) {
      setTimeout(() => {
        // console.log('📸 [CANVAS] Calling onRenderComplete for PAGE:', PAGE?.id);
        onRenderComplete(PAGE?.id);
      }, 50);
    }
  }, [PAGE, canvasScale, printableStyle, onRenderComplete]);

  // Helper: Insert object into canvas at correct position based on Z-Index
  // "The Painter's Algorithm" - Strict Insertion
  // FIX: Also removes any existing object with the same elementId to prevent duplicates from async loading
  const addToCanvasSorted = (canvas, object, zIndex) => {
    if (!canvas || !object) return;

    // Persist Z-Index on the object itself for future reference
    object.zIndex = parseInt(zIndex) || 0;

    // FIX: Remove any existing object with the same elementId to prevent duplicates
    // This is critical for async icon loading where multiple render cycles may trigger
    // before the first async callback completes
    if (object.elementId) {
      const existingObjects = canvas.getObjects().filter(obj => obj.elementId === object.elementId);
      if (existingObjects.length > 0) {
        // console.log(`🧹 [CANVAS] Removing ${existingObjects.length} duplicate(s) for elementId: ${object.elementId}`);
        existingObjects.forEach(existing => canvas.remove(existing));
      }
    }

    const objects = canvas.getObjects();

    // Find the first object that has a HIGHER zIndex than our new object.
    // We should insert BEFORE that object.
    // If no object is higher, we append to the end.
    let insertionIndex = objects.length; // Default: Append to top

    for (let i = 0; i < objects.length; i++) {
      const objZ = parseInt(objects[i].zIndex) || 0;
      if (objZ > object.zIndex) {
        insertionIndex = i;
        break;
      }
    }

    canvas.insertAt(object, insertionIndex);
  };

  // Render individual element (Create or Update)
  const renderElement = async (element, canvas, fabric, renderId, currentPAGEId, existingObj = null, skipLayout = false) => {
    // Safety check at start - also check if canvas has been disposed
    if (renderIdRef.current !== renderId || isDisposedRef.current) return;

    // Card-like shapes render translucent (50%). Done at render time so it
    // also applies to documents loaded from the database. Shallow-copy rather
    // than mutate — the original element stays intact in React state.
    if (isCardLikeShape(element, PAGE_WIDTH, PAGE_HEIGHT)) {
      element = { ...element, opacity: 0.5 };
    }

    let fabricObj = existingObj;

    const scaledX = element.x * canvasScale;
    const scaledY = element.y * canvasScale;
    const scaledWidth = element.width * canvasScale;
    const scaledHeight = element.height * canvasScale;

    // Common options for set() or constructor
    // Note: We need to handle specific types separately because constructors verify args

    // Helper to modify SVG deeply (recursive) - Shared for both Create and Update
    const applyColorToObjects = (objects, color) => {
      // Normalize objects to array
      const objs = Array.isArray(objects) ? objects : [objects];

      objs.forEach(obj => {
        if (!obj) return;

        if (obj.type === 'group' && obj.getObjects) {
          applyColorToObjects(obj.getObjects(), color);
        } else if (['path', 'rect', 'polygon', 'circle', 'ellipse', 'line', 'polyline'].includes(obj.type)) {

          const hasVisibleStroke = obj.stroke && obj.stroke !== 'none' && obj.stroke !== 'transparent' && (obj.strokeWidth && obj.strokeWidth > 0);
          const hasFill = obj.fill && obj.fill !== 'none' && obj.fill !== 'transparent';
          const defaultColor = color || '#000000';

          if (hasFill) {
            // Change fill — leave stroke alone to preserve user-set border colors
            obj.set({ fill: defaultColor });
          } else if (hasVisibleStroke) {
            // Outline-only path — stroke IS the visual color
            obj.set({ stroke: defaultColor });
          } else {
            // Default to FILL for shapes
            obj.set({ fill: defaultColor });
            if (!obj.stroke || obj.stroke === 'none') {
              obj.set({ stroke: 'transparent', strokeWidth: 0 });
            }
          }
        }
      });
    };

    // Helper for async rendering (shared by Priority 3 and S3 fallback)
    const renderAsyncIcon = (targetIconName, targetRenderId) => {
      // console.log(`[CANVAS] Triggering async render helper for: ${targetIconName}`);
      mapIconToPathAsync(targetIconName).then(({ path, svg, name }) => {
        // Allow late-arriving icons if still on same PAGE
        if (PAGERef.current?.id !== currentPAGEId) {
          // console.warn(`⚠️ [CANVAS] Stale render for ${targetIconName} (async). Aborting.`);
          return;
        }
        if (!fabricCanvasRef.current) return;

        // console.log(`✅ [CANVAS] Proceeding with async render for ${targetIconName}`);

        // 1. Try SVG content first (preferred for complex icons)
        if (svg) {
          // pre-process SVG to force colors at string level (most robust)
          let finalSvg = svg;
          // FIX: Check both element.fill and element.color (AI JSON uses color)
          const targetColor = element.fill || element.color;
          if (targetColor) {
            // Replace currentColor with user's fill/color
            finalSvg = finalSvg.replace(/currentColor/g, targetColor);

            // Also try to replace explicit black/white if they are not 'none'
            // Be careful not to break IDs or Urls
          }

          fabric.loadSVGFromString(finalSvg, (objects, options) => {
            // Allow late-arriving icons if still on same PAGE
            if (PAGERef.current?.id !== currentPAGEId) return;
            if (objects && objects.length > 0) {
              const svgGroup = fabric.util.groupSVGElements(objects, options);

              // Calculate scale based on actual content size
              const contentW = svgGroup.width || options.width || 24;
              const contentH = svgGroup.height || options.height || 24;
              const iSize = (element.size || 24) * scale;

              const sX = (element.width && element.height)
                ? (element.width * scale) / contentW
                : iSize / contentW;

              const sY = (element.width && element.height)
                ? (element.height * scale) / contentH
                : iSize / contentH;

              svgGroup.set({
                left: scaledX,
                top: scaledY,
                scaleX: sX,
                scaleY: sY,
                fill: element.fill || element.color || '#000000', // Apply fill if possible (check both fill and color for AI JSON)
                selectable: isEditable,
                originX: 'left',
                originY: 'top',
                elementId: element.id,
                iconName: targetIconName, // Store icon name for diffing
                _iconRefW: contentW, _iconRefH: contentH, // Reference dims for scale updates
                zIndex: element.zIndex // Ensure zIndex is set
              });

              // Recursive helper to apply color to all paths/objects
              const applyColorRecursively = (obj, color) => {
                if (obj.type === 'group' && obj.getObjects) {
                  obj.getObjects().forEach(child => applyColorRecursively(child, color));
                } else {
                  // Apply fill color — only change stroke for outline-only paths
                  if (obj.fill && obj.fill !== 'none') {
                    obj.set('fill', color);
                  } else if (obj.stroke && obj.stroke !== 'none') {
                    // Outline-only path — stroke IS the visible color
                    obj.set('stroke', color);
                  } else {
                    // Fallback for uncolored paths
                    obj.set('fill', color);
                  }
                }
              };

              // Apply color to paths
              // FIX: Check both element.fill and element.color (AI JSON uses color)
              const iconColor = element.fill || element.color;
              if (iconColor) {
                applyColorRecursively(svgGroup, iconColor);
              }

              // FIX: Use addToCanvasSorted instead of canvas.add to ensure duplicate prevention
              addToCanvasSorted(canvas, svgGroup, element.zIndex);
              canvas.requestRenderAll();
            }
          });
        }
        // 2. Fallback to Path data
        else if (path) {
          const oW = 24; const oH = 24;
          let sX, sY;
          if (element.width && element.height) {
            sX = (element.width * scale) / oW;
            sY = (element.height * scale) / oH;
          } else {
            const iSize = (element.size || 24) * scale;
            sX = iSize / oW;
            sY = iSize / oH;
          }

          const asyncFabricObj = new fabric.Path(path, {
            left: scaledX,
            top: scaledY,
            fill: 'none',
            stroke: element.fill || element.color || '#000000',
            strokeWidth: 1.5,
            scaleX: sX,
            scaleY: sY,
            selectable: isEditable,
            originX: 'left',
            originY: 'top',
            elementId: element.id,
            iconName: targetIconName, // Store icon name for diffing
            _iconRefW: oW, _iconRefH: oH, // Reference dims for scale updates
            zIndex: element.zIndex
          });



          if (asyncFabricObj) {
            addToCanvasSorted(canvas, asyncFabricObj, element.zIndex);
            canvas.requestRenderAll();
          }
        }
      });
    };

    switch (element.type) {
      case ELEMENT_TYPES.TEXT:
        const textStyle = printableStyle?.textStyles?.[element.textType] || {};

        // Smart Text Color Resolution
        // IMPORTANT: Prioritize 'color' over 'fill' - AI stores intended color in 'color' field
        // while 'fill' may contain a default value (e.g., #ffffff)
        let textFillColor = element.color || element.fill;

        // DEBUG: Log what color values we're receiving
        // console.log(`🎨 [TEXT_COLOR_DEBUG] Element ${element.id} | color: ${element.color} | fill: ${element.fill} | resolved: ${textFillColor}`);

        // 1. If no explicit color from AI, try theme default for this text type
        if (!textFillColor && textStyle.color) {
          textFillColor = textStyle.color;
          // console.log(`🎨 [TEXT_COLOR_DEBUG] Using theme style color: ${textStyle.color}`);
        }

        // 2. If still no color, fallback to high-contrast against background
        if (!textFillColor) {
          const bg = PAGE.backgroundColor || printableStyle?.PAGEBackground || '#ffffff';
          // Simple brightness check (loose approximation)
          const r = parseInt(bg.substr(1, 2), 16);
          const g = parseInt(bg.substr(3, 2), 16);
          const b = parseInt(bg.substr(5, 2), 16);
          const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
          const fallbackColor = (yiq >= 128) ? '#000000' : '#ffffff';

          console.warn(`[Canvas] ⚠️ Missing text color for ${element.id}, applying high-contrast fallback: ${fallbackColor}`);
          textFillColor = fallbackColor;
        }

        // 3. Final safety check against hardcoded dark gray on dark background
        // If AI returned strictly '#333333' (common default) on a dark background, force white
        if (textFillColor === '#333333') {
          const bg = PAGE.backgroundColor || printableStyle?.PAGEBackground || '#ffffff';
          const r = parseInt(bg.substr(1, 2), 16);
          const g = parseInt(bg.substr(3, 2), 16);
          const b = parseInt(bg.substr(5, 2), 16);
          if (!isNaN(r)) {
            const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
            if (yiq < 100) { // Dark background
              console.warn(`[Canvas] ⚠️ Detected dark gray text on dark background for ${element.id}, forcing white`);
              textFillColor = '#ffffff';
            }
          }
        }

        // 4. Safety: If text sits inside a card/step, check contrast against parent background
        // (post-processor should have handled this, but this is a last-resort safety net)
        if (textFillColor && element.parentBgColor) {
          const pbg = element.parentBgColor;
          try {
            const tr = parseInt(textFillColor.substr(1, 2), 16);
            const tg = parseInt(textFillColor.substr(3, 2), 16);
            const tb = parseInt(textFillColor.substr(5, 2), 16);
            const br = parseInt(pbg.substr(1, 2), 16);
            const bg2 = parseInt(pbg.substr(3, 2), 16);
            const bb = parseInt(pbg.substr(5, 2), 16);
            if (!isNaN(tr) && !isNaN(br)) {
              const dist = Math.sqrt((tr-br)**2 + (tg-bg2)**2 + (tb-bb)**2);
              const tLum = (0.299*tr + 0.587*tg + 0.114*tb) / 255;
              const bLum = (0.299*br + 0.587*bg2 + 0.114*bb) / 255;
              const bothDark = tLum < 0.4 && bLum < 0.4;
              const bothLight = tLum > 0.6 && bLum > 0.6;
              if (dist < 60 || ((bothDark || bothLight) && Math.abs(tLum - bLum) < 0.15)) {
                textFillColor = bLum < 0.5 ? '#ffffff' : '#111827';
                console.warn(`[Canvas] ⚠️ Low contrast text on parent bg for ${element.id}, forcing ${textFillColor}`);
              }
            }
          } catch(e) { /* ignore parse errors */ }
        }

        const textOptions = {
          width: scaledWidth,
          fontSize: (element.fontSize || textStyle.fontSize || 20) * canvasScale,
          fontFamily: element.fontFamily || textStyle.fontFamily || 'Inter, system-ui, sans-serif',
          fontWeight: element.fontWeight || textStyle.fontWeight || '400',
          fill: textFillColor,
          textAlign: element.textAlign || 'left',
          lineHeight: element.lineHeight || 1.4,
          editable: isEditable,
          selectable: isEditable,
          lockScalingX: false,
          lockScalingY: false,
          scaleX: 1, // Reset scale
          scaleY: 1,
          angle: element.rotation || 0, // Apply rotation
          breakWords: true, // Force wrapping
          opacity: element.opacity ?? 1,
        };

        if (!skipLayout) {
          textOptions.left = scaledX;
          textOptions.top = scaledY;
        }

        if (fabricObj && (fabricObj.type === 'textbox' || fabricObj.type === 'text')) {
          // FONT SYNC: React state is authoritative for font changes.
          // AI edits, collaboration sync, and programmatic updates all flow through React state.
          // No Fabric-side font preservation — React state should always be applied.

          fabricObj.set(textOptions);

          // Apply persisted character-level styles (inline bold, italic, color, etc.)
          // Only when not actively editing to avoid conflicts
          if (element.styles && !fabricObj.isEditing) {
            fabricObj.styles = JSON.parse(JSON.stringify(element.styles));
            fabricObj.set('dirty', true);
          }
          // Update content if changed and not editing
          if (element.content !== fabricObj.text && !fabricObj.isEditing) {
            // console.log(`📝 [CANVAS] Updating text content for ${element.id}: "${fabricObj.text?.substring(0, 30)}..." → "${element.content?.substring(0, 30)}..."`);
            fabricObj.set('text', element.content || '');
            fabricObj.set('dirty', true); // Mark dirty to force re-render
          }
        } else {
          if (fabricObj) canvas.remove(fabricObj); // Type mismatch? remove old
          fabricObj = new fabric.Textbox(element.content || 'Click to edit', {
            left: scaledX, top: scaledY, ...textOptions
          });
          // Apply persisted character-level styles to new textbox
          if (element.styles) {
            fabricObj.styles = JSON.parse(JSON.stringify(element.styles));
          }
          addToCanvasSorted(canvas, fabricObj, element.zIndex);
        }
        break;


      case 'group':
        // Handle grouped elements recursively
        if (element.children && element.children.length > 0) {
          console.log(`🧩 [CANVAS] Rendering group ${element.id} with ${element.children.length} children`);

          // Render children first
          // Note: This is simplified. True groups in Fabric should be created by adding objects to a fabric.Group
          // But since our recursive renderElement adds to canvas directly, we need a way to collect them.

          // STRATEGY: 
          // 1. Create a Promise array for children
          // 2. Resolve them to fabric objects (requires changing renderElement to return objects instead of just adding to canvas)
          // 3. BUT renderElement is deeply coupled with side-effects (adding to canvas).

          // ALTERNATE SAFE STRATEGY for this codebase:
          // Treat 'group' as a container passed through from AI but flattened visually if needed,
          // OR implement proper Group support.

          // Given the error "Unknown element type: group", the immediate fix is to NOT CRASH.
          // Let's try to flatten "on the fly" by rendering children individually with offset.

          const parentX = element.x || 0;
          const parentY = element.y || 0;

          // We can't use await inside this sync loop easily if we want to map them.
          // But renderElement is async.

          for (const child of element.children) {
            const childWithOffset = {
              ...child,
              x: parentX + (child.x || 0),
              y: parentY + (child.y || 0),
              zIndex: (element.zIndex || 0) + (child.zIndex || 0) + 1, // ensure children are above group base
              parentId: element.id // Track parent for potential grouping later
            };

            // Recursively render child
            // Note: We await here to ensure order
            await renderElement(childWithOffset, canvas, fabric, renderId);
          }

          // Create a transparent rect for the group container itself so it can be selected/moved as a unit?
          // For now, let's just make sure children render so the chart appears.
          // The chart itself is a child of the group.

          // We can also make a invisible container for the group if needed.
          fabricObj = new fabric.Rect({
            left: scaledX, top: scaledY,
            width: scaledWidth, height: scaledHeight,
            fill: 'transparent',
            stroke: 'transparent',
            selectable: isEditable,
            elementId: element.id,
            zIndex: element.zIndex,
            visible: false // Invisible container
          });

          if (fabricObj) {
            addToCanvasSorted(canvas, fabricObj, element.zIndex);
          }

        } else {
          console.warn(`⚠️ [CANVAS] Empty group ${element.id}`);
        }
        break;

      case ELEMENT_TYPES.IMAGE:
        if (element.src) {
          // Check if we have the originalSrc stored on the fabric object
          const currentSrc = fabricObj?.originalSrc || fabricObj?._element?.src;
          const isSameSource = currentSrc === element.src;

          if (fabricObj && isSameSource) {
            // UPDATE EXISTING — apply element dimensions directly
            if (!skipLayout) {
              const imgW = fabricObj.width || 1;
              const imgH = fabricObj.height || 1;
              const isBackground = element.imageType === 'background';
              if (isBackground) {
                // Cover-fit for backgrounds (fill entire area)
                const coverScale = Math.max(scaledWidth / imgW, scaledHeight / imgH);
                const offsetX = (scaledWidth - imgW * coverScale) / 2;
                const offsetY = (scaledHeight - imgH * coverScale) / 2;
                fabricObj.set({
                  left: scaledX + offsetX,
                  top: scaledY + offsetY,
                  scaleX: coverScale,
                  scaleY: coverScale,
                  opacity: element.opacity ?? 1,
                  selectable: false,
                  evented: false,
                });
              } else {
                // Direct scale for regular images — respects user resize dimensions
                fabricObj.set({
                  left: scaledX,
                  top: scaledY,
                  scaleX: scaledWidth / imgW,
                  scaleY: scaledHeight / imgH,
                  opacity: element.opacity ?? 1,
                });
              }
              fabricObj.setCoords();
            }
          } else {
            // CREATE / RELOAD
            if (fabricObj) {
              canvas.remove(fabricObj);
              fabricObj = null;
            }

            // 1. Check global shared cache first, then local ref cache
            let loadSrc = globalImageCache.get(element.src) || imageCacheRef.current[element.src];

            const loadAndRender = (finalSrc, useCors = true) => {
              const imgOpts = useCors ? { crossOrigin: 'anonymous' } : undefined;
              fabric.Image.fromURL(finalSrc, (img) => {
                if (isDisposedRef.current || !fabricCanvasRef.current) return;
                // Allow late-arriving images if we're still on the same PAGE
                const stillSamePAGE = PAGERef.current?.id === currentPAGEId;
                if (!stillSamePAGE) {
                  console.log(`🚫 [CANVAS] Aborting image load for ${element.id} - PAGE changed`);
                  return;
                }
                // FIX: Recompute positions using CURRENT scale (via ref), not the stale
                // closure-captured canvasScale. On mobile, the initial render may start at
                // scale=1, then scale changes to ~0.42 before the image loads. Without this,
                // images appear at wrong positions (e.g., x=50 instead of x=21).
                const currentScale = scaleRef.current || canvasScale;
                const freshX = element.x * currentScale;
                const freshY = element.y * currentScale;
                const freshW = element.width * currentScale;
                const freshH = element.height * currentScale;
                if (img) {
                  const isBackground = element.imageType === 'background';
                  if (isBackground) {
                    const coverScale = Math.max(freshW / img.width, freshH / img.height);
                    const offsetX = (freshW - img.width * coverScale) / 2;
                    const offsetY = (freshH - img.height * coverScale) / 2;
                    img.set({
                      left: freshX + offsetX,
                      top: freshY + offsetY,
                      scaleX: coverScale,
                      scaleY: coverScale,
                      opacity: element.opacity ?? 1,
                      angle: element.rotation || 0,
                      selectable: false,
                      evented: false,
                    });
                  } else {
                    img.set({
                      left: freshX,
                      top: freshY,
                      scaleX: freshW / img.width,
                      scaleY: freshH / img.height,
                      opacity: element.opacity ?? 1,
                      angle: element.rotation || 0,
                      selectable: isEditable,
                      evented: true,
                    });
                    // Apply rounded corners via clipPath
                    if (element.rx) {
                      img.set({
                        clipPath: new fabric.Rect({
                          width: img.width,
                          height: img.height,
                          rx: element.rx / (freshW / img.width),
                          ry: element.rx / (freshH / img.height),
                          originX: 'center',
                          originY: 'center',
                        }),
                      });
                    }
                    // Apply shadow
                    if (element.shadow) {
                      img.set({
                        shadow: new fabric.Shadow({
                          color: element.shadow.color || 'rgba(0,0,0,0.1)',
                          blur: element.shadow.blur || 10,
                          offsetX: element.shadow.offsetX || 0,
                          offsetY: element.shadow.offsetY || 3,
                        }),
                      });
                    }
                  }
                  img.elementId = element.id;
                  img.originalSrc = element.src;

                  addToCanvasSorted(canvas, img, element.zIndex);
                  fabricObj = img;

                  canvas.requestRenderAll();
                } else if (useCors) {
                  console.warn(`⚠️ [CANVAS] Image load failed with CORS for element ${element.id}, retrying without CORS...`);
                  loadAndRender(finalSrc, false);
                } else {
                  // FIX: Last resort for mobile — load via raw Image() element and wrap in fabric.Image
                  console.warn(`⚠️ [CANVAS] fabric.Image.fromURL failed for ${element.id}, trying raw Image() fallback...`);
                  const rawImg = new Image();
                  rawImg.onload = () => {
                    if (isDisposedRef.current || !fabricCanvasRef.current) return;
                    const stillSame = PAGERef.current?.id === currentPAGEId;
                    if (!stillSame) return;
                    const cs2 = scaleRef.current || canvasScale;
                    const fX = element.x * cs2, fY = element.y * cs2, fW = element.width * cs2, fH = element.height * cs2;
                    try {
                      const fImg = new fabric.Image(rawImg);
                      const isBg = element.imageType === 'background';
                      if (isBg) {
                        const cs = Math.max(fW / fImg.width, fH / fImg.height);
                        fImg.set({ left: fX + (fW - fImg.width * cs) / 2, top: fY + (fH - fImg.height * cs) / 2, scaleX: cs, scaleY: cs, opacity: element.opacity ?? 1, selectable: false, evented: false });
                      } else {
                        fImg.set({ left: fX, top: fY, scaleX: fW / fImg.width, scaleY: fH / fImg.height, opacity: element.opacity ?? 1, selectable: isEditable, evented: true });
                      }
                      fImg.elementId = element.id;
                      fImg.originalSrc = element.src;
                      addToCanvasSorted(canvas, fImg, element.zIndex);
                      canvas.requestRenderAll();
                    } catch (e) {
                      console.error(`❌ [CANVAS] Raw Image fallback failed for ${element.id}:`, e);
                      addPlaceholder(element, canvas, fX, fY, fW, fH);
                    }
                  };
                  rawImg.onerror = () => {
                    console.error(`❌ [CANVAS] FATAL: All image load methods failed for element ${element.id}`);
                    const cs2 = scaleRef.current || canvasScale;
                    addPlaceholder(element, canvas, element.x * cs2, element.y * cs2, element.width * cs2, element.height * cs2);
                  };
                  rawImg.src = finalSrc;
                }
              }, imgOpts);
            };

            if (loadSrc) {
              // Hit cache - sync render (mostly)
              loadAndRender(loadSrc, true);
            } else {
              // Miss - Fetch blob via global cache, then render
              globalImageCache.fetchAndCache(element.src)
                .then(blobUrl => {
                  // Also store in local ref for backward compat
                  imageCacheRef.current[element.src] = blobUrl;
                  loadAndRender(blobUrl, true);
                })
                .catch(err => {
                  console.warn(`⚠️ [CANVAS] Failed to cache image for ${element.id}, falling back to direct URL:`, err);
                  loadAndRender(element.src, false);
                });
            }
          }
        } else {
          console.error(`❌ [CANVAS] Image element ${element.id} missing 'src' property. Rendering placeholder.`);
          const phX = element.x * canvasScale;
          const phY = element.y * canvasScale;
          const phW = (element.width || 200) * canvasScale;
          const phH = (element.height || 150) * canvasScale;
          addPlaceholder(element, canvas, phX, phY, phW, phH);
        }
        break;

        // Helper for Failed Image Placeholder
        function addPlaceholder(element, canvas, x, y, w, h) {
          const rect = new fabric.Rect({
            left: x, top: y, width: w, height: h,
            fill: '#f0f0f0', stroke: '#ccc', strokeWidth: 2,
            selectable: isEditable
          });
          const text = new fabric.Text('Image Not Found', {
            left: x + w / 2, top: y + h / 2,
            fontSize: 16, textAlign: 'center', originX: 'center', originY: 'center',
            fill: '#888', selectable: false
          });
          const group = new fabric.Group([rect, text], {
            left: x, top: y, selectable: isEditable,
            elementId: element.id // Ensure we track it
          });
          addToCanvasSorted(canvas, group, element.zIndex);
        }



      case ELEMENT_TYPES.SHAPE:
        // Common shape properties
        const shapeFill = element.fill || '#3B82F6';
        const shapeStroke = element.stroke === 'none' ? null : (element.stroke || '#1E40AF');
        const shapeStrokeWidth = shapeStroke ? (element.strokeWidth || 2) : 0;

        // Helper to generate polygon points for regular polygons
        const generatePolygonPoints = (cx, cy, r, sides) => {
          const angle = (2 * Math.PI) / sides;
          const points = [];
          for (let i = 0; i < sides; i++) {
            const x = cx + r * Math.sin(i * angle - Math.PI / 2);
            const y = cy - r * Math.cos(i * angle - Math.PI / 2);
            points.push({ x, y });
          }
          return points;
        };

        // Helper to generate star points
        const generateStarPoints = (cx, cy, outerR, innerR, numPoints) => {
          const angle = Math.PI / numPoints;
          const points = [];
          for (let i = 0; i < 2 * numPoints; i++) {
            const r = i % 2 === 0 ? outerR : innerR;
            const x = cx + r * Math.sin(i * angle);
            const y = cy - r * Math.cos(i * angle);
            points.push({ x, y });
          }
          return points;
        };

        // Shape-specific rendering
        const shapeType = element.shapeType;

        // Complex shapes list
        const complexShapes = ['arrow', 'block_arrow', 'chevron', 'pentagon_arrow', 'polygon', 'star',
          'triangle', 'triangle_right', 'diamond', 'parallelogram', 'trapezoid',
          'callout_rect', 'callout_rounded', 'callout_cloud', 'ellipse', 'square', 'rectangle_rounded'];

        if (complexShapes.includes(shapeType)) {
          // For complex shapes, try to update in-place if possible
          // Only recreate if dimensions changed or object doesn't exist
          const needsRecreation = !fabricObj ||
            (fabricObj._elementWidth !== scaledWidth) ||
            (fabricObj._elementHeight !== scaledHeight);

          if (fabricObj && !needsRecreation) {
            // UPDATE IN-PLACE: Update ONLY styling and rotation
            // DO NOT update position (left/top) - for rotated polygons, the Fabric coordinate
            // system differs from our stored x/y. The position is controlled by user interaction.
            fabricObj.set({
              angle: element.rotation || 0,
              fill: shapeFill,
              stroke: shapeStroke,
              strokeWidth: shapeStrokeWidth,
            });
            fabricObj.setCoords();
            break; // Skip recreation, we're done
          }

          // Remove existing object if we need to recreate
          if (fabricObj) {
            canvas.remove(fabricObj);
            fabricObj = null;
          }

          const cx = scaledWidth / 2;
          const cy = scaledHeight / 2;
          const r = Math.min(scaledWidth, scaledHeight) / 2;
          let points = [];
          let pathData = '';

          switch (shapeType) {
            case 'arrow':
              // Simple arrow line with head
              const arrowLine = new fabric.Line([0, scaledHeight / 2, scaledWidth - 15, scaledHeight / 2], {
                stroke: shapeStroke || shapeFill,
                strokeWidth: element.strokeWidth || 3,
                strokeDashArray: element.strokeDashArray || null,
              });
              const arrowHead = new fabric.Triangle({
                left: scaledWidth - 15,
                top: 0,
                width: 15,
                height: scaledHeight,
                fill: shapeStroke || shapeFill,
                angle: 90,
                originX: 'center',
                originY: 'center',
              });
              arrowHead.set({ left: scaledWidth, top: scaledHeight / 2 });
              fabricObj = new fabric.Group([arrowLine, arrowHead], {
                left: scaledX, top: scaledY,
                selectable: isEditable,
                angle: element.rotation || 0,
                elementId: element.id,
                zIndex: element.zIndex
              });
              break;

            case 'block_arrow':
              const dir = element.direction || 'right';
              if (dir === 'right') {
                points = [
                  { x: 0, y: scaledHeight * 0.25 },
                  { x: scaledWidth * 0.6, y: scaledHeight * 0.25 },
                  { x: scaledWidth * 0.6, y: 0 },
                  { x: scaledWidth, y: scaledHeight * 0.5 },
                  { x: scaledWidth * 0.6, y: scaledHeight },
                  { x: scaledWidth * 0.6, y: scaledHeight * 0.75 },
                  { x: 0, y: scaledHeight * 0.75 },
                ];
              } else if (dir === 'left') {
                points = [
                  { x: scaledWidth, y: scaledHeight * 0.25 },
                  { x: scaledWidth * 0.4, y: scaledHeight * 0.25 },
                  { x: scaledWidth * 0.4, y: 0 },
                  { x: 0, y: scaledHeight * 0.5 },
                  { x: scaledWidth * 0.4, y: scaledHeight },
                  { x: scaledWidth * 0.4, y: scaledHeight * 0.75 },
                  { x: scaledWidth, y: scaledHeight * 0.75 },
                ];
              } else if (dir === 'up') {
                points = [
                  { x: scaledWidth * 0.25, y: scaledHeight },
                  { x: scaledWidth * 0.25, y: scaledHeight * 0.4 },
                  { x: 0, y: scaledHeight * 0.4 },
                  { x: scaledWidth * 0.5, y: 0 },
                  { x: scaledWidth, y: scaledHeight * 0.4 },
                  { x: scaledWidth * 0.75, y: scaledHeight * 0.4 },
                  { x: scaledWidth * 0.75, y: scaledHeight },
                ];
              } else if (dir === 'down') {
                points = [
                  { x: scaledWidth * 0.25, y: 0 },
                  { x: scaledWidth * 0.25, y: scaledHeight * 0.6 },
                  { x: 0, y: scaledHeight * 0.6 },
                  { x: scaledWidth * 0.5, y: scaledHeight },
                  { x: scaledWidth, y: scaledHeight * 0.6 },
                  { x: scaledWidth * 0.75, y: scaledHeight * 0.6 },
                  { x: scaledWidth * 0.75, y: 0 },
                ];
              }
              fabricObj = new fabric.Polygon(points, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'chevron':
              points = [
                { x: 0, y: 0 },
                { x: scaledWidth * 0.7, y: 0 },
                { x: scaledWidth, y: scaledHeight * 0.5 },
                { x: scaledWidth * 0.7, y: scaledHeight },
                { x: 0, y: scaledHeight },
                { x: scaledWidth * 0.3, y: scaledHeight * 0.5 },
              ];
              fabricObj = new fabric.Polygon(points, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'pentagon_arrow':
              points = [
                { x: 0, y: scaledHeight * 0.15 },
                { x: scaledWidth * 0.75, y: scaledHeight * 0.15 },
                { x: scaledWidth, y: scaledHeight * 0.5 },
                { x: scaledWidth * 0.75, y: scaledHeight * 0.85 },
                { x: 0, y: scaledHeight * 0.85 },
              ];
              fabricObj = new fabric.Polygon(points, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'polygon':
              const sides = element.sides || 6;
              points = generatePolygonPoints(cx, cy, r, sides);
              fabricObj = new fabric.Polygon(points, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'star':
              const starPoints = element.points || 5;
              const outerR = r;
              const innerR = r * 0.4;
              points = generateStarPoints(cx, cy, outerR, innerR, starPoints);
              fabricObj = new fabric.Polygon(points, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'triangle':
              points = [
                { x: scaledWidth / 2, y: 0 },
                { x: scaledWidth, y: scaledHeight },
                { x: 0, y: scaledHeight },
              ];
              fabricObj = new fabric.Polygon(points, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'triangle_right':
              points = [
                { x: 0, y: 0 },
                { x: scaledWidth, y: scaledHeight },
                { x: 0, y: scaledHeight },
              ];
              fabricObj = new fabric.Polygon(points, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'diamond':
              points = [
                { x: scaledWidth / 2, y: 0 },
                { x: scaledWidth, y: scaledHeight / 2 },
                { x: scaledWidth / 2, y: scaledHeight },
                { x: 0, y: scaledHeight / 2 },
              ];
              fabricObj = new fabric.Polygon(points, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'parallelogram':
              const offset = scaledWidth * 0.2;
              points = [
                { x: offset, y: 0 },
                { x: scaledWidth, y: 0 },
                { x: scaledWidth - offset, y: scaledHeight },
                { x: 0, y: scaledHeight },
              ];
              fabricObj = new fabric.Polygon(points, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'trapezoid':
              const topInset = scaledWidth * 0.15;
              points = [
                { x: topInset, y: 0 },
                { x: scaledWidth - topInset, y: 0 },
                { x: scaledWidth, y: scaledHeight },
                { x: 0, y: scaledHeight },
              ];
              fabricObj = new fabric.Polygon(points, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'ellipse':
              fabricObj = new fabric.Ellipse({
                left: scaledX, top: scaledY,
                rx: scaledWidth / 2, ry: scaledHeight / 2,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'square':
              const squareSize = Math.min(scaledWidth, scaledHeight);
              fabricObj = new fabric.Rect({
                left: scaledX, top: scaledY,
                width: squareSize, height: squareSize,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'rectangle_rounded':
              const borderRad = (element.borderRadius || 12) * scale;
              fabricObj = new fabric.Rect({
                left: scaledX, top: scaledY,
                width: scaledWidth, height: scaledHeight,
                rx: borderRad, ry: borderRad,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                opacity: element.opacity ?? 1,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'callout_rect':
              // Rectangle with speech bubble tail
              pathData = `M 0 0 L ${scaledWidth} 0 L ${scaledWidth} ${scaledHeight * 0.7} L ${scaledWidth * 0.4} ${scaledHeight * 0.7} L ${scaledWidth * 0.25} ${scaledHeight} L ${scaledWidth * 0.25} ${scaledHeight * 0.7} L 0 ${scaledHeight * 0.7} Z`;
              fabricObj = new fabric.Path(pathData, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'callout_rounded':
              const cr = 10 * scale;
              pathData = `M ${cr} 0 L ${scaledWidth - cr} 0 Q ${scaledWidth} 0 ${scaledWidth} ${cr} L ${scaledWidth} ${scaledHeight * 0.6 - cr} Q ${scaledWidth} ${scaledHeight * 0.6} ${scaledWidth - cr} ${scaledHeight * 0.6} L ${scaledWidth * 0.4} ${scaledHeight * 0.6} L ${scaledWidth * 0.25} ${scaledHeight} L ${scaledWidth * 0.25} ${scaledHeight * 0.6} L ${cr} ${scaledHeight * 0.6} Q 0 ${scaledHeight * 0.6} 0 ${scaledHeight * 0.6 - cr} L 0 ${cr} Q 0 0 ${cr} 0 Z`;
              fabricObj = new fabric.Path(pathData, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            case 'callout_cloud':
              // Simplified cloud callout path
              pathData = `M ${scaledWidth * 0.25} ${scaledHeight * 0.75} Q ${scaledWidth * 0.05} ${scaledHeight * 0.75} ${scaledWidth * 0.05} ${scaledHeight * 0.5} Q ${scaledWidth * 0.05} ${scaledHeight * 0.25} ${scaledWidth * 0.25} ${scaledHeight * 0.15} Q ${scaledWidth * 0.25} 0 ${scaledWidth * 0.5} 0 Q ${scaledWidth * 0.75} 0 ${scaledWidth * 0.75} ${scaledHeight * 0.15} Q ${scaledWidth * 0.95} ${scaledHeight * 0.25} ${scaledWidth * 0.95} ${scaledHeight * 0.5} Q ${scaledWidth * 0.95} ${scaledHeight * 0.75} ${scaledWidth * 0.75} ${scaledHeight * 0.75} L ${scaledWidth * 0.4} ${scaledHeight * 0.75} L ${scaledWidth * 0.3} ${scaledHeight} L ${scaledWidth * 0.3} ${scaledHeight * 0.75} Z`;
              fabricObj = new fabric.Path(pathData, {
                left: scaledX, top: scaledY,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
                angle: element.rotation || 0,
              });
              break;

            default:
              // Fallback to rectangle for unknown complex shapes
              fabricObj = new fabric.Rect({
                left: scaledX, top: scaledY,
                width: scaledWidth, height: scaledHeight,
                fill: shapeFill, stroke: shapeStroke, strokeWidth: shapeStrokeWidth,
                selectable: isEditable, elementId: element.id, zIndex: element.zIndex,
              });
          }

          if (fabricObj) {
            // Store dimensions for in-place update detection
            fabricObj._elementWidth = scaledWidth;
            fabricObj._elementHeight = scaledHeight;

            // Apply stored scale factors (from previous resize)
            if (element.scaleX !== undefined && element.scaleX !== 1) {
              fabricObj.set({ scaleX: element.scaleX });
            }
            if (element.scaleY !== undefined && element.scaleY !== 1) {
              fabricObj.set({ scaleY: element.scaleY });
            }
            fabricObj.setCoords();

            addToCanvasSorted(canvas, fabricObj, element.zIndex);
          }
        } else {
          // Simple shapes: rectangle, circle, line (support update)
          const shapeOptions = {
            elementId: element.id,
            width: scaledWidth,
            height: scaledHeight,
            scaleX: 1,
            scaleY: 1,
            angle: element.rotation || 0,
            fill: shapeFill,
            stroke: shapeStroke,
            strokeWidth: shapeStrokeWidth,
            strokeDashArray: element.strokeDashArray || null,
            opacity: element.opacity ?? 1,
            zIndex: element.zIndex,
          };

          if (shapeType === 'rectangle') {
            shapeOptions.rx = (element.rx || element.borderRadius || 0) * scale;
            shapeOptions.ry = (element.ry || element.rx || element.borderRadius || 0) * scale;
          } else if (shapeType === 'circle') {
            shapeOptions.radius = Math.min(scaledWidth, scaledHeight) / 2;
          }

          if (!skipLayout) {
            shapeOptions.left = scaledX;
            shapeOptions.top = scaledY;
          }

          if (fabricObj) {
            fabricObj.set(shapeOptions);
          } else {
            if (shapeType === 'rectangle') {
              fabricObj = new fabric.Rect({ left: scaledX, top: scaledY, ...shapeOptions, selectable: isEditable });
            } else if (shapeType === 'circle') {
              fabricObj = new fabric.Circle({ left: scaledX, top: scaledY, ...shapeOptions, selectable: isEditable });
            } else if (shapeType === 'line') {
              fabricObj = new fabric.Line([scaledX, scaledY, scaledX + scaledWidth, scaledY + (element.strokeWidth || 2)], {
                ...shapeOptions,
                fill: null,
                stroke: shapeStroke || shapeFill,
                selectable: isEditable
              });
            } else {
              // Fallback for unknown shapes (e.g. 'accent_line')
              // Default to Rectangle so it renders *something* instead of crashing/warning
              fabricObj = new fabric.Rect({ left: scaledX, top: scaledY, ...shapeOptions, selectable: isEditable });
            }

            if (fabricObj) addToCanvasSorted(canvas, fabricObj, element.zIndex);
          }
        }
        break;


      case ELEMENT_TYPES.CHART:
        // Interactive Chart.js charts using fabric.Chart
        if (fabricModule.Chart && element.chartConfig) {
          // FULL REPLACEMENT STRATEGY: When chart config changes, destroy the old
          // fabric.Chart entirely and create a fresh one. This avoids Chart.js internal
          // diffing issues that cause partial data updates (some datasets/labels update
          // but others retain stale values).
          // NOTE: This check runs OUTSIDE skipLayout to ensure data always syncs
          // even if the chart element is currently selected/being dragged.
          if (fabricObj && JSON.stringify(fabricObj._chartConfig) !== JSON.stringify(element.chartConfig)) {
            console.log('📊 [CANVAS] Chart config changed — FULL RECREATION for clean state:', element.id);
            // Dispose Chart.js instance to free resources
            if (typeof fabricObj.dispose === 'function') fabricObj.dispose();
            canvas.remove(fabricObj);
            fabricObj = null; // Fall through to CREATE NEW path below
          }

          if (fabricObj) {
            // SAME CONFIG — just update position/size if not being dragged
            if (!skipLayout) {
              fabricObj.set({
                left: scaledX,
                top: scaledY,
                width: scaledWidth,
                height: scaledHeight,
                selectable: isEditable,
              });
            }
            fabricObj.setCoords();
          } else {
            // CREATE NEW (initial render or after config-change recreation)
            fabricObj = new fabricModule.Chart({
              left: scaledX,
              top: scaledY,
              width: scaledWidth,
              height: scaledHeight,
              chart: {
                type: element.chartConfig.type,
                data: element.chartConfig.data,
                options: {
                  ...element.chartConfig.options,
                  responsive: false,
                  maintainAspectRatio: false,
                  animation: false,
                }
              },
              selectable: isEditable,
              elementId: element.id,
              zIndex: element.zIndex,
            });
            // Deep clone for future diffing — prevents Chart.js mutation interference
            fabricObj._chartConfig = JSON.parse(JSON.stringify(element.chartConfig));
            addToCanvasSorted(canvas, fabricObj, element.zIndex);
            console.log(`📊 [CANVAS] Created interactive chart: ${element.id}`);

            // Force re-render after Chart.js initialization to catch any async painting
            setTimeout(() => {
              if (fabricObj && canvas) {
                fabricObj.dirty = true;
                canvas.requestRenderAll();
              }
            }, 150);
          }
        } else if (element.chartConfig) {
          // Fallback: If fabric.Chart not available, log warning
          console.warn(`⚠️ [CANVAS] fabric.Chart not available for element ${element.id}`);
        }
        break;

      case ELEMENT_TYPES.ICON:
        // Icons are Paths. Recreate if iconName changes, otherwise update props.
        // Paths are hard to update geometric data. Recreating is safer for Icons.

        // FIX: Skip position updates if user is currently interacting with this icon
        // This prevents the "snap-back" issue during drag operations
        if (skipLayout && fabricObj) {
          // Just update coords without recreating - user is dragging
          fabricObj.setCoords();
          break;
        }

        // Check if icon name changed - only recreate if necessary
        const currentIconName = fabricObj?.iconName;
        const newIconName = element.iconName || element.resolvedIconName || element.name || element.icon;

        if (fabricObj && currentIconName === newIconName) {
          // Same icon - update props (Scale, Color, Position)
          if (!skipLayout) {
            const targetColor = element.fill || element.color || '#000000';

            applyColorToObjects(fabricObj, targetColor);

            // Restore border (group-level stroke) if set in element data
            if (element.stroke) {
              fabricObj.set('stroke', element.stroke);
              if (element.strokeWidth) {
                fabricObj.set('strokeWidth', element.strokeWidth);
              }
            }

            // Recompute scaleX/scaleY using stored reference dimensions
            const refW = fabricObj._iconRefW || fabricObj.width || 24;
            const refH = fabricObj._iconRefH || fabricObj.height || 24;
            let sX, sY;
            if (element.width && element.height) {
              sX = (element.width * canvasScale) / refW;
              sY = (element.height * canvasScale) / refH;
            } else {
              const iSize = (element.size || 24) * canvasScale;
              sX = iSize / refW;
              sY = iSize / refH;
            }

            fabricObj.set({
              left: scaledX,
              top: scaledY,
              scaleX: sX,
              scaleY: sY,
              opacity: element.opacity ?? 1,
              dirty: true,
              objectCaching: false
            });

            canvas.requestRenderAll();
          }
          break;
        }

        // Icon changed or doesn't exist - recreate
        if (fabricObj) {
          canvas.remove(fabricObj);
          fabricObj = null;
        }

        const iconSize = (element.size || 24) * scale;

        // FIX: Also check 'name' and 'icon' properties which are used by AI-generated JSON
        const iconName = element.iconName || element.resolvedIconName || element.name || element.icon;
        let cachedPath = null;
        // console.log(`[CANVAS] Element ${element.id} iconName: ${iconName}`);

        // ── S3 svgSrc detection (used to decide priority order) ──
        // Icons saved to S3 have svgSrc with presigned AWS URL.
        // We MUST check S3 BEFORE mapIconToPath() because mapIconToPath() fires
        // background Iconify API fetches as a side-effect even for saved icons.
        const hasValidSvgSrc = element.svgSrc && (element.svgSrc.startsWith('http') || element.svgSrc.startsWith('s3://'));
        const svgUrlLower = (element.svgSrc || '').toLowerCase();
        const iconNameLower = (iconName || '').toLowerCase().replace(/[^a-z0-9-]/g, '');
        const isStaleCircleFallback = hasValidSvgSrc && svgUrlLower.includes('/circle.svg') && iconNameLower && iconNameLower !== 'circle';

        // PRIORITY 1: Check Local In-Memory Cache (fastest, no network)
        // Only check cache if NO valid S3 URL, or if S3 URL is stale circle fallback
        // This prevents mapIconToPath from firing Iconify fetches when S3 data is available
        if (iconName && (!hasValidSvgSrc || isStaleCircleFallback)) {
          const { path, svg, name, isPlaceholder } = mapIconToPath(iconName);
          // mapIconToPath returns default circle path if not found, we need to know if it's a REAL cache hit
          // FIX: Also check isPlaceholder flag - if true, icon is not yet loaded, don't use circle
          if ((path || svg) && name !== 'circle' && !isPlaceholder) {
            cachedPath = path;
            // CHECK FOR SVG CONTENT
            if (svg) {
              cachedPath = null; // Fix race condition
              fabric.loadSVGFromString(svg, (objects, options) => {
                // Allow late-arriving icons if still on same PAGE
                if (PAGERef.current?.id !== currentPAGEId) return;
                if (!objects || !objects.length) return;

                const svgGroup = fabric.util.groupSVGElements(objects, options);

                // Scale Logic for Group
                // FIX: Use the ACTUAL bounds of the loaded content (svgGroup.width) rather than the SVG Viewbox (options.width)
                // This prevents "Giant Icon" issues where viewbox is small (24) but paths are huge (1000+)
                const originalW = svgGroup.width || options.width || 24;
                const originalH = svgGroup.height || options.height || 24;

                let sX, sY;
                if (element.width && element.height) {
                  sX = (element.width * scale) / originalW;
                  sY = (element.height * scale) / originalH;
                } else {
                  const iSize = (element.size || 24) * scale;
                  sX = iSize / originalW;
                  sY = iSize / originalH;
                }

                // Helper to modify SVG deeply (recursive)
                const applyColorToObjects = (objects, color) => {
                  objects.forEach(obj => {
                    if (!obj) return;

                    if (obj.type === 'group' && obj.getObjects) {
                      applyColorToObjects(obj.getObjects(), color);
                    } else if (['path', 'rect', 'polygon', 'circle', 'ellipse', 'line', 'polyline'].includes(obj.type)) {

                      const hasVisibleStroke = obj.stroke && obj.stroke !== 'none' && obj.stroke !== 'transparent' && (obj.strokeWidth && obj.strokeWidth > 0);
                      const hasFill = obj.fill && obj.fill !== 'none' && obj.fill !== 'transparent';

                      if (hasFill) {
                        // Change fill — leave stroke alone to preserve border colors
                        obj.set({ fill: color });
                      } else if (hasVisibleStroke) {
                        // Outline-only path — stroke IS the visual color
                        obj.set({ stroke: color });
                      } else {
                        // Default to FILL for shapes
                        obj.set({ fill: color });
                        if (!obj.stroke || obj.stroke === 'none') {
                          obj.set({ stroke: 'transparent', strokeWidth: 0 });
                        }
                      }
                    }
                  });
                };

                // Apply Color deeply
                // FIX: Also check 'color' property which is used by AI-generated JSON
                const color = element.fill || element.color || '#000000';
                // console.log(`[CANVAS] Applying color ${color} to icon ${iconName}`);

                const objectsToStyle = svgGroup.getObjects ? svgGroup.getObjects() : [svgGroup];
                applyColorToObjects(objectsToStyle, color);

                // Force group update
                if (svgGroup.type === 'group') {
                  svgGroup.addWithUpdate();
                  svgGroup.dirty = true;
                  svgGroup.objectCaching = false;
                }

                svgGroup.set({
                  left: scaledX, top: scaledY,
                  scaleX: sX, scaleY: sY,
                  selectable: isEditable,
                  elementId: element.id,
                  iconName: newIconName, // Store icon name for diffing
                  _iconRefW: originalW, _iconRefH: originalH, // Reference dims for scale updates
                  zIndex: element.zIndex, // Store Z-Index
                  opacity: element.opacity ?? 1,
                  originX: 'left', originY: 'top',
                });

                addToCanvasSorted(canvas, svgGroup, element.zIndex);

                canvas.requestRenderAll();
              });
              // Skip sync path handling since we are handling via SVG
              cachedPath = null;
            }
          }
        } else if (iconName && hasValidSvgSrc && !isStaleCircleFallback) {
          // S3 URL exists — check in-memory cache WITHOUT triggering Iconify fetch
          const normalized = iconName.toLowerCase().trim().replace(/[^a-z0-9:-]/g, '');
          if (ICON_PATHS[normalized]) {
            cachedPath = ICON_PATHS[normalized];
          }
        }

        // console.log(`[CANVAS] Decision state for ${iconName}:`, { cachedPath: !!cachedPath, hasSvgSrc: hasValidSvgSrc });

        if (cachedPath) {
          // RENDER FROM CACHE (Legacy Path)
          try {
            // Calculate scale
            const oW = 24; const oH = 24;
            let sX, sY;
            if (element.width && element.height) {
              sX = (element.width * scale) / oW;
              sY = (element.height * scale) / oH;
            } else {
              const iSize = (element.size || 24) * scale;
              sX = iSize / oW;
              sY = iSize / oH;
            }

            fabricObj = new fabric.Path(cachedPath, {
              left: scaledX,
              top: scaledY,
              fill: 'none',
              stroke: element.fill || element.color || '#000000',
              strokeWidth: 1.5,
              scaleX: sX,
              scaleY: sY,
              selectable: isEditable,
              elementId: element.id, // CRITICAL: Required for diffing logic
              iconName: newIconName, // Store icon name for diffing
              _iconRefW: oW, _iconRefH: oH, // Reference dims for scale updates
              opacity: element.opacity ?? 1,
              originX: 'left',
              originY: 'top',
            });
            if (fabricObj) addToCanvasSorted(canvas, fabricObj, element.zIndex);
          } catch (err) {
            console.error(`❌ [CANVAS] FATAL: Failed to render cached path for ${iconName}`, err);
          }
        }
        else if (hasValidSvgSrc && !isStaleCircleFallback) {
          // PRIORITY 2: Load from S3 (saved icon with presigned URL — NO Iconify call)
          const svgUrl = element.svgSrc;
          // console.log(`[CANVAS] Loading icon ${iconName} from S3: ${svgUrl.substring(0, 80)}...`);

          try {
            // FIX: Use fetch() to get SVG text, cache it, then render via loadSVGFromString
            // This prevents repeated S3 requests on every page change
            fetch(svgUrl)
              .then(response => {
                if (!response.ok) throw new Error(`S3 fetch failed: ${response.status}`);
                return response.text();
              })
              .then(svgText => {
                // Allow late-arriving icons if still on same PAGE
                if (PAGERef.current?.id !== currentPAGEId) return;
                if (!fabricCanvasRef.current) return;

                // Cache the SVG text so next render hits Priority 1 (in-memory cache)
                if (iconName) {
                  cacheIconSVG(iconName, svgText);
                }

                fabric.loadSVGFromString(svgText, (objects, options) => {
                  if (PAGERef.current?.id !== currentPAGEId) return;
                  if (!fabricCanvasRef.current) return;

                  if (!objects || objects.length === 0) {
                    console.warn(`[CANVAS] S3 SVG parse returned empty for ${iconName}, falling back to Iconify`);
                    if (iconName) renderAsyncIcon(iconName, renderId);
                    return;
                  }

                  const svgGroup = fabric.util.groupSVGElements(objects, options);
                  const originalW = svgGroup.width || options.width || 24;
                  const originalH = svgGroup.height || options.height || 24;
                  let sX, sY;
                  if (element.width && element.height) {
                    sX = (element.width * scale) / originalW;
                    sY = (element.height * scale) / originalH;
                  } else {
                    const iSize = (element.size || 24) * scale;
                    sX = iSize / originalW;
                    sY = iSize / originalH;
                  }

                  // Apply color from element.fill or element.color (AI JSON uses color)
                  const color = element.fill || element.color || '#000000';
                  const objectsToStyle = svgGroup.getObjects ? svgGroup.getObjects() : [svgGroup];
                  objectsToStyle.forEach(obj => {
                    // For Lucide-style stroke icons
                    if (obj.stroke && obj.stroke !== 'none') {
                      obj.set({ stroke: color });
                    }
                    // For filled icons
                    if (obj.fill && obj.fill !== 'none' && obj.fill !== '') {
                      obj.set({ fill: color });
                    }
                    // Fallback: if path has no fill or stroke set, apply stroke (common for line icons)
                    if ((!obj.fill || obj.fill === 'none' || obj.fill === '') && (!obj.stroke || obj.stroke === 'none')) {
                      obj.set({ stroke: color, strokeWidth: 1.5 });
                    }
                  });

                  svgGroup.set({
                    left: scaledX,
                    top: scaledY,
                    scaleX: sX,
                    scaleY: sY,
                    selectable: isEditable,
                    originX: 'left',
                    originY: 'top',
                    elementId: element.id,
                    iconName: newIconName, // Store icon name for diffing
                    _iconRefW: originalW, _iconRefH: originalH, // Reference dims for scale updates
                    zIndex: element.zIndex, // Store zIndex on the object
                    opacity: element.opacity ?? 1,
                  });
                  addToCanvasSorted(canvas, svgGroup, element.zIndex);
                  canvas.renderAll();
                });
              })
              .catch(err => {
                console.warn(`[CANVAS] S3 fetch failed for ${svgUrl}, falling back to Iconify`, err.message);
                if (iconName) renderAsyncIcon(iconName, renderId);
              });
          } catch (err) {
            console.error(`❌ [CANVAS] S3 Load Failed: ${svgUrl}, falling back`, err);
            if (iconName) renderAsyncIcon(iconName, renderId);
          }
        } else if (isStaleCircleFallback) {
          // S3 has stale circle.svg but icon should be something else — fetch from Iconify
          // console.log(`[CANVAS] Skipping stale S3 URL (circle.svg) for icon ${iconName}, using Iconify instead`);
          if (iconName) renderAsyncIcon(iconName, renderId);
        } else if (iconName) {
          // PRIORITY 3: Fetch from Iconify (Fallback - new icons without S3 URL)
          renderAsyncIcon(iconName, renderId);
        } else {
          console.warn(`⚠️ [CANVAS] Icon element ${element.id} missing 'iconName' or 'resolvedIconName'.`);
        }
        break;

      case ELEMENT_TYPES.SVG_DIAGRAM: {
        // Full-slot inline SVG diagram (org charts, process flows, infographics).
        if (fabricObj) {
          canvas.remove(fabricObj);
          fabricObj = null;
        }

        const rawSvg = (element.svgContent && typeof element.svgContent === 'string') ? element.svgContent : '';
        const accentColor = element.fillColor || element.fill || element.color || '#3B82F6';

        if (!rawSvg) {
          const phRect = new fabric.Rect({
            width: scaledWidth,
            height: scaledHeight,
            fill: '#EEF2FF',
            stroke: '#6366F1',
            strokeDashArray: [6, 4],
            strokeWidth: 1,
            rx: 8,
            ry: 8,
            originX: 'left',
            originY: 'top',
          });
          const phText = new fabric.Text('Generating diagram…', {
            fontSize: 16 * canvasScale,
            fill: '#4338CA',
            fontFamily: 'Inter, Arial, sans-serif',
            fontWeight: '600',
            originX: 'center',
            originY: 'center',
            left: scaledWidth / 2,
            top: scaledHeight / 2 - 12,
          });
          const phSub = new fabric.Text('Double-click to open the AI Diagram modal', {
            fontSize: 11 * canvasScale,
            fill: '#6366F1',
            fontFamily: 'Inter, Arial, sans-serif',
            originX: 'center',
            originY: 'center',
            left: scaledWidth / 2,
            top: scaledHeight / 2 + 12,
          });
          fabricObj = new fabric.Group([phRect, phText, phSub], {
            left: scaledX,
            top: scaledY,
            selectable: isEditable,
            elementId: element.id,
            zIndex: element.zIndex,
            originX: 'left',
            originY: 'top',
          });
          addToCanvasSorted(canvas, fabricObj, element.zIndex);
          break;
        }

        const themedSvg = preprocessSvgForFabric(rawSvg).replace(/currentColor/g, accentColor);

        // PRIMARY render path: encode the SVG as a data URL and let the browser's
        // native SVG renderer paint it into a fabric.Image. This handles every SVG
        // feature (markers, gradients, classes, masks, clipPaths, filters, …) with
        // pixel-perfect accuracy. Fabric's own SVG parser silently drops elements
        // when it encounters features it doesn't fully understand, which leaves
        // complex LLM-generated diagrams partially rendered. Diagrams are now
        // edited via the AI Diagram modal (regenerate-in-place), not by breaking
        // them into individual fabric objects.
        const renderViaDataUrl = () => {
          try {
            const encoded = encodeURIComponent(themedSvg)
              .replace(/'/g, '%27')
              .replace(/"/g, '%22');
            const dataUrl = `data:image/svg+xml;charset=utf-8,${encoded}`;
            fabric.Image.fromURL(
              dataUrl,
              (img) => {
                if (!img) {
                  renderSvgFallback('Image.fromURL returned null');
                  canvas.requestRenderAll();
                  return;
                }
                if (!img.width || !img.height) {
                  console.warn(`⚠️ [CANVAS] svg_diagram ${element.id} loaded with 0 intrinsic size (w=${img.width}, h=${img.height}) — using fallback`);
                  renderSvgFallback('SVG loaded with 0 intrinsic dimensions');
                  canvas.requestRenderAll();
                  return;
                }
                const origW = img.width;
                const origH = img.height;
                img.set({
                  left: scaledX,
                  top: scaledY,
                  scaleX: scaledWidth / origW,
                  scaleY: scaledHeight / origH,
                  selectable: isEditable,
                  originX: 'left',
                  originY: 'top',
                  elementId: element.id,
                  zIndex: element.zIndex,
                  opacity: element.opacity ?? 1,
                });
                fabricObj = img;
                addToCanvasSorted(canvas, img, element.zIndex);
                canvas.requestRenderAll();
              },
              { crossOrigin: 'anonymous' }
            );
            return true;
          } catch (err) {
            console.error(`❌ [CANVAS] svg_diagram data-URL render failed for ${element.id}:`, err);
            return false;
          }
        };

        const renderSvgFallback = (reason) => {
          const phRect = new fabric.Rect({
            width: scaledWidth,
            height: scaledHeight,
            fill: '#FEF2F2',
            stroke: '#F43F5E',
            strokeDashArray: [6, 4],
            strokeWidth: 1,
            rx: 8,
            ry: 8,
            originX: 'left',
            originY: 'top',
          });
          const phText = new fabric.Text('Diagram failed to render — double-click to regenerate', {
            fontSize: 12 * canvasScale,
            fill: '#9F1239',
            fontFamily: 'Arial',
            originX: 'center',
            originY: 'center',
            left: scaledWidth / 2,
            top: scaledHeight / 2,
            textAlign: 'center',
          });
          fabricObj = new fabric.Group([phRect, phText], {
            left: scaledX,
            top: scaledY,
            selectable: isEditable,
            elementId: element.id,
            zIndex: element.zIndex,
            originX: 'left',
            originY: 'top',
          });
          addToCanvasSorted(canvas, fabricObj, element.zIndex);
          if (reason) console.warn(`⚠️ [CANVAS] svg_diagram fallback for ${element.id}: ${reason}`);
        };

        try {
          // PRIMARY: browser-native SVG render via data URL.
          if (renderViaDataUrl()) break;

          // FALLBACK: fabric's own SVG parser (limited — drops markers, sometimes
          // partial-renders complex SVGs — but kept for offline / CSP-restricted setups).
          fabric.loadSVGFromString(themedSvg, (objects, options) => {
            if (!objects || !objects.length) {
              renderSvgFallback('parse returned no objects');
              canvas.requestRenderAll();
              return;
            }
            const svgGroup = fabric.util.groupSVGElements(objects, options);
            const origW = options.width || svgGroup.width || scaledWidth;
            const origH = options.height || svgGroup.height || scaledHeight;
            svgGroup.set({
              left: scaledX,
              top: scaledY,
              scaleX: scaledWidth / origW,
              scaleY: scaledHeight / origH,
              selectable: isEditable,
              originX: 'left',
              originY: 'top',
              elementId: element.id,
              zIndex: element.zIndex,
              opacity: element.opacity ?? 1,
            });
            fabricObj = svgGroup;
            addToCanvasSorted(canvas, svgGroup, element.zIndex);
            canvas.requestRenderAll();
          });
        } catch (err) {
          console.error(`❌ [CANVAS] svg_diagram render failed for ${element.id}:`, err);
          renderSvgFallback(err && err.message ? err.message : 'render exception');
          canvas.requestRenderAll();
        }
        break;
      }

      case ELEMENT_TYPES.IMAGE_PLACEHOLDER:
        // Render as a placeholder rectangle (image generation in progress)
        if (fabricObj) {
          canvas.remove(fabricObj);
          fabricObj = null;
        }

        // Create a group with a gray rectangle and "loading" text
        const placeholderRect = new fabric.Rect({
          width: scaledWidth,
          height: scaledHeight,
          fill: '#94a3b8',
          rx: element.rx || 8,
          ry: element.rx || 8,
          originX: 'left',
          originY: 'top',
        });

        const placeholderText = new fabric.Text('Generating image...', {
          fontSize: 14 * canvasScale,
          fill: '#f1f5f9',
          fontFamily: 'Arial',
          originX: 'center',
          originY: 'center',
          left: scaledWidth / 2,
          top: scaledHeight / 2,
        });

        fabricObj = new fabric.Group([placeholderRect, placeholderText], {
          left: scaledX,
          top: scaledY,
          selectable: isEditable,
        });

        addToCanvasSorted(canvas, fabricObj, element.zIndex);
        console.log(`🖼️ [CANVAS] Rendered image_placeholder: ${element.id}`);
        break;

      case ELEMENT_TYPES.TABLE:
        // Table element using custom fabric.Table class
        console.log(`📊 [CANVAS] TABLE case hit for element: ${element.id}`, {
          hasFabricTable: !!fabricModule.Table,
          hasTableConfig: !!element.tableConfig,
          tableConfig: element.tableConfig
        });
        if (fabricModule.Table && element.tableConfig) {
          const tableConfig = element.tableConfig;

          if (fabricObj) {
            // UPDATE EXISTING: Just update position if dragging
            if (!skipLayout) {
              fabricObj.set({
                left: scaledX,
                top: scaledY,
                scaleX: scaledWidth / (tableConfig.cols * tableConfig.cellWidth),
                scaleY: scaledHeight / (tableConfig.rows * tableConfig.cellHeight),
              });
              fabricObj.setCoords();
            }
          } else {
            // CREATE NEW: Create fabric.Table
            try {
              fabricObj = new fabricModule.Table([], {
                ...tableConfig,
                left: scaledX,
                top: scaledY,
                scaleX: scaledWidth / (tableConfig.cols * tableConfig.cellWidth),
                scaleY: scaledHeight / (tableConfig.rows * tableConfig.cellHeight),
                selectable: isEditable,
                elementId: element.id,
                zIndex: element.zIndex,
              });

              if (fabricObj) {
                addToCanvasSorted(canvas, fabricObj, element.zIndex);
                console.log(`📊 [CANVAS] Rendered table: ${element.id} (${tableConfig.cols}×${tableConfig.rows})`);
              }
            } catch (tableError) {
              console.error(`❌ [CANVAS] Failed to create table ${element.id}:`, tableError);
            }
          }
        } else {
          console.warn(`⚠️ [CANVAS] fabric.Table not available or missing tableConfig for ${element.id}`);
        }
        break;

      case ELEMENT_TYPES.VIDEO:
        console.log(`🎥 [DEBUG] Video processing started for ${element.id}`, element);

        // ROBUST: Auto-detect YouTube/Vimeo/Loom/Spotify even if videoType is missing (handles legacy data/paste)
        let isExternalVideo = element.videoType === 'youtube' || element.videoType === 'vimeo' || element.videoType === 'loom' || element.videoType === 'spotify';
        // Recorded videos should also use overlay-based playback (click to play)
        let isRecordedVideo = element.videoType === 'recorded';

        // Safety Check: If no videoType, regex the src URL
        if (!isExternalVideo && !isRecordedVideo && element.src && typeof element.src === 'string') {
          if (element.src.match(/youtu\.?be/i)) {
            element.videoType = 'youtube';
            isExternalVideo = true;
          } else if (element.src.match(/vimeo\.com/i)) {
            element.videoType = 'vimeo';
            isExternalVideo = true;
          } else if (element.src.match(/loom\.com/i)) {
            element.videoType = 'loom';
            isExternalVideo = true;
          } else if (element.src.match(/spotify\.com/i)) {
            element.videoType = 'spotify';
            isExternalVideo = true;
          } else if (element.src.startsWith('data:video/')) {
            element.videoType = 'recorded';
            isRecordedVideo = true;
          }
        }

        // HANDLE EXTERNAL/RECORDED VIDEOS - Render as Static Thumbnail/Placeholder Group
        if (isExternalVideo || isRecordedVideo) {
          if (fabricObj && fabricObj.type === 'group' && fabricObj.videoType === element.videoType) {
            // Already rendered as group, just update position
            if (!skipLayout) {
              fabricObj.set({
                left: scaledX,
                top: scaledY,
                scaleX: (element.width * canvasScale) / fabricObj.width,
                scaleY: (element.height * canvasScale) / fabricObj.height,
                angle: element.rotation || 0,
              });
              fabricObj.setCoords();
            }
          } else {
            console.log(`🎥 [DEBUG] Rendering external video thumbnail for ${element.id}`);
            if (fabricObj) canvas.remove(fabricObj);

            const safeLoadImage = (url, onLoad, onError) => {
              console.log(`🖼️ [THUMBNAIL] Attempting to load: ${url}`);
              const img = new Image();
              img.crossOrigin = 'anonymous';
              img.onload = () => {
                console.log(`✅ [THUMBNAIL] Successfully loaded: ${url}`);
                onLoad(img);
              };
              img.onerror = (e) => {
                console.error(`❌ [THUMBNAIL] Failed to load: ${url}`, e);
                onError(e);
              };
              img.src = url;
            };

            const createGroup = (img) => {
              if (!fabricCanvasRef.current) return;

              // Wrap HTML Image in Fabric Image
              const fImg = new fabricModule.Image(img);

              // Initial dimensions based on element or default
              const width = element.width * canvasScale;
              const height = element.height * canvasScale;

              // Inset thumbnail to match video overlay (15px padding)
              const PADDING = 15;
              const innerWidth = width - (PADDING * 2);
              const innerHeight = height - (PADDING * 2);

              // Transparent container to define full selection area
              const container = new fabricModule.Rect({
                width: width,
                height: height,
                fill: 'transparent',
                originX: 'center',
                originY: 'center',
              });

              // Scale image to fit INNER area
              fImg.set({
                originX: 'center',
                originY: 'center',
                scaleX: innerWidth / fImg.width,
                scaleY: innerHeight / fImg.height
              });

              // Create Play Icon Overlay
              const circle = new fabricModule.Circle({
                radius: 30 * canvasScale,
                fill: 'rgba(0,0,0,0.6)',
                originX: 'center',
                originY: 'center'
              });

              const triangle = new fabricModule.Triangle({
                width: 20 * canvasScale,
                height: 20 * canvasScale,
                fill: '#ffffff',
                angle: 90,
                originX: 'center',
                originY: 'center',
                left: 2 * canvasScale
              });

              const group = new fabricModule.Group([container, fImg, circle, triangle], {
                left: scaledX,
                top: scaledY,
                width: width,
                height: height,
                originX: 'left',
                originY: 'top',
                selectable: isEditable,
                elementId: element.id,
                videoType: element.videoType,
                zIndex: element.zIndex
              });

              fabricObj = group;
              addToCanvasSorted(canvas, fabricObj, element.zIndex);
              console.log(`✅ [THUMBNAIL] Group created and added for ${element.id}`);
            };

            // Chain of fallback URLs
            const primaryUrl = element.thumbnail;
            // Different fallback for recorded videos vs external
            const fallbackUrl = isRecordedVideo
              ? 'https://placehold.co/600x400/1E3A8A/FFFFFF.png?text=🎥+Recorded+Video'
              : 'https://placehold.co/600x400/333333/FFFFFF.png?text=Video+Source';

            console.log(`🎥 [THUMBNAIL] Primary URL: ${primaryUrl}, Element:`, element);

            // Attempt to load primary -> fallback
            if (primaryUrl) {
              safeLoadImage(primaryUrl,
                (img) => createGroup(img),
                () => {
                  console.warn(`⚠️ [CANVAS] Failed to load video thumbnail: ${primaryUrl}, trying fallback.`);
                  // Try fallback logic for YouTube (maxres -> hqdefault)
                  if (element.videoType === 'youtube' && primaryUrl.includes('maxresdefault')) {
                    const hqUrl = primaryUrl.replace('maxresdefault', 'hqdefault');
                    safeLoadImage(hqUrl,
                      (img2) => createGroup(img2),
                      () => {
                        // Final fallback
                        safeLoadImage(fallbackUrl, (img3) => createGroup(img3), () => { });
                      }
                    );
                  } else {
                    // Direct fallback to placeholder
                    safeLoadImage(fallbackUrl, (img2) => createGroup(img2), () => { });
                  }
                }
              );
            } else {
              console.warn(`⚠️ [THUMBNAIL] No primary URL, using fallback`);
              safeLoadImage(fallbackUrl, (img) => createGroup(img), () => { });
            }
          }
          break; // EXIT HERE for external videos
        }

        // HANDLE LOCAL VIDEOS (Existing Logic)
        if (Platform.OS === 'web') {
          // Check if we already have this video object
          if (fabricObj && fabricObj.type === 'image' && fabricObj.getElement()?.tagName === 'VIDEO') {
            const videoEl = fabricObj.getElement();
            if (videoEl.src !== element.src) {
              videoEl.src = element.src;
            }
            // Update positioning
            if (!skipLayout) {
              // Use video's intrinsic dimensions for proper scaling
              // Fallback to 560 (typical video size) if metadata not loaded yet
              const videoWidth = videoEl.videoWidth || 560;
              const videoHeight = videoEl.videoHeight || 560;
              const targetWidth = element.width * canvasScale;
              const targetHeight = element.height * canvasScale;

              console.log(`🎥 [UPDATE_EXISTING] Video ${element.id} alignment debug:`, {
                elementDimensions: { width: element.width, height: element.height },
                elementPosition: { x: element.x, y: element.y },
                videoIntrinsic: { width: videoWidth, height: videoHeight },
                canvasScale: canvasScale,
                scaledPosition: { x: scaledX, y: scaledY },
                targetDimensions: { width: targetWidth, height: targetHeight },
                calculatedScale: { x: targetWidth / videoWidth, y: targetHeight / videoHeight },
                fabricObjBefore: {
                  width: fabricObj.width,
                  height: fabricObj.height,
                  scaleX: fabricObj.scaleX,
                  scaleY: fabricObj.scaleY,
                  left: fabricObj.left,
                  top: fabricObj.top,
                  originX: fabricObj.originX,
                  originY: fabricObj.originY
                }
              });

              fabricObj.set({
                left: scaledX,
                top: scaledY,
                width: videoWidth,
                height: videoHeight,
                scaleX: targetWidth / videoWidth,
                scaleY: targetHeight / videoHeight,
                angle: element.rotation || 0,
                originX: 'left',
                originY: 'top'
              });
              fabricObj.setCoords();

              console.log(`🎥 [UPDATE_EXISTING] After update:`, {
                fabricObj: {
                  width: fabricObj.width,
                  height: fabricObj.height,
                  scaleX: fabricObj.scaleX,
                  scaleY: fabricObj.scaleY,
                  left: fabricObj.left,
                  top: fabricObj.top,
                  originX: fabricObj.originX,
                  originY: fabricObj.originY
                },
                boundingRect: fabricObj.getBoundingRect()
              });

              // Ensure video is playing and loop is running
              if (videoEl && videoEl.paused) {
                console.log(`🎥 [DEBUG] Restarting video playback for existing element ${element.id}`);
                videoEl.play().catch(e => console.warn('Autoplay restart prevented:', e));
              }
              // Restart render loop if it exists
              if (fabricObj.renderLoop) {
                requestAnimationFrame(fabricObj.renderLoop);
              }
            }
          } else {
            console.log(`🎥 [DEBUG] Creating NEW video fabric object for ${element.id}`);
            // Create new video object
            if (fabricObj) canvas.remove(fabricObj);

            // Create video element
            const videoEl = document.createElement('video');
            videoEl.src = element.src;
            videoEl.crossOrigin = 'anonymous';
            videoEl.muted = true; // Auto-play usually requires muted
            videoEl.loop = true;
            videoEl.autoplay = true;
            // DO NOT set videoEl.width/height - let it use intrinsic dimensions
            // Fabric will handle all scaling via scaleX/scaleY
            videoEl.playsInline = true; // For mobile web

            // Trigger load to ensure metadata is available
            console.log(`🎥 [DEBUG] Loading video src: ${element.src.substring(0, 50)}...`);

            videoEl.addEventListener('loadedmetadata', () => {
              console.log(`🎥 [METADATA] Video loadedmetadata: ${videoEl.videoWidth}x${videoEl.videoHeight}, duration: ${videoEl.duration}`);

              if (videoFabricObj && videoEl.videoWidth && videoEl.videoHeight) {
                // Determine target dimensions (scaled to canvas)
                const targetWidth = element.width * canvasScale;
                const targetHeight = element.height * canvasScale;

                console.log(`🎥 [METADATA] Updating video ${element.id} with real dimensions:`, {
                  videoIntrinsic: { width: videoEl.videoWidth, height: videoEl.videoHeight },
                  elementDimensions: { width: element.width, height: element.height },
                  targetDimensions: { width: targetWidth, height: targetHeight },
                  calculatedScale: { x: targetWidth / videoEl.videoWidth, y: targetHeight / videoEl.videoHeight },
                  fabricObjBefore: {
                    width: videoFabricObj.width,
                    height: videoFabricObj.height,
                    scaleX: videoFabricObj.scaleX,
                    scaleY: videoFabricObj.scaleY
                  }
                });

                // Set the Fabric Object to use the Full Video resolution (no cropping)
                videoFabricObj.set({
                  width: videoEl.videoWidth,
                  height: videoEl.videoHeight,
                  // Scale it down/up to fit the element's box
                  scaleX: targetWidth / videoEl.videoWidth,
                  scaleY: targetHeight / videoEl.videoHeight,
                  left: scaledX,
                  top: scaledY,
                  originX: 'left',
                  originY: 'top'
                });
                videoFabricObj.setCoords();

                console.log(`🎥 [METADATA] After metadata update:`, {
                  fabricObj: {
                    width: videoFabricObj.width,
                    height: videoFabricObj.height,
                    scaleX: videoFabricObj.scaleX,
                    scaleY: videoFabricObj.scaleY,
                    left: videoFabricObj.left,
                    top: videoFabricObj.top
                  },
                  boundingRect: videoFabricObj.getBoundingRect()
                });

                canvas.requestRenderAll();
              }
            });
            videoEl.addEventListener('canplay', () => console.log(`🎥 [DEBUG] Video canplay event`));
            videoEl.addEventListener('playing', () => console.log(`🎥 [DEBUG] Video playing event`));
            videoEl.addEventListener('error', (e) => console.error(`🎥 [DEBUG] Video error event:`, e, videoEl.error));
            videoEl.load();

            // Wait for video to be ready before rendering to avoid empty frame
            // But don't block the UI - Fabric handles element loading generally well
            // CRITICAL: Use FIXED placeholder matching typical video intrinsic size (560x560)
            // Using element.width/height causes mismatch with video intrinsic dimensions
            // loadedmetadata handler will correct this once video loads
            const initialWidth = 560;  // Typical intrinsic video width
            const initialHeight = 560; // Typical intrinsic video height

            // CRITICAL: Set video element dimensions - Fabric needs this to render!
            // Without width/height on the video element, Fabric renders nothing
            videoEl.width = initialWidth;
            videoEl.height = initialHeight;

            const targetWidth = element.width * canvasScale;
            const targetHeight = element.height * canvasScale;

            console.log(`🎥 [CREATE_NEW] Creating video ${element.id} with initial dimensions:`, {
              elementDimensions: { width: element.width, height: element.height },
              elementPosition: { x: element.x, y: element.y },
              initialDimensions: { width: initialWidth, height: initialHeight },
              canvasScale: canvasScale,
              scaledPosition: { x: scaledX, y: scaledY },
              targetDimensions: { width: targetWidth, height: targetHeight },
              calculatedScale: { x: targetWidth / initialWidth, y: targetHeight / initialHeight },
              videoElDimensions: { width: videoEl.width, height: videoEl.height }
            });

            const videoFabricObj = new fabricModule.Image(videoEl, {
              left: scaledX,
              top: scaledY,
              originX: 'left',
              originY: 'top',
              width: initialWidth,
              height: initialHeight,
              scaleX: targetWidth / initialWidth,
              scaleY: targetHeight / initialHeight,
              objectCaching: false, // Essential for video playback updates
              angle: element.rotation || 0,
            });

            // Override type for identification
            videoFabricObj.type = 'image';
            videoFabricObj.elementId = element.id;

            console.log(`🎥 [CREATE_NEW] After constructor:`, {
              fabricObj: {
                width: videoFabricObj.width,
                height: videoFabricObj.height,
                scaleX: videoFabricObj.scaleX,
                scaleY: videoFabricObj.scaleY,
                left: videoFabricObj.left,
                top: videoFabricObj.top,
                originX: videoFabricObj.originX,
                originY: videoFabricObj.originY
              },
              boundingRect: videoFabricObj.getBoundingRect()
            });

            // Start playing immediately
            console.log(`🎥 [DEBUG] Attempting to play video ${element.id}`);
            videoEl.play().catch(e => console.warn('Autoplay prevented:', e));

            // Setup continuous rendering for video playback
            // Fabric needs to re-render every frame to show video progress
            const renderLoop = () => {
              // Safety check: Stop loop if canvas is disposed or context is missing
              if (!canvas || !canvas.getElement() || !canvas.contextContainer) return;

              if (videoEl && !videoEl.paused && !videoEl.ended) {
                videoFabricObj.dirty = true;
                canvas.requestRenderAll();
                requestAnimationFrame(renderLoop);
              }
            };

            // Attach loop to object so we can restart it later
            videoFabricObj.renderLoop = renderLoop;

            videoEl.onplay = () => {
              requestAnimationFrame(renderLoop);
            };

            fabricObj = videoFabricObj;
            addToCanvasSorted(canvas, fabricObj, element.zIndex);

            // Start render loop IMMEDIATELY after adding to canvas
            // Don't wait for onplay - video might already be playing
            requestAnimationFrame(renderLoop);

            console.log(`🎥 [CANVAS] Rendered video: ${element.id}`);
          }
        } else {
          console.warn('Video rendering not supported on native yet');
        }
        break;

      // ===================== EMBED ELEMENTS =====================
      case ELEMENT_TYPES.EMBED:
        console.log(`🔗 [EMBED] Processing embed element: ${element.id}`);
        if (fabricObj) {
          // Update existing embed placeholder
          if (!skipLayout) {
            fabricObj.set({
              left: scaledX,
              top: scaledY,
              scaleX: (element.width * canvasScale) / fabricObj.width,
              scaleY: (element.height * canvasScale) / fabricObj.height,
              angle: element.rotation || 0,
            });
            fabricObj.setCoords();
          }
        } else {
          // Create embed placeholder (static reprintable in edit mode)
          const embedWidth = element.width * canvasScale;
          const embedHeight = element.height * canvasScale;

          // Background rect
          const bgRect = new fabricModule.Rect({
            width: embedWidth,
            height: embedHeight,
            fill: '#F3F4F6',
            stroke: '#D1D5DB',
            strokeWidth: 2,
            rx: 8,
            ry: 8,
            originX: 'center',
            originY: 'center',
          });

          // Provider icon/text
          const providerText = new fabricModule.Text(element.provider || 'Embed', {
            fontSize: 14 * canvasScale,
            fontFamily: 'Inter, sans-serif',
            fill: '#6B7280',
            originX: 'center',
            originY: 'center',
            top: -embedHeight / 4,
          });

          // Title text
          const titleText = new fabricModule.Text(element.title || element.src || 'Embedded Content', {
            fontSize: 16 * canvasScale,
            fontFamily: 'Inter, sans-serif',
            fontWeight: '600',
            fill: '#374151',
            originX: 'center',
            originY: 'center',
            top: 10,
          });

          // Link icon placeholder
          const linkIcon = new fabricModule.Text('🔗', {
            fontSize: 24 * canvasScale,
            originX: 'center',
            originY: 'center',
            top: embedHeight / 4,
          });

          fabricObj = new fabricModule.Group([bgRect, providerText, titleText, linkIcon], {
            left: scaledX,
            top: scaledY,
            selectable: isEditable,
            elementId: element.id,
            zIndex: element.zIndex,
            embedType: element.embedType,
          });

          addToCanvasSorted(canvas, fabricObj, element.zIndex);
          console.log(`🔗 [EMBED] Rendered embed: ${element.id} (${element.provider})`);
        }
        break;

      // ===================== BUTTON ELEMENTS =====================
      case ELEMENT_TYPES.BUTTON:
        console.log(`🔘 [BUTTON] Processing button element: ${element.id}`);
        if (fabricObj) {
          // Update existing button
          if (!skipLayout) {
            fabricObj.set({
              left: scaledX,
              top: scaledY,
              angle: element.rotation || 0,
            });
            fabricObj.setCoords();
          }
        } else {
          // Create button (Rect + Text group)
          const btnWidth = (element.width || 160) * canvasScale;
          const btnHeight = (element.height || 48) * canvasScale;

          const buttonColors = {
            primary: { bg: '#2563EB', text: '#FFFFFF', border: '#2563EB' },
            secondary: { bg: '#E5E7EB', text: '#1F2937', border: '#D1D5DB' },
            ghost: { bg: 'transparent', text: '#2563EB', border: '#2563EB' },
          };
          const colors = buttonColors[element.style] || buttonColors.primary;

          const btnRect = new fabricModule.Rect({
            width: btnWidth,
            height: btnHeight,
            fill: colors.bg,
            stroke: colors.border,
            strokeWidth: 2,
            rx: 8,
            ry: 8,
            originX: 'center',
            originY: 'center',
          });

          const btnText = new fabricModule.Text(element.label || 'Button', {
            fontSize: 14 * canvasScale,
            fontFamily: 'Inter, sans-serif',
            fontWeight: '600',
            fill: colors.text,
            originX: 'center',
            originY: 'center',
          });

          fabricObj = new fabricModule.Group([btnRect, btnText], {
            left: scaledX,
            top: scaledY,
            selectable: isEditable,
            elementId: element.id,
            zIndex: element.zIndex,
            buttonUrl: element.url, // Store URL for click handling
          });

          addToCanvasSorted(canvas, fabricObj, element.zIndex);
          console.log(`🔘 [BUTTON] Rendered button: ${element.id} (${element.label})`);
        }
        break;

      // ===================== ANIMATION ELEMENTS (Live Video to Canvas) =====================
      case ELEMENT_TYPES.ANIMATION:
        console.log(`🎬 [ANIMATION] Processing animation element: ${element.id}`, element);

        if (!element.videoSrc) {
          console.warn(`⚠️ [ANIMATION] No videoSrc found for element ${element.id}`);
          break;
        }

        const animWidth = element.width * canvasScale;
        const animHeight = element.height * canvasScale;

        if (fabricObj && fabricObj.isAnimation) {
          // Update existing animation object position
          if (!skipLayout) {
            fabricObj.set({
              left: scaledX,
              top: scaledY,
              scaleX: animWidth / (fabricObj.width || 1),
              scaleY: animHeight / (fabricObj.height || 1),
              angle: element.rotation || 0,
            });
            fabricObj.setCoords();
          }
        } else {
          // Create new animation object with live video streaming
          if (fabricObj) canvas.remove(fabricObj);

          // Stop any existing animation for this element
          if (animationIntervalsRef.current.has(element.id)) {
            const existing = animationIntervalsRef.current.get(element.id);
            if (existing.rafId) cancelAnimationFrame(existing.rafId);
            if (existing.video) {
              existing.video.pause();
              existing.video.src = '';
            }
            animationIntervalsRef.current.delete(element.id);
          }

          // Capture element data for async operations
          const animElementId = element.id;
          const animZIndex = element.zIndex;
          const animIsPlaying = element.isPlaying !== false;
          const animLoop = element.loop !== false;
          const videoSrc = element.videoSrc;

          // Create hidden video element
          const video = document.createElement('video');
          video.src = videoSrc;
          video.muted = true;
          video.loop = animLoop;
          video.playsInline = true;
          video.crossOrigin = 'anonymous';
          video.style.display = 'none';
          document.body.appendChild(video);

          // Create a temp canvas to draw video frames
          const tempCanvas = document.createElement('canvas');
          tempCanvas.width = element.width;
          tempCanvas.height = element.height;
          const tempCtx = tempCanvas.getContext('2d');

          video.onloadeddata = () => {
            if (!fabricCanvasRef.current) {
              video.remove();
              return;
            }

            // Draw first frame
            tempCtx.drawImage(video, 0, 0, tempCanvas.width, tempCanvas.height);
            const dataUrl = tempCanvas.toDataURL('image/jpeg', 0.8);

            fabricModule.Image.fromURL(dataUrl, (img) => {
              if (!fabricCanvasRef.current) {
                video.remove();
                return;
              }

              img.set({
                left: scaledX,
                top: scaledY,
                originX: 'left',
                originY: 'top',
                scaleX: animWidth / img.width,
                scaleY: animHeight / img.height,
                selectable: isEditable,
                angle: element.rotation || 0,
              });

              // Custom properties
              img.elementId = animElementId;
              img.zIndex = animZIndex;
              img.isAnimation = true;

              addToCanvasSorted(fabricCanvasRef.current, img, animZIndex);
              console.log(`🎬 [ANIMATION] Created live video animation: ${animElementId}`);

              // Start video playback and frame streaming
              if (animIsPlaying) {
                video.play().catch(e => console.warn('Video autoplay blocked:', e));

                // Use requestAnimationFrame to continuously update the fabric image
                let rafId;
                const updateFrame = () => {
                  if (!fabricCanvasRef.current || !video || video.paused) {
                    return;
                  }

                  // Draw current video frame
                  tempCtx.drawImage(video, 0, 0, tempCanvas.width, tempCanvas.height);
                  const frameUrl = tempCanvas.toDataURL('image/jpeg', 0.7);

                  img.setSrc(frameUrl, () => {
                    if (fabricCanvasRef.current) {
                      fabricCanvasRef.current.requestRenderAll();
                    }
                  }, { crossOrigin: 'anonymous' });

                  rafId = requestAnimationFrame(updateFrame);
                };

                rafId = requestAnimationFrame(updateFrame);

                // Store references for cleanup
                animationIntervalsRef.current.set(animElementId, {
                  video,
                  tempCanvas,
                  rafId,
                  img
                });

                console.log(`🎬 [ANIMATION] Started live video playback for ${animElementId}`);
              }
            }, { crossOrigin: 'anonymous' });
          };

          video.onerror = () => {
            console.error(`🎬 [ANIMATION] Failed to load video for ${animElementId}`);
            video.remove();
          };
        }
        break;

      default:
        console.warn(`⚠️ [CANVAS] Unknown element type: ${element.type} for element ${element.id}`);
        break;
    }

    if (fabricObj) {
      fabricObj.elementId = element.id; // Ensure ID is attached
      fabricObj.zIndex = element.zIndex; // Store Z-Index for sorting
      if (!skipLayout) {
        fabricObj.set({ angle: element.rotation || 0 });
        fabricObj.setCoords();
      }

      // select if needed
      if (element.id === selectedElementId && !canvas.getActiveObject()) {
        canvas.setActiveObject(fabricObj);
      }
    } else if (
      (element.type !== ELEMENT_TYPES.SHAPE || element.shapeType !== 'arrow') &&
      element.type !== ELEMENT_TYPES.ICON &&
      element.type !== ELEMENT_TYPES.IMAGE &&
      element.type !== ELEMENT_TYPES.VIDEO &&
      element.type !== ELEMENT_TYPES.ANIMATION &&
      element.type !== ELEMENT_TYPES.SVG_DIAGRAM
    ) {
      // Arrows are handled via groups. Icons/Images/Videos/Animations/SvgDiagrams
      // are async or complex, so fabricObj might be null here initially.
      console.warn(`⚠️ [CANVAS] Element ${element.id} (${element.type}) resulted in NULL fabric object.`);
    }
  };

  // Helper to get next highest Z-Index
  const getNextZIndex = useCallback(() => {
    if (!PAGE?.elements || PAGE.elements.length === 0) return 1;
    const maxZ = Math.max(...PAGE.elements.map(e => parseInt(e.zIndex) || 0));
    return maxZ + 1;
  }, [PAGE?.elements]);

  // Local handlers
  const handleAddText = useCallback((textType = 'body', content = '', position = {}) => {
    console.log('[printableCanvas] Adding text:', textType);

    // Capture snapshot before adding element
    if (handlersRef.current.capturePreEditSnapshot) {
      handlersRef.current.capturePreEditSnapshot();
    }

    const newElement = {
      type: ELEMENT_TYPES.TEXT,
      textType,
      content,
      x: position.x || 50,
      y: position.y || 50,
      width: position.width || 400,
      height: position.height || 100,
      zIndex: getNextZIndex(),
    };
    if (onAddElement) {
      onAddElement(PAGE.id, ELEMENT_TYPES.TEXT, newElement);
    } else {
      console.error('[printableCanvas] onAddElement prop is missing');
    }
  }, [PAGE, onAddElement, getNextZIndex]);

  // Generic add element dispatcher for toolbar
  const handleAddElement = useCallback((type, options = {}) => {
    if (type === 'text') {
      handleAddText('body', '', options);
    }
    // Other types like image, shape are handled by their specific buttons or dropdowns
  }, [handleAddText]);

  const handleAddImage = useCallback((src = '', position = {}) => {
    console.log('[printableCanvas] Adding image:', src);

    // Capture snapshot before adding element
    if (handlersRef.current.capturePreEditSnapshot) {
      handlersRef.current.capturePreEditSnapshot();
    }

    const newElement = {
      type: ELEMENT_TYPES.IMAGE,
      src,
      x: position.x || 50,
      y: position.y || 50,
      width: position.width || 300,
      height: position.height || 200,
      zIndex: getNextZIndex(),
      isUserMedia: true, // Mark as user media for AI preservation
    };
    if (onAddElement) {
      onAddElement(PAGE.id, ELEMENT_TYPES.IMAGE, newElement);
    } else {
      console.error('[printableCanvas] onAddElement prop is missing');
    }
  }, [PAGE, onAddElement, getNextZIndex]);

  const handleAddShape = useCallback((shapeConfig = 'rectangle', position = {}) => {
    // Support both simple shapeType string and full fabricData object from ShapesPickerModal
    const isConfigObject = typeof shapeConfig === 'object';
    const shapeType = isConfigObject ? shapeConfig.shapeType : shapeConfig;
    const shapeOptions = isConfigObject ? shapeConfig : {};

    console.log('[printableCanvas] Adding shape:', shapeType, shapeOptions);

    // Capture snapshot before adding element
    if (handlersRef.current.capturePreEditSnapshot) {
      handlersRef.current.capturePreEditSnapshot();
    }

    // Determine default dimensions based on shape type
    let defaultWidth = 200;
    let defaultHeight = 100;

    // Lines should be wider
    if (shapeType === 'line' || shapeType === 'arrow') {
      defaultWidth = 200;
      defaultHeight = 4;
    }
    // Circles and stars should be square
    else if (['circle', 'square', 'star', 'polygon'].includes(shapeType)) {
      defaultWidth = 120;
      defaultHeight = 120;
    }
    // Block arrows need more height
    else if (shapeType === 'block_arrow' || shapeType === 'chevron') {
      defaultWidth = 160;
      defaultHeight = 80;
    }
    // Callouts
    else if (shapeType.startsWith('callout')) {
      defaultWidth = 200;
      defaultHeight = 120;
    }

    const newElement = {
      type: ELEMENT_TYPES.SHAPE,
      shapeType,
      // Include extended shape options (sides, points, direction, subType, etc.)
      ...(shapeOptions.sides && { sides: shapeOptions.sides }),
      ...(shapeOptions.points && { points: shapeOptions.points }),
      ...(shapeOptions.direction && { direction: shapeOptions.direction }),
      ...(shapeOptions.subType && { subType: shapeOptions.subType }),
      ...(shapeOptions.strokeDashArray && { strokeDashArray: shapeOptions.strokeDashArray }),
      ...(shapeOptions.borderRadius !== undefined && { borderRadius: shapeOptions.borderRadius }),
      x: position.x || 50,
      y: position.y || 50,
      width: position.width || defaultWidth,
      height: position.height || defaultHeight,
      zIndex: getNextZIndex(),
    };

    if (onAddElement) {
      onAddElement(PAGE.id, ELEMENT_TYPES.SHAPE, newElement);
    } else {
      console.error('[printableCanvas] onAddElement prop is missing');
    }

  }, [PAGE, onAddElement, getNextZIndex]);


  // Handle Icon Insertion from Modal
  const handleInsertIcon = useCallback((iconName) => {
    // console.log('[printableCanvas] Inserting selected icon:', iconName);
    setShowIconPicker(false);

    // Capture snapshot
    if (handlersRef.current.capturePreEditSnapshot) {
      handlersRef.current.capturePreEditSnapshot();
    }

    // Determine best color based on User Rule:
    // "parse the object you will see an object of typ icon and then extract from tht pbjects its color , the first icon u see return color , if none found in object list then retun black color ."
    let bestColor = '#000000';

    // Find ONLY the first icon (User request: "the first icon u see")
    const firstIcon = PAGE?.elements?.find(e => e.type === ELEMENT_TYPES.ICON);

    if (firstIcon) {
      // Check fill, then stroke, then 'color' property just in case
      if (firstIcon.fill && firstIcon.fill !== 'none' && firstIcon.fill !== 'transparent') bestColor = firstIcon.fill;
      else if (firstIcon.stroke && firstIcon.stroke !== 'none') bestColor = firstIcon.stroke;
      else if (firstIcon.color) bestColor = firstIcon.color;
    } else {
      // Only fallback to textPrimary if clearly defined, else strictly Black as requested
      // "if none found in object list then retun black color"
      // fallback to textPrimary MIGHT be what they want if no icons exist, but they said "return black".
      // However, if textPrimary is dark (e.g. #111827), it's close enough to black but "richer".
      // Let's stick to true black #000000 if that's the strict request, or maybe printableStyle.textPrimary if available?
      // User said: "return black color". I will strict default to #000000.
      bestColor = '#000000';
    }

    const newElement = {
      type: ELEMENT_TYPES.ICON,
      iconName: iconName,
      x: PAGE_WIDTH / 2 - 24, // Center
      y: PAGE_HEIGHT / 2 - 24,
      size: 48,
      fill: bestColor,
      zIndex: getNextZIndex(),
    };

    if (onAddElement) {
      onAddElement(PAGE.id, ELEMENT_TYPES.ICON, newElement);
    }
  }, [PAGE, onAddElement, getNextZIndex, printableStyle]);

  const handleDeleteSelected = useCallback(() => {
    if (selectedElementId) {
      // Capture snapshot before delete
      if (handlersRef.current.capturePreEditSnapshot) {
        handlersRef.current.capturePreEditSnapshot();
      }
      onDeleteElement(PAGE.id, selectedElementId);
      // Commit history
      if (handlersRef.current.saveToHistory) {
        handlersRef.current.saveToHistory();
      }
    }
  }, [PAGE, selectedElementId, onDeleteElement]);

  const handleZoomIn = useCallback(() => setCanvasScale(prev => Math.min(prev + 0.1, 2)), []);
  const handleZoomOut = useCallback(() => setCanvasScale(prev => Math.max(prev - 0.1, 0.5)), []);
  const handleResetZoom = useCallback(() => setCanvasScale(1), []);

  const handleToDataURL = useCallback(() => {
    if (fabricCanvasRef.current) {
      try {
        return fabricCanvasRef.current.toDataURL({
          format: 'png',
          quality: 1,
          multiplier: 2,
        });
      } catch (err) {
        console.warn('Failed to export canvas to data URL (likely tainted):', err);
        return null;
      }
    }
    return null;
  }, []);

  const handleToJSON = useCallback(() => {
    if (fabricCanvasRef.current) {
      return fabricCanvasRef.current.toJSON();
    }
    return null;
  }, []);

  // Image file picker handler
  const handleImageFileSelect = useCallback((event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const base64 = e.target.result;
      console.log('[printableCanvas] Image loaded from file');

      // Add image to canvas directly via Fabric
      if (fabricCanvasRef.current && typeof fabric !== 'undefined') {
        fabricModule.Image.fromURL(base64, (img) => {
          if (img) {
            // Scale image to fit reasonably on canvas
            const maxSize = 400;
            const scale = Math.min(maxSize / img.width, maxSize / img.height, 1);
            img.set({
              left: 100,
              top: 100,
              scaleX: scale,
              scaleY: scale,
              selectable: true,
            });
            // fabricCanvasRef.current.add(img); // Removed manual add to prevent duplicate
            // fabricCanvasRef.current.setActiveObject(img);
            // fabricCanvasRef.current.renderAll();

            // Also save to PAGE data
            if (onAddElement && PAGE) {
              onAddElement(PAGE.id, ELEMENT_TYPES.IMAGE, {
                src: base64,
                x: 100,
                y: 100,
                width: img.width * (img.scaleX || 1),
                height: img.height * (img.scaleY || 1),
                zIndex: getNextZIndex(),
                isUserMedia: true, // Mark as user media for AI preservation
              });
            }
          }
        });
      }
    };
    reader.readAsDataURL(file);

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [PAGE, onAddElement, getNextZIndex]);

  // Animation video file picker handler - converts to base64 data URL for S3 persistence
  const handleAnimationVideoSelect = useCallback(async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    console.log('[PrintableCanvas] Processing animation video:', file.name);

    // Check file size (100MB limit for animation videos)
    const MAX_SIZE_MB = 100;
    const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;
    if (file.size > MAX_SIZE_BYTES) {
      alert(`Animation video is too large! Maximum allowed size is ${MAX_SIZE_MB}MB. Your file is ${(file.size / 1024 / 1024).toFixed(2)}MB.`);
      if (animationInputRef.current) animationInputRef.current.value = '';
      return;
    }

    try {
      // Convert file to base64 data URL so it persists across save/reload and can be uploaded to S3
      const videoDataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });

      // Get video dimensions using a temporary blob URL (for metadata only)
      const tempBlobUrl = URL.createObjectURL(file);
      const video = document.createElement('video');
      video.muted = true;
      video.src = tempBlobUrl;

      await new Promise((resolve, reject) => {
        video.onloadedmetadata = resolve;
        video.onerror = reject;
      });

      const videoWidth = video.videoWidth;
      const videoHeight = video.videoHeight;
      URL.revokeObjectURL(tempBlobUrl); // Clean up temp blob URL

      // Scale down if too large
      const maxWidth = 400;
      const scale = Math.min(maxWidth / videoWidth, 1);
      const width = Math.round(videoWidth * scale);
      const height = Math.round(videoHeight * scale);

      console.log(`[Animation] Video loaded: ${videoWidth}x${videoHeight}, scaled to ${width}x${height}`);

      // Add animation element with base64 data URL (will be uploaded to S3 by backend)
      if (onAddElement && PAGE) {
        onAddElement(PAGE.id, ELEMENT_TYPES.ANIMATION, {
          videoSrc: videoDataUrl, // Base64 data URL for persistence and S3 upload
          isPlaying: true,
          loop: true,
          x: 100,
          y: 100,
          width: width,
          height: height,
          zIndex: getNextZIndex(),
          isUserMedia: true,
        });
      }

    } catch (error) {
      console.error('[Animation] Failed to load video:', error);
      alert('Failed to load video. Please try a different video file.');
    }

    // Reset file input
    if (animationInputRef.current) {
      animationInputRef.current.value = '';
    }
  }, [PAGE, onAddElement, getNextZIndex]);

  // Duplicate selected object (persists to React state with proper z-index)
  const handleDuplicate = useCallback(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();
    if (!activeObj || !activeObj.elementId) return;

    const PAGE = PAGERef.current;
    if (!PAGE?.elements) return;

    // Find the original element in React state
    const originalElement = PAGE.elements.find(el => el.id === activeObj.elementId);
    if (!originalElement) {
      console.warn('[DUPLICATE] Original element not found in React state');
      return;
    }

    // Calculate next z-index
    const maxZ = Math.max(...PAGE.elements.map(e => parseInt(e.zIndex) || 0));
    const newZIndex = maxZ + 1;

    // Create duplicate element data with offset and new z-index
    const duplicateData = {
      ...originalElement,
      x: (originalElement.x || 0) + 20,
      y: (originalElement.y || 0) + 20,
      zIndex: newZIndex,
    };
    delete duplicateData.id; // Let onAddElement generate new ID

    // Add via React state (canvas will sync automatically)
    if (handlersRef.current.onAddElement) {
      handlersRef.current.onAddElement(PAGE.id, originalElement.type, duplicateData);
    }
  }, []);

  // Layer management - bring forward (persists to React state)
  const handleBringForward = useCallback(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.elementId) {
      canvas.bringForward(activeObj);
      canvas.renderAll();

      // Calculate new z-index based on canvas position and persist to React state
      const objects = canvas.getObjects();
      const objIndex = objects.indexOf(activeObj);
      // Find the object that was previously above (now below in z-order)
      const PAGE = PAGERef.current;
      if (PAGE?.elements && handlersRef.current.onUpdateElement) {
        // Get z-index of the object we passed
        const objAbove = objIndex < objects.length - 1 ? objects[objIndex + 1] : null;
        const currentZ = parseInt(activeObj.zIndex) || 0;
        let newZ = currentZ + 1;
        if (objAbove && objAbove.zIndex !== undefined) {
          newZ = (parseInt(objAbove.zIndex) || 0) + 1;
        }
        handlersRef.current.onUpdateElement(PAGE.id, activeObj.elementId, { zIndex: newZ });
      }
    }
  }, []);

  // Layer management - send backward (persists to React state)
  const handleSendBackward = useCallback(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.elementId) {
      canvas.sendBackwards(activeObj);
      canvas.renderAll();

      // Calculate new z-index based on canvas position and persist to React state
      const objects = canvas.getObjects();
      const objIndex = objects.indexOf(activeObj);
      const PAGE = PAGERef.current;
      if (PAGE?.elements && handlersRef.current.onUpdateElement) {
        // Get z-index of the object we passed (now above us in z-order)
        const objBelow = objIndex > 0 ? objects[objIndex - 1] : null;
        const currentZ = parseInt(activeObj.zIndex) || 0;
        let newZ = Math.max(0, currentZ - 1);
        if (objBelow && objBelow.zIndex !== undefined) {
          newZ = Math.max(0, (parseInt(objBelow.zIndex) || 0) - 1);
        }
        handlersRef.current.onUpdateElement(PAGE.id, activeObj.elementId, { zIndex: newZ });
      }
    }
  }, []);

  // Update fill color of selected object
  const handleUpdateFillColor = useCallback((color) => {
    setFillColor(color);
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.elementId && handlersRef.current.onUpdateElement) {
      // Capture snapshot before change
      if (handlersRef.current.capturePreEditSnapshot) {
        handlersRef.current.capturePreEditSnapshot();
      }

      // For icons (groups), recursively apply color to all child paths
      if (activeObj.type === 'group' && activeObj.getObjects) {
        const applyColorRecursively = (obj, fillColor) => {
          if (obj.type === 'group' && obj.getObjects) {
            // Mark subgroups dirty so Fabric invalidates their cached render
            obj.set({ dirty: true, objectCaching: false });
            obj.getObjects().forEach(child => applyColorRecursively(child, fillColor));
          } else {
            // Apply fill color to visible parts of the path
            // IMPORTANT: Only change stroke for outline-only paths (fill='none')
            // to avoid overwriting user-set border/stroke colors
            if (obj.fill && obj.fill !== 'none') {
              obj.set('fill', fillColor);
            } else if (obj.stroke && obj.stroke !== 'none') {
              // Outline-only path — stroke IS the visible "fill" color
              obj.set('stroke', fillColor);
            } else {
              // Fallback for uncolored paths
              obj.set('fill', fillColor);
            }
            obj.set({ dirty: true });
          }
        };
        applyColorRecursively(activeObj, color);
        activeObj.dirty = true;
        activeObj.objectCaching = false;
      } else {
        activeObj.set('fill', color);
      }

      canvas.renderAll();

      // FIX: For text elements, also update 'color' property since sync loop prioritizes it
      const isTextElement = activeObj.type === 'textbox' || activeObj.type === 'i-text' || activeObj.type === 'text';
      const updateProps = isTextElement ? { fill: color, color: color } : { fill: color };

      handlersRef.current.onUpdateElement(PAGERef.current.id, activeObj.elementId, updateProps);
      handlersRef.current.saveToHistory();

      // Re-notify shared toolbar so it picks up the updated fill color
      if (onElementSelectionChangeRef.current) {
        const isText = activeObj.type === 'textbox' || activeObj.type === 'i-text' || activeObj.type === 'text';
        onElementSelectionChangeRef.current({
          hasSelection: true,
          type: activeObj.type,
          fill: color,
          stroke: activeObj.stroke || null,
          fontSize: (activeObj.fontSize || 16) / (scaleRef.current || 1),
          lineHeight: activeObj.lineHeight || 1.4,
          fontWeight: activeObj.fontWeight || 'normal',
          fontStyle: activeObj.fontStyle || 'normal',
          textAlign: activeObj.textAlign || 'left',
          fontFamily: activeObj.fontFamily || '',
          opacity: activeObj.opacity ?? 1,
          isText,
        });
      }
    }
  }, []);

  // Update opacity of selected object
  const handleUpdateOpacity = useCallback((value) => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.elementId && handlersRef.current.onUpdateElement) {
      if (handlersRef.current.capturePreEditSnapshot) {
        handlersRef.current.capturePreEditSnapshot();
      }

      activeObj.set('opacity', value);
      canvas.renderAll();

      handlersRef.current.onUpdateElement(PAGERef.current.id, activeObj.elementId, { opacity: value });
      handlersRef.current.saveToHistory();

      // Re-notify shared toolbar
      if (onElementSelectionChangeRef.current) {
        const isText = activeObj.type === 'textbox' || activeObj.type === 'i-text' || activeObj.type === 'text';
        onElementSelectionChangeRef.current({
          hasSelection: true,
          type: activeObj.type,
          fill: activeObj.fill || null,
          stroke: activeObj.stroke || null,
          fontSize: (activeObj.fontSize || 16) / (scaleRef.current || 1),
          lineHeight: activeObj.lineHeight || 1.4,
          fontWeight: activeObj.fontWeight || 'normal',
          fontStyle: activeObj.fontStyle || 'normal',
          textAlign: activeObj.textAlign || 'left',
          fontFamily: activeObj.fontFamily || '',
          opacity: value,
          isText,
        });
      }
    }
  }, []);

  // Update stroke color of selected object
  const handleUpdateStrokeColor = useCallback((color) => {
    setStrokeColor(color);
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.elementId && handlersRef.current.onUpdateElement) {
      // Capture snapshot before change
      if (handlersRef.current.capturePreEditSnapshot) {
        handlersRef.current.capturePreEditSnapshot();
      }
      activeObj.set('stroke', color);
      // Ensure strokeWidth is set so the border is visible (especially for groups/icons)
      if (!activeObj.strokeWidth || activeObj.strokeWidth < 1) {
        activeObj.set('strokeWidth', 2);
      }
      canvas.renderAll();

      const strokeUpdateProps = { stroke: color };
      if (!activeObj.strokeWidth || activeObj.strokeWidth <= 2) {
        strokeUpdateProps.strokeWidth = activeObj.strokeWidth || 2;
      }
      handlersRef.current.onUpdateElement(PAGERef.current.id, activeObj.elementId, strokeUpdateProps);
      handlersRef.current.saveToHistory();

      // Re-notify shared toolbar so it picks up the updated stroke color
      if (onElementSelectionChangeRef.current) {
        const isText = activeObj.type === 'textbox' || activeObj.type === 'i-text' || activeObj.type === 'text';
        onElementSelectionChangeRef.current({
          hasSelection: true,
          type: activeObj.type,
          fill: activeObj.fill || null,
          stroke: color,
          fontSize: (activeObj.fontSize || 16) / (scaleRef.current || 1),
          lineHeight: activeObj.lineHeight || 1.4,
          fontWeight: activeObj.fontWeight || 'normal',
          fontStyle: activeObj.fontStyle || 'normal',
          textAlign: activeObj.textAlign || 'left',
          fontFamily: activeObj.fontFamily || '',
          isText,
        });
      }
    }
  }, []);

  // Update font size of selected text
  const handleUpdateFontSize = useCallback((size) => {
    setFontSize(size);
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.elementId && handlersRef.current.onUpdateElement && (activeObj.type === 'textbox' || activeObj.type === 'i-text')) {
      // Capture snapshot before change
      if (handlersRef.current.capturePreEditSnapshot) {
        handlersRef.current.capturePreEditSnapshot();
      }
      activeObj.set('fontSize', size * (scaleRef.current || 1));
      canvas.renderAll();

      handlersRef.current.onUpdateElement(PAGERef.current.id, activeObj.elementId, { fontSize: size });
      handlersRef.current.saveToHistory();

      // Re-notify shared toolbar so it picks up the updated fontSize
      if (onElementSelectionChangeRef.current) {
        onElementSelectionChangeRef.current({
          hasSelection: true,
          type: activeObj.type,
          fill: activeObj.fill || null,
          stroke: activeObj.stroke || null,
          fontSize: size,
          lineHeight: activeObj.lineHeight || 1.4,
          fontWeight: activeObj.fontWeight || 'normal',
          fontStyle: activeObj.fontStyle || 'normal',
          textAlign: activeObj.textAlign || 'left',
          fontFamily: activeObj.fontFamily || '',
          isText: true,
        });
      }
    }
  }, []);

  // Update line height of selected text
  const handleUpdateLineHeight = useCallback((height) => {
    // Clamp line height between 0.8 and 3
    const newHeight = Math.max(0.8, Math.min(3, Math.round(height * 100) / 100));
    setLineHeight(newHeight);

    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.elementId && handlersRef.current.onUpdateElement && (activeObj.type === 'textbox' || activeObj.type === 'i-text')) {
      // Capture snapshot before change
      if (handlersRef.current.capturePreEditSnapshot) {
        handlersRef.current.capturePreEditSnapshot();
      }
      activeObj.set('lineHeight', newHeight);
      canvas.renderAll();

      handlersRef.current.onUpdateElement(PAGERef.current.id, activeObj.elementId, { lineHeight: newHeight });
      handlersRef.current.saveToHistory();

      // Re-notify shared toolbar so it picks up the updated lineHeight
      if (onElementSelectionChangeRef.current) {
        onElementSelectionChangeRef.current({
          hasSelection: true,
          type: activeObj.type,
          fill: activeObj.fill || null,
          stroke: activeObj.stroke || null,
          fontSize: (activeObj.fontSize || 16) / (scaleRef.current || 1),
          lineHeight: newHeight,
          fontWeight: activeObj.fontWeight || 'normal',
          fontStyle: activeObj.fontStyle || 'normal',
          textAlign: activeObj.textAlign || 'left',
          fontFamily: activeObj.fontFamily || '',
          isText: true,
        });
      }
    }
  }, []);

  // ═══════════════════════════════════════════════════════════════
  // INLINE (CHARACTER-LEVEL) FORMATTING HANDLERS
  // These operate on selected text within a Textbox using Fabric.js
  // setSelectionStyles() / getSelectionStyles() APIs
  // ═══════════════════════════════════════════════════════════════

  // Helper: apply style to selection or fall back to whole-object
  const applyInlineOrWholeStyle = useCallback((styleKey, newValue, elementUpdateKey) => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;
    const activeObj = canvas.getActiveObject();
    if (!activeObj || !activeObj.elementId) return;
    if (activeObj.type !== 'textbox' && activeObj.type !== 'i-text') return;

    if (handlersRef.current.capturePreEditSnapshot) {
      handlersRef.current.capturePreEditSnapshot();
    }

    const currentScale = scaleRef.current || 1;

    if (activeObj.isEditing && activeObj.selectionStart !== activeObj.selectionEnd) {
      // Inline: apply to selected characters only
      const styleObj = {};
      if (styleKey === 'fontSize') {
        styleObj[styleKey] = newValue * currentScale;
      } else {
        styleObj[styleKey] = newValue;
      }
      activeObj.setSelectionStyles(styleObj);
      canvas.renderAll();

      // Persist the full styles object
      handlersRef.current.onUpdateElement(PAGERef.current.id, activeObj.elementId, {
        styles: JSON.parse(JSON.stringify(activeObj.styles || {})),
      });

      // Refresh the toolbar with updated styles
      const start = activeObj.selectionStart;
      const end = activeObj.selectionEnd;
      const selStyles = activeObj.getSelectionStyles(start, end);
      const firstStyle = selStyles[0] || {};
      if (handlersRef.current.setInlineToolbar) {
        const boundingRect = activeObj.getBoundingRect();
        handlersRef.current.setInlineToolbar({
          visible: true,
          x: boundingRect.left + boundingRect.width / 2,
          y: boundingRect.top,
          styles: {
            fontWeight: firstStyle.fontWeight || activeObj.fontWeight || 'normal',
            fontStyle: firstStyle.fontStyle || activeObj.fontStyle || 'normal',
            underline: firstStyle.underline !== undefined ? firstStyle.underline : (activeObj.underline || false),
            fill: firstStyle.fill || activeObj.fill || '#000000',
            textBackgroundColor: firstStyle.textBackgroundColor || '',
            fontFamily: firstStyle.fontFamily || activeObj.fontFamily || 'Inter',
            fontSize: (firstStyle.fontSize || activeObj.fontSize || 16) / currentScale,
          },
        });
      }
    } else {
      // Whole-object: apply to entire text element
      if (styleKey === 'fontSize') {
        activeObj.set(styleKey, newValue * currentScale);
      } else {
        activeObj.set(styleKey, newValue);
      }
      canvas.renderAll();
      const updatePayload = {};
      updatePayload[elementUpdateKey || styleKey] = newValue;
      handlersRef.current.onUpdateElement(PAGERef.current.id, activeObj.elementId, updatePayload);
    }
    handlersRef.current.saveToHistory();
  }, []);

  const handleInlineToggleBold = useCallback(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;
    const activeObj = canvas.getActiveObject();
    if (!activeObj) return;

    let currentWeight = 'normal';
    if (activeObj.isEditing && activeObj.selectionStart !== activeObj.selectionEnd) {
      const selStyles = activeObj.getSelectionStyles(activeObj.selectionStart, activeObj.selectionEnd);
      currentWeight = selStyles[0]?.fontWeight || activeObj.fontWeight || 'normal';
    } else {
      currentWeight = activeObj.fontWeight || 'normal';
    }
    const newWeight = (currentWeight === 'bold' || currentWeight >= 700) ? 'normal' : 'bold';
    applyInlineOrWholeStyle('fontWeight', newWeight, 'fontWeight');
  }, [applyInlineOrWholeStyle]);

  const handleInlineToggleItalic = useCallback(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;
    const activeObj = canvas.getActiveObject();
    if (!activeObj) return;

    let currentStyle = 'normal';
    if (activeObj.isEditing && activeObj.selectionStart !== activeObj.selectionEnd) {
      const selStyles = activeObj.getSelectionStyles(activeObj.selectionStart, activeObj.selectionEnd);
      currentStyle = selStyles[0]?.fontStyle || activeObj.fontStyle || 'normal';
    } else {
      currentStyle = activeObj.fontStyle || 'normal';
    }
    const newStyle = currentStyle === 'italic' ? 'normal' : 'italic';
    applyInlineOrWholeStyle('fontStyle', newStyle, 'fontStyle');
  }, [applyInlineOrWholeStyle]);

  const handleInlineToggleUnderline = useCallback(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;
    const activeObj = canvas.getActiveObject();
    if (!activeObj) return;

    let currentUnderline = false;
    if (activeObj.isEditing && activeObj.selectionStart !== activeObj.selectionEnd) {
      const selStyles = activeObj.getSelectionStyles(activeObj.selectionStart, activeObj.selectionEnd);
      currentUnderline = selStyles[0]?.underline || false;
    } else {
      currentUnderline = activeObj.underline || false;
    }
    applyInlineOrWholeStyle('underline', !currentUnderline, 'underline');
  }, [applyInlineOrWholeStyle]);

  const handleInlineSetColor = useCallback((color) => {
    applyInlineOrWholeStyle('fill', color, 'fill');
  }, [applyInlineOrWholeStyle]);

  const handleInlineSetHighlight = useCallback((color) => {
    applyInlineOrWholeStyle('textBackgroundColor', color || '', 'textBackgroundColor');
  }, [applyInlineOrWholeStyle]);

  const handleInlineSetFontFamily = useCallback((family) => {
    applyInlineOrWholeStyle('fontFamily', family, 'fontFamily');
  }, [applyInlineOrWholeStyle]);

  const handleInlineSetFontSize = useCallback((size) => {
    applyInlineOrWholeStyle('fontSize', size, 'fontSize');
  }, [applyInlineOrWholeStyle]);

  // Toggle bold on selected text
  const handleToggleBold = useCallback(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.elementId && handlersRef.current.onUpdateElement && (activeObj.type === 'textbox' || activeObj.type === 'i-text')) {
      // Delegate to inline handler when editing with a selection
      if (activeObj.isEditing && activeObj.selectionStart !== activeObj.selectionEnd) {
        handleInlineToggleBold();
        return;
      }
      // Capture snapshot before change
      if (handlersRef.current.capturePreEditSnapshot) {
        handlersRef.current.capturePreEditSnapshot();
      }
      const currentWeight = activeObj.fontWeight;
      const newWeight = currentWeight === 'bold' ? 'normal' : 'bold';
      activeObj.set('fontWeight', newWeight);
      canvas.renderAll();

      handlersRef.current.onUpdateElement(PAGERef.current.id, activeObj.elementId, { fontWeight: newWeight });
      handlersRef.current.saveToHistory();

      // Re-notify shared toolbar so it picks up the updated fontWeight
      if (onElementSelectionChangeRef.current) {
        onElementSelectionChangeRef.current({
          hasSelection: true,
          type: activeObj.type,
          fill: activeObj.fill || null,
          stroke: activeObj.stroke || null,
          fontSize: (activeObj.fontSize || 16) / (scaleRef.current || 1),
          lineHeight: activeObj.lineHeight || 1.4,
          fontWeight: newWeight,
          fontStyle: activeObj.fontStyle || 'normal',
          textAlign: activeObj.textAlign || 'left',
          fontFamily: activeObj.fontFamily || '',
          isText: true,
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Toggle italic on selected text
  const handleToggleItalic = useCallback(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.elementId && handlersRef.current.onUpdateElement && (activeObj.type === 'textbox' || activeObj.type === 'i-text')) {
      // Delegate to inline handler when editing with a selection
      if (activeObj.isEditing && activeObj.selectionStart !== activeObj.selectionEnd) {
        handleInlineToggleItalic();
        return;
      }
      // Capture snapshot before change
      if (handlersRef.current.capturePreEditSnapshot) {
        handlersRef.current.capturePreEditSnapshot();
      }
      const currentStyle = activeObj.fontStyle;
      const newStyle = currentStyle === 'italic' ? 'normal' : 'italic';
      activeObj.set('fontStyle', newStyle);
      canvas.renderAll();

      handlersRef.current.onUpdateElement(PAGERef.current.id, activeObj.elementId, { fontStyle: newStyle });
      handlersRef.current.saveToHistory();

      // Re-notify shared toolbar so it picks up the updated fontStyle
      if (onElementSelectionChangeRef.current) {
        onElementSelectionChangeRef.current({
          hasSelection: true,
          type: activeObj.type,
          fill: activeObj.fill || null,
          stroke: activeObj.stroke || null,
          fontSize: (activeObj.fontSize || 16) / (scaleRef.current || 1),
          lineHeight: activeObj.lineHeight || 1.4,
          fontWeight: activeObj.fontWeight || 'normal',
          fontStyle: newStyle,
          textAlign: activeObj.textAlign || 'left',
          fontFamily: activeObj.fontFamily || '',
          isText: true,
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Helper to flush any pending edits to history (called before undo/redo)
  const flushPendingEditsToHistory = useCallback(() => {
    if (!PAGERef.current?.id || PAGERef.current.id !== currentPAGEIdRef.current) return;
    // Skip if an undo/redo is in progress to avoid corrupting history
    if (isUndoRedoActiveFor(PAGERef.current.id)) return;

    // Clear any pending debounce for this PAGE
    const pending = historyDebounceMapRef.current.get(PAGERef.current.id);
    if (pending) {
      clearTimeout(pending);
      historyDebounceMapRef.current.delete(PAGERef.current.id);
    }

    if (!PAGERef.current?.id || !PAGERef.current?.elements) return;
    const history = getPAGEHistory(PAGERef.current.id);
    if (!history) return;

    // If a text object is still in editing mode, force Fabric to commit the text
    const canvas = fabricCanvasRef.current;
    if (canvas) {
      const activeObj = canvas.getActiveObject();
      if (activeObj?.isEditing && activeObj.exitEditing) {
        activeObj.exitEditing();
        // Ensure Fabric renders the committed text
        canvas.setActiveObject(activeObj);
        canvas.renderAll();
      }
    }

    // First, commit any pending pre-edit snapshot
    if (preEditSnapshotRef.current) {
      const snapshotStr = JSON.stringify(preEditSnapshotRef.current);
      if (snapshotStr !== history.lastSaved) {
        if (history.index < history.states.length - 1) {
          history.states = history.states.slice(0, history.index + 1);
        }
        history.states.push(preEditSnapshotRef.current);
        history.index = history.states.length - 1;
        history.lastSaved = snapshotStr;
        prevElementsMapRef.current.set(PAGERef.current.id, snapshotStr);
        console.log('💾 [FLUSH] Saved pre-edit snapshot for PAGE', PAGERef.current.id, 'index:', history.index);
      }
      preEditSnapshotRef.current = null;
    }

    // Do NOT snapshot current fabric state here; leaving it caused duplicate undo steps.
  }, [getPAGEHistory, isUndoRedoActiveFor]);

  // Undo - restore previous state for current PAGE
  const handleUndo = useCallback(() => {
    if (!PAGE?.id) return;
    if (PAGE.id !== currentPAGEIdRef.current) return; // guard per-PAGE history

    // CRITICAL: Flush any pending edits before undo
    flushPendingEditsToHistory();

    const history = getPAGEHistory(PAGE.id);
    if (!history) return;

    console.log('⏪ [UNDO] Called for PAGE', PAGE.id, 'index:', history.index, 'history length:', history.states.length);
    if (history.index <= 0) {
      console.log('⏪ [UNDO] Nothing to undo for PAGE', PAGE.id);
      return;
    }

    setUndoRedoActiveFor(PAGE.id, true);
    history.index -= 1;
    const prevState = history.states[history.index];

    if (prevState) {
      // Normalize and rewrite the stored state so history stays consistent
      const elementsToRestore = Array.isArray(prevState)
        ? prevState
        : Array.isArray(prevState.elements)
          ? prevState.elements
          : Array.isArray(prevState.elements?.elements)
            ? prevState.elements.elements
            : [];
      const backgroundToRestore = prevState.backgroundColor ?? prevState.elements?.backgroundColor;

      const normalizedState = { elements: elementsToRestore, backgroundColor: backgroundToRestore };
      history.states[history.index] = normalizedState;

      console.log('⏪ [UNDO] Restoring state with', elementsToRestore.length, 'elements for PAGE', PAGE.id);
      const restoredSnapshotStr = JSON.stringify(normalizedState);
      prevElementsMapRef.current.set(PAGE.id, restoredSnapshotStr);
      history.lastSaved = restoredSnapshotStr;
      // Discard active selection so renderSlideElements doesn't skip layout (skipLayout=isActive)
      fabricCanvasRef.current?.discardActiveObject();
      onUpdateElement(PAGE.id, null, { elements: elementsToRestore });
      if (backgroundToRestore !== undefined && backgroundToRestore !== PAGE.backgroundColor && onUpdatePAGEBackground) {
        onUpdatePAGEBackground(backgroundToRestore);
      }
    }

    setTimeout(() => {
      setUndoRedoActiveFor(PAGE.id, false);
    }, 200);
  }, [PAGE?.id, onUpdateElement, getPAGEHistory, flushPendingEditsToHistory, setUndoRedoActiveFor]);

  // Redo - restore next state for current PAGE
  const handleRedo = useCallback(() => {
    if (!PAGE?.id) return;
    if (PAGE.id !== currentPAGEIdRef.current) return; // guard per-PAGE history

    // Flush any pending edits before redo
    flushPendingEditsToHistory();

    const history = getPAGEHistory(PAGE.id);
    if (!history) return;

    console.log('⏩ [REDO] Called for PAGE', PAGE.id, 'index:', history.index, 'history length:', history.states.length);
    if (history.index >= history.states.length - 1) {
      console.log('⏩ [REDO] Nothing to redo for PAGE', PAGE.id);
      return;
    }

    setUndoRedoActiveFor(PAGE.id, true);
    history.index += 1;
    const nextState = history.states[history.index];

    if (nextState) {
      const elementsToRestore = Array.isArray(nextState)
        ? nextState
        : Array.isArray(nextState.elements)
          ? nextState.elements
          : Array.isArray(nextState.elements?.elements)
            ? nextState.elements.elements
            : [];
      const backgroundToRestore = nextState.backgroundColor ?? nextState.elements?.backgroundColor;

      const normalizedState = { elements: elementsToRestore, backgroundColor: backgroundToRestore };
      history.states[history.index] = normalizedState;

      console.log('⏩ [REDO] Restoring state with', elementsToRestore.length, 'elements for PAGE', PAGE.id);
      const restoredSnapshotStr = JSON.stringify(normalizedState);
      prevElementsMapRef.current.set(PAGE.id, restoredSnapshotStr);
      history.lastSaved = restoredSnapshotStr;
      // Discard active selection so renderSlideElements doesn't skip layout (skipLayout=isActive)
      fabricCanvasRef.current?.discardActiveObject();
      onUpdateElement(PAGE.id, null, { elements: elementsToRestore });
      if (backgroundToRestore !== undefined && backgroundToRestore !== PAGE.backgroundColor && onUpdatePAGEBackground) {
        onUpdatePAGEBackground(backgroundToRestore);
      }
    }

    setTimeout(() => {
      setUndoRedoActiveFor(PAGE.id, false);
    }, 200);
  }, [PAGE?.id, onUpdateElement, getPAGEHistory, flushPendingEditsToHistory, setUndoRedoActiveFor]);

  // Capture a snapshot BEFORE starting an edit (call this before making changes)
  const capturePreEditSnapshot = useCallback(() => {
    if (isUndoRedoActiveFor(PAGE?.id) || !PAGE?.elements) return;

    // Only capture if we don't already have a pending snapshot
    if (!preEditSnapshotRef.current) {
      preEditSnapshotRef.current = JSON.parse(JSON.stringify({
        elements: PAGE.elements || [],
        backgroundColor: PAGE.backgroundColor,
      }));
      console.log('📷 [HISTORY] Captured pre-edit snapshot with', PAGE.elements?.length || 0, 'elements for PAGE', PAGE.id);
    }
  }, [PAGE?.id, PAGE?.elements]);

  // Commit the pre-edit snapshot to history (call this after edit is complete)
  const commitToHistory = useCallback(() => {
    if (isUndoRedoActiveFor(PAGE?.id) || !PAGE?.id) return;

    // Clear any pending debounce for this PAGE
    const pending = historyDebounceMapRef.current.get(PAGE.id);
    if (pending) {
      clearTimeout(pending);
      historyDebounceMapRef.current.delete(PAGE.id);
    }

    const history = getPAGEHistory(PAGE.id);
    if (!history) return;

    // If we have a pre-edit snapshot and current state is different, save it
    const snapshot = preEditSnapshotRef.current;
    if (snapshot) {
      const snapshotStr = JSON.stringify(snapshot);

      // Check if this snapshot is different from what's already saved
      if (snapshotStr !== history.lastSaved) {
        // Trim any redo states if we're not at the end
        if (history.index < history.states.length - 1) {
          history.states = history.states.slice(0, history.index + 1);
        }

        // Save the PRE-EDIT state (so undo goes back to this)
        history.states.push(snapshot);
        history.index = history.states.length - 1;
        history.lastSaved = snapshotStr;
        prevElementsMapRef.current.set(PAGE.id, snapshotStr);

        // Limit history to 50 states
        if (history.states.length > 50) {
          history.states.shift();
          history.index -= 1;
        }

        console.log('💾 [HISTORY] Committed pre-edit state for PAGE', PAGE.id, 'index:', history.index, 'elements:', snapshot.elements?.length || 0);
      }

      preEditSnapshotRef.current = null;
    }
  }, [PAGE?.id, getPAGEHistory]);

  // Save state to history with debouncing for rapid edits
  const saveToHistory = useCallback(() => {
    if (isUndoRedoActiveFor(PAGERef.current?.id) || !PAGERef.current?.id) return;

    const history = getPAGEHistory(PAGERef.current.id);
    if (!history) return;

    const currentState = collectCurrentPAGEState(PAGERef.current.id);
    if (!currentState) return;
    const currentStr = JSON.stringify(currentState);

    // Skip if state hasn't changed
    if (currentStr === history.lastSaved) {
      console.log('⏭️ [HISTORY] Skipped duplicate state for PAGE', PAGERef.current.id);
      return;
    }

    // Trim any redo states if we're not at the end
    if (history.index < history.states.length - 1) {
      history.states = history.states.slice(0, history.index + 1);
    }

    // Save current state
    history.states.push(currentState);
    history.index = history.states.length - 1;
    history.lastSaved = currentStr;
    prevElementsMapRef.current.set(PAGERef.current.id, currentStr);

    // Limit history to 50 states
    if (history.states.length > 50) {
      history.states.shift();
      history.index -= 1;
    }

    // console.log('💾 [HISTORY] Saved state for PAGE', PAGERef.current.id, 'index:', history.index, 'elements:', currentState.elements?.length || 0);
  }, [collectCurrentPAGEState, getPAGEHistory]);

  // Debounced save - batches rapid changes (like dragging)
  const debouncedSaveToHistory = useCallback(() => {
    if (isUndoRedoActiveFor(PAGERef.current?.id)) return;

    // Clear existing debounce for this PAGE
    const pending = historyDebounceMapRef.current.get(PAGERef.current?.id);
    if (pending) {
      clearTimeout(pending);
    }

    // Schedule save after 300ms of inactivity for this PAGE
    const timer = setTimeout(() => {
      saveToHistory();
      historyDebounceMapRef.current.delete(PAGERef.current?.id);
    }, 300);
    if (PAGERef.current?.id) {
      historyDebounceMapRef.current.set(PAGERef.current.id, timer);
    }
  }, [saveToHistory]);

  // Update refs on render & handle pending history save
  useEffect(() => {
    PAGERef.current = PAGE;
    scaleRef.current = canvasScale; // Keep scale ref in sync for event handlers

    handlersRef.current = {
      onUpdateElement,
      onDeleteElement,
      onAddElement,  // FIX: Add onAddElement for handleDuplicate to work
      handleInlineToggleBold,
      handleInlineToggleItalic,
      handleInlineToggleUnderline,
      handleDuplicate,
      handleBringForward,
      handleSendBackward,
      capturePreEditSnapshot: () => {
        // Capture snapshot immediately using current PAGE state
        if (!preEditSnapshotRef.current && PAGERef.current) {
          preEditSnapshotRef.current = JSON.parse(JSON.stringify({
            elements: PAGERef.current.elements || [],
            backgroundColor: PAGERef.current.backgroundColor,
          }));
          console.log('📷 [HANDLERS] Captured pre-edit snapshot with', PAGERef.current.elements?.length || 0, 'elements');
        }
      },
      saveToHistory: () => {
        // This is called AFTER an edit is complete (e.g., object:modified, text:editing:exited)
        // We need to save BOTH the pre-edit snapshot AND the current state

        // Clear any pending debounce timer first (important for text editing)
        const pending = historyDebounceMapRef.current.get(PAGERef.current.id);
        if (pending) {
          clearTimeout(pending);
          historyDebounceMapRef.current.delete(PAGERef.current.id);
        }

        // Step 1: Commit pre-edit snapshot to history (the state BEFORE the edit)
        commitToHistory();

        // Step 2: Save the current state by reading directly from Fabric canvas
        // This is more reliable than waiting for React state to update
        if (!isUndoRedoActiveFor(PAGERef.current?.id) && PAGERef.current?.id) {
          const history = getPAGEHistory(PAGERef.current.id);
          if (!history) return;

          const currentState = collectCurrentPAGEState(PAGERef.current.id);
          if (!currentState) return;
          const currentStr = JSON.stringify(currentState);

          // Skip if state hasn't changed from last saved
          if (currentStr !== history.lastSaved) {
            // Trim any redo states
            if (history.index < history.states.length - 1) {
              history.states = history.states.slice(0, history.index + 1);
            }

            history.states.push(currentState);
            history.index = history.states.length - 1;
            history.lastSaved = currentStr;

            // Update prevElementsMap to prevent false external change detection
            prevElementsMapRef.current.set(PAGERef.current.id, currentStr);

            // Limit history
            if (history.states.length > 50) {
              history.states.shift();
              history.index -= 1;
            }

            console.log('💾 [HANDLERS] Saved post-edit state for PAGE', PAGERef.current.id, 'index:', history.index);
          }
        }
      },
      debouncedSaveToHistory: () => {
        // For continuous edits like text typing - debounce the save
        // Clear existing debounce for this PAGE
        const pending = historyDebounceMapRef.current.get(PAGERef.current?.id);
        if (pending) {
          clearTimeout(pending);
        }

        // Schedule save after 300ms of inactivity using refs (not closures)
        const timer = setTimeout(() => {
          if (!isUndoRedoActiveFor(PAGERef.current?.id) && PAGERef.current?.id && PAGERef.current?.elements) {
            // First commit any pending pre-edit snapshot
            commitToHistory();

            // Then save current state by syncing from Fabric canvas
            const history = getPAGEHistory(PAGERef.current.id);
            if (!history) return;

            const currentState = collectCurrentPAGEState(PAGERef.current.id);
            if (!currentState) return;
            const currentStr = JSON.stringify(currentState);

            if (currentStr !== history.lastSaved) {
              if (history.index < history.states.length - 1) {
                history.states = history.states.slice(0, history.index + 1);
              }

              history.states.push(currentState);
              history.index = history.states.length - 1;
              history.lastSaved = currentStr;
              prevElementsMapRef.current.set(PAGERef.current.id, currentStr);

              if (history.states.length > 50) {
                history.states.shift();
                history.index -= 1;
              }

              console.log('💾 [HANDLERS-DEBOUNCED] Saved state for PAGE', PAGERef.current.id, 'index:', history.index);
            }
          }
          if (PAGERef.current?.id) {
            historyDebounceMapRef.current.delete(PAGERef.current.id);
          }
        }, 300);

        if (PAGERef.current?.id) {
          historyDebounceMapRef.current.set(PAGERef.current.id, timer);
        }
      }
    };
  }, [PAGE, onUpdateElement, onDeleteElement, saveToHistory, commitToHistory, debouncedSaveToHistory, canvasScale, getPAGEHistory]);

  // Keep inline toolbar ref in sync with state setter (avoids stale closures in Fabric events)
  handlersRef.current.setInlineToolbar = (val) => {
    inlineToolbarRef.current = val;
    setInlineToolbar(val);
  };

  // Keep format painter refs updated for use in canvas event handlers
  useEffect(() => {
    formatPainterActiveRef.current = formatPainterActive;
    formatPainterDataRef.current = formatPainterData;
    onFormatPainterApplyRef.current = onFormatPainterApply;
    onElementSelectionChangeRef.current = onElementSelectionChange;
  }, [formatPainterActive, formatPainterData, onFormatPainterApply, onElementSelectionChange]);

  // Helper to notify shared toolbar of selection state changes
  const notifySelectionChange = useCallback((selectedObjects) => {
    if (!onElementSelectionChangeRef.current) return;
    if (!selectedObjects || selectedObjects.length === 0) {
      onElementSelectionChangeRef.current({ hasSelection: false });
      return;
    }
    const obj = selectedObjects[0];
    const isText = obj.type === 'textbox' || obj.type === 'i-text' || obj.type === 'text';
    const currentScale = scaleRef.current || 1;
    onElementSelectionChangeRef.current({
      hasSelection: true,
      type: obj.type,
      fill: obj.fill || null,
      stroke: obj.stroke || null,
      fontSize: isText ? ((obj.fontSize || 16) / currentScale) : null,
      lineHeight: isText ? (obj.lineHeight || 1.4) : null,
      fontWeight: isText ? (obj.fontWeight || 'normal') : null,
      fontStyle: isText ? (obj.fontStyle || 'normal') : null,
      textAlign: isText ? (obj.textAlign || 'left') : null,
      fontFamily: isText ? (obj.fontFamily || '') : null,
      isText,
    });
  }, []);

  // Text alignment
  const handleTextAlign = useCallback((align) => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.elementId && handlersRef.current.onUpdateElement && (activeObj.type === 'textbox' || activeObj.type === 'i-text')) {
      // Capture snapshot before change
      if (handlersRef.current.capturePreEditSnapshot) {
        handlersRef.current.capturePreEditSnapshot();
      }
      activeObj.set('textAlign', align);
      canvas.renderAll();

      handlersRef.current.onUpdateElement(PAGERef.current.id, activeObj.elementId, { textAlign: align });
      handlersRef.current.saveToHistory();

      // Re-notify shared toolbar so it picks up the updated textAlign
      if (onElementSelectionChangeRef.current) {
        onElementSelectionChangeRef.current({
          hasSelection: true,
          type: activeObj.type,
          fill: activeObj.fill || null,
          stroke: activeObj.stroke || null,
          fontSize: (activeObj.fontSize || 16) / (scaleRef.current || 1),
          lineHeight: activeObj.lineHeight || 1.4,
          fontWeight: activeObj.fontWeight || 'normal',
          fontStyle: activeObj.fontStyle || 'normal',
          textAlign: align,
          fontFamily: activeObj.fontFamily || '',
          isText: true,
        });
      }
    }
  }, []);
  // Apply font combination to selected text element only
  const handleApplyFontCombination = useCallback((combination) => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    const activeObj = canvas.getActiveObject();

    // Check if there's a selected text object
    if (!activeObj || (activeObj.type !== 'textbox' && activeObj.type !== 'i-text')) {
      console.log('⚠️ No text element selected. Please select a text element first.');
      return;
    }

    const { headingFont, bodyFont } = combination;

    // Find the corresponding element to determine if it's heading or body
    const element = PAGE?.elements?.find(el => el.id === activeObj.elementId);

    // Determine if this is a heading or body text
    const isHeading = element?.textType === 'title' ||
      element?.textType === 'heading' ||
      element?.textType === 'subtitle' ||
      (element?.fontSize && element.fontSize >= 28) ||
      (activeObj.fontSize && (activeObj.fontSize / (scaleRef.current || 1)) >= 28);

    const fontToApply = isHeading ? headingFont : bodyFont;

    // Update Fabric object
    activeObj.set({
      fontFamily: fontToApply.family,
      fontWeight: fontToApply.weight,
    });

    // CRITICAL: Mark text as dirty to force Fabric.js to recalculate dimensions and re-render
    activeObj.dirty = true;
    if (activeObj.initDimensions) {
      activeObj.initDimensions(); // Recalculate text dimensions with new font
    }
    activeObj.setCoords(); // Update bounding box

    canvas.requestRenderAll(); // Use requestRenderAll for async render

    // Update element in PAGE state - use onUpdateElement prop directly with PAGE.id from prop
    // This ensures we're not using stale refs and the update is properly applied
    if (onUpdateElement && activeObj.elementId && PAGE?.id) {
      console.log('🎨 [FONT] Updating element', activeObj.elementId, 'on PAGE', PAGE.id, 'with font:', fontToApply.family);
      onUpdateElement(PAGE.id, activeObj.elementId, {
        fontFamily: fontToApply.family,
        fontWeight: fontToApply.weight,
      });
      console.log('✅ [FONT] Applied font combination:', combination.name, 'to element', activeObj.elementId);
    } else {
      console.error('❌ [FONT] Failed to update element - missing:', { onUpdateElement: !!onUpdateElement, elementId: activeObj.elementId, PAGEId: PAGE?.id });
    }
  }, [PAGE, onUpdateElement]);

  // Expose methods via ref - UNIFIED (all imperative methods in one place)
  useImperativeHandle(ref, () => ({
    // === Canvas editing methods ===
    addText: handleAddText,
    addImage: handleAddImage,
    addShape: handleAddShape,
    deleteSelected: handleDeleteSelected,
    toJSON: handleToJSON,
    zoomIn: handleZoomIn,
    zoomOut: handleZoomOut,
    resetZoom: handleResetZoom,

    // === Formatting methods (for shared toolbar) ===
    toggleBold: handleToggleBold,
    toggleItalic: handleToggleItalic,
    updateFillColor: handleUpdateFillColor,
    updateStrokeColor: handleUpdateStrokeColor,
    updateOpacity: handleUpdateOpacity,
    updateFontSize: handleUpdateFontSize,
    updateLineHeight: handleUpdateLineHeight,
    setTextAlign: handleTextAlign,

    // === Edit operations (for shared toolbar) ===
    undo: handleUndo,
    redo: handleRedo,
    duplicate: handleDuplicate,
    bringForward: handleBringForward,
    sendBackward: handleSendBackward,

    // === Insert helpers (for shared toolbar) ===
    insertElement: handleAddElement,
    triggerFileInput: (type) => {
      if (type === 'image') fileInputRef.current?.click();
      else if (type === 'video') videoInputRef.current?.click();
      else if (type === 'animation') animationInputRef.current?.click();
    },
    openModal: (name) => {
      switch (name) {
        case 'shapes': setShowShapesPicker(true); break;
        case 'icon': setShowIconPicker(true); break;
        case 'fontCombo': setShowFontComboPicker(true); break;
        case 'table': setShowTablePicker(true); break;
        case 'video': setShowVideoModal(true); break;
        case 'embed': setShowEmbedModal(true); break;
        case 'forms': setShowFormsModal(true); break;
      }
    },

    // === Clipboard & Format Painter (for shared toolbar) ===
    copyElements: onCopyElements,
    pasteElements: onPasteElements,
    activateFormatPainter: onActivateFormatPainter,
    deactivateFormatPainter: onDeactivateFormatPainter,

    // === Selection helpers ===
    discardSelection: () => {
      fabricCanvasRef.current?.discardActiveObject();
      fabricCanvasRef.current?.requestRenderAll();
    },
    getSelectedElementInfo: () => ({
      fill: fillColor,
      stroke: strokeColor,
      fontSize,
      lineHeight,
    }),
    getFabricCanvas: () => fabricCanvasRef.current,

    // === Chart insertion ===
    addChart: async (chartConfig) => {
      if (Platform.OS !== 'web' || !fabricModule) {
        console.warn('Charts only supported on web');
        return;
      }

      console.log('📊 [CANVAS] Adding interactive chart...');

      // Capture snapshot before adding chart
      if (handlersRef.current.capturePreEditSnapshot) {
        handlersRef.current.capturePreEditSnapshot();
      }

      try {
        const fabricRef = window.fabric || fabricModule;
        if (fabricRef?.Chart) {
          console.log('📊 [CANVAS] Using fabric.Chart for interactive chart');
          const chartWidth = 480;
          const chartHeight = 320;
          const chartLeft = PAGE_WIDTH / 2 - chartWidth / 2;
          const chartTop = PAGE_HEIGHT / 2 - chartHeight / 2;

          onAddElement(PAGE.id, 'chart', {
            x: chartLeft,
            y: chartTop,
            width: chartWidth,
            height: chartHeight,
            chartConfig: chartConfig,
            zIndex: getNextZIndex(),
          });

          if (fabricCanvasRef.current) {
            fabricCanvasRef.current.requestRenderAll();
          }

          console.log('✅ [CANVAS] Interactive chart state added (waiting for sync)');
        } else {
          // Fallback: Render chart to PNG if plugin not available
          console.warn('⚠️ fabric.Chart not available, falling back to PNG');
          return new Promise((resolve, reject) => {
            const chartCanvas = document.createElement('canvas');
            chartCanvas.width = 600;
            chartCanvas.height = 400;

            const chart = new Chart(chartCanvas, {
              ...chartConfig,
              options: {
                ...chartConfig.options,
                animation: false,
                responsive: false,
              }
            });

            setTimeout(() => {
              const dataUrl = chartCanvas.toDataURL('image/png');
              chart.destroy();

              fabricModule.Image.fromURL(dataUrl, (img) => {
                if (!fabricCanvasRef.current) return;

                img.set({
                  left: PAGE_WIDTH / 2 - 240,
                  top: PAGE_HEIGHT / 2 - 160,
                  scaleX: 0.8,
                  scaleY: 0.8,
                });

                onAddElement(PAGE.id, 'image', {
                  src: dataUrl,
                  x: img.left,
                  y: img.top,
                  width: 600 * 0.8,
                  height: 400 * 0.8,
                  chartConfig: chartConfig,
                  zIndex: getNextZIndex(),
                });

                resolve();
              });
            }, 200);
          });
        }
      } catch (err) {
        console.error('Chart render error:', err);
      }
    },

    // === Diagram insertion ===
    addDiagram: async (diagramImage) => {
      if (Platform.OS !== 'web' || !fabricModule) {
        console.warn('Diagrams only supported on web');
        return;
      }

      console.log('📊 [CANVAS] Adding diagram...');

      if (handlersRef.current.capturePreEditSnapshot) {
        handlersRef.current.capturePreEditSnapshot();
      }

      return new Promise((resolve, reject) => {
        try {
          fabricModule.Image.fromURL(diagramImage, (img) => {
            if (!fabricCanvasRef.current) return;

            const imgWidth = img.width || 800;
            const imgHeight = img.height || 600;
            const maxWidth = PAGE_WIDTH * 0.8;
            const maxHeight = PAGE_HEIGHT * 0.8;
            const scaleX = maxWidth / imgWidth;
            const scaleY = maxHeight / imgHeight;
            const scale = Math.min(scaleX, scaleY, 1);
            const finalWidth = imgWidth * scale;
            const finalHeight = imgHeight * scale;

            img.set({
              left: PAGE_WIDTH / 2 - finalWidth / 2,
              top: PAGE_HEIGHT / 2 - finalHeight / 2,
              scaleX: scale,
              scaleY: scale,
            });

            console.log(`📊 [CANVAS] Diagram added: ${imgWidth}x${imgHeight} → ${finalWidth.toFixed(0)}x${finalHeight.toFixed(0)} (scale: ${scale.toFixed(2)})`);

            onAddElement(PAGE.id, 'image', {
              src: diagramImage,
              x: img.left,
              y: img.top,
              width: finalWidth,
              height: finalHeight,
              zIndex: getNextZIndex(),
            });

            resolve();
          });
        } catch (err) {
          console.error('Diagram add error:', err);
          reject(err);
        }
      });
    },

    // === Image base64 export (for AI editing) ===
    getImageAsBase64: async (elementId) => {
      if (Platform.OS !== 'web' || !fabricModule || !fabricCanvasRef.current) {
        console.warn('getImageAsBase64 only supported on web with Fabric');
        return null;
      }

      const canvas = fabricCanvasRef.current;
      const objects = canvas.getObjects();
      const imageObj = objects.find(obj => obj.elementId === elementId && obj.type === 'image');

      if (!imageObj) {
        console.warn('🖼️ [CANVAS] Image element not found on canvas:', elementId);
        return null;
      }

      try {
        const dataUrl = imageObj.toDataURL({
          format: 'png',
          quality: 1,
          multiplier: 3  // 3x resolution to preserve quality for AI editing
        });
        console.log('🖼️ [CANVAS] Exported image as base64, size:', (dataUrl.length / 1024).toFixed(2), 'KB');
        return dataUrl;
      } catch (err) {
        console.error('🖼️ [CANVAS] Failed to export image:', err);
        return null;
      }
    },

    // === Thumbnail generation ===
    toDataURL: (options) => {
      if (fabricCanvasRef.current) {
        return fabricCanvasRef.current.toDataURL(options);
      }
      return null;
    },

    // Snapshot the fabric canvas as a PNG data URL for the vision-critique
    // pass. Mirrors the presentation canvas API so PrintableComposer can run
    // the same critique loop. Returns null if the canvas isn't ready or the
    // export tainted (e.g. cross-origin images).
    snapshotForCritique: () => {
      const c = fabricCanvasRef.current;
      if (!c) return null;
      try {
        return c.toDataURL({ format: 'png', quality: 0.92, multiplier: 1 });
      } catch (err) {
        console.warn('🖼️ [CRITIQUE] page canvas snapshot failed (tainted?):', err);
        return null;
      }
    },
  }), [handleAddText, handleAddImage, handleAddShape, handleDeleteSelected, handleToDataURL, handleToJSON, handleZoomIn, handleZoomOut, handleResetZoom, PAGE, onAddElement, handleToggleBold, handleToggleItalic, handleUpdateFillColor, handleUpdateStrokeColor, handleUpdateFontSize, handleUpdateLineHeight, handleTextAlign, handleUndo, handleRedo, handleDuplicate, handleBringForward, handleSendBackward, handleAddElement, onCopyElements, onPasteElements, onActivateFormatPainter, onDeactivateFormatPainter, fillColor, strokeColor, fontSize, lineHeight]);

  // Native fallback rendering
  const renderNativePAGE = () => {
    return (
      <View
        style={[
          styles.nativePAGEContainer,
          {
            width: PAGE_WIDTH * canvasScale,
            height: PAGE_HEIGHT * canvasScale,
            backgroundColor: PAGE?.backgroundColor || '#ffffff',
          },
        ]}
      >
        {PAGE?.elements?.map((element) => (
          <TouchableOpacity
            key={element.id}
            style={[
              styles.nativeElement,
              {
                left: element.x * canvasScale,
                top: element.y * canvasScale,
                width: element.width * canvasScale,
                height: element.height * canvasScale,
                borderColor: selectedElementId === element.id ? theme.primary : 'transparent',
                borderWidth: selectedElementId === element.id ? 2 : 0,
              },
            ]}
            onPress={() => onSelectElement(element.id)}
            activeOpacity={0.8}
          >
            {element.type === ELEMENT_TYPES.TEXT && (
              editingTextId === element.id ? (
                <TextInput
                  style={[
                    styles.nativeTextInput,
                    {
                      fontSize: element.fontSize * canvasScale,
                      fontWeight: element.fontWeight,
                      color: element.color,
                      textAlign: element.textAlign,
                    },
                  ]}
                  value={editingTextValue}
                  onChangeText={setEditingTextValue}
                  onBlur={() => {
                    onUpdateElement(PAGE.id, element.id, { content: editingTextValue });
                    setEditingTextId(null);
                  }}
                  autoFocus
                  multiline
                />
              ) : (
                <Text
                  style={{
                    fontSize: element.fontSize * canvasScale,
                    fontWeight: element.fontWeight,
                    color: element.color,
                    textAlign: element.textAlign,
                  }}
                  onLongPress={() => {
                    setEditingTextId(element.id);
                    setEditingTextValue(element.content);
                  }}
                >
                  {element.content}
                </Text>
              )
            )}
            {element.type === ELEMENT_TYPES.SHAPE && (
              <View
                style={{
                  flex: 1,
                  backgroundColor: element.fill,
                  borderRadius: element.borderRadius || 0,
                  borderWidth: element.strokeWidth || 0,
                  borderColor: element.stroke,
                }}
              />
            )}
          </TouchableOpacity>
        ))}
      </View>
    );
  };

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]} ref={containerRef}>
      {/* Toolbar */}
      {isEditable && !hideToolbar && (
        <View style={[styles.toolbar, isMobile && { paddingHorizontal: 8, paddingVertical: 6 }]}>

          {isMobile ? (
            /* MOBILE TOOLBAR: Single flat wrapping container - all buttons as direct children */
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, rowGap: 6, alignItems: 'center', zIndex: 2000 }}>
              {/* INSERT BUTTONS */}
              <Tooltip text="Insert Text" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={() => handleAddElement('text')}>
                  <Ionicons name="text" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Insert Image" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={() => fileInputRef.current?.click()}>
                  <Ionicons name="image-outline" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              {/* Insert Video — HIDDEN for now (kept for future). Flip `false`. */}
              {false && (
              <Tooltip text="Insert Video" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={() => setShowVideoModal(true)}>
                  <Ionicons name="videocam-outline" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              )}
              <Tooltip text="Insert Animation" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={() => animationInputRef.current?.click()}>
                  <Ionicons name="film-outline" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              {/* Embed App — HIDDEN for now (kept for future). Flip `false`. */}
              {false && (
              <Tooltip text="Embed App" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={() => setShowEmbedModal(true)}>
                  <Ionicons name="code-slash-outline" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              )}
              <Tooltip text="Forms & Buttons" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={() => setShowFormsModal(true)}>
                  <Ionicons name="document-text-outline" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Insert Shape" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={() => setShowShapesPicker(true)}>
                  <Ionicons name="shapes-outline" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Insert Icon" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={() => setShowIconPicker(true)}>
                  <Ionicons name="happy-outline" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Insert Table" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={() => setShowTablePicker(true)}>
                  <Ionicons name="grid-outline" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Insert Chart" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={onOpenChartHelp}>
                  <Ionicons name="bar-chart-outline" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Insert Diagram" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={onOpenDiagram}>
                  <Ionicons name="git-network-outline" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="AI Image Generator" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={() => onGenerateImage && onGenerateImage()}>
                  <Ionicons name="sparkles-outline" size={20} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>

              {/* EDITING BUTTONS */}
              <Tooltip text="Undo" theme={theme}>
                <TouchableOpacity onPress={handleUndo} style={styles.arrangeBtn}>
                  <Ionicons name="arrow-undo" size={18} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Redo" theme={theme}>
                <TouchableOpacity onPress={handleRedo} style={styles.arrangeBtn}>
                  <Ionicons name="arrow-redo" size={18} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text={formatPainterActive ? "Cancel Format Painter" : "Format Painter"} theme={theme}>
                <TouchableOpacity
                  style={[styles.toolButton, formatPainterActive && { backgroundColor: theme.primary + '30', borderRadius: 4 }]}
                  onPress={() => {
                    if (formatPainterActive) {
                      onDeactivateFormatPainter && onDeactivateFormatPainter();
                    } else {
                      const canvas = fabricCanvasRef.current;
                      const activeObj = canvas?.getActiveObject();
                      if (activeObj?.elementId && PAGE?.elements) {
                        const element = PAGE.elements.find(el => el.id === activeObj.elementId);
                        if (element && onActivateFormatPainter) {
                          onActivateFormatPainter(element);
                        }
                      }
                    }
                  }}
                >
                  <Ionicons name="color-fill-outline" size={20} color={formatPainterActive ? theme.primary : theme.text} />
                </TouchableOpacity>
              </Tooltip>

              {/* STYLE & TYPOGRAPHY */}
              <Tooltip text="Style Presets" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={onOpenStylePicker}>
                  <Ionicons name="color-palette-outline" size={18} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Font Combinations" theme={theme}>
                <TouchableOpacity style={styles.toolButton} onPress={() => setShowFontComboPicker(true)}>
                  <Ionicons name="text-outline" size={18} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Bold" theme={theme}>
                <TouchableOpacity onPress={handleToggleBold} style={styles.formatBtn}>
                  <Text style={{ fontWeight: 'bold', fontSize: 16, color: theme.text }}>B</Text>
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Italic" theme={theme}>
                <TouchableOpacity onPress={handleToggleItalic} style={styles.formatBtn}>
                  <Text style={{ fontStyle: 'italic', fontSize: 16, color: theme.text }}>I</Text>
                </TouchableOpacity>
              </Tooltip>
              <View style={{ zIndex: 1100 }}>
                <ColorPickerDropdown label="Fill" value={fillColor} onChange={handleUpdateFillColor} themeColors={['#ffffff', '#000000', '#2196F3', '#4CAF50', '#F44336', '#FFC107']} theme={{ ...theme, surface: '#ffffff' }} compact={true} />
              </View>
              <View style={{ zIndex: 1100 }}>
                <ColorPickerDropdown label="Border" value={strokeColor} onChange={handleUpdateStrokeColor} themeColors={['#000000', '#ffffff', '#2196F3', '#4CAF50', '#F44336', '#FFC107']} theme={{ ...theme, surface: '#ffffff' }} compact={true} />
              </View>
              <View style={{ zIndex: 1100 }}>
                <ColorPickerDropdown label="Bg" value={PAGE?.backgroundColor || '#ffffff'} onChange={(c) => onUpdatePAGEBackground && onUpdatePAGEBackground(c)} themeColors={['#ffffff', '#f5f5f5', '#1a1a2e']} theme={{ ...theme, surface: '#ffffff' }} compact={true} />
              </View>
              <View style={[styles.fontSizeContainer, { marginHorizontal: 2 }]}>
                <TouchableOpacity style={styles.fontSizeBtn} onPress={() => handleUpdateFontSize(Math.round((fontSize || 20) - 2))}>
                  <Text style={{ color: theme.text }}>-</Text>
                </TouchableOpacity>
                <Text style={[styles.fontSizeText, { color: theme.text }]}>{Math.round(fontSize || 20)}</Text>
                <TouchableOpacity style={styles.fontSizeBtn} onPress={() => handleUpdateFontSize(Math.round((fontSize || 20) + 2))}>
                  <Text style={{ color: theme.text }}>+</Text>
                </TouchableOpacity>
              </View>
              <View style={[styles.fontSizeContainer, { marginHorizontal: 2 }]}>
                <TouchableOpacity style={styles.fontSizeBtn} onPress={() => handleUpdateLineHeight((lineHeight || 1.4) - 0.1)}>
                  <MaterialIcons name="format-line-spacing" size={14} color={theme.text} style={{ transform: [{ scaleY: 0.8 }] }} />
                </TouchableOpacity>
                <Text style={[styles.fontSizeText, { color: theme.text, minWidth: 24, fontSize: 11 }]}>{(lineHeight || 1.4).toFixed(1)}</Text>
                <TouchableOpacity style={styles.fontSizeBtn} onPress={() => handleUpdateLineHeight((lineHeight || 1.4) + 0.1)}>
                  <MaterialIcons name="format-line-spacing" size={14} color={theme.text} style={{ transform: [{ scaleY: 1.2 }] }} />
                </TouchableOpacity>
              </View>
              <TouchableOpacity style={styles.alignBtn} onPress={() => handleTextAlign && handleTextAlign('left')}>
                <MaterialIcons name="format-align-left" size={20} color={theme.text} />
              </TouchableOpacity>
              <TouchableOpacity style={styles.alignBtn} onPress={() => handleTextAlign && handleTextAlign('center')}>
                <MaterialIcons name="format-align-center" size={20} color={theme.text} />
              </TouchableOpacity>
              <TouchableOpacity style={styles.alignBtn} onPress={() => handleTextAlign && handleTextAlign('right')}>
                <MaterialIcons name="format-align-right" size={20} color={theme.text} />
              </TouchableOpacity>

              {/* ARRANGE */}
              <Tooltip text="Bring Forward" theme={theme}>
                <TouchableOpacity style={styles.arrangeBtn} onPress={handleBringForward}>
                  <Ionicons name="arrow-up-outline" size={18} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Send Backward" theme={theme}>
                <TouchableOpacity style={styles.arrangeBtn} onPress={handleSendBackward}>
                  <Ionicons name="arrow-down-outline" size={18} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Duplicate" theme={theme}>
                <TouchableOpacity style={styles.arrangeBtn} onPress={handleDuplicate}>
                  <Ionicons name="copy-outline" size={18} color={theme.text} />
                </TouchableOpacity>
              </Tooltip>
              <Tooltip text="Delete" theme={theme}>
                <TouchableOpacity style={[styles.arrangeBtn, { backgroundColor: '#fee2e2' }]} onPress={handleDeleteSelected}>
                  <Ionicons name="trash-outline" size={18} color="#dc2626" />
                </TouchableOpacity>
              </Tooltip>
            </View>
          ) : (
            <>
              {/* ROW 1: INSERT + GLOBAL ACTIONS — flat wrapping flow */}
              <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 2, rowGap: 4, zIndex: 2000 }}>
                <Tooltip text="Insert Text" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={() => handleAddElement('text')}>
                    <Ionicons name="text" size={20} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Insert Image" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={() => fileInputRef.current?.click()}>
                    <Ionicons name="image-outline" size={20} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                {/* Insert Video — HIDDEN for now (kept for future). Flip `false`. */}
                {false && (
                <Tooltip text="Insert Video" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={() => setShowVideoModal(true)}>
                    <Ionicons name="videocam-outline" size={20} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                )}
                <Tooltip text="Insert Animation (Video to Frames)" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={() => animationInputRef.current?.click()}>
                    <Ionicons name="film-outline" size={20} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                {/* Embed App — HIDDEN for now (kept for future). Flip `false`. */}
                {false && (
                <Tooltip text="Embed App" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={() => setShowEmbedModal(true)}>
                    <Ionicons name="code-slash-outline" size={20} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                )}
                <Tooltip text="Forms & Buttons" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={() => setShowFormsModal(true)}>
                    <Ionicons name="document-text-outline" size={20} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Insert Shape" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={() => setShowShapesPicker(true)}>
                    <Ionicons name="shapes-outline" size={20} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Insert Icon" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={() => setShowIconPicker(true)}>
                    <Ionicons name="happy-outline" size={20} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Insert Table" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={() => setShowTablePicker(true)}>
                    <Ionicons name="grid-outline" size={20} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Insert Chart" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={onOpenChartHelp}>
                    <Ionicons name="bar-chart-outline" size={20} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Insert Diagram" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={onOpenDiagram}>
                    <Ionicons name="git-network-outline" size={20} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="AI Image Generator" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={() => onGenerateImage && onGenerateImage()}>
                    <Ionicons name="sparkles-outline" size={20} color={theme.text} />
                    <Text style={[styles.toolButtonText, { color: theme.text, marginLeft: 4 }]}>AI Image</Text>
                  </TouchableOpacity>
                </Tooltip>

                {/* GLOBAL ACTIONS — push to right */}
                {!isMobile && (
                  <>
                    <View style={{ flex: 1, minWidth: 8 }} />

                    <Tooltip text="Present PAGEShow" theme={theme}>
                      <TouchableOpacity style={[styles.actionBtn, styles.primaryBtn]} onPress={onPresent}>
                        <Ionicons name="play" size={14} color="#fff" />
                        <Text style={[styles.actionBtnText, { color: '#fff' }]}>Present</Text>
                      </TouchableOpacity>
                    </Tooltip>

                    <Tooltip text="Save" theme={theme}>
                      <TouchableOpacity style={styles.ghostBtn} onPress={onSave}>
                        <Ionicons name="save-outline" size={18} color={theme.text} />
                      </TouchableOpacity>
                    </Tooltip>

                    {/* Generation Quality Badge — HIDDEN for now (kept for future). */}
                    {false && onShowQualityModal && qualityLabel && (
                      <Tooltip text="Image Generation Quality" theme={theme}>
                        <TouchableOpacity
                          onPress={onShowQualityModal}
                          style={{
                            paddingHorizontal: 8,
                            paddingVertical: 4,
                            borderRadius: 12,
                            backgroundColor: (qualityColor || '#6366F1') + '18',
                            borderWidth: 1,
                            borderColor: (qualityColor || '#6366F1') + '40',
                            flexDirection: 'row',
                            alignItems: 'center',
                            gap: 4,
                            marginLeft: 2,
                          }}
                        >
                          <Ionicons name="sparkles" size={12} color={qualityColor || '#6366F1'} />
                          <Text style={{ fontSize: 11, fontWeight: '600', color: qualityColor || '#6366F1' }}>{qualityLabel}</Text>
                        </TouchableOpacity>
                      </Tooltip>
                    )}

                    {/* Share Button */}
                    {printableId && (
                      <View style={{ height: 34, justifyContent: 'center' }}>
                        <ShareButton
                          contentType="printable"
                          sourceId={printableId}
                          title={printableTitle}
                          theme={theme}
                          size="small"
                          showLabel={false}
                          userType={userType}
                          onUpgrade={onUpgrade}
                        />
                      </View>
                    )}

                    {/* Collaboration Button — HIDDEN for now (kept for future). */}
                    {false && printableId && onShowCollaboration && (
                      <Tooltip text={`Collaborate${collaborators.length > 0 ? ` (${collaborators.length} online)` : ''}`} theme={theme}>
                        <TouchableOpacity
                          style={[
                            styles.ghostBtn,
                            collaborationStatus === 'connected' && { backgroundColor: '#E0F2FE' }
                          ]}
                          onPress={onShowCollaboration}
                        >
                          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                            <Ionicons
                              name="people-outline"
                              size={18}
                              color={collaborationStatus === 'connected' ? '#0284C7' : theme.text}
                            />
                            {collaborators.length > 1 && (
                              <View style={{
                                backgroundColor: '#22C55E',
                                borderRadius: 8,
                                minWidth: 16,
                                height: 16,
                                alignItems: 'center',
                                justifyContent: 'center',
                                marginLeft: 2,
                              }}>
                                <Text style={{ color: '#fff', fontSize: 10, fontWeight: '600' }}>
                                  {collaborators.length}
                                </Text>
                              </View>
                            )}
                          </View>
                        </TouchableOpacity>
                      </Tooltip>
                    )}

                    {/* Stats/Analytics Button */}
                    {printableId && onShowAnalytics && (
                      <Tooltip text="View Analytics" theme={theme}>
                        <TouchableOpacity style={styles.ghostBtn} onPress={onShowAnalytics}>
                          <Ionicons name="stats-chart-outline" size={18} color={theme.text} />
                        </TouchableOpacity>
                      </Tooltip>
                    )}

                    <Tooltip text="Export" theme={theme}>
                      <TouchableOpacity style={styles.ghostBtn} onPress={onExport}>
                        <Ionicons name="download-outline" size={18} color={theme.text} />
                      </TouchableOpacity>
                    </Tooltip>

                    <Tooltip text="Close Editor" theme={theme}>
                      <TouchableOpacity style={[styles.ghostBtn, { backgroundColor: '#FEE2E2', marginLeft: 4 }]} onPress={onClose}>
                        <Ionicons name="close-outline" size={18} color="#EF4444" />
                      </TouchableOpacity>
                    </Tooltip>
                  </>
                )}
              </View>

              {/* ROW 2: EDITING & FORMATTING — flat wrapping flow */}
              <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 2, rowGap: 4, zIndex: 1000, marginTop: 4, paddingTop: 4, borderTopWidth: 1, borderTopColor: '#f0f0f0' }}>

                {/* Undo/Redo */}
                <Tooltip text="Undo" theme={theme}>
                  <TouchableOpacity onPress={handleUndo} style={styles.arrangeBtn}>
                    <Ionicons name="arrow-undo" size={18} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Redo" theme={theme}>
                  <TouchableOpacity onPress={handleRedo} style={styles.arrangeBtn}>
                    <Ionicons name="arrow-redo" size={18} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>

                <View style={styles.verticalDivider} />

                {/* Format Painter */}
                <Tooltip
                  text={formatPainterActive ? "Click to cancel Format Painter" : "Format Painter (select element first)"}
                  theme={theme}
                >
                  <TouchableOpacity
                    style={[
                      styles.toolButton,
                      formatPainterActive && { backgroundColor: theme.primary + '30', borderRadius: 4 }
                    ]}
                    onPress={() => {
                      if (formatPainterActive) {
                        onDeactivateFormatPainter && onDeactivateFormatPainter();
                      } else {
                        const canvas = fabricCanvasRef.current;
                        const activeObj = canvas?.getActiveObject();
                        if (activeObj?.elementId && PAGE?.elements) {
                          const element = PAGE.elements.find(el => el.id === activeObj.elementId);
                          if (element && onActivateFormatPainter) {
                            onActivateFormatPainter(element);
                          }
                        } else {
                          console.log('⚠️ [FORMAT_PAINTER] No element selected. Select an element first.');
                        }
                      }
                    }}
                  >
                    <Ionicons name="color-fill-outline" size={20} color={formatPainterActive ? theme.primary : theme.text} />
                  </TouchableOpacity>
                </Tooltip>

                <View style={styles.verticalDivider} />

                {/* Style & Typography */}
                <Tooltip text="Style Presets" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={onOpenStylePicker}>
                    <Ionicons name="color-palette-outline" size={18} color={theme.text} />
                    <Text style={[styles.toolButtonText, { color: theme.text, marginLeft: 4 }]}>Style</Text>
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Font Combinations" theme={theme}>
                  <TouchableOpacity style={styles.toolButton} onPress={() => setShowFontComboPicker(true)}>
                    <Ionicons name="text-outline" size={18} color={theme.text} />
                    <Text style={[styles.toolButtonText, { color: theme.text, marginLeft: 4 }]}>Fonts</Text>
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Bold" theme={theme}>
                  <TouchableOpacity onPress={handleToggleBold} style={styles.formatBtn}>
                    <Text style={{ fontWeight: 'bold', fontSize: 16, color: theme.text }}>B</Text>
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Italic" theme={theme}>
                  <TouchableOpacity onPress={handleToggleItalic} style={styles.formatBtn}>
                    <Text style={{ fontStyle: 'italic', fontSize: 16, color: theme.text }}>I</Text>
                  </TouchableOpacity>
                </Tooltip>
                <View style={{ zIndex: 1100 }}>
                  <ColorPickerDropdown
                    label="Fill"
                    value={fillColor}
                    onChange={handleUpdateFillColor}
                    themeColors={['#ffffff', '#000000', '#2196F3', '#4CAF50', '#F44336', '#FFC107']}
                    theme={{ ...theme, surface: '#ffffff' }}
                    compact={true}
                  />
                </View>
                <View style={{ zIndex: 1100 }}>
                  <ColorPickerDropdown
                    label="Border"
                    value={strokeColor}
                    onChange={handleUpdateStrokeColor}
                    themeColors={['#000000', '#ffffff', '#2196F3', '#4CAF50', '#F44336', '#FFC107']}
                    theme={{ ...theme, surface: '#ffffff' }}
                    compact={true}
                  />
                </View>
                <View style={{ zIndex: 1100 }}>
                  <ColorPickerDropdown
                    label="Bg"
                    value={PAGE?.backgroundColor || '#ffffff'}
                    onChange={(c) => onUpdatePAGEBackground && onUpdatePAGEBackground(c)}
                    themeColors={['#ffffff', '#f5f5f5', '#1a1a2e']}
                    theme={{ ...theme, surface: '#ffffff' }}
                    compact={true}
                  />
                </View>
                <View style={[styles.fontSizeContainer, { marginHorizontal: 2 }]}>
                  <TouchableOpacity style={styles.fontSizeBtn} onPress={() => handleUpdateFontSize(Math.round((fontSize || 20) - 2))}>
                    <Text style={{ color: theme.text }}>-</Text>
                  </TouchableOpacity>
                  <Text style={[styles.fontSizeText, { color: theme.text }]}>{Math.round(fontSize || 20)}</Text>
                  <TouchableOpacity style={styles.fontSizeBtn} onPress={() => handleUpdateFontSize(Math.round((fontSize || 20) + 2))}>
                    <Text style={{ color: theme.text }}>+</Text>
                  </TouchableOpacity>
                </View>
                <View style={[styles.fontSizeContainer, { marginHorizontal: 2 }]}>
                  <Tooltip text="Decrease Line Height" theme={theme}>
                    <TouchableOpacity style={styles.fontSizeBtn} onPress={() => handleUpdateLineHeight((lineHeight || 1.4) - 0.1)}>
                      <MaterialIcons name="format-line-spacing" size={14} color={theme.text} style={{ transform: [{ scaleY: 0.8 }] }} />
                      <Text style={{ color: theme.text, fontSize: 10, marginLeft: 2 }}>-</Text>
                    </TouchableOpacity>
                  </Tooltip>
                  <Text style={[styles.fontSizeText, { color: theme.text, minWidth: 24, fontSize: 11 }]}>{(lineHeight || 1.4).toFixed(1)}</Text>
                  <Tooltip text="Increase Line Height" theme={theme}>
                    <TouchableOpacity style={styles.fontSizeBtn} onPress={() => handleUpdateLineHeight((lineHeight || 1.4) + 0.1)}>
                      <Text style={{ color: theme.text, fontSize: 10, marginRight: 2 }}>+</Text>
                      <MaterialIcons name="format-line-spacing" size={14} color={theme.text} style={{ transform: [{ scaleY: 1.2 }] }} />
                    </TouchableOpacity>
                  </Tooltip>
                </View>
                <TouchableOpacity style={styles.alignBtn} onPress={() => handleTextAlign && handleTextAlign('left')}>
                  <MaterialIcons name="format-align-left" size={20} color={theme.text} />
                </TouchableOpacity>
                <TouchableOpacity style={styles.alignBtn} onPress={() => handleTextAlign && handleTextAlign('center')}>
                  <MaterialIcons name="format-align-center" size={20} color={theme.text} />
                </TouchableOpacity>
                <TouchableOpacity style={styles.alignBtn} onPress={() => handleTextAlign && handleTextAlign('right')}>
                  <MaterialIcons name="format-align-right" size={20} color={theme.text} />
                </TouchableOpacity>

                <View style={styles.verticalDivider} />

                {/* Arrange */}
                <Tooltip text="Bring Forward" theme={theme}>
                  <TouchableOpacity style={styles.arrangeBtn} onPress={handleBringForward}>
                    <Ionicons name="arrow-up-outline" size={18} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Send Backward" theme={theme}>
                  <TouchableOpacity style={styles.arrangeBtn} onPress={handleSendBackward}>
                    <Ionicons name="arrow-down-outline" size={18} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Duplicate" theme={theme}>
                  <TouchableOpacity style={styles.arrangeBtn} onPress={handleDuplicate}>
                    <Ionicons name="copy-outline" size={18} color={theme.text} />
                  </TouchableOpacity>
                </Tooltip>
                <Tooltip text="Delete" theme={theme}>
                  <TouchableOpacity style={[styles.arrangeBtn, { backgroundColor: '#fee2e2' }]} onPress={handleDeleteSelected}>
                    <Ionicons name="trash-outline" size={18} color="#dc2626" />
                  </TouchableOpacity>
                </Tooltip>
              </View>
            </>
          )}

          {/* Hidden inputs are outside the toolbar view, but we can leave them here or move them down. 
              Ideally moving them down to keep toolbar purely visual, but keeping them here maintains logic 
          */}
          <input
            type="file"
            ref={videoInputRef}
            accept="video/mp4,video/webm,video/ogg"
            style={{ display: 'none' }}
            onChange={(e) => {
              console.log('🎬 [VIDEO_UPLOAD] File input onChange triggered');
              const file = e.target.files?.[0];
              if (!file) {
                console.log('❌ [VIDEO_UPLOAD] No file selected');
                return;
              }

              console.log('📹 [VIDEO_UPLOAD] File selected:', {
                name: file.name,
                type: file.type,
                size: `${(file.size / 1024 / 1024).toFixed(2)}MB`
              });

              // Check file size (5MB limit)
              const MAX_SIZE_MB = 5;
              const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;
              if (file.size > MAX_SIZE_BYTES) {
                console.log('❌ [VIDEO_UPLOAD] File too large:', file.size);
                alert(`Video file is too large! Maximum allowed size is ${MAX_SIZE_MB}MB. Your file is ${(file.size / 1024 / 1024).toFixed(2)}MB.`);
                e.target.value = '';
                return;
              }

              console.log('✅ [VIDEO_UPLOAD] File size OK, starting FileReader...');

              // Read file and add to canvas
              const reader = new FileReader();
              reader.onload = (event) => {
                console.log('📖 [VIDEO_UPLOAD] FileReader onload triggered');
                const videoDataUrl = event.target.result;
                console.log('📦 [VIDEO_UPLOAD] Data URL generated, length:', videoDataUrl?.length || 0);

                // Create temp video to get dimensions
                const tempVideo = document.createElement('video');
                tempVideo.src = videoDataUrl;
                console.log('🎥 [VIDEO_UPLOAD] Temp video element created, waiting for metadata...');

                tempVideo.onloadedmetadata = () => {
                  console.log('📐 [VIDEO_UPLOAD] Video metadata loaded:', {
                    width: tempVideo.videoWidth,
                    height: tempVideo.videoHeight,
                    duration: tempVideo.duration
                  });

                  const aspectRatio = tempVideo.videoWidth / tempVideo.videoHeight;
                  const maxWidth = PAGE_WIDTH * 0.5;
                  const width = Math.min(tempVideo.videoWidth, maxWidth);
                  const height = width / aspectRatio;

                  console.log('📏 [VIDEO_UPLOAD] Calculated dimensions:', { width, height, aspectRatio });

                  // FIX: Generate thumbnail by capturing a video frame
                  const addElementWithThumbnail = (thumbnail) => {
                    if (PAGE?.id) {
                      const maxZ = PAGE.elements?.length > 0
                        ? Math.max(...PAGE.elements.map(el => parseInt(el.zIndex) || 0)) + 1
                        : 1;

                      console.log('🎯 [VIDEO_UPLOAD] Calling onAddElement with:', {
                        PAGEId: PAGE.id,
                        type: 'video',
                        width,
                        height,
                        zIndex: maxZ,
                        srcLength: videoDataUrl.length,
                        hasThumbnail: !!thumbnail
                      });

                      onAddElement(PAGE.id, 'video', {
                        src: videoDataUrl,
                        thumbnail: thumbnail, // Generated frame thumbnail
                        x: (PAGE_WIDTH - width) / 2,
                        y: (PAGE_HEIGHT - height) / 2,
                        width: width,
                        height: height,
                        zIndex: maxZ,
                        isUserMedia: true, // Mark as user media for AI preservation
                      });

                      console.log('✅ [VIDEO_UPLOAD] onAddElement called successfully');
                    } else {
                      console.log('❌ [VIDEO_UPLOAD] No PAGE ID available:', PAGE);
                    }
                  };

                  // Seek to 1s (or start if shorter) and capture a frame as thumbnail
                  const seekTime = Math.min(1, tempVideo.duration || 0);
                  tempVideo.currentTime = seekTime;
                  tempVideo.onseeked = () => {
                    try {
                      const thumbCanvas = document.createElement('canvas');
                      thumbCanvas.width = tempVideo.videoWidth;
                      thumbCanvas.height = tempVideo.videoHeight;
                      const ctx = thumbCanvas.getContext('2d');
                      ctx.drawImage(tempVideo, 0, 0, thumbCanvas.width, thumbCanvas.height);
                      const thumbnail = thumbCanvas.toDataURL('image/jpeg', 0.7);
                      console.log('🖼️ [VIDEO_UPLOAD] Thumbnail generated, length:', thumbnail.length);
                      addElementWithThumbnail(thumbnail);
                    } catch (thumbErr) {
                      console.warn('⚠️ [VIDEO_UPLOAD] Thumbnail capture failed, adding without thumbnail:', thumbErr);
                      addElementWithThumbnail(null);
                    }
                  };
                  // Fallback: if seek doesn't fire (e.g. very short video), add after timeout
                  setTimeout(() => {
                    if (!tempVideo.seeked) {
                      addElementWithThumbnail(null);
                    }
                  }, 3000);
                };

                tempVideo.onerror = (err) => {
                  console.error('❌ [VIDEO_UPLOAD] Video metadata loading error:', err);
                };
              };

              reader.onerror = (err) => {
                console.error('❌ [VIDEO_UPLOAD] FileReader error:', err);
              };

              reader.readAsDataURL(file);
              console.log('🔄 [VIDEO_UPLOAD] FileReader.readAsDataURL() called');
              e.target.value = ''; // Reset for next upload
            }}
          />
        </View>
      )}

      {/* Canvas container - Web uses native overflow, RN uses ScrollView */}
      {Platform.OS === 'web' ? (
        <div
          style={{
            flex: 1,
            width: '100%',
            height: '100%',
            overflow: isEditable ? 'auto' : 'hidden',
            display: 'flex',
            justifyContent: 'center',
            alignItems: isEditable ? 'flex-start' : 'center',
            paddingTop: isEditable ? 20 : 0,
            paddingBottom: isEditable ? 20 : 0,
          }}
        >
          <View
            style={[
              styles.canvasWrapper,
              {
                backgroundColor: isEditable ? '#E5E7EB' : 'transparent',
                padding: isEditable ? CANVAS_PADDING : 0,
              },
            ]}
          >
            <div
              onMouseDown={(e) => {
                console.log('Canvas area clicked - onMouseDown');

                // Check if Fabric is in text editing mode
                const fabricCanvas = fabricCanvasRef.current;
                const activeObject = fabricCanvas && fabricCanvas.getActiveObject();
                const isEditingText = activeObject && activeObject.isEditing;

                if (isEditingText) {
                  console.log('Fabric is editing text - stopping propagation');
                  // CRITICAL: Stop event from bubbling to React Native Web
                  e.stopPropagation();
                  // Don't call onCanvasFocus or anything else
                  return;
                }

                if (onCanvasFocus) {
                  onCanvasFocus();
                }

                // Only blur external inputs when clicking empty canvas area
                const clickedOnObject = activeObject !== null;

                if (!clickedOnObject) {
                  const aiSidebar = document.getElementById('ai-sidebar');
                  if (document.activeElement && aiSidebar && aiSidebar.contains(document.activeElement)) {
                    console.log('Blurring AI sidebar input');
                    document.activeElement.blur();
                  }
                } else {
                  console.log('Clicked on object - letting Fabric handle focus');
                  // Stop propagation to prevent React Native Web from stealing focus
                  e.stopPropagation();
                }

                // Ensure canvas element gets focus for keyboard events
                if (canvasRef.current) {
                  canvasRef.current.focus();
                }
              }}
              onFocus={(e) => {
                // Prevent the wrapper div from stealing focus from Fabric's textarea
                const fabricCanvas = fabricCanvasRef.current;
                const activeObject = fabricCanvas && fabricCanvas.getActiveObject();
                if (activeObject && activeObject.isEditing && activeObject.hiddenTextarea) {
                  console.log('Wrapper div received focus while editing - redirecting to textarea');
                  e.preventDefault();
                  activeObject.hiddenTextarea.focus();
                }
              }}
              style={{ position: 'relative' }}
            >
              <canvas
                ref={canvasRef}
                tabIndex={0}
                onFocus={() => {
                  // Also close when canvas receives focus
                  if (onCanvasFocus) {
                    onCanvasFocus();
                  }
                }}
                style={{
                  borderRadius: isEditable ? 4 : 0,
                  boxShadow: isEditable ? '0 4px 20px rgba(0,0,0,0.15)' : 'none',
                  outline: 'none',
                }}
              />

              {/* Inline Video Player Overlay - Positioned relative to this wrapper */}
              <InlineVideoOverlay
                videoData={inlineVideoData}
                onClose={() => {
                  // FIX: Also delete the underlying element when closing overlay
                  if (inlineVideoData?.id && PAGE?.id && onDeleteElement) {
                    onDeleteElement(PAGE.id, inlineVideoData.id);
                  }
                  setInlineVideoData(null);
                }}
                isEditable={isEditable}
              />

              {/* Floating Inline Text Formatting Toolbar */}
              {isEditable && (
                <FloatingTextToolbar
                  visible={inlineToolbar.visible}
                  position={{ x: inlineToolbar.x, y: inlineToolbar.y }}
                  currentStyles={inlineToolbar.styles}
                  onToggleBold={handleInlineToggleBold}
                  onToggleItalic={handleInlineToggleItalic}
                  onToggleUnderline={handleInlineToggleUnderline}
                  onChangeColor={handleInlineSetColor}
                  onChangeHighlight={handleInlineSetHighlight}
                  onChangeFontFamily={handleInlineSetFontFamily}
                  onChangeFontSize={handleInlineSetFontSize}
                  theme={theme}
                  containerRef={containerRef}
                />
              )}
            </div>
          </View>
        </div>
      ) : (
        <ScrollView
          style={styles.canvasScrollView}
          contentContainerStyle={styles.canvasScrollContentHorizontal}
          horizontal
          showsHorizontalScrollIndicator={false}
        >
          <ScrollView
            style={styles.verticalScrollView}
            contentContainerStyle={styles.canvasScrollContentVertical}
            showsVerticalScrollIndicator={true}
          >
            <View
              style={[
                styles.canvasWrapper,
                {
                  backgroundColor: isEditable ? '#E5E7EB' : 'transparent',
                  padding: isEditable ? CANVAS_PADDING : 0,
                },
              ]}
            >
              {renderNativePAGE()}
            </View>
          </ScrollView>
        </ScrollView>
      )}

      {/* PAGE info - hidden in present mode */}
      {isEditable && (
        <View style={[styles.PAGEInfo, { backgroundColor: theme.surface, borderTopColor: theme.border }, isMobile && { justifyContent: 'center', gap: 8 }]}>
          <Text style={[styles.PAGEInfoText, { color: theme.textSecondary }, isMobile && { textAlign: 'center' }]}>
            PAGE {PAGE?.order || 1} • {PAGE?.title || 'Untitled'}
          </Text>
          {!isMobile && (
            <Text style={[styles.PAGEInfoText, { color: theme.textSecondary }]}>
              {PAGE?.elements?.length || 0} elements
            </Text>
          )}
        </View>
      )}

      {/* Hidden File Input for Image Upload */}
      <input
        type="file"
        ref={fileInputRef}
        style={{ display: 'none' }}
        accept="image/*"
        onChange={handleImageFileSelect}
      />

      {/* Hidden File Input for Animation Video Upload */}
      <input
        type="file"
        ref={animationInputRef}
        style={{ display: 'none' }}
        accept="video/*"
        onChange={handleAnimationVideoSelect}
      />


      {/* Icon Picker Modal */}
      <IconPickerModal
        visible={showIconPicker}
        onClose={() => setShowIconPicker(false)}
        onSelectIcon={handleInsertIcon}
        theme={theme}
      />

      {/* Shapes Picker Modal */}
      <ShapesPickerModal
        visible={showShapesPicker}
        onClose={() => setShowShapesPicker(false)}
        onSelectShape={handleAddShape}
        theme={theme}
      />

      {/* Font Combination Picker Modal */}
      <FontCombinationPickerModal
        visible={showFontComboPicker}
        onClose={() => setShowFontComboPicker(false)}
        onSelectCombination={handleApplyFontCombination}
        theme={theme}
      />

      {/* Table Picker Modal */}
      <TablePickerModal
        visible={showTablePicker}
        onClose={() => setShowTablePicker(false)}
        theme={theme}
        printableStyle={printableStyle}
        onInsert={(rows, cols, includeHeader, themeColors) => {
          // Calculate table dimensions
          const cellWidth = 100;
          const cellHeight = 30;
          const tableWidth = cols * cellWidth;
          const tableHeight = rows * cellHeight;

          // Center in canvas
          const x = (PAGE_WIDTH - tableWidth) / 2;
          const y = (PAGE_HEIGHT - tableHeight) / 2;

          // Create table element data
          const tableElement = {
            id: `table_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            type: 'table',
            x: x,
            y: y,
            width: tableWidth,
            height: tableHeight,
            zIndex: 50,
            tableConfig: {
              rows,
              cols,
              cellWidth,
              cellHeight,
              hasHeader: includeHeader,
              headerColor: themeColors.headerColor,
              headerTextColor: themeColors.headerTextColor,
              cellColor: themeColors.cellColor,
              altRowColor: themeColors.altRowColor,
              borderColor: themeColors.borderColor,
              textColor: themeColors.textColor,
              cellData: null, // Will be generated with defaults
            },
          };

          // Add to PAGE via onAddElement prop
          if (onAddElement && PAGE?.id) {
            onAddElement(PAGE.id, 'table', tableElement);
            console.log(`📊 [TABLE] Inserted ${cols}×${rows} table with header=${includeHeader}`);
          }

          setShowTablePicker(false);
        }}
      />

      {/* Video Source Modal */}
      <VideoSourceModal
        visible={showVideoModal}
        onClose={() => setShowVideoModal(false)}
        theme={theme}
        onSelectVideo={(videoData) => {
          if (videoData.videoType === 'local') {
            // Use existing local file picker
            videoInputRef.current?.click();
          } else if (videoData.videoType === 'recorded') {
            // Handle recorded video (base64 data URL)
            // FIX: Generate thumbnail from video frame instead of using null
            if (onAddElement && PAGE) {
              const recVideo = document.createElement('video');
              recVideo.src = videoData.src;
              recVideo.muted = true;
              recVideo.playsInline = true;
              recVideo.onloadedmetadata = () => {
                const seekTime = Math.min(1, recVideo.duration || 0);
                recVideo.currentTime = seekTime;
                recVideo.onseeked = () => {
                  let thumbnail = null;
                  try {
                    const thumbCanvas = document.createElement('canvas');
                    thumbCanvas.width = recVideo.videoWidth;
                    thumbCanvas.height = recVideo.videoHeight;
                    const ctx = thumbCanvas.getContext('2d');
                    ctx.drawImage(recVideo, 0, 0, thumbCanvas.width, thumbCanvas.height);
                    thumbnail = thumbCanvas.toDataURL('image/jpeg', 0.7);
                    console.log('🖼️ [RECORDED] Thumbnail generated, length:', thumbnail.length);
                  } catch (thumbErr) {
                    console.warn('⚠️ [RECORDED] Thumbnail capture failed:', thumbErr);
                  }
                  onAddElement(PAGE.id, ELEMENT_TYPES.VIDEO, {
                    src: videoData.src,
                    thumbnail: thumbnail,
                    videoType: 'recorded',
                    title: videoData.title,
                    x: 100,
                    y: 100,
                    width: 480,
                    height: 270,
                    zIndex: getNextZIndex(),
                  });
                  // Cleanup
                  recVideo.src = '';
                  recVideo.remove();
                };
              };
              recVideo.onerror = () => {
                // Fallback: add without thumbnail
                console.warn('⚠️ [RECORDED] Could not load video for thumbnail, adding without');
                onAddElement(PAGE.id, ELEMENT_TYPES.VIDEO, {
                  src: videoData.src,
                  thumbnail: null,
                  videoType: 'recorded',
                  title: videoData.title,
                  x: 100,
                  y: 100,
                  width: 480,
                  height: 270,
                  zIndex: getNextZIndex(),
                });
              };
            }
          } else {
            // Handle URL based video (YouTube/Vimeo/Loom/Spotify)
            if (fabricCanvasRef.current && typeof fabric !== 'undefined') {
              // Use thumbnail as the image
              // Use generic video placeholder if none provided
              fabricModule.Image.fromURL(videoData.thumbnail || 'https://placehold.co/600x400/333333/FFFFFF.png?text=Video+Source', (img) => {
                if (img) {
                  const maxSize = 400;
                  const scale = Math.min(maxSize / img.width, maxSize / img.height, 1);

                  img.set({
                    left: 100,
                    top: 100,
                    scaleX: scale,
                    scaleY: scale,
                    selectable: true,
                  });

                  // Add "Play" icon overlay group
                  // Simple circle and triangle
                  const playCircle = new fabricModule.Circle({
                    radius: 30,
                    fill: 'rgba(0,0,0,0.6)',
                    originX: 'center',
                    originY: 'center',
                    left: 100 + (img.width * scale) / 2,
                    top: 100 + (img.height * scale) / 2
                  });

                  const playTriangle = new fabricModule.Triangle({
                    width: 20,
                    height: 20,
                    fill: '#fff',
                    angle: 90,
                    originX: 'center',
                    originY: 'center',
                    left: 100 + (img.width * scale) / 2 + 2, // slight offset for visual balance
                    top: 100 + (img.height * scale) / 2
                  });

                  const group = new fabricModule.Group([img, playCircle, playTriangle], {
                    left: 100,
                    top: 100,
                    elementId: `video_${Date.now()}`
                  });

                  // Add meta data
                  if (onAddElement && PAGE) {
                    onAddElement(PAGE.id, ELEMENT_TYPES.VIDEO, {
                      src: videoData.src, // The YouTube/Vimeo URL
                      thumbnail: videoData.thumbnail,
                      videoType: videoData.videoType, // 'youtube' or 'vimeo'
                      videoId: videoData.videoId,
                      x: group.left,
                      y: group.top,
                      width: group.width * group.scaleX,
                      height: group.height * group.scaleY,
                      zIndex: getNextZIndex(),
                    });
                  }
                }
              }, { crossOrigin: 'anonymous' });
            }
          }
        }}
      />

      {/* Embed Source Modal (Figma, Miro, Google Drive, etc.) */}
      <EmbedSourceModal
        visible={showEmbedModal}
        onClose={() => setShowEmbedModal(false)}
        onSelectEmbed={(embedData) => {
          console.log('🔗 [EMBED] Selected:', embedData);
          if (onAddElement && PAGE) {
            onAddElement(PAGE.id, ELEMENT_TYPES.EMBED, {
              src: embedData.src,
              embedType: embedData.embedType,
              provider: embedData.provider,
              thumbnail: embedData.thumbnail,
              title: embedData.title,
              html: embedData.html,
              x: 100,
              y: 100,
              width: embedData.width || 640,
              height: embedData.height || 480,
              zIndex: getNextZIndex(),
            });
          }
        }}
        theme={theme}
      />

      {/* Forms & Button Modal (Calendly, Typeform, Buttons, etc.) */}
      <FormsButtonModal
        visible={showFormsModal}
        onClose={() => setShowFormsModal(false)}
        onSelectForm={(formData) => {
          console.log('📝 [FORM] Selected:', formData);
          if (onAddElement && PAGE) {
            onAddElement(PAGE.id, ELEMENT_TYPES.EMBED, {
              src: formData.src,
              embedType: formData.formType,
              provider: formData.provider,
              title: formData.title,
              html: formData.html,
              x: 100,
              y: 100,
              width: formData.width || 640,
              height: formData.height || 500,
              zIndex: getNextZIndex(),
            });
          }
        }}
        onSelectButton={(buttonData) => {
          console.log('🔘 [BUTTON] Selected:', buttonData);
          if (onAddElement && PAGE) {
            onAddElement(PAGE.id, ELEMENT_TYPES.BUTTON, {
              label: buttonData.label,
              url: buttonData.url,
              style: buttonData.style,
              x: 100,
              y: 100,
              width: buttonData.width || 160,
              height: buttonData.height || 48,
              zIndex: getNextZIndex(),
            });
          }
        }}
        theme={theme}
      />

    </View>



  );
});

const styles = {
  container: {
    flex: 1,
  },
  toolbar: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
    backgroundColor: '#fff',
    gap: 8,
    zIndex: 100, // Ensure toolbar is above canvas for dropdowns
  },
  toolbarGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  toolbarLabel: {
    fontSize: 12,
    fontWeight: '500',
    display: 'none', // Hide labels
  },
  verticalDivider: {
    width: 1,
    height: 24,
    backgroundColor: '#d1d5db',
    marginHorizontal: 6,
  },
  headerTitleInput: {
    fontSize: 18,
    fontWeight: '600',
    borderBottomWidth: 1,
    borderBottomColor: 'transparent', // Only show border on focus optionally
    paddingVertical: 4,
    color: '#333',
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 6,
    gap: 6,
  },
  primaryBtn: {
    backgroundColor: '#2563EB',
    shadowColor: '#2563EB',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 2,
  },
  ghostBtn: {
    padding: 8,
    borderRadius: 6,
    backgroundColor: 'transparent',
  },
  actionBtnText: {
    fontSize: 13,
    fontWeight: '600',
  },
  iconToolBtn: {
    width: 32,
    height: 32,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 6,
    backgroundColor: 'transparent',
  },
  toolButton: {
    flexDirection: 'row', // Re-add toolButton for standard buttons
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 6,
    backgroundColor: 'transparent',
  },
  toolButtonText: {
    fontSize: 13,
    fontWeight: '500',
  },
  zoomButton: {
    width: 32,
    height: 32,
    borderRadius: 6,
    justifyContent: 'center',
    alignItems: 'center',
  },
  zoomText: {
    fontSize: 13,
    fontWeight: '500',
    minWidth: 45,
    textAlign: 'center',
  },
  canvasScrollView: {
    flex: 1,
  },
  verticalScrollView: {
    flex: 1,
  },
  canvasScrollContentHorizontal: {
    flexGrow: 1,
    alignItems: 'center',
  },
  canvasScrollContentVertical: {
    flexGrow: 1,
    justifyContent: 'flex-start',
    alignItems: 'center',
    paddingVertical: 20,
  },
  canvasWrapper: {
    borderRadius: 8,
    margin: 0,
  },
  nativePAGEContainer: {
    position: 'relative',
    borderRadius: 4,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 20,
    elevation: 8,
  },
  nativeElement: {
    position: 'absolute',
    padding: 4,
    borderRadius: 4,
  },
  nativeTextInput: {
    flex: 1,
    padding: 0,
  },
  PAGEInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderTopWidth: 1,
  },
  PAGEInfoText: {
    fontSize: 12,
  },
  // New toolbar styles
  toolbarDivider: {
    borderLeftWidth: 1,
    borderLeftColor: '#e5e7eb',
    paddingLeft: 12,
    marginLeft: 4,
  },
  dropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    minWidth: 140,
    borderRadius: 8,
    borderWidth: 1,
    padding: 4,
    zIndex: 1000,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 8,
  },
  dropdownItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 8,
    borderRadius: 4,
    gap: 8,
  },
  dropdownText: {
    fontSize: 13,
  },
  colorPickerContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  colorLabel: {
    fontSize: 11,
  },
  colorSwatch: {
    width: 24,
    height: 24,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: '#ccc',
  },
  fontSizeContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  fontSizeBtn: {
    width: 20,
    height: 20,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 4,
    backgroundColor: '#f3f4f6',
  },
  fontSizeText: {
    fontSize: 11,
    minWidth: 35,
    textAlign: 'center',
  },
  formatBtn: {
    width: 28,
    height: 28,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 4,
  },
  alignBtn: {
    padding: 4,
  },
  arrangeBtn: {
    width: 28,
    height: 28,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 4,
  },
};

export default PrintableCanvas;
