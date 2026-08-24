// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

/**
 * UpdateInstructionModal Component
 * 
 * A multi-step modal for "Update ALL" operations.
 * Step 1: Review/edit topic(goal) and outline with full control — add, delete, reorder, edit, and AI refresh
 * Step 2: Add instructions and confirm
 * 
 * Mirrors the outline editing power of PresentationGoalInput / PrintableGoalInput.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TextInput, Modal, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView, Platform, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const UpdateInstructionModal = ({
    visible,
    onClose,
    onConfirm,
    isUpdating,
    theme,
    title = "Update All Pages",
    itemLabel = "Item",  // "Slide" | "Page" | "Section" — context-aware label
    // Props for goal/outline editing
    currentGoal = '',
    currentOutline = [], // Array of { slideIndex, title, outline }
    onRefreshOutline, // async (goal, outline) => { topic, outline } | outline[]
    isRefreshingOutline = false,
}) => {
    const defaultInstruction = "Update with the latest data from my data store.";
    const [instruction, setInstruction] = useState(defaultInstruction);
    const [step, setStep] = useState(1); // 1 = goal/outline, 2 = instruction/confirm
    const [editedGoal, setEditedGoal] = useState('');
    const [editedOutline, setEditedOutline] = useState([]); // [{ slideIndex, title, outline }]

    // Inline editing state (one item at a time)
    const [editingIndex, setEditingIndex] = useState(null);
    const [editingTitle, setEditingTitle] = useState('');
    const [editingOutline, setEditingOutline] = useState('');

    // Track whether outline was regenerated via AI (triggers template re-matching)
    const [outlineRefreshed, setOutlineRefreshed] = useState(false);

    // Reset state when modal opens
    useEffect(() => {
        if (visible) {
            setStep(1);
            setInstruction(defaultInstruction);
            setEditedGoal(typeof currentGoal === 'object' ? (currentGoal?.purpose || '') : (currentGoal || ''));
            setEditedOutline(
                currentOutline.map(item => ({ ...item }))
            );
            setEditingIndex(null);
            setOutlineRefreshed(false);
        }
    }, [visible, currentGoal, currentOutline]);

    const handleConfirm = () => {
        // Save any in-progress editing before confirming
        if (editingIndex !== null) saveEditing();
        onConfirm({
            instruction,
            updatedGoal: editedGoal,
            updatedOutline: editedOutline,
            outlineChanged: outlineRefreshed,
        });
    };

    const handleRefreshOutline = async () => {
        if (onRefreshOutline) {
            // Save any in-progress editing first
            if (editingIndex !== null) saveEditing();
            const result = await onRefreshOutline(editedGoal, editedOutline);
            if (result) {
                // Support both { topic, outline } and plain outline[]
                if (Array.isArray(result)) {
                    setEditedOutline(result);
                    setOutlineRefreshed(true);
                } else if (result.outline && Array.isArray(result.outline)) {
                    setEditedOutline(result.outline);
                    setOutlineRefreshed(true);
                    if (result.topic) {
                        setEditedGoal(result.topic);
                    }
                }
            }
        }
    };

    // ── Outline manipulation functions (modeled after PresentationGoalInput) ──

    const saveEditing = useCallback(() => {
        if (editingIndex === null) return;
        setEditedOutline(prev => {
            const updated = [...prev];
            if (updated[editingIndex]) {
                updated[editingIndex] = { ...updated[editingIndex], title: editingTitle, outline: editingOutline };
            }
            return updated;
        });
        setEditingIndex(null);
        setEditingTitle('');
        setEditingOutline('');
    }, [editingIndex, editingTitle, editingOutline]);

    const addOutlineItem = useCallback(() => {
        if (editingIndex !== null) saveEditing();
        const newItem = {
            slideIndex: editedOutline.length,
            title: `New ${itemLabel}`,
            outline: `Describe what this ${itemLabel.toLowerCase()} should cover...`,
        };
        setEditedOutline(prev => [...prev, newItem]);
        // Auto-enter edit mode for the new item
        setEditingIndex(editedOutline.length);
        setEditingTitle(newItem.title);
        setEditingOutline(newItem.outline);
    }, [editedOutline, editingIndex, itemLabel, saveEditing]);

    const deleteOutlineItem = useCallback((index) => {
        if (editedOutline.length <= 1) {
            Alert.alert('Cannot Delete', `You need at least one ${itemLabel.toLowerCase()}.`);
            return;
        }
        if (editingIndex === index) {
            setEditingIndex(null);
        } else if (editingIndex !== null && editingIndex > index) {
            setEditingIndex(editingIndex - 1);
        }
        setEditedOutline(prev => {
            const updated = prev.filter((_, i) => i !== index);
            return updated.map((item, i) => ({ ...item, slideIndex: i }));
        });
    }, [editedOutline.length, editingIndex, itemLabel]);

    const moveOutlineItemUp = useCallback((index) => {
        if (index <= 0) return;
        if (editingIndex !== null) saveEditing();
        setEditedOutline(prev => {
            const updated = [...prev];
            [updated[index - 1], updated[index]] = [updated[index], updated[index - 1]];
            return updated.map((item, i) => ({ ...item, slideIndex: i }));
        });
    }, [editingIndex, saveEditing]);

    const moveOutlineItemDown = useCallback((index) => {
        if (index >= editedOutline.length - 1) return;
        if (editingIndex !== null) saveEditing();
        setEditedOutline(prev => {
            const updated = [...prev];
            [updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
            return updated.map((item, i) => ({ ...item, slideIndex: i }));
        });
    }, [editedOutline.length, editingIndex, saveEditing]);

    const startEditing = useCallback((index) => {
        // Save previous editing first
        if (editingIndex !== null && editingIndex !== index) {
            setEditedOutline(prev => {
                const updated = [...prev];
                updated[editingIndex] = { ...updated[editingIndex], title: editingTitle, outline: editingOutline };
                return updated;
            });
        }
        setEditingIndex(index);
        setEditingTitle(editedOutline[index]?.title || '');
        setEditingOutline(editedOutline[index]?.outline || '');
    }, [editingIndex, editingTitle, editingOutline, editedOutline]);

    if (!visible) return null;

    const styles = getStyles(theme || {});
    const placeholderColor = theme?.textSecondary || '#999';
    const primaryColor = theme?.primary || '#2563EB';

    return (
        <Modal
            visible={visible}
            transparent={true}
            animationType="fade"
            onRequestClose={isUpdating ? null : onClose}
        >
            <View style={styles.overlay}>
                <View style={styles.modalContainer}>
                    {/* Header */}
                    <View style={styles.header}>
                        <View style={styles.titleRow}>
                            <Ionicons name="refresh-circle" size={24} color={primaryColor} />
                            <Text style={styles.title}>{title}</Text>
                            {!isUpdating && (
                                <View style={styles.stepIndicator}>
                                    <View style={[styles.stepDot, step >= 1 && { backgroundColor: primaryColor }]} />
                                    <View style={[styles.stepDotLine, step >= 2 && { backgroundColor: primaryColor }]} />
                                    <View style={[styles.stepDot, step >= 2 && { backgroundColor: primaryColor }]} />
                                </View>
                            )}
                        </View>
                        {!isUpdating && (
                            <TouchableOpacity onPress={onClose} style={styles.closeButton}>
                                <Ionicons name="close" size={24} color={theme?.text || '#333'} />
                            </TouchableOpacity>
                        )}
                    </View>

                    {/* Step 1: Topic & Outline with full editing */}
                    {step === 1 && !isUpdating && (
                        <ScrollView style={styles.scrollContent} contentContainerStyle={styles.scrollContentInner} keyboardShouldPersistTaps="handled">
                            {/* Topic / Goal Section */}
                            <View style={styles.section}>
                                <Text style={styles.sectionTitle}>
                                    <Ionicons name="bulb-outline" size={16} color={primaryColor} /> Topic / Purpose
                                </Text>
                                <Text style={styles.sectionHint}>
                                    Edit the topic or let AI suggest a new one via refresh below
                                </Text>
                                <TextInput
                                    style={styles.goalInput}
                                    value={editedGoal}
                                    onChangeText={setEditedGoal}
                                    multiline
                                    numberOfLines={3}
                                    textAlignVertical="top"
                                    placeholder="Describe the topic/purpose..."
                                    placeholderTextColor={placeholderColor}
                                />
                            </View>

                            {/* Outline Section with full controls */}
                            <View style={styles.section}>
                                <View style={styles.outlineHeaderRow}>
                                    <View style={{ flex: 1 }}>
                                        <Text style={styles.sectionTitle}>
                                            <Ionicons name="list-outline" size={16} color={primaryColor} /> {itemLabel} Outline
                                        </Text>
                                        <Text style={styles.sectionHint}>
                                            Edit, reorder, add or delete. Generate a new outline with AI suggestions based on latest data store content.
                                        </Text>
                                    </View>
                                    <View style={styles.outlineActionButtons}>
                                        {!isRefreshingOutline && (
                                            <TouchableOpacity
                                                style={[styles.addItemButton, { backgroundColor: primaryColor }]}
                                                onPress={addOutlineItem}
                                            >
                                                <Ionicons name="add" size={16} color="#fff" />
                                                <Text style={styles.addItemButtonText}>Add {itemLabel}</Text>
                                            </TouchableOpacity>
                                        )}
                                        <TouchableOpacity
                                            style={[styles.refreshButton, isRefreshingOutline && styles.refreshButtonDisabled]}
                                            onPress={handleRefreshOutline}
                                            disabled={isRefreshingOutline}
                                        >
                                            {isRefreshingOutline ? (
                                                <ActivityIndicator size="small" color={primaryColor} />
                                            ) : (
                                                <Ionicons name="sparkles" size={16} color={primaryColor} />
                                            )}
                                            <Text style={[styles.refreshButtonText, { color: primaryColor }]}>
                                                {isRefreshingOutline ? 'Generating...' : 'Generate New Outline'}
                                            </Text>
                                        </TouchableOpacity>
                                    </View>
                                </View>

                                {/* Refreshing progress indicator */}
                                {isRefreshingOutline && (
                                    <View style={[styles.refreshingBanner, { backgroundColor: primaryColor + '15' }]}>
                                        <ActivityIndicator size="small" color={primaryColor} />
                                        <View style={{ flex: 1 }}>
                                            <Text style={{ color: primaryColor, fontWeight: '600', fontSize: 14 }}>
                                                AI is generating new outline...
                                            </Text>
                                            <Text style={{ color: theme?.textSecondary || '#6B7280', fontSize: 12, marginTop: 2 }}>
                                                Based on your goal and latest data store content
                                            </Text>
                                        </View>
                                    </View>
                                )}

                                {/* Outline items with card-based editing */}
                                {editedOutline.map((item, idx) => (
                                    <View
                                        key={`outline-${idx}`}
                                        style={[
                                            styles.outlineCard,
                                            {
                                                borderColor: editingIndex === idx ? primaryColor : (theme?.border || '#E5E7EB'),
                                            },
                                        ]}
                                    >
                                        {/* Card header: number badge + title + action buttons */}
                                        <View style={styles.outlineCardHeader}>
                                            <View style={[styles.outlineNumberBadge, { backgroundColor: primaryColor }]}>
                                                <Text style={styles.outlineNumber}>{idx + 1}</Text>
                                            </View>

                                            {editingIndex === idx ? (
                                                <TextInput
                                                    style={[styles.outlineTitleInput, { borderColor: primaryColor }]}
                                                    value={editingTitle}
                                                    onChangeText={setEditingTitle}
                                                    placeholder={`${itemLabel} title`}
                                                    placeholderTextColor={placeholderColor}
                                                    autoFocus
                                                />
                                            ) : (
                                                <Text style={styles.outlineCardTitle} numberOfLines={1}>
                                                    {item.title}
                                                </Text>
                                            )}

                                            <View style={styles.outlineCardActions}>
                                                <TouchableOpacity onPress={() => moveOutlineItemUp(idx)} disabled={idx === 0}>
                                                    <Ionicons
                                                        name="chevron-up"
                                                        size={20}
                                                        color={idx === 0 ? (theme?.border || '#D1D5DB') : (theme?.textSecondary || '#6B7280')}
                                                    />
                                                </TouchableOpacity>
                                                <TouchableOpacity onPress={() => moveOutlineItemDown(idx)} disabled={idx === editedOutline.length - 1}>
                                                    <Ionicons
                                                        name="chevron-down"
                                                        size={20}
                                                        color={idx === editedOutline.length - 1 ? (theme?.border || '#D1D5DB') : (theme?.textSecondary || '#6B7280')}
                                                    />
                                                </TouchableOpacity>
                                                {editingIndex === idx ? (
                                                    <TouchableOpacity onPress={saveEditing}>
                                                        <Ionicons name="checkmark" size={20} color={primaryColor} />
                                                    </TouchableOpacity>
                                                ) : (
                                                    <TouchableOpacity onPress={() => startEditing(idx)}>
                                                        <Ionicons name="pencil" size={18} color={theme?.textSecondary || '#6B7280'} />
                                                    </TouchableOpacity>
                                                )}
                                                <TouchableOpacity onPress={() => deleteOutlineItem(idx)}>
                                                    <Ionicons name="trash-outline" size={18} color="#EF4444" />
                                                </TouchableOpacity>
                                            </View>
                                        </View>

                                        {/* Card content: outline text */}
                                        {editingIndex === idx ? (
                                            <TextInput
                                                style={[styles.outlineDescInput, { borderColor: primaryColor }]}
                                                value={editingOutline}
                                                onChangeText={setEditingOutline}
                                                placeholder={`What should this ${itemLabel.toLowerCase()} cover?`}
                                                placeholderTextColor={placeholderColor}
                                                multiline
                                                numberOfLines={3}
                                                textAlignVertical="top"
                                            />
                                        ) : (
                                            <Text style={styles.outlineCardContent} numberOfLines={3}>
                                                {item.outline || `No description yet — click pencil to edit`}
                                            </Text>
                                        )}
                                    </View>
                                ))}

                                {editedOutline.length === 0 && (
                                    <Text style={styles.emptyOutline}>
                                        No outline data available. Click "Add {itemLabel}" or "Refresh Topic & Outline" to generate one based on your goal and data store content.
                                    </Text>
                                )}
                            </View>
                        </ScrollView>
                    )}

                    {/* Step 2: Instruction */}
                    {step === 2 && !isUpdating && (
                        <View style={styles.content}>
                            <Text style={styles.label}>
                                Additional Instructions for AI:
                            </Text>
                            <TextInput
                                style={styles.input}
                                value={instruction}
                                onChangeText={setInstruction}
                                multiline
                                numberOfLines={4}
                                textAlignVertical="top"
                                placeholder="Enter additional instructions..."
                                placeholderTextColor={placeholderColor}
                            />
                            <Text style={styles.hint}>
                                This instruction along with the updated topic and outline will guide the AI to update all {itemLabel.toLowerCase()}s coherently.
                            </Text>
                        </View>
                    )}

                    {/* Updating state */}
                    {isUpdating && (
                        <View style={styles.content}>
                            <View style={styles.updatingContainer}>
                                <ActivityIndicator size="small" color={primaryColor} />
                                <Text style={styles.updatingText}>Updating... please wait</Text>
                            </View>
                        </View>
                    )}

                    {/* Footer */}
                    <View style={styles.footer}>
                        {!isUpdating && (
                            <View style={styles.buttonRow}>
                                {step === 1 ? (
                                    <>
                                        <TouchableOpacity
                                            style={[styles.button, styles.cancelButton]}
                                            onPress={onClose}
                                        >
                                            <Text style={styles.cancelButtonText}>Cancel</Text>
                                        </TouchableOpacity>
                                        <TouchableOpacity
                                            style={[styles.button, styles.confirmButton]}
                                            onPress={() => {
                                                if (editingIndex !== null) saveEditing();
                                                setStep(2);
                                            }}
                                        >
                                            <Text style={styles.confirmButtonText}>Next</Text>
                                            <Ionicons name="arrow-forward" size={16} color="white" style={{ marginLeft: 4 }} />
                                        </TouchableOpacity>
                                    </>
                                ) : (
                                    <>
                                        <TouchableOpacity
                                            style={[styles.button, styles.cancelButton]}
                                            onPress={() => setStep(1)}
                                        >
                                            <Ionicons name="arrow-back" size={16} color={theme?.text || '#374151'} style={{ marginRight: 4 }} />
                                            <Text style={styles.cancelButtonText}>Back</Text>
                                        </TouchableOpacity>
                                        <TouchableOpacity
                                            style={[styles.button, styles.confirmButton]}
                                            onPress={handleConfirm}
                                        >
                                            <Ionicons name="sparkles" size={16} color="white" style={{ marginRight: 6 }} />
                                            <Text style={styles.confirmButtonText}>Update All</Text>
                                        </TouchableOpacity>
                                    </>
                                )}
                            </View>
                        )}
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
        padding: 20,
    },
    modalContainer: {
        width: '100%',
        maxWidth: 600,
        maxHeight: '85%',
        backgroundColor: theme.surface || '#FFFFFF',
        borderRadius: 12,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.25,
        shadowRadius: 10,
        elevation: 10,
        overflow: 'hidden',
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 16,
        borderBottomWidth: 1,
        borderBottomColor: theme.border || '#E5E7EB',
        backgroundColor: theme.background || '#F9FAFB',
    },
    titleRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        flex: 1,
    },
    title: {
        fontSize: 18,
        fontWeight: '600',
        color: theme.text || '#111827',
    },
    stepIndicator: {
        flexDirection: 'row',
        alignItems: 'center',
        marginLeft: 12,
        gap: 0,
    },
    stepDot: {
        width: 8,
        height: 8,
        borderRadius: 4,
        backgroundColor: theme.border || '#D1D5DB',
    },
    stepDotLine: {
        width: 20,
        height: 2,
        backgroundColor: theme.border || '#D1D5DB',
    },
    closeButton: {
        padding: 4,
    },
    scrollContent: {
        maxHeight: 480,
    },
    scrollContentInner: {
        padding: 20,
    },
    section: {
        marginBottom: 20,
    },
    sectionTitle: {
        fontSize: 15,
        fontWeight: '600',
        color: theme.text || '#111827',
        marginBottom: 2,
    },
    sectionHint: {
        fontSize: 12,
        color: theme.textSecondary || '#6B7280',
        marginBottom: 8,
    },
    goalInput: {
        borderWidth: 1,
        borderColor: theme.border || '#D1D5DB',
        borderRadius: 8,
        padding: 12,
        fontSize: 14,
        color: theme.text || '#111827',
        backgroundColor: theme.background || '#FFFFFF',
        minHeight: 70,
    },
    outlineHeaderRow: {
        flexDirection: 'column',
        marginBottom: 12,
    },
    outlineActionButtons: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        marginTop: 8,
        flexWrap: 'wrap',
    },
    addItemButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        paddingVertical: 6,
        paddingHorizontal: 10,
        borderRadius: 6,
    },
    addItemButtonText: {
        fontSize: 12,
        fontWeight: '600',
        color: '#FFFFFF',
    },
    refreshButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        paddingVertical: 6,
        paddingHorizontal: 10,
        borderRadius: 6,
        borderWidth: 1,
        borderColor: theme.primary || '#2563EB',
    },
    refreshButtonDisabled: {
        opacity: 0.6,
    },
    refreshButtonText: {
        fontSize: 12,
        fontWeight: '500',
    },
    refreshingBanner: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 12,
        borderRadius: 10,
        marginBottom: 12,
        gap: 12,
    },
    // Card-based outline item styles
    outlineCard: {
        borderWidth: 1,
        borderRadius: 10,
        padding: 12,
        marginBottom: 10,
        backgroundColor: theme.background || '#FFFFFF',
    },
    outlineCardHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        marginBottom: 6,
    },
    outlineNumberBadge: {
        width: 26,
        height: 26,
        borderRadius: 13,
        justifyContent: 'center',
        alignItems: 'center',
    },
    outlineNumber: {
        color: '#FFFFFF',
        fontSize: 12,
        fontWeight: '700',
    },
    outlineCardTitle: {
        flex: 1,
        fontSize: 14,
        fontWeight: '600',
        color: theme.text || '#111827',
    },
    outlineCardActions: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
    },
    outlineTitleInput: {
        flex: 1,
        borderWidth: 1,
        borderRadius: 6,
        paddingVertical: 4,
        paddingHorizontal: 8,
        fontSize: 14,
        fontWeight: '600',
        color: theme.text || '#111827',
        backgroundColor: theme.surface || '#FFFFFF',
    },
    outlineDescInput: {
        borderWidth: 1,
        borderColor: theme.border || '#D1D5DB',
        borderRadius: 6,
        paddingVertical: 6,
        paddingHorizontal: 10,
        fontSize: 13,
        color: theme.text || '#111827',
        backgroundColor: theme.surface || '#FFFFFF',
        minHeight: 50,
    },
    outlineCardContent: {
        fontSize: 13,
        color: theme.textSecondary || '#6B7280',
        lineHeight: 18,
    },
    emptyOutline: {
        fontSize: 13,
        color: theme.textSecondary || '#6B7280',
        fontStyle: 'italic',
        textAlign: 'center',
        paddingVertical: 20,
    },
    content: {
        padding: 20,
    },
    label: {
        fontSize: 14,
        fontWeight: '500',
        color: theme.text || '#374151',
        marginBottom: 8,
    },
    input: {
        borderWidth: 1,
        borderColor: theme.border || '#D1D5DB',
        borderRadius: 8,
        padding: 12,
        fontSize: 14,
        color: theme.text || '#111827',
        backgroundColor: theme.background || '#FFFFFF',
        minHeight: 100,
    },
    hint: {
        marginTop: 8,
        fontSize: 12,
        color: theme.textSecondary || '#6B7280',
        fontStyle: 'italic',
    },
    footer: {
        padding: 16,
        borderTopWidth: 1,
        borderTopColor: theme.border || '#E5E7EB',
        backgroundColor: theme.background || '#F9FAFB',
    },
    buttonRow: {
        flexDirection: 'row',
        justifyContent: 'flex-end',
        gap: 12,
    },
    button: {
        paddingVertical: 10,
        paddingHorizontal: 16,
        borderRadius: 6,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
    },
    cancelButton: {
        backgroundColor: 'transparent',
        borderWidth: 1,
        borderColor: theme.border || '#D1D5DB',
    },
    cancelButtonText: {
        color: theme.text || '#374151',
        fontWeight: '500',
    },
    confirmButton: {
        backgroundColor: theme.primary || '#2563EB',
    },
    confirmButtonText: {
        color: '#FFFFFF',
        fontWeight: '600',
    },
    updatingContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 10,
        paddingVertical: 6,
    },
    updatingText: {
        color: theme.primary || '#2563EB',
        fontWeight: '500',
    }
});

export default UpdateInstructionModal;
