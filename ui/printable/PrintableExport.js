// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// printableExport.js - Export printable to PPTX, PDF, or images
import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Modal,
  Alert,
  ActivityIndicator,
  Platform,
  ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { mapIconToPathAsync, prefetchIcons, cacheIconSVG } from '../composer/utils/iconMapper';
import { rasterizeSvgToPng, prerasterizeSvgDiagrams } from '../composer/utils/svgRasterize';
import globalImageCache from '../../utils/globalImageCache';

/**
 * printableExport - Export printable to various formats
 * 
 * Supported formats:
 * - PPTX (PowerPoint) - using pptxgenjs
 * - PDF - using browser print or server-side
 * - PNG images - individual PAGE images
 */
const PrintableExport = ({
  visible,
  onClose,
  PAGES = [],
  printableTitle = 'Printable',
  style = {},
  theme,
  userType = 'free',
  onOpenCredits,
}) => {
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState({ current: 0, total: 0, format: '' });


  // Lazy-load pptxgenjs from CDN on web to avoid Metro async require failures
  const loadPptxGen = () => {
    return new Promise((resolve, reject) => {
      if (Platform.OS !== 'web') {
        reject(new Error('PPTX export is web-only'));
        return;
      }

      // Check if already loaded
      if (window.PptxGenJS) {
        console.log('✅ [PPTX] PptxGenJS already loaded');
        resolve(window.PptxGenJS);
        return;
      }

      // Check if script is already loading
      const existingScript = document.querySelector('script[data-pptxgenjs]');
      if (existingScript) {
        console.log('⏳ [PPTX] Script already loading, waiting...');
        const checkInterval = setInterval(() => {
          if (window.PptxGenJS) {
            clearInterval(checkInterval);
            resolve(window.PptxGenJS);
          }
        }, 100);
        // Timeout after 10 seconds
        setTimeout(() => {
          clearInterval(checkInterval);
          if (!window.PptxGenJS) {
            reject(new Error('Timeout waiting for PptxGenJS to load'));
          }
        }, 10000);
        return;
      }

      console.log('📦 [PPTX] Loading PptxGenJS from CDN...');
      const script = document.createElement('script');
      // Try the bundle version which includes all dependencies
      script.src = 'https://cdn.jsdelivr.net/npm/pptxgenjs@3.12.0/dist/pptxgen.bundle.js';
      script.async = true;
      script.dataset.pptxgenjs = 'true';

      script.onload = () => {
        console.log('✅ [PPTX] Script loaded, checking for PptxGenJS...');
        // Give it a moment to initialize
        setTimeout(() => {
          if (window.PptxGenJS) {
            console.log('✅ [PPTX] PptxGenJS available');
            resolve(window.PptxGenJS);
          } else if (window.pptxgen) {
            // Some versions export as pptxgen
            console.log('✅ [PPTX] pptxgen available (alternate name)');
            resolve(window.pptxgen);
          } else {
            console.error('❌ [PPTX] Script loaded but PptxGenJS not found on window');
            reject(new Error('PptxGenJS not found after script load'));
          }
        }, 100);
      };

      script.onerror = (err) => {
        console.error('❌ [PPTX] Failed to load script:', err);
        reject(new Error('Failed to load PptxGenJS from CDN'));
      };

      document.head.appendChild(script);
    });
  };

  // Lazy-load html2canvas from CDN for PNG export
  const loadHtml2Canvas = () => {
    return new Promise((resolve, reject) => {
      if (Platform.OS !== 'web') {
        reject(new Error('PNG export is web-only'));
        return;
      }

      // Check if already loaded
      if (window.html2canvas) {
        console.log('✅ [PNG] html2canvas already loaded');
        resolve(window.html2canvas);
        return;
      }

      console.log('📦 [PNG] Loading html2canvas from CDN...');
      const script = document.createElement('script');
      script.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
      script.async = true;

      script.onload = () => {
        console.log('✅ [PNG] html2canvas loaded from CDN');
        if (window.html2canvas) {
          resolve(window.html2canvas);
        } else {
          reject(new Error('html2canvas not found after script load'));
        }
      };

      script.onerror = (err) => {
        console.error('❌ [PNG] Failed to load html2canvas:', err);
        reject(new Error('Failed to load html2canvas from CDN'));
      };

      document.head.appendChild(script);
    });
  };

  // Lazy-load JSZip from CDN for bundling PNG exports
  const loadJSZip = () => {
    return new Promise((resolve, reject) => {
      if (window.JSZip) {
        resolve(window.JSZip);
        return;
      }

      const script = document.createElement('script');
      script.src = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
      script.async = true;

      script.onload = () => {
        if (window.JSZip) {
          resolve(window.JSZip);
        } else {
          reject(new Error('JSZip not found after script load'));
        }
      };

      script.onerror = () => reject(new Error('Failed to load JSZip from CDN'));
      document.head.appendChild(script);
    });
  };

  // Export to PowerPoint (PPTX)
  const exportToPPTX = async () => {
    if (Platform.OS !== 'web') {
      Alert.alert('Web Only', 'PowerPoint export is currently only available on web.');
      return;
    }

    setIsExporting(true);
    setExportProgress({ current: 0, total: PAGES.length, format: 'PPTX' });

    try {
      // Pre-cache all images from PAGES before starting export (including background images)
      const allImageUrls = [
        ...PAGES.flatMap(p =>
          (p.elements || []).filter(e => e.type === 'image' && e.src).map(e => e.src)
        ),
        ...PAGES.filter(p => p.backgroundImage).map(p => p.backgroundImage),
      ];
      await globalImageCache.preCacheAll(allImageUrls);

      const PptxGenJS = await loadPptxGen();
      if (!PptxGenJS) {
        throw new Error('pptxgenjs failed to load');
      }

      console.log('📊 [PPTX] Creating printable with', PAGES.length, 'PAGES');

      // PptxGenJS can be either a class or have a default export
      const pres = typeof PptxGenJS === 'function' ? new PptxGenJS() : new PptxGenJS.default();

      // Set printable properties
      pres.title = printableTitle;
      pres.author = userType === 'paid' ? '' : 'Citra AI';
      pres.subject = 'Generated printable';
      pres.layout = 'LAYOUT_16x9';

      // Define master slide with style
      if (style.PAGEBackground) {
        pres.defineSlideMaster({
          title: 'STYLED_MASTER',
          background: { color: style.PAGEBackground?.replace('#', '') || 'FFFFFF' },
        });
      }

      // Process each PAGE
      for (let i = 0; i < PAGES.length; i++) {
        const PAGEData = PAGES[i];
        setExportProgress({ current: i + 1, total: PAGES.length, format: 'PPTX' });

        const pptPAGE = pres.addSlide(style.PAGEBackground ? 'STYLED_MASTER' : undefined);

        // Set PAGE background (image takes priority, then color)
        if (PAGEData.backgroundImage) {
          try {
            const bgBase64 = await globalImageCache.getAsBase64(PAGEData.backgroundImage);
            if (bgBase64) {
              pptPAGE.background = { data: bgBase64 };
            } else if (PAGEData.backgroundColor) {
              pptPAGE.background = { color: PAGEData.backgroundColor.replace('#', '') };
            }
          } catch (bgErr) {
            console.warn('[PPTX] Failed to add background image, falling back to color:', bgErr);
            if (PAGEData.backgroundColor) {
              pptPAGE.background = { color: PAGEData.backgroundColor.replace('#', '') };
            }
          }
        } else if (PAGEData.backgroundColor) {
          pptPAGE.background = { color: PAGEData.backgroundColor.replace('#', '') };
        }

        // Process PAGE elements (sorted by zIndex so layers match the editor)
        if (PAGEData.elements && Array.isArray(PAGEData.elements)) {
          const sortedElements = [...PAGEData.elements].sort((a, b) => (a.zIndex || 0) - (b.zIndex || 0));
          for (const element of sortedElements) {
            try {
              switch (element.type) {
                case 'text':
                  addTextToPptPAGE(pptPAGE, element, style);
                  break;
                case 'image':
                  await addImageToPptPAGE(pptPAGE, element);
                  break;
                case 'shape':
                  addShapeToPptPAGE(pres, pptPAGE, element);
                  break;
                case 'icon':
                  // Convert icon to PNG and add as image
                  await addIconToPptPAGE(pres, pptPAGE, element);
                  break;
                case 'chart':
                  // Render chart to PNG and add as image
                  await addChartToPptPAGE(pptPAGE, element);
                  break;
                case 'svg_diagram':
                  // Rasterize inline SVG diagram to PNG and add as image
                  await addSvgDiagramToPptPAGE(pptPAGE, element);
                  break;
              }
            } catch (elementError) {
              console.warn('[PPTX] Error adding element, skipping:', element.type, elementError);
            }
          }
        }
      }

      // Generate and download the file
      const fileName = `${sanitizeFileName(printableTitle)}.pptx`;
      await pres.writeFile({ fileName });

      console.log('✅ [EXPORT] PPTX exported successfully:', fileName);
      Alert.alert('Export Complete', `${fileName} has been downloaded.`);
    } catch (error) {
      console.error('Error exporting to PPTX:', error);
      Alert.alert('Export Failed', 'Failed to export to PowerPoint. Please try again.');
    } finally {
      setIsExporting(false);
      setExportProgress({ current: 0, total: 0, format: '' });
    }
  };

  // Helper: Add text element to PPTX PAGE
  const addTextToPptPAGE = (pptPAGE, element, printableStyle) => {
    // Convert pixel positions to inches (assuming 96 DPI and 960x540 canvas)
    const x = (element.x || 0) / 96;
    const y = (element.y || 0) / 96;
    const w = (element.width || 200) / 96;
    const h = (element.height || 50) / 96;

    // Get color from element, then fall back to style
    const textColor = element.fill || element.color ||
      printableStyle?.textStyles?.title?.color ||
      printableStyle?.textPrimary || '#000000';

    const transparency = Math.round((1 - (element.opacity ?? 1)) * 100);

    const textOptions = {
      x: Math.max(0, x),
      y: Math.max(0, y),
      w: Math.min(10 - x, w),
      h: Math.min(5.625 - y, h),
      color: textColor.replace('#', ''),
      fontFace: element.fontFamily || printableStyle?.fontFamily || 'Arial',
      fontSize: Math.round((element.fontSize || 24) * 0.75), // Convert px to pt
      bold: element.fontWeight === 'bold' || element.fontWeight === '700' || element.textType === 'title',
      italic: element.fontStyle === 'italic',
      underline: !!element.underline,
      align: element.textAlign || 'left',
      valign: 'top',
      wrap: true,
      transparency,
      rotate: element.rotation || 0,
    };

    // Adjust for different text types — only override fontSize if element doesn't have its own
    if (element.textType === 'title') {
      if (!element.fontSize) {
        textOptions.fontSize = Math.round((printableStyle?.textStyles?.title?.fontSize || 44) * 0.75);
      }
      textOptions.bold = true;
    } else if (element.textType === 'subtitle') {
      if (!element.fontSize) {
        textOptions.fontSize = Math.round((printableStyle?.textStyles?.subtitle?.fontSize || 24) * 0.75);
      }
    } else if (element.textType === 'bullet') {
      textOptions.bullet = true;
    }

    pptPAGE.addText(element.content || '', textOptions);
  };

  // Helper: Add image element to PPTX PAGE
  const addImageToPptPAGE = async (pptPAGE, element) => {
    if (!element.src) return;

    const x = (element.x || 0) / 96;
    const y = (element.y || 0) / 96;
    const w = (element.width || 200) / 96;
    const h = (element.height || 150) / 96;

    try {
      const imgTransparency = Math.round((1 - (element.opacity ?? 1)) * 100);
      const imgOpts = {
        x: Math.max(0, x),
        y: Math.max(0, y),
        w: Math.min(10 - x, w),
        h: Math.min(5.625 - y, h),
        rotate: element.rotation || 0,
        transparency: imgTransparency,
      };

      // Check if it's a data URL or regular URL
      if (element.src.startsWith('data:')) {
        pptPAGE.addImage({ data: element.src, ...imgOpts });
      } else {
        // Use global image cache to get base64 - avoids CORS issues
        const dataUrl = await globalImageCache.getAsBase64(element.src);

        if (dataUrl) {
          pptPAGE.addImage({ data: dataUrl, ...imgOpts });
        } else {
          throw new Error('Failed to convert image to base64');
        }
      }
    } catch (error) {
      console.error('Failed to add image to PPTX:', error);
      // Add placeholder text instead
      pptPAGE.addText('[Image could not be exported]', {
        x: Math.max(0, x),
        y: Math.max(0, y),
        w: w,
        h: h,
        color: '999999',
        fontSize: 12,
        align: 'center',
        valign: 'middle',
      });
    }
  };

  // Helper: Add shape element to PPTX PAGE
  const addShapeToPptPAGE = (pres, pptPAGE, element) => {
    try {
      const x = (element.x || 0) / 96;
      const y = (element.y || 0) / 96;
      const w = (element.width || 100) / 96;
      const h = (element.height || 100) / 96;

      // Use pres.shapes for proper shape type constants
      // pptxgenjs exposes shape types via pres.shapes (e.g., pres.shapes.RECTANGLE)
      let shapeType;
      if (pres.shapes) {
        const shapeMap = {
          rect: pres.shapes.RECTANGLE,
          rectangle: pres.shapes.RECTANGLE,
          circle: pres.shapes.OVAL,
          ellipse: pres.shapes.OVAL,
          triangle: pres.shapes.TRIANGLE,
          line: pres.shapes.LINE,
          arrow: pres.shapes.RIGHT_ARROW,
        };
        shapeType = shapeMap[element.shapeType] || pres.shapes.RECTANGLE;
      } else {
        // Fallback for older versions
        shapeType = element.shapeType === 'circle' ? 'ellipse' : (element.shapeType || 'rect');
      }

      const shapeTransparency = Math.round((1 - (element.opacity ?? 1)) * 100);

      pptPAGE.addShape(shapeType, {
        x: Math.max(0, x),
        y: Math.max(0, y),
        w: Math.max(0.1, Math.min(10 - x, w)),
        h: Math.max(0.1, Math.min(5.625 - y, h)),
        fill: { color: (element.fill || '#3B82F6').replace('#', ''), transparency: shapeTransparency },
        line: element.stroke ? { color: element.stroke.replace('#', ''), pt: element.strokeWidth || 1 } : undefined,
        rotate: element.rotation || 0,
      });
    } catch (error) {
      console.warn('[PPTX] Failed to add shape, skipping:', error);
    }
  };

  // Helper: Add icon element to PPTX PAGE (render as PNG from SVG path)
  const addIconToPptPAGE = async (pres, pptPAGE, element) => {
    try {
      const x = (element.x || 0) / 96;
      const y = (element.y || 0) / 96;
      const size = (element.size || 48) / 96;
      const pixelSize = element.size || 48;

      const iconColor = element.fill || element.color || '#000000';
      const iconName = element.iconName || 'star';
      const hasS3Src = element.svgSrc && (element.svgSrc.startsWith('http') || element.svgSrc.startsWith('s3://'));

      // Build SVG string - prefer S3 svgSrc over Iconify API
      let svgString;
      if (hasS3Src) {
        // Priority 1: Fetch SVG from S3 presigned URL — avoids Iconify API call
        try {
          const response = await fetch(element.svgSrc);
          if (response.ok) {
            let svgText = await response.text();
            // Inject color and size into fetched SVG
            svgText = svgText
              .replace(/width="[^"]*"/, `width="${pixelSize * 2}"`)
              .replace(/height="[^"]*"/, `height="${pixelSize * 2}"`)
              .replace(/currentColor/g, iconColor);
            svgText = svgText.replace(/fill="(?!(?:none|transparent))[^"]*"/g, `fill="${iconColor}"`);
            svgText = svgText.replace(/stroke="(?!(?:none|transparent))[^"]*"/g, `stroke="${iconColor}"`);
            svgString = svgText;
            console.log('[PPTX] Got icon from S3 for:', iconName);
          }
        } catch (e) {
          console.warn('[PPTX] S3 fetch failed for icon:', iconName, e);
        }
      }

      if (!svgString) {
        // Priority 2: Fall back to Iconify mapper
        const iconData = await mapIconToPathAsync(iconName);
        console.log('[PPTX] Got icon from Iconify for:', iconName, '->', iconData.name);

        if (iconData.svg) {
          svgString = iconData.svg
            .replace(/width="[^"]*"/, `width="${pixelSize * 2}"`)
            .replace(/height="[^"]*"/, `height="${pixelSize * 2}"`)
            .replace(/stroke="[^"]*"/g, `stroke="${iconColor}"`)
            .replace(/currentColor/g, iconColor);
          if (!svgString.includes('stroke=')) {
            svgString = svgString.replace('<svg', `<svg stroke="${iconColor}"`);
          }
        } else if (iconData.path) {
          svgString = `<svg xmlns="http://www.w3.org/2000/svg" width="${pixelSize * 2}" height="${pixelSize * 2}" viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${iconData.path}"/></svg>`;
        } else {
          console.warn('[PPTX] No valid icon data for:', iconName);
          svgString = `<svg xmlns="http://www.w3.org/2000/svg" width="${pixelSize * 2}" height="${pixelSize * 2}" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="${iconColor}"/></svg>`;
        }
      }

      // Create image from SVG
      const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
      const svgUrl = URL.createObjectURL(svgBlob);

      const img = new Image();
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = () => reject(new Error('Failed to load icon SVG'));
        img.src = svgUrl;
      });

      // Draw to canvas
      const canvas = document.createElement('canvas');
      canvas.width = pixelSize * 2; // 2x for higher resolution
      canvas.height = pixelSize * 2;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      // Cleanup
      URL.revokeObjectURL(svgUrl);

      // Convert to PNG data URL
      const dataUrl = canvas.toDataURL('image/png');

      // Add as image to PPTX
      const iconTransparency = Math.round((1 - (element.opacity ?? 1)) * 100);
      pptPAGE.addImage({
        data: dataUrl,
        x: Math.max(0, x),
        y: Math.max(0, y),
        w: size,
        h: size,
        transparency: iconTransparency,
        rotate: element.rotation || 0,
      });

      console.log('[PPTX] Icon exported from cache as PNG:', iconName);
    } catch (error) {
      console.warn('[PPTX] Failed to add icon as image, skipping:', iconName, error);
    }
  };

  // Helper: Add chart element to PPTX PAGE (render Chart.js to PNG)
  const addChartToPptPAGE = async (pptPAGE, element) => {
    try {
      if (!element.chartConfig) {
        console.warn('[PPTX] Chart element has no chartConfig, skipping');
        return;
      }

      const x = (element.x || 0) / 96;
      const y = (element.y || 0) / 96;
      const w = (element.width || 400) / 96;
      const h = (element.height || 300) / 96;

      // Create offscreen canvas
      const chartCanvas = document.createElement('canvas');
      chartCanvas.width = element.width || 400;
      chartCanvas.height = element.height || 300;

      // Dynamically load Chart.js if needed
      const { Chart, registerables } = require('chart.js');
      Chart.register(...registerables);

      // Create Chart.js instance
      const chartInstance = new Chart(chartCanvas, {
        type: element.chartConfig.type || 'bar',
        data: element.chartConfig.data || { labels: [], datasets: [] },
        options: {
          ...element.chartConfig.options,
          responsive: false,
          maintainAspectRatio: false,
          animation: false,
        }
      });

      // Wait for chart to render
      await new Promise(resolve => setTimeout(resolve, 100));

      // Convert to PNG data URL
      const dataUrl = chartCanvas.toDataURL('image/png');

      // Cleanup
      chartInstance.destroy();

      // Add as image to PPTX
      pptPAGE.addImage({
        data: dataUrl,
        x: Math.max(0, x),
        y: Math.max(0, y),
        w: Math.min(10 - x, w),
        h: Math.min(5.625 - y, h),
      });

      console.log('[PPTX] Chart exported as PNG');
    } catch (error) {
      console.warn('[PPTX] Failed to add chart, skipping:', error);
      // Add placeholder text
      const x = (element.x || 0) / 96;
      const y = (element.y || 0) / 96;
      pptPAGE.addText('[Chart could not be exported]', {
        x: Math.max(0, x),
        y: Math.max(0, y),
        w: 4,
        h: 0.5,
        color: '999999',
        fontSize: 12,
        align: 'center',
      });
    }
  };

  // Export to PDF with A4 format
  // Helper: Add SVG diagram element to PPTX PAGE (rasterize inline SVG to PNG)
  const addSvgDiagramToPptPAGE = async (pptPAGE, element) => {
    try {
      if (!element.svgContent) {
        console.warn('[PPTX] svg_diagram element has no svgContent, skipping');
        return;
      }

      const x = (element.x || 0) / 96;
      const y = (element.y || 0) / 96;
      const w = (element.width || 400) / 96;
      const h = (element.height || 300) / 96;

      const dataUrl = await rasterizeSvgToPng(
        element.svgContent,
        element.fillColor || element.fill || element.color,
        element.width,
        element.height,
      );
      if (!dataUrl) throw new Error('rasterizeSvgToPng returned null');

      const diagramTransparency = Math.round((1 - (element.opacity ?? 1)) * 100);
      pptPAGE.addImage({
        data: dataUrl,
        x: Math.max(0, x),
        y: Math.max(0, y),
        w: Math.min(10 - x, w),
        h: Math.min(5.625 - y, h),
        rotate: element.rotation || 0,
        transparency: diagramTransparency > 0 ? diagramTransparency : undefined,
      });

      console.log('[PPTX] SVG diagram exported as PNG');
    } catch (error) {
      console.warn('[PPTX] Failed to add SVG diagram, skipping:', error);
      const x = (element.x || 0) / 96;
      const y = (element.y || 0) / 96;
      pptPAGE.addText('[Diagram could not be exported]', {
        x: Math.max(0, x),
        y: Math.max(0, y),
        w: 4,
        h: 0.5,
        color: '999999',
        fontSize: 12,
        align: 'center',
      });
    }
  };

  const exportToPDF = async (quality = 'normal') => {
    if (Platform.OS !== 'web') {
      Alert.alert('Web Only', 'PDF export is currently only available on web.');
      return;
    }

    setIsExporting(true);
    setExportProgress({ current: 0, total: PAGES.length, format: 'PDF' });

    // A4 dimensions at 96 DPI
    const pageWidth = 794;
    const pageHeight = 1123;
    const dpiMultiplier = quality === 'high' ? 3 : 1.5; // 300 DPI vs 150 DPI

    try {
      // Pre-cache all images from PAGES before PDF rendering (including background images)
      const allImageUrls = [
        ...PAGES.flatMap(p =>
          (p.elements || []).filter(e => e.type === 'image' && e.src).map(e => e.src)
        ),
        ...PAGES.filter(p => p.backgroundImage).map(p => p.backgroundImage),
      ];
      await globalImageCache.preCacheAll(allImageUrls);

      // Pre-fetch all icon SVGs so synchronous getIconSVG() finds them in cache
      const allIconElements = PAGES.flatMap(p =>
        (p.elements || []).filter(e => e.type === 'icon')
      );
      // Fetch S3-hosted SVGs and cache them by icon name for inline rendering
      const s3IconElements = allIconElements.filter(e => e.svgSrc && (e.svgSrc.startsWith('http') || e.svgSrc.startsWith('s3://')));
      if (s3IconElements.length > 0) {
        await Promise.all(s3IconElements.map(async (e) => {
          try {
            const response = await fetch(e.svgSrc);
            if (response.ok) {
              const svgText = await response.text();
              cacheIconSVG(e.iconName || e.resolvedIconName || 'star', svgText);
            }
          } catch (err) {
            console.warn('[PDF] Failed to pre-fetch S3 icon:', e.iconName, err);
          }
        }));
      }
      // Fetch Iconify icons that aren't S3-hosted
      const allIconNames = allIconElements
        .filter(e => !e.svgSrc)
        .map(e => e.iconName || e.resolvedIconName || 'star');
      if (allIconNames.length > 0) {
        await prefetchIcons(allIconNames);
      }

      // Pre-rasterize SVG diagrams to PNG — createElementDiv() is synchronous
      // and cannot await the SVG→PNG conversion, so do it up front.
      const svgDiagramMap = await prerasterizeSvgDiagrams(PAGES);

      // Create a hidden div for rendering pages
      const printContainer = document.createElement('div');
      printContainer.id = 'printable-print-container';
      printContainer.style.cssText = `
        position: fixed;
        top: -9999px;
        left: -9999px;
        width: ${pageWidth}px;
      `;
      document.body.appendChild(printContainer);

      // Render each page as HTML
      for (let i = 0; i < PAGES.length; i++) {
        const PAGEData = PAGES[i];
        setExportProgress({ current: i + 1, total: PAGES.length, format: 'PDF' });

        // Create page container with proper class for PDF styling
        const pageContainer = document.createElement('div');
        pageContainer.className = 'page-container';

        const pageDiv = document.createElement('div');
        pageDiv.className = 'page-content';
        const pageBgImage = PAGEData.backgroundImage ? globalImageCache.get(PAGEData.backgroundImage) || PAGEData.backgroundImage : null;
        pageDiv.style.cssText = `
          width: ${pageWidth}px;
          height: ${pageHeight}px;
          background-color: ${PAGEData.backgroundColor || style.PAGEBackground || '#ffffff'};
          ${pageBgImage ? `background-image: url('${pageBgImage}'); background-size: cover; background-position: center;` : ''}
          position: relative;
          overflow: hidden;
        `;

        // Render elements (sorted by zIndex so layers match the editor)
        if (PAGEData.elements && Array.isArray(PAGEData.elements)) {
          const sortedElements = [...PAGEData.elements].sort((a, b) => (a.zIndex || 0) - (b.zIndex || 0));
          for (const element of sortedElements) {
            const elementDiv = createElementDiv(element, style, svgDiagramMap);
            if (elementDiv) {
              pageDiv.appendChild(elementDiv);
            }
          }
        }

        pageContainer.appendChild(pageDiv);
        printContainer.appendChild(pageContainer);
      }

      // Trigger print dialog
      const printWindow = window.open('', '_blank');
      if (printWindow) {
        printWindow.document.write(`
          <!DOCTYPE html>
          <html>
          <head>
            <title>${printableTitle}</title>
            <style>
              @page { 
                size: A4 portrait;
                margin: 0; 
              }
              @media print {
                * {
                  -webkit-print-color-adjust: exact !important;
                  print-color-adjust: exact !important;
                  color-adjust: exact !important;
                }
              }
              * {
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
                color-adjust: exact !important;
                box-sizing: border-box;
              }
              html, body { 
                margin: 0; 
                padding: 0;
                width: 100%;
                height: 100%;
              }
              .page-container {
                width: 210mm;
                height: 297mm;
                page-break-after: always;
                page-break-inside: avoid;
                overflow: hidden;
                position: relative;
              }
              .page-content {
                width: ${pageWidth}px;
                height: ${pageHeight}px;
                transform-origin: top left;
                transform: scale(${210 / (pageWidth / 96 * 25.4)}); /* Scale to fit A4 */
                position: relative;
              }
              img {
                image-rendering: -webkit-optimize-contrast;
                image-rendering: crisp-edges;
              }
            </style>
          </head>
          <body>
            ${printContainer.innerHTML}
          </body>
          </html>
        `);
        printWindow.document.close();

        // Wait for images to load before printing
        setTimeout(() => {
          printWindow.focus();
          printWindow.print();
        }, 500);
      }

      // Cleanup
      document.body.removeChild(printContainer);

      console.log('✅ [EXPORT] PDF print dialog opened');
    } catch (error) {
      console.error('Error exporting to PDF:', error);
      Alert.alert('Export Failed', 'Failed to export to PDF. Please try again.');
    } finally {
      setIsExporting(false);
      setExportProgress({ current: 0, total: 0, format: '' });
    }
  };

  // Helper: Create DOM element for PDF rendering
  // svgDiagramMap: Map<elementId, pngDataUrl> of pre-rasterized SVG diagrams
  const createElementDiv = (element, printableStyle, svgDiagramMap) => {
    const opacity = element.opacity ?? 1;
    const rotation = element.rotation || 0;
    const div = document.createElement('div');
    div.style.cssText = `
      position: absolute;
      left: ${element.x || 0}px;
      top: ${element.y || 0}px;
      width: ${element.width || 'auto'}px;
      height: ${element.height || 'auto'}px;
      opacity: ${opacity};
      z-index: ${element.zIndex || 0};
      transform: rotate(${rotation}deg);
      transform-origin: top left;
    `;

    switch (element.type) {
      case 'text':
        // Use correct style property paths
        const textColor = element.fill || element.color ||
          printableStyle?.textStyles?.title?.color ||
          printableStyle?.textPrimary || '#000000';
        div.style.color = textColor;
        div.style.fontFamily = element.fontFamily || printableStyle?.fontFamily || 'Arial';
        div.style.fontSize = `${element.fontSize || 24}px`;
        div.style.fontWeight = element.fontWeight || (element.textType === 'title' ? 'bold' : 'normal');
        div.style.textAlign = element.textAlign || 'left';
        div.style.whiteSpace = 'pre-wrap';
        div.style.wordWrap = 'break-word';
        div.style.lineHeight = '1.4';
        div.innerHTML = (element.content || '').replace(/\n/g, '<br>');
        break;

      case 'image':
        if (element.src) {
          const img = document.createElement('img');
          // Use cached blob URL if available, otherwise fall back to original
          const cachedSrc = globalImageCache.get(element.src);
          img.src = cachedSrc || element.src;
          img.style.width = '100%';
          img.style.height = '100%';
          img.style.objectFit = 'contain';
          img.crossOrigin = 'anonymous'; // Enable CORS for canvas capture
          div.appendChild(img);
        }
        break;

      case 'shape':
        div.style.backgroundColor = element.fill || '#3B82F6';
        if (element.shapeType === 'circle') {
          div.style.borderRadius = '50%';
        } else if (element.shapeType === 'triangle') {
          div.style.width = '0';
          div.style.height = '0';
          div.style.backgroundColor = 'transparent';
          div.style.borderLeft = `${(element.width || 100) / 2}px solid transparent`;
          div.style.borderRight = `${(element.width || 100) / 2}px solid transparent`;
          div.style.borderBottom = `${element.height || 100}px solid ${element.fill || '#3B82F6'}`;
        }
        if (element.stroke) {
          div.style.border = `${element.strokeWidth || 1}px solid ${element.stroke}`;
        }
        break;

      case 'icon':
        // Render icon with inline SVG — all icons pre-cached (S3 + Iconify) during prefetch
        const iconSize = element.size || 48;
        const iconColor = element.fill || element.color || '#000000';
        div.style.width = `${iconSize}px`;
        div.style.height = `${iconSize}px`;

        try {
          const iconName = element.iconName || element.resolvedIconName || 'star';
          const { getIconSVG } = require('../composer/utils/iconMapper');
          const svgContent = getIconSVG(iconName, { fill: iconColor, size: iconSize });

          if (svgContent && svgContent.includes('<svg')) {
            div.innerHTML = svgContent;
            div.style.display = 'flex';
            div.style.alignItems = 'center';
            div.style.justifyContent = 'center';
          } else {
            // Fallback: render as colored circle
            div.style.backgroundColor = iconColor;
            div.style.borderRadius = '50%';
          }
        } catch (e) {
          console.warn('[PDF] Icon mapper failed:', e);
          div.style.backgroundColor = element.fill || element.color || '#000000';
          div.style.borderRadius = '50%';
        }
        break;

      case 'chart':
        // Render chart using Chart.js to canvas, then convert to PNG image for PDF
        // CRITICAL: Canvas elements are NOT serialized by .innerHTML — only the empty <canvas> tag
        // is copied, not the rendered pixels. We must convert to <img> with data URL.
        if (element.chartConfig) {
          try {
            const chartWidth = element.width || 400;
            const chartHeight = element.height || 300;

            // Create offscreen canvas for Chart.js rendering
            const chartCanvas = document.createElement('canvas');
            chartCanvas.width = chartWidth;
            chartCanvas.height = chartHeight;

            // Initialize Chart.js on the offscreen canvas
            const { Chart, registerables } = require('chart.js');
            Chart.register(...registerables);

            const chartInstance = new Chart(chartCanvas, {
              type: element.chartConfig.type || 'bar',
              data: JSON.parse(JSON.stringify(element.chartConfig.data || { labels: [], datasets: [] })),
              options: {
                ...element.chartConfig.options,
                responsive: false,
                maintainAspectRatio: false,
                animation: false,
              }
            });

            // Convert rendered chart canvas to PNG data URL image
            // This ensures .innerHTML serialization preserves the chart
            const dataUrl = chartCanvas.toDataURL('image/png');
            chartInstance.destroy();

            const chartImg = document.createElement('img');
            chartImg.src = dataUrl;
            chartImg.style.width = '100%';
            chartImg.style.height = '100%';
            div.appendChild(chartImg);
          } catch (chartError) {
            console.warn('[PDF] Failed to render chart:', chartError);
            div.style.backgroundColor = '#f0f0f0';
            div.style.display = 'flex';
            div.style.alignItems = 'center';
            div.style.justifyContent = 'center';
            div.innerHTML = '<span style="color:#999">[Chart]</span>';
          }
        }
        break;

      case 'svg_diagram':
        // SVG diagram is pre-rasterized to a PNG data URL (see prerasterizeSvgDiagrams).
        // An <img> with a PNG data URL survives .innerHTML serialization and renders
        // reliably in both the print window and html2canvas — raw inline SVG does not.
        {
          const diagramPng = svgDiagramMap && svgDiagramMap.get(element.id);
          if (diagramPng) {
            const diagramImg = document.createElement('img');
            diagramImg.src = diagramPng;
            diagramImg.style.width = '100%';
            diagramImg.style.height = '100%';
            diagramImg.style.objectFit = 'contain';
            div.appendChild(diagramImg);
          } else {
            div.style.backgroundColor = '#f0f0f0';
            div.style.display = 'flex';
            div.style.alignItems = 'center';
            div.style.justifyContent = 'center';
            div.innerHTML = '<span style="color:#999">[Diagram]</span>';
          }
        }
        break;

      default:
        return null;
    }

    return div;
  };

  // Export PAGES as PNG images
  const exportToPNG = async () => {
    if (Platform.OS !== 'web') {
      Alert.alert('Web Only', 'PNG export is currently only available on web.');
      return;
    }

    setIsExporting(true);
    setExportProgress({ current: 0, total: PAGES.length, format: 'PNG' });

    try {
      // Load html2canvas and JSZip from CDN
      const html2canvas = await loadHtml2Canvas();
      const JSZip = await loadJSZip();
      const zip = new JSZip();
      const fileName = sanitizeFileName(printableTitle);

      // Pre-cache all images before PNG rendering (including background images)
      const allImageUrls = [
        ...PAGES.flatMap(p =>
          (p.elements || []).filter(e => e.type === 'image' && e.src).map(e => e.src)
        ),
        ...PAGES.filter(p => p.backgroundImage).map(p => p.backgroundImage),
      ];
      await globalImageCache.preCacheAll(allImageUrls);

      // Pre-fetch all icon SVGs so synchronous getIconSVG() finds them in cache
      const pngIconElements = PAGES.flatMap(p =>
        (p.elements || []).filter(e => e.type === 'icon')
      );
      const pngS3IconElements = pngIconElements.filter(e => e.svgSrc && (e.svgSrc.startsWith('http') || e.svgSrc.startsWith('s3://')));
      if (pngS3IconElements.length > 0) {
        await Promise.all(pngS3IconElements.map(async (e) => {
          try {
            const response = await fetch(e.svgSrc);
            if (response.ok) {
              const svgText = await response.text();
              cacheIconSVG(e.iconName || e.resolvedIconName || 'star', svgText);
            }
          } catch (err) {
            console.warn('[PNG] Failed to pre-fetch S3 icon:', e.iconName, err);
          }
        }));
      }
      const pngIconNames = pngIconElements
        .filter(e => !e.svgSrc)
        .map(e => e.iconName || e.resolvedIconName || 'star');
      if (pngIconNames.length > 0) {
        await prefetchIcons(pngIconNames);
      }

      // Pre-rasterize SVG diagrams to PNG for synchronous createElementDiv() lookup.
      const svgDiagramMap = await prerasterizeSvgDiagrams(PAGES);

      for (let i = 0; i < PAGES.length; i++) {
        const PAGEData = PAGES[i];
        setExportProgress({ current: i + 1, total: PAGES.length, format: 'PNG' });

        // Create container for PAGE
        const container = document.createElement('div');
        const pngBgImage = PAGEData.backgroundImage ? globalImageCache.get(PAGEData.backgroundImage) || PAGEData.backgroundImage : null;
        container.style.cssText = `
          position: fixed;
          top: -9999px;
          left: -9999px;
          width: 960px;
          height: 540px;
          background-color: ${PAGEData.backgroundColor || style.PAGEBackground || '#ffffff'};
          ${pngBgImage ? `background-image: url('${pngBgImage}'); background-size: cover; background-position: center;` : ''}
        `;

        // Add elements (sorted by zIndex so layers match the editor)
        if (PAGEData.elements && Array.isArray(PAGEData.elements)) {
          const sortedElements = [...PAGEData.elements].sort((a, b) => (a.zIndex || 0) - (b.zIndex || 0));
          for (const element of sortedElements) {
            const elementDiv = createElementDiv(element, style, svgDiagramMap);
            if (elementDiv) {
              container.appendChild(elementDiv);
            }
          }
        }

        document.body.appendChild(container);

        // Convert to canvas
        const canvas = await html2canvas(container, {
          width: 960,
          height: 540,
          scale: 2, // Higher resolution
          useCORS: true,
        });

        // Add PNG to ZIP
        const dataUrl = canvas.toDataURL('image/png');
        const base64 = dataUrl.split(',')[1];
        zip.file(`${fileName}_page_${i + 1}.png`, base64, { base64: true });

        // Cleanup
        document.body.removeChild(container);
      }

      // Generate and download ZIP
      const zipBlob = await zip.generateAsync({ type: 'blob' });
      const link = document.createElement('a');
      link.download = `${fileName}_pages.zip`;
      link.href = URL.createObjectURL(zipBlob);
      link.click();
      URL.revokeObjectURL(link.href);

      console.log('✅ [EXPORT] PNG images exported as ZIP successfully');
      Alert.alert('Export Complete', `${PAGES.length} page images have been downloaded as a ZIP file.`);
    } catch (error) {
      console.error('Error exporting to PNG:', error);
      Alert.alert('Export Failed', 'Failed to export to PNG. You may need to install html2canvas package.');
    } finally {
      setIsExporting(false);
      setExportProgress({ current: 0, total: 0, format: '' });
    }
  };

  // Helper: Sanitize file name
  const sanitizeFileName = (name) => {
    return name
      .replace(/[^a-z0-9]/gi, '_')
      .replace(/_+/g, '_')
      .substring(0, 50);
  };

  // A4 page dimensions at different DPIs
  const A4_WIDTH = 794; // pixels at 96 DPI
  const A4_HEIGHT = 1123; // pixels at 96 DPI

  // Quality settings for export
  const [selectedQuality, setSelectedQuality] = useState('normal'); // 'normal' or 'high'

  // Export to PDF with quality option
  const exportToPDFWithQuality = async (quality = 'normal') => {
    setSelectedQuality(quality);
    await exportToPDF(quality);
  };

  // Export to Word/DOCX format
  const exportToWord = async (quality = 'normal') => {
    if (Platform.OS !== 'web') {
      Alert.alert('Web Only', 'Word export is currently only available on web.');
      return;
    }

    setIsExporting(true);
    setExportProgress({ current: 0, total: PAGES.length, format: 'DOCX' });

    // A4 dimensions at 96 DPI
    const A4_W = 794;
    const A4_H = 1123;

    try {
      // Pre-cache all images before Word export (including background images)
      const allImageUrls = [
        ...PAGES.flatMap(p =>
          (p.elements || []).filter(e => e.type === 'image' && e.src).map(e => e.src)
        ),
        ...PAGES.filter(p => p.backgroundImage).map(p => p.backgroundImage),
      ];
      await globalImageCache.preCacheAll(allImageUrls);

      // Pre-rasterize SVG diagrams to PNG — Word/HTML cannot render inline SVG
      // reliably, and createElementHtml() is synchronous.
      const svgDiagramMap = await prerasterizeSvgDiagrams(PAGES);

      // Create HTML content for Word export
      // Word does NOT support CSS position:absolute — use flow layout with block-level elements
      // Elements are sorted by Y position to approximate their visual order
      let htmlContent = `
        <!DOCTYPE html>
        <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
        <head>
          <meta charset="utf-8">
          <title>${printableTitle}</title>
          <!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View></w:WordDocument></xml><![endif]-->
          <style>
            @page { size: A4 portrait; margin: 15mm 20mm; }
            body { margin: 0; padding: 0; font-family: Arial, sans-serif; }
            .page { 
              page-break-after: always;
              box-sizing: border-box;
            }
            .page:last-child { page-break-after: auto; }
            .element-block { margin-bottom: 8px; }
            img { max-width: 100%; height: auto; }
            table { border-collapse: collapse; }
            td, th { padding: 4px 8px; border: 1px solid #E5E7EB; }
          </style>
        </head>
        <body>
      `;

      for (let i = 0; i < PAGES.length; i++) {
        const PAGEData = PAGES[i];
        setExportProgress({ current: i + 1, total: PAGES.length, format: 'DOCX' });

        htmlContent += `<div class="page" style="background-color: ${PAGEData.backgroundColor || style.PAGEBackground || '#ffffff'};">`;

        // Sort elements by Y position to maintain visual order in flow layout
        if (PAGEData.elements && Array.isArray(PAGEData.elements)) {
          const sortedElements = [...PAGEData.elements].sort((a, b) => (a.y || 0) - (b.y || 0));
          for (const element of sortedElements) {
            const elementHtml = createElementHtml(element, style, svgDiagramMap);
            if (elementHtml) {
              htmlContent += elementHtml;
            }
          }
        }

        htmlContent += '</div>';
      }

      htmlContent += '</body></html>';

      // Create Blob and download as .doc (Word can open HTML files)
      const blob = new Blob([htmlContent], { type: 'application/msword' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${sanitizeFileName(printableTitle)}.doc`;
      link.click();
      URL.revokeObjectURL(url);

      console.log('✅ [EXPORT] Word document exported successfully');
      Alert.alert('Export Complete', `${printableTitle}.doc has been downloaded.`);
    } catch (error) {
      console.error('Error exporting to Word:', error);
      Alert.alert('Export Failed', 'Failed to export to Word. Please try again.');
    } finally {
      setIsExporting(false);
      setExportProgress({ current: 0, total: 0, format: '' });
    }
  };

  // Helper: Create HTML element for Word export (uses flow layout, not absolute positioning)
  // svgDiagramMap: Map<elementId, pngDataUrl> of pre-rasterized SVG diagrams
  const createElementHtml = (element, printableStyle, svgDiagramMap) => {
    const width = element.width || 200;
    const height = element.height || 50;

    switch (element.type) {
      case 'text': {
        const textColor = element.fill || element.color || printableStyle?.textPrimary || '#000000';
        const fontSize = element.fontSize || 20;
        const fontWeight = element.fontWeight || (element.textType === 'title' ? 'bold' : 'normal');
        const textAlign = element.textAlign || 'left';
        return `<div class="element-block" style="color:${textColor};font-size:${fontSize}px;font-family:${element.fontFamily || 'Arial'};font-weight:${fontWeight};text-align:${textAlign};white-space:pre-wrap;line-height:1.4;">${(element.content || '').replace(/\n/g, '<br>')}</div>`;
      }

      case 'image': {
        if (element.src) {
          // Use cached image if available
          const cachedSrc = globalImageCache.get(element.src);
          const imgSrc = cachedSrc || element.src;
          return `<div class="element-block" style="text-align:center;"><img src="${imgSrc}" style="max-width:${Math.min(width, 600)}px;height:auto;" alt=""/></div>`;
        }
        return '';
      }

      case 'shape': {
        const bgColor = element.fill || '#3B82F6';
        const borderRadius = element.shapeType === 'circle' ? '50%' : (element.rx || 0) + 'px';
        const border = element.stroke ? `border:${element.strokeWidth || 1}px solid ${element.stroke};` : '';
        return `<div class="element-block" style="width:${Math.min(width, 600)}px;height:${height}px;background-color:${bgColor};border-radius:${borderRadius};${border}"></div>`;
      }

      case 'icon': {
        // Export icon as image if S3 SVG source is available
        if (element.svgSrc && element.svgSrc.startsWith('http')) {
          const iconSize = element.size || 48;
          return `<div class="element-block"><img src="${element.svgSrc}" style="width:${iconSize}px;height:${iconSize}px;" alt="icon"/></div>`;
        }
        return '';
      }

      case 'chart': {
        // Charts cannot be directly exported to Word HTML — show placeholder
        return `<div class="element-block" style="width:${Math.min(width, 600)}px;height:${height}px;border:1px dashed #ccc;display:flex;align-items:center;justify-content:center;color:#999;font-size:14px;">[Chart — export as PDF for full fidelity]</div>`;
      }

      case 'svg_diagram': {
        // SVG diagram pre-rasterized to a PNG data URL — embeds reliably in Word.
        const diagramPng = svgDiagramMap && svgDiagramMap.get(element.id);
        if (diagramPng) {
          return `<div class="element-block" style="text-align:center;"><img src="${diagramPng}" style="max-width:${Math.min(width, 600)}px;height:auto;" alt="diagram"/></div>`;
        }
        return `<div class="element-block" style="width:${Math.min(width, 600)}px;height:${height}px;border:1px dashed #ccc;display:flex;align-items:center;justify-content:center;color:#999;font-size:14px;">[Diagram — export as PDF for full fidelity]</div>`;
      }

      default:
        return '';
    }
  };

  // Export options - PDF and Word only (no PPTX for printable documents)
  const exportOptions = [
    {
      id: 'pdf-high',
      label: 'PDF (High Quality)',
      description: 'High DPI for professional printing (300 DPI)',
      icon: 'print-outline',
      color: '#E53935',
      action: () => exportToPDFWithQuality('high'),
    },
    {
      id: 'pdf-normal',
      label: 'PDF (Standard)',
      description: 'Optimized for screen viewing & sharing',
      icon: 'document-text-outline',
      color: '#FF7043',
      action: () => exportToPDFWithQuality('normal'),
    },
    {
      id: 'word-high',
      label: 'Word Document (High Quality)',
      description: 'Editable document for professional printing',
      icon: 'document-outline',
      color: '#2196F3',
      action: () => exportToWord('high'),
    },
    {
      id: 'word-normal',
      label: 'Word Document (Standard)',
      description: 'Editable document for web sharing',
      icon: 'create-outline',
      color: '#42A5F5',
      action: () => exportToWord('normal'),
    },
  ];

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <View style={styles.overlay}>
        <View style={[styles.modal, { backgroundColor: theme.background }]}>
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: theme.border }]}>
            <Text style={[styles.title, { color: theme.text }]}>Export Document</Text>
            <TouchableOpacity onPress={onClose} disabled={isExporting}>
              <Ionicons name="close" size={24} color={theme.text} />
            </TouchableOpacity>
          </View>

          {/* Content */}
          <ScrollView style={styles.content}>
            {/* Document info */}
            <View style={[styles.infoCard, { backgroundColor: theme.surface, borderColor: theme.border }]}>
              <Ionicons name="document-text-outline" size={24} color={theme.primary} />
              <View style={styles.infoText}>
                <Text style={[styles.infoTitle, { color: theme.text }]}>{printableTitle}</Text>
                <Text style={[styles.infoSubtitle, { color: theme.textSecondary }]}>
                  {PAGES.length} page{PAGES.length !== 1 ? 's' : ''} (A4 format)
                </Text>
              </View>
            </View>

            {/* Export options */}
            {exportOptions.map((option) => (
              <TouchableOpacity
                key={option.id}
                style={[
                  styles.exportOption,
                  {
                    backgroundColor: theme.surface,
                    borderColor: theme.border,
                    opacity: isExporting ? 0.6 : 1,
                  },
                ]}
                onPress={option.action}
                disabled={isExporting}
              >
                <View style={[styles.optionIcon, { backgroundColor: option.color + '20' }]}>
                  <Ionicons name={option.icon} size={24} color={option.color} />
                </View>
                <View style={styles.optionText}>
                  <Text style={[styles.optionLabel, { color: theme.text }]}>{option.label}</Text>
                  <Text style={[styles.optionDescription, { color: theme.textSecondary }]}>
                    {option.description}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={theme.textSecondary} />
              </TouchableOpacity>
            ))}

            {/* Progress indicator */}
            {isExporting && (
              <View style={[styles.progressContainer, { backgroundColor: theme.surface, borderColor: theme.primary }]}>
                <ActivityIndicator size="large" color={theme.primary} />
                <Text style={[styles.progressText, { color: theme.text }]}>
                  Exporting to {exportProgress.format}...
                </Text>
                <Text style={[styles.progressSubtext, { color: theme.textSecondary }]}>
                  PAGE {exportProgress.current} of {exportProgress.total}
                </Text>
                <View style={[styles.progressBar, { backgroundColor: theme.border }]}>
                  <View
                    style={[
                      styles.progressFill,
                      {
                        backgroundColor: theme.primary,
                        width: `${(exportProgress.current / exportProgress.total) * 100}%`,
                      },
                    ]}
                  />
                </View>
              </View>
            )}

            {/* Web-only notice */}
            {Platform.OS !== 'web' && (
              <View style={[styles.noticeCard, { backgroundColor: '#FEF3C7', borderColor: '#F59E0B' }]}>
                <Ionicons name="information-circle" size={20} color="#D97706" />
                <Text style={[styles.noticeText, { color: '#92400E' }]}>
                  Export features are currently only available on web. Please use the web version for full export functionality.
                </Text>
              </View>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
};

const styles = {
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modal: {
    width: '100%',
    maxWidth: 450,
    borderRadius: 16,
    maxHeight: '80%',
    ...Platform.select({
      web: {
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.15)',
      },
      default: {
        elevation: 10,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.15,
        shadowRadius: 20,
      },
    }),
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
  },
  content: {
    padding: 16,
  },
  infoCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 20,
    gap: 12,
  },
  infoText: {
    flex: 1,
  },
  infoTitle: {
    fontSize: 15,
    fontWeight: '600',
  },
  infoSubtitle: {
    fontSize: 13,
    marginTop: 2,
  },
  exportOption: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
    gap: 12,
  },
  optionIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  optionText: {
    flex: 1,
  },
  optionLabel: {
    fontSize: 15,
    fontWeight: '600',
  },
  optionDescription: {
    fontSize: 12,
    marginTop: 2,
  },
  progressContainer: {
    alignItems: 'center',
    padding: 24,
    borderRadius: 12,
    borderWidth: 2,
    marginBottom: 16,
  },
  progressText: {
    fontSize: 15,
    fontWeight: '500',
    marginTop: 16,
  },
  progressSubtext: {
    fontSize: 13,
    marginTop: 4,
  },
  progressBar: {
    width: '100%',
    height: 6,
    borderRadius: 3,
    marginTop: 12,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 3,
  },
  noticeCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    marginBottom: 16,
    gap: 10,
  },
  noticeText: {
    flex: 1,
    fontSize: 13,
    lineHeight: 18,
  },
};

export default PrintableExport;
