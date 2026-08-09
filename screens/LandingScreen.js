import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const CARDS = [
  {
    key: 'presentation',
    icon: 'easel-outline',
    title: 'Presentation',
    description: 'AI-generated slide decks — outline, write, and design a presentation from a goal.',
  },
  {
    key: 'printable',
    icon: 'bar-chart-outline',
    title: 'Visual Report',
    description: 'One-page visual reports with charts and KPIs, laid out for print or export.',
  },
  {
    key: 'report',
    icon: 'document-text-outline',
    title: 'MS-Word Report',
    description: 'Long-form written reports — structured sections, grounded in your documents.',
  },
];

export default function LandingScreen({ onSelectType, theme }) {
  const { width } = useWindowDimensions();
  const isMobile = width < 768;

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <Text style={[styles.title, { color: theme.text }]}>Citra Decks</Text>
        <Text style={[styles.subtitle, { color: theme.textSecondary }]}>
          Choose what you want to create
        </Text>

        <View style={[styles.cardRow, isMobile && styles.cardRowMobile]}>
          {CARDS.map((card) => (
            <TouchableOpacity
              key={card.key}
              style={[
                styles.card,
                isMobile && styles.cardMobile,
                { backgroundColor: theme.surface || theme.card || '#16213e', borderColor: theme.borderColor || '#2a2a3e' },
              ]}
              onPress={() => onSelectType(card.key)}
            >
              <Ionicons name={card.icon} size={40} color={theme.primary} />
              <Text style={[styles.cardTitle, { color: theme.text }]}>{card.title}</Text>
              <Text style={[styles.cardDescription, { color: theme.textSecondary }]}>
                {card.description}
              </Text>
              <View style={[styles.cardAction, { borderColor: theme.primary }]}>
                <Text style={[styles.cardActionText, { color: theme.primary }]}>Sign in to start</Text>
              </View>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.footer}>
          <Text style={[styles.footerLine, { color: theme.textSecondary }]}>
            Citra is a product of Trustedwear Tech Private Limited
          </Text>
          <Text style={[styles.footerLine, { color: theme.textSecondary }]}>
            Founder ex-Microsoft (20+ yrs enterprise software) · Incubated at IIT Patna
          </Text>
          <Text style={[styles.footerLine, { color: theme.textSecondary }]}>
            Funded by Startup India, MeitY &amp; the Government of Bihar
          </Text>
          <Text style={[styles.footerContact, { color: theme.textSecondary }]}>
            Rohit Kumar Chandan · Founder · rohit@citra-ai.com · https://citra-ai.com
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    marginBottom: 8,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 16,
    marginBottom: 40,
    textAlign: 'center',
  },
  cardRow: {
    flexDirection: 'row',
    gap: 20,
    maxWidth: 1000,
    width: '100%',
    justifyContent: 'center',
  },
  cardRowMobile: {
    flexDirection: 'column',
  },
  card: {
    flex: 1,
    minWidth: 240,
    maxWidth: 320,
    borderWidth: 1,
    borderRadius: 16,
    padding: 28,
    alignItems: 'center',
  },
  cardMobile: {
    maxWidth: '100%',
  },
  cardTitle: {
    fontSize: 20,
    fontWeight: '700',
    marginTop: 16,
    marginBottom: 8,
    textAlign: 'center',
  },
  cardDescription: {
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
    marginBottom: 20,
  },
  cardAction: {
    borderWidth: 1,
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 16,
  },
  cardActionText: {
    fontSize: 14,
    fontWeight: '600',
  },
  footer: {
    marginTop: 48,
    alignItems: 'center',
  },
  footerLine: {
    fontSize: 12,
    textAlign: 'center',
    marginBottom: 4,
    opacity: 0.8,
  },
  footerContact: {
    fontSize: 12,
    textAlign: 'center',
    marginTop: 8,
    opacity: 0.8,
  },
});
