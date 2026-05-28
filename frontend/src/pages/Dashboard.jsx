import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, RefreshCw, ChevronRight } from 'lucide-react'
import { submissionsApi, employeesApi } from '../api'
import VerdictBadge from '../components/VerdictBadge'

const STATUS_OPTIONS = ['', 'pending', 'compliant', 'flagged', 'rejected']

function StatCard({ label, count, color }) {
  const colors = {
    blue:   'bg-blue-50 border-blue-200 text-blue-700',
    yellow: 'bg-yellow-50 border-yellow-200 text-yellow-700',
    red:    'bg-red-50 border-red-200 text-red-700',
    green:  'bg-green-50 border-green-200 text-green-700',
    gray:   'bg-gray-50 border-gray-200 text-gray-600',
  }
  return (
    <div className={`border rounded-lg px-4 py-3 flex flex-col gap-0.5 ${colors[color] || colors.gray}`}>
      <span className="text-2xl font-bold">{count}</span>
      <span className="text-xs font-medium uppercase tracking-wide opacity-80">{label}</span>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [filters, setFilters] = useState({ employee_name: '', status: '', date_from: '', date_to: '' })

  const { data: employees } = useQuery({
    queryKey: ['employees'],
    queryFn: employeesApi.list,
  })

  // Send only backend-supported filters (status, dates) — employee filtered client-side by name
  const activeFilters = Object.fromEntries(
    Object.entries(filters)
      .filter(([k, v]) => v !== '' && k !== 'employee_name')
  )

  const { data: submissions, isLoading, refetch } = useQuery({
    queryKey: ['submissions', activeFilters],
    queryFn: () => submissionsApi.list(activeFilters),
  })

  const submissionList = Array.isArray(submissions) ? submissions : []
  const employeeList = Array.isArray(employees) ? employees : []

  // Filter by name client-side so all UUIDs for the same person are included
  const displayList = filters.employee_name
    ? submissionList.filter(s => s.employee_name === filters.employee_name)
    : submissionList

  const stats = {
    total: displayList.length,
    flagged: displayList.filter(s => s.status === 'flagged').length,
    rejected: displayList.filter(s => s.status === 'rejected').length,
    compliant: displayList.filter(s => s.status === 'compliant').length,
  }

  const clearFilters = () => setFilters({ employee_name: '', status: '', date_from: '', date_to: '' })
  const hasFilters = Object.values(filters).some(v => v !== '')

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Header band */}
      <div className="rounded-xl bg-gradient-to-r from-blue-600 to-blue-800 px-6 py-5 mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Expense Submissions</h1>
          <p className="text-blue-200 text-sm mt-0.5">Review and approve employee travel expenses</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            className="p-2 text-blue-200 hover:text-white hover:bg-white/10 rounded-md transition-colors"
          >
            <RefreshCw size={16} />
          </button>
          <button
            onClick={() => navigate('/new')}
            className="inline-flex items-center gap-2 bg-white text-blue-700 px-4 py-2 rounded-md text-sm font-semibold hover:bg-blue-50 transition-colors shadow-sm"
          >
            <Plus size={16} />
            New Submission
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-3 mb-5">
        <StatCard label="Total" count={stats.total} color="blue" />
        <StatCard label="Compliant" count={stats.compliant} color="green" />
        <StatCard label="Flagged" count={stats.flagged} color="yellow" />
        <StatCard label="Rejected" count={stats.rejected} color="red" />
      </div>

      {/* Filter bar */}
      <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 mb-4 flex flex-wrap items-end gap-3 shadow-sm">
        <select
          value={filters.employee_name}
          onChange={e => setFilters(f => ({ ...f, employee_name: e.target.value }))}
          className="border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 min-w-[160px]"
        >
          <option value="">All employees</option>
          {[...new Map(employeeList.map(emp => [emp.name, emp])).values()].map(emp => (
            <option key={emp.id} value={emp.name}>{emp.name}</option>
          ))}
        </select>

        <select
          value={filters.status}
          onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}
          className="border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {STATUS_OPTIONS.map(s => (
            <option key={s} value={s}>{s || 'All statuses'}</option>
          ))}
        </select>

        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">From</span>
          <input
            type="date"
            value={filters.date_from}
            onChange={e => setFilters(f => ({ ...f, date_from: e.target.value }))}
            className="border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">To</span>
          <input
            type="date"
            value={filters.date_to}
            onChange={e => setFilters(f => ({ ...f, date_to: e.target.value }))}
            className="border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {hasFilters && (
          <button
            onClick={clearFilters}
            className="px-3 py-1.5 text-xs text-gray-500 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="p-12 text-center text-gray-400">Loading submissions…</div>
        ) : displayList.length === 0 ? (
          <div className="p-16 text-center">
            <p className="text-4xl mb-3">📂</p>
            <p className="text-gray-600 font-medium mb-1">No submissions yet</p>
            <p className="text-sm text-gray-400 mb-5">
              {hasFilters ? 'No submissions match your filters.' : 'Create your first expense submission to get started.'}
            </p>
            {!hasFilters && (
              <button
                onClick={() => navigate('/new')}
                className="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700"
              >
                <Plus size={15} />
                New Submission
              </button>
            )}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-5 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide">Employee</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide">Trip Purpose</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide">Dates</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide">Status</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide">Submitted</th>
                <th className="px-4 py-3 w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {displayList.map(sub => (
                <tr
                  key={sub.id}
                  onClick={() => navigate(`/submissions/${sub.id}`)}
                  className="cursor-pointer hover:bg-blue-50/40 transition-colors group"
                >
                  <td className="px-5 py-3.5 font-semibold text-gray-900">{sub.employee_name || '—'}</td>
                  <td className="px-4 py-3.5 text-gray-500 max-w-xs truncate">{sub.trip_purpose || '—'}</td>
                  <td className="px-4 py-3.5 text-gray-500 font-mono text-xs whitespace-nowrap">
                    {sub.trip_start && sub.trip_end
                      ? `${sub.trip_start} → ${sub.trip_end}`
                      : sub.trip_start || '—'}
                  </td>
                  <td className="px-4 py-3.5">
                    <VerdictBadge verdict={sub.status} />
                  </td>
                  <td className="px-4 py-3.5 text-gray-400 text-xs whitespace-nowrap">
                    {sub.created_at ? new Date(sub.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-4 py-3.5 text-gray-300 group-hover:text-blue-400 transition-colors">
                    <ChevronRight size={16} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
