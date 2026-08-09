// PresentationExport.js - Export presentation to PPTX, PDF, or images
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
import { mapIconToPathAsync, prefetchIcons, cacheIconSVG } from './utils/iconMapper';
import { rasterizeSvgToPng, prerasterizeSvgDiagrams } from './utils/svgRasterize';
import globalImageCache from '../../utils/globalImageCache';

/**
 * PresentationExport - Export presentation to various formats
 * 
 * Supported formats:
 * - PPTX (PowerPoint) - using pptxgenjs
 * - PDF - using browser print or server-side
 * - PNG images - individual slide images
 */
const PresentationExport = ({
  visible,
  onClose,
  slides = [],
  presentationTitle = 'Presentation',
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
    setExportProgress({ current: 0, total: slides.length, format: 'PPTX' });

    try {
      // Pre-cache all images from slides before starting export (including background images)
      const allImageUrls = [
        ...slides.flatMap(s =>
          (s.elements || []).filter(e => e.type === 'image' && e.src).map(e => e.src)
        ),
        ...slides.filter(s => s.backgroundImage).map(s => s.backgroundImage),
      ];
      await globalImageCache.preCacheAll(allImageUrls);

      const PptxGenJS = await loadPptxGen();
      if (!PptxGenJS) {
        throw new Error('pptxgenjs failed to load');
      }

      console.log('📊 [PPTX] Creating presentation with', slides.length, 'slides');

      // PptxGenJS can be either a class or have a default export
      const pres = typeof PptxGenJS === 'function' ? new PptxGenJS() : new PptxGenJS.default();

      // Set presentation properties
      pres.title = presentationTitle;
      pres.author = userType === 'paid' ? '' : 'Citra AI';
      pres.subject = 'Generated Presentation';
      pres.layout = 'LAYOUT_16x9';

      // Define master slide with style
      if (style.slideBackground) {
        pres.defineSlideMaster({
          title: 'STYLED_MASTER',
          background: { color: style.slideBackground?.replace('#', '') || 'FFFFFF' },
        });
      }

      // Process each slide
      for (let i = 0; i < slides.length; i++) {
        const slideData = slides[i];
        setExportProgress({ current: i + 1, total: slides.length, format: 'PPTX' });

        const pptSlide = pres.addSlide(style.slideBackground ? 'STYLED_MASTER' : undefined);

        // Set slide background (image takes priority, color is fallback)
        if (slideData.backgroundImage) {
          try {
            const bgBase64 = await globalImageCache.getAsBase64(slideData.backgroundImage);
            if (bgBase64) {
              pptSlide.background = { data: bgBase64 };
            } else if (slideData.backgroundColor) {
              pptSlide.background = { color: slideData.backgroundColor.replace('#', '') };
            }
          } catch (bgErr) {
            console.warn('[PPTX] Failed to export background image, using color:', bgErr);
            if (slideData.backgroundColor) {
              pptSlide.background = { color: slideData.backgroundColor.replace('#', '') };
            }
          }
        } else if (slideData.backgroundColor) {
          pptSlide.background = { color: slideData.backgroundColor.replace('#', '') };
        }

        // Process slide elements (sorted by zIndex so layers match the editor)
        if (slideData.elements && Array.isArray(slideData.elements)) {
          const sortedElements = [...slideData.elements].sort((a, b) => (a.zIndex || 0) - (b.zIndex || 0));
          for (const element of sortedElements) {
            try {
              switch (element.type) {
                case 'text':
                  addTextToPptSlide(pptSlide, element, style);
                  break;
                case 'image':
                  await addImageToPptSlide(pptSlide, element);
                  break;
                case 'shape':
                  addShapeToPptSlide(pres, pptSlide, element);
                  break;
                case 'icon':
                  // Convert icon to PNG and add as image
                  await addIconToPptSlide(pres, pptSlide, element);
                  break;
                case 'chart':
                  // Render chart to PNG and add as image
                  await addChartToPptSlide(pptSlide, element);
                  break;
                case 'svg_diagram':
                  // Rasterize inline SVG diagram to PNG and add as image
                  await addSvgDiagramToPptSlide(pptSlide, element);
                  break;
              }
            } catch (elementError) {
              console.warn('[PPTX] Error adding element, skipping:', element.type, elementError);
            }
          }
        }
      }

      // Generate and download the file
      const fileName = `${sanitizeFileName(presentationTitle)}.pptx`;
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

  // Helper: Add text element to PPTX slide
  const addTextToPptSlide = (pptSlide, element, presentationStyle) => {
    // Convert pixel positions to inches (assuming 96 DPI and 960x540 canvas)
    const x = (element.x || 0) / 96;
    const y = (element.y || 0) / 96;
    const w = (element.width || 200) / 96;
    const h = (element.height || 50) / 96;

    // Get color from element, then fall back to style
    const textColor = element.fill || element.color ||
      presentationStyle?.textStyles?.title?.color ||
      presentationStyle?.textPrimary || '#000000';

    // Compute transparency from element opacity (pptxgenjs: 0=opaque, 100=fully transparent)
    const transparency = Math.round((1 - (element.opacity ?? 1)) * 100);

    const textOptions = {
      x: Math.max(0, x),
      y: Math.max(0, y),
      w: Math.min(10 - x, w),
      h: Math.min(5.625 - y, h),
      color: textColor.replace('#', ''),
      fontFace: element.fontFamily || presentationStyle?.fontFamily || 'Arial',
      fontSize: Math.round((element.fontSize || 24) * 0.75), // Convert px to pt
      bold: element.fontWeight === 'bold' || element.fontWeight === '700' || element.textType === 'title',
      italic: element.fontStyle === 'italic',
      underline: !!element.underline,
      align: element.textAlign || 'left',
      valign: 'top',
      wrap: true,
      rotate: element.rotation || 0,
      transparency: transparency > 0 ? transparency : undefined,
    };

    // Adjust for different text types — only override fontSize if element doesn't have its own
    if (element.textType === 'title') {
      if (!element.fontSize) {
        textOptions.fontSize = Math.round((presentationStyle?.textStyles?.title?.fontSize || 44) * 0.75);
      }
      textOptions.bold = true;
    } else if (element.textType === 'subtitle') {
      if (!element.fontSize) {
        textOptions.fontSize = Math.round((presentationStyle?.textStyles?.subtitle?.fontSize || 24) * 0.75);
      }
    } else if (element.textType === 'bullet') {
      textOptions.bullet = true;
    }

    pptSlide.addText(element.content || '', textOptions);
  };

  // Helper: Add image element to PPTX slide
  const addImageToPptSlide = async (pptSlide, element) => {
    if (!element.src) return;

    const x = (element.x || 0) / 96;
    const y = (element.y || 0) / 96;
    const w = (element.width || 200) / 96;
    const h = (element.height || 150) / 96;

    try {
      // Check if it's a data URL or regular URL
      const imgTransparency = Math.round((1 - (element.opacity ?? 1)) * 100);
      const imgOpts = {
        x: Math.max(0, x),
        y: Math.max(0, y),
        w: Math.min(10 - x, w),
        h: Math.min(5.625 - y, h),
        rotate: element.rotation || 0,
        transparency: imgTransparency > 0 ? imgTransparency : undefined,
      };

      if (element.src.startsWith('data:')) {
        pptSlide.addImage({ ...imgOpts, data: element.src });
      } else {
        // Use global image cache to get base64 - avoids CORS issues
        const dataUrl = await globalImageCache.getAsBase64(element.src);

        if (dataUrl) {
          pptSlide.addImage({ ...imgOpts, data: dataUrl });
        } else {
          throw new Error('Failed to convert image to base64');
        }
      }
    } catch (error) {
      console.error('Failed to add image to PPTX:', error);
      // Add placeholder text instead
      pptSlide.addText('[Image could not be exported]', {
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

  // Helper: Add shape element to PPTX slide
  const addShapeToPptSlide = (pres, pptSlide, element) => {
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
      pptSlide.addShape(shapeType, {
        x: Math.max(0, x),
        y: Math.max(0, y),
        w: Math.max(0.1, Math.min(10 - x, w)),
        h: Math.max(0.1, Math.min(5.625 - y, h)),
        fill: { color: (element.fill || '#3B82F6').replace('#', ''), transparency: shapeTransparency > 0 ? shapeTransparency : undefined },
        line: element.stroke ? { color: element.stroke.replace('#', ''), pt: element.strokeWidth || 1 } : undefined,
        rotate: element.rotation || 0,
      });
    } catch (error) {
      console.warn('[PPTX] Failed to add shape, skipping:', error);
    }
  };

  // Helper: Add icon element to PPTX slide (render as PNG from SVG path)
  const addIconToPptSlide = async (pres, pptSlide, element) => {
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
      pptSlide.addImage({
        data: dataUrl,
        x: Math.max(0, x),
        y: Math.max(0, y),
        w: size,
        h: size,
        rotate: element.rotation || 0,
        transparency: iconTransparency > 0 ? iconTransparency : undefined,
      });

      console.log('[PPTX] Icon exported from cache as PNG:', iconName);
    } catch (error) {
      console.warn('[PPTX] Failed to add icon as image, skipping:', iconName, error);
    }
  };

  // Helper: Add chart element to PPTX slide (render Chart.js to PNG)
  const addChartToPptSlide = async (pptSlide, element) => {
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
      pptSlide.addImage({
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
      pptSlide.addText('[Chart could not be exported]', {
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

  // Helper: Add SVG diagram element to PPTX slide (rasterize inline SVG to PNG)
  const addSvgDiagramToPptSlide = async (pptSlide, element) => {
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
      pptSlide.addImage({
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
      pptSlide.addText('[Diagram could not be exported]', {
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

  // Export to PDF
  const exportToPDF = async () => {
    if (Platform.OS !== 'web') {
      Alert.alert('Web Only', 'PDF export is currently only available on web.');
      return;
    }

    setIsExporting(true);
    setExportProgress({ current: 0, total: slides.length, format: 'PDF' });

    try {
      // Pre-cache all images from slides before PDF rendering (including background images)
      const allImageUrls = [
        ...slides.flatMap(s =>
          (s.elements || []).filter(e => e.type === 'image' && e.src).map(e => e.src)
        ),
        ...slides.filter(s => s.backgroundImage).map(s => s.backgroundImage),
      ];
      await globalImageCache.preCacheAll(allImageUrls);

      // Pre-fetch all icon SVGs so synchronous getIconSVG() finds them in cache
      const allIconElements = slides.flatMap(s =>
        (s.elements || []).filter(e => e.type === 'icon')
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
      const svgDiagramMap = await prerasterizeSvgDiagrams(slides);

      // Create a hidden div for rendering slides
      const printContainer = document.createElement('div');
      printContainer.id = 'presentation-print-container';
      printContainer.style.cssText = `
        position: fixed;
        top: -9999px;
        left: -9999px;
        width: 960px;
      `;
      document.body.appendChild(printContainer);

      // Render each slide as HTML
      for (let i = 0; i < slides.length; i++) {
        const slideData = slides[i];
        setExportProgress({ current: i + 1, total: slides.length, format: 'PDF' });

        // Create slide container with proper class for PDF styling
        const slideContainer = document.createElement('div');
        slideContainer.className = 'slide-container';

        const slideDiv = document.createElement('div');
        slideDiv.className = 'slide-content';
        const slideBgColor = slideData.backgroundColor || style.slideBackground || '#ffffff';
        const slideBgImage = slideData.backgroundImage;
        let slideBgCss = `background-color: ${slideBgColor};`;
        if (slideBgImage) {
          const cachedBg = globalImageCache.get(slideBgImage);
          slideBgCss += ` background-image: url('${cachedBg || slideBgImage}'); background-size: 100% 100%; background-position: center; background-repeat: no-repeat;`;
        }
        slideDiv.style.cssText = `
          width: 960px;
          height: 540px;
          ${slideBgCss}
          position: relative;
          overflow: hidden;
        `;

        // Render elements (sorted by zIndex so layers match the editor)
        if (slideData.elements && Array.isArray(slideData.elements)) {
          const sortedElements = [...slideData.elements].sort((a, b) => (a.zIndex || 0) - (b.zIndex || 0));
          for (const element of sortedElements) {
            const elementDiv = createElementDiv(element, style, svgDiagramMap);
            if (elementDiv) {
              slideDiv.appendChild(elementDiv);
            }
          }
        }

        slideContainer.appendChild(slideDiv);
        printContainer.appendChild(slideContainer);
      }

      // Trigger print dialog
      const printWindow = window.open('', '_blank');
      if (printWindow) {
        printWindow.document.write(`
          <!DOCTYPE html>
          <html>
          <head>
            <title>${presentationTitle}</title>
            <style>
              @page { 
                size: 10in 5.625in; /* 16:9 aspect ratio */
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
              .slide-container {
                width: 10in;
                height: 5.625in;
                page-break-after: always;
                page-break-inside: avoid;
                overflow: hidden;
                position: relative;
              }
              .slide-content {
                width: 960px;
                height: 540px;
                transform-origin: top left;
                transform: scale(calc(10 / 960 * 96)); /* Scale to fit 10 inches */
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
  const createElementDiv = (element, presentationStyle, svgDiagramMap) => {
    const rotation = element.rotation || 0;
    const opacity = element.opacity ?? 1;
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
          presentationStyle?.textStyles?.title?.color ||
          presentationStyle?.textPrimary || '#000000';
        div.style.color = textColor;
        div.style.fontFamily = element.fontFamily || presentationStyle?.fontFamily || 'Arial';
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
          const { getIconSVG } = require('./utils/iconMapper');
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
        // A <canvas> would not survive .innerHTML serialization, and raw inline SVG
        // is unreliable in html2canvas — an <img> with a PNG data URL works everywhere.
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

  // Export slides as PNG images
  const exportToPNG = async () => {
    if (Platform.OS !== 'web') {
      Alert.alert('Web Only', 'PNG export is currently only available on web.');
      return;
    }

    setIsExporting(true);
    setExportProgress({ current: 0, total: slides.length, format: 'PNG' });

    try {
      // Load html2canvas and JSZip from CDN
      const html2canvas = await loadHtml2Canvas();
      const JSZip = await loadJSZip();
      const zip = new JSZip();
      const fileName = sanitizeFileName(presentationTitle);

      // Pre-cache all images before PNG rendering (including background images)
      const allImageUrls = [
        ...slides.flatMap(s =>
          (s.elements || []).filter(e => e.type === 'image' && e.src).map(e => e.src)
        ),
        ...slides.filter(s => s.backgroundImage).map(s => s.backgroundImage),
      ];
      await globalImageCache.preCacheAll(allImageUrls);

      // Pre-fetch all icon SVGs so synchronous getIconSVG() finds them in cache
      const pngIconElements = slides.flatMap(s =>
        (s.elements || []).filter(e => e.type === 'icon')
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
      const svgDiagramMap = await prerasterizeSvgDiagrams(slides);

      for (let i = 0; i < slides.length; i++) {
        const slideData = slides[i];
        setExportProgress({ current: i + 1, total: slides.length, format: 'PNG' });

        // Create container for slide
        const container = document.createElement('div');
        const pngBgColor = slideData.backgroundColor || style.slideBackground || '#ffffff';
        const pngBgImage = slideData.backgroundImage;
        let pngBgCss = `background-color: ${pngBgColor};`;
        if (pngBgImage) {
          const cachedBg = globalImageCache.get(pngBgImage);
          pngBgCss += ` background-image: url('${cachedBg || pngBgImage}'); background-size: 100% 100%; background-position: center; background-repeat: no-repeat;`;
        }
        container.style.cssText = `
          position: fixed;
          top: -9999px;
          left: -9999px;
          width: 960px;
          height: 540px;
          ${pngBgCss}
        `;

        // Add elements (sorted by zIndex so layers match the editor)
        if (slideData.elements && Array.isArray(slideData.elements)) {
          const sortedElements = [...slideData.elements].sort((a, b) => (a.zIndex || 0) - (b.zIndex || 0));
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
        zip.file(`${fileName}_slide_${i + 1}.png`, base64, { base64: true });

        // Cleanup
        document.body.removeChild(container);
      }

      // Generate and download ZIP
      const zipBlob = await zip.generateAsync({ type: 'blob' });
      const link = document.createElement('a');
      link.download = `${fileName}_slides.zip`;
      link.href = URL.createObjectURL(zipBlob);
      link.click();
      URL.revokeObjectURL(link.href);

      console.log('✅ [EXPORT] PNG images exported as ZIP successfully');
      Alert.alert('Export Complete', `${slides.length} slide images have been downloaded as a ZIP file.`);
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

  // Export options
  const exportOptions = [
    {
      id: 'pptx',
      label: 'PowerPoint (.pptx)',
      description: 'Editable PowerPoint presentation',
      icon: 'document-outline',
      color: '#D04424',
      action: exportToPPTX,
    },
    {
      id: 'pdf',
      label: 'PDF Document',
      description: 'Print-ready PDF format',
      icon: 'document-text-outline',
      color: '#E53935',
      action: exportToPDF,
    },
    {
      id: 'png',
      label: 'PNG Images',
      description: 'Individual slide images',
      icon: 'image-outline',
      color: '#43A047',
      action: exportToPNG,
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
            <Text style={[styles.title, { color: theme.text }]}>Export Presentation</Text>
            <TouchableOpacity onPress={onClose} disabled={isExporting}>
              <Ionicons name="close" size={24} color={theme.text} />
            </TouchableOpacity>
          </View>

          {/* Content */}
          <ScrollView style={styles.content}>
            {/* Presentation info */}
            <View style={[styles.infoCard, { backgroundColor: theme.surface, borderColor: theme.border }]}>
              <Ionicons name="easel-outline" size={24} color={theme.primary} />
              <View style={styles.infoText}>
                <Text style={[styles.infoTitle, { color: theme.text }]}>{presentationTitle}</Text>
                <Text style={[styles.infoSubtitle, { color: theme.textSecondary }]}>
                  {slides.length} slide{slides.length !== 1 ? 's' : ''}
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
                  Slide {exportProgress.current} of {exportProgress.total}
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

export default PresentationExport;
