import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from '@/layouts/AppLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import { ProtectedRoute } from '@/auth/ProtectedRoute'
import { LoginPage } from '@/pages/Login'
import { DashboardPage } from '@/pages/Dashboard'
import { ExperimentListPage } from '@/pages/ExperimentList'
import { ExperimentDetailPage } from '@/pages/ExperimentDetail'
import { ReplicateGroupPage } from '@/pages/ReplicateGroup'
import { NewExperimentPage } from '@/pages/NewExperiment'
import { BulkUploadsPage } from '@/pages/BulkUploads'
import { SamplesPage } from '@/pages/Samples'
import { SampleDetailPage } from '@/pages/SampleDetail'
import { ChemicalsPage } from '@/pages/Chemicals'
import { DataExportPage } from '@/pages/DataExport'
import { AnalysisPage } from '@/pages/Analysis'
import { NotesReviewPage } from '@/pages/NotesReview'
import { CoreFloodListPage, CoreFloodRunPage } from '@/pages/CoreFloods'
import { HphtListPage, HphtRunPage } from '@/pages/Hpht'
import { NotFoundPage } from '@/pages/NotFound'

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
          {/* Issue #159: explicit, so bookmarks and the e2e specs keep working now
              that unknown paths show a not-found page instead of redirecting. */}
          <Route path="/dashboard" element={<Navigate to="/" replace />} />
          <Route path="/experiments" element={<ExperimentListPage />} />
          <Route path="/experiments/new" element={<NewExperimentPage />} />
          <Route path="/experiments/groups/:baseId" element={<ReplicateGroupPage />} />
          <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
          <Route path="/hpht" element={<HphtListPage />} />
          <Route path="/hpht/:baseId" element={<HphtRunPage />} />
          <Route path="/core-floods" element={<CoreFloodListPage />} />
          <Route path="/core-floods/:baseId" element={<CoreFloodRunPage />} />
          <Route path="/bulk-uploads" element={<BulkUploadsPage />} />
          <Route path="/samples" element={<SamplesPage />} />
          <Route path="/samples/:sampleId" element={<SampleDetailPage />} />
          <Route path="/chemicals" element={<ChemicalsPage />} />
          <Route path="/data-export" element={<DataExportPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/notes/review" element={<NotesReviewPage />} />
          {/* Inside the protected layout so a miss keeps the sidebar (issue #159). */}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Router>
  )
}
