// TablePickerModal.js - Visual grid picker for table dimensions
import React, { useState, useCallback } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    StyleSheet,
    Switch,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';

const MAX_ROWS = 8;
const MAX_COLS = 8;
const CELL_SIZE = 24;

/**
 * TablePickerModal - PowerPoint-style table dimension picker
 * 
 * Props:
 * - visible: boolean
 * - onClose: () => void
 * - onInsert: (rows, cols, includeHeader, themeColors) => void
 * - theme: presentation theme for colors
 * - presentationStyle: for deriving table colors
 */
const TablePickerModal = ({
    visible,
    onClose,
    onInsert,
    theme = {},
    presentationStyle = {},
}) => {
    const [hoverRow, setHoverRow] = useState(0);
    const [hoverCol, setHoverCol] = useState(0);
    const [selectionLocked, setSelectionLocked] = useState(false);
    const [includeHeader, setIncludeHeader] = useState(true);

    // Derive table theme colors from presentation style
    const getTableThemeColors = useCallback(() => ({
        headerColor: presentationStyle?.accentColor || presentationStyle?.preview?.primary || '#3B82F6',
        headerTextColor: '#FFFFFF',
        cellColor: '#FFFFFF',
        altRowColor: presentationStyle?.cardBackground || '#F8FAFC',
        borderColor: presentationStyle?.cardBorder || '#E5E7EB',
        textColor: presentationStyle?.textPrimary || '#374151',
    }), [presentationStyle]);

    const handleCellHover = useCallback((row, col) => {
        // Only update hover if selection is not locked
        if (!selectionLocked) {
            setHoverRow(row);
            setHoverCol(col);
        }
    }, [selectionLocked]);

    // Accept optional row/col for direct cell click (avoids stale state)
    const handleInsert = useCallback((directRow = null, directCol = null) => {
        const rows = directRow ?? hoverRow;
        const cols = directCol ?? hoverCol;

        console.log(`📊 [TABLE_PICKER] handleInsert called: rows=${rows}, cols=${cols}, directRow=${directRow}, directCol=${directCol}`);

        if (rows > 0 && cols > 0) {
            const themeColors = getTableThemeColors();
            console.log(`📊 [TABLE_PICKER] Calling onInsert with: ${cols}×${rows} table`);
            onInsert(rows, cols, includeHeader, themeColors);
            // Reset state AFTER calling onInsert
            setHoverRow(0);
            setHoverCol(0);
            setSelectionLocked(false);
            onClose();
        }
    }, [hoverRow, hoverCol, includeHeader, getTableThemeColors, onInsert, onClose]);

    const handleClose = useCallback(() => {
        setHoverRow(0);
        setHoverCol(0);
        setSelectionLocked(false);
        onClose();
    }, [onClose]);

    const renderGrid = () => {
        const rows = [];
        for (let r = 1; r <= MAX_ROWS; r++) {
            const cells = [];
            for (let c = 1; c <= MAX_COLS; c++) {
                const isHighlighted = r <= hoverRow && c <= hoverCol;
                cells.push(
                    <TouchableOpacity
                        key={`${r}-${c}`}
                        style={[
                            styles.gridCell,
                            isHighlighted && styles.gridCellHighlighted,
                        ]}
                        onPress={() => {
                            // Just set selection - don't auto-insert
                            // User must click "Insert" button to confirm
                            console.log(`📊 [TABLE_PICKER] Cell clicked: ${c}×${r} - setting selection`);
                            setHoverRow(r);
                            setHoverCol(c);
                            setSelectionLocked(true); // Lock selection so hovering doesn't change it
                        }}
                        onMouseEnter={() => handleCellHover(r, c)}
                        activeOpacity={0.7}
                    />
                );
            }
            rows.push(
                <View key={r} style={styles.gridRow}>
                    {cells}
                </View>
            );
        }
        return rows;
    };

    const themeColors = getTableThemeColors();

    return (
        <Modal
            visible={visible}
            transparent
            animationType="fade"
            onRequestClose={handleClose}
        >
            <TouchableOpacity
                style={styles.overlay}
                activeOpacity={1}
                onPress={handleClose}
            >
                <TouchableOpacity
                    activeOpacity={1}
                    onPress={(e) => e.stopPropagation()}
                >
                    <View style={[styles.container, { backgroundColor: theme.surface || '#FFFFFF' }]}>
                        {/* Header */}
                        <View style={styles.header}>
                            <Text style={[styles.title, { color: theme.text || '#111827' }]}>
                                Insert Table
                            </Text>
                            <TouchableOpacity onPress={handleClose} style={styles.closeBtn}>
                                <MaterialIcons name="close" size={20} color={theme.textSecondary || '#6B7280'} />
                            </TouchableOpacity>
                        </View>

                        {/* Grid */}
                        <View
                            style={styles.gridContainer}
                            onMouseLeave={() => {
                                if (hoverRow === 0 && hoverCol === 0) return;
                                // Keep selection on mouse leave
                            }}
                        >
                            {renderGrid()}
                        </View>

                        {/* Dimension Label */}
                        <Text style={[styles.dimensionLabel, { color: theme.text || '#111827' }]}>
                            {hoverRow > 0 && hoverCol > 0
                                ? `${hoverCol} × ${hoverRow} Table`
                                : 'Hover to select size'}
                        </Text>

                        {/* Preview */}
                        {hoverRow > 0 && hoverCol > 0 && (
                            <View style={styles.previewContainer}>
                                <View style={[styles.previewTable, { borderColor: themeColors.borderColor }]}>
                                    {/* Show mini preview of 2-3 rows */}
                                    {[0, 1, 2].slice(0, Math.min(hoverRow, 3)).map((r) => (
                                        <View key={r} style={styles.previewRow}>
                                            {[0, 1, 2].slice(0, Math.min(hoverCol, 3)).map((c) => (
                                                <View
                                                    key={c}
                                                    style={[
                                                        styles.previewCell,
                                                        {
                                                            backgroundColor: r === 0 && includeHeader
                                                                ? themeColors.headerColor
                                                                : r % 2 === 0
                                                                    ? themeColors.altRowColor
                                                                    : themeColors.cellColor,
                                                            borderColor: themeColors.borderColor,
                                                        },
                                                    ]}
                                                />
                                            ))}
                                            {hoverCol > 3 && (
                                                <Text style={styles.previewEllipsis}>...</Text>
                                            )}
                                        </View>
                                    ))}
                                    {hoverRow > 3 && (
                                        <Text style={[styles.previewEllipsis, { textAlign: 'center' }]}>...</Text>
                                    )}
                                </View>
                            </View>
                        )}

                        {/* Options */}
                        <View style={styles.optionsRow}>
                            <Text style={[styles.optionLabel, { color: theme.text || '#111827' }]}>
                                Include header row
                            </Text>
                            <Switch
                                value={includeHeader}
                                onValueChange={setIncludeHeader}
                                trackColor={{ false: '#D1D5DB', true: themeColors.headerColor }}
                                thumbColor="#FFFFFF"
                            />
                        </View>

                        {/* Actions */}
                        <View style={styles.actions}>
                            <TouchableOpacity
                                style={[styles.cancelBtn, { borderColor: theme.border || '#E5E7EB' }]}
                                onPress={handleClose}
                            >
                                <Text style={[styles.cancelBtnText, { color: theme.text || '#374151' }]}>
                                    Cancel
                                </Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={[
                                    styles.insertBtn,
                                    { backgroundColor: themeColors.headerColor },
                                    (hoverRow === 0 || hoverCol === 0) && styles.insertBtnDisabled,
                                ]}
                                onPress={() => {
                                    console.log(`📊 [TABLE_PICKER] Insert button clicked: ${hoverCol}×${hoverRow}`);
                                    handleInsert();
                                }}
                                disabled={hoverRow === 0 || hoverCol === 0}
                            >
                                <Text style={styles.insertBtnText}>Insert</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
                </TouchableOpacity>
            </TouchableOpacity>
        </Modal>
    );
};

