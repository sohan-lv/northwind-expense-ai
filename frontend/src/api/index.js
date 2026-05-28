import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 120000,
})

export const employeesApi = {
  list: () => api.get('/api/employees').then(r => r.data),
  create: (data) => api.post('/api/employees', data).then(r => r.data),
  get: (id) => api.get(`/api/employees/${id}`).then(r => r.data),
}

export const submissionsApi = {
  create: (data) => api.post('/api/submissions', data).then(r => r.data),
  list: (params) => api.get('/api/submissions', { params }).then(r => r.data),
  get: (id) => api.get(`/api/submissions/${id}`).then(r => r.data),
}

export const receiptsApi = {
  upload: (submissionId, file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/api/submissions/${submissionId}/receipts`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }).then(r => r.data)
  },
  get: (id) => api.get(`/api/receipts/${id}`).then(r => r.data),
}

export const verdictsApi = {
  get: (id) => api.get(`/api/verdicts/${id}`).then(r => r.data),
  override: (id, data) => api.post(`/api/verdicts/${id}/override`, data).then(r => r.data),
}

export const policyQaApi = {
  ask: (question) => api.post('/api/policy-qa', { question }).then(r => r.data),
}
