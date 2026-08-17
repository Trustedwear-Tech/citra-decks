// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, ScrollView, Animated } from 'react-native';
import { MaterialIcons as Icon } from '@expo/vector-icons';

const ContextNavigator = ({ 
  contextManager, 
  currentPage, 
  totalPages,
  onPageChange,
  documentProgress = null 
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [rotateAnim] = useState(new Animated.Value(0));

  const toggleExpanded = () => {
    const toValue = isExpanded ? 1 : 0;
    Animated.timing(rotateAnim, {
      toValue,
      duration: 200,
      useNativeDriver: true,
    }).start();
    setIsExpanded(!isExpanded);
  };

  const getProgressColor = (progress) => {
    if (progress >= 80) return '#4CAF50';
    if (progress >= 60) return '#FF9800';
    if (progress >= 40) return '#2196F3';
    return '#f44336';
  };

  const getPageStatus = (pageNum) => {
    if (pageNum < currentPage) return 'completed';
    if (pageNum === currentPage) return 'current';
    return 'upcoming';
  };

  const getPageStatusIcon = (pageNum) => {
    const status = getPageStatus(pageNum);
    switch (status) {
      case 'completed': return { name: 'check-circle', color: '#4CAF50' };
      case 'current': return { name: 'edit', color: '#2196F3' };
      case 'upcoming': return { name: 'radio-button-unchecked', color: '#999' };
      default: return { name: 'radio-button-unchecked', color: '#999' };
    }
  };

  const calculateGoalProgress = () => {
    if (!documentProgress) return 0;
    return documentProgress.overall_completion || 0;
  };

  const getNextStepSuggestion = () => {
    if (!documentProgress?.next_priorities?.length) {
      return "Continue writing to develop your document further";
    }
    return documentProgress.next_priorities[0];
  };

  const styles = {
    container: {
      backgroundColor: 'white',
      borderRadius: 12,
      marginVertical: 10,
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.1,
      shadowRadius: 4,
      elevation: 3,
      borderWidth: 1,
      borderColor: '#e0e0e0'
    },
    header: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: 15,
      borderBottomWidth: isExpanded ? 1 : 0,
      borderBottomColor: '#f0f0f0'
    },
    headerTitle: {
      fontSize: 16,
      fontWeight: '600',
      color: '#333',
      flex: 1
    },
    expandButton: {
      padding: 5
    },
    content: {
      padding: isExpanded ? 15 : 0,
      maxHeight: isExpanded ? 400 : 0,
      overflow: 'hidden'
    },
    contextSection: {
      marginBottom: 20
    },
    sectionTitle: {
      fontSize: 14,
      fontWeight: '600',
      color: '#555',
      marginBottom: 10,
      flexDirection: 'row',
      alignItems: 'center'
    },
    sectionIcon: {
      marginRight: 6
    },
    contextCard: {
      backgroundColor: '#f8f9fa',
      padding: 12,
      borderRadius: 8,
      borderLeftWidth: 3,
      borderLeftColor: '#007AFF',
      marginBottom: 10
    },
    contextLabel: {
      fontSize: 12,
      fontWeight: '600',
      color: '#666',
      marginBottom: 4
    },
    contextText: {
      fontSize: 14,
      color: '#333',
      lineHeight: 18
    },
    progressContainer: {
      backgroundColor: '#e3f2fd',
      padding: 12,
      borderRadius: 8,
      borderLeftWidth: 3,
      borderLeftColor: '#2196F3'
    },
    progressHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: 8
    },
    progressPercent: {
      fontSize: 16,
      fontWeight: 'bold',
      color: '#1976d2'
    },
    progressBar: {
      height: 6,
      backgroundColor: '#e0e0e0',
      borderRadius: 3,
      overflow: 'hidden',
      marginBottom: 8
    },
    progressFill: {
      height: '100%',
      borderRadius: 3
    },
    progressDetails: {
      fontSize: 12,
      color: '#424242',
      lineHeight: 16
    },
    pagesNavigation: {
      marginTop: 10
    },
    pagesScrollView: {
      paddingVertical: 5
    },
    pageButton: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 12,
      paddingVertical: 8,
      marginRight: 10,
      borderRadius: 20,
      borderWidth: 1,
      borderColor: '#ddd',
      backgroundColor: '#f8f9fa',
      minWidth: 80
    },
    currentPageButton: {
      backgroundColor: '#2196F3',
      borderColor: '#2196F3'
    },
    completedPageButton: {
      backgroundColor: '#e8f5e8',
      borderColor: '#4CAF50'
    },
    pageButtonText: {
      fontSize: 12,
      color: '#666',
      marginLeft: 5,
      fontWeight: '500'
    },
    currentPageButtonText: {
      color: 'white'
    },
    completedPageButtonText: {
      color: '#2e7d32'
    },
    nextStepCard: {
      backgroundColor: '#fff3e0',
      padding: 12,
      borderRadius: 8,
      borderLeftWidth: 3,
      borderLeftColor: '#FF9800'
    },
    nextStepText: {
      fontSize: 13,
      color: '#e65100',
      lineHeight: 18,
      fontStyle: 'italic'
    },
    goalSummary: {
      backgroundColor: '#f3e5f5',
      padding: 12,
      borderRadius: 8,
      borderLeftWidth: 3,
      borderLeftColor: '#9C27B0',
      marginBottom: 15
    },
    goalTitle: {
      fontSize: 12,
      fontWeight: '600',
      color: '#7b1fa2',
      marginBottom: 4
    },
    goalText: {
      fontSize: 13,
      color: '#4a148c',
      lineHeight: 16
    }
  };

  const rotate = rotateAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '180deg'],
  });

  return (
    <View style={styles.container}>
      <TouchableOpacity onPress={toggleExpanded} style={styles.header} activeOpacity={0.7}>
        <Text style={styles.headerTitle}>🧭 Document Context Navigator</Text>
        <Animated.View style={[styles.expandButton, { transform: [{ rotate }] }]}>
          <Icon name="expand-more" size={24} color="#666" />
        </Animated.View>
      </TouchableOpacity>

      {isExpanded && (
        <View style={styles.content}>
          {/* Goal Summary */}
          {contextManager?.reportGoal?.purpose && (
            <View style={styles.goalSummary}>
              <Text style={styles.goalTitle}>📝 Document Goal</Text>
              <Text style={styles.goalText}>
                {contextManager.reportGoal.purpose.length > 80 
                  ? contextManager.reportGoal.purpose.substring(0, 80) + '...'
                  : contextManager.reportGoal.purpose
                }
              </Text>
            </View>
          )}

          {/* Progress Tracking */}
          <View style={styles.contextSection}>
            <Text style={styles.sectionTitle}>
              <Icon name="trending-up" size={16} color="#555" style={styles.sectionIcon} />
              Goal Progress
            </Text>
            
            <View style={styles.progressContainer}>
              <View style={styles.progressHeader}>
                <Text style={styles.contextLabel}>Overall Completion</Text>
                <Text style={styles.progressPercent}>
                  {Math.round(calculateGoalProgress())}%
                </Text>
              </View>
              
              <View style={styles.progressBar}>
                <View 
                  style={[
                    styles.progressFill,
                    { 
                      width: `${calculateGoalProgress()}%`,
                      backgroundColor: getProgressColor(calculateGoalProgress())
                    }
                  ]} 
                />
              </View>
              
              {documentProgress?.strengths?.length > 0 && (
                <Text style={styles.progressDetails}>
                  ✅ Strengths: {documentProgress.strengths.slice(0, 2).join(', ')}
                </Text>
              )}
            </View>
          </View>

          {/* Pages Navigation */}
          <View style={styles.contextSection}>
            <Text style={styles.sectionTitle}>
              <Icon name="library-books" size={16} color="#555" style={styles.sectionIcon} />
              Pages ({currentPage} of {totalPages})
            </Text>
            
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.pagesScrollView}>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map(pageNum => {
                const status = getPageStatus(pageNum);
                const statusIcon = getPageStatusIcon(pageNum);
                
                return (
                  <TouchableOpacity
                    key={pageNum}
                    style={[
                      styles.pageButton,
                      status === 'current' && styles.currentPageButton,
                      status === 'completed' && styles.completedPageButton
                    ]}
                    onPress={() => onPageChange && onPageChange(pageNum)}
                    activeOpacity={0.7}
                  >
                    <Icon name={statusIcon.name} size={16} color={statusIcon.color} />
                    <Text style={[
                      styles.pageButtonText,
                      status === 'current' && styles.currentPageButtonText,
                      status === 'completed' && styles.completedPageButtonText
                    ]}>
                      Page {pageNum}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>

          {/* Context Flow */}
          <View style={styles.contextSection}>
            <Text style={styles.sectionTitle}>
              <Icon name="timeline" size={16} color="#555" style={styles.sectionIcon} />
              Document Flow
            </Text>
            
            {/* Previous Page Context */}
            {currentPage > 1 && (
              <View style={styles.contextCard}>
                <Text style={styles.contextLabel}>← Previous Section</Text>
                <Text style={styles.contextText}>
                  {contextManager?.contextWindow?.previousPage?.summary || 
                   `Page ${currentPage - 1} content leads into current section`}
                </Text>
              </View>
            )}

            {/* Current Page Focus */}
            <View style={styles.contextCard}>
              <Text style={styles.contextLabel}>🎯 Current Focus (Page {currentPage})</Text>
              <Text style={styles.contextText}>
                {contextManager?.documentStructure?.pages?.[currentPage]?.keyPoints ||
                 'Developing content that aligns with document goals'}
              </Text>
            </View>

            {/* Next Section Planning */}
            {currentPage < totalPages && (
              <View style={styles.contextCard}>
                <Text style={styles.contextLabel}>→ Next Section</Text>
                <Text style={styles.contextText}>
                  {contextManager?.contextWindow?.nextPage?.plannedContent || 
                   `Page ${currentPage + 1} will continue building toward the document goal`}
                </Text>
              </View>
            )}
          </View>

          {/* Next Steps */}
          <View style={styles.contextSection}>
            <Text style={styles.sectionTitle}>
              <Icon name="assistant" size={16} color="#555" style={styles.sectionIcon} />
              AI Suggestion
            </Text>
            
            <View style={styles.nextStepCard}>
              <Text style={styles.nextStepText}>
                💡 {getNextStepSuggestion()}
              </Text>
            </View>
          </View>
        </View>
      )}
    </View>
  );
};

export default ContextNavigator;
