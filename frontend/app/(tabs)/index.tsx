import { Ionicons } from '@expo/vector-icons'
import * as ImagePicker from 'expo-image-picker'
import { useState } from 'react'
import { Alert, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native'
import { useComplaints } from './ComplaintContext'

const ISSUE_TYPES = [
  { label: 'Garbage / Waste', icon: 'trash-outline', value: 'garbage' },
  { label: 'Water / Sewage', icon: 'water-outline', value: 'sewage' },
  { label: 'Air / Pollution', icon: 'cloud-outline', value: 'pollution' },
  { label: 'Road / Infrastructure', icon: 'construct-outline', value: 'road' },
  { label: 'Noise Pollution', icon: 'volume-high-outline', value: 'noise' },
  { label: "Don't Know", icon: 'help-circle-outline', value: 'unknown' },
]

export default function UploadScreen() {
  const [uploadMode, setUploadMode] = useState<'file' | 'link'>('file')
  const [video, setVideo] = useState<any>(null)
  const [videoLink, setVideoLink] = useState('')
  const [location, setLocation] = useState('')
  const [locationUnknown, setLocationUnknown] = useState(false)
  const [selectedIssue, setSelectedIssue] = useState<string | null>(null)
  const { addComplaint } = useComplaints()

  const pickVideo = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync()
    if (!permission.granted) {
      Alert.alert('Permission needed', 'Please allow access to your gallery')
      return
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Videos,
    })
    if (!result.canceled) {
      setVideo(result.assets[0])
    }
  }

  const submitComplaint = () => {
    if (uploadMode === 'file' && !video) {
      Alert.alert('Missing video', 'Please select a video first')
      return
    }
    if (uploadMode === 'link' && !videoLink) {
      Alert.alert('Missing link', 'Please paste a video link')
      return
    }

    const complaintData = {
      video_url: uploadMode === 'link' ? videoLink : null,
      video_file_path: uploadMode === 'file' ? video?.uri : null,
      user_description: selectedIssue,
      user_location_text: locationUnknown ? null : location,
      timestamp: new Date().toISOString(),
    }

    console.log('Complaint Data:', JSON.stringify(complaintData, null, 2))

    const trackingId = addComplaint(locationUnknown ? 'Location unknown' : location)
    Alert.alert('Submitted!', 'Tracking ID: ' + trackingId)
    setVideo(null)
    setVideoLink('')
    setLocation('')
    setSelectedIssue(null)
    setLocationUnknown(false)
  }

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Ionicons name="shield-checkmark" size={28} color="#4ade80" />
        <Text style={styles.logoText}>CivicAlert</Text>
      </View>
      <Text style={styles.tagline}>Report violations. Drive change.</Text>

      {/* Upload Mode Toggle */}
      <Text style={styles.sectionLabel}>How do you want to submit?</Text>
      <View style={styles.toggleRow}>
        <TouchableOpacity
          style={[styles.toggleBtn, uploadMode === 'file' && styles.toggleBtnActive]}
          onPress={() => { setUploadMode('file'); setVideoLink(''); setVideo(null) }}
        >
          <Ionicons name="phone-portrait-outline" size={16} color={uploadMode === 'file' ? '#000' : '#aaa'} />
          <Text style={[styles.toggleText, uploadMode === 'file' && styles.toggleTextActive]}>
            Upload from Phone
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.toggleBtn, uploadMode === 'link' && styles.toggleBtnActive]}
          onPress={() => { setUploadMode('link'); setVideo(null) }}
        >
          <Ionicons name="link-outline" size={16} color={uploadMode === 'link' ? '#000' : '#aaa'} />
          <Text style={[styles.toggleText, uploadMode === 'link' && styles.toggleTextActive]}>
            Paste Video Link
          </Text>
        </TouchableOpacity>
      </View>

      {/* Upload from phone */}
      {uploadMode === 'file' && (
        <TouchableOpacity
          style={[styles.uploadBox, video && styles.uploadBoxDone]}
          onPress={pickVideo}
        >
          <Ionicons
            name={video ? 'checkmark-circle' : 'cloud-upload-outline'}
            size={48}
            color="#4ade80"
          />
          <Text style={styles.uploadText}>{video ? 'Video selected!' : 'Tap to upload video'}</Text>
          <Text style={styles.uploadSub}>{video ? 'Tap to change' : 'From your gallery'}</Text>
        </TouchableOpacity>
      )}

      {/* Paste link */}
      {uploadMode === 'link' && (
        <View style={styles.linkBox}>
          <Ionicons name="logo-instagram" size={20} color="#4ade80" />
          <Ionicons name="logo-youtube" size={20} color="#4ade80" />
          <TextInput
            style={styles.linkInput}
            placeholder="Paste Instagram or YouTube link here"
            placeholderTextColor="#555"
            value={videoLink}
            onChangeText={setVideoLink}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>
      )}

      {/* Issue Type — optional */}
      <Text style={styles.sectionLabel}>
        What is the issue? <Text style={styles.optional}>(optional)</Text>
      </Text>
      <View style={styles.issueGrid}>
        {ISSUE_TYPES.map((issue) => (
          <TouchableOpacity
            key={issue.value}
            style={[styles.issueCard, selectedIssue === issue.value && styles.issueCardSelected]}
            onPress={() => setSelectedIssue(selectedIssue === issue.value ? null : issue.value)}
          >
            <Ionicons
              name={issue.icon as any}
              size={22}
              color={selectedIssue === issue.value ? '#000' : '#4ade80'}
            />
            <Text style={[styles.issueLabel, selectedIssue === issue.value && styles.issueLabelSelected]}>
              {issue.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Location — optional */}
      <Text style={styles.sectionLabel}>
        Location <Text style={styles.optional}>(optional)</Text>
      </Text>
      <View style={[styles.inputWrapper, locationUnknown && styles.inputWrapperDisabled]}>
        <Ionicons name="location-outline" size={20} color="#4ade80" />
        <TextInput
          style={styles.input}
          placeholder="Enter location (e.g. Mandi, HP)"
          placeholderTextColor="#555"
          value={locationUnknown ? "Don't know" : location}
          onChangeText={setLocation}
          editable={!locationUnknown}
        />
      </View>
      <TouchableOpacity
        style={styles.unknownRow}
        onPress={() => {
          setLocationUnknown(!locationUnknown)
          if (!locationUnknown) setLocation('')
        }}
      >
        <View style={[styles.checkbox, locationUnknown && styles.checkboxChecked]}>
          {locationUnknown && <Ionicons name="checkmark" size={12} color="#000" />}
        </View>
        <Text style={styles.unknownText}>I don't know the location</Text>
      </TouchableOpacity>

      {/* Submit */}
      <TouchableOpacity style={styles.button} onPress={submitComplaint}>
        <Ionicons name="paper-plane-outline" size={20} color="#000" />
        <Text style={styles.buttonText}>Submit Complaint</Text>
      </TouchableOpacity>

      <View style={{ height: 100 }} />
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f', paddingHorizontal: 24, paddingTop: 60 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 4 },
  logoText: { fontSize: 26, fontWeight: 'bold', color: '#fff' },
  tagline: { fontSize: 13, color: '#555', marginBottom: 24 },
  sectionLabel: { fontSize: 13, color: '#aaa', marginBottom: 10, fontWeight: '600' },
  optional: { fontSize: 11, color: '#555', fontWeight: 'normal' },

  // Toggle
  toggleRow: { flexDirection: 'row', gap: 10, marginBottom: 16 },
  toggleBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, backgroundColor: '#1a1a1a', borderRadius: 12,
    borderWidth: 1, borderColor: '#2a2a2a', paddingVertical: 12,
  },
  toggleBtnActive: { backgroundColor: '#4ade80', borderColor: '#4ade80' },
  toggleText: { color: '#aaa', fontSize: 12, fontWeight: '600' },
  toggleTextActive: { color: '#000' },

  // Upload box
  uploadBox: {
    borderWidth: 2, borderColor: '#222', borderStyle: 'dashed',
    borderRadius: 16, height: 160, justifyContent: 'center',
    alignItems: 'center', backgroundColor: '#1a1a1a', gap: 8, marginBottom: 24,
  },
  uploadBoxDone: { borderColor: '#4ade80' },
  uploadText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  uploadSub: { color: '#555', fontSize: 12 },

  // Link box
  linkBox: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#1a1a1a', borderRadius: 12, borderWidth: 1,
    borderColor: '#2a2a2a', paddingHorizontal: 14, marginBottom: 24, minHeight: 56,
  },
  linkInput: { flex: 1, paddingVertical: 14, fontSize: 13, color: '#fff' },

  // Issue grid
  issueGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 },
  issueCard: {
    width: '47%', backgroundColor: '#1a1a1a', borderRadius: 12,
    borderWidth: 1, borderColor: '#2a2a2a', padding: 14,
    alignItems: 'center', gap: 8,
  },
  issueCardSelected: { backgroundColor: '#4ade80', borderColor: '#4ade80' },
  issueLabel: { color: '#aaa', fontSize: 12, textAlign: 'center' },
  issueLabelSelected: { color: '#000', fontWeight: 'bold' },

  // Location
  inputWrapper: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#1a1a1a', borderRadius: 12, borderWidth: 1,
    borderColor: '#222', paddingHorizontal: 14, marginBottom: 10,
  },
  inputWrapperDisabled: { opacity: 0.4 },
  input: { flex: 1, paddingVertical: 14, fontSize: 14, color: '#fff' },
  unknownRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20 },
  checkbox: {
    width: 20, height: 20, borderRadius: 4, borderWidth: 1,
    borderColor: '#555', justifyContent: 'center', alignItems: 'center',
  },
  checkboxChecked: { backgroundColor: '#4ade80', borderColor: '#4ade80' },
  unknownText: { color: '#aaa', fontSize: 13 },

  // Submit
  button: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 8, backgroundColor: '#4ade80', padding: 16, borderRadius: 12,
  },
  buttonText: { color: '#000', fontWeight: 'bold', fontSize: 16 },
})