const styles = StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        justifyContent: 'center',
        alignItems: 'center',
    },
    container: {
        borderRadius: 12,
        padding: 20,
        minWidth: 280,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.15,
        shadowRadius: 12,
        elevation: 8,
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 16,
    },
    title: {
        fontSize: 16,
        fontWeight: '600',
    },
    closeBtn: {
        padding: 4,
    },
    gridContainer: {
        alignSelf: 'center',
        padding: 4,
        backgroundColor: '#F9FAFB',
        borderRadius: 8,
    },
    gridRow: {
        flexDirection: 'row',
    },
    gridCell: {
        width: CELL_SIZE,
        height: CELL_SIZE,
        borderWidth: 1,
        borderColor: '#D1D5DB',
        margin: 1,
        borderRadius: 2,
        backgroundColor: '#FFFFFF',
    },
    gridCellHighlighted: {
        backgroundColor: '#DBEAFE',
        borderColor: '#3B82F6',
    },
    dimensionLabel: {
        textAlign: 'center',
        marginTop: 12,
        fontSize: 14,
        fontWeight: '500',
    },
    previewContainer: {
        marginTop: 12,
        alignItems: 'center',
    },
    previewTable: {
        borderWidth: 1,
        borderRadius: 4,
        overflow: 'hidden',
    },
    previewRow: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    previewCell: {
        width: 32,
        height: 16,
        borderWidth: 0.5,
    },
    previewEllipsis: {
        fontSize: 10,
        color: '#9CA3AF',
        marginLeft: 4,
    },
    optionsRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginTop: 16,
        paddingTop: 12,
        borderTopWidth: 1,
        borderTopColor: '#E5E7EB',
    },
    optionLabel: {
        fontSize: 14,
    },
    actions: {
        flexDirection: 'row',
        justifyContent: 'flex-end',
        gap: 8,
        marginTop: 16,
    },
    cancelBtn: {
        paddingVertical: 8,
        paddingHorizontal: 16,
        borderRadius: 6,
        borderWidth: 1,
    },
    cancelBtnText: {
        fontSize: 14,
        fontWeight: '500',
    },
    insertBtn: {
        paddingVertical: 8,
        paddingHorizontal: 16,
        borderRadius: 6,
    },
    insertBtnDisabled: {
        opacity: 0.5,
    },
    insertBtnText: {
        fontSize: 14,
        fontWeight: '500',
        color: '#FFFFFF',
    },
});

export default TablePickerModal;
