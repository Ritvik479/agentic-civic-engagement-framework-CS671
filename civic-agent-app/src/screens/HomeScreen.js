import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  StatusBar,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const COLORS = {
  bg: '#1c1a17',
  card: '#252320',
  primary: '#c9952a',
  foreground: '#e6ddd0',
  muted: '#7a7164',
  accent: '#c0392b',
};

export default function HomeScreen({ navigation }) {
  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" />

      {/* 🔰 Header */}
      <View style={styles.header}>
        <Text style={styles.title}>CIVICWATCH</Text>
        <Ionicons name="shield-checkmark" size={22} color={COLORS.primary} />
      </View>

      {/* 🧠 Main CTA */}
      <View style={styles.center}>
        <TouchableOpacity
          style={styles.reportButton}
          activeOpacity={0.8}
          onPress={() => navigation.navigate('New Complaint')}
        >
          <Ionicons name="camera" size={40} color="#fff" />
        </TouchableOpacity>

        <Text style={styles.ctaText}>Report an Issue</Text>
        <Text style={styles.subText}>
          Record a video complaint and let the system handle it
        </Text>
      </View>

      {/* 📊 Simple Stats (static placeholder) */}
      <View style={styles.stats}>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>12</Text>
          <Text style={styles.statLabel}>Filed</Text>
        </View>

        <View style={styles.statCard}>
          <Text style={styles.statValue}>3</Text>
          <Text style={styles.statLabel}>Processing</Text>
        </View>

        <View style={styles.statCard}>
          <Text style={styles.statValue}>8</Text>
          <Text style={styles.statLabel}>Resolved</Text>
        </View>
      </View>

      {/* 📄 Navigation shortcut */}
      <TouchableOpacity
        style={styles.tasksBtn}
        onPress={() => navigation.navigate('Processing')}
      >
        <Ionicons name="clipboard-outline" size={18} color={COLORS.primary} />
        <Text style={styles.tasksText}>View My Reports</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
    padding: 20,
    justifyContent: 'space-between',
  },

  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 40,
  },

  title: {
    fontSize: 20,
    fontWeight: '800',
    color: COLORS.primary,
    letterSpacing: 2,
  },

  center: {
    alignItems: 'center',
    marginTop: -40,
  },

  reportButton: {
    width: 100,
    height: 100,
    borderRadius: 20,
    backgroundColor: COLORS.accent,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: COLORS.accent,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.4,
    shadowRadius: 10,
    elevation: 10,
  },

  ctaText: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.foreground,
    marginTop: 16,
  },

  subText: {
    fontSize: 13,
    color: COLORS.muted,
    marginTop: 6,
    textAlign: 'center',
    paddingHorizontal: 20,
  },

  stats: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 20,
  },

  statCard: {
    flex: 1,
    backgroundColor: COLORS.card,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
    marginHorizontal: 5,
  },

  statValue: {
    fontSize: 20,
    fontWeight: '800',
    color: COLORS.foreground,
  },

  statLabel: {
    fontSize: 11,
    color: COLORS.muted,
    marginTop: 4,
  },

  tasksBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    padding: 14,
    borderRadius: 12,
    backgroundColor: COLORS.card,
  },

  tasksText: {
    color: COLORS.primary,
    fontWeight: '600',
  },
});