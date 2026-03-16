import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<div>Dashboard (stub)</div>} />
        <Route path="/experiments" element={<div>Experiments List (stub)</div>} />
        <Route path="/experiments/new" element={<div>New Experiment (stub)</div>} />
        <Route path="/experiments/:id" element={<div>Experiment Detail (stub)</div>} />
        <Route path="/bulk-uploads" element={<div>Bulk Uploads (stub)</div>} />
        <Route path="/samples" element={<div>Samples (stub)</div>} />
        <Route path="/chemicals" element={<div>Chemicals (stub)</div>} />
        <Route path="/analysis" element={<div>Analysis (stub)</div>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  )
}
