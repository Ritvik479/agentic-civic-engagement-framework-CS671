import { Ionicons } from '@expo/vector-icons'
import { ScrollView, StyleSheet, Text, View } from 'react-native'
import { useComplaints } from './ComplaintContext'

export default function TrackScreen() {
  const { complaints } = useComplaints()

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Ionicons name="shield-checkmark" size={28} color="#4ade80" />
        <Text style={styles.logoText}>CivicAlert</Text>
      </View>
      <Text style={styles.tagline}>Track your complaint status</Text>

      <View style={styles.statsRow}>
        <View style={styles.statBox}>
          <Text style={styles.statNum}>{complaints.length}</Text>
          <Text style={styles.statLabel}>Total</Text>
        </View>
        <View style={styles.statBox}>
          <Text style={[styles.statNum, { color: '#f0a500' }]}>
            {complaints.filter((c: any) => c.status === 'Submitted').length}
          </Text>
          <Text style={styles.statLabel}>Submitted</Text>
        </View>
        <View style={styles.statBox}>
          <Text style={[styles.statNum, { color: '#4ade80' }]}>
            {complaints.filter((c: any) => c.status === 'Under Review').length}
          </Text>
          <Text style={styles.statLabel}>In Review</Text>
        </View>
        <View style={styles.statBox}>
          <Text style={[styles.statNum, { color: '#f87171' }]}>
            {complaints.filter((c: any) => c.status === 'Escalated').length}
          </Text>
          <Text style={styles.statLabel}>Escalated</Text>
        </View>
      </View>

      {complaints.map((item: any) => (
        <View key={item.id} style={styles.card}>
          <View style={styles.cardTop}>
            <Text style={styles.cardId}>{item.id}</Text>
            <View style={[styles.badge, { borderColor: item.color }]}>
              <Text style={[styles.badgeText, { color: item.color }]}>{item.status}</Text>
            </View>
          </View>
          <Text style={styles.cardIssue}>{item.issue}</Text>
          <View style={styles.cardFooter}>
            <Ionicons name="location-outline" size={13} color="#555" />
            <Text style={styles.cardLocation}>{item.location}</Text>
          </View>
        </View>
      ))}
      <View style={{ height: 40 }} />
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f', paddingHorizontal: 24, paddingTop: 60 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 4 },
  logoText: { fontSize: 26, fontWeight: 'bold', color: '#fff' },
  tagline: { fontSize: 13, color: '#555', marginBottom: 24 },
  statsRow: { flexDirection: 'row', gap: 8, marginBottom: 24 },
  statBox: {
    flex: 1, backgroundColor: '#1a1a1a', borderRadius: 12,
    padding: 12, alignItems: 'center', borderWidth: 1, borderColor: '#222',
  },
  statNum: { fontSize: 22, fontWeight: 'bold', color: '#fff' },
  statLabel: { fontSize: 11, color: '#555', marginTop: 2 },
  card: {
    backgroundColor: '#1a1a1a', borderRadius: 14,
    padding: 16, marginBottom: 12, borderWidth: 1, borderColor: '#222',
  },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  cardId: { fontWeight: 'bold', color: '#fff' },
  badge: {
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: 20, borderWidth: 1,
  },
  badgeText: { fontSize: 12, fontWeight: '600' },
  cardIssue: { fontSize: 15, color: '#ddd', marginBottom: 8 },
  cardFooter: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  cardLocation: { fontSize: 13, color: '#555' },
})