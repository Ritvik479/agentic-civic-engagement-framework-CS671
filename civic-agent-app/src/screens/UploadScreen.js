import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  StyleSheet,
} from 'react-native';
import { VideoView } from 'expo-video';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import * as AudioModule from 'expo-audio';
import { Camera, UploadCloud, MapPin } from 'lucide-react-native';
import { StatusBar } from 'react-native';
const API_URL = process.env.EXPO_PUBLIC_API_URL;

export default function UploadScreen({ navigation }) {
  const [video, setVideo] = useState(null);
  const [location, setLocation] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isFetchingLocation, setIsFetchingLocation] = useState(false);

  // 🎥 Capture
  const handleCaptureVideo = async () => {
    try {
      const cameraPermission = await ImagePicker.requestCameraPermissionsAsync();
      if (cameraPermission.status !== 'granted') {
        return Alert.alert('Permission Needed', 'Camera required');
      }

      const micPermission = await AudioModule.requestRecordingPermissionsAsync();
      if (!micPermission.granted) {
        return Alert.alert('Permission Needed', 'Microphone required');
      }

      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ['videos'],
        quality: 1,
      });

      if (!result.canceled) {
        setVideo(result.assets[0]);
        requestLocation();
      }
    } catch (err) {
      Alert.alert('Error', 'Camera failed');
    }
  };

  // 📁 Gallery
  const handlePickFromGallery = async () => {
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (permission.status !== 'granted') {
        return Alert.alert('Permission Needed', 'Gallery required');
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['videos'],
      });

      if (!result.canceled) {
        setVideo(result.assets[0]);
        requestLocation();
      }
    } catch (err) {
      Alert.alert('Error', 'Gallery failed');
    }
  };

  // 📍 Location
  const requestLocation = async () => {
    try {
      setIsFetchingLocation(true);

      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        return Alert.alert('Permission Needed', 'Location required');
      }

      const loc = await Location.getCurrentPositionAsync({});
      setLocation(loc.coords);
    } catch {
      Alert.alert('Error', 'Location failed');
    } finally {
      setIsFetchingLocation(false);
    }
  };

  // 🔄 Reset
  const resetAll = () => {
    setVideo(null);
    setLocation(null);
  };

  // 🚀 Submit
  const handleFinalSubmit = async () => {
    if (!video || !location) {
      return Alert.alert("Incomplete", "Video + location required");
    }

    if (isUploading) return;

    setIsUploading(true);

    try {
      const formData = new FormData();

        formData.append('video', {
            uri: video.uri,
            name: video.fileName ?? 'upload.mp4',
            type: video.mimeType ?? 'video/mp4',
        });

      formData.append('latitude', String(location.latitude));
      formData.append('longitude', String(location.longitude));

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 300000);



      const response = await fetch(`${process.env.EXPO_PUBLIC_API_URL}/process`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
    });

clearTimeout(timeout);

if (!response.ok) throw new Error('Upload failed');

const res = await response.json();

console.log("BACKEND RESPONSE:", res);

const jobId = res.data.jobId;
if (!res.success) {
  Alert.alert("Error", res.error?.message || "Failed");
  return;
}



navigation.navigate('Processing', { jobId });

    } catch (err) {
      if (err.name === 'AbortError') {
        Alert.alert("Timeout", "Server took too long");
      } else {
        Alert.alert("Upload Failed", "Check backend");
      }
    } finally {
      setIsUploading(false);
    }
  };

// ONLY UI CHANGED — keep your existing logic functions

return (
  <View style={styles.container}>
    <StatusBar barStyle="light-content" />

    {/* 🔰 Header */}
    <View style={styles.header}>
      <Text style={styles.title}>NEW REPORT</Text>
    </View>

    {!video ? (
      <View style={styles.center}>
        {/* 🎥 Capture */}
        <TouchableOpacity onPress={handleCaptureVideo} style={styles.mainBtn}>
          <Camera color="#fff" size={40} />
        </TouchableOpacity>

        <Text style={styles.ctaText}>Record Video</Text>
        <Text style={styles.subText}>Capture issue directly</Text>

        {/* 📁 Gallery */}
        <TouchableOpacity
          onPress={handlePickFromGallery}
          style={styles.secondaryBtn}
        >
          <Text style={styles.secondaryText}>Pick from Gallery</Text>
        </TouchableOpacity>
      </View>
    ) : (
      <View style={styles.previewContainer}>
        <VideoView
          source={{ uri: video.uri }}
          style={styles.video}
          nativeControls
        />

        <TouchableOpacity onPress={resetAll}>
          <Text style={styles.changeText}>Change Video</Text>
        </TouchableOpacity>

        {/* 📍 Location */}
        <View style={styles.locationBox}>
          {isFetchingLocation ? (
            <ActivityIndicator color="#fff" />
          ) : location ? (
            <Text style={styles.locationText}>
              📍 {location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}
            </Text>
          ) : (
            <TouchableOpacity onPress={requestLocation}>
              <Text style={styles.retryText}>Retry Location</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* 🚀 Submit */}
        <TouchableOpacity
          onPress={handleFinalSubmit}
          disabled={!location || isUploading}
          style={[
            styles.submitBtn,
            (!location || isUploading) && styles.disabledBtn,
          ]}
        >
          {isUploading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.submitText}>Submit Report</Text>
          )}
        </TouchableOpacity>
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

  mainBtn: {
    width: 100,
    height: 100,
    borderRadius: 20,
    backgroundColor: '#c0392b',
    justifyContent: 'center',
    alignItems: 'center',
  },

  ctaText: {
    fontSize: 18,
    color: '#e6ddd0',
    marginTop: 16,
    fontWeight: '700',
  },

  subText: {
    color: '#7a7164',
    marginTop: 6,
  },

  secondaryBtn: {
    marginTop: 20,
    padding: 12,
    borderRadius: 10,
    backgroundColor: '#252320',
  },

  secondaryText: {
    color: '#c9952a',
  },

  previewContainer: {
    flex: 1,
    alignItems: 'center',
  },

  video: {
    width: '100%',
    height: 220,
    borderRadius: 12,
    backgroundColor: '#000',
  },

  changeText: {
    color: '#c0392b',
    marginTop: 10,
  },

  locationBox: {
    marginTop: 16,
    padding: 10,
    backgroundColor: '#252320',
    borderRadius: 10,
  },

  locationText: {
    color: '#e6ddd0',
    fontSize: 12,
  },

  retryText: {
    color: '#c9952a',
  },

  submitBtn: {
    marginTop: 20,
    backgroundColor: '#27ae60',
    paddingVertical: 14,
    borderRadius: 30,
    width: '100%',
    alignItems: 'center',
  },

  disabledBtn: {
    backgroundColor: '#555',
  },

  submitText: {
    color: '#fff',
    fontWeight: '700',
  },
});