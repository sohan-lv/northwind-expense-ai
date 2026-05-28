import { useState } from 'react'
import { FileText, AlertTriangle } from 'lucide-react'
import VerdictBadge from './VerdictBadge'
import CitationBlock from './CitationBlock'
import OverrideModal from './OverrideModal'

const VERDICT_CARD_STYLES = {
  compliant: {
    border: 'border-l-4 border-l-green-400',
    bg: 'bg-white',
    banner: 'bg-green-50 border-b border-green-100',
    bannerText: 'text-green-700',
  },
  flagged: {
    border: 'border-l-4 border-l-yellow-400',
    bg: 'bg-yellow-50/30',
    banner: 'bg-yellow-50 border-b border-yellow-100',
    bannerText: 'text-yellow-800',
  },
  rejected: {
    border: 'border-l-4 border-l-red-400',
    bg: 'bg-red-50/20',
    banner: 'bg-red-50 border-b border-red-100',
    bannerText: 'text-red-700',
  },
}

const DEFAULT_STYLE = {
  border: 'border-l-4 border-l-gray-200',
  bg: 'bg-white',
  banner: 'bg-gray-50 border-b border-gray-100',
  bannerText: 'text-gray-600',
}

export default function ReceiptCard({ receipt, submissionId }) {
  const [showOverride, setShowOverride] = useState(false)
  const v = receipt.verdict
  const effectiveVerdict = v?.override?.new_verdict || v?.verdict
  const style = VERDICT_CARD_STYLES[effectiveVerdict] || DEFAULT_STYLE

  return (
    <div className={`border border-gray-200 rounded-lg shadow-sm overflow-hidden ${style.border} ${style.bg}`}>
      {/* Top banner */}
      <div className={`px-4 py-2.5 ${style.banner} flex items-start justify-between gap-4`}>
        <div className="flex items-center gap-2 min-w-0">
          <FileText size={15} className="text-gray-400 flex-shrink-0" />
          <div className="min-w-0">
            <p className="font-semibold text-gray-900 text-sm truncate">{receipt.filename}</p>
            <p className="text-xs text-gray-500 mt-0.5">
              {receipt.vendor || 'Unknown vendor'}
              {receipt.receipt_date && <span> · {receipt.receipt_date}</span>}
              {receipt.amount != null && (
                <span className="font-medium text-gray-700"> · ${Number(receipt.amount).toFixed(2)}</span>
              )}
            </p>
          </div>
        </div>
        <div className="flex-shrink-0">
          {v ? (
            <VerdictBadge verdict={effectiveVerdict} confidence={v.confidence} />
          ) : (
            <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded-full">
              {receipt.processing_status}
            </span>
          )}
        </div>
      </div>

      {/* Verdict body */}
      {v && (
        <div className="px-4 py-4 space-y-4">
          {/* AI Verdict */}
          <div>
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">AI Verdict</span>
              <VerdictBadge verdict={v.verdict} size="sm" />
              {v.confidence === 'HIGH' && (
                <span className="inline-flex items-center gap-1 text-xs text-green-700 bg-green-50 border border-green-200 rounded-full px-2 py-0.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                  High confidence
                </span>
              )}
              {v.confidence === 'MEDIUM' && (
                <span className="inline-flex items-center gap-1 text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded-full px-2 py-0.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-yellow-500 flex-shrink-0" />
                  Medium confidence
                </span>
              )}
              {v.confidence === 'LOW' && (
                <span className="inline-flex items-center gap-1.5 text-xs text-orange-700 bg-orange-100 border border-orange-300 rounded-full px-2.5 py-0.5 font-semibold">
                  <AlertTriangle size={11} />
                  Low confidence
                </span>
              )}
            </div>
            {v.requires_human_review && (
              <div className="mb-2">
                <span className="inline-flex items-center gap-1.5 text-xs text-red-700 bg-red-50 border border-red-200 rounded px-2 py-0.5 font-medium">
                  <span>⚑</span>
                  Requires human review
                </span>
              </div>
            )}

            {v.reasoning && (
              <p className="text-sm text-gray-700 leading-relaxed">{v.reasoning}</p>
            )}

            <CitationBlock citations={v.cited_clauses} />
          </div>

          {/* Override section */}
          {v.override ? (
            <div className="border-t border-gray-100 pt-4">
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Reviewer Override</span>
                <VerdictBadge verdict={v.override.new_verdict} size="sm" />
              </div>
              <p className="text-sm text-gray-700 italic">"{v.override.reviewer_comment}"</p>
              <p className="text-xs text-gray-400 mt-1">
                {v.override.overridden_by && <span>{v.override.overridden_by} · </span>}
                {v.override.overridden_at && new Date(v.override.overridden_at).toLocaleString()}
              </p>
            </div>
          ) : (
            <div className="border-t border-gray-100 pt-3">
              <button
                onClick={() => setShowOverride(true)}
                className="text-sm text-blue-600 hover:text-blue-800 font-medium"
              >
                Override verdict
              </button>
            </div>
          )}
        </div>
      )}

      {showOverride && (
        <OverrideModal
          verdictId={v.id}
          currentVerdict={v.verdict}
          submissionId={submissionId}
          onClose={() => setShowOverride(false)}
        />
      )}
    </div>
  )
}
