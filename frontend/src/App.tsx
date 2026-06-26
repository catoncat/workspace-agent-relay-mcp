import { Navigate, Route, Routes } from 'react-router-dom'
import { RelayPage } from '@/pages/RelayPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RelayPage />} />
      <Route path="/c/:conversationId" element={<RelayPage />} />
      <Route path="/c/:conversationId/r/:runId" element={<RelayPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
