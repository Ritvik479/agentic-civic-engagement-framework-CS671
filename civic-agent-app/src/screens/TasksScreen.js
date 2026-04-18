import React, { useEffect, useState } from 'react';
import { View, Text,StyleSheet, ActivityIndicator } from 'react-native';
import { StatusBar } from 'react-native';
const API_URL = process.env.EXPO_PUBLIC_API_URL;

export default function TasksScreen({ route }) {
  const jobId = route?.params?.jobId;

  const [job, setJob] = useState(null);

  useEffect(() => {
  if (!jobId) return; // 🚨 STOP HERE

  const interval = setInterval(async () => {
    try {
      const res = await fetch(`${API_URL}/jobs/${jobId}`);
      const data = await res.json();

      if (data.success) {
        setJob(data.data);

        if (data.data.status === "completed") {
          clearInterval(interval);
        }
      }
    } catch (err) {
      console.log("Polling error", err);
    }
  }, 3000);


    return () => clearInterval(interval);
  }, []);

  if (!jobId) {
  return (
    <View style={styles.center}>
      <Text style={{ color: '#fff' }}>
        No active job
      </Text>

      <Text style={{ color: '#7a7164', marginTop: 8 }}>
        Submit a report to track it here
      </Text>
    </View>
  );
}

  if (job.status === "processing") {
    return (
      <View>
        <Text>⏳ Processing complaint...</Text>
      </View>
    );
  }

  return (
  <View style={styles.container}>
    <StatusBar barStyle="light-content" />

    <View style={styles.header}>
      <Text style={styles.title}>MY REPORTS</Text>
    </View>

    {!job ? (
      <ActivityIndicator size="large" color="#c9952a" />
    ) : job.status === "processing" ? (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#c9952a" />
        <Text style={styles.processingText}>Processing complaint...</Text>
      </View>
    ) : (
      <View style={styles.resultCard}>
        <Text style={styles.success}>✅ Completed</Text>

        <Text style={styles.label}>Report</Text>
        <Text style={styles.value}>{job.result.report}</Text>

        <Text style={styles.label}>Severity</Text>
        <Text style={styles.value}>{job.result.severity}</Text>

        <Text style={styles.label}>PDF</Text>
        <Text style={styles.value}>{job.result.pdf}</Text>
      </View>
    )}
  </View>
);
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1c1a17',
    padding: 20,
  },

  header: {
    marginTop: 40,
    marginBottom: 20,
  },

  title: {
    fontSize: 18,
    fontWeight: '800',
    color: '#c9952a',
    letterSpacing: 2,
  },

  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },

  processingText: {
    marginTop: 12,
    color: '#e6ddd0',
  },

  resultCard: {
    backgroundColor: '#252320',
    padding: 20,
    borderRadius: 12,
  },

  success: {
    fontSize: 18,
    color: '#27ae60',
    fontWeight: '700',
    marginBottom: 16,
  },

  label: {
    fontSize: 12,
    color: '#7a7164',
    marginTop: 10,
  },

  value: {
    fontSize: 14,
    color: '#e6ddd0',
  },
});