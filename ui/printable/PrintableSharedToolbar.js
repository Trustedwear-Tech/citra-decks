// PrintableSharedToolbar.js - Shared toolbar for multi-canvas printable editor
// Operates via activeCanvasRef.current?.method() pattern
import React, { memo } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  useWindowDimensions,
} from 'react-native';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';
import ColorPickerDropdown from '../composer/ColorPickerDropdown';
import BackgroundControlDropdown from '../composer/BackgroundControlDropdown';
import Tooltip from '../ui/Tooltip';
import { ShareButton } from '../ShareManager';

// The toolbar chrome is a fixed light surface (see toolbarStyles.toolbar:
// #fff background, #E5E7EB border). The app theme is dark, so taking icon
// colour straight from it painted every glyph #e0e0e0 on white — legible as
// a shape, but reading as "disabled". Contrast against the toolbar's own
// background instead, and let Tooltip pick its light-mode (dark) bubble.
const TOOLBAR_CHROME = {
  text: '#374151',
  isDark: false,
};

const PrintableSharedToolbar = memo(({
  theme: appTheme,
  activeCanvasRef,
  selectionInfo, // { hasSelection, type, fill, stroke, fontSize, lineHeight, fontWeight, fontStyle, textAlign, isText }
  // Action callbacks that go to PrintableComposer (not per-canvas)
  onOpenStylePicker,
  onOpenChartHelp,
  onOpenDiagram,
  onGenerateImage,
  formatPainterActive = false,
  // Header integration props
  printableTitle,
  printableId,
  isOwner = true, // Whether the current user owns this printable (hides share button for shared viewers)
  onSave,
  onExport,
  onPresent,
  onClose,
  onShowAnalytics,
  onOpenFolder,
  onShowCollaboration,
  collaborationStatus,
  collaborators = [],
  userType = 'free',
  onUpgrade,
  onShowQualityModal,
  qualityLabel,
  qualityColor,
  // Background
  pageBackgroundColor = '#ffffff',
  onUpdatePAGEBackground,
  hasBackgroundImage = false,
  backgroundImageOpacity,
  onChangeBackgroundOpacity,
  onRemoveBackgroundImage,
}) => {
  // Keeps every existing `theme.text` reference below correct without
  // touching ~70 call sites; theme.primary and the rest pass through.
  const theme = { ...appTheme, ...TOOLBAR_CHROME };

  const { width: screenWidth } = useWindowDimensions();
  const isMobile = screenWidth < 768;

  const canvas = activeCanvasRef?.current;
  const sel = selectionInfo || { hasSelection: false };
  const fillColor = sel.fill || '#3B82F6';
  const strokeColor = sel.stroke || '#1E40AF';
  const fontSize = sel.fontSize || 16;
  const lineHeight = sel.lineHeight || 1.4;
  const elementOpacity = sel.opacity ?? 1;

  if (isMobile) {
    // Responsive scale: shrink icons/buttons on narrow screens, grow on wider mobile
    const mScale = Math.min(Math.max(screenWidth / 400, 0.7), 1.3);
    const mIcon = Math.round(16 * mScale);
    const mPad = Math.round(5 * mScale);
    const mBtn = { padding: mPad, borderRadius: 5 };
    const mGap = Math.round(2 * mScale);
    const mBoldSize = Math.round(26 * mScale);
    const mFontSize = Math.round(14 * mScale);
    const mSmallFont = Math.round(12 * mScale);
    const mTinyFont = Math.round(11 * mScale);
    return (
      <View style={[toolbarStyles.toolbar, { paddingHorizontal: Math.round(6 * mScale), paddingVertical: Math.round(4 * mScale), gap: 0 }]}>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: mGap, rowGap: Math.round(4 * mScale) }}>
          {/* INSERT */}
          <TouchableOpacity style={mBtn} onPress={() => canvas?.insertElement?.('text')}>
            <Ionicons name="text" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.triggerFileInput?.('image')}>
            <Ionicons name="image-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.openModal?.('video')}>
            <Ionicons name="videocam-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.openModal?.('shapes')}>
            <Ionicons name="shapes-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.openModal?.('icon')}>
            <Ionicons name="happy-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.openModal?.('table')}>
            <Ionicons name="grid-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={onOpenChartHelp}>
            <Ionicons name="bar-chart-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={onOpenDiagram}>
            <Ionicons name="git-network-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => onGenerateImage?.()}>
            <Ionicons name="sparkles-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.triggerFileInput?.('animation')}>
            <Ionicons name="film-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.openModal?.('embed')}>
            <Ionicons name="code-slash-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.openModal?.('forms')}>
            <Ionicons name="document-text-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={onOpenStylePicker}>
            <Ionicons name="color-palette-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.openModal?.('fontCombo')}>
            <Ionicons name="text-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          {/* EDIT / FORMAT */}
          <View style={{ width: '100%', height: 1, backgroundColor: '#E5E7EB', marginVertical: Math.round(2 * mScale) }} />
          <TouchableOpacity onPress={() => activeCanvasRef?.current?.undo?.()} style={mBtn}>
            <Ionicons name="arrow-undo" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => activeCanvasRef?.current?.redo?.()} style={mBtn}>
            <Ionicons name="arrow-redo" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity
            style={[mBtn, formatPainterActive && { backgroundColor: theme.primary + '30' }]}
            onPress={() => formatPainterActive ? canvas?.deactivateFormatPainter?.() : canvas?.activateFormatPainter?.()}
          >
            <Ionicons name="color-fill-outline" size={mIcon} color={formatPainterActive ? theme.primary : theme.text} />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => canvas?.toggleBold?.()} style={{ width: mBoldSize, height: mBoldSize, alignItems: 'center', justifyContent: 'center', borderRadius: 4 }}>
            <Text style={{ fontWeight: 'bold', fontSize: mFontSize, color: theme.text }}>B</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => canvas?.toggleItalic?.()} style={{ width: mBoldSize, height: mBoldSize, alignItems: 'center', justifyContent: 'center', borderRadius: 4 }}>
            <Text style={{ fontStyle: 'italic', fontSize: mFontSize, color: theme.text }}>I</Text>
          </TouchableOpacity>
          <View style={{ zIndex: 1100 }}>
            <ColorPickerDropdown label="Fill" value={fillColor} onChange={(c) => canvas?.updateFillColor?.(c)} themeColors={['#ffffff', '#000000', '#2196F3', '#4CAF50', '#F44336', '#FFC107']} theme={{ ...theme, surface: '#ffffff' }} compact={true} showOpacity={sel.hasSelection} opacity={elementOpacity} onOpacityChange={(v) => canvas?.updateOpacity?.(v)} />
          </View>
          <View style={{ zIndex: 1100 }}>
            <ColorPickerDropdown label="Border" value={strokeColor} onChange={(c) => canvas?.updateStrokeColor?.(c)} themeColors={['#000000', '#ffffff', '#2196F3', '#4CAF50', '#F44336', '#FFC107']} theme={{ ...theme, surface: '#ffffff' }} compact={true} />
          </View>
          <View style={{ zIndex: 1100 }}>
            <BackgroundControlDropdown
              theme={theme}
              slideBackgroundColor={pageBackgroundColor}
              onUpdateSlideBackground={onUpdatePAGEBackground}
              hasBackgroundImage={hasBackgroundImage}
              backgroundImageOpacity={backgroundImageOpacity}
              onChangeBackgroundOpacity={onChangeBackgroundOpacity}
              onRemoveBackgroundImage={onRemoveBackgroundImage}
              compact={true}
            />
          </View>
          <View style={[toolbarStyles.fontSizeContainer, { marginHorizontal: 1 }]}>
            <TouchableOpacity style={[toolbarStyles.fontSizeBtn, { paddingHorizontal: Math.round(4 * mScale), paddingVertical: Math.round(2 * mScale) }]} onPress={() => canvas?.updateFontSize?.(Math.round((fontSize || 20) - 2))}>
              <Text style={{ color: theme.text, fontSize: mSmallFont }}>-</Text>
            </TouchableOpacity>
            <Text style={[toolbarStyles.fontSizeText, { color: theme.text, fontSize: mTinyFont, minWidth: Math.round(22 * mScale) }]}>{Math.round(fontSize || 20)}</Text>
            <TouchableOpacity style={[toolbarStyles.fontSizeBtn, { paddingHorizontal: Math.round(4 * mScale), paddingVertical: Math.round(2 * mScale) }]} onPress={() => canvas?.updateFontSize?.(Math.round((fontSize || 20) + 2))}>
              <Text style={{ color: theme.text, fontSize: mSmallFont }}>+</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity style={{ padding: Math.round(3 * mScale), borderRadius: 4 }} onPress={() => canvas?.setTextAlign?.('left')}>
            <MaterialIcons name="format-align-left" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={{ padding: Math.round(3 * mScale), borderRadius: 4 }} onPress={() => canvas?.setTextAlign?.('center')}>
            <MaterialIcons name="format-align-center" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={{ padding: Math.round(3 * mScale), borderRadius: 4 }} onPress={() => canvas?.setTextAlign?.('right')}>
            <MaterialIcons name="format-align-right" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.bringForward?.()}>
            <Ionicons name="arrow-up-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.sendBackward?.()}>
            <Ionicons name="arrow-down-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={mBtn} onPress={() => canvas?.duplicate?.()}>
            <Ionicons name="copy-outline" size={mIcon} color={theme.text} />
          </TouchableOpacity>
          <TouchableOpacity style={[mBtn, { backgroundColor: '#fee2e2' }]} onPress={() => canvas?.deleteSelected?.()}>
            <Ionicons name="trash-outline" size={mIcon} color="#dc2626" />
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // === DESKTOP TOOLBAR (two rows) ===
  return (
    <View style={[toolbarStyles.toolbar, { zIndex: 100 }]}>
      {/* ROW 1: INSERT + GLOBAL ACTIONS */}
      <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 2, rowGap: 4, zIndex: 2000 }}>
        <Tooltip text="Insert Text" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={() => canvas?.insertElement?.('text')}>
            <Ionicons name="text" size={20} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Insert Image" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={() => canvas?.triggerFileInput?.('image')}>
            <Ionicons name="image-outline" size={20} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        {/* Insert Video / media — HIDDEN for now (kept for future). Flip `false`. */}
        {false && (
        <Tooltip text="Insert Video" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={() => canvas?.openModal?.('video')}>
            <Ionicons name="videocam-outline" size={20} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        )}
        <Tooltip text="Insert Animation (Video to Frames)" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={() => canvas?.triggerFileInput?.('animation')}>
            <Ionicons name="film-outline" size={20} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        {/* Embed App / webpages — HIDDEN for now (kept for future). Flip `false`. */}
        {false && (
        <Tooltip text="Embed App" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={() => canvas?.openModal?.('embed')}>
            <Ionicons name="code-slash-outline" size={20} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        )}
        <Tooltip text="Forms & Buttons" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={() => canvas?.openModal?.('forms')}>
            <Ionicons name="document-text-outline" size={20} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Insert Shape" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={() => canvas?.openModal?.('shapes')}>
            <Ionicons name="shapes-outline" size={20} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Insert Icon" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={() => canvas?.openModal?.('icon')}>
            <Ionicons name="happy-outline" size={20} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Insert Table" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={() => canvas?.openModal?.('table')}>
            <Ionicons name="grid-outline" size={20} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Insert Chart" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={onOpenChartHelp}>
            <Ionicons name="bar-chart-outline" size={20} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Insert Diagram" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={onOpenDiagram}>
            <Ionicons name="git-network-outline" size={20} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="AI Image Generator" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={() => onGenerateImage?.()}>
            <Ionicons name="sparkles-outline" size={20} color={theme.text} />
            <Text style={[toolbarStyles.toolButtonText, { color: theme.text, marginLeft: 4 }]}>AI Image</Text>
          </TouchableOpacity>
        </Tooltip>

        {/* GLOBAL ACTIONS — push to right */}
        <View style={{ flex: 1, minWidth: 8 }} />

        <Tooltip text="Present Slideshow" theme={theme}>
          <TouchableOpacity style={[toolbarStyles.actionBtn, toolbarStyles.primaryBtn]} onPress={onPresent}>
            <Ionicons name="play" size={14} color="#fff" />
            <Text style={[toolbarStyles.actionBtnText, { color: '#fff' }]}>Present</Text>
          </TouchableOpacity>
        </Tooltip>

        <Tooltip text="Save Dashboard" theme={theme}>
          <TouchableOpacity style={toolbarStyles.ghostBtn} onPress={onSave}>
            <Ionicons name="save-outline" size={18} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>

        {/* Generation Quality Badge — HIDDEN for now (image-tier / cost selector
            kept for future). Flip `false` to re-enable. */}
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
        {printableId && isOwner && (
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

        {/* Collaboration Button — HIDDEN for now (real-time co-editing is an
            advanced, not-fully-tested feature kept for future). Flip `false`. */}
        {false && printableId && onShowCollaboration && (
          <Tooltip text={`Collaborate${collaborators.length > 0 ? ` (${collaborators.length} online)` : ''}`} theme={theme}>
            <TouchableOpacity
              style={[
                toolbarStyles.ghostBtn,
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
            <TouchableOpacity style={toolbarStyles.ghostBtn} onPress={onShowAnalytics}>
              <Ionicons name="stats-chart-outline" size={18} color={theme.text} />
            </TouchableOpacity>
          </Tooltip>
        )}

        {/* Open Folder Button */}
        {onOpenFolder && (
          <Tooltip text="View data source folder" theme={theme}>
            <TouchableOpacity style={toolbarStyles.ghostBtn} onPress={onOpenFolder}>
              <Ionicons name="folder-outline" size={18} color={theme.text} />
            </TouchableOpacity>
          </Tooltip>
        )}

        <Tooltip text="Export Dashboard" theme={theme}>
          <TouchableOpacity style={toolbarStyles.ghostBtn} onPress={onExport}>
            <Ionicons name="download-outline" size={18} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>

        <Tooltip text="Close Editor" theme={theme}>
          <TouchableOpacity style={[toolbarStyles.ghostBtn, { backgroundColor: '#FEE2E2', marginLeft: 4 }]} onPress={onClose}>
            <Ionicons name="close-outline" size={18} color="#EF4444" />
          </TouchableOpacity>
        </Tooltip>
      </View>

      {/* ROW 2: EDITING & FORMATTING */}
      <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 2, rowGap: 4, zIndex: 1000, marginTop: 4, paddingTop: 4, borderTopWidth: 1, borderTopColor: '#f0f0f0' }}>
        {/* Undo/Redo */}
        <Tooltip text="Undo" theme={theme}>
          <TouchableOpacity onPress={() => activeCanvasRef?.current?.undo?.()} style={toolbarStyles.arrangeBtn}>
            <Ionicons name="arrow-undo" size={18} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Redo" theme={theme}>
          <TouchableOpacity onPress={() => activeCanvasRef?.current?.redo?.()} style={toolbarStyles.arrangeBtn}>
            <Ionicons name="arrow-redo" size={18} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>

        <View style={toolbarStyles.verticalDivider} />

        {/* Format Painter */}
        <Tooltip
          text={formatPainterActive ? "Click to cancel Format Painter" : "Format Painter (select element first)"}
          theme={theme}
        >
          <TouchableOpacity
            style={[
              toolbarStyles.toolButton,
              formatPainterActive && { backgroundColor: theme.primary + '30', borderRadius: 4 }
            ]}
            onPress={() => {
              if (formatPainterActive) {
                canvas?.deactivateFormatPainter?.();
              } else {
                canvas?.activateFormatPainter?.();
              }
            }}
          >
            <Ionicons name="color-fill-outline" size={20} color={formatPainterActive ? theme.primary : theme.text} />
          </TouchableOpacity>
        </Tooltip>

        <View style={toolbarStyles.verticalDivider} />

        {/* Style & Typography */}
        <Tooltip text="Style Presets" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={onOpenStylePicker}>
            <Ionicons name="color-palette-outline" size={18} color={theme.text} />
            <Text style={[toolbarStyles.toolButtonText, { color: theme.text, marginLeft: 4 }]}>Style</Text>
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Font Combinations" theme={theme}>
          <TouchableOpacity style={toolbarStyles.toolButton} onPress={() => canvas?.openModal?.('fontCombo')}>
            <Ionicons name="text-outline" size={18} color={theme.text} />
            <Text style={[toolbarStyles.toolButtonText, { color: theme.text, marginLeft: 4 }]}>Fonts</Text>
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Bold" theme={theme}>
          <TouchableOpacity onPress={() => canvas?.toggleBold?.()} style={toolbarStyles.formatBtn}>
            <Text style={{ fontWeight: 'bold', fontSize: 16, color: theme.text }}>B</Text>
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Italic" theme={theme}>
          <TouchableOpacity onPress={() => canvas?.toggleItalic?.()} style={toolbarStyles.formatBtn}>
            <Text style={{ fontStyle: 'italic', fontSize: 16, color: theme.text }}>I</Text>
          </TouchableOpacity>
        </Tooltip>
        <View style={{ zIndex: 1100 }}>
          <ColorPickerDropdown
            label="Fill"
            value={fillColor}
            onChange={(c) => canvas?.updateFillColor?.(c)}
            themeColors={['#ffffff', '#000000', '#2196F3', '#4CAF50', '#F44336', '#FFC107']}
            theme={{ ...theme, surface: '#ffffff' }}
            compact={true}
            showOpacity={sel.hasSelection}
            opacity={elementOpacity}
            onOpacityChange={(v) => canvas?.updateOpacity?.(v)}
          />
        </View>
        <View style={{ zIndex: 1100 }}>
          <ColorPickerDropdown
            label="Border"
            value={strokeColor}
            onChange={(c) => canvas?.updateStrokeColor?.(c)}
            themeColors={['#000000', '#ffffff', '#2196F3', '#4CAF50', '#F44336', '#FFC107']}
            theme={{ ...theme, surface: '#ffffff' }}
            compact={true}
          />
        </View>
        <View style={{ zIndex: 1100 }}>
          <BackgroundControlDropdown
            theme={theme}
            slideBackgroundColor={pageBackgroundColor}
            onUpdateSlideBackground={onUpdatePAGEBackground}
            hasBackgroundImage={hasBackgroundImage}
            backgroundImageOpacity={backgroundImageOpacity}
            onChangeBackgroundOpacity={onChangeBackgroundOpacity}
            onRemoveBackgroundImage={onRemoveBackgroundImage}
            compact={true}
          />
        </View>
        <View style={[toolbarStyles.fontSizeContainer, { marginHorizontal: 2 }]}>
          <TouchableOpacity style={toolbarStyles.fontSizeBtn} onPress={() => canvas?.updateFontSize?.(Math.round((fontSize || 20) - 2))}>
            <Text style={{ color: theme.text }}>-</Text>
          </TouchableOpacity>
          <Text style={[toolbarStyles.fontSizeText, { color: theme.text }]}>{Math.round(fontSize || 20)}</Text>
          <TouchableOpacity style={toolbarStyles.fontSizeBtn} onPress={() => canvas?.updateFontSize?.(Math.round((fontSize || 20) + 2))}>
            <Text style={{ color: theme.text }}>+</Text>
          </TouchableOpacity>
        </View>
        <View style={[toolbarStyles.fontSizeContainer, { marginHorizontal: 2 }]}>
          <Tooltip text="Decrease Line Height" theme={theme}>
            <TouchableOpacity style={toolbarStyles.fontSizeBtn} onPress={() => canvas?.updateLineHeight?.((lineHeight || 1.4) - 0.1)}>
              <MaterialIcons name="format-line-spacing" size={14} color={theme.text} style={{ transform: [{ scaleY: 0.8 }] }} />
              <Text style={{ color: theme.text, fontSize: 10, marginLeft: 2 }}>-</Text>
            </TouchableOpacity>
          </Tooltip>
          <Text style={[toolbarStyles.fontSizeText, { color: theme.text, minWidth: 24, fontSize: 11 }]}>{(lineHeight || 1.4).toFixed(1)}</Text>
          <Tooltip text="Increase Line Height" theme={theme}>
            <TouchableOpacity style={toolbarStyles.fontSizeBtn} onPress={() => canvas?.updateLineHeight?.((lineHeight || 1.4) + 0.1)}>
              <Text style={{ color: theme.text, fontSize: 10, marginRight: 2 }}>+</Text>
              <MaterialIcons name="format-line-spacing" size={14} color={theme.text} style={{ transform: [{ scaleY: 1.2 }] }} />
            </TouchableOpacity>
          </Tooltip>
        </View>
        <TouchableOpacity style={toolbarStyles.alignBtn} onPress={() => canvas?.setTextAlign?.('left')}>
          <MaterialIcons name="format-align-left" size={20} color={theme.text} />
        </TouchableOpacity>
        <TouchableOpacity style={toolbarStyles.alignBtn} onPress={() => canvas?.setTextAlign?.('center')}>
          <MaterialIcons name="format-align-center" size={20} color={theme.text} />
        </TouchableOpacity>
        <TouchableOpacity style={toolbarStyles.alignBtn} onPress={() => canvas?.setTextAlign?.('right')}>
          <MaterialIcons name="format-align-right" size={20} color={theme.text} />
        </TouchableOpacity>

        <View style={toolbarStyles.verticalDivider} />

        {/* Arrange */}
        <Tooltip text="Bring Forward" theme={theme}>
          <TouchableOpacity style={toolbarStyles.arrangeBtn} onPress={() => canvas?.bringForward?.()}>
            <Ionicons name="arrow-up-outline" size={18} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Send Backward" theme={theme}>
          <TouchableOpacity style={toolbarStyles.arrangeBtn} onPress={() => canvas?.sendBackward?.()}>
            <Ionicons name="arrow-down-outline" size={18} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Duplicate" theme={theme}>
          <TouchableOpacity style={toolbarStyles.arrangeBtn} onPress={() => canvas?.duplicate?.()}>
            <Ionicons name="copy-outline" size={18} color={theme.text} />
          </TouchableOpacity>
        </Tooltip>
        <Tooltip text="Delete" theme={theme}>
          <TouchableOpacity style={[toolbarStyles.arrangeBtn, { backgroundColor: '#fee2e2' }]} onPress={() => canvas?.deleteSelected?.()}>
            <Ionicons name="trash-outline" size={18} color="#dc2626" />
          </TouchableOpacity>
        </Tooltip>
      </View>
    </View>
  );
});

