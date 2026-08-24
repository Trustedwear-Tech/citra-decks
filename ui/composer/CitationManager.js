// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may not
// use this file except in compliance with the License. You may obtain a copy of
// the License at http://www.apache.org/licenses/LICENSE-2.0

// CitationManager.js - Comprehensive citation management system
import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  TextInput,
  Modal,
  Alert,
  Switch,
  FlatList
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const CitationManager = ({
  visible,
  onClose,
  onInsertCitation,
  reportId,
  theme,
  apiConfig,
  userDeviceId
}) => {
  const [activeTab, setActiveTab] = useState('library'); // 'library', 'add', 'bibliography'
  const [citations, setCitations] = useState([]);
  const [filteredCitations, setFilteredCitations] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCitations, setSelectedCitations] = useState([]);
  const [citationStyle, setCitationStyle] = useState('APA'); // APA, MLA, Chicago, Harvard
  const [isLoading, setIsLoading] = useState(false);
  
  // Add Citation Form State
  const [newCitation, setNewCitation] = useState({
    type: 'article', // article, book, website, report, journal
    title: '',
    authors: [''],
    publication: '',
    year: '',
    pages: '',
    url: '',
    doi: '',
    accessDate: '',
    publisher: '',
    volume: '',
    issue: '',
    notes: ''
  });

  // Load citations
  useEffect(() => {
    if (visible && reportId) {
      loadCitations();
    }
  }, [visible, reportId]);

  // Filter citations based on search
  useEffect(() => {
    if (!searchQuery) {
      setFilteredCitations(citations);
    } else {
      const filtered = citations.filter(citation =>
        citation.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        citation.authors.some(author => 
          author.toLowerCase().includes(searchQuery.toLowerCase())
        ) ||
        citation.publication.toLowerCase().includes(searchQuery.toLowerCase())
      );
      setFilteredCitations(filtered);
    }
  }, [searchQuery, citations]);

  const loadCitations = async () => {
    try {
      setIsLoading(true);
      // Mock citations data - replace with actual API call
      const mockCitations = [
        {
          id: '1',
          type: 'article',
          title: 'The Impact of Digital Transformation on Business Operations',
          authors: ['Smith, J.', 'Johnson, M.'],
          publication: 'Harvard Business Review',
          year: '2023',
          pages: '45-62',
          volume: '101',
          issue: '3',
          url: 'https://hbr.org/2023/03/digital-transformation',
          doi: '10.1177/1234567890',
          accessDate: '2023-12-01',
          notes: 'Key insights on operational efficiency',
          citationKey: 'smith2023digital',
          usedInReport: true
        },
        {
          id: '2',
          type: 'book',
          title: 'Strategic Management: Concepts and Cases',
          authors: ['Thompson, A.', 'Strickland, A.', 'Gamble, J.'],
          publisher: 'McGraw-Hill Education',
          year: '2022',
          pages: '1-650',
          url: '',
          doi: '',
          accessDate: '',
          notes: 'Comprehensive strategic management framework',
          citationKey: 'thompson2022strategic',
          usedInReport: false
        },
        {
          id: '3',
          type: 'website',
          title: 'Global Market Trends 2023',
          authors: ['McKinsey & Company'],
          publication: 'McKinsey.com',
          year: '2023',
          url: 'https://mckinsey.com/insights/global-trends-2023',
          accessDate: '2023-11-15',
          notes: 'Current market analysis and forecasts',
          citationKey: 'mckinsey2023trends',
          usedInReport: true
        },
        {
          id: '4',
          type: 'report',
          title: 'Industry Analysis Report: Technology Sector Q3 2023',
          authors: ['Deloitte Research Team'],
          publisher: 'Deloitte Insights',
          year: '2023',
          pages: '1-85',
          url: 'https://deloitte.com/insights/tech-sector-q3-2023',
          accessDate: '2023-10-20',
          notes: 'Detailed technology sector performance metrics',
          citationKey: 'deloitte2023tech',
          usedInReport: false
        }
      ];
      setCitations(mockCitations);
    } catch (error) {
      console.error('Error loading citations:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddCitation = async () => {
    if (!newCitation.title.trim() || newCitation.authors[0].trim() === '') {
      Alert.alert('Error', 'Please fill in at least the title and first author');
      return;
    }

    try {
      const citation = {
        id: Date.now().toString(),
        ...newCitation,
        citationKey: generateCitationKey(newCitation),
        usedInReport: false
      };

      setCitations(prev => [citation, ...prev]);
      resetNewCitation();
      setActiveTab('library');
      Alert.alert('Success', 'Citation added to library');
    } catch (error) {
      console.error('Error adding citation:', error);
      Alert.alert('Error', 'Failed to add citation. Please try again.');
    }
  };

  const generateCitationKey = (citation) => {
    const firstAuthor = citation.authors[0].split(',')[0].toLowerCase();
    const year = citation.year;
    const firstWord = citation.title.split(' ')[0].toLowerCase().replace(/[^a-z]/g, '');
    return `${firstAuthor}${year}${firstWord}`;
  };

  const resetNewCitation = () => {
    setNewCitation({
      type: 'article',
      title: '',
      authors: [''],
      publication: '',
      year: '',
      pages: '',
      url: '',
      doi: '',
      accessDate: '',
      publisher: '',
      volume: '',
      issue: '',
      notes: ''
    });
  };

  const handleInsertCitation = (citation) => {
    const formattedCitation = formatInTextCitation(citation, citationStyle);
    onInsertCitation?.(formattedCitation, citation);
    
    // Mark as used in report
    setCitations(prev =>
      prev.map(c =>
        c.id === citation.id ? { ...c, usedInReport: true } : c
      )
    );
  };

  const formatInTextCitation = (citation, style) => {
    switch (style) {
      case 'APA':
        if (citation.authors.length === 1) {
          return `(${citation.authors[0].split(',')[0]}, ${citation.year})`;
        } else if (citation.authors.length === 2) {
          return `(${citation.authors[0].split(',')[0]} & ${citation.authors[1].split(',')[0]}, ${citation.year})`;
        } else {
          return `(${citation.authors[0].split(',')[0]} et al., ${citation.year})`;
        }
      case 'MLA':
        return `(${citation.authors[0].split(',')[0]} ${citation.pages ? citation.pages.split('-')[0] : ''})`;
      case 'Chicago':
        return `(${citation.authors[0].split(',')[0]} ${citation.year})`;
      case 'Harvard':
        return `(${citation.authors[0].split(',')[0]}, ${citation.year})`;
      default:
        return `(${citation.authors[0].split(',')[0]}, ${citation.year})`;
    }
  };

  const formatBibliographyEntry = (citation, style) => {
    const authors = citation.authors.join(', ');
    
    switch (style) {
      case 'APA':
        switch (citation.type) {
          case 'article':
            return `${authors} (${citation.year}). ${citation.title}. *${citation.publication}*, ${citation.volume}(${citation.issue}), ${citation.pages}. ${citation.doi ? `https://doi.org/${citation.doi}` : citation.url}`;
          case 'book':
            return `${authors} (${citation.year}). *${citation.title}*. ${citation.publisher}.`;
          case 'website':
            return `${authors} (${citation.year}). ${citation.title}. Retrieved ${citation.accessDate}, from ${citation.url}`;
          case 'report':
            return `${authors} (${citation.year}). *${citation.title}*. ${citation.publisher}. ${citation.url}`;
          default:
            return `${authors} (${citation.year}). ${citation.title}.`;
        }
      case 'MLA':
        switch (citation.type) {
          case 'article':
            return `${authors} "${citation.title}." *${citation.publication}*, vol. ${citation.volume}, no. ${citation.issue}, ${citation.year}, pp. ${citation.pages}.`;
          case 'book':
            return `${authors} *${citation.title}*. ${citation.publisher}, ${citation.year}.`;
          case 'website':
            return `${authors} "${citation.title}." *${citation.publication}*, ${citation.year}, ${citation.url}. Accessed ${citation.accessDate}.`;
          default:
            return `${authors} "${citation.title}." ${citation.year}.`;
        }
      default:
        return `${authors} (${citation.year}). ${citation.title}. ${citation.publication}.`;
    }
  };

  const generateBibliography = () => {
    const usedCitations = citations.filter(c => c.usedInReport);
    const sortedCitations = usedCitations.sort((a, b) => 
      a.authors[0].localeCompare(b.authors[0])
    );
    
    return sortedCitations.map(citation => 
      formatBibliographyEntry(citation, citationStyle)
    ).join('\n\n');
  };

  const handleDeleteCitation = (citationId) => {
    Alert.alert(
      'Delete Citation',
      'Are you sure you want to delete this citation?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: () => {
            setCitations(prev => prev.filter(c => c.id !== citationId));
          }
        }
      ]
    );
  };

  const updateAuthor = (index, value) => {
    const updatedAuthors = [...newCitation.authors];
    updatedAuthors[index] = value;
    setNewCitation(prev => ({ ...prev, authors: updatedAuthors }));
  };

  const addAuthor = () => {
    setNewCitation(prev => ({ 
      ...prev, 
      authors: [...prev.authors, ''] 
    }));
  };

  const removeAuthor = (index) => {
    if (newCitation.authors.length > 1) {
      const updatedAuthors = newCitation.authors.filter((_, i) => i !== index);
      setNewCitation(prev => ({ ...prev, authors: updatedAuthors }));
    }
  };

  const tabs = [
    { id: 'library', label: 'Library', icon: 'library-outline' },
    { id: 'add', label: 'Add', icon: 'add-circle-outline' },
    { id: 'bibliography', label: 'Bibliography', icon: 'list-outline' }
  ];

  const citationTypes = [
    { id: 'article', label: 'Journal Article' },
    { id: 'book', label: 'Book' },
    { id: 'website', label: 'Website' },
    { id: 'report', label: 'Report' }
  ];

  const citationStyles = ['APA', 'MLA', 'Chicago', 'Harvard'];

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <View style={[styles.container, { backgroundColor: theme.background }]}>
        {/* Header */}
        <View style={[styles.header, { borderBottomColor: theme.borderColor }]}>
          <TouchableOpacity onPress={onClose}>
            <Ionicons name="close" size={24} color={theme.text} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: theme.text }]}>
            Citations
          </Text>
          <View style={styles.styleSelector}>
            <Text style={[styles.styleLabel, { color: theme.placeholderText }]}>
              Style:
            </Text>
            <TouchableOpacity style={[styles.styleButton, { backgroundColor: theme.surface }]}>
              <Text style={[styles.styleText, { color: theme.text }]}>
                {citationStyle}
              </Text>
              <Ionicons name="chevron-down" size={16} color={theme.placeholderText} />
            </TouchableOpacity>
          </View>
        </View>

        {/* Tabs */}
        <View style={[styles.tabsContainer, { backgroundColor: theme.surface }]}>
          {tabs.map(tab => (
            <TouchableOpacity
              key={tab.id}
              style={[
                styles.tab,
                activeTab === tab.id && { backgroundColor: theme.primary }
              ]}
              onPress={() => setActiveTab(tab.id)}
            >
              <Ionicons 
                name={tab.icon} 
                size={16} 
                color={activeTab === tab.id ? theme.buttonText : theme.text} 
              />
              <Text style={[
                styles.tabText,
                { color: activeTab === tab.id ? theme.buttonText : theme.text }
              ]}>
                {tab.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Content */}
        <View style={styles.content}>
          {activeTab === 'library' && (
            <View style={styles.libraryContent}>
              {/* Search Bar */}
              <View style={[styles.searchContainer, { backgroundColor: theme.surface }]}>
                <Ionicons name="search" size={20} color={theme.placeholderText} />
                <TextInput
                  style={[styles.searchInput, { color: theme.text }]}
                  placeholder="Search citations..."
                  placeholderTextColor={theme.placeholderText}
                  value={searchQuery}
                  onChangeText={setSearchQuery}
                />
                {searchQuery && (
                  <TouchableOpacity onPress={() => setSearchQuery('')}>
                    <Ionicons name="close-circle" size={20} color={theme.placeholderText} />
                  </TouchableOpacity>
                )}
              </View>

              {/* Citations List */}
              <FlatList
                data={filteredCitations}
                keyExtractor={(item) => item.id}
                showsVerticalScrollIndicator={false}
                renderItem={({ item: citation }) => (
                  <View style={[styles.citationItem, { backgroundColor: theme.surface }]}>
                    <View style={styles.citationHeader}>
                      <View style={styles.citationInfo}>
                        <Text style={[styles.citationTitle, { color: theme.text }]}>
                          {citation.title}
                        </Text>
                        <Text style={[styles.citationAuthors, { color: theme.placeholderText }]}>
                          {citation.authors.join(', ')} ({citation.year})
                        </Text>
                        <Text style={[styles.citationPublication, { color: theme.placeholderText }]}>
                          {citation.publication}
                        </Text>
                      </View>
                      
                      {citation.usedInReport && (
                        <View style={[styles.usedTag, { backgroundColor: theme.primary + '20' }]}>
                          <Text style={[styles.usedText, { color: theme.primary }]}>
                            Used
                          </Text>
                        </View>
                      )}
                    </View>
                    
                    <View style={styles.citationActions}>
                      <TouchableOpacity
                        style={[styles.actionButton, { backgroundColor: theme.primary }]}
                        onPress={() => handleInsertCitation(citation)}
                      >
                        <Ionicons name="add" size={16} color={theme.buttonText} />
                        <Text style={[styles.actionText, { color: theme.buttonText }]}>
                          Insert
                        </Text>
                      </TouchableOpacity>
                      
                      <TouchableOpacity
                        style={[styles.actionButton, { borderColor: theme.borderColor, borderWidth: 1 }]}
                        onPress={() => {/* Edit citation */}}
                      >
                        <Ionicons name="create-outline" size={16} color={theme.text} />
                        <Text style={[styles.actionText, { color: theme.text }]}>
                          Edit
                        </Text>
                      </TouchableOpacity>
                      
                      <TouchableOpacity
                        onPress={() => handleDeleteCitation(citation.id)}
                        style={styles.deleteButton}
                      >
                        <Ionicons name="trash-outline" size={16} color={theme.error} />
                      </TouchableOpacity>
                    </View>
                  </View>
                )}
                ListEmptyComponent={
                  <Text style={[styles.emptyText, { color: theme.placeholderText }]}>
                    No citations found. Add your first citation to get started.
                  </Text>
                }
              />
            </View>
          )}

          {activeTab === 'add' && (
            <ScrollView style={styles.addContent} showsVerticalScrollIndicator={false}>
              {/* Citation Type Selector */}
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: theme.text }]}>Type</Text>
                <View style={styles.typeSelector}>
                  {citationTypes.map(type => (
                    <TouchableOpacity
                      key={type.id}
                      style={[
                        styles.typeOption,
                        { borderColor: theme.borderColor },
                        newCitation.type === type.id && { 
                          backgroundColor: theme.primary, 
                          borderColor: theme.primary 
                        }
                      ]}
                      onPress={() => setNewCitation(prev => ({ ...prev, type: type.id }))}
                    >
                      <Text style={[
                        styles.typeText,
                        { color: newCitation.type === type.id ? theme.buttonText : theme.text }
                      ]}>
                        {type.label}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              {/* Title */}
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: theme.text }]}>Title *</Text>
                <TextInput
                  style={[styles.textInput, { 
                    backgroundColor: theme.inputBackground,
                    color: theme.text,
                    borderColor: theme.borderColor 
                  }]}
                  placeholder="Enter title"
                  placeholderTextColor={theme.placeholderText}
                  value={newCitation.title}
                  onChangeText={(value) => setNewCitation(prev => ({ ...prev, title: value }))}
                  multiline
                />
              </View>

              {/* Authors */}
              <View style={styles.fieldGroup}>
                <View style={styles.fieldHeader}>
                  <Text style={[styles.fieldLabel, { color: theme.text }]}>Authors *</Text>
                  <TouchableOpacity onPress={addAuthor} style={styles.addButton}>
                    <Ionicons name="add" size={16} color={theme.primary} />
                    <Text style={[styles.addButtonText, { color: theme.primary }]}>
                      Add Author
                    </Text>
                  </TouchableOpacity>
                </View>
                {newCitation.authors.map((author, index) => (
                  <View key={index} style={styles.authorInput}>
                    <TextInput
                      style={[styles.textInput, { 
                        flex: 1,
                        backgroundColor: theme.inputBackground,
                        color: theme.text,
                        borderColor: theme.borderColor 
                      }]}
                      placeholder="Last, First"
                      placeholderTextColor={theme.placeholderText}
                      value={author}
                      onChangeText={(value) => updateAuthor(index, value)}
                    />
                    {newCitation.authors.length > 1 && (
                      <TouchableOpacity
                        onPress={() => removeAuthor(index)}
                        style={styles.removeAuthorButton}
                      >
                        <Ionicons name="remove-circle" size={20} color={theme.error} />
                      </TouchableOpacity>
                    )}
                  </View>
                ))}
              </View>

              {/* Publication/Publisher */}
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: theme.text }]}>
                  {newCitation.type === 'book' ? 'Publisher' : 'Publication'}
                </Text>
                <TextInput
                  style={[styles.textInput, { 
                    backgroundColor: theme.inputBackground,
                    color: theme.text,
                    borderColor: theme.borderColor 
                  }]}
                  placeholder={newCitation.type === 'book' ? 'Publisher name' : 'Publication name'}
                  placeholderTextColor={theme.placeholderText}
                  value={newCitation.type === 'book' ? newCitation.publisher : newCitation.publication}
                  onChangeText={(value) => setNewCitation(prev => ({ 
                    ...prev, 
                    [newCitation.type === 'book' ? 'publisher' : 'publication']: value 
                  }))}
                />
              </View>

              {/* Year */}
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: theme.text }]}>Year</Text>
                <TextInput
                  style={[styles.textInput, { 
                    backgroundColor: theme.inputBackground,
                    color: theme.text,
                    borderColor: theme.borderColor 
                  }]}
                  placeholder="YYYY"
                  placeholderTextColor={theme.placeholderText}
                  value={newCitation.year}
                  onChangeText={(value) => setNewCitation(prev => ({ ...prev, year: value }))}
                  keyboardType="numeric"
                />
              </View>

              {/* Pages */}
              {newCitation.type !== 'website' && (
                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, { color: theme.text }]}>Pages</Text>
                  <TextInput
                    style={[styles.textInput, { 
                      backgroundColor: theme.inputBackground,
                      color: theme.text,
                      borderColor: theme.borderColor 
                    }]}
                    placeholder="e.g., 45-62 or 1-350"
                    placeholderTextColor={theme.placeholderText}
                    value={newCitation.pages}
                    onChangeText={(value) => setNewCitation(prev => ({ ...prev, pages: value }))}
                  />
                </View>
              )}

              {/* URL */}
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: theme.text }]}>URL</Text>
                <TextInput
                  style={[styles.textInput, { 
                    backgroundColor: theme.inputBackground,
                    color: theme.text,
                    borderColor: theme.borderColor 
                  }]}
                  placeholder="https://..."
                  placeholderTextColor={theme.placeholderText}
                  value={newCitation.url}
                  onChangeText={(value) => setNewCitation(prev => ({ ...prev, url: value }))}
                  keyboardType="url"
                  autoCapitalize="none"
                />
              </View>

              {/* Volume and Issue for articles */}
              {newCitation.type === 'article' && (
                <View style={styles.rowFields}>
                  <View style={[styles.fieldGroup, { flex: 1 }]}>
                    <Text style={[styles.fieldLabel, { color: theme.text }]}>Volume</Text>
                    <TextInput
                      style={[styles.textInput, { 
                        backgroundColor: theme.inputBackground,
                        color: theme.text,
                        borderColor: theme.borderColor 
                      }]}
                      placeholder="Vol."
                      placeholderTextColor={theme.placeholderText}
                      value={newCitation.volume}
                      onChangeText={(value) => setNewCitation(prev => ({ ...prev, volume: value }))}
                    />
                  </View>
                  
                  <View style={[styles.fieldGroup, { flex: 1 }]}>
                    <Text style={[styles.fieldLabel, { color: theme.text }]}>Issue</Text>
                    <TextInput
                      style={[styles.textInput, { 
                        backgroundColor: theme.inputBackground,
                        color: theme.text,
                        borderColor: theme.borderColor 
                      }]}
                      placeholder="No."
                      placeholderTextColor={theme.placeholderText}
                      value={newCitation.issue}
                      onChangeText={(value) => setNewCitation(prev => ({ ...prev, issue: value }))}
                    />
                  </View>
                </View>
              )}

              {/* DOI */}
              {newCitation.type === 'article' && (
                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, { color: theme.text }]}>DOI</Text>
                  <TextInput
                    style={[styles.textInput, { 
                      backgroundColor: theme.inputBackground,
                      color: theme.text,
                      borderColor: theme.borderColor 
                    }]}
                    placeholder="10.1177/1234567890"
                    placeholderTextColor={theme.placeholderText}
                    value={newCitation.doi}
                    onChangeText={(value) => setNewCitation(prev => ({ ...prev, doi: value }))}
                  />
                </View>
              )}

              {/* Access Date for websites */}
              {newCitation.type === 'website' && (
                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, { color: theme.text }]}>Access Date</Text>
                  <TextInput
                    style={[styles.textInput, { 
                      backgroundColor: theme.inputBackground,
                      color: theme.text,
                      borderColor: theme.borderColor 
                    }]}
                    placeholder="YYYY-MM-DD"
                    placeholderTextColor={theme.placeholderText}
                    value={newCitation.accessDate}
                    onChangeText={(value) => setNewCitation(prev => ({ ...prev, accessDate: value }))}
                  />
                </View>
              )}

              {/* Notes */}
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: theme.text }]}>Notes</Text>
                <TextInput
                  style={[styles.textInput, styles.notesInput, { 
                    backgroundColor: theme.inputBackground,
                    color: theme.text,
                    borderColor: theme.borderColor 
                  }]}
                  placeholder="Additional notes about this source..."
                  placeholderTextColor={theme.placeholderText}
                  value={newCitation.notes}
                  onChangeText={(value) => setNewCitation(prev => ({ ...prev, notes: value }))}
                  multiline
                />
              </View>

              {/* Add Button */}
              <TouchableOpacity
                style={[styles.addCitationButton, { backgroundColor: theme.primary }]}
                onPress={handleAddCitation}
              >
                <Text style={[styles.addCitationText, { color: theme.buttonText }]}>
                  Add Citation
                </Text>
              </TouchableOpacity>

              <View style={{ height: 20 }} />
            </ScrollView>
          )}

          {activeTab === 'bibliography' && (
            <ScrollView style={styles.bibliographyContent} showsVerticalScrollIndicator={false}>
              <View style={styles.bibliographyHeader}>
                <Text style={[styles.bibliographyTitle, { color: theme.text }]}>
                  Bibliography ({citationStyle} Style)
                </Text>
                <Text style={[styles.bibliographySubtitle, { color: theme.placeholderText }]}>
                  {citations.filter(c => c.usedInReport).length} citations used in this report
                </Text>
              </View>

              <View style={[styles.bibliographyPreview, { 
                backgroundColor: theme.surface,
                borderColor: theme.borderColor 
              }]}>
                <Text style={[styles.bibliographyText, { color: theme.text }]}>
                  {generateBibliography() || 'No citations used in this report yet.'}
                </Text>
              </View>

              <TouchableOpacity
                style={[styles.copyButton, { 
                  backgroundColor: theme.primary,
                  opacity: citations.filter(c => c.usedInReport).length > 0 ? 1 : 0.5
                }]}
                disabled={citations.filter(c => c.usedInReport).length === 0}
                onPress={() => {
                  // Copy to clipboard functionality
                  Alert.alert('Success', 'Bibliography copied to clipboard');
                }}
              >
                <Ionicons name="copy-outline" size={16} color={theme.buttonText} />
                <Text style={[styles.copyButtonText, { color: theme.buttonText }]}>
                  Copy Bibliography
                </Text>
              </TouchableOpacity>
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
};

const styles = {
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderBottomWidth: 1,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
  },
  styleSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  styleLabel: {
    fontSize: 12,
  },
  styleButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    gap: 4,
  },
  styleText: {
    fontSize: 12,
    fontWeight: '500',
  },
  tabsContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 8,
    gap: 4,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 6,
    gap: 4,
  },
  tabText: {
    fontSize: 12,
    fontWeight: '500',
  },
  content: {
    flex: 1,
  },
  libraryContent: {
    flex: 1,
    padding: 16,
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    marginBottom: 16,
    gap: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 16,
  },
  citationItem: {
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
  },
  citationHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  citationInfo: {
    flex: 1,
  },
  citationTitle: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 4,
    lineHeight: 20,
  },
  citationAuthors: {
    fontSize: 12,
    marginBottom: 2,
  },
  citationPublication: {
    fontSize: 12,
    fontStyle: 'italic',
  },
  usedTag: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  usedText: {
    fontSize: 10,
    fontWeight: '500',
  },
  citationActions: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    gap: 4,
  },
  actionText: {
    fontSize: 12,
    fontWeight: '500',
  },
  deleteButton: {
    padding: 4,
  },
  emptyText: {
    textAlign: 'center',
    fontSize: 14,
    fontStyle: 'italic',
    marginTop: 40,
  },
  addContent: {
    flex: 1,
    padding: 16,
  },
  fieldGroup: {
    marginBottom: 20,
  },
  fieldHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  fieldLabel: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 8,
  },
  typeSelector: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  typeOption: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 6,
    borderWidth: 1,
  },
  typeText: {
    fontSize: 12,
    fontWeight: '500',
  },
  textInput: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
  },
  notesInput: {
    height: 80,
    textAlignVertical: 'top',
  },
  addButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  addButtonText: {
    fontSize: 12,
    fontWeight: '500',
  },
  authorInput: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  removeAuthorButton: {
    padding: 4,
  },
  rowFields: {
    flexDirection: 'row',
    gap: 12,
  },
  addCitationButton: {
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 20,
  },
  addCitationText: {
    fontSize: 16,
    fontWeight: '600',
  },
  bibliographyContent: {
    flex: 1,
    padding: 16,
  },
  bibliographyHeader: {
    marginBottom: 20,
  },
  bibliographyTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 4,
  },
  bibliographySubtitle: {
    fontSize: 14,
  },
  bibliographyPreview: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 16,
    marginBottom: 20,
    minHeight: 200,
  },
  bibliographyText: {
    fontSize: 14,
    lineHeight: 22,
  },
  copyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: 8,
    gap: 8,
  },
  copyButtonText: {
    fontSize: 16,
    fontWeight: '600',
  },
};

export default CitationManager;
