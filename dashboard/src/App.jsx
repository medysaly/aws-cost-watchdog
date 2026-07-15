import { useState, useEffect, useMemo, useCallback } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { RefreshCw, AlertCircle, DollarSign, Package, Clock, Tag } from 'lucide-react'

const API_URL = 'https://1gmg7sqroe.execute-api.us-east-1.amazonaws.com/findings'
const AUTO_REFRESH_MS = 30_000

// Ordered list of all categories the watchdog can detect.
const ALL_CATEGORIES = [
  { key: 'idle_ebs',     label: 'Idle EBS',        color: '#eab308' },
  { key: 'stopped_ec2',  label: 'Stopped EC2',     color: '#f97316' },
  { key: 'empty_s3',     label: 'Empty S3',        color: '#3b82f6' },
  { key: 'old_snapshot', label: 'Old Snapshots',   color: '#a855f7' },
  { key: 'missing_tags', label: 'Missing Tags',    color: '#ec4899' },
  { key: 'cost_anomaly', label: 'Cost Anomalies',  color: '#ef4444' },
]

const CATEGORY_META = Object.fromEntries(ALL_CATEGORIES.map((c) => [c.key, c]))

function App() {
  const [findings, setFindings] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [lastUpdated, setLastUpdated] = useState(null)

  const fetchFindings = useCallback(async (opts = { silent: false }) => {
    if (opts.silent) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const res = await fetch(API_URL)
      if (!res.ok) throw new Error(`API returned ${res.status}`)
      const data = await res.json()
      setFindings(data.findings || [])
      setLastUpdated(new Date())
    } catch (err) {
      // Silent auto-refresh failure — don't destroy the current UI with an error
      if (!opts.silent) setError(err.message)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => { fetchFindings() }, [fetchFindings])

  // Auto-refresh every AUTO_REFRESH_MS
  useEffect(() => {
    const interval = setInterval(() => fetchFindings({ silent: true }), AUTO_REFRESH_MS)
    return () => clearInterval(interval)
  }, [fetchFindings])

  const stats = useMemo(() => {
    const totalCost = findings.reduce((sum, f) => sum + Number(f.estimated_monthly_cost || 0), 0)
    const byCategory = {}
    ALL_CATEGORIES.forEach((c) => { byCategory[c.key] = 0 })
    findings.forEach((f) => {
      byCategory[f.category] = (byCategory[f.category] || 0) + 1
    })
    const activeCategoryCount = Object.values(byCategory).filter((v) => v > 0).length
    return { total: findings.length, totalCost, byCategory, activeCategoryCount }
  }, [findings])

  const filteredFindings = useMemo(() => {
    if (selectedCategory === 'all') return findings
    return findings.filter((f) => f.category === selectedCategory)
  }, [findings, selectedCategory])

  const chartData = useMemo(() => {
    return ALL_CATEGORIES
      .filter((c) => stats.byCategory[c.key] > 0)
      .map((c) => ({ name: c.label, value: stats.byCategory[c.key], category: c.key, color: c.color }))
      .sort((a, b) => b.value - a.value)
  }, [stats.byCategory])

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">AWS Cost Watchdog</h1>
            <p className="text-sm text-slate-500 mt-1 flex items-center gap-2">
              <span>Serverless FinOps monitoring · Last updated {lastUpdated ? lastUpdated.toLocaleTimeString() : '—'}</span>
              <span className="inline-flex items-center gap-1 text-xs text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                <span className={`w-1.5 h-1.5 rounded-full bg-emerald-500 ${refreshing ? 'animate-pulse' : ''}`} />
                Auto-refresh 30s
              </span>
            </p>
          </div>
          <button
            onClick={() => fetchFindings()}
            disabled={loading || refreshing}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading || refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3 text-red-800">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span>Error loading findings: {error}</span>
          </div>
        )}

        {/* KPI cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <KpiCard icon={<Package className="w-4 h-4 text-slate-500" />} label="Total Findings" value={stats.total} />
          <KpiCard icon={<DollarSign className="w-4 h-4 text-emerald-600" />} label="Est. Monthly Waste" value={`$${stats.totalCost.toFixed(2)}`} />
          <KpiCard icon={<Tag className="w-4 h-4 text-indigo-600" />} label="Active Categories" value={`${stats.activeCategoryCount} / ${ALL_CATEGORIES.length}`} />
          <KpiCard icon={<Clock className="w-4 h-4 text-amber-600" />} label="Last Scan" value={lastUpdated ? lastUpdated.toLocaleDateString() : '—'} />
        </div>

        {/* Donut with center total + ranked breakdown */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 mb-6">
          {/* Donut chart with center label */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Distribution</h2>
            {chartData.length === 0 ? (
              <div className="h-56 flex flex-col items-center justify-center text-slate-400 text-sm">
                <div className="text-4xl text-slate-200 mb-2">◯</div>
                <div>No findings yet</div>
              </div>
            ) : (
              <div className="relative">
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={chartData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={90}
                      innerRadius={60}
                      paddingAngle={2}
                      startAngle={90}
                      endAngle={-270}
                      animationDuration={600}
                    >
                      {chartData.map((entry) => (
                        <Cell key={entry.category} fill={entry.color} stroke="none" />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: 'white',
                        border: '1px solid #e2e8f0',
                        borderRadius: '8px',
                        fontSize: '13px',
                        padding: '8px 12px',
                        boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                      }}
                      formatter={(value, name) => [`${value} findings`, name]}
                    />
                  </PieChart>
                </ResponsiveContainer>
                {/* Center label overlay */}
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  <div className="text-4xl font-semibold text-slate-900 tabular-nums leading-none">{stats.total}</div>
                  <div className="text-xs text-slate-500 uppercase tracking-wider mt-1.5">findings</div>
                </div>
              </div>
            )}
          </div>

          {/* Ranked breakdown — all 6 categories */}
          <div className="lg:col-span-3 bg-white rounded-xl border border-slate-200 p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Monitored categories</h2>
              <span className="text-xs text-slate-400 tabular-nums">{stats.total} findings across {ALL_CATEGORIES.length} categories</span>
            </div>
            <div className="space-y-4">
              {ALL_CATEGORIES.map(({ key, label, color }) => {
                const count = stats.byCategory[key] || 0
                const percentage = stats.total > 0 ? (count / stats.total) * 100 : 0
                const isEmpty = count === 0
                return (
                  <div key={key} className={isEmpty ? 'opacity-40' : ''}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2.5">
                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                        <span className="text-sm font-medium text-slate-800">{label}</span>
                      </div>
                      <div className="flex items-center gap-3 text-sm">
                        <span className="text-slate-400 tabular-nums text-xs w-8 text-right">
                          {isEmpty ? '—' : `${percentage.toFixed(0)}%`}
                        </span>
                        <span className="text-slate-900 font-semibold tabular-nums w-6 text-right">{count}</span>
                      </div>
                    </div>
                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${percentage}%`, backgroundColor: color }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* Findings table with filter chips in header */}
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-6 py-5 border-b border-slate-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-slate-900 tracking-tight">Findings</h2>
              <span className="text-sm text-slate-400 tabular-nums">{filteredFindings.length} of {stats.total}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <FilterChip label={`All (${stats.total})`} active={selectedCategory === 'all'} onClick={() => setSelectedCategory('all')} disabled={false} />
              {ALL_CATEGORIES.map(({ key, label, color }) => {
                const count = stats.byCategory[key] || 0
                return (
                  <FilterChip
                    key={key}
                    label={`${label} (${count})`}
                    color={color}
                    active={selectedCategory === key}
                    onClick={() => setSelectedCategory(key)}
                    disabled={count === 0}
                  />
                )
              })}
            </div>
          </div>

          {loading && findings.length === 0 ? (
            <div className="p-16 text-center text-slate-400 text-sm">Loading findings…</div>
          ) : filteredFindings.length === 0 ? (
            <div className="p-16 text-center text-slate-400 text-sm">
              {stats.total === 0 ? 'No findings — your account is clean.' : 'No findings match this filter.'}
            </div>
          ) : (
            <table className="min-w-full divide-y divide-slate-100">
              <thead className="bg-slate-50/50">
                <tr>
                  <Th>Category</Th>
                  <Th>Resource ID</Th>
                  <Th>Type</Th>
                  <Th align="right">Est. Cost/mo</Th>
                  <Th>Detected</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {filteredFindings.map((f) => (
                  <tr key={f.finding_id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-3.5"><CategoryBadge category={f.category} /></td>
                    <td className="px-6 py-3.5 text-sm font-mono text-slate-700 break-all">{f.resource_id}</td>
                    <td className="px-6 py-3.5 text-sm text-slate-500">{f.resource_type}</td>
                    <td className="px-6 py-3.5 text-sm text-slate-900 text-right tabular-nums">
                      ${Number(f.estimated_monthly_cost || 0).toFixed(2)}
                    </td>
                    <td className="px-6 py-3.5 text-sm text-slate-500 tabular-nums">
                      {new Date(f.detected_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>
    </div>
  )
}

function KpiCard({ icon, label, value }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500 uppercase tracking-wider">
        {icon}<span>{label}</span>
      </div>
      <div className="mt-3 text-3xl font-semibold text-slate-900 tracking-tight tabular-nums">{value}</div>
    </div>
  )
}

function FilterChip({ label, active, onClick, color, disabled = false }) {
  return (
    <button
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      className={`inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-full border transition-all ${
        active
          ? 'bg-slate-900 text-white border-slate-900'
          : disabled
            ? 'bg-white text-slate-400 border-slate-200 cursor-not-allowed'
            : 'bg-white text-slate-700 border-slate-200 hover:border-slate-300 hover:bg-slate-50'
      }`}
    >
      {color && !active && (
        <span
          className="inline-block w-1.5 h-1.5 rounded-full mr-2"
          style={{ backgroundColor: color, opacity: disabled ? 0.4 : 1 }}
        />
      )}
      {label}
    </button>
  )
}

function Th({ children, align = 'left' }) {
  return (
    <th className={`px-6 py-3 text-${align} text-xs font-semibold text-slate-500 uppercase tracking-wider`}>
      {children}
    </th>
  )
}

function CategoryBadge({ category }) {
  const meta = CATEGORY_META[category]
  const label = meta?.label || category
  const color = meta?.color || '#94a3b8'
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full whitespace-nowrap"
      style={{ backgroundColor: `${color}15`, color: color }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}

export default App
