// FloatingTextToolbar.js - PowerPoint-style floating toolbar for inline text formatting
// Appears near selected text in Fabric.js canvas editors (Presentation & Printable)
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform, ScrollView } from 'react-native';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';
import ColorPickerDropdown from './ColorPickerDropdown';

// ═══════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════

// Curated list of popular web-safe + Google Fonts for quick inline selection
const INLINE_FONT_LIST = [
  'Inter',
  'Roboto',
  'Open Sans',
  'Lato',
  'Montserrat',
  'Poppins',
  'Raleway',
  'Nunito',
  'Playfair Display',
  'Merriweather',
  'Source Sans Pro',
  'DM Sans',
  'Work Sans',
  'Oswald',
  'Lora',
  'PT Sans',
  'Roboto Slab',
  'Libre Baskerville',
  'Quicksand',
  'Archivo',
  'Arial',
  'Georgia',
  'Times New Roman',
  'Verdana',
  'Courier New',
];

// ═══════════════════════════════════════════════════════════════════
// FONT FAMILY DROPDOWN (inline)
// ═══════════════════════════════════════════════════════════════════
const FontFamilyDropdown = ({ value, onChange, theme }) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    if (isOpen) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const displayName = value || 'Inter';
  // Truncate long font names
  const truncated = displayName.length > 12 ? displayName.substring(0, 11) + '…' : displayName;

  return (
    <View ref={dropdownRef} style={ffdStyles.container}>
      <TouchableOpacity
        style={[ffdStyles.trigger, { borderColor: theme.border || '#d0d0d0' }]}
        onPress={() => setIsOpen(!isOpen)}
      >
        <Text style={[ffdStyles.triggerText, { color: theme.text || '#333', fontFamily: value || 'Inter' }]} numberOfLines={1}>
          {truncated}
        </Text>
        <Ionicons name="chevron-down" size={10} color={theme.textSecondary || '#999'} />
      </TouchableOpacity>

      {isOpen && (
        <View style={[ffdStyles.dropdown, { backgroundColor: theme.surface || '#fff', borderColor: theme.border || '#e0e0e0' }]}>
          <ScrollView style={ffdStyles.scrollList} nestedScrollEnabled>
            {INLINE_FONT_LIST.map((font) => (
              <TouchableOpacity
                key={font}
                style={[
                  ffdStyles.fontItem,
                  value === font && { backgroundColor: (theme.primary || '#4472C4') + '18' },
                ]}
                onPress={() => { onChange(font); setIsOpen(false); }}
              >
                <Text style={[ffdStyles.fontItemText, { fontFamily: font, color: theme.text || '#333' }]}>
                  {font}
                </Text>
                {value === font && (
                  <Ionicons name="checkmark" size={14} color={theme.primary || '#4472C4'} />
                )}
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      )}
    </View>
  );
};

const ffdStyles = StyleSheet.create({
  container: { position: 'relative', zIndex: 1200 },
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderWidth: 1,
    borderRadius: 4,
    minWidth: 90,
    maxWidth: 120,
    gap: 4,
  },
  triggerText: { fontSize: 12, flex: 1 },
  dropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    marginTop: 4,
    borderRadius: 8,
    borderWidth: 1,
    minWidth: 180,
    maxHeight: 260,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.18,
    shadowRadius: 12,
    elevation: 10,
    zIndex: 1300,
    overflow: 'hidden',
  },
  scrollList: { maxHeight: 250, paddingVertical: 4 },
  fontItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  fontItemText: { fontSize: 14 },
});

// ═══════════════════════════════════════════════════════════════════
// FLOATING TEXT TOOLBAR (main export)
// ═══════════════════════════════════════════════════════════════════

