import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  ActivityIndicator,
  StatusBar,
  Modal,
  FlatList,
} from 'react-native';
import { VideoView } from 'expo-video';
import * as ImagePicker from 'expo-image-picker';
import * as AudioModule from 'expo-audio';
import { Camera, Link, Image as ImageIcon, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react-native';

import { INDIA_STATES } from '../constants/india';

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
  inputBg: '#1e1c19',
};

const TOTAL_STEPS = 3;

function StepIndicator({ current }) {
  const labels = ['Your Details', 'Issue & Media', 'Location'];
  return (
    <View style={ind.row}>
      {labels.map((label, i) => {
        const step = i + 1;
        const active = step === current;
        const done = step < current;
        return (
          <React.Fragment key={step}>
            <View style={ind.item}>
              <View style={[ind.circle, active && ind.circleActive, done && ind.circleDone]}>
                <Text style={[ind.num, (active || done) && ind.numActive]}>
                  {done ? '✓' : step}
                </Text>
              </View>
              <Text style={[ind.label, active && ind.labelActive]}>{label}</Text>
            </View>
            {i < labels.length - 1 && (
              <View style={[ind.line, done && ind.lineDone]} />
            )}
          </React.Fragment>
        );
      })}
    </View>
  );
}

const ind = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginBottom: 28 },
  item: { alignItems: 'center', width: 72 },
  circle: { width: 28, height: 28, borderRadius: 14, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.border, justifyContent: 'center', alignItems: 'center', marginBottom: 4 },
  circleActive: { borderColor: COLORS.primary, backgroundColor: COLORS.primary },
  circleDone: { borderColor: COLORS.success, backgroundColor: COLORS.success },
  num: { fontSize: 11, fontWeight: '700', color: COLORS.muted },
  numActive: { color: '#fff' },
  label: { fontSize: 9, color: COLORS.muted, textAlign: 'center', fontWeight: '500' },
  labelActive: { color: COLORS.primary },
  line: { flex: 1, height: 1, backgroundColor: COLORS.border, marginBottom: 20 },
  lineDone: { backgroundColor: COLORS.success },
});

function Field({ label, optional, ...props }) {
  return (
    <View style={f.wrap}>
      <Text style={f.label}>
        {label}
        {optional && <Text style={f.opt}> (optional)</Text>}
      </Text>
      <TextInput
        style={f.input}
        placeholderTextColor={COLORS.muted}
        {...props}
      />
    </View>
  );
}

const f = StyleSheet.create({
  wrap: { marginBottom: 16 },
  label: { fontSize: 12, color: COLORS.muted, marginBottom: 6, fontWeight: '600', letterSpacing: 0.5 },
  opt: { fontWeight: '400', color: COLORS.muted },
  input: {
    backgroundColor: COLORS.inputBg,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 11,
    color: COLORS.foreground,  // ✅ FIX B: text is now visible (light color)
    fontSize: 14,
  },
});

function StatePicker({ value, onChange }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <View style={f.wrap}>
        <Text style={f.label}>STATE</Text>
        <TouchableOpacity style={[f.input, sp.trigger]} onPress={() => setOpen(true)} activeOpacity={0.7}>
          <Text style={value ? { color: COLORS.foreground, fontSize: 14 } : { color: COLORS.muted, fontSize: 14 }}>
            {value || 'Select state…'}
          </Text>
          <ChevronDown color={COLORS.muted} size={16} />
        </TouchableOpacity>
      </View>
      <Modal visible={open} animationType="slide" transparent>
        <View style={sp.overlay}>
          <View style={sp.sheet}>
            <Text style={sp.sheetTitle}>Select State / UT</Text>
            <FlatList
              data={INDIA_STATES}
              keyExtractor={(item) => item}
              renderItem={({ item }) => (
                <TouchableOpacity style={[sp.option, item === value && sp.optionActive]} onPress={() => { onChange(item); setOpen(false); }}>
                  <Text style={[sp.optionText, item === value && sp.optionTextActive]}>{item}</Text>
                </TouchableOpacity>
              )}
            />
            <TouchableOpacity style={sp.cancel} onPress={() => setOpen(false)}>
              <Text style={sp.cancelText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </>
  );
}

