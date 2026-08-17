// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

import React, { useState } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    StyleSheet,
    TextInput,
    ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { fetchEmbedMetadata } from './utils/embedMetadataService';

/**
 * Modal to add Forms and Buttons (Calendly, Typeform, Google Form, Tally, custom CTA)
 */
const FormsButtonModal = ({
    visible,
    onClose,
    onSelectForm, // (data) => void for form embeds
    onSelectButton, // (data) => void for button CTAs
    theme
}) => {
    const [mode, setMode] = useState('menu'); // 'menu' | 'form' | 'button'
    const [selectedType, setSelectedType] = useState(null);
    const [url, setUrl] = useState('');
    const [buttonLabel, setButtonLabel] = useState('');
    const [buttonStyle, setButtonStyle] = useState('primary'); // 'primary' | 'secondary' | 'ghost'
    const [error, setError] = useState('');
    const [isValidating, setIsValidating] = useState(false);

    const resetState = () => {
        setMode('menu');
        setSelectedType(null);
        setUrl('');
        setButtonLabel('');
        setButtonStyle('primary');
        setError('');
        setIsValidating(false);
    };

    const handleClose = () => {
        resetState();
        onClose();
    };

    const handleSelectType = (type, isButton = false) => {
        setSelectedType(type);
        setMode(isButton ? 'button' : 'form');
    };

    const handleFormSubmit = async () => {
        if (!url.trim()) return;
        setError('');
        setIsValidating(true);

        try {
            const metadata = await fetchEmbedMetadata(url);

            onSelectForm({
                src: url,
                formType: metadata?.videoType || selectedType,
                provider: metadata?.provider || selectedType,
                title: metadata?.title || `${selectedType} Form`,
                html: metadata?.html,
                width: metadata?.width || 640,
                height: metadata?.height || 500
            });
            handleClose();
        } catch (err) {
            console.error('Form validation error:', err);
            setError(err.message || 'Failed to validate URL');
        } finally {
            setIsValidating(false);
        }
    };

    const handleButtonSubmit = () => {
        if (!buttonLabel.trim() || !url.trim()) {
            setError('Please enter both label and URL');
            return;
        }

        onSelectButton({
            type: 'button',
            label: buttonLabel,
            url: url,
            style: buttonStyle,
            width: 160,
            height: 48
        });
        handleClose();
    };

    const FORM_TYPES = [
        { id: 'button', label: 'Clickable Button', icon: 'hand-left-outline', color: '#6366F1', isButton: true },
        { id: 'calendly', label: 'Calendly', icon: 'calendar-outline', color: '#006BFF' },
        { id: 'typeform', label: 'Typeform', icon: 'checkbox-outline', color: '#262627' },
        { id: 'googleform', label: 'Google Form', icon: 'document-text-outline', color: '#673AB7' },
        { id: 'tally', label: 'Tally Form', icon: 'list-outline', color: '#1E1E1E' },
    ];

    const BUTTON_STYLES = [
        { id: 'primary', label: 'Primary', bgColor: '#2563EB', textColor: '#fff' },
        { id: 'secondary', label: 'Secondary', bgColor: '#E5E7EB', textColor: '#1F2937' },
        { id: 'ghost', label: 'Ghost', bgColor: 'transparent', textColor: '#2563EB', borderColor: '#2563EB' },
    ];

    const getPlaceholder = () => {
        switch (selectedType) {
            case 'calendly': return 'https://calendly.com/your-name';
            case 'typeform': return 'https://form.typeform.com/to/...';
            case 'googleform': return 'https://docs.google.com/forms/...';
            case 'tally': return 'https://tally.so/r/...';
            default: return 'https://...';
        }
    };

    const OptionButton = ({ icon, label, color, onPress }) => (
        <TouchableOpacity
            style={[styles.optionBtn, { borderColor: theme.border }]}
            onPress={onPress}
        >
            <View style={[styles.iconContainer, { backgroundColor: color + '20' }]}>
                <Ionicons name={icon} size={24} color={color} />
            </View>
            <Text style={[styles.optionLabel, { color: theme.text }]}>{label}</Text>
            <Ionicons name="chevron-forward" size={16} color={theme.textSecondary} style={{ marginLeft: 'auto' }} />
        </TouchableOpacity>
    );

    return (
        <Modal
            visible={visible}
            transparent
            animationType="fade"
            onRequestClose={handleClose}
        >
            <View style={styles.overlay}>
                <TouchableOpacity style={styles.backdrop} onPress={handleClose} />

                <View style={[styles.modal, { backgroundColor: theme.surface }]}>
                    <View style={[styles.header, { borderBottomColor: theme.border }]}>
                        <TouchableOpacity onPress={mode === 'menu' ? handleClose : () => setMode('menu')}>
                            <Ionicons name={mode === 'menu' ? "close" : "arrow-back"} size={20} color={theme.text} />
                        </TouchableOpacity>
                        <Text style={[styles.title, { color: theme.text }]}>
                            {mode === 'menu' ? 'Forms & Buttons' : mode === 'button' ? 'Add Button' : `Add ${selectedType?.charAt(0).toUpperCase() + selectedType?.slice(1)}`}
                        </Text>
                        <View style={{ width: 20 }} />
                    </View>

                    <View style={styles.content}>
                        {mode === 'menu' ? (
                            <View style={styles.menuContainer}>
                                {FORM_TYPES.map((type) => (
                                    <OptionButton
                                        key={type.id}
                                        icon={type.icon}
                                        label={type.label}
                                        color={type.color}
                                        onPress={() => handleSelectType(type.id, type.isButton)}
                                    />
                                ))}
                            </View>
                        ) : mode === 'button' ? (
                            <View style={styles.inputContainer}>
                                <Text style={[styles.inputLabel, { color: theme.text }]}>Button Label</Text>
                                <TextInput
                                    style={[styles.input, {
                                        backgroundColor: theme.background,
                                        color: theme.text,
                                        borderColor: theme.border
                                    }]}
                                    placeholder="e.g. Learn More"
                                    placeholderTextColor={theme.textSecondary}
                                    value={buttonLabel}
                                    onChangeText={setButtonLabel}
                                    autoFocus
                                />

                                <Text style={[styles.inputLabel, { color: theme.text }]}>Button URL</Text>
                                <TextInput
                                    style={[styles.input, {
                                        backgroundColor: theme.background,
                                        color: theme.text,
                                        borderColor: theme.border
                                    }]}
                                    placeholder="https://..."
                                    placeholderTextColor={theme.textSecondary}
                                    value={url}
                                    onChangeText={setUrl}
                                    autoCapitalize="none"
                                />

                                <Text style={[styles.inputLabel, { color: theme.text }]}>Style</Text>
                                <View style={styles.styleRow}>
                                    {BUTTON_STYLES.map((style) => (
                                        <TouchableOpacity
                                            key={style.id}
                                            style={[
                                                styles.stylePill,
                                                {
                                                    backgroundColor: style.bgColor,
                                                    borderColor: style.borderColor || 'transparent',
                                                    borderWidth: style.borderColor ? 2 : 0,
                                                },
                                                buttonStyle === style.id && styles.styleSelected
                                            ]}
                                            onPress={() => setButtonStyle(style.id)}
                                        >
                                            <Text style={{ color: style.textColor, fontWeight: '600', fontSize: 12 }}>{style.label}</Text>
                                        </TouchableOpacity>
                                    ))}
                                </View>

                                {error ? <Text style={styles.errorText}>{error}</Text> : null}

                                <TouchableOpacity
                                    style={[styles.submitBtn, { backgroundColor: theme.primary }]}
                                    onPress={handleButtonSubmit}
                                >
                                    <Text style={styles.submitBtnText}>Add Button</Text>
                                </TouchableOpacity>
                            </View>
                        ) : (
                            <View style={styles.inputContainer}>
                                <Text style={[styles.inputLabel, { color: theme.text }]}>Paste form URL</Text>
                                <TextInput
                                    style={[styles.input, {
                                        backgroundColor: theme.background,
                                        color: theme.text,
                                        borderColor: error ? '#EF4444' : theme.border
                                    }]}
                                    placeholder={getPlaceholder()}
                                    placeholderTextColor={theme.textSecondary}
                                    value={url}
                                    onChangeText={setUrl}
                                    autoFocus
                                    autoCapitalize="none"
                                />
                                {error ? <Text style={styles.errorText}>{error}</Text> : null}

                                <TouchableOpacity
                                    style={[styles.submitBtn, { backgroundColor: theme.primary, opacity: !url.trim() || isValidating ? 0.6 : 1 }]}
                                    onPress={handleFormSubmit}
                                    disabled={!url.trim() || isValidating}
                                >
                                    {isValidating ? (
                                        <ActivityIndicator size="small" color="#fff" />
                                    ) : (
                                        <Text style={styles.submitBtnText}>Add Form</Text>
                                    )}
                                </TouchableOpacity>
                            </View>
                        )}
                    </View>
                </View>
            </View>
        </Modal>
    );
};