const toolbarStyles = {
  toolbar: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
    backgroundColor: '#fff',
    gap: 8,
    zIndex: 100,
  },
  toolButton: {
    padding: 6,
    borderRadius: 6,
    flexDirection: 'row',
    alignItems: 'center',
  },
  toolButtonText: {
    fontSize: 12,
    fontWeight: '500',
  },
  formatBtn: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 4,
  },
  arrangeBtn: {
    padding: 6,
    borderRadius: 6,
  },
  alignBtn: {
    padding: 4,
    borderRadius: 4,
  },
  verticalDivider: {
    width: 1,
    height: 24,
    backgroundColor: '#d1d5db',
    marginHorizontal: 6,
  },
  fontSizeContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 6,
    overflow: 'hidden',
  },
  fontSizeBtn: {
    paddingHorizontal: 6,
    paddingVertical: 4,
    flexDirection: 'row',
    alignItems: 'center',
  },
  fontSizeText: {
    fontSize: 13,
    fontWeight: '500',
    minWidth: 28,
    textAlign: 'center',
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 6,
    gap: 6,
  },
  actionBtnText: {
    fontSize: 13,
    fontWeight: '600',
  },
  primaryBtn: {
    backgroundColor: '#2563EB',
    shadowColor: '#2563EB',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
  },
  ghostBtn: {
    padding: 8,
    borderRadius: 6,
  },
};

export default PrintableSharedToolbar;
