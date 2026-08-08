/**
 * ReportHeaderFooterModal.js - Configure document-wide headers and footers
 * 
 * Features:
 * - Enable/disable headers and footers
 * - Configure left/center/right content for each
 * - Support placeholders: {date}, {page}, {total}, {title}, {author}
 * - Option to show/hide on first page
 * - Logo upload for header
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  Modal,
  Switch,
  Image,
} from 'react-native';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';

// Placeholder options
const PLACEHOLDERS = [
  { id: '{date}', label: 'Date', icon: 'event', description: 'Current date' },
  { id: '{page}', label: 'Page #', icon: 'looks-one', description: 'Current page number' },
  { id: '{total}', label: 'Total Pages', icon: 'format-list-numbered', description: 'Total page count' },
  { id: '{title}', label: 'Title', icon: 'title', description: 'Report title' },
  { id: '{author}', label: 'Author', icon: 'person', description: 'Author name' },
];

// MODULE-LEVEL on purpose: defining this inside the modal recreated the
// component type on every keystroke, which remounted the TextInput and dropped
// focus — the "can only type one character at a time" bug.
const InputRow = ({ label, value, setValue, inputId, placeholder, activeInput, setActiveInput, safeTheme }) => (
  <View style={styles.inputRow}>
    <Text style={[styles.inputLabel, { color: safeTheme.textSecondary }]}>{label}</Text>
    <TextInput
      style={[
        styles.input,
        {
          color: safeTheme.text,
          borderColor: activeInput === inputId ? safeTheme.primary : safeTheme.border,
          backgroundColor: safeTheme.surface,
        },
      ]}
      value={value}
      onChangeText={setValue}
      onFocus={() => setActiveInput(inputId)}
      onBlur={() => setActiveInput(null)}
      placeholder={placeholder}
      placeholderTextColor={safeTheme.textSecondary + '80'}
    />
  </View>
);

const ReportHeaderFooterModal = ({
  visible,
  onClose,
  onSave,
  headerConfig = {},
  footerConfig = {},
  letterheadConfig = {},
  reportMetadata = {},
  theme,
}) => {
  // Letterhead state — company identity block at the top of the document
  const [lhEnabled, setLhEnabled] = useState(letterheadConfig.enabled ?? false);
  const [lhCompanyName, setLhCompanyName] = useState(letterheadConfig.companyName || '');
  const [lhAddress, setLhAddress] = useState(letterheadConfig.address || '');
  const [lhPhone, setLhPhone] = useState(letterheadConfig.phone || '');
  const [lhEmail, setLhEmail] = useState(letterheadConfig.email || '');
  const [lhWebsite, setLhWebsite] = useState(letterheadConfig.website || '');
  const [lhLogoUrl, setLhLogoUrl] = useState(letterheadConfig.logoUrl || '');
  const [lhShowRule, setLhShowRule] = useState(letterheadConfig.showRule ?? true);
  const [lhAllPages, setLhAllPages] = useState(letterheadConfig.allPages ?? false);

  // Header state
  const [headerEnabled, setHeaderEnabled] = useState(headerConfig.enabled ?? false);
  const [headerLeft, setHeaderLeft] = useState(headerConfig.leftContent || '');
  const [headerCenter, setHeaderCenter] = useState(headerConfig.centerContent || '');
  const [headerRight, setHeaderRight] = useState(headerConfig.rightContent || '');
  const [headerShowOnFirst, setHeaderShowOnFirst] = useState(headerConfig.showOnFirstPage ?? false);
  const [headerShowLogo, setHeaderShowLogo] = useState(headerConfig.showLogo ?? false);
  const [headerLogoUrl, setHeaderLogoUrl] = useState(headerConfig.logoUrl || '');

  // Footer state
  const [footerEnabled, setFooterEnabled] = useState(footerConfig.enabled ?? true);
  const [footerLeft, setFooterLeft] = useState(footerConfig.leftContent || '');
  const [footerCenter, setFooterCenter] = useState(footerConfig.centerContent || '');
  const [footerRight, setFooterRight] = useState(footerConfig.rightContent || 'Page {page} of {total}');
  const [footerShowOnFirst, setFooterShowOnFirst] = useState(footerConfig.showOnFirstPage ?? true);

  // Active input for placeholder insertion
  const [activeInput, setActiveInput] = useState(null);

  const safeTheme = theme || {
    background: '#FFFFFF',
    surface: '#F9FAFB',
    text: '#1F2937',
    textSecondary: '#6B7280',
    primary: '#3B82F6',
    border: '#E5E7EB',
  };

  // Reset state when modal opens
  useEffect(() => {
    if (visible) {
      setLhEnabled(letterheadConfig.enabled ?? false);
      setLhCompanyName(letterheadConfig.companyName || '');
      setLhAddress(letterheadConfig.address || '');
      setLhPhone(letterheadConfig.phone || '');
      setLhEmail(letterheadConfig.email || '');
      setLhWebsite(letterheadConfig.website || '');
      setLhLogoUrl(letterheadConfig.logoUrl || '');
      setLhShowRule(letterheadConfig.showRule ?? true);
      setLhAllPages(letterheadConfig.allPages ?? false);

      setHeaderEnabled(headerConfig.enabled ?? false);
      setHeaderLeft(headerConfig.leftContent || '');
      setHeaderCenter(headerConfig.centerContent || '');
      setHeaderRight(headerConfig.rightContent || '');
      setHeaderShowOnFirst(headerConfig.showOnFirstPage ?? false);
      setHeaderShowLogo(headerConfig.showLogo ?? false);
      setHeaderLogoUrl(headerConfig.logoUrl || '');
      
      setFooterEnabled(footerConfig.enabled ?? true);
      setFooterLeft(footerConfig.leftContent || '');
      setFooterCenter(footerConfig.centerContent || '');
      setFooterRight(footerConfig.rightContent || 'Page {page} of {total}');
      setFooterShowOnFirst(footerConfig.showOnFirstPage ?? true);
    }
  }, [visible, headerConfig, footerConfig]);

  // Insert placeholder at cursor
  const insertPlaceholder = (placeholder) => {
    if (!activeInput) return;

    const setterMap = {
      headerLeft: setHeaderLeft,
      headerCenter: setHeaderCenter,
      headerRight: setHeaderRight,
      footerLeft: setFooterLeft,
      footerCenter: setFooterCenter,
      footerRight: setFooterRight,
    };

    const valueMap = {
      headerLeft,
      headerCenter,
      headerRight,
      footerLeft,
      footerCenter,
      footerRight,
    };

    const setter = setterMap[activeInput];
    const currentValue = valueMap[activeInput];
    
    if (setter) {
      setter(currentValue + placeholder);
    }
  };

  // Handle save
  const handleSave = () => {
    onSave({
      letterhead: {
        enabled: lhEnabled,
        companyName: lhCompanyName,
        address: lhAddress,
        phone: lhPhone,
        email: lhEmail,
        website: lhWebsite,
        logoUrl: lhLogoUrl,
        showRule: lhShowRule,
        allPages: lhAllPages,
      },
      header: {
        enabled: headerEnabled,
        leftContent: headerLeft,
        centerContent: headerCenter,
        rightContent: headerRight,
        showOnFirstPage: headerShowOnFirst,
        showLogo: headerShowLogo,
        logoUrl: headerLogoUrl,
      },
      footer: {
        enabled: footerEnabled,
        leftContent: footerLeft,
        centerContent: footerCenter,
        rightContent: footerRight,
        showOnFirstPage: footerShowOnFirst,
      },
    });
    onClose();
  };

  // Preview renderer
  const renderPreview = (position, left, center, right, showLogo = false, logoUrl = '') => {
    const resolveValue = (text) => {
      return text
        .replace('{date}', new Date().toLocaleDateString())
        .replace('{page}', '1')
        .replace('{total}', '10')
        .replace('{title}', reportMetadata.title || 'Report Title')
        .replace('{author}', 'Author Name');
    };

    return (
      <View style={[styles.previewBar, { backgroundColor: safeTheme.surface, borderColor: safeTheme.border }]}>
        <View style={styles.previewSection}>
          {showLogo && logoUrl ? (
            <Image source={{ uri: logoUrl }} style={styles.previewLogo} />
          ) : null}
          <Text style={[styles.previewText, { color: safeTheme.textSecondary }]}>
            {resolveValue(left)}
          </Text>
        </View>
        <View style={[styles.previewSection, styles.previewCenter]}>
          <Text style={[styles.previewText, { color: safeTheme.textSecondary }]}>
            {resolveValue(center)}
          </Text>
        </View>
        <View style={[styles.previewSection, styles.previewRight]}>
          <Text style={[styles.previewText, { color: safeTheme.textSecondary }]}>
            {resolveValue(right)}
          </Text>
        </View>
      </View>
    );
  };

  // Shared props for the module-level InputRow (see definition above).
  const inputRowProps = { activeInput, setActiveInput, safeTheme };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.modalContainer, { backgroundColor: safeTheme.background }]}>
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: safeTheme.border }]}>
            <View style={styles.headerLeft}>
              <MaterialIcons name="view-headline" size={24} color={safeTheme.primary} />
              <Text style={[styles.title, { color: safeTheme.text }]}>Letterhead, Headers & Footers</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Ionicons name="close" size={24} color={safeTheme.text} />
            </TouchableOpacity>
          </View>

          {/* Body */}
          <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent}>
            {/* Placeholders Help */}
            <View style={[styles.placeholdersSection, { backgroundColor: safeTheme.primary + '08', borderColor: safeTheme.primary + '20' }]}>
              <Text style={[styles.placeholdersTitle, { color: safeTheme.primary }]}>
                <MaterialIcons name="help-outline" size={14} /> Available Placeholders
              </Text>
              <View style={styles.placeholdersList}>
                {PLACEHOLDERS.map((p) => (
                  <TouchableOpacity
                    key={p.id}
                    style={[styles.placeholderChip, { backgroundColor: safeTheme.background, borderColor: safeTheme.border }]}
                    onPress={() => insertPlaceholder(p.id)}
                  >
                    <MaterialIcons name={p.icon} size={14} color={safeTheme.textSecondary} />
                    <Text style={[styles.placeholderChipText, { color: safeTheme.text }]}>{p.id}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={[styles.placeholdersHint, { color: safeTheme.textSecondary }]}>
                Click a placeholder to insert it into the focused field
              </Text>
            </View>

            {/* Letterhead Section */}
            <View style={[styles.section, { borderColor: safeTheme.border }]}>
              <View style={styles.sectionHeader}>
                <View style={styles.sectionTitleRow}>
                  <MaterialIcons name="business" size={20} color={safeTheme.text} />
                  <Text style={[styles.sectionTitle, { color: safeTheme.text }]}>Letterhead</Text>
                </View>
                <Switch
                  value={lhEnabled}
                  onValueChange={setLhEnabled}
                  trackColor={{ false: '#E5E7EB', true: safeTheme.primary + '50' }}
                  thumbColor={lhEnabled ? safeTheme.primary : '#f4f3f4'}
                />
              </View>

              {lhEnabled && (
                <View style={styles.sectionBody}>
                  {/* Live preview — classic letterhead: logo left, identity right */}
                  <Text style={[styles.previewLabel, { color: safeTheme.textSecondary }]}>Preview:</Text>
                  <View style={[styles.lhPreview, { backgroundColor: safeTheme.surface, borderColor: safeTheme.border }]}>
                    {lhLogoUrl ? <Image source={{ uri: lhLogoUrl }} style={styles.lhPreviewLogo} resizeMode="contain" /> : <View style={styles.lhPreviewLogo} />}
                    <View style={styles.lhPreviewIdentity}>
                      <Text style={[styles.lhPreviewName, { color: safeTheme.text }]} numberOfLines={1}>{lhCompanyName || 'Company Name'}</Text>
                      {!!lhAddress && <Text style={[styles.previewText, { color: safeTheme.textSecondary }]} numberOfLines={2}>{lhAddress}</Text>}
                      <Text style={[styles.previewText, { color: safeTheme.textSecondary }]} numberOfLines={1}>
                        {[lhPhone, lhEmail, lhWebsite].filter(Boolean).join('  •  ')}
                      </Text>
                    </View>
                  </View>
                  {lhShowRule && <View style={[styles.lhRule, { backgroundColor: safeTheme.primary }]} />}

                  <View style={styles.inputsGrid}>
                    <InputRow {...inputRowProps} label="Company Name" value={lhCompanyName} setValue={setLhCompanyName} inputId="lhCompanyName" placeholder="e.g., Trustedwear Tech Pvt Ltd" />
                    <InputRow {...inputRowProps} label="Logo URL" value={lhLogoUrl} setValue={setLhLogoUrl} inputId="lhLogoUrl" placeholder="https://…/logo.png" />
                  </View>
                  <View style={styles.inputRow}>
                    <Text style={[styles.inputLabel, { color: safeTheme.textSecondary }]}>Address</Text>
                    <TextInput
                      style={[styles.input, { color: safeTheme.text, borderColor: safeTheme.border, backgroundColor: safeTheme.surface, minHeight: 56 }]}
                      value={lhAddress}
                      onChangeText={setLhAddress}
                      placeholder={'4th Floor, MG Road\nBengaluru 560001, India'}
                      placeholderTextColor={safeTheme.textSecondary + '80'}
                      multiline
                    />
                  </View>
                  <View style={styles.inputsGrid}>
                    <InputRow {...inputRowProps} label="Phone" value={lhPhone} setValue={setLhPhone} inputId="lhPhone" placeholder="+91 …" />
                    <InputRow {...inputRowProps} label="Email" value={lhEmail} setValue={setLhEmail} inputId="lhEmail" placeholder="hello@company.com" />
                    <InputRow {...inputRowProps} label="Website" value={lhWebsite} setValue={setLhWebsite} inputId="lhWebsite" placeholder="company.com" />
                  </View>

                  <View style={styles.optionsRow}>
                    <TouchableOpacity
                      style={[styles.optionChip, lhShowRule && { backgroundColor: safeTheme.primary + '15' }]}
                      onPress={() => setLhShowRule(!lhShowRule)}
                    >
                      <Ionicons name={lhShowRule ? 'checkbox' : 'square-outline'} size={16} color={lhShowRule ? safeTheme.primary : safeTheme.textSecondary} />
                      <Text style={[styles.optionText, { color: lhShowRule ? safeTheme.primary : safeTheme.textSecondary }]}>Divider rule below</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.optionChip, lhAllPages && { backgroundColor: safeTheme.primary + '15' }]}
                      onPress={() => setLhAllPages(!lhAllPages)}
                    >
                      <Ionicons name={lhAllPages ? 'checkbox' : 'square-outline'} size={16} color={lhAllPages ? safeTheme.primary : safeTheme.textSecondary} />
                      <Text style={[styles.optionText, { color: lhAllPages ? safeTheme.primary : safeTheme.textSecondary }]}>Show on all pages (default: first page only)</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              )}
            </View>

            {/* Header Section */}
            <View style={[styles.section, { borderColor: safeTheme.border }]}>
              <View style={styles.sectionHeader}>
                <View style={styles.sectionTitleRow}>
                  <MaterialIcons name="vertical-align-top" size={20} color={safeTheme.text} />
                  <Text style={[styles.sectionTitle, { color: safeTheme.text }]}>Header</Text>
                </View>
                <Switch
                  value={headerEnabled}
                  onValueChange={setHeaderEnabled}
                  trackColor={{ false: '#E5E7EB', true: safeTheme.primary + '50' }}
                  thumbColor={headerEnabled ? safeTheme.primary : '#f4f3f4'}
                />
              </View>

              {headerEnabled && (
                <View style={styles.sectionBody}>
                  {/* Preview */}
                  <Text style={[styles.previewLabel, { color: safeTheme.textSecondary }]}>Preview:</Text>
                  {renderPreview('header', headerLeft, headerCenter, headerRight, headerShowLogo, headerLogoUrl)}

                  {/* Inputs */}
                  <View style={styles.inputsGrid}>
                    <InputRow {...inputRowProps}
                      label="Left"
                      value={headerLeft}
                      setValue={setHeaderLeft}
                      inputId="headerLeft"
                      placeholder="e.g., Company Name"
                    />
                    <InputRow {...inputRowProps}
                      label="Center"
                      value={headerCenter}
                      setValue={setHeaderCenter}
                      inputId="headerCenter"
                      placeholder="e.g., {title}"
                    />
                    <InputRow {...inputRowProps}
                      label="Right"
                      value={headerRight}
                      setValue={setHeaderRight}
                      inputId="headerRight"
                      placeholder="e.g., {date}"
                    />
                  </View>

                  {/* Options */}
                  <View style={styles.optionsRow}>
                    <TouchableOpacity
                      style={[styles.optionChip, headerShowOnFirst && { backgroundColor: safeTheme.primary + '15' }]}
                      onPress={() => setHeaderShowOnFirst(!headerShowOnFirst)}
                    >
                      <Ionicons
                        name={headerShowOnFirst ? 'checkbox' : 'square-outline'}
                        size={16}
                        color={headerShowOnFirst ? safeTheme.primary : safeTheme.textSecondary}
                      />
                      <Text style={[styles.optionText, { color: headerShowOnFirst ? safeTheme.primary : safeTheme.textSecondary }]}>
                        Show on first page
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.optionChip, headerShowLogo && { backgroundColor: safeTheme.primary + '15' }]}
                      onPress={() => setHeaderShowLogo(!headerShowLogo)}
                    >
                      <Ionicons
                        name={headerShowLogo ? 'checkbox' : 'square-outline'}
                        size={16}
                        color={headerShowLogo ? safeTheme.primary : safeTheme.textSecondary}
                      />
                      <Text style={[styles.optionText, { color: headerShowLogo ? safeTheme.primary : safeTheme.textSecondary }]}>
                        Include logo
                      </Text>
                    </TouchableOpacity>
                  </View>

                  {/* Logo URL Input */}
                  {headerShowLogo && (
                    <View style={styles.logoInputRow}>
                      <Text style={[styles.inputLabel, { color: safeTheme.textSecondary }]}>Logo URL</Text>
                      <TextInput
                        style={[
                          styles.input,
                          styles.logoInput,
                          { color: safeTheme.text, borderColor: safeTheme.border, backgroundColor: safeTheme.surface },
                        ]}
                        value={headerLogoUrl}
                        onChangeText={setHeaderLogoUrl}
                        placeholder="https://example.com/logo.png"
                        placeholderTextColor={safeTheme.textSecondary + '80'}
                      />
                    </View>
                  )}
                </View>
              )}
            </View>

            {/* Footer Section */}
            <View style={[styles.section, { borderColor: safeTheme.border }]}>
              <View style={styles.sectionHeader}>
                <View style={styles.sectionTitleRow}>
                  <MaterialIcons name="vertical-align-bottom" size={20} color={safeTheme.text} />
                  <Text style={[styles.sectionTitle, { color: safeTheme.text }]}>Footer</Text>
                </View>
                <Switch
                  value={footerEnabled}
                  onValueChange={setFooterEnabled}
                  trackColor={{ false: '#E5E7EB', true: safeTheme.primary + '50' }}
                  thumbColor={footerEnabled ? safeTheme.primary : '#f4f3f4'}
                />
              </View>

              {footerEnabled && (
                <View style={styles.sectionBody}>
                  {/* Preview */}
                  <Text style={[styles.previewLabel, { color: safeTheme.textSecondary }]}>Preview:</Text>
                  {renderPreview('footer', footerLeft, footerCenter, footerRight)}

                  {/* Inputs */}
                  <View style={styles.inputsGrid}>
                    <InputRow {...inputRowProps}
                      label="Left"
                      value={footerLeft}
                      setValue={setFooterLeft}
                      inputId="footerLeft"
                      placeholder="e.g., Confidential"
                    />
                    <InputRow {...inputRowProps}
                      label="Center"
                      value={footerCenter}
                      setValue={setFooterCenter}
                      inputId="footerCenter"
                      placeholder="Optional"
                    />
                    <InputRow {...inputRowProps}
                      label="Right"
                      value={footerRight}
                      setValue={setFooterRight}
                      inputId="footerRight"
                      placeholder="e.g., Page {page} of {total}"
                    />
                  </View>

                  {/* Options */}
                  <View style={styles.optionsRow}>
                    <TouchableOpacity
                      style={[styles.optionChip, footerShowOnFirst && { backgroundColor: safeTheme.primary + '15' }]}
                      onPress={() => setFooterShowOnFirst(!footerShowOnFirst)}
                    >
                      <Ionicons
                        name={footerShowOnFirst ? 'checkbox' : 'square-outline'}
                        size={16}
                        color={footerShowOnFirst ? safeTheme.primary : safeTheme.textSecondary}
                      />
                      <Text style={[styles.optionText, { color: footerShowOnFirst ? safeTheme.primary : safeTheme.textSecondary }]}>
                        Show on first page
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>
              )}
            </View>
          </ScrollView>

          {/* Footer */}
          <View style={[styles.footer, { borderTopColor: safeTheme.border }]}>
            <TouchableOpacity
              style={[styles.cancelBtn, { borderColor: safeTheme.border }]}
              onPress={onClose}
            >
              <Text style={[styles.cancelBtnText, { color: safeTheme.text }]}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.saveBtn, { backgroundColor: safeTheme.primary }]}
              onPress={handleSave}
            >
              <MaterialIcons name="check" size={18} color="#fff" />
              <Text style={styles.saveBtnText}>Save Settings</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
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
  modalContainer: {
    width: 640,
    maxWidth: '95%',
    maxHeight: '90%',
    borderRadius: 12,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 10,
    elevation: 10,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
  },
  closeBtn: {
    padding: 4,
  },
  body: {
    flex: 1,
  },
  bodyContent: {
    padding: 20,
    gap: 20,
  },
  placeholdersSection: {
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
  },
  placeholdersTitle: {
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 8,
  },
  placeholdersList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 8,
  },
  placeholderChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 4,
    paddingHorizontal: 8,
    borderRadius: 4,
    borderWidth: 1,
    gap: 4,
  },
  placeholderChipText: {
    fontSize: 12,
    fontFamily: 'monospace',
  },
  placeholdersHint: {
    fontSize: 11,
    fontStyle: 'italic',
  },
  section: {
    borderWidth: 1,
    borderRadius: 10,
    overflow: 'hidden',
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 14,
    backgroundColor: '#FAFAFA',
  },
  sectionTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '600',
  },
  sectionBody: {
    padding: 16,
    gap: 16,
  },
  previewLabel: {
    fontSize: 12,
    fontWeight: '500',
    marginBottom: 4,
  },
  previewBar: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    borderWidth: 1,
    borderRadius: 6,
    minHeight: 40,
  },
  previewSection: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  previewCenter: {
    justifyContent: 'center',
  },
  previewRight: {
    justifyContent: 'flex-end',
  },
  previewText: {
    fontSize: 12,
  },
  previewLogo: {
    width: 24,
    height: 24,
    borderRadius: 4,
    marginRight: 6,
  },
  lhPreview: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderWidth: 1,
    borderRadius: 6,
    gap: 12,
  },
  lhPreviewLogo: {
    width: 48,
    height: 48,
    borderRadius: 6,
  },
  lhPreviewIdentity: {
    flex: 1,
    gap: 2,
  },
  lhPreviewName: {
    fontSize: 15,
    fontWeight: '700',
  },
  lhRule: {
    height: 2,
    borderRadius: 1,
    marginTop: -8,
  },
  inputsGrid: {
    flexDirection: 'row',
    gap: 12,
  },
  inputRow: {
    flex: 1,
    gap: 4,
  },
  inputLabel: {
    fontSize: 11,
    fontWeight: '500',
    textTransform: 'uppercase',
  },
  input: {
    borderWidth: 1,
    borderRadius: 6,
    padding: 10,
    fontSize: 13,
  },
  logoInputRow: {
    gap: 4,
  },
  logoInput: {
    flex: 1,
  },
  optionsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  optionChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 6,
    gap: 6,
  },
  optionText: {
    fontSize: 13,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    padding: 16,
    borderTopWidth: 1,
    backgroundColor: '#FAFAFA',
    gap: 12,
  },
  cancelBtn: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    borderWidth: 1,
  },
  cancelBtnText: {
    fontSize: 14,
    fontWeight: '500',
  },
  saveBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    gap: 6,
  },
  saveBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#fff',
  },
});

export default ReportHeaderFooterModal;
