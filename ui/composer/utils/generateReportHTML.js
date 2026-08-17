// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

// generateReportHTML.js - Shared utility for generating combined report HTML
// Used by both ExportModal (for export) and ReportPreviewModal (for preview)

/**
 * Convert markdown to HTML. If content is already HTML, return as-is.
 */
export const convertMarkdownToHTML = (markdown) => {
  if (!markdown) return '';

  // If content is already HTML (from text editor), return as is
  if (/^\s*<(p|div|h[1-6]|ul|ol|blockquote)[^>]*>/i.test(markdown) || (markdown.match(/<[^>]+>/g) || []).length > 3) {
    return markdown;
  }

  return markdown
    // Headers
    .replace(/^### (.*$)/gm, '<h3>$1</h3>')
    .replace(/^## (.*$)/gm, '<h2>$1</h2>')
    .replace(/^# (.*$)/gm, '<h1>$1</h1>')

    // Bold and italic
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')

    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')

    // Code
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/```[\s\S]*?```/g, (match) => {
      const code = match.replace(/```(\w+)?\n?/, '').replace(/\n?```$/, '');
      return `<pre><code>${code}</code></pre>`;
    })

    // Lists
    .replace(/^\* (.+$)/gm, '<li>$1</li>')
    .replace(/^\d+\. (.+$)/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')

    // Blockquotes
    .replace(/^> (.+$)/gm, '<blockquote>$1</blockquote>')

    // Line breaks
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(.+)$/, '<p>$1</p>')
    .replace(/<p><\/p>/g, '');
};

/**
 * Generate full HTML document content combining all report pages.
 * 
 * @param {Object} params
 * @param {Array} params.pages - Array of page objects with { id, order, title, content, wordCount }
 * @param {Object} params.reportMetadata - Report metadata { title, author, description }
 * @param {Object} params.reportGoal - Report goal { purpose }
 * @param {string} params.userType - User plan type ('free' or 'paid')
 * @returns {string} Full HTML document string
 */
export const generateReportHTML = ({ pages, reportMetadata, reportGoal, userType = 'free' }) => {
  const reportTitle = reportMetadata?.title || 'Untitled Report';

  // Cover metadata (author byline, generated-on date, page/word counts, goal box,
  // table of contents) intentionally REMOVED from exports — the exported document
  // should contain only the user's content, not authoring metadata.

  // Only include title if it's different from goal (to avoid duplication)
  const shouldIncludeTitle = !reportGoal?.purpose ||
    reportTitle.toLowerCase().trim() !== reportGoal.purpose.toLowerCase().trim().substring(0, reportTitle.length);

  // ── Letterhead / header / footer chrome (from reportMetadata configs) ──────
  const letterhead = reportMetadata?.letterheadConfig || {};
  const headerCfg = reportMetadata?.headerConfig || {};
  const footerCfg = reportMetadata?.footerConfig || {};
  const sortedPages = [...pages].sort((a, b) => a.order - b.order);
  const totalPages = sortedPages.length;

  // Escape chrome values — they can carry user OR LLM-authored strings (the
  // agent writes these configs), so unescaped injection here would be stored
  // XSS in every export/preview. Mirrors the backend share renderer.
  const escapeHtml = (s) => String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  const resolvePlaceholders = (text, pageNum) => escapeHtml(text || '')
    // en-GB = dd/mm/yyyy, matching the share renderer's %d/%m/%Y exactly.
    .replaceAll('{date}', new Date().toLocaleDateString('en-GB'))
    .replaceAll('{page}', String(pageNum))
    .replaceAll('{total}', String(totalPages))
    .replaceAll('{title}', escapeHtml(reportTitle))
    .replaceAll('{author}', escapeHtml(reportMetadata?.author || ''));

  const letterheadHTML = letterhead.enabled ? `
      <div class="letterhead">
        ${letterhead.logoUrl ? `<img class="letterhead-logo" src="${escapeHtml(letterhead.logoUrl)}" alt="" />` : ''}
        <div class="letterhead-identity">
          ${letterhead.companyName ? `<div class="letterhead-name">${escapeHtml(letterhead.companyName)}</div>` : ''}
          ${letterhead.address ? `<div class="letterhead-line">${escapeHtml(letterhead.address).replace(/\n/g, '<br/>')}</div>` : ''}
          ${[letterhead.phone, letterhead.email, letterhead.website].filter(Boolean).length
            ? `<div class="letterhead-line">${[letterhead.phone, letterhead.email, letterhead.website].filter(Boolean).map(escapeHtml).join(' &bull; ')}</div>` : ''}
        </div>
      </div>
      ${letterhead.showRule !== false ? '<div class="letterhead-rule"></div>' : ''}` : '';

  const hfBar = (cfg, pageNum, cls) => `
      <div class="page-hf ${cls}">
        <span class="hf-left">${cfg.showLogo && cfg.logoUrl ? `<img class="hf-logo" src="${escapeHtml(cfg.logoUrl)}" alt="" />` : ''}${resolvePlaceholders(cfg.leftContent, pageNum)}</span>
        <span class="hf-center">${resolvePlaceholders(cfg.centerContent, pageNum)}</span>
        <span class="hf-right">${resolvePlaceholders(cfg.rightContent, pageNum)}</span>
      </div>`;

  const pageContent = sortedPages
    .map((page, index) => {
      const pageNum = index + 1;
      const isFirst = index === 0;
      const showLetterhead = letterhead.enabled && (isFirst || letterhead.allPages);
      const showHeader = headerCfg.enabled && (!isFirst || headerCfg.showOnFirstPage);
      const showFooter = footerCfg.enabled && (!isFirst || footerCfg.showOnFirstPage !== false);
      return `
      <div class="page-break" id="page-${page.id}">
        ${showLetterhead ? letterheadHTML : ''}
        ${showHeader ? hfBar(headerCfg, pageNum, 'hf-top') : ''}
        <h2 class="page-title">${page.title || `Page ${page.order}`}</h2>
        <div class="page-content">
          ${convertMarkdownToHTML(page.content || '')}
        </div>
        ${showFooter ? hfBar(footerCfg, pageNum, 'hf-bottom') : ''}
      </div>
    `;
    }).join('');

  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${reportTitle}</title>
  <style>
      body {
          font-family: 'Georgia', 'Times New Roman', serif;
          line-height: 1.5;
          color: #000;
          width: 100%;
          max-width: none;
          margin: 0;
          padding: 0;
          background: white;
      }
      
      .report-header {
          text-align: center;
          margin-bottom: 40px;
          padding-bottom: 20px;
          border-bottom: 2px solid #e0e0e0;
      }
      
      .report-title {
          font-size: 2.5em;
          font-weight: 700;
          color: #1a1a1a;
          margin-bottom: 10px;
      }
      
      .report-subtitle {
          font-size: 1.2em;
          color: #666;
          margin-bottom: 5px;
      }
      
      .report-meta {
          color: #888;
          font-size: 0.9em;
      }
      
      .page-break {
          margin-bottom: 50px;
          page-break-inside: avoid;
      }

      /* ── Letterhead + running header/footer chrome ── */
      .letterhead {
          display: flex;
          align-items: center;
          gap: 18px;
          margin-bottom: 6px;
      }
      .letterhead-logo {
          max-height: 64px;
          max-width: 160px;
          object-fit: contain;
      }
      .letterhead-identity {
          flex: 1;
      }
      .letterhead-name {
          font-size: 1.35em;
          font-weight: 700;
          color: #1f2937;
      }
      .letterhead-line {
          font-size: 0.85em;
          color: #4b5563;
          line-height: 1.45;
      }
      .letterhead-rule {
          height: 2px;
          background: #1f2937;
          margin: 10px 0 24px 0;
      }
      .page-hf {
          display: flex;
          align-items: center;
          font-size: 0.78em;
          color: #6b7280;
      }
      .page-hf .hf-left { flex: 1; text-align: left; display: flex; align-items: center; gap: 6px; }
      .page-hf .hf-center { flex: 1; text-align: center; }
      .page-hf .hf-right { flex: 1; text-align: right; }
      .page-hf.hf-top { border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; margin-bottom: 18px; }
      .page-hf.hf-bottom { border-top: 1px solid #e5e7eb; padding-top: 6px; margin-top: 24px; }
      .hf-logo { max-height: 20px; max-width: 80px; object-fit: contain; }

      .page-title {
          color: #2c3e50;
          font-size: 1.8em;
          font-weight: 600;
          margin-bottom: 20px;
          padding-bottom: 10px;
          border-bottom: 1px solid #e0e0e0;
      }
      
      .page-content {
          text-align: justify;
          margin-bottom: 30px;
      }
      
      .page-content h1,
      .page-content h2,
      .page-content h3,
      .page-content h4,
      .page-content h5,
      .page-content h6 {
          color: #2c3e50;
          margin-top: 30px;
          margin-bottom: 15px;
          font-weight: 600;
      }
      
      .page-content p {
          margin-bottom: 15px;
          text-align: justify;
      }
      
      .page-content ul,
      .page-content ol {
          margin-bottom: 15px;
          padding-left: 30px;
      }
      
      .page-content li {
          margin-bottom: 5px;
      }
      
      .page-content blockquote {
          border-left: 4px solid #3498db;
          padding-left: 20px;
          margin: 20px 0;
          font-style: italic;
          color: #555;
          background: #f8f9fa;
          padding: 15px 20px;
          border-radius: 4px;
      }
      
      .page-content code {
          background: #f1f1f1;
          padding: 2px 6px;
          border-radius: 4px;
          font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
          font-size: 0.9em;
      }
      
      .page-content pre {
          background: #f8f8f8;
          padding: 15px;
          border-radius: 8px;
          overflow-x: auto;
          border: 1px solid #e0e0e0;
      }
      
      .page-content pre code {
          background: none;
          padding: 0;
      }
      
      .table-of-contents {
          background: #f8f9fa;
          padding: 20px;
          border-radius: 8px;
          margin-bottom: 40px;
          border: 1px solid #e0e0e0;
      }
      
      .toc-title {
          font-size: 1.3em;
          font-weight: 600;
          margin-bottom: 15px;
          color: #2c3e50;
      }
      
      .toc-item {
          padding: 5px 0;
          border-bottom: 1px dotted #ccc;
          display: flex;
          justify-content: space-between;
      }
      
      .toc-item:last-child {
          border-bottom: none;
      }
      
      .page-number {
          color: #666;
          font-weight: 500;
      }
      
      .footer {
          margin-top: 60px;
          padding-top: 20px;
          border-top: 1px solid #e0e0e0;
          text-align: center;
          color: #888;
          font-size: 0.8em;
      }
      
      .page-content img {
          max-width: 100%;
          height: auto;
          border-radius: 4px;
          margin: 10px 0;
      }

      .page-content table {
          width: 100%;
          border-collapse: collapse;
          margin: 15px 0;
      }

      .page-content th,
      .page-content td {
          border: 1px solid #ddd;
          padding: 8px 12px;
          text-align: left;
      }

      .page-content th {
          background-color: #f5f5f5;
          font-weight: 600;
      }

      @media print {
          body {
              padding: 20px;
          }
          
          .page-break {
              page-break-after: always;
          }
          
          .page-break:last-child {
              page-break-after: avoid;
          }
          
          .report-header {
              page-break-after: avoid;
          }
          
          .table-of-contents {
              page-break-after: always;
          }
      }
      
      @media screen and (max-width: 768px) {
          body {
              padding: 20px 15px;
          }
          
          .report-title {
              font-size: 2em;
          }
          
          .page-title {
              font-size: 1.5em;
          }
      }
          margin-bottom: 10px;
          color: #1a1a1a;
      }
      
      .report-meta {
          font-size: 0.9em;
          color: #666;
          margin-bottom: 5px;
      }
      
      .table-of-contents {
          background: #f8f9fa;
          padding: 20px;
          border-radius: 8px;
          margin-bottom: 40px;
      }
      
      .toc-title {
          font-size: 1.2em;
          font-weight: 600;
          margin-bottom: 15px;
      }
      
      .toc-item {
          margin-bottom: 8px;
          padding-left: 20px;
      }
      
      .page-break {
          margin-bottom: 40px;
          page-break-before: auto;
      }
      
      .page-title {
          font-size: 1.8em;
          font-weight: 600;
          margin-bottom: 20px;
          color: #2c3e50;
          border-bottom: 1px solid #e0e0e0;
          padding-bottom: 10px;
      }
      
      .page-content {
          font-size: 1em;
          line-height: 1.7;
      }
      
      .page-content h1 {
          font-size: 1.6em;
          margin-top: 30px;
          margin-bottom: 15px;
      }
      
      .page-content h2 {
          font-size: 1.4em;
          margin-top: 25px;
          margin-bottom: 12px;
      }
      
      .page-content h3 {
          font-size: 1.2em;
          margin-top: 20px;
          margin-bottom: 10px;
      }
      
      .page-content p {
          margin-bottom: 15px;
      }
      
      .page-content ul, .page-content ol {
          margin-bottom: 15px;
          padding-left: 25px;
      }
      
      .page-content li {
          margin-bottom: 5px;
      }
      
      .page-content blockquote {
          border-left: 4px solid #007acc;
          margin: 20px 0;
          padding: 10px 20px;
          background: rgba(0, 122, 204, 0.05);
          font-style: italic;
      }
      
      .page-content code {
          background: #f4f4f4;
          padding: 2px 6px;
          border-radius: 3px;
          font-family: Monaco, Consolas, monospace;
          font-size: 0.9em;
      }
      
      .page-content pre {
          background: #f8f8f8;
          padding: 15px;
          border-radius: 5px;
          overflow-x: auto;
          border: 1px solid #e0e0e0;
      }
      
      .footer {
          margin-top: 60px;
          padding-top: 20px;
          border-top: 1px solid #e0e0e0;
          text-align: center;
          font-size: 0.8em;
          color: #666;
      }
      
      @media print {
          body {
              width: 100%;
              margin: 0;
              padding: 0;
              color: #000;
          }
          @page {
              size: auto;
              margin: 15mm 15mm 15mm 15mm;
          }
          
          .page-break {
              page-break-before: always;
          }
          
          .page-break:first-child {
              page-break-before: auto;
          }
      }
  </style>
</head>
<body>
  ${shouldIncludeTitle ? `<div class="report-header"><h1 class="report-title">${reportTitle}</h1></div>` : ''}

  ${pageContent}

</body>
</html>`;
};
