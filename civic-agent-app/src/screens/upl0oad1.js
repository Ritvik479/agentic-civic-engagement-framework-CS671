import React, { useState } from 'react';
import { 
  View, 
  Text, 
  TouchableOpacity, 
  Alert, 
  ActivityIndicator 
} from 'react-native';

import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { Video } from 'expo-av';

import { Camera, UploadCloud, MapPin } from 'lucide-react-native';

export default function UploadScreen({ navigation }) {
  const [video, setVideo] = useState(null);
  const [location, setLocation] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isFetchingLocation, setIsFetchingLocation] = useState(false);

  // 🎥 Capture Video from Camera
  const handleCaptureVideo = async () => {
    try {
      // Permissions
      const camPerm = await ImagePicker.requestCameraPermissionsAsync();
      const micPerm = await ImagePicker.requestMediaLibraryPermissionsAsync();

      if (camPerm.status !== 'granted') {
        Alert.alert("Permission Needed", "Camera access is required.");
        return;
      }

      let result = await ImagePicker.launchCameraAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Videos,
        allowsEditing: true,
        quality: 1,
      });

      if (!result.canceled) {
        const vid = result.assets[0];
        setVideo(vid);
        requestLocation();
      }
    } catch (err) {
      Alert.alert("Error", "Failed to open camera");
    }
  };

  // 📁 Pick Video from Gallery
  const handlePickFromGallery = async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (perm.status !== 'granted') {
        Alert.alert("Permission Needed", "Gallery access is required.");
        return;
      }

      let result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Videos,
      });

      if (!result.canceled) {
        const vid = result.assets[0];
        setVideo(vid);
        requestLocation();
      }
    } catch (err) {
      Alert.alert("Error", "Failed to open gallery");
    }
  };

  // 📍 Get GPS Location
  const requestLocation = async () => {
    try {
      setIsFetchingLocation(true);

      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert("Permission Needed", "Enable location to tag complaint.");
        setIsFetchingLocation(false);
        return;
      }

      let loc = await Location.getCurrentPositionAsync({});
      setLocation(loc.coords);
    } catch (err) {
      Alert.alert("Error", "Could not fetch location");
    } finally {
      setIsFetchingLocation(false);
    }
  };

  // 🚀 Submit
  const handleFinalSubmit = async () => {
    if (!video || !location) {
      Alert.alert("Incomplete", "Video and location required.");
      return;
    }

    setIsUploading(true);

    try {
      // 🔥 Prepare payload (for future backend)
      const payload = {
        videoUri: video.uri,
        location,
        timestamp: new Date().toISOString(),
      };

      console.log("UPLOAD PAYLOAD:", payload);

      // ⏳ Simulate API call
      setTimeout(() => {
        setIsUploading(false);
        navigation.navigate('Processing');
      }, 1500);

    } catch (err) {
      Alert.alert("Upload Failed", "Try again.");
      setIsUploading(false);
    }
  };

  return (
    <View style={styles.container}>

      {!video ? (
        <>
          <TouchableOpacity onPress={handleCaptureVideo} style={styles.uploadBtn}>
            <Camera color="#fff" size={40} />
            <Text style={styles.btnText}>Record Video</Text>
          </TouchableOpacity>

          <TouchableOpacity onPress={handlePickFromGallery} style={styles.secondaryBtn}>
            <UploadCloud color="#2563eb" size={30} />
            <Text style={{ color: '#2563eb', marginTop: 5 }}>Pick from Gallery</Text>
          </TouchableOpacity>
        </>
      ) : (
        <View style={styles.previewCard}>

          {/* 🎥 Video Preview */}
          <Video
            source={{ uri: video.uri }}
            style={styles.video}
            useNativeControls
            resizeMode="contain"
          />

          {/* 📍 Location */}
          <View style={{ marginTop: 10 }}>
            {isFetchingLocation ? (
              <Text>Fetching location...</Text>
            ) : location ? (
              <Text style={styles.locationText}>
                📍 {location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}
              </Text>
            ) : (
              <TouchableOpacity onPress={requestLocation}>
                <Text style={{ color: 'red' }}>Retry Location</Text>
              </TouchableOpacity>
            )}
          </View>

          {/* 🚀 Submit */}
          <TouchableOpacity
            onPress={handleFinalSubmit}
            disabled={!location || isUploading}
            style={[
              styles.submitBtn,
              (!location || isUploading) && { backgroundColor: '#ccc' }
            ]}
          >
            {isUploading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.btnText}>Submit Complaint</Text>
            )}
          </TouchableOpacity>

        </View>
      )}
    </View>
  );
}

// 🎨 Styles
const styles = {
  container: {
    flex: 1,
    padding: 20,
    justifyContent: 'center',
    alignItems: 'center'
  },
  uploadBtn: {
    backgroundColor: '#2563eb',
    padding: 40,
    borderRadius: 20,
    alignItems: 'center',
    width: '100%'
  },
  secondaryBtn: {
    marginTop: 20,
    padding: 20,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: '#2563eb',
    alignItems: 'center',
    width: '100%'
  },
  previewCard: {
    padding: 15,
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 15,
    width: '100%',
    alignItems: 'center'
  },
  video: {
    width: '100%',
    height: 200,
    borderRadius: 10
  },
  submitBtn: {
    backgroundColor: '#059669',
    padding: 15,
    borderRadius: 10,
    marginTop: 20,
    width: '100%',
    alignItems: 'center'
  },
  btnText: {
    color: '#fff',
    marginTop: 10
  },
  locationText: {
    fontSize: 12,
    color: 'gray'
  }
};