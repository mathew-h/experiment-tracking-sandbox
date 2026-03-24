import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from '@/layouts/AppLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import { ProtectedRoute } from '@/auth/ProtectedRoute'
import { LoginPage } from '@/pages/Login'
import { DashboardPage } from '@/pages/Dashboard'
import { ExperimentListPage } from '@/pages/ExperimentList'
import { ExperimentDetailPage } from '@/pages/ExperimentDetail'
import { NewExperimentPage } from '@/pages/NewExperiment'
import { BulkUploadsPage } from '@/pages/BulkUploads'
import { SamplesPage } from '@/pages/Samples'
import { SampleDetailPage } from '@/pages/SampleDetail'
import { ChemicalsPage } from '@/pages/Chemicals'
import { AnalysisPage } from '@/pages/Analysis'

/** Root component: sets up React Query, React Router, and the auth/toast providers. */
export default function App() {
  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        {/* Auth routes */}
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<LoginPage />} />
        </Route>

        {/* Protected app routes */}
        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="/experiments" element={<ExperimentListPage />} />
          <Route path="/experiments/new" element={<NewExperimentPage />} />
          <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
          <Route path="/bulk-uploads" element={<BulkUploadsPage />} />
          <Route path="/samples" element={<SamplesPage />} />
          <Route path="/samples/:sampleId" element={<SampleDetailPage />} />
          <Route path="/chemicals" element={<ChemicalsPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  )
}
