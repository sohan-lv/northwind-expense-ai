import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 120000,
})

export const employeesApi = {
  list: () => api.get('/employees').then(r => r.data),
  create: (data) => api.post('/employees', data).then(r => r.data),
  get: (id) => api.get(`/employees/${id}`).then(r => r.data),
}

export const submissionsApi = {
  create: (data) => api.post('/submissions', data).then(r => r.data),
  list: (params) => api.get('/submissions', { params }).then(r => r.data),
  get: (id) => api.get(`/submissions/${id}`).then(r => r.data),
}

export const receiptsApi = {
  upload: (submissionId, file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/submissions/${submissionId}/receipts`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }).then(r => r.data)
  },
  get: (id) => api.get(`/receipts/${id}`).then(r => r.data),
}

export const verdictsApi = {
  get: (id) => api.get(`/verdicts/${id}`).then(r => r.data),
  override: (id, data) => api.post(`/verdicts/${id}/override`, data).then(r => r.data),
}

export const policyQaApi = {
  ask: (question) => api.post('/policy-qa', { question }).then(r => r.data),
}
