import { Ionicons } from '@expo/vector-icons'
import { Tabs } from 'expo-router'
import { ComplaintProvider } from './ComplaintContext'

export default function TabLayout() {
  return (
    <ComplaintProvider>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarStyle: { backgroundColor: '#0f0f0f', borderTopColor: '#222' },
          tabBarActiveTintColor: '#4ade80',
          tabBarInactiveTintColor: '#555',
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            tabBarLabel: 'Upload',
            tabBarIcon: ({ color }) => (
              <Ionicons name="cloud-upload-outline" size={24} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="explore"
          options={{
            tabBarLabel: 'Track',
            tabBarIcon: ({ color }) => (
              <Ionicons name="list-outline" size={24} color={color} />
            ),
          }}
        />
      </Tabs>
    </ComplaintProvider>
  )
}