import { useState, useEffect } from 'react'

// TODO: move to env variable eventually
const API_URL = 'https://1gmg7sqroe.execute-api.us-east-1.amazonaws.com/findings'

function App() {
  const [findings, setFindings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(API_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`)
        return res.json()
      })
      .then((data) => {
        setFindings(data.findings || [])
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  if (loading) return <div className="p-8 text-gray-600">Loading findings…</div>
  if (error) return <div className="p-8 text-red-600">Error: {error}</div>

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">AWS Cost Watchdog</h1>
          <p className="text-gray-600 mt-2">
            {findings.length} finding{findings.length !== 1 ? 's' : ''}
          </p>
        </header>

        {findings.length === 0 ? (
          <div className="bg-white rounded-lg p-8 text-center text-gray-500 shadow">
            No findings yet. Your account looks clean.
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <Th>Category</Th>
                  <Th>Resource ID</Th>
                  <Th>Type</Th>
                  <Th align="right">Est. Cost/mo</Th>
                  <Th>Detected</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {findings.map((f) => (
                  <tr key={f.finding_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <CategoryBadge category={f.category} />
                    </td>
                    <td className="px-6 py-4 text-sm font-mono text-gray-900 break-all">
                      {f.resource_id}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {f.resource_type}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900 text-right">
                      ${Number(f.estimated_monthly_cost || 0).toFixed(2)}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {new Date(f.detected_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function Th({ children, align = 'left' }) {
  return (
    <th className={`px-6 py-3 text-${align} text-xs font-medium text-gray-500 uppercase tracking-wider`}>
      {children}
    </th>
  )
}

function CategoryBadge({ category }) {
  const colors = {
    idle_ebs:      'bg-yellow-100 text-yellow-800',
    stopped_ec2:   'bg-orange-100 text-orange-800',
    empty_s3:      'bg-blue-100 text-blue-800',
    old_snapshot:  'bg-purple-100 text-purple-800',
    missing_tags:  'bg-pink-100 text-pink-800',
    cost_anomaly:  'bg-red-100 text-red-800',
  }
  const color = colors[category] || 'bg-gray-100 text-gray-800'
  return (
    <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${color}`}>
      {category}
    </span>
  )
}

export default App
