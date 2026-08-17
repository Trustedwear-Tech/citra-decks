// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

import React, { useState } from 'react';
import { View, Text, Platform, StyleSheet } from 'react-native';

const Tooltip = ({ text, children, position = 'bottom', theme }) => {
    const [visible, setVisible] = useState(false);

    // Simple tooltip implementation for Web
    // For Native, we rely on the native 'title' prop or platform-specific implementation
    if (Platform.OS !== 'web') {
        return children;
    }

    const isDark = theme?.isDark || false;

    return (
        <View
            style={[styles.container, { zIndex: visible ? 9999 : 1 }]}
            onMouseEnter={() => setVisible(true)}
            onMouseLeave={() => setVisible(false)}
        >
            {children}
            {visible && text && (
                <View style={[
                    styles.tooltipContainer,
                    styles[position],
                    { backgroundColor: isDark ? '#E5E7EB' : '#1F2937' } // Inverse of theme usually looks good
                ]}>
                    <Text style={[
                        styles.tooltipText,
                        { color: isDark ? '#1F2937' : '#F9FAFB' }
                    ]}>
                        {text}
                    </Text>
                    {/* Arrow */}
                    <View style={[
                        styles.arrow,
                        styles[`arrow${position.charAt(0).toUpperCase() + position.slice(1)}`],
                        { borderTopColor: isDark ? '#E5E7EB' : '#1F2937' },
                        position === 'bottom' && { borderBottomColor: isDark ? '#E5E7EB' : '#1F2937', borderTopColor: 'transparent' },
                        position === 'left' && { borderLeftColor: isDark ? '#E5E7EB' : '#1F2937', borderTopColor: 'transparent' },
                        position === 'right' && { borderRightColor: isDark ? '#E5E7EB' : '#1F2937', borderTopColor: 'transparent' }
                    ]} />
                </View>
            )}
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        position: 'relative',
        alignItems: 'center',
        justifyContent: 'center',
    },
    tooltipContainer: {
        position: 'absolute',
        paddingHorizontal: 8,
        paddingVertical: 5,
        borderRadius: 6,
        zIndex: 9999,
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.15,
        shadowRadius: 3,
        elevation: 5,
        maxWidth: 200,
        minWidth: 'max-content',
        whiteSpace: 'nowrap',
    },
    tooltipText: {
        fontSize: 12,
        fontWeight: '500',
        textAlign: 'center',
        userSelect: 'none',
    },
    arrow: {
        position: 'absolute',
        width: 0,
        height: 0,
        borderStyle: 'solid',
        borderWidth: 5,
        borderColor: 'transparent',
    },
    // Positions
    top: {
        bottom: '100%',
        marginBottom: 8,
    },
    bottom: {
        top: '100%',
        marginTop: 8,
    },
    left: {
        right: '100%',
        marginRight: 8,
        top: '50%',
        transform: [{ translateY: '-50%' }],
    },
    right: {
        left: '100%',
        marginLeft: 8,
        top: '50%',
        transform: [{ translateY: '-50%' }],
    },
    // Arrows
    arrowTop: {
        top: '100%',
        left: '50%',
        transform: [{ translateX: '-5' }],
    },
    arrowBottom: {
        bottom: '100%',
        left: '50%',
        transform: [{ translateX: '-5' }],
    },
    arrowLeft: {
        left: '100%',
        top: '50%',
        transform: [{ translateY: '-5' }],
    },
    arrowRight: {
        right: '100%',
        top: '50%',
        transform: [{ translateY: '-5' }],
    },
});

export default Tooltip;