const styles = StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.5)',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 20,
    },
    backdrop: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
    },
    modal: {
        width: '100%',
        maxWidth: 400,
        borderRadius: 12,
        overflow: 'hidden',
        elevation: 5,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.2,
        shadowRadius: 10,
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 16,
        borderBottomWidth: 1,
    },
    title: {
        fontSize: 16,
        fontWeight: '600',
    },
    content: {
        padding: 16,
    },
    menuContainer: {
        gap: 8,
    },
    optionBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 12,
        borderRadius: 8,
        borderWidth: 1,
        gap: 12,
    },
    iconContainer: {
        width: 40,
        height: 40,
        borderRadius: 8,
        justifyContent: 'center',
        alignItems: 'center',
    },
    optionLabel: {
        fontSize: 14,
        fontWeight: '500',
    },
    inputContainer: {
        gap: 12,
    },
    inputLabel: {
        fontSize: 14,
        fontWeight: '500',
    },
    input: {
        height: 48,
        borderWidth: 1,
        borderRadius: 8,
        paddingHorizontal: 12,
        fontSize: 14,
    },
    styleRow: {
        flexDirection: 'row',
        gap: 8,
    },
    stylePill: {
        paddingHorizontal: 16,
        paddingVertical: 8,
        borderRadius: 20,
    },
    styleSelected: {
        ring: 2,
        ringColor: '#2563EB',
    },
    errorText: {
        color: '#EF4444',
        fontSize: 12,
    },
    submitBtn: {
        height: 44,
        borderRadius: 8,
        justifyContent: 'center',
        alignItems: 'center',
        marginTop: 8,
    },
    submitBtnText: {
        color: '#fff',
        fontSize: 14,
        fontWeight: '600',
    },
});

export default FormsButtonModal;
