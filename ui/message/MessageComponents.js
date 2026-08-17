// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

// WebHTMLRenderer — lightweight markdown-ish text -> HTML renderer used by
// PageEditor.js's preview panel.
//
// Extracted from Citra-UI's components/message/MessageComponents.js (a
// ~1100-line chat-message-rendering file) rather than ported wholesale:
// WebHTMLRenderer is the only export PageEditor.js uses, and it turned out
// to be fully self-contained — the file's other exports (WebMarkdownText,
// FormattedMessageContent, MessageActions, etc.) depend on ShareManager,
// RichMessageRenderer (itself ~6000 lines, pulling in Mermaid/ChartJs/Ascii
// diagram rendering — the AI-diagram-insertion cluster explicitly out of
// scope for this build), textProcessing, and other chat-specific machinery
// none of which WebHTMLRenderer's own body ever references. Verified by
// grep across its body before extracting.
import React from 'react';
import { Platform, Text } from 'react-native';

export const WebHTMLRenderer = ({ content, theme, style, shouldAnimate }) => {
  const sanitizeHtml = (html) => {
    try {
      // Remove any orphaned text nodes that could cause React Native Web errors
      return html
        .replace(/>\s+</g, '><') // Remove whitespace between tags
        .replace(/^\s+|\s+$/g, '') // Trim leading/trailing whitespace
        .replace(/\n\s*\n/g, '<br><br>') // Ensure proper line breaks
        .replace(/([^>])\n([^<])/g, '$1<br>$2'); // Convert standalone newlines to <br>
    } catch (error) {
      console.error('Error sanitizing HTML:', error);
      return html || '';
    }
  };

  const processContent = (text) => {
    try {
      if (!text || typeof text !== 'string') {
        return '';
      }

      // Enhanced processing for better formatting
      let processedText = text
        // Handle headers
        .replace(/###\s+(.*?)(?:\n|$)/g, (_, heading) => `
          <h3 style="
            font-size: 18px;
            font-weight: bold;
            color: ${theme.text};
            margin: 16px 0 8px 0;
            padding: 0;
            line-height: 1.4;
          ">${heading}</h3>
        `)
        .replace(/##\s+(.*?)(?:\n|$)/g, (_, heading) => `
          <h2 style="
            font-size: 20px;
            font-weight: bold;
            color: ${theme.text};
            margin: 20px 0 10px 0;
            padding: 0;
            line-height: 1.4;
          ">${heading}</h2>
        `)
        .replace(/#\s+(.*?)(?:\n|$)/g, (_, heading) => `
          <h1 style="
            font-size: 22px;
            font-weight: bold;
            color: ${theme.text};
            margin: 24px 0 12px 0;
            padding: 0;
            line-height: 1.4;
          ">${heading}</h1>
        `)
        // Handle unordered lists
        .replace(/^\s*[-*+]\s+(.+)$/gm, (match, item) => `
          <li style="
            margin-bottom: 4px;
            line-height: 1.5;
            color: ${theme.text};
          ">${item}</li>
        `)
        // Handle ordered lists
        .replace(/^\s*\d+\.\s+(.+)$/gm, (match, item) => `
          <li style="
            margin-bottom: 4px;
            line-height: 1.5;
            color: ${theme.text};
          ">${item}</li>
        `)
        // Wrap consecutive list items in ul/ol tags
        .replace(/(<li[^>]*>.*?<\/li>\s*)+/gs, (listItems) => {
          // Determine if it's ordered or unordered based on original format
          const isOrdered = /^\s*\d+\.\s+/.test(text);
          const tag = isOrdered ? 'ol' : 'ul';
          return `<${tag} style="
            margin: 8px 0;
            padding-left: 20px;
          ">${listItems}</${tag}>`;
        });

      return processedText
        // Handle horizontal rules first (before other conversions)
        .replace(/^---+\s*$/gm, `<hr style="
          border: none;
          border-top: 2px solid ${theme.isDark ? '#4a5568' : '#e2e8f0'};
          margin: 24px 0;
          width: 100%;
        " />`)
        // Handle code blocks (before other formatting to protect content)
        .replace(/```([\s\S]*?)```/g, (match, code) => {
          const lines = code.split('\n');
          const language = lines[0].trim();
          const codeContent = lines.slice(language ? 1 : 0).join('\n').trim();

          return `<pre style="
            background-color: ${theme.isDark ? '#2a2a2a' : '#f8f8f8'};
            color: ${theme.isDark ? '#ffffff' : '#333333'};
            padding: 16px;
            margin: 16px 0;
            border-radius: 8px;
            border: 1px solid ${theme.isDark ? '#444444' : '#e1e4e8'};
            overflow-x: auto;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.4;
          "><code>${codeContent}</code></pre>`;
        })
        // Handle inline code (before bold/italic to protect code content)
        .replace(/`([^`]+)`/g, `<code style="
          background-color: ${theme.isDark ? '#404040' : '#f3f4f4'};
          color: ${theme.isDark ? '#f8f8f2' : '#e83e8c'};
          padding: 2px 4px;
          border-radius: 3px;
          font-family: 'Courier New', monospace;
          font-size: 14px;
        ">$1</code>`)
        // Handle display math \[...\]
        .replace(/\\\[([\s\S]*?)\\\]/g, (match, math) => {
          const processedMath = math
            .replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, '<span style="display: inline-block; text-align: center;"><span style="display: block; border-bottom: 1px solid; padding-bottom: 2px;">$1</span><span style="display: block; padding-top: 2px;">$2</span></span>')
            .replace(/\\sqrt\{([^}]+)\}/g, '√($1)')
            .replace(/\\cdot/g, '·')
            .replace(/\\times/g, '×')
            .replace(/\\div/g, '÷')
            .replace(/\\pm/g, '±')
            .replace(/\\leq/g, '≤')
            .replace(/\\geq/g, '≥')
            .replace(/\\neq/g, '≠')
            .replace(/\\alpha/g, 'α').replace(/\\beta/g, 'β').replace(/\\gamma/g, 'γ')
            .replace(/\\delta/g, 'δ').replace(/\\epsilon/g, 'ε').replace(/\\theta/g, 'θ')
            .replace(/\\lambda/g, 'λ').replace(/\\mu/g, 'μ').replace(/\\pi/g, 'π')
            .replace(/\\sigma/g, 'σ').replace(/\\phi/g, 'φ').replace(/\\omega/g, 'ω')
            .replace(/\\sum/g, 'Σ').replace(/\\int/g, '∫').replace(/\\infty/g, '∞')
            .replace(/\\partial/g, '∂').replace(/\\nabla/g, '∇')
            .replace(/\{([^}]+)\}/g, '$1')
            .replace(/\\/g, '');

          return `<div style="
            background-color: ${theme.isDark ? '#2a2a2a' : '#f8f9fa'};
            color: ${theme.isDark ? '#ffffff' : '#333333'};
            padding: 16px;
            margin: 12px 0;
            border-radius: 8px;
            border-left: 4px solid ${theme.isDark ? '#4a9eff' : '#007acc'};
            text-align: center;
            font-size: 18px;
            font-weight: 500;
            line-height: 1.5;
            font-family: 'Times New Roman', serif;
          ">${processedMath}</div>`;
        })
        // Handle inline math \(...\)
        .replace(/\\\(([\s\S]*?)\\\)/g, (match, math) => {
          const processedMath = math
            .replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, '$1/$2')
            .replace(/\\sqrt\{([^}]+)\}/g, '√($1)')
            .replace(/\\cdot/g, '·')
            .replace(/\\times/g, '×')
            .replace(/\\div/g, '÷')
            .replace(/\\pm/g, '±')
            .replace(/\\leq/g, '≤')
            .replace(/\\geq/g, '≥')
            .replace(/\\neq/g, '≠')
            .replace(/\\alpha/g, 'α').replace(/\\beta/g, 'β').replace(/\\gamma/g, 'γ')
            .replace(/\\delta/g, 'δ').replace(/\\epsilon/g, 'ε').replace(/\\theta/g, 'θ')
            .replace(/\\lambda/g, 'λ').replace(/\\mu/g, 'μ').replace(/\\pi/g, 'π')
            .replace(/\\sigma/g, 'σ').replace(/\\phi/g, 'φ').replace(/\\omega/g, 'ω')
            .replace(/\\sum/g, 'Σ').replace(/\\int/g, '∫').replace(/\\infty/g, '∞')
            .replace(/\\partial/g, '∂').replace(/\\nabla/g, '∇')
            .replace(/\{([^}]+)\}/g, '$1')
            .replace(/\\/g, '');

          return `<span style="
            background-color: ${theme.isDark ? '#3a3a3a' : '#f0f0f0'};
            color: ${theme.isDark ? '#ffffff' : '#333333'};
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 16px;
            font-weight: 500;
            font-family: 'Times New Roman', serif;
          ">${processedMath}</span>`;
        })
        // Handle images
        .replace(/!\[([^\]]*)\]\s*\(([^)]+)\)/g, (match, alt, src) => {
          return `<div style="text-align: center; margin: 16px 0;">
            <img src="${src}" alt="${alt}" style="
              max-width: 100%;
              height: auto;
              border-radius: 8px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.1);
              border: 1px solid #e0e0e0;
            " />
            ${alt ? `<div style="font-size: 12px; color: ${theme.text}; opacity: 0.7; margin-top: 8px; font-style: italic;">${alt}</div>` : ''}
          </div>`;
        })
        // Handle bold text - robust patterns to handle multiline and complex text
        .replace(/\*\*((?:[^*]|\*(?!\*))+?)\*\*/g, '<strong>$1</strong>')
        .replace(/__((?:[^_]|_(?!_))+?)__/g, '<strong>$1</strong>')
        // Handle italic text - robust patterns to handle multiline and complex text
        .replace(/\*((?:[^*]|\*\*)+?)\*/g, '<em>$1</em>')
        .replace(/_((?:[^_]|__)+?)_/g, '<em>$1</em>')
        // Handle strikethrough text - robust patterns to handle multiline and complex text
        .replace(/~~((?:[^~]|~(?!~))+?)~~/g, '<del style="text-decoration: line-through;">$1</del>')
        // Handle blockquotes
        .replace(/^>\s+(.+)$/gm, `<blockquote style="
          background-color: ${theme.isDark ? 'rgba(74, 158, 255, 0.1)' : 'rgba(0, 122, 204, 0.05)'};
          border-left: 4px solid ${theme.isDark ? '#4a9eff' : '#007acc'};
          padding: 12px 16px;
          margin: 12px 0;
          border-radius: 4px;
          font-style: italic;
        ">$1</blockquote>`)
        // Handle line breaks with proper spacing
        .replace(/\n\n/g, '<br><br>')
        .replace(/\n/g, '<br>');
    } catch (error) {
      console.error('Error processing content for WebHTMLRenderer:', error);
      return (text || '').replace(/\n/g, '<br>');
    }
  };

  const safeGetHtmlContent = () => {
    try {
      const processedContent = processContent(content);
      return sanitizeHtml(processedContent);
    } catch (error) {
      console.error('Error generating HTML content:', error);
      return sanitizeHtml((content || '').replace(/\n/g, '<br>'));
    }
  };

  const htmlContent = safeGetHtmlContent();

  if (Platform.OS === 'web') {
    try {
      return (
        <div
          className={`web-bot-message ${shouldAnimate ? 'web-bot-message-content' : ''}`}
          style={{
            color: style?.color || theme.text,
            fontSize: style?.fontSize || 16,
            fontWeight: style?.fontWeight || '400',
            lineHeight: 1.6,
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            opacity: style?.opacity ?? 1,
          }}
          dangerouslySetInnerHTML={{ __html: htmlContent }}
        />
      );
    } catch (error) {
      console.error('Error rendering HTML content:', error);
      return (
        <div className="web-bot-message">
          {content || ''}
        </div>
      );
    }
  } else {
    return <Text style={style}>{content}</Text>;
  }
};
