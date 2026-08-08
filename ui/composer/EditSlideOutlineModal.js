/**
 * EditSlideOutlineModal Component
 * 
 * A simple dialog for editing a single slide/page's topic (title) and outline.
 * Used by the edit (pencil) button on the left panel card in all three composers:
 * PresentationComposer, PrintableComposer, ReportComposer.
 */

import React, { useState, useEffect } from 'react';
import { View, Text, TextInput, Modal, StyleSheet, TouchableOpacity, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const EditSlideOutlineModal = ({
    visible,
    onClose,
    onSave,
    theme,
    itemLabel = "Slide",  // "Slide" | "Page"
    initialTitle = '',
    initialOutline = '',
}) => {
    const [title, setTitle] = useState('');
    const [outline, setOutline] = useState('');

    useEffect(() => {
        if (visible) {
            setTitle(initialTitle);
            setOutline(initialOutline);
        }
    }, [visible, initialTitle, initialOutline]);

    const handleSave = () => {
        onSave({
            title: title.trim() || `Untitled ${itemLabel}`,
            outline: outline.trim(),
        });
        onClose();
    };

    if (!visible) return null;

    const styles = getStyles(theme || {});
    const primaryColor = theme?.primary || '#2563EB';

    return (
        <Modal
            visible={visible}
            transparent={true}
            animationType="fade"
            onRequestClose={onClose}
        >
            <View style={styles.overlay}>
                <View style={styles.modalContainer}>
                    {/* Header */}
                    <View style={styles.header}>
                        <View style={styles.titleRow}>
                            <Ionicons name="create-outline" size={22} color={primaryColor} />
                            <Text style={styles.title}>Edit {itemLabel}</Text>
                        </View>
                        <TouchableOpacity onPress={onClose} style={styles.closeButton}>
                            <Ionicons name="close" size={22} color={theme?.text || '#333'} />
                        </TouchableOpacity>
                    </View>

                    {/* Title Field */}
                    <View style={styles.fieldContainer}>
                        <Text style={styles.fieldLabel}>Topic / Title</Text>
                        <TextInput
                            style={styles.titleInput}
                            value={title}
                            onChangeText={setTitle}
                            placeholder={`Enter ${itemLabel.toLowerCase()} title...`}
                            placeholderTextColor={theme?.textSecondary || '#999'}
                            autoFocus
                        />
                    </View>

                    {/* Outline Field */}
                    <View style={styles.fieldContainer}>
                        <Text style={styles.fieldLabel}>Outline / Description</Text>
                        <TextInput
                            style={styles.outlineInput}
                            value={outline}
                            onChangeText={setOutline}
                            placeholder={`Describe what this ${itemLabel.toLowerCase()} should cover...`}
                            placeholderTextColor={theme?.textSecondary || '#999'}
                            multiline
                            textAlignVertical="top"
                        />
                    </View>

                    {/* Actions */}
                    <View style={styles.actions}>
                        <TouchableOpacity onPress={onClose} style={styles.cancelButton}>
                            <Text style={styles.cancelButtonText}>Cancel</Text>
                        </TouchableOpacity>
                        <TouchableOpacity onPress={handleSave} style={[styles.saveButton, { backgroundColor: primaryColor }]}>
                            <Ionicons name="checkmark" size={16} color="#fff" />
                            <Text style={styles.saveButtonText}>Save</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            </View>
        </Modal>
    );
};

const getStyles = (theme) => StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        justifyContent: 'center',
        alignItems: 'center',
    },
    modalContainer: {
        width: Platform.OS === 'web' ? 480 : '90%',
        maxWidth: 520,
        backgroundColor: theme?.cardBackground || theme?.background || '#fff',
        borderRadius: 16,
        padding: 24,
        ...(Platform.OS === 'web' ? {
            boxShadow: '0 20px 60px rgba(0, 0, 0, 0.3)',
        } : {
            shadowColor: '#000',
            shadowOffset: { width: 0, height: 8 },
            shadowOpacity: 0.3,
            shadowRadius: 24,
            elevation: 12,
        }),
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 20,
    },
    titleRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
    },
    title: {
        fontSize: 18,
        fontWeight: '700',
        color: theme?.text || '#1a1a1a',
    },
    closeButton: {
        padding: 4,
        borderRadius: 8,
    },
    fieldContainer: {
        marginBottom: 16,
    },
    fieldLabel: {
        fontSize: 13,
        fontWeight: '600',
        color: theme?.textSecondary || '#666',
        marginBottom: 6,
    },
    titleInput: {
        fontSize: 15,
        color: theme?.text || '#1a1a1a',
        backgroundColor: theme?.inputBackground || theme?.background || '#f8f9fa',
        borderWidth: 1,
        borderColor: theme?.borderColor || '#e0e0e0',
        borderRadius: 10,
        paddingHorizontal: 14,
        paddingVertical: 10,
        ...(Platform.OS === 'web' ? { outlineStyle: 'none' } : {}),
    },
    outlineInput: {
        fontSize: 14,
        color: theme?.text || '#1a1a1a',
        backgroundColor: theme?.inputBackground || theme?.background || '#f8f9fa',
        borderWidth: 1,
        borderColor: theme?.borderColor || '#e0e0e0',
        borderRadius: 10,
        paddingHorizontal: 14,
        paddingVertical: 10,
        minHeight: 100,
        maxHeight: 200,
        ...(Platform.OS === 'web' ? { outlineStyle: 'none' } : {}),
    },
    actions: {
        flexDirection: 'row',
        justifyContent: 'flex-end',
        alignItems: 'center',
        gap: 10,
        marginTop: 8,
    },
    cancelButton: {
        paddingHorizontal: 18,
        paddingVertical: 10,
        borderRadius: 10,
        borderWidth: 1,
        borderColor: theme?.borderColor || '#e0e0e0',
    },
    cancelButtonText: {
        fontSize: 14,
        fontWeight: '600',
        color: theme?.textSecondary || '#666',
    },
    saveButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingHorizontal: 20,
        paddingVertical: 10,
        borderRadius: 10,
    },
    saveButtonText: {
        fontSize: 14,
        fontWeight: '600',
        color: '#fff',
    },
});

export default EditSlideOutlineModal;
