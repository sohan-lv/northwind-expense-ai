import { Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import NewSubmission from './pages/NewSubmission'
import SubmissionDetail from './pages/SubmissionDetail'
import PolicyQA from './pages/PolicyQA'

function Nav() {
  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        <NavLink to="/" className="font-bold text-gray-900 text-lg">
          Northwind <span className="text-blue-600">Expense AI</span>
        </NavLink>
        <div className="flex items-center gap-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                isActive ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-100'
              }`
            }
          >
            Submissions
          </NavLink>
          <NavLink
            to="/policy-qa"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                isActive ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-100'
              }`
            }
          >
            Policy Q&amp;A
          </NavLink>
        </div>
      </div>
    </nav>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Nav />
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={<NewSubmission />} />
          <Route path="/submissions/:id" element={<SubmissionDetail />} />
          <Route path="/policy-qa" element={<PolicyQA />} />
        </Routes>
      </main>
    </div>
  )
}
