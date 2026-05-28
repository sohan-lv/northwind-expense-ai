import { useState } from 'react'
import { X } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { verdictsApi } from '../api'

const VERDICT_OPTIONS = ['compliant', 'flagged', 'rejected']

export default function OverrideModal({ verdictId, currentVerdict, submissionId, onClose }) {
  const queryClient = useQueryClient()
  const [newVerdict, setNewVerdict] = useState(currentVerdict || 'compliant')
  const [comment, setComment] = useState('')
  const [reviewer, setReviewer] = useState('')
  const [commentError, setCommentError] = useState('')

  const mutation = useMutation({
    mutationFn: () => verdictsApi.override(verdictId, {
      new_verdict: newVerdict,
      reviewer_comment: comment.trim(),
      overridden_by: reviewer.trim() || undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['submission', submissionId] })
      onClose()
    },
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!comment.trim()) {
      setCommentError('Reviewer comment is required')
      return
    }
    setCommentError('')
    mutation.mutate()
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h2 className="text-lg font-semibold text-gray-900">Override Verdict</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">New Verdict</label>
            <select
              value={newVerdict}
              onChange={e => setNewVerdict(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {VERDICT_OPTIONS.map(v => (
                <option key={v} value={v}>{v.charAt(0).toUpperCase() + v.slice(1)}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Reviewer Name / Email</label>
            <input
              type="text"
              value={reviewer}
              onChange={e => setReviewer(e.target.value)}
              placeholder="reviewer@company.com"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Comment <span className="text-red-500">*</span>
            </label>
            <textarea
              value={comment}
              onChange={e => { setComment(e.target.value); setCommentError('') }}
              rows={3}
              placeholder="Reason for override..."
              className={`w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                commentError ? 'border-red-400' : 'border-gray-300'
              }`}
            />
            {commentError && <p className="text-xs text-red-500 mt-1">{commentError}</p>}
          </div>

          {mutation.isError && (
            <p className="text-sm text-red-600">
              {mutation.error?.response?.data?.detail || 'Override failed. Try again.'}
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {mutation.isPending ? 'Saving…' : 'Save Override'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
