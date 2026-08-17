// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

// BusinessTemplates.js - Pre-built business report templates
import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  Modal,
  Alert
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const BusinessTemplates = ({
  visible,
  onClose,
  onTemplateSelect,
  theme
}) => {
  const [selectedTemplate, setSelectedTemplate] = useState(null);

  const businessTemplates = [
    {
      id: 'quarterly-report',
      name: 'Quarterly Business Report',
      description: 'Comprehensive quarterly performance analysis',
      category: 'Financial',
      estimatedPages: 8,
      icon: 'bar-chart-outline',
      sections: [
        'Executive Summary',
        'Financial Performance',
        'Market Analysis',
        'Operational Highlights',
        'Risk Assessment',
        'Strategic Initiatives',
        'Future Outlook',
        'Appendices'
      ],
      template: {
        overall_goal: 'Create a comprehensive quarterly business report analyzing performance, market conditions, and strategic outlook',
        pages: [
          {
            title: 'Executive Summary',
            outline: '- Key performance highlights\n- Major achievements\n- Strategic priorities\n- Financial overview\n- Market position summary',
            guidance: 'Provide a high-level overview that executives can read to understand the quarter\'s performance and key decisions needed.'
          },
          {
            title: 'Financial Performance',
            outline: '- Revenue and growth metrics\n- Profit margins analysis\n- Cash flow statement\n- Budget vs actual performance\n- Key financial ratios',
            guidance: 'Present detailed financial analysis with charts and trend comparisons to previous quarters.'
          },
          {
            title: 'Market Analysis',
            outline: '- Industry trends\n- Competitive landscape\n- Market share analysis\n- Customer insights\n- Economic factors impact',
            guidance: 'Analyze external market conditions affecting business performance and opportunities.'
          },
          {
            title: 'Operational Highlights',
            outline: '- Production metrics\n- Operational efficiency\n- Quality measures\n- Supply chain performance\n- Technology initiatives',
            guidance: 'Detail operational achievements and challenges, including process improvements and efficiency gains.'
          },
          {
            title: 'Risk Assessment',
            outline: '- Identified risks\n- Risk mitigation strategies\n- Contingency plans\n- Compliance status\n- Internal controls',
            guidance: 'Assess current and emerging risks with mitigation strategies and contingency planning.'
          },
          {
            title: 'Strategic Initiatives',
            outline: '- Current projects status\n- New initiative proposals\n- Resource allocation\n- Timeline and milestones\n- Expected outcomes',
            guidance: 'Report on strategic projects and propose new initiatives for future quarters.'
          },
          {
            title: 'Future Outlook',
            outline: '- Market forecasts\n- Business projections\n- Strategic goals\n- Investment plans\n- Growth opportunities',
            guidance: 'Provide forward-looking analysis and strategic recommendations for upcoming quarters.'
          },
          {
            title: 'Appendices',
            outline: '- Detailed financial statements\n- Supporting charts and graphs\n- Methodology notes\n- Data sources\n- Glossary of terms',
            guidance: 'Include supporting documentation and detailed data that supports the main report findings.'
          }
        ]
      }
    },
    {
      id: 'market-research',
      name: 'Market Research Report',
      description: 'In-depth market analysis and consumer insights',
      category: 'Research',
      estimatedPages: 6,
      icon: 'analytics-outline',
      sections: [
        'Research Methodology',
        'Market Overview',
        'Consumer Analysis',
        'Competitive Landscape',
        'Findings & Insights',
        'Recommendations'
      ],
      template: {
        overall_goal: 'Conduct comprehensive market research to inform strategic business decisions and identify opportunities',
        pages: [
          {
            title: 'Research Methodology',
            outline: '- Research objectives\n- Data collection methods\n- Sample size and demographics\n- Timeline and scope\n- Limitations and assumptions',
            guidance: 'Establish the research framework, methodology, and scope to ensure credible and actionable insights.'
          },
          {
            title: 'Market Overview',
            outline: '- Market size and growth\n- Key market drivers\n- Industry trends\n- Regulatory environment\n- Economic factors',
            guidance: 'Provide comprehensive market context including size, growth trends, and external factors.'
          },
          {
            title: 'Consumer Analysis',
            outline: '- Target audience profiles\n- Consumer behavior patterns\n- Purchasing decision factors\n- Brand preferences\n- Unmet needs',
            guidance: 'Deep dive into consumer insights, behaviors, and preferences that drive market dynamics.'
          },
          {
            title: 'Competitive Landscape',
            outline: '- Key competitors analysis\n- Market share distribution\n- Competitive advantages\n- Pricing strategies\n- Product positioning',
            guidance: 'Analyze competitive environment and positioning strategies of major market players.'
          },
          {
            title: 'Findings & Insights',
            outline: '- Key research findings\n- Consumer insights\n- Market opportunities\n- Threats and challenges\n- Emerging trends',
            guidance: 'Synthesize research data into actionable insights and identify strategic opportunities.'
          },
          {
            title: 'Recommendations',
            outline: '- Strategic recommendations\n- Action plan\n- Implementation timeline\n- Resource requirements\n- Success metrics',
            guidance: 'Provide specific, actionable recommendations based on research findings with implementation guidance.'
          }
        ]
      }
    },
    {
      id: 'project-proposal',
      name: 'Project Proposal',
      description: 'Structured proposal for new business initiatives',
      category: 'Planning',
      estimatedPages: 5,
      icon: 'document-text-outline',
      sections: [
        'Project Overview',
        'Business Case',
        'Implementation Plan',
        'Resource Requirements',
        'Risk Management'
      ],
      template: {
        overall_goal: 'Present a compelling business case for a new project initiative with detailed implementation planning',
        pages: [
          {
            title: 'Project Overview',
            outline: '- Project description\n- Objectives and goals\n- Success criteria\n- Stakeholders\n- Project scope',
            guidance: 'Clearly define the project purpose, scope, and expected outcomes to establish project foundation.'
          },
          {
            title: 'Business Case',
            outline: '- Problem statement\n- Proposed solution\n- Benefits and value\n- Cost-benefit analysis\n- ROI projections',
            guidance: 'Build compelling business justification with quantified benefits and return on investment analysis.'
          },
          {
            title: 'Implementation Plan',
            outline: '- Project phases\n- Timeline and milestones\n- Deliverables\n- Dependencies\n- Quality assurance',
            guidance: 'Detail the implementation approach with realistic timelines and clear deliverable milestones.'
          },
          {
            title: 'Resource Requirements',
            outline: '- Human resources needed\n- Budget requirements\n- Technology and tools\n- External vendors\n- Training needs',
            guidance: 'Specify all resources required for successful project execution including costs and procurement.'
          },
          {
            title: 'Risk Management',
            outline: '- Risk identification\n- Risk assessment\n- Mitigation strategies\n- Contingency plans\n- Monitoring approach',
            guidance: 'Identify potential risks and provide comprehensive mitigation and contingency strategies.'
          }
        ]
      }
    },
    {
      id: 'swot-analysis',
      name: 'SWOT Analysis Report',
      description: 'Strategic analysis of strengths, weaknesses, opportunities, and threats',
      category: 'Strategic',
      estimatedPages: 4,
      icon: 'grid-outline',
      sections: [
        'Analysis Framework',
        'Internal Analysis (S&W)',
        'External Analysis (O&T)',
        'Strategic Recommendations'
      ],
      template: {
        overall_goal: 'Conduct comprehensive SWOT analysis to inform strategic planning and decision-making',
        pages: [
          {
            title: 'Analysis Framework',
            outline: '- SWOT methodology\n- Analysis scope\n- Data sources\n- Evaluation criteria\n- Stakeholder input',
            guidance: 'Establish the analytical framework and methodology for conducting the SWOT analysis.'
          },
          {
            title: 'Internal Analysis (Strengths & Weaknesses)',
            outline: '- Core strengths inventory\n- Competitive advantages\n- Internal weaknesses\n- Resource limitations\n- Capability gaps',
            guidance: 'Analyze internal factors that provide advantages or present challenges to the organization.'
          },
          {
            title: 'External Analysis (Opportunities & Threats)',
            outline: '- Market opportunities\n- Industry trends\n- External threats\n- Competitive pressures\n- Regulatory changes',
            guidance: 'Examine external environment for opportunities to leverage and threats to mitigate.'
          },
          {
            title: 'Strategic Recommendations',
            outline: '- Strategic options\n- Prioritized recommendations\n- Implementation roadmap\n- Resource allocation\n- Success metrics',
            guidance: 'Synthesize SWOT findings into actionable strategic recommendations with implementation guidance.'
          }
        ]
      }
    },
    {
      id: 'feasibility-study',
      name: 'Feasibility Study',
      description: 'Comprehensive analysis of project or initiative viability',
      category: 'Planning',
      estimatedPages: 7,
      icon: 'search-outline',
      sections: [
        'Study Overview',
        'Market Feasibility',
        'Technical Feasibility',
        'Financial Feasibility',
        'Operational Feasibility',
        'Risk Analysis',
        'Conclusions & Recommendations'
      ],
      template: {
        overall_goal: 'Evaluate the viability and feasibility of a proposed project or business initiative across multiple dimensions',
        pages: [
          {
            title: 'Study Overview',
            outline: '- Project description\n- Study objectives\n- Scope and limitations\n- Methodology\n- Key assumptions',
            guidance: 'Define the feasibility study parameters and establish the evaluation framework.'
          },
          {
            title: 'Market Feasibility',
            outline: '- Market demand analysis\n- Target market size\n- Competition assessment\n- Market entry barriers\n- Revenue potential',
            guidance: 'Assess market viability and commercial potential for the proposed initiative.'
          },
          {
            title: 'Technical Feasibility',
            outline: '- Technical requirements\n- Technology assessment\n- Infrastructure needs\n- Implementation complexity\n- Technical risks',
            guidance: 'Evaluate technical requirements and implementation challenges from a technology perspective.'
          },
          {
            title: 'Financial Feasibility',
            outline: '- Cost estimates\n- Revenue projections\n- Cash flow analysis\n- Break-even analysis\n- ROI calculations',
            guidance: 'Analyze financial viability with detailed cost-benefit analysis and financial projections.'
          },
          {
            title: 'Operational Feasibility',
            outline: '- Operational requirements\n- Resource availability\n- Process integration\n- Organizational impact\n- Implementation timeline',
            guidance: 'Assess operational capacity and organizational readiness for project implementation.'
          },
          {
            title: 'Risk Analysis',
            outline: '- Risk identification\n- Probability assessment\n- Impact analysis\n- Risk mitigation\n- Contingency planning',
            guidance: 'Comprehensive risk evaluation with mitigation strategies and contingency planning.'
          },
          {
            title: 'Conclusions & Recommendations',
            outline: '- Feasibility summary\n- Go/No-go recommendation\n- Critical success factors\n- Next steps\n- Decision criteria',
            guidance: 'Synthesize analysis into clear recommendations with decision criteria and next steps.'
          }
        ]
      }
    }
  ];

  const handleTemplateSelect = () => {
    if (!selectedTemplate) {
      Alert.alert('Selection Required', 'Please select a template to use.');
      return;
    }

    const template = businessTemplates.find(t => t.id === selectedTemplate);
    if (template) {
      onTemplateSelect(template.template, template);
      onClose();
    }
  };

  const getCategoryIcon = (category) => {
    const icons = {
      'Financial': 'trending-up-outline',
      'Research': 'analytics-outline',
      'Planning': 'document-text-outline',
      'Strategic': 'compass-outline'
    };
    return icons[category] || 'document-outline';
  };

  const getCategoryColor = (category) => {
    const colors = {
      'Financial': '#10B981',
      'Research': '#3B82F6',
      'Planning': '#8B5CF6',
      'Strategic': '#F59E0B'
    };
    return colors[category] || theme.primary;
  };

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
            Business Templates
          </Text>
          <View style={{ width: 24 }} />
        </View>

        {/* Templates List */}
        <ScrollView style={styles.content}>
          <Text style={[styles.subtitle, { color: theme.placeholderText }]}>
            Choose a professional template to jumpstart your report
          </Text>

          {businessTemplates.map((template) => (
            <TouchableOpacity
              key={template.id}
              style={[
                styles.templateCard,
                { 
                  backgroundColor: selectedTemplate === template.id ? theme.primary + '10' : theme.surface,
                  borderColor: selectedTemplate === template.id ? theme.primary : theme.borderColor
                }
              ]}
              onPress={() => setSelectedTemplate(template.id)}
            >
              {/* Template Header */}
              <View style={styles.templateHeader}>
                <View style={styles.templateInfo}>
                  <View style={[
                    styles.categoryBadge,
                    { backgroundColor: getCategoryColor(template.category) + '20' }
                  ]}>
                    <Ionicons 
                      name={getCategoryIcon(template.category)} 
                      size={14} 
                      color={getCategoryColor(template.category)} 
                    />
                    <Text style={[
                      styles.categoryText,
                      { color: getCategoryColor(template.category) }
                    ]}>
                      {template.category}
                    </Text>
                  </View>
                  
                  <Text style={[styles.templateName, { color: theme.text }]}>
                    {template.name}
                  </Text>
                  <Text style={[styles.templateDescription, { color: theme.placeholderText }]}>
                    {template.description}
                  </Text>
                </View>
                
                <View style={styles.templateMeta}>
                  <View style={styles.metaItem}>
                    <Ionicons name="document-outline" size={16} color={theme.placeholderText} />
                    <Text style={[styles.metaText, { color: theme.placeholderText }]}>
                      {template.estimatedPages} pages
                    </Text>
                  </View>
                  
                  {selectedTemplate === template.id && (
                    <Ionicons name="checkmark-circle" size={24} color={theme.primary} />
                  )}
                </View>
              </View>

              {/* Sections Preview */}
              <View style={styles.sectionsPreview}>
                <Text style={[styles.sectionsTitle, { color: theme.text }]}>
                  Report Sections:
                </Text>
                <View style={styles.sectionsList}>
                  {template.sections.map((section, index) => (
                    <View key={index} style={styles.sectionTag}>
                      <Text style={[styles.sectionText, { color: theme.placeholderText }]}>
                        {section}
                      </Text>
                    </View>
                  ))}
                </View>
              </View>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Footer */}
        <View style={[styles.footer, { borderTopColor: theme.borderColor }]}>
          <TouchableOpacity
            style={[styles.footerButton, { borderColor: theme.borderColor }]}
            onPress={onClose}
          >
            <Text style={[styles.footerButtonText, { color: theme.text }]}>Cancel</Text>
          </TouchableOpacity>
          
          <TouchableOpacity
            style={[
              styles.footerButton, 
              styles.primaryFooterButton, 
              { 
                backgroundColor: selectedTemplate ? theme.primary : theme.borderColor,
                opacity: selectedTemplate ? 1 : 0.5
              }
            ]}
            onPress={handleTemplateSelect}
            disabled={!selectedTemplate}
          >
            <Text style={[styles.footerButtonText, { color: theme.buttonText }]}>
              Use Template
            </Text>
          </TouchableOpacity>
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
  content: {
    flex: 1,
    padding: 16,
  },
  subtitle: {
    fontSize: 14,
    textAlign: 'center',
    marginBottom: 20,
    lineHeight: 20,
  },
  templateCard: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 16,
    marginBottom: 16,
  },
  templateHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  templateInfo: {
    flex: 1,
    marginRight: 12,
  },
  categoryBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    marginBottom: 8,
    gap: 4,
  },
  categoryText: {
    fontSize: 11,
    fontWeight: '500',
  },
  templateName: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  templateDescription: {
    fontSize: 13,
    lineHeight: 18,
  },
  templateMeta: {
    alignItems: 'flex-end',
    gap: 8,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  metaText: {
    fontSize: 12,
  },
  sectionsPreview: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.1)',
  },
  sectionsTitle: {
    fontSize: 13,
    fontWeight: '500',
    marginBottom: 8,
  },
  sectionsList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  sectionTag: {
    backgroundColor: 'rgba(0,0,0,0.05)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  sectionText: {
    fontSize: 11,
  },
  footer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderTopWidth: 1,
    gap: 12,
  },
  footerButton: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
    borderWidth: 1,
  },
  primaryFooterButton: {
    borderWidth: 0,
  },
  footerButtonText: {
    fontSize: 16,
    fontWeight: '500',
  },
};

export default BusinessTemplates;
