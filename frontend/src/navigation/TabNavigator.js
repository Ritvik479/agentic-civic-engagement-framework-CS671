import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';

import HomeScreen from '../screens/HomeScreen';
import UploadScreen from '../screens/UploadScreen';
import TasksScreen from '../screens/TasksScreen';

import { LayoutDashboard, Video, ClipboardList } from 'lucide-react-native';

const Tab = createBottomTabNavigator();

export default function TabNavigator() {
  return (
    <Tab.Navigator
      screenOptions={{
        tabBarActiveTintColor: '#c9952a',
        tabBarInactiveTintColor: '#7a7164',
        tabBarStyle: {
          backgroundColor: '#1c1a17',
          borderTopColor: '#2a2820',
        },
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

      {/* 🎥 New Complaint */}
      <Tab.Screen
        name="New Complaint"
        component={UploadScreen}
        options={{
          tabBarIcon: ({ color, size }) => (
            <Video color={color} size={size} />
          ),
        }}
      />

      {/* 📋 Processing */}
      <Tab.Screen
        name="Processing"
        component={TasksScreen}
        options={{
          tabBarIcon: ({ color, size }) => (
            <ClipboardList color={color} size={size} />
          ),
        }}
      />
    </Tab.Navigator>
  );
}