/**
 * PowerPoint-style floating toolbar that appears above selected text.
 *
 * Props:
 *   visible       - boolean, show/hide the toolbar
 *   position      - { x, y } absolute position in the canvas container
 *   currentStyles - { fontWeight, fontStyle, underline, fill, textBackgroundColor, fontFamily, fontSize }
 *   onToggleBold  - () => void
 *   onToggleItalic - () => void
 *   onToggleUnderline - () => void
 *   onChangeColor  - (hex) => void
 *   onChangeHighlight - (hex) => void
 *   onChangeFontFamily - (family) => void
 *   onChangeFontSize - (size) => void
 *   theme          - { surface, text, textSecondary, border, primary }
 *   containerRef   - ref to the canvas container for boundary detection
 */
const FloatingTextToolbar = ({
  visible = false,
  position = { x: 0, y: 0 },
  currentStyles = {},
  onToggleBold,
  onToggleItalic,
  onToggleUnderline,
  onChangeColor,
  onChangeHighlight,
  onChangeFontFamily,
  onChangeFontSize,
  theme = {},
  containerRef,
}) => {
  const toolbarRef = useRef(null);
  const [adjustedPos, setAdjustedPos] = useState(position);

  // Adjust position to stay within container bounds
  useEffect(() => {
    if (!visible || Platform.OS !== 'web') {
      setAdjustedPos(position);
      return;
    }

    // Use requestAnimationFrame to let the toolbar render first so we can measure it
    requestAnimationFrame(() => {
      const toolbar = toolbarRef.current;
      if (!toolbar) {
        setAdjustedPos(position);
        return;
      }

      const toolbarRect = toolbar.getBoundingClientRect ? toolbar.getBoundingClientRect() : null;
      const toolbarWidth = toolbarRect?.width || 380;
      const toolbarHeight = toolbarRect?.height || 40;

      let newX = position.x - toolbarWidth / 2; // Center above selection
      let newY = position.y - toolbarHeight - 10; // 10px gap above selection

      // Get container bounds
      const container = containerRef?.current;
      if (container) {
        const containerRect = container.getBoundingClientRect();
        // Clamp X
        if (newX < 0) newX = 4;
        if (newX + toolbarWidth > containerRect.width) newX = containerRect.width - toolbarWidth - 4;
        // Flip below if too close to top
        if (newY < 0) newY = position.y + 24;
      } else {
        if (newX < 0) newX = 4;
        if (newY < 0) newY = position.y + 24;
      }

      setAdjustedPos({ x: newX, y: newY });
    });
  }, [visible, position.x, position.y]);

  if (!visible || Platform.OS !== 'web') return null;

  const isBold = currentStyles.fontWeight === 'bold' || currentStyles.fontWeight >= 700;
  const isItalic = currentStyles.fontStyle === 'italic';
  const isUnderline = !!currentStyles.underline;
  const currentColor = currentStyles.fill || '#000000';
  const currentHighlight = currentStyles.textBackgroundColor || 'transparent';
  const currentFontFamily = currentStyles.fontFamily || 'Inter';
  const currentFontSize = currentStyles.fontSize || 16;

  const surface = theme.surface || '#ffffff';
  const textColor = theme.text || '#333333';
  const primary = theme.primary || '#4472C4';
  const border = theme.border || '#e0e0e0';

  return (
    <View
      ref={toolbarRef}
      style={[
        styles.toolbar,
        {
          left: adjustedPos.x,
          top: adjustedPos.y,
          backgroundColor: surface,
          borderColor: border,
        },
      ]}
      // Prevent canvas deselection when interacting with toolbar
      onStartShouldSetResponder={() => true}
      pointerEvents="box-none"
    >
      {/* Font Family */}
      <FontFamilyDropdown
        value={currentFontFamily}
        onChange={onChangeFontFamily}
        theme={theme}
      />

      {/* Font Size Stepper */}
      <View style={[styles.fontSizeGroup, { borderColor: border }]}>
        <TouchableOpacity
          style={styles.fontSizeBtn}
          onPress={() => onChangeFontSize && onChangeFontSize(Math.max(8, currentFontSize - 1))}
        >
          <Text style={{ color: textColor, fontSize: 13, fontWeight: '600' }}>−</Text>
        </TouchableOpacity>
        <Text style={[styles.fontSizeValue, { color: textColor }]}>{Math.round(currentFontSize)}</Text>
        <TouchableOpacity
          style={styles.fontSizeBtn}
          onPress={() => onChangeFontSize && onChangeFontSize(Math.min(200, currentFontSize + 1))}
        >
          <Text style={{ color: textColor, fontSize: 13, fontWeight: '600' }}>+</Text>
        </TouchableOpacity>
      </View>

      <View style={[styles.divider, { backgroundColor: border }]} />

      {/* B / I / U toggles */}
      <TouchableOpacity
        style={[styles.formatBtn, isBold && { backgroundColor: primary + '20' }]}
        onPress={onToggleBold}
      >
        <Text style={{ fontWeight: 'bold', fontSize: 14, color: isBold ? primary : textColor }}>B</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.formatBtn, isItalic && { backgroundColor: primary + '20' }]}
        onPress={onToggleItalic}
      >
        <Text style={{ fontStyle: 'italic', fontSize: 14, color: isItalic ? primary : textColor }}>I</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.formatBtn, isUnderline && { backgroundColor: primary + '20' }]}
        onPress={onToggleUnderline}
      >
        <Text style={{ textDecorationLine: 'underline', fontSize: 14, color: isUnderline ? primary : textColor }}>U</Text>
      </TouchableOpacity>

      <View style={[styles.divider, { backgroundColor: border }]} />

      {/* Text Color */}
      <View style={{ zIndex: 1100 }}>
        <ColorPickerDropdown
          label=""
          value={currentColor}
          onChange={(c) => onChangeColor && onChangeColor(c)}
          themeColors={['#000000', '#ffffff', '#2196F3', '#4CAF50', '#F44336', '#FFC107']}
          theme={{ ...theme, surface: '#ffffff' }}
          compact={true}
        />
      </View>

      {/* Highlight Color */}
      <View style={{ zIndex: 1100 }}>
        <TouchableOpacity
          style={[styles.highlightBtn, { borderColor: border }]}
          onPress={() => {
            // Toggle highlight: if already highlighted, clear it; otherwise apply yellow
            if (currentHighlight && currentHighlight !== 'transparent') {
              onChangeHighlight && onChangeHighlight('');
            } else {
              onChangeHighlight && onChangeHighlight('#FFFF00');
            }
          }}
        >
          <MaterialIcons name="highlight" size={16} color={currentHighlight && currentHighlight !== 'transparent' ? currentHighlight : textColor} />
          <View style={[styles.highlightIndicator, {
            backgroundColor: currentHighlight && currentHighlight !== 'transparent' ? currentHighlight : 'transparent',
            borderColor: border,
          }]} />
        </TouchableOpacity>
      </View>
    </View>
  );
};

