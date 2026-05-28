export default function CitationBlock({ citations }) {
  if (!citations || citations.length === 0) return null

  const renderQuote = (quote) => {
    if (!quote) return null

    if (quote.startsWith('[TABLE]')) {
      const tableContent = quote.replace('[TABLE]', '').trim()
      const cells = tableContent.split(' | ').map(c => c.trim())

      // Build rows of 2 cells each
      const rows = []
      for (let i = 0; i < cells.length; i += 2) {
        if (cells[i + 1] !== undefined) {
          rows.push([cells[i], cells[i + 1]])
        } else {
          rows.push([cells[i], ''])
        }
      }

      return (
        <div className="mt-1 overflow-x-auto">
          <table className="text-xs border-collapse w-auto">
            <thead>
              <tr className="bg-blue-100">
                <th className="border border-blue-200 px-2 py-1 text-left font-medium text-blue-800">
                  {rows[0]?.[0] || ''}
                </th>
                <th className="border border-blue-200 px-2 py-1 text-left font-medium text-blue-800">
                  {rows[0]?.[1] || ''}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(1).map((row, i) => (
                <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-blue-50'}>
                  <td className="border border-blue-200 px-2 py-1">{row[0]}</td>
                  <td className="border border-blue-200 px-2 py-1 font-medium">{row[1]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }

    return (
      <blockquote className="text-xs text-gray-700 italic mt-1">
        "{quote}"
      </blockquote>
    )
  }

  return (
    <div className="space-y-2 mt-2">
      {citations.map((cite, i) => (
        <div key={i} className="border-l-4 border-blue-400 pl-3 py-1 bg-blue-50 rounded-r">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono font-bold text-blue-700 bg-blue-100 px-1.5 py-0.5 rounded">
              {cite.doc_id}
            </span>
            <span className="text-xs text-blue-600">
              {cite.section}
            </span>
          </div>
          {renderQuote(cite.quote)}
        </div>
      ))}
    </div>
  )
}
