import { useState, useRef, useEffect } from 'react'
import { Send, AlertTriangle } from 'lucide-react'
import { policyQaApi } from '../api'
import CitationBlock from '../components/CitationBlock'

const SUGGESTED = [
  'What is the dinner cap?',
  'Do I need VP approval for international travel?',
  'What are the hotel caps by city tier?',
  'Is alcohol reimbursable during solo travel?',
]

export default function PolicyQA() {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const sendQuestion = async (q) => {
    const text = q.trim()
    if (!text || loading) return

    setMessages(m => [...m, { role: 'user', text }])
    setQuestion('')
    setLoading(true)

    try {
      const result = await policyQaApi.ask(text)
      setMessages(m => [...m, {
        role: 'assistant',
        text: result.answer,
        citations: result.citations,
        refused: result.refused,
      }])
    } catch {
      setMessages(m => [...m, {
        role: 'assistant',
        text: 'Something went wrong. Please try again.',
        citations: [],
        refused: false,
        error: true,
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (e) => {
    e?.preventDefault()
    sendQuestion(question)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendQuestion(question)
    }
  }

  const handleChip = (q) => {
    sendQuestion(q)
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 flex flex-col h-[calc(100vh-64px)]">
      <h1 className="text-2xl font-bold text-gray-900 mb-1">Policy Q&A</h1>
      <p className="text-sm text-gray-500 mb-3">Ask questions about Northwind Logistics expense policies.</p>

      {/* Suggested chips */}
      <div className="flex flex-wrap gap-2 mb-4">
        {SUGGESTED.map(q => (
          <button
            key={q}
            onClick={() => handleChip(q)}
            disabled={loading}
            className="text-xs px-3 py-1.5 rounded-full border border-blue-200 text-blue-700 bg-blue-50 hover:bg-blue-100 hover:border-blue-300 transition-colors disabled:opacity-40"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-1">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 text-sm mt-10 space-y-2">
            <p className="text-4xl">📋</p>
            <p className="font-medium text-gray-500">Ask about expense policies</p>
            <p className="text-xs text-gray-400">Click a suggested question above or type your own below.</p>
          </div>
        )}

        {(messages || []).map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'user' ? (
              <div className="max-w-[75%] bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm">
                {msg.text}
              </div>
            ) : (
              <div className={`max-w-[85%] rounded-2xl rounded-tl-sm px-4 py-3 text-sm ${
                msg.refused
                  ? 'bg-amber-50 border border-amber-200'
                  : msg.error
                  ? 'bg-red-50 border border-red-200'
                  : 'bg-white border border-gray-200 shadow-sm'
              }`}>
                {msg.refused && (
                  <div className="flex items-center gap-1.5 text-amber-700 text-xs font-semibold mb-2">
                    <AlertTriangle size={13} />
                    Outside policy library
                  </div>
                )}
                <p className={`leading-relaxed ${msg.refused ? 'text-amber-800' : 'text-gray-700'}`}>
                  {msg.text}
                </p>
                {msg.citations && msg.citations.length > 0 && (
                  <CitationBlock citations={msg.citations} />
                )}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
              <div className="flex gap-1.5 items-center h-5">
                <span className="w-2 h-2 bg-gray-300 rounded-full animate-bounce [animation-delay:-0.3s]" />
                <span className="w-2 h-2 bg-gray-300 rounded-full animate-bounce [animation-delay:-0.15s]" />
                <span className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="flex gap-2 items-end">
        <textarea
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Ask about expense policies… (Enter to send)"
          className="flex-1 border border-gray-300 rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 max-h-32"
        />
        <button
          type="submit"
          disabled={!question.trim() || loading}
          className="p-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 flex-shrink-0 transition-colors"
        >
          <Send size={16} />
        </button>
      </form>
    </div>
  )
}