const sp = StyleSheet.create({
  trigger: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: COLORS.card, borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: '75%', padding: 20 },
  sheetTitle: { color: COLORS.primary, fontWeight: '800', fontSize: 14, letterSpacing: 1, marginBottom: 12, textAlign: 'center' },
  option: { paddingVertical: 13, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  optionActive: { backgroundColor: '#2e2b26' },
  optionText: { color: COLORS.foreground, fontSize: 14 },
  optionTextActive: { color: COLORS.primary, fontWeight: '700' },
  cancel: { marginTop: 12, alignItems: 'center', padding: 12 },
  cancelText: { color: COLORS.accent, fontWeight: '700' },
});

export default function UploadScreen({ navigation }) {
  const [step, setStep] = useState(1);
  const [isUploading, setIsUploading] = useState(false);

  // Step 1
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');

  // Step 2
  const [issueDescription, setIssueDescription] = useState('');
  const [mediaMode, setMediaMode] = useState(null);
  const [video, setVideo] = useState(null);
  const [photo, setPhoto] = useState(null);
  const [mediaUrl, setMediaUrl] = useState('');

  // Step 3
  const [state, setState] = useState('');
  const [district, setDistrict] = useState('');
  const [landmark, setLandmark] = useState('');

  const validateStep = () => {
    if (step === 1) {
      if (!name.trim()) { Alert.alert('Required', 'Please enter your name.'); return false; }
      if (!email.trim()) { Alert.alert('Required', 'Please enter your email.'); return false; }
      if (!phone.trim()) { Alert.alert('Required', 'Please enter your phone number.'); return false; }
      const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
      if (!emailOk) { Alert.alert('Invalid', 'Please enter a valid email address.'); return false; }
      const phoneOk = /^[6-9]\d{9}$/.test(phone.trim());
      if (!phoneOk) { Alert.alert('Invalid', 'Please enter a valid 10-digit Indian mobile number.'); return false; }
    }

    // ✅ FIX A: evidence is now compulsory on step 2
    if (step === 2) {
      const hasMedia = video || photo || mediaUrl.trim();
      if (!hasMedia) {
        Alert.alert('Evidence Required', 'Please attach a video, photo, or URL as evidence before proceeding.');
        return false;
      }
    }

    if (step === 3) {
      if (!state) { Alert.alert('Required', 'Please select a state.'); return false; }
      if (!district.trim()) { Alert.alert('Required', 'Please enter a district.'); return false; }
    }
    return true;
  };

  const goNext = () => { if (validateStep()) setStep(s => s + 1); };
  const goBack = () => setStep(s => s - 1);

  const handleCaptureVideo = async () => {
    try {
      const camPerm = await ImagePicker.requestCameraPermissionsAsync();
      if (camPerm.status !== 'granted') { Alert.alert('Permission Needed', 'Camera access required.'); return; }
      const micPerm = await AudioModule.requestRecordingPermissionsAsync();
      if (!micPerm.granted) { Alert.alert('Permission Needed', 'Microphone access required.'); return; }
      const result = await ImagePicker.launchCameraAsync({ mediaTypes: ['videos'], quality: 1 });
      if (!result.canceled) { setVideo(result.assets[0]); setPhoto(null); setMediaMode('file'); }
    } catch {
      Alert.alert('Error', 'Camera failed.');
    }
  };

  const handlePickMedia = async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (perm.status !== 'granted') { Alert.alert('Permission Needed', 'Gallery access required.'); return; }
      const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['videos', 'images'] });
      if (!result.canceled) {
        const asset = result.assets[0];
        if (asset.type === 'image') { setPhoto(asset); setVideo(null); }
        else { setVideo(asset); setPhoto(null); }
        setMediaMode('file');
      }
    } catch {
      Alert.alert('Error', 'Gallery failed.');
    }
  };

  const clearMedia = () => { setVideo(null); setPhoto(null); setMediaUrl(''); setMediaMode(null); };

  const handleSubmit = async () => {
    if (!validateStep()) return;
    if (isUploading) return;
    setIsUploading(true);

    try {
      const formData = new FormData();
      formData.append('name', name.trim());
      formData.append('email', email.trim());
      formData.append('phone', phone.trim());
      formData.append('user_issue_description', issueDescription.trim());
      formData.append('state', state);
      formData.append('district', district.trim());
      formData.append('landmark', landmark.trim());

      if (video) {
        formData.append('video', { uri: video.uri, name: video.fileName ?? 'upload.mp4', type: video.mimeType ?? 'video/mp4' });
      } else if (photo) {
        formData.append('video', { uri: photo.uri, name: photo.fileName ?? 'upload.jpg', type: photo.mimeType ?? 'image/jpeg' });
      } else if (mediaUrl.trim()) {
        formData.append('video_url', mediaUrl.trim());
      }

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 300000);
      const response = await fetch(`${API_URL}/process`, { method: 'POST', body: formData, signal: controller.signal });
      clearTimeout(timeout);
      const res = await response.json();

      if (!response.ok || !res.id) { Alert.alert('Error', res.detail || 'Submission failed.'); return; }

      navigation.navigate('Processing', { trackingId: res.id });

      // Reset form after successful submission
      setStep(1);
      setName('');
      setEmail('');
      setPhone('');
      setIssueDescription('');
      setMediaMode(null);
      setVideo(null);
      setPhoto(null);
      setMediaUrl('');
      setState('');
      setDistrict('');
      setLandmark('');

    } catch (err) {
      if (err.name === 'AbortError') {
        Alert.alert('Timeout', 'Server took too long. Please try again.');
      } else {
        Alert.alert('Upload Failed', 'Could not reach the server. Check your connection.');
      }
    } finally {
      setIsUploading(false);
    }
  };

  const renderStep1 = () => (
    <ScrollView showsVerticalScrollIndicator={false}>
      <Text style={s.stepHeading}>Your Details</Text>
      <Text style={s.stepSub}>This information is used to file the complaint on your behalf.</Text>
      <Field label="FULL NAME" placeholder="e.g. Ravi Sharma" value={name} onChangeText={setName} autoCapitalize="words" />
      <Field label="EMAIL ADDRESS" placeholder="e.g. ravi@gmail.com" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
      <Field label="PHONE NUMBER" placeholder="10-digit mobile number" value={phone} onChangeText={setPhone} keyboardType="phone-pad" maxLength={10} />
    </ScrollView>
  );

  const renderStep2 = () => (
    <ScrollView showsVerticalScrollIndicator={false}>
      <Text style={s.stepHeading}>Issue & Evidence</Text>
      <Text style={s.stepSub}>Describe the issue and attach evidence.</Text>

      {/* ✅ FIX B: description box — color is set to foreground so typed text is visible */}
      <View style={f.wrap}>
        <Text style={f.label}>
          DESCRIBE THE ISSUE <Text style={f.opt}>(optional)</Text>
        </Text>
        <TextInput
          style={[f.input, { height: 100, textAlignVertical: 'top', color: COLORS.foreground }]}
          placeholder="e.g. Open drain near the main market causing flooding..."
          placeholderTextColor={COLORS.muted}
          value={issueDescription}
          onChangeText={setIssueDescription}
          multiline
          numberOfLines={4}
        />
      </View>

      {/* ✅ FIX A: label now says REQUIRED not optional */}
      <Text style={f.label}>
        EVIDENCE <Text style={s.required}>*required</Text>
      </Text>

      {!mediaMode && (
        <View style={s.mediaOptions}>
          <TouchableOpacity style={s.mediaBtn} onPress={handleCaptureVideo} activeOpacity={0.7}>
            <Camera color={COLORS.primary} size={22} />
            <Text style={s.mediaBtnText}>Record Video</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.mediaBtn} onPress={handlePickMedia} activeOpacity={0.7}>
            <ImageIcon color={COLORS.primary} size={22} />
            <Text style={s.mediaBtnText}>Gallery</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.mediaBtn} onPress={() => setMediaMode('url')} activeOpacity={0.7}>
            <Link color={COLORS.primary} size={22} />
            <Text style={s.mediaBtnText}>Paste URL</Text>
          </TouchableOpacity>
        </View>
      )}

      {mediaMode === 'url' && (
        <View style={s.urlRow}>
          <TextInput
            style={[f.input, { flex: 1 }]}
            placeholder="https://youtube.com/..."
            placeholderTextColor={COLORS.muted}
            value={mediaUrl}
            onChangeText={setMediaUrl}
            autoCapitalize="none"
            keyboardType="url"
          />
          <TouchableOpacity onPress={clearMedia} style={s.clearBtn}>
            <Text style={s.clearText}>✕</Text>
          </TouchableOpacity>
        </View>
      )}

      {mediaMode === 'file' && (video || photo) && (
        <View style={s.filePreview}>
          <Text style={s.filePreviewText}>
            {video ? '🎥 ' : '📷 '}
            {(video || photo).fileName ?? (video ? 'video selected' : 'photo selected')}
          </Text>
          <TouchableOpacity onPress={clearMedia}>
            <Text style={s.clearText}>✕ Change</Text>
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  );

  const renderStep3 = () => (
    <ScrollView showsVerticalScrollIndicator={false}>
      <Text style={s.stepHeading}>Location</Text>
      <Text style={s.stepSub}>Where did this issue occur?</Text>
      <StatePicker value={state} onChange={setState} />
      <Field label="DISTRICT" placeholder="e.g. Jhansi" value={district} onChangeText={setDistrict} autoCapitalize="words" />
      <Field label="LANDMARK / AREA / VILLAGE" optional placeholder="e.g. Near Collectorate, Babina Road" value={landmark} onChangeText={setLandmark} autoCapitalize="sentences" />
    </ScrollView>
  );

  return (
    <View style={s.container}>
      <StatusBar barStyle="light-content" />
      <View style={s.header}>
        <Text style={s.title}>NEW REPORT</Text>
      </View>

      <StepIndicator current={step} />

      <View style={s.content}>
        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}
        {step === 3 && renderStep3()}
      </View>

      <View style={s.navRow}>
        {step > 1 ? (
          <TouchableOpacity style={s.backBtn} onPress={goBack} activeOpacity={0.7}>
            <ChevronLeft color={COLORS.primary} size={18} />
            <Text style={s.backText}>Back</Text>
          </TouchableOpacity>
        ) : (
          <View />
        )}

        {step < TOTAL_STEPS ? (
          <TouchableOpacity style={s.nextBtn} onPress={goNext} activeOpacity={0.8}>
            <Text style={s.nextText}>Next</Text>
            <ChevronRight color="#fff" size={18} />
          </TouchableOpacity>
        ) : (
          <TouchableOpacity
            style={[s.nextBtn, s.submitBtn, isUploading && s.disabledBtn]}
            onPress={handleSubmit}
            disabled={isUploading}
            activeOpacity={0.8}
          >
            {isUploading ? <ActivityIndicator color="#fff" /> : <Text style={s.nextText}>Submit</Text>}
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg, padding: 20 },
  header: { marginTop: 40, marginBottom: 24 },
  title: { fontSize: 18, fontWeight: '800', color: COLORS.primary, letterSpacing: 2 },
  content: { flex: 1 },
  stepHeading: { fontSize: 20, fontWeight: '800', color: COLORS.foreground, marginBottom: 6 },
  stepSub: { fontSize: 13, color: COLORS.muted, marginBottom: 24, lineHeight: 18 },
  required: { color: COLORS.accent, fontWeight: '700' },  // ✅ red *required label
  mediaOptions: { flexDirection: 'row', gap: 10, marginTop: 4 },
  mediaBtn: { flex: 1, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.border, borderRadius: 10, paddingVertical: 14, alignItems: 'center', gap: 6 },
  mediaBtnText: { fontSize: 11, color: COLORS.primary, fontWeight: '600' },
  urlRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  filePreview: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: COLORS.card, padding: 12, borderRadius: 10, marginTop: 4 },
  filePreviewText: { color: COLORS.foreground, fontSize: 13, flex: 1, marginRight: 8 },
  clearBtn: { padding: 4 },
  clearText: { color: COLORS.accent, fontWeight: '700', fontSize: 13 },
  navRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 16, paddingTop: 12, borderTopWidth: 1, borderTopColor: COLORS.border },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, padding: 10 },
  backText: { color: COLORS.primary, fontWeight: '600' },
  nextBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.primary, paddingVertical: 12, paddingHorizontal: 24, borderRadius: 10 },
  submitBtn: { backgroundColor: COLORS.success },
  disabledBtn: { backgroundColor: COLORS.muted },
  nextText: { color: '#fff', fontWeight: '700', fontSize: 14 },
});