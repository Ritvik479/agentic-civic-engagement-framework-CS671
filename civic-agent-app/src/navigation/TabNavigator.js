import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';

import HomeScreen from '../screens/HomeScreen';
import UploadScreen from '../screens/UploadScreen';
import TasksScreen from '../screens/TasksScreen';

// Icons
import { LayoutDashboard, Video, Loader2 } from 'lucide-react-native';

const Tab = createBottomTabNavigator();

export default function TabNavigator() {
  return (
    <Tab.Navigator
      screenOptions={{
        tabBarActiveTintColor: '#2563eb',
        headerShown: false,
      }}
    >
      {/* 🏠 Dashboard */}
      <Tab.Screen
        name="Dashboard"
        component={HomeScreen}
        options={{
          tabBarIcon: ({ color, size }) => (
            <LayoutDashboard color={color} size={size} />
          ),
        }}
      />

      {/* 🎥 Upload */}
      <Tab.Screen
        name="New Complaint"
        component={UploadScreen}
        options={{
          tabBarIcon: ({ color, size }) => (
            <Video color={color} size={size} />
          ),
        }}
      />

      {/* ⚙️ Processing */}
      <Tab.Screen
        name="Processing"
        component={TasksScreen}
        options={{
          tabBarIcon: ({ color, size }) => (
            <Loader2 color={color} size={size} />
          ),
        }}
      />
    </Tab.Navigator>
  );
}