import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Upload, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import { employeesApi, submissionsApi, receiptsApi } from '../api'

const GRADE_OPTIONS = ['1','2','3','4','5','6','7','8','9','10']

const FILE_STATUS = { ready: 'ready', processing: 'processing', done: 'done', failed: 'failed' }

export default function NewSubmission() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [useExisting, setUseExisting] = useState(true)
  const [selectedEmployeeId, setSelectedEmployeeId] = useState('')
  const [newEmp, setNewEmp] = useState({
    employee_id: '', name: '', grade: '5', department: '', manager: '', trip_purpose: '', trip_start: '', trip_end: '',
  })
  const [tripDetails, setTripDetails] = useState({ trip_purpose: '', trip_start: '', trip_end: '' })
  const [submissionId, setSubmissionId] = useState(null)
  const [files, setFiles] = useState([])
  const [fileStatuses, setFileStatuses] = useState({})
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const { data: employees = [] } = useQuery({
    queryKey: ['employees'],
    queryFn: employeesApi.list,
  })

  const handleStep1 = async () => {
    setError('')
    setSubmitting(true)
    try {
      let employeeId
      if (useExisting) {
        if (!selectedEmployeeId) { setError('Select an employee'); setSubmitting(false); return }
        employeeId = selectedEmployeeId
      } else {
        if (!newEmp.name.trim()) { setError('Name is required'); setSubmitting(false); return }
        const created = await employeesApi.create({
          employee_id: newEmp.employee_id || undefined,
          name: newEmp.name,
          grade: newEmp.grade,
          department: newEmp.department || undefined,
          manager: newEmp.manager || undefined,
          trip_purpose: newEmp.trip_purpose || undefined,
          trip_start: newEmp.trip_start || undefined,
          trip_end: newEmp.trip_end || undefined,
        })
        employeeId = created.id
      }

      const tp = useExisting ? tripDetails : newEmp
      const sub = await submissionsApi.create({
        employee_id: employeeId,
        trip_purpose: tp.trip_purpose || undefined,
        trip_start: tp.trip_start || undefined,
        trip_end: tp.trip_end || undefined,
      })
      setSubmissionId(sub.id)
      setStep(2)
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to create submission')
    } finally {
      setSubmitting(false)
    }
  }

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files)
    setFiles(selected)
    const statuses = {}
    selected.forEach(f => { statuses[f.name] = FILE_STATUS.ready })
    setFileStatuses(statuses)
  }

  const handleUpload = async () => {
    if (files.length === 0) return
    for (const file of files) {
      setFileStatuses(s => ({ ...s, [file.name]: FILE_STATUS.processing }))
      try {
        await receiptsApi.upload(submissionId, file)
        setFileStatuses(s => ({ ...s, [file.name]: FILE_STATUS.done }))
      } catch {
        setFileStatuses(s => ({ ...s, [file.name]: FILE_STATUS.failed }))
      }
    }
    setTimeout(() => navigate(`/submissions/${submissionId}`), 800)
  }

  const allDone = files.length > 0 && files.every(f =>
    [FILE_STATUS.done, FILE_STATUS.failed].includes(fileStatuses[f.name])
  )

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <div className="flex items-center gap-2 mb-8">
        <div className={`flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold ${step >= 1 ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'}`}>1</div>
        <div className="text-sm font-medium text-gray-700">Employee & Trip</div>
        <ChevronRight size={16} className="text-gray-400" />
        <div className={`flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold ${step >= 2 ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'}`}>2</div>
        <div className="text-sm font-medium text-gray-700">Upload Receipts</div>
      </div>

      {step === 1 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Employee & Trip Details</h2>

          <div className="flex rounded-md border border-gray-300 mb-5 overflow-hidden">
            <button
              onClick={() => setUseExisting(true)}
              className={`flex-1 py-2 text-sm font-medium transition-colors ${useExisting ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
            >
              Existing Employee
            </button>
            <button
              onClick={() => setUseExisting(false)}
              className={`flex-1 py-2 text-sm font-medium transition-colors ${!useExisting ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
            >
              New Employee
            </button>
          </div>

          {useExisting ? (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Employee</label>
                <select
                  value={selectedEmployeeId}
                  onChange={e => setSelectedEmployeeId(e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Select employee…</option>
                  {employees.map(emp => (
                    <option key={emp.id} value={emp.id}>{emp.name} · Grade {emp.grade}{emp.department ? ` · ${emp.department}` : ''}</option>
                  ))}
                </select>
              </div>
              <TripFields values={tripDetails} onChange={setTripDetails} />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Employee ID" value={newEmp.employee_id} onChange={v => setNewEmp(e => ({ ...e, employee_id: v }))} placeholder="NW-99999" />
                <Field label="Name *" value={newEmp.name} onChange={v => setNewEmp(e => ({ ...e, name: v }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Grade</label>
                  <select
                    value={newEmp.grade}
                    onChange={e => setNewEmp(n => ({ ...n, grade: e.target.value }))}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {GRADE_OPTIONS.map(g => <option key={g} value={g}>{g}</option>)}
                  </select>
                </div>
                <Field label="Department" value={newEmp.department} onChange={v => setNewEmp(e => ({ ...e, department: v }))} />
              </div>
              <Field label="Manager ID" value={newEmp.manager} onChange={v => setNewEmp(e => ({ ...e, manager: v }))} placeholder="NW-00001" />
              <TripFields values={newEmp} onChange={vals => setNewEmp(e => ({ ...e, ...vals }))} />
            </div>
          )}

          {error && <p className="text-sm text-red-600 mt-3">{error}</p>}

          <button
            onClick={handleStep1}
            disabled={submitting}
            className="mt-5 w-full bg-blue-600 text-white py-2.5 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 size={16} className="animate-spin" />}
            {submitting ? 'Creating…' : 'Continue to Upload'}
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Upload Receipts</h2>
          <p className="text-sm text-gray-500 mb-4">Submission created. Now upload your receipt files.</p>

          <label className="block border-2 border-dashed border-gray-300 rounded-lg p-8 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors">
            <Upload size={24} className="mx-auto mb-2 text-gray-400" />
            <span className="text-sm text-gray-600">Click to select files (PDF, JPG, PNG, TXT)</span>
            <input
              type="file"
              multiple
              accept=".pdf,.jpg,.jpeg,.png,.txt"
              onChange={handleFileChange}
              className="hidden"
            />
          </label>

          {files.length > 0 && (
            <div className="mt-4 space-y-2">
              {files.map(file => {
                const status = fileStatuses[file.name]
                return (
                  <div key={file.name} className="flex items-center justify-between bg-gray-50 rounded-md px-3 py-2">
                    <span className="text-sm text-gray-700 truncate flex-1 mr-2">{file.name}</span>
                    {status === FILE_STATUS.ready && <span className="text-xs text-gray-400">ready</span>}
                    {status === FILE_STATUS.processing && <Loader2 size={14} className="animate-spin text-blue-500" />}
                    {status === FILE_STATUS.done && <CheckCircle size={14} className="text-green-500" />}
                    {status === FILE_STATUS.failed && <XCircle size={14} className="text-red-500" />}
                  </div>
                )
              })}
            </div>
          )}

          <div className="mt-5 flex gap-3">
            <button
              onClick={handleUpload}
              disabled={files.length === 0 || allDone}
              className="flex-1 bg-blue-600 text-white py-2.5 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {allDone ? 'Done — redirecting…' : `Process ${files.length} file${files.length !== 1 ? 's' : ''}`}
            </button>
            <button
              onClick={() => navigate(`/submissions/${submissionId}`)}
              className="px-4 py-2.5 text-sm text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Skip
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, value, onChange, placeholder }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    </div>
  )
}

function TripFields({ values, onChange }) {
  return (
    <>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Trip Purpose</label>
        <input
          type="text"
          value={values.trip_purpose}
          onChange={e => onChange({ ...values, trip_purpose: e.target.value })}
          placeholder="e.g. Client review Denver"
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Trip Start</label>
          <input
            type="date"
            value={values.trip_start}
            onChange={e => onChange({ ...values, trip_start: e.target.value })}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Trip End</label>
          <input
            type="date"
            value={values.trip_end}
            onChange={e => onChange({ ...values, trip_end: e.target.value })}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>
    </>
  )
}
