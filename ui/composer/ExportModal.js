// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

// ExportModal.js - Export report to various formats
import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Modal,
  ScrollView,
  Alert,
  Platform,
  ActivityIndicator
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';
import globalImageCache from '../../utils/globalImageCache';
import { generateReportHTML } from './utils/generateReportHTML';


const ExportModal = ({
  visible,
  onClose,
  pages,
  reportMetadata,
  reportGoal,
  theme,
  userType = 'free',
  onOpenCredits,
}) => {
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState('');
  const [selectedFormat, setSelectedFormat] = useState('pdf');


  const exportFormats = [
    {
      id: 'pdf',
      name: 'PDF Document',
      description: 'Professional PDF with formatting',
      icon: 'document-text',
      color: '#FF3B30'
    },
    {
      id: 'copy',
      name: 'Copy to Clipboard',
      description: 'Copy with formatting (for Word/Docs)',
      icon: 'copy',
      color: '#8E8E93'
    },
    {
      id: 'html',
      name: 'HTML Document',
      description: 'Web page with styling',
      icon: 'globe',
      color: '#007AFF'
    },
    {
      id: 'markdown',
      name: 'Markdown File',
      description: 'Plain text with markdown formatting',
      icon: 'code-slash',
      color: '#34C759'
    },
    {
      id: 'docx',
      name: 'Word Document',
      description: 'Microsoft Word compatible',
      icon: 'document',
      color: '#2E5DCC'
    }
  ];

  // Generate HTML content for the report using shared utility
  const generateHTMLContent = useCallback(() => {
    return generateReportHTML({ pages, reportMetadata, reportGoal, userType });
  }, [pages, reportMetadata, reportGoal, userType]);

  // Generate markdown content
  const generateMarkdownContent = useCallback(() => {
    const reportTitle = reportMetadata.title || 'Untitled Report';
    const currentDate = new Date().toLocaleDateString();
    const totalWords = pages.reduce((sum, page) => sum + (page.wordCount || 0), 0);

    // Only include title if it's different from goal (to avoid duplication)
    const shouldIncludeTitle = !reportGoal?.purpose || 
      reportTitle.toLowerCase().trim() !== reportGoal.purpose.toLowerCase().trim().substring(0, reportTitle.length);

    const tableOfContents = pages
      .sort((a, b) => a.order - b.order)
      .map((page, index) => `${index + 1}. ${page.title || `Page ${page.order}`}`)
      .join('\n');

    const pageContent = pages
      .sort((a, b) => a.order - b.order)
      .map(page => `
## ${page.title || `Page ${page.order}`}

${page.content || ''}

---
`).join('\n');

    const titleSection = shouldIncludeTitle ? `# ${reportTitle}\n\n` : '';
    const goalSection = reportGoal?.purpose ? `**Goal:** ${reportGoal.purpose}\n\n` : '';

    return `${titleSection}${goalSection}**Generated:** ${currentDate}  
**Pages:** ${pages.length}  
**Words:** ${totalWords}  
${reportMetadata.description ? `**Description:** ${reportMetadata.description}` : ''}

## Table of Contents

${tableOfContents}

---

${pageContent}
`;
  }, [pages, reportMetadata, reportGoal]);

  /**
   * Replace external image URLs (S3 presigned, etc.) in HTML with embedded base64 data.
   * This ensures exported files don't depend on expiring URLs or CORS.
   * Images already cached in globalImageCache are converted instantly.
   */
  const replaceImagesWithBase64 = useCallback(async (html) => {
    if (!html) return html;

    // Find all <img src="..."> tags
    const imgRegex = /<img\s+[^>]*src\s*=\s*["']([^"']+)["'][^>]*>/gi;
    const matches = [...html.matchAll(imgRegex)];
    if (matches.length === 0) return html;

    // Collect URLs that need conversion (skip data: and blob: which are already embedded)
    const urlsToConvert = matches
      .map(m => m[1])
      .filter(url => url && !url.startsWith('data:'));

    if (urlsToConvert.length === 0) return html;

    // Pre-cache all images first (batch fetch)
    await globalImageCache.preCacheAll(urlsToConvert);

    // Convert each to base64 and replace in HTML
    let result = html;
    for (const match of matches) {
      const originalUrl = match[1];
      if (!originalUrl || originalUrl.startsWith('data:')) continue;

      try {
        const base64 = await globalImageCache.getAsBase64(originalUrl);
        if (base64) {
          // Replace this specific occurrence
          result = result.replace(match[0], match[0].replace(originalUrl, base64));
        }
      } catch (err) {
        console.warn('[ExportModal] Failed to embed image:', err.message);
        // Leave original URL as fallback
      }
    }

    return result;
  }, []);

  /**
   * Strip editor-only data attributes and normalize image sizes for export.
   * - data-chart-config contains huge URL-encoded Chart.js JSON that breaks Word's HTML parser.
   * - Inline percentage widths (e.g. "width: 80%") are not handled reliably by Word;
   *   replace them with a fixed width that fits within the 6.5in content area.
   */
  const cleanHtmlForExport = useCallback((html, format) => {
    if (!html) return html;
    let result = html
      .replace(/\s+data-chart-config="[^"]*"/gi, '')
      .replace(/\s+data-user-media="[^"]*"/gi, '');

    if (format === 'docx') {
      // Replace inline percentage/pixel widths on <img> tags with Word-safe fixed width.
      // Word ignores CSS max-width and uses native image pixels, so we set an explicit width attribute.
      result = result.replace(/<img\b([^>]*)>/gi, (match, attrs) => {
        // Remove any existing style width (percentage or px) and width attribute
        let cleaned = attrs
          .replace(/\s*style\s*=\s*"[^"]*"/gi, '')
          .replace(/\s*width\s*=\s*"[^"]*"/gi, '');
        // Add Word-compatible width (100% of content area) and auto height
        return `<img${cleaned} width="100%" style="max-width:6.5in;height:auto;display:block;margin:10pt auto;">`;
      });
    }

    return result;
  }, []);

  // Handle export
  const handleExport = useCallback(async (format) => {
    try {
      setIsExporting(true);

      const reportTitle = reportMetadata.title || 'Untitled Report';
      const fileName = `${reportTitle.replace(/[^a-zA-Z0-9]/g, '_')}_${Date.now()}`;

      switch (format) {
        case 'pdf':
          if (Platform.OS === 'web') {
            // For web, open new window with HTML and use browser print dialog
            setExportProgress('Processing images...');
            const htmlContent = cleanHtmlForExport(await replaceImagesWithBase64(generateHTMLContent()));
            const printWindow = window.open('', '_blank', 'width=800,height=600');

            if (printWindow) {
              printWindow.document.write(htmlContent);
              printWindow.document.close();

              // Wait for content to load then print
              printWindow.onload = function () {
                setTimeout(() => {
                  printWindow.print();
                  // Close after print dialog (user can save as PDF from there)
                }, 500);
              };

              // Fallback if onload doesn't fire
              setTimeout(() => {
                printWindow.print();
              }, 1000);
            } else {
              Alert.alert('Popup Blocked', 'Please allow popups to export PDF.');
              return;
            }
          }
          break;

        case 'html':
          if (Platform.OS === 'web') {
            setExportProgress('Processing images...');
            const htmlContent = cleanHtmlForExport(await replaceImagesWithBase64(generateHTMLContent()));
            const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${fileName}.html`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
          }
          break;

        case 'markdown':
          if (Platform.OS === 'web') {
            const markdownContent = generateMarkdownContent();
            const blob = new Blob([markdownContent], { type: 'text/markdown;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${fileName}.md`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
          }
          break;

        case 'docx':
          if (Platform.OS === 'web') {
            // Only include title if it's different from goal (to avoid duplication)
            const shouldIncludeTitle = !reportGoal?.purpose || 
              reportTitle.toLowerCase().trim() !== reportGoal.purpose.toLowerCase().trim().substring(0, reportTitle.length);

            // Create Word-compatible HTML with better formatting control
            const wordHtml = `
<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office" 
      xmlns:w="urn:schemas-microsoft-com:office:word" 
      xmlns="http://www.w3.org/TR/REC-html40">
<head>
<meta charset="utf-8">
<meta name="ProgId" content="Word.Document">
<meta name="Generator" content="Microsoft Word 15">
<meta name="Originator" content="Microsoft Word 15">
<title>${reportGoal?.purpose || reportTitle}</title>
<!--[if gte mso 9]>
<xml>
<w:WordDocument>
<w:View>Print</w:View>
<w:Zoom>100</w:Zoom>
<w:DoNotBreakWrappedTables/>
<w:DoNotSnapToGridInCell/>
</w:WordDocument>
</xml>
<![endif]-->
<style>
@page Section1 { size: 8.5in 11.0in; margin: 1.0in 1.0in 1.0in 1.0in; mso-header-margin: 0.5in; mso-footer-margin: 0.5in; mso-paper-source: 0; }
div.Section1 { page: Section1; word-wrap: break-word; overflow: hidden; }
body { font-family: "Times New Roman", serif; font-size: 12pt; line-height: 1.5; word-wrap: break-word; }
h1 { font-size: 24pt; font-weight: bold; margin: 0 0 12pt 0; color: #000; page-break-after: avoid; }
h2 { font-size: 18pt; font-weight: bold; margin: 24pt 0 12pt 0; color: #000; page-break-after: avoid; }
h3 { font-size: 14pt; font-weight: bold; margin: 18pt 0 10pt 0; color: #000; page-break-after: avoid; }
h4 { font-size: 12pt; font-weight: bold; margin: 14pt 0 8pt 0; color: #000; page-break-after: avoid; }
p { margin: 0 0 10pt 0; text-align: justify; }
ul, ol { margin: 0 0 10pt 0; padding-left: 40pt; }
li { margin: 0 0 5pt 0; }
strong, b { font-weight: bold; }
em, i { font-style: italic; }
blockquote { border-left: 4pt solid #007acc; margin: 10pt 0; padding: 10pt 15pt; background: #f8f9fa; font-style: italic; }
code { background: #f4f4f4; padding: 2pt 6pt; font-family: Consolas, Monaco, monospace; font-size: 11pt; }
pre { background: #f8f8f8; padding: 15pt; border: 1pt solid #e0e0e0; margin: 10pt 0; word-wrap: break-word; overflow-x: hidden; }
hr { border: none; border-top: 1pt solid #ccc; margin: 12pt 0; }
.goal-box { background: #f0f7ff; border-left: 4pt solid #007acc; padding: 12pt; margin: 0 0 12pt 0; font-style: italic; }
.section-break { margin-top: 24pt; padding-top: 12pt; border-top: 2pt solid #e0e0e0; }
img { width: 100%; max-width: 6.5in; height: auto; display: block; margin: 10pt 0; mso-width-percent: 1000; }
</style>
</head>
<body>
<div class="Section1">
${shouldIncludeTitle ? `<h1>${reportTitle}</h1>` : ''}
${reportGoal?.purpose ? `<div class="goal-box"><strong>Goal:</strong> ${reportGoal.purpose}</div>` : ''}
<p style="margin-bottom: 12pt;"><strong>Generated:</strong> ${new Date().toLocaleDateString()} &nbsp;|&nbsp; <strong>Sections:</strong> ${pages.length} &nbsp;|&nbsp; <strong>Words:</strong> ${pages.reduce((sum, page) => sum + (page.wordCount || 0), 0).toLocaleString()}</p>
<hr>
${pages.sort((a, b) => a.order - b.order).map((page, idx) => `
${idx > 0 ? '<div class="section-break"></div>' : ''}
<h2>${page.title || 'Untitled Section'}</h2>
${page.content || ''}
`).join('')}
</div>
</body>
</html>`;

            // Embed images as base64 so the .doc file is self-contained
            setExportProgress('Processing images...');
            const processedWordHtml = cleanHtmlForExport(await replaceImagesWithBase64(wordHtml), 'docx');

            const blob = new Blob([processedWordHtml], {
              type: 'application/msword'
            });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${fileName}.doc`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
          }
          break;

        case 'copy':
          if (Platform.OS === 'web') {
            try {
              setExportProgress('Processing images...');
              const htmlContent = cleanHtmlForExport(await replaceImagesWithBase64(generateHTMLContent()));
              // Only include title if it's different from goal (to avoid duplication)
              const shouldIncludeTitle = !reportGoal?.purpose || 
                reportTitle.toLowerCase().trim() !== reportGoal.purpose.toLowerCase().trim().substring(0, reportTitle.length);
              
              // Create a properly formatted plain text version for fallback
              const titleLine = shouldIncludeTitle ? `${reportTitle}\n${'='.repeat(reportTitle.length)}\n\n` : '';
              const goalText = reportGoal?.purpose ? `Goal: ${reportGoal.purpose}\n\n` : '';
              const textContent = `${titleLine}${goalText}${pages
                .sort((a, b) => a.order - b.order)
                .map(p => {
                  // Convert HTML content to plain text
                  let text = p.content || '';
                  text = text.replace(/<br\s*\/?>/gi, '\n');
                  text = text.replace(/<\/p>/gi, '\n\n');
                  text = text.replace(/<\/h[1-6]>/gi, '\n\n');
                  text = text.replace(/<\/li>/gi, '\n');
                  text = text.replace(/<li>/gi, '• ');
                  text = text.replace(/<[^>]*>/g, '');
                  text = text.replace(/&nbsp;/g, ' ')
                             .replace(/&amp;/g, '&')
                             .replace(/&lt;/g, '<')
                             .replace(/&gt;/g, '>')
                             .replace(/&quot;/g, '"')
                             .replace(/&#39;/g, "'");
                  return `${p.title}\n${'-'.repeat(p.title.length)}\n\n${text.trim()}`;
                })
                .join('\n\n---\n\n')}`;

              const htmlBlob = new Blob([htmlContent], { type: 'text/html' });
              const textBlob = new Blob([textContent], { type: 'text/plain' });

              const data = [new ClipboardItem({
                'text/html': htmlBlob,
                'text/plain': textBlob
              })];

              await navigator.clipboard.write(data);
              Alert.alert('Copied!', 'Report copied to clipboard with formatting. You can now paste it into Word or Google Docs.');
            } catch (err) {
              console.error('Clipboard write failed:', err);
              Alert.alert('Error', 'Failed to copy to clipboard. Please try using Chrome or Edge.');
            }
          }
          break;

        default:
          throw new Error('Unsupported export format');
      }

      Alert.alert('Success', `Report exported successfully as ${format.toUpperCase()}!`);
      onClose();

    } catch (error) {
      console.error('Export error:', error);
      Alert.alert('Export Failed', 'There was an error exporting your report. Please try again.');
    } finally {
      setIsExporting(false);
      setExportProgress('');
    }
  }, [reportMetadata, pages, generateHTMLContent, generateMarkdownContent, replaceImagesWithBase64, onClose]);

  const getExportStats = useCallback(() => {
    const totalWords = pages.reduce((sum, page) => sum + (page.wordCount || 0), 0);
    const totalPages = pages.length;
    const avgWordsPerPage = totalPages > 0 ? Math.round(totalWords / totalPages) : 0;

    return { totalWords, totalPages, avgWordsPerPage };
  }, [pages]);

  const stats = getExportStats();

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent={true}
      onRequestClose={onClose}
    >
      <View style={styles.modalOverlay}>
        <View style={[styles.modalContent, { backgroundColor: theme.surface }]}>
          {/* Header */}
          <View style={[styles.modalHeader, { borderBottomColor: theme.borderColor }]}>
            <Text style={[styles.modalTitle, { color: theme.text }]}>
              Export Report
            </Text>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={theme.text} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalBody}>
            {/* Report Stats */}
            <View style={[styles.statsContainer, {
              backgroundColor: theme.inputBackground,
              borderColor: theme.borderColor
            }]}>
              <Text style={[styles.statsTitle, { color: theme.text }]}>
                Report Summary
              </Text>
              <View style={styles.statsGrid}>
                <View style={styles.statItem}>
                  <Text style={[styles.statLabel, { color: theme.placeholderText }]}>
                    Pages
                  </Text>
                  <Text style={[styles.statValue, { color: theme.text }]}>
                    {stats.totalPages}
                  </Text>
                </View>
                <View style={styles.statItem}>
                  <Text style={[styles.statLabel, { color: theme.placeholderText }]}>
                    Total Words
                  </Text>
                  <Text style={[styles.statValue, { color: theme.text }]}>
                    {stats.totalWords.toLocaleString()}
                  </Text>
                </View>
                <View style={styles.statItem}>
                  <Text style={[styles.statLabel, { color: theme.placeholderText }]}>
                    Avg/Page
                  </Text>
                  <Text style={[styles.statValue, { color: theme.text }]}>
                    {stats.avgWordsPerPage}
                  </Text>
                </View>
              </View>
            </View>

            {/* Export Formats */}
            <View style={styles.formatsContainer}>
              <Text style={[styles.sectionTitle, { color: theme.text }]}>
                Choose Export Format
              </Text>
              {exportFormats.map(format => (
                <TouchableOpacity
                  key={format.id}
                  style={[
                    styles.formatOption,
                    {
                      backgroundColor: selectedFormat === format.id ? theme.primary + '20' : theme.inputBackground,
                      borderColor: selectedFormat === format.id ? theme.primary : theme.borderColor
                    }
                  ]}
                  onPress={() => setSelectedFormat(format.id)}
                >
                  <View style={[styles.formatIcon, { backgroundColor: format.color }]}>
                    <Ionicons name={format.icon} size={20} color="white" />
                  </View>
                  <View style={styles.formatInfo}>
                    <Text style={[styles.formatName, { color: theme.text }]}>
                      {format.name}
                    </Text>
                    <Text style={[styles.formatDescription, { color: theme.placeholderText }]}>
                      {format.description}
                    </Text>
                  </View>
                  {selectedFormat === format.id && (
                    <Ionicons name="checkmark-circle" size={20} color={theme.primary} />
                  )}
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>

          {/* Actions */}
          <View style={[styles.modalActions, { borderTopColor: theme.borderColor }]}>
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: theme.borderColor }]}
              onPress={onClose}
            >
              <Text style={[styles.actionButtonText, { color: theme.text }]}>
                Cancel
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: theme.primary }]}
              onPress={() => handleExport(selectedFormat)}
              disabled={isExporting}
            >
              {isExporting ? (
                <Text style={[styles.actionButtonText, { color: theme.buttonText }]}>
                  Exporting...
                </Text>
              ) : (
                <>
                  <Ionicons name="download" size={16} color={theme.buttonText} />
                  <Text style={[styles.actionButtonText, { color: theme.buttonText }]}>
                    Export
                  </Text>
                </>
              )}
            </TouchableOpacity>
          </View>

          {/* Export progress overlay */}
          {isExporting && (
            <View style={[styles.exportingOverlay, { backgroundColor: theme.surface + 'F2' }]}>
              <ActivityIndicator size="large" color={theme.primary} />
              <Text style={[styles.exportingText, { color: theme.text }]}>
                {exportProgress || 'Preparing export...'}
              </Text>
            </View>
          )}
        </View>
      </View>
    </Modal>
  );
};

const styles = {
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContent: {
    width: '90%',
    maxWidth: 500,
    maxHeight: '80%',
    borderRadius: 12,
    overflow: 'hidden',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
  },
  modalBody: {
    flex: 1,
    padding: 20,
  },
  statsContainer: {
    padding: 16,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 20,
  },
  statsTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 12,
  },
  statsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  statItem: {
    alignItems: 'center',
  },
  statLabel: {
    fontSize: 12,
    marginBottom: 4,
  },
  statValue: {
    fontSize: 18,
    fontWeight: '600',
  },
  formatsContainer: {
    gap: 12,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  formatOption: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 8,
    borderWidth: 2,
    gap: 12,
  },
  formatIcon: {
    width: 40,
    height: 40,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  formatInfo: {
    flex: 1,
  },
  formatName: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 2,
  },
  formatDescription: {
    fontSize: 12,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderTopWidth: 1,
    gap: 12,
  },
  actionButton: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 12,
    borderRadius: 8,
    gap: 8,
  },
  actionButtonText: {
    fontSize: 14,
    fontWeight: '600',
  },
  exportingOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 100,
    borderRadius: 12,
  },
  exportingText: {
    marginTop: 16,
    fontSize: 16,
    fontWeight: '500',
  },
};

export default ExportModal;
