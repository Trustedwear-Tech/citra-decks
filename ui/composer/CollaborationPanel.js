// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

// CollaborationPanel.js - Advanced collaboration features for reports
import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  TextInput,
  Modal,
  Alert,
  Switch
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const CollaborationPanel = ({
  visible,
  onClose,
  reportId,
  currentUser,
  theme,
  apiConfig,
  userDeviceId,
  collaborators: propCollaborators // Rename to avoid conflict with state
}) => {
  // Use prop if provided
  const props = { collaborators: propCollaborators };
  const [activeTab, setActiveTab] = useState('collaborators'); // 'collaborators', 'comments', 'versions'
  const [collaborators, setCollaborators] = useState([]);
  const [comments, setComments] = useState([]);
  const [versions, setVersions] = useState([]);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('editor'); // 'viewer', 'editor', 'admin'
  const [newComment, setNewComment] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Load collaboration data
  useEffect(() => {
    if (visible && reportId) {
      loadCollaborationData();
    }
  }, [visible, reportId]);

  const loadCollaborationData = async () => {
    try {
      setIsLoading(true);
      await Promise.all([
        loadCollaborators(),
        loadComments(),
        loadVersions()
      ]);
    } catch (error) {
      console.error('Error loading collaboration data:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // Update collaborators from prop
  useEffect(() => {
    if (visible) {
      // If we have real-time collaborators from Yjs, use them
      if (props.collaborators) {
        // Map Yjs awareness users to UI format
        // Awareness user shape: { name, email, color, avatar }
        // UI shape: { id, name, email, role, status, lastSeen, avatar }
        const realCollaborators = props.collaborators.map((u, i) => ({
          id: u.email || `user-${i}`,
          name: u.name || 'Anonymous',
          email: u.email,
          role: 'editor', // Default role for now
          status: 'active',
          lastSeen: new Date().toISOString(),
          avatar: u.avatar,
          color: u.color
        }));

        // Merge with existing/mock to show 'self' if needed, or just replace
        // For now, let's just replace the list with real ones + maybe 'self' if not included?
        // Actually Yjs awareness usually includes self.
        setCollaborators(realCollaborators);
      } else {
        loadCollaborators();
      }
    }
  }, [visible, props.collaborators]);

  const loadCollaborators = async () => {
    // Mock collaborators data - fallback
    const mockCollaborators = [
      {
        id: '1',
        name: 'Sarah Johnson',
        email: 'sarah.johnson@company.com',
        role: 'admin',
        status: 'active',
        lastSeen: new Date().toISOString(),
        avatar: null
      },
      {
        id: '2',
        name: 'Mike Chen',
        email: 'mike.chen@company.com',
        role: 'editor',
        status: 'active',
        lastSeen: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
        avatar: null
      },
      {
        id: '3',
        name: 'Emma Davis',
        email: 'emma.davis@company.com',
        role: 'viewer',
        status: 'pending',
        lastSeen: null,
        avatar: null
      }
    ];
    setCollaborators(mockCollaborators);
  };

  const loadComments = async () => {
    // Mock comments data - replace with actual API call
    const mockComments = [
      {
        id: '1',
        author: 'Sarah Johnson',
        content: 'The financial analysis section needs more detailed breakdown of revenue streams.',
        pageId: 'page-2',
        timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
        resolved: false,
        replies: [
          {
            id: '1-1',
            author: 'Mike Chen',
            content: 'I agree. I can add the Q3 revenue breakdown charts.',
            timestamp: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString()
          }
        ]
      },
      {
        id: '2',
        author: 'Emma Davis',
        content: 'Great work on the market analysis! Very comprehensive.',
        pageId: 'page-3',
        timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
        resolved: false,
        replies: []
      }
    ];
    setComments(mockComments);
  };

  const loadVersions = async () => {
    // Mock version history - replace with actual API call
    const mockVersions = [
      {
        id: 'v1.3',
        name: 'Final Review Draft',
        author: 'Sarah Johnson',
        timestamp: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
        changes: 'Updated financial projections and market analysis',
        isCurrent: true
      },
      {
        id: 'v1.2',
        name: 'Market Analysis Update',
        author: 'Mike Chen',
        timestamp: new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString(),
        changes: 'Added competitive landscape analysis',
        isCurrent: false
      },
      {
        id: 'v1.1',
        name: 'Initial Draft Complete',
        author: 'Sarah Johnson',
        timestamp: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
        changes: 'Completed all sections of initial draft',
        isCurrent: false
      }
    ];
    setVersions(mockVersions);
  };

  const handleInviteCollaborator = async () => {
    if (!inviteEmail.trim()) {
      Alert.alert('Error', 'Please enter an email address');
      return;
    }

    try {
      // Mock API call - replace with actual implementation
      const newCollaborator = {
        id: Date.now().toString(),
        name: inviteEmail.split('@')[0],
        email: inviteEmail,
        role: inviteRole,
        status: 'pending',
        lastSeen: null,
        avatar: null
      };

      setCollaborators(prev => [...prev, newCollaborator]);
      setInviteEmail('');
      setShowInviteModal(false);
      Alert.alert('Success', `Invitation sent to ${inviteEmail}`);
    } catch (error) {
      console.error('Error inviting collaborator:', error);
      Alert.alert('Error', 'Failed to send invitation. Please try again.');
    }
  };

  const handleAddComment = async () => {
    if (!newComment.trim()) return;

    try {
      const comment = {
        id: Date.now().toString(),
        author: currentUser?.name || 'You',
        content: newComment,
        pageId: 'current-page',
        timestamp: new Date().toISOString(),
        resolved: false,
        replies: []
      };

      setComments(prev => [comment, ...prev]);
      setNewComment('');
    } catch (error) {
      console.error('Error adding comment:', error);
      Alert.alert('Error', 'Failed to add comment. Please try again.');
    }
  };

  const handleRoleChange = (collaboratorId, newRole) => {
    setCollaborators(prev =>
      prev.map(collab =>
        collab.id === collaboratorId ? { ...collab, role: newRole } : collab
      )
    );
  };

  const handleRemoveCollaborator = (collaboratorId) => {
    Alert.alert(
      'Remove Collaborator',
      'Are you sure you want to remove this collaborator?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: () => {
            setCollaborators(prev => prev.filter(c => c.id !== collaboratorId));
          }
        }
      ]
    );
  };

  const formatTimeAgo = (timestamp) => {
    if (!timestamp) return 'Never';

    const now = new Date();
    const time = new Date(timestamp);
    const diffInMinutes = Math.floor((now - time) / (1000 * 60));

    if (diffInMinutes < 1) return 'Just now';
    if (diffInMinutes < 60) return `${diffInMinutes}m ago`;
    if (diffInMinutes < 1440) return `${Math.floor(diffInMinutes / 60)}h ago`;
    return `${Math.floor(diffInMinutes / 1440)}d ago`;
  };

  const getRoleColor = (role) => {
    const colors = {
      admin: '#EF4444',
      editor: '#10B981',
      viewer: '#6B7280'
    };
    return colors[role] || theme.placeholderText;
  };

  const tabs = [
    { id: 'collaborators', label: 'Members', icon: 'people-outline' },
    { id: 'comments', label: 'Comments', icon: 'chatbubble-outline' },
    { id: 'versions', label: 'Versions', icon: 'git-branch-outline' }
  ];

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
            Collaboration
          </Text>
          <TouchableOpacity
            onPress={() => setShowInviteModal(true)}
            disabled={activeTab !== 'collaborators'}
          >
            <Ionicons
              name="person-add"
              size={24}
              color={activeTab === 'collaborators' ? theme.primary : theme.placeholderText}
            />
          </TouchableOpacity>
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
        <ScrollView style={styles.content}>
          {activeTab === 'collaborators' && (
            <View style={styles.collaboratorsContent}>
              {collaborators.map((collaborator) => (
                <View
                  key={collaborator.id}
                  style={[styles.collaboratorItem, { backgroundColor: theme.surface }]}
                >
                  <View style={styles.collaboratorInfo}>
                    <View style={[styles.avatar, { backgroundColor: theme.primary }]}>
                      <Text style={[styles.avatarText, { color: theme.buttonText }]}>
                        {collaborator.name.charAt(0).toUpperCase()}
                      </Text>
                    </View>
                    <View style={styles.collaboratorDetails}>
                      <Text style={[styles.collaboratorName, { color: theme.text }]}>
                        {collaborator.name}
                      </Text>
                      <Text style={[styles.collaboratorEmail, { color: theme.placeholderText }]}>
                        {collaborator.email}
                      </Text>
                      <Text style={[styles.lastSeen, { color: theme.placeholderText }]}>
                        Last seen: {formatTimeAgo(collaborator.lastSeen)}
                      </Text>
                    </View>
                  </View>

                  <View style={styles.collaboratorActions}>
                    <View style={[styles.roleTag, { backgroundColor: getRoleColor(collaborator.role) + '20' }]}>
                      <Text style={[styles.roleText, { color: getRoleColor(collaborator.role) }]}>
                        {collaborator.role}
                      </Text>
                    </View>

                    {collaborator.status === 'pending' && (
                      <View style={[styles.statusTag, { backgroundColor: theme.warning + '20' }]}>
                        <Text style={[styles.statusText, { color: theme.warning }]}>
                          Pending
                        </Text>
                      </View>
                    )}

                    <TouchableOpacity
                      onPress={() => handleRemoveCollaborator(collaborator.id)}
                      style={styles.removeButton}
                    >
                      <Ionicons name="ellipsis-horizontal" size={16} color={theme.placeholderText} />
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </View>
          )}

          {activeTab === 'comments' && (
            <View style={styles.commentsContent}>
              {/* Add Comment Input */}
              <View style={[styles.commentInput, { backgroundColor: theme.surface }]}>
                <TextInput
                  style={[styles.commentTextInput, {
                    backgroundColor: theme.inputBackground,
                    color: theme.text,
                    borderColor: theme.borderColor
                  }]}
                  placeholder="Add a comment..."
                  placeholderTextColor={theme.placeholderText}
                  value={newComment}
                  onChangeText={setNewComment}
                  multiline
                />
                <TouchableOpacity
                  style={[styles.commentSubmit, {
                    backgroundColor: newComment.trim() ? theme.primary : theme.borderColor
                  }]}
                  onPress={handleAddComment}
                  disabled={!newComment.trim()}
                >
                  <Ionicons
                    name="send"
                    size={16}
                    color={newComment.trim() ? theme.buttonText : theme.placeholderText}
                  />
                </TouchableOpacity>
              </View>

              {/* Comments List */}
              {comments.map((comment) => (
                <View
                  key={comment.id}
                  style={[styles.commentItem, { backgroundColor: theme.surface }]}
                >
                  <View style={styles.commentHeader}>
                    <Text style={[styles.commentAuthor, { color: theme.text }]}>
                      {comment.author}
                    </Text>
                    <Text style={[styles.commentTime, { color: theme.placeholderText }]}>
                      {formatTimeAgo(comment.timestamp)}
                    </Text>
                  </View>

                  <Text style={[styles.commentContent, { color: theme.text }]}>
                    {comment.content}
                  </Text>

                  {comment.replies.length > 0 && (
                    <View style={styles.replies}>
                      {comment.replies.map((reply) => (
                        <View key={reply.id} style={styles.replyItem}>
                          <Text style={[styles.replyAuthor, { color: theme.placeholderText }]}>
                            {reply.author}
                          </Text>
                          <Text style={[styles.replyContent, { color: theme.text }]}>
                            {reply.content}
                          </Text>
                        </View>
                      ))}
                    </View>
                  )}

                  <View style={styles.commentActions}>
                    <TouchableOpacity style={styles.commentAction}>
                      <Ionicons name="chatbubble-outline" size={14} color={theme.placeholderText} />
                      <Text style={[styles.commentActionText, { color: theme.placeholderText }]}>
                        Reply
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity style={styles.commentAction}>
                      <Ionicons name="checkmark-circle-outline" size={14} color={theme.placeholderText} />
                      <Text style={[styles.commentActionText, { color: theme.placeholderText }]}>
                        Resolve
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </View>
          )}

          {activeTab === 'versions' && (
            <View style={styles.versionsContent}>
              {versions.map((version) => (
                <View
                  key={version.id}
                  style={[styles.versionItem, { backgroundColor: theme.surface }]}
                >
                  <View style={styles.versionHeader}>
                    <View style={styles.versionInfo}>
                      <Text style={[styles.versionName, { color: theme.text }]}>
                        {version.name}
                        {version.isCurrent && (
                          <Text style={[styles.currentTag, { color: theme.primary }]}>
                            {' '}(Current)
                          </Text>
                        )}
                      </Text>
                      <Text style={[styles.versionAuthor, { color: theme.placeholderText }]}>
                        By {version.author} • {formatTimeAgo(version.timestamp)}
                      </Text>
                    </View>

                    {!version.isCurrent && (
                      <TouchableOpacity style={[styles.restoreButton, { borderColor: theme.borderColor }]}>
                        <Text style={[styles.restoreText, { color: theme.text }]}>
                          Restore
                        </Text>
                      </TouchableOpacity>
                    )}
                  </View>

                  <Text style={[styles.versionChanges, { color: theme.placeholderText }]}>
                    {version.changes}
                  </Text>
                </View>
              ))}
            </View>
          )}
        </ScrollView>

        {/* Invite Modal */}
        <Modal
          visible={showInviteModal}
          animationType="fade"
          transparent={true}
        >
          <View style={styles.overlay}>
            <View style={[styles.inviteModal, { backgroundColor: theme.surface }]}>
              <Text style={[styles.inviteTitle, { color: theme.text }]}>
                Invite Collaborator
              </Text>

              <TextInput
                style={[styles.inviteInput, {
                  backgroundColor: theme.inputBackground,
                  color: theme.text,
                  borderColor: theme.borderColor
                }]}
                placeholder="Email address"
                placeholderTextColor={theme.placeholderText}
                value={inviteEmail}
                onChangeText={setInviteEmail}
                keyboardType="email-address"
                autoCapitalize="none"
              />

              <View style={styles.roleSelector}>
                <Text style={[styles.roleLabel, { color: theme.text }]}>Role:</Text>
                {['viewer', 'editor', 'admin'].map((role) => (
                  <TouchableOpacity
                    key={role}
                    style={[
                      styles.roleOption,
                      inviteRole === role && { backgroundColor: theme.primary + '20' }
                    ]}
                    onPress={() => setInviteRole(role)}
                  >
                    <Text style={[
                      styles.roleOptionText,
                      { color: inviteRole === role ? theme.primary : theme.text }
                    ]}>
                      {role.charAt(0).toUpperCase() + role.slice(1)}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={styles.inviteActions}>
                <TouchableOpacity
                  style={[styles.inviteButton, { borderColor: theme.borderColor }]}
                  onPress={() => {
                    setShowInviteModal(false);
                    setInviteEmail('');
                  }}
                >
                  <Text style={[styles.inviteButtonText, { color: theme.text }]}>Cancel</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.inviteButton, styles.primaryInviteButton, { backgroundColor: theme.primary }]}
                  onPress={handleInviteCollaborator}
                >
                  <Text style={[styles.inviteButtonText, { color: theme.buttonText }]}>
                    Send Invite
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
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
    padding: 16,
  },
  collaboratorsContent: {
    gap: 12,
  },
  collaboratorItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
  },
  collaboratorInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 12,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    fontSize: 16,
    fontWeight: '600',
  },
  collaboratorDetails: {
    flex: 1,
  },
  collaboratorName: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 2,
  },
  collaboratorEmail: {
    fontSize: 12,
    marginBottom: 2,
  },
  lastSeen: {
    fontSize: 11,
  },
  collaboratorActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  roleTag: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  roleText: {
    fontSize: 11,
    fontWeight: '500',
  },
  statusTag: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 8,
  },
  statusText: {
    fontSize: 10,
    fontWeight: '500',
  },
  removeButton: {
    padding: 4,
  },
  commentsContent: {
    gap: 16,
  },
  commentInput: {
    flexDirection: 'row',
    padding: 12,
    borderRadius: 12,
    gap: 8,
    alignItems: 'flex-end',
  },
  commentTextInput: {
    flex: 1,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    maxHeight: 80,
    fontSize: 14,
  },
  commentSubmit: {
    width: 36,
    height: 36,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  commentItem: {
    padding: 16,
    borderRadius: 12,
  },
  commentHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  commentAuthor: {
    fontSize: 14,
    fontWeight: '500',
  },
  commentTime: {
    fontSize: 12,
  },
  commentContent: {
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 12,
  },
  replies: {
    marginLeft: 16,
    paddingLeft: 16,
    borderLeftWidth: 2,
    borderLeftColor: 'rgba(0,0,0,0.1)',
    marginBottom: 12,
  },
  replyItem: {
    marginBottom: 8,
  },
  replyAuthor: {
    fontSize: 12,
    fontWeight: '500',
    marginBottom: 2,
  },
  replyContent: {
    fontSize: 13,
    lineHeight: 18,
  },
  commentActions: {
    flexDirection: 'row',
    gap: 16,
  },
  commentAction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  commentActionText: {
    fontSize: 12,
  },
  versionsContent: {
    gap: 12,
  },
  versionItem: {
    padding: 16,
    borderRadius: 12,
  },
  versionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  versionInfo: {
    flex: 1,
  },
  versionName: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 4,
  },
  currentTag: {
    fontSize: 12,
    fontWeight: '600',
  },
  versionAuthor: {
    fontSize: 12,
  },
  restoreButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
  },
  restoreText: {
    fontSize: 12,
    fontWeight: '500',
  },
  versionChanges: {
    fontSize: 13,
    lineHeight: 18,
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  inviteModal: {
    width: '90%',
    maxWidth: 400,
    padding: 24,
    borderRadius: 16,
    margin: 20,
  },
  inviteTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 20,
    textAlign: 'center',
  },
  inviteInput: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 16,
    marginBottom: 20,
  },
  roleSelector: {
    marginBottom: 24,
  },
  roleLabel: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 8,
  },
  roleOption: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 6,
    marginBottom: 4,
  },
  roleOptionText: {
    fontSize: 14,
  },
  inviteActions: {
    flexDirection: 'row',
    gap: 12,
  },
  inviteButton: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
    borderWidth: 1,
  },
  primaryInviteButton: {
    borderWidth: 0,
  },
  inviteButtonText: {
    fontSize: 16,
    fontWeight: '500',
  },
};

export default CollaborationPanel;
