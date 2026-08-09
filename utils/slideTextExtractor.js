/**
 * Slide/Page Text Extraction Utility
 * ====================================
 * Extracts searchable text summaries from slide/page objects
 * for building lightweight context to send to orchestrate-all endpoints.
 * 
 * Used by: PresentationComposer, PrintableComposer, ReportComposer
 */

/**
 * Extract all searchable text from a presentation/printable slide object.
 * Handles elements array with text, charts, tables, icons, cards, etc.
 * 
 * @param {Object} slide - Slide object with elements array
 * @param {number} maxLength - Maximum chars to return
 * @returns {string} Concatenated text summary
 */
export function extractSlideTextSummary(slide, maxLength = 300) {
  if (!slide) return '';
  
  const parts = [];

  // Title
  if (slide.title) parts.push(slide.title);
  if (slide.subtitle) parts.push(slide.subtitle);
  if (slide.notes) parts.push(slide.notes);

  // Elements array (presentation / printable slides)
  if (slide.elements && Array.isArray(slide.elements)) {
    for (const el of slide.elements) {
      if (el.text) parts.push(el.text);
      if (el.content) parts.push(el.content);
      if (el.label) parts.push(el.label);
      if (el.caption) parts.push(el.caption);
      if (el.heading) parts.push(el.heading);
      if (el.subheading) parts.push(el.subheading);

      // Bullet points / list items
      if (el.items && Array.isArray(el.items)) {
        for (const item of el.items) {
          if (typeof item === 'string') parts.push(item);
          else if (item?.text) parts.push(item.text);
          else if (item?.title) parts.push(item.title);
        }
      }

      // Card elements with sub-items  
      if (el.cards && Array.isArray(el.cards)) {
        for (const card of el.cards) {
          if (card.title) parts.push(card.title);
          if (card.text) parts.push(card.text);
          if (card.description) parts.push(card.description);
        }
      }

      // Chart data labels  
      if (el.chartData) {
        if (el.chartData.title) parts.push(el.chartData.title);
        if (el.chartData.labels && Array.isArray(el.chartData.labels)) {
          parts.push(el.chartData.labels.join(', '));
        }
      }

      // Table data
      if (el.tableData && Array.isArray(el.tableData)) {
        for (const row of el.tableData) {
          if (Array.isArray(row)) {
            parts.push(row.map(String).join(' | '));
          }
        }
      }

      // Image descriptions
      if (el.imageDescription) parts.push(`[Image: ${el.imageDescription}]`);
    }
  }

  const combined = parts.filter(Boolean).join(' ').trim();
  return combined.length > maxLength ? combined.substring(0, maxLength) : combined;
}

/**
 * Extract text from an HTML content string (used by ReportComposer).
 * Strips HTML tags and returns plain text summary.
 * 
 * @param {string} htmlContent - HTML string from TipTap editor
 * @param {number} maxLength - Maximum chars to return
 * @returns {string} Plain text summary
 */
export function extractPageTextSummary(htmlContent, maxLength = 300) {
  if (!htmlContent) return '';

  // Strip HTML tags
  let text = htmlContent.replace(/<[^>]*>/g, ' ');
  
  // Decode common HTML entities
  text = text
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ');

  // Collapse whitespace
  text = text.replace(/\s+/g, ' ').trim();

  return text.length > maxLength ? text.substring(0, maxLength) : text;
}

/**
 * Derive a live 1-line outline from actual slide element content.
 * Used instead of stale slide.outline to ensure API payloads reflect current content.
 * 
 * @param {Object} slide - Slide object with elements array
 * @returns {string} Live outline derived from current content (max 150 chars)
 */
export function deriveLiveOutline(slide) {
  if (!slide) return '';
  const parts = [];
  if (slide.title) parts.push(slide.title);
  if (slide.elements && Array.isArray(slide.elements)) {
    for (const el of slide.elements) {
      if (el.type === 'text' || el.type === 'card' || el.type === 'numbered_step') {
        const text = (el.content || el.text || el.title || el.label || el.heading || '').replace(/<[^>]*>/g, ' ').trim();
        if (text) parts.push(text);
      }
    }
  }
  const combined = parts.filter(Boolean).join(' | ').trim();
  return combined.length > 150 ? combined.substring(0, 150) : combined;
}

/**
 * Build lightweight slide summaries array for the orchestrate-all endpoint.
 * Includes title, outline/section topic, element types, and text summary.
 * Uses deriveLiveOutline() for fresh content-based outlines, and sends the
 * stored outline as old_outline so the AI can see what changed.
 * 
 * @param {Array} slides - Array of slide objects
 * @returns {Array<{slide_index: number, slide_id: string, text_summary: string, element_types: string[], title: string, outline: string, old_outline: string}>}
 */
export function buildSlidesSummary(slides) {
  if (!slides || !Array.isArray(slides)) return [];

  return slides.map((slide, index) => ({
    slide_index: index,
    slide_id: slide.id || `slide_${index}`,
    title: slide.title || '',
    outline: deriveLiveOutline(slide),
    old_outline: slide.outline || slide.sectionTopic || '',
    text_summary: extractSlideTextSummary(slide),
    element_types: (slide.elements || []).map(e => e.type || 'unknown'),
  }));
}

/**
 * Build lightweight page summaries array for report orchestrate-all endpoint.
 * Includes title, section order, and text summary for relevance matching.
 * Sends text_summary as the live outline so the backend always has fresh content.
 * 
 * @param {Array} pages - Array of page objects with .content (HTML)
 * @returns {Array<{page_index: number, page_id: string, title: string, section_order: number, text_summary: string, old_outline: string}>}
 */
export function buildPagesSummary(pages) {
  if (!pages || !Array.isArray(pages)) return [];

  return pages.map((page, index) => ({
    page_index: index,
    page_id: page.id || `page_${index}`,
    title: page.title || `Page ${index + 1}`,
    section_order: page.order || (index + 1),
    text_summary: extractPageTextSummary(page.content),
    old_outline: page.outline || '',
  }));
}
