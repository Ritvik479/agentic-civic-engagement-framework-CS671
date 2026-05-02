import React, { useEffect, useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  ScrollView,
  StatusBar,
} from 'react-native';

const API_URL = process.env.EXPO_PUBLIC_API_URL;

const COLORS = {
  bg: '#1c1a17',
  card: '#252320',
  primary: '#c9952a',
  foreground: '#e6ddd0',
  muted: '#7a7164',
  accent: '#c0392b',
  success: '#27ae60',
  border: '#2a2820',
};

const STATUS_STEPS = [
  { key: 'pending',           label: 'Complaint received' },
  { key: 'detecting_issue',   label: 'Detecting issue from video' },
  { key: 'mapping_authority', label: 'Identifying responsible authority' },
  { key: 'drafting',          label: 'Drafting complaint text' },
  { key: 'submitting',        label: 'Submitting to authority portal' },
  { key: 'completed',         label: 'Complaint filed successfully' },
];

const TERMINAL_STATUSES = new Set(['completed', 'failed']);

export default function TasksScreen({ route }) {
  const trackingId = route?.params?.trackingId;

  const [status, setStatus] = useState('pending'); // hardcoded for preview
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!trackingId) return;
    if (intervalRef.current) clearInterval(intervalRef.current);

    const poll = async () => {
      try {
        const res = await fetch(`${API_URL}/status/${trackingId}`);
        if (!res.ok) { setError(`Server returned ${res.status}. Retrying…`); return; }
        const data = await res.json();
        setError(null);
        setStatus(data.status);
        setLogs(data.logs ?? []);
        if (TERMINAL_STATUSES.has(data.status)) clearInterval(intervalRef.current);
      } catch {
        setError('Connection error. Retrying…');
      }
    };

    poll();
    intervalRef.current = setInterval(poll, 3000);
    return () => clearInterval(intervalRef.current);
  }, [trackingId]);

  // No active job
  if (!trackingId) {
    return (
      <View style={styles.container}>
        <StatusBar barStyle="light-content" />
        <View style={styles.header}>
          <Text style={styles.title}>MY REPORTS</Text>
        </View>
        <View style={styles.center}>
          <Text style={styles.emptyIcon}>📋</Text>
          <Text style={styles.emptyText}>No active complaint</Text>
          <Text style={styles.emptySubText}>
            Submit a report from the New Report tab to track it here
          </Text>
        </View>
      </View>
    );
  }

  const isFailed = status === 'failed';
  const isCompleted = status === 'completed';
  const currentStepIndex = STATUS_STEPS.findIndex(s => s.key === status);

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" />

      <View style={styles.header}>
        <Text style={styles.title}>MY REPORTS</Text>
        <Text style={styles.trackingId}>{trackingId}</Text>
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>

        {error && (
          <View style={styles.errorBanner}>
            <Text style={styles.errorBannerText}>⚠️ {error}</Text>
          </View>
        )}

        {/* Pipeline Steps */}
        <View style={styles.stepsCard}>
          {STATUS_STEPS.map((step, i) => {
            const done = i < currentStepIndex;
            const active = i === currentStepIndex;

            return (
              <View key={step.key} style={styles.stepRow}>
                {i > 0 && (
                  <View style={[styles.connector, done && styles.connectorDone]} />
                )}
                <View style={styles.stepDotRow}>
                  <View style={[
                    styles.dot,
                    done && styles.dotDone,
                    active && !isFailed && styles.dotActive,
                    active && isFailed && styles.dotFailed,
                  ]}>
                    {done && <Text style={styles.dotCheck}>✓</Text>}
                    {active && !isFailed && !isCompleted && (
                      <ActivityIndicator size="small" color="#fff" />
                    )}
                    {active && isCompleted && <Text style={styles.dotCheck}>✓</Text>}
                    {active && isFailed && <Text style={styles.dotCheck}>✕</Text>}
                  </View>
                  <Text style={[
                    styles.stepLabel,
                    done && styles.stepLabelDone,
                    active && styles.stepLabelActive,
                    !done && !active && styles.stepLabelPending,
                  ]}>
                    {step.label}
                  </Text>
                </View>
              </View>
            );
          })}
        </View>

        {/* Logs */}
        {logs.length > 0 && (
          <View style={styles.logsCard}>
            <Text style={styles.logsTitle}>ACTIVITY LOG</Text>
            {logs.map((log, i) => (
              <Text key={i} style={styles.logLine}>› {log}</Text>
            ))}
          </View>
        )}

        {/* Completed */}
        {isCompleted && (
          <View style={styles.resultCard}>
            <Text style={styles.resultSuccess}>✅ Complaint Filed</Text>
            <Text style={styles.resultSub}>
              Your complaint has been submitted to the relevant authority.
              You may follow up using your tracking ID.
            </Text>
          </View>
        )}

        {/* Failed */}
        {isFailed && (
          <View style={styles.failedCard}>
            <Text style={styles.failedText}>❌ Submission Failed</Text>
            <Text style={styles.failedSub}>
              Something went wrong. Please try submitting again.
            </Text>
          </View>
        )}

      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg, padding: 20 },
  header: { marginTop: 40, marginBottom: 20 },
  title: { fontSize: 18, fontWeight: '800', color: COLORS.primary, letterSpacing: 2 },
  trackingId: { fontSize: 11, color: COLORS.muted, marginTop: 4, letterSpacing: 1 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  emptyIcon: { fontSize: 40, marginBottom: 12 },
  emptyText: { color: COLORS.foreground, fontSize: 16, fontWeight: '700' },
  emptySubText: { color: COLORS.muted, fontSize: 13, textAlign: 'center', marginTop: 8, paddingHorizontal: 30, lineHeight: 18 },
  errorBanner: { backgroundColor: '#3a1a1a', borderWidth: 1, borderColor: COLORS.accent, borderRadius: 8, padding: 10, marginBottom: 14 },
  errorBannerText: { color: '#e07070', fontSize: 12 },
  stepsCard: { backgroundColor: COLORS.card, borderRadius: 12, padding: 16, marginBottom: 14 },
  stepRow: { alignItems: 'flex-start' },
  connector: { width: 2, height: 14, backgroundColor: COLORS.border, marginLeft: 11 },
  connectorDone: { backgroundColor: COLORS.success },
  stepDotRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  dot: { width: 24, height: 24, borderRadius: 12, backgroundColor: COLORS.border, justifyContent: 'center', alignItems: 'center' },
  dotActive: { backgroundColor: COLORS.primary },
  dotDone: { backgroundColor: COLORS.success },
  dotFailed: { backgroundColor: COLORS.accent },
  dotCheck: { color: '#fff', fontSize: 11, fontWeight: '800' },
  stepLabel: { fontSize: 13, color: COLORS.muted, flex: 1 },
  stepLabelActive: { color: COLORS.foreground, fontWeight: '600' },
  stepLabelDone: { color: COLORS.success },
  stepLabelPending: { color: COLORS.muted },
  logsCard: { backgroundColor: COLORS.card, borderRadius: 12, padding: 16, marginBottom: 14 },
  logsTitle: { fontSize: 11, fontWeight: '700', color: COLORS.muted, letterSpacing: 1, marginBottom: 10 },
  logLine: { fontSize: 12, color: COLORS.muted, lineHeight: 20 },
  resultCard: { backgroundColor: '#1a2e1f', borderWidth: 1, borderColor: COLORS.success, borderRadius: 12, padding: 16, marginBottom: 14 },
  resultSuccess: { fontSize: 16, fontWeight: '800', color: COLORS.success, marginBottom: 8 },
  resultSub: { fontSize: 13, color: COLORS.foreground, lineHeight: 18 },
  failedCard: { backgroundColor: '#2e1a1a', borderWidth: 1, borderColor: COLORS.accent, borderRadius: 12, padding: 16, marginBottom: 14 },
  failedText: { fontSize: 16, fontWeight: '800', color: COLORS.accent, marginBottom: 8 },
  failedSub: { fontSize: 13, color: COLORS.foreground, lineHeight: 18 },
});