import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, User, Calendar, Briefcase, Building2 } from 'lucide-react'
import { submissionsApi } from '../api'
import VerdictBadge from '../components/VerdictBadge'
import ReceiptCard from '../components/ReceiptCard'

const GRADE_COLORS = {
  '9': 'bg-purple-100 text-purple-800',
  '10': 'bg-purple-100 text-purple-800',
  '8': 'bg-blue-100 text-blue-800',
  '7': 'bg-blue-100 text-blue-800',
}

export default function SubmissionDetail() {
  const { id } = useParams()
  const navigate = useNavigate()

  const { data: submission, isLoading, isError } = useQuery({
    queryKey: ['submission', id],
    queryFn: () => submissionsApi.get(id),
    refetchInterval: false,
  })

  if (isLoading) {
    return <div className="max-w-4xl mx-auto px-4 py-12 text-center text-gray-400">Loading submission…</div>
  }
  if (isError || !submission) {
    return <div className="max-w-4xl mx-auto px-4 py-12 text-center text-red-500">Submission not found.</div>
  }

  const emp = submission.employee
  const gradeColor = emp?.grade ? (GRADE_COLORS[emp.grade] || 'bg-gray-100 text-gray-600') : 'bg-gray-100 text-gray-600'

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <button
        onClick={() => navigate('/')}
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 mb-5 transition-colors"
      >
        <ArrowLeft size={15} />
        Back to submissions
      </button>

      {/* Employee header card */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden mb-6">
        <div className="bg-gradient-to-r from-gray-50 to-white px-5 py-4 border-b border-gray-100 flex items-start justify-between gap-4">
          <div className="space-y-2.5">
            <div className="flex items-center gap-2.5 flex-wrap">
              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                <User size={15} className="text-blue-600" />
              </div>
              <span className="font-bold text-gray-900 text-lg">{emp?.name || 'Unknown'}</span>
              {emp?.grade && (
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${gradeColor}`}>
                  Grade {emp.grade}
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-3 pl-10">
              {emp?.department && (
                <div className="flex items-center gap-1.5 text-sm text-gray-600">
                  <Building2 size={13} className="text-gray-400" />
                  {emp.department}
                </div>
              )}
              {submission.trip_purpose && (
                <div className="flex items-center gap-1.5 text-sm text-gray-600">
                  <Briefcase size={13} className="text-gray-400" />
                  {submission.trip_purpose}
                </div>
              )}
              {(submission.trip_start || submission.trip_end) && (
                <div className="flex items-center gap-1.5 text-sm text-gray-500">
                  <Calendar size={13} className="text-gray-400" />
                  <span className="font-mono text-xs">
                    {submission.trip_start}
                    {submission.trip_end && ` → ${submission.trip_end}`}
                  </span>
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
            <VerdictBadge verdict={submission.status} />
            <span className="text-xs text-gray-400">
              {submission.created_at ? new Date(submission.created_at).toLocaleString() : ''}
            </span>
          </div>
        </div>

        {emp?.manager && (
          <div className="px-5 py-2 bg-gray-50/50 flex gap-6 text-xs text-gray-500">
            <span>Manager: <span className="font-mono">{emp.manager}</span></span>
            {emp.employee_id && <span>ID: <span className="font-mono">{emp.employee_id}</span></span>}
          </div>
        )}
      </div>

      {/* Receipts */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-gray-800">
          Receipts <span className="text-gray-400 font-normal">({submission.receipts?.length || 0})</span>
        </h2>
      </div>

      {!submission.receipts || submission.receipts.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-lg p-10 text-center text-gray-400 text-sm">
          No receipts uploaded yet.
        </div>
      ) : (
        <div className="space-y-4">
          {submission.receipts.map(receipt => (
            <ReceiptCard key={receipt.id} receipt={receipt} submissionId={id} />
          ))}
        </div>
      )}
    </div>
  )
}
