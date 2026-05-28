const VERDICT_STYLES = {
  compliant: { pill: 'bg-green-100 text-green-800', dot: 'bg-green-500' },
  flagged:   { pill: 'bg-yellow-100 text-yellow-800', dot: 'bg-yellow-500' },
  rejected:  { pill: 'bg-red-100 text-red-800', dot: 'bg-red-500' },
  pending:   { pill: 'bg-gray-100 text-gray-600', dot: 'bg-gray-400' },
}

const CONFIDENCE_COLORS = {
  HIGH:   'bg-green-500',
  MEDIUM: 'bg-yellow-500',
  LOW:    'bg-red-500',
}

export default function VerdictBadge({ verdict, confidence, size = 'md' }) {
  const style = VERDICT_STYLES[verdict] || VERDICT_STYLES.pending
  const cls = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1'

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-medium ${cls} ${style.pill}`}>
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${style.dot}`} />
      {verdict || 'pending'}
      {confidence && (
        <span
          className={`ml-0.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${CONFIDENCE_COLORS[confidence] || 'bg-gray-400'}`}
          title={`Confidence: ${confidence}`}
        />
      )}
    </span>
  )
}
