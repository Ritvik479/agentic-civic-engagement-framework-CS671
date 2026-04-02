import { createContext, useContext, useState } from 'react'

const ComplaintContext = createContext<any>(null)

export function ComplaintProvider({ children }: any) {
  const [complaints, setComplaints] = useState<any[]>([])

  const addComplaint = (location: string, issueType: string) => {
    const newId = 'CMP' + Math.floor(Math.random() * 9000 + 1000)
    const issueLabels: any = {
      garbage: 'Garbage / Waste Dumping',
      sewage: 'Water / Sewage Issue',
      pollution: 'Air / Industrial Pollution',
      road: 'Road / Infrastructure Damage',
      noise: 'Noise Pollution',
      ai: 'Civic Violation (AI to classify)',
    }
    const newComplaint = {
      id: newId,
      issue: issueLabels[issueType] || 'Civic Violation',
      issueType,
      location,
      status: 'Submitted',
      color: '#f0a500',
    }
    setComplaints(prev => [newComplaint, ...prev])
    return newId
  }

  return (
    <ComplaintContext.Provider value={{ complaints, addComplaint }}>
      {children}
    </ComplaintContext.Provider>
  )
}

export function useComplaints() {
  return useContext(ComplaintContext)
}