// ═══════════════════════════════════════════════════════════════════
// STYLES
// ═══════════════════════════════════════════════════════════════════

const styles = StyleSheet.create({
  toolbar: {
    position: 'absolute',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 6,
    paddingVertical: 4,
    borderRadius: 8,
    borderWidth: 1,
    gap: 4,
    zIndex: 2000,
    // Shadow
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 8,
    // Prevent text selection on toolbar
    ...(Platform.OS === 'web' ? { userSelect: 'none' } : {}),
  },
  divider: {
    width: 1,
    height: 20,
    marginHorizontal: 2,
  },
  formatBtn: {
    width: 28,
    height: 28,
    borderRadius: 4,
    alignItems: 'center',
    justifyContent: 'center',
  },
  fontSizeGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: 4,
    overflow: 'hidden',
  },
  fontSizeBtn: {
    paddingHorizontal: 6,
    paddingVertical: 3,
    alignItems: 'center',
    justifyContent: 'center',
  },
  fontSizeValue: {
    fontSize: 12,
    fontWeight: '500',
    minWidth: 28,
    textAlign: 'center',
    paddingHorizontal: 2,
  },
  highlightBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 4,
    paddingVertical: 3,
    borderRadius: 4,
    gap: 2,
  },
  highlightIndicator: {
    width: 14,
    height: 4,
    borderRadius: 1,
    borderWidth: 0.5,
    marginTop: 1,
  },
});

export default FloatingTextToolbar;
