import { useState, useEffect, useRef } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer, LabelList } from 'recharts'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import kspLogo from './assets/ksp_logo.png'

const NEO4J_URI = import.meta.env.VITE_NEO4J_URI || 'bolt://localhost:7687'
const NEO4J_USERNAME = import.meta.env.VITE_NEO4J_USERNAME || 'neo4j'
const NEO4J_PASSWORD = import.meta.env.VITE_NEO4J_PASSWORD || 'sandy411'
const NEO4J_DATABASE = import.meta.env.VITE_NEO4J_DATABASE || 'neo4j'

declare global {
  interface Window {
    NeoVis?: any
  }
}

async function loadNeovisScript(): Promise<void> {
  if (typeof window === 'undefined') return
  if (window.NeoVis) return

  await new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-neovis]')
    if (existing) {
      if (window.NeoVis) { resolve(); return }
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('Failed to load Neovis')))
      return
    }

    const script = document.createElement('script')
    script.src = 'https://unpkg.com/neovis.js@2.0.2/dist/neovis.js'
    script.async = true
    script.dataset.neovis = 'true'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Neovis'))
    document.body.appendChild(script)
  })
}

interface SummaryData {
  ack_no: number
  total_transaction_amount: number
  total_disputed_amount: number
  total_put_on_hold_amount: number
  total_withdrawal_amount: number
  total_atm_withdrawal: number
  total_records: number
}

interface LayerData {
  layer: number
  amount: number
}

type ViewMode = 'chart' | 'graph'
type PageMode = 'dashboard' | 'investigation' | 'profiler' | 'triage' | 'intelligence'

function formatCurrency(val: number): string {
  return '₹ ' + val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatCompact(val: number): string {
  if (val >= 10000000) return '₹ ' + (val / 10000000).toFixed(2) + ' Cr'
  if (val >= 100000) return '₹ ' + (val / 100000).toFixed(2) + ' L'
  if (val >= 1000) return '₹ ' + (val / 1000).toFixed(1) + ' K'
  return '₹ ' + val.toFixed(0)
}

const LAYER_COLORS = [
  '#ffd400', '#43A047', '#FB8C00', '#E53935', '#8E24AA',
  '#6D4C41', '#00ACC1', '#C62828', '#1565C0', '#F06292',
  '#00897B', '#FFB300', '#5C6BC0',
]

function App() {
  const [ackNo, setAckNo] = useState('')
  const [data, setData] = useState<SummaryData | null>(null)
  const [layers, setLayers] = useState<LayerData[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [view, setView] = useState<ViewMode>('chart')
  const [page, setPage] = useState<PageMode>('dashboard')

  // Investigation state
  const [invAckNo, setInvAckNo] = useState('')
  const [invLoading, setInvLoading] = useState(false)
  const [invStatus, setInvStatus] = useState('')
  const [invReport, setInvReport] = useState('')
  const [invError, setInvError] = useState('')
  const invReportRef = useRef<HTMLDivElement | null>(null)

  // Neovis state
  const [graphReady, setGraphReady] = useState(false)
  const [graphCypher, setGraphCypher] = useState('')
  const [graphError, setGraphError] = useState('')
  const [graphStatus, setGraphStatus] = useState('')
  const graphRef = useRef<HTMLDivElement | null>(null)
  const graphVizRef = useRef<any>(null)

  // Load Neovis script on mount
  useEffect(() => {
    loadNeovisScript()
      .then(() => setGraphReady(true))
      .catch(() => setGraphError('Failed to load Neovis library.'))
  }, [])

  // Render graph when cypher changes or view switches to graph
  useEffect(() => {
    if (view !== 'graph') return
    if (!graphCypher || !graphReady || !graphRef.current) return
    if (!window.NeoVis) {
      setGraphError('Neovis is not available in the browser.')
      return
    }

    try {
      graphRef.current.innerHTML = ''

      const NeoVisModule = window.NeoVis as any
      const NEOVIS_ADV = NeoVisModule?.NEOVIS_ADVANCED_CONFIG || 'NEOVIS_ADVANCED_CONFIG'

      const config = {
        containerId: graphRef.current.id,
        neo4j: {
          serverUrl: NEO4J_URI,
          serverUser: NEO4J_USERNAME,
          serverPassword: NEO4J_PASSWORD,
          serverDatabase: NEO4J_DATABASE,
        },
        visConfig: {
          interaction: {
            hover: true,
            tooltipDelay: 100,
            hoverConnectedEdges: true,
          },
          nodes: {
            shape: 'dot',
            size: 16,
            font: { size: 0 },
          },
          edges: {
            arrows: { to: { enabled: true, scaleFactor: 0.7 } },
            smooth: { type: 'curvedCW', roundness: 0.2 },
            font: { size: 0 },
          },
          physics: { stabilization: true },
        },
        labels: {
          Account: {
            [NEOVIS_ADV]: {
              static: {
                label: '',
              },
              function: {
                title: (node: any) => {
                  const p = node.properties
                  const caseCount = p.case_count ? (p.case_count.toInt ? p.case_count.toInt() : Number(p.case_count)) : 1
                  const div = document.createElement('div')
                  div.style.cssText = 'font-family:Inter,sans-serif;font-size:13px;padding:6px 10px;line-height:1.6'
                  if (p.account_type === 'victim') {
                    div.innerHTML = [
                      `<b>Victim Account (Layer 0)</b>`,
                      `<b>Account No:</b> ${p.account_no || 'N/A'}`,
                      `<b>Acknowledgement No:</b> ${p.crime_no || p.name || 'N/A'}`,
                    ].join('<br/>')
                  } else {
                    const lines = [
                      `<b>Account:</b> ${p.account_no || 'N/A'}`,
                      `<b>Bank:</b> ${p.bank_name || 'N/A'}`,
                      `<b>IFSC:</b> ${p.bank_ifsc || 'N/A'}`,
                      `<b>Layer:</b> ${p.level ?? 'N/A'}`,
                    ]
                    if (caseCount > 1) {
                      lines.push(`<b style="color:#b10000">Involved in ${caseCount} cases — double-click to expand</b>`)
                    }
                    div.innerHTML = lines.join('<br/>')
                  }
                  return div
                },
                color: (node: any) => {
                  const layerColors: Record<number, string> = {
                    0: '#ffd400',
                    1: '#43A047',
                    2: '#FB8C00',
                    3: '#E53935',
                    4: '#8E24AA',
                    5: '#6D4C41',
                    6: '#00ACC1',
                    7: '#C62828',
                    8: '#1565C0',
                    9: '#F06292',
                    10: '#00897B',
                    11: '#FFB300',
                    12: '#5C6BC0',
                  }
                  const lvl = Number(node.properties.level) || 0
                  const bg = layerColors[lvl] || '#999999'
                  const caseCount = node.properties.case_count ? (node.properties.case_count.toInt ? node.properties.case_count.toInt() : Number(node.properties.case_count)) : 1
                  const isMultiCase = caseCount > 1 && node.properties.account_type !== 'victim'
                  const border = isMultiCase ? '#000000' : bg
                  const borderWidth = isMultiCase ? 4 : 1
                  return { background: bg, border, borderWidth, highlight: { background: bg, border: '#333', borderWidth }, hover: { background: bg, border: '#333', borderWidth } }
                },
                size: (node: any) => {
                  return node.properties.account_type === 'victim' ? 30 : 16
                },
              },
            },
          },
        },
        relationships: {
          TRANSFERRED_TO: {
            thickness: 'amount',
            [NEOVIS_ADV]: {
              static: {
                label: '',
              },
              function: {
                title: (rel: any) => {
                  const p = rel.properties
                  const amt = p.amount != null
                    ? `₹${Number(p.amount).toLocaleString('en-IN')}`
                    : 'N/A'
                  const div = document.createElement('div')
                  div.style.cssText = 'font-family:Inter,sans-serif;font-size:13px;padding:6px 10px'
                  div.innerHTML = `<b>Amount Transferred:</b> ${amt}`
                  return div
                },
              },
            },
          },
        },
        initialCypher: graphCypher,
      }

      const NeoVisClass = window.NeoVis?.default || window.NeoVis
      const viz = new NeoVisClass(config)
      graphVizRef.current = viz
      viz.render()

      // After graph renders, attach double-click handler for multi-case expansion
      viz.registerOnEvent('completed', () => {
        if (!viz.network) return
        viz.network.on('doubleClick', (params: any) => {
          if (!params.nodes || params.nodes.length === 0) return
          const nodeId = params.nodes[0]
          try {
            const visNode = viz.network.body.data.nodes.get(nodeId)
            if (!visNode?.raw?.properties) return
            const props = visNode.raw.properties
            if (props.account_type === 'victim') return
            const cc = props.case_count
            const caseCount = cc ? (cc.toInt ? cc.toInt() : Number(cc)) : 1
            if (caseCount <= 1) return
            const accountNo = String(props.account_no).replace(/'/g, "\\'")
            setGraphStatus(`Expanding connections for account ${props.account_no} (${caseCount} cases)...`)
            viz.updateWithCypher(
              `MATCH (a:Account {account_no: '${accountNo}'})-[r:TRANSFERRED_TO]-(b:Account) RETURN a, r, b`
            )
          } catch (e) {
            console.warn('Double-click expansion failed:', e)
          }
        })
      })
    } catch (err) {
      setGraphError(err instanceof Error ? err.message : 'Failed to render graph.')
    }
  }, [graphCypher, graphReady, view])

  async function handleSearch() {
    const trimmed = ackNo.trim()
    if (!trimmed) return

    setLoading(true)
    setError('')
    setData(null)
    setLayers([])
    setGraphCypher('')
    setGraphError('')
    setGraphStatus('')

    try {
      const [sumRes, layerRes] = await Promise.all([
        fetch(`/api/summary/${trimmed}`),
        fetch(`/api/layers/${trimmed}`),
      ])

      if (!sumRes.ok) {
        const body = await sumRes.json().catch(() => null)
        throw new Error(body?.detail || `No records found (HTTP ${sumRes.status})`)
      }

      const json: SummaryData = await sumRes.json()
      setData(json)

      if (layerRes.ok) {
        const layerJson: LayerData[] = await layerRes.json()
        setLayers(layerJson)
      }

      // Check graph data availability via backend API
      try {
        const graphRes = await fetch(`/api/graph/ack/${trimmed}`)
        if (graphRes.ok) {
          const graphJson = await graphRes.json()
          setGraphStatus(`Money flow graph loaded. ${graphJson.recordCount} transfer records.`)
          setGraphCypher(
            `MATCH (p:Account)-[r:TRANSFERRED_TO]->(c:Account) ` +
            `WHERE r.crime_no = '${trimmed}' ` +
            `RETURN p, r, c`
          )
        } else {
          setGraphStatus('No graph data available. Run neo4j_etl.py to load data.')
        }
      } catch {
        setGraphStatus('Neo4j not available. Run neo4j_etl.py to load graph data.')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleSearch()
  }

  async function handleInvestigate() {
    const trimmed = invAckNo.trim()
    if (!trimmed) return

    setInvLoading(true)
    setInvStatus('Starting investigation...')
    setInvReport('')
    setInvError('')

    try {
      const response = await fetch(`/api/investigate/${trimmed}`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response stream')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            if (event.type === 'status') {
              setInvStatus(event.message)
            } else if (event.type === 'token') {
              setInvReport(prev => prev + event.content)
              if (invReportRef.current) {
                invReportRef.current.scrollTop = invReportRef.current.scrollHeight
              }
            } else if (event.type === 'error') {
              setInvError(event.message)
              setInvStatus('')
            } else if (event.type === 'done') {
              setInvStatus('')
            }
          } catch {
            // skip malformed SSE lines
          }
        }
      }
    } catch (err) {
      setInvError(err instanceof Error ? err.message : 'Investigation failed')
    } finally {
      setInvLoading(false)
      if (!invError) setInvStatus('')
    }
  }

  function handleInvKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleInvestigate()
  }

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <img src={kspLogo} alt="KSP Logo" />
        </div>
        <div className="ksp-danger-divider" />
        <div className="sidebar-info">
          Karnataka State Police<br />
          Criminal Investigation Department
        </div>
        <div className="ksp-danger-divider" />

        {/* Dashboard views */}
        <button
          className={`sidebar-btn ${page === 'dashboard' && view === 'chart' ? 'sidebar-btn-active' : ''}`}
          onClick={() => { setPage('dashboard'); setView('chart') }}
        >
          Chart View
        </button>
        <button
          className={`sidebar-btn ${page === 'dashboard' && view === 'graph' ? 'sidebar-btn-active' : ''}`}
          onClick={() => { setPage('dashboard'); setView('graph') }}
        >
          Graph View
        </button>

        <div className="ksp-danger-divider" />
        <div className="sidebar-info">AI Agents for Investigation</div>

        <button
          className={`sidebar-btn ${page === 'investigation' ? 'sidebar-btn-active' : ''}`}
          onClick={() => setPage('investigation')}
        >
          Fraud Investigation
        </button>
        <button
          className={`sidebar-btn ${page === 'profiler' ? 'sidebar-btn-active' : ''}`}
          onClick={() => setPage('profiler')}
        >
          Account Profiler
        </button>
        <button
          className={`sidebar-btn ${page === 'triage' ? 'sidebar-btn-active' : ''}`}
          onClick={() => setPage('triage')}
        >
          Complaint Triage
        </button>
        <button
          className={`sidebar-btn ${page === 'intelligence' ? 'sidebar-btn-active' : ''}`}
          onClick={() => setPage('intelligence')}
        >
          Multi-Source Intel
        </button>
      </aside>

      {/* Main content */}
      <main className="main">
        {/* ============ DASHBOARD PAGE ============ */}
        {page === 'dashboard' && (
          <>
            <div className="ksp-banner">
              <h1 className="ksp-title">NCRP Cyber Fraud Dashboard</h1>
              <p className="ksp-subtitle">
                Search by Acknowledgement Number to view transaction summaries across all bank action trail tables.
              </p>
            </div>

            {/* Search */}
            <div className="ksp-card" style={{ marginBottom: 20 }}>
              <div className="search-row">
                <div className="input-group">
                  <label className="ksp-label">Acknowledgement Number</label>
                  <input
                    className="ksp-input"
                    type="text"
                    placeholder="e.g. 21612250083721"
                    value={ackNo}
                    onChange={e => setAckNo(e.target.value)}
                    onKeyDown={handleKeyDown}
                  />
                </div>
                <button className="btn-navy" onClick={handleSearch} disabled={loading || !ackNo.trim()}>
                  {loading ? 'Searching...' : 'Search'}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && <div className="error-box">{error}</div>}

            {/* Loading */}
            {loading && <div className="loading">Querying database...</div>}

            {/* Results */}
            {data && !loading && (
              <>
                {/* Summary cards */}
                <div className="summary-cards">
                  <div className="summary-card card-transaction">
                    <div className="card-label">Total Transaction Amount</div>
                    <div className="card-value">{formatCurrency(data.total_transaction_amount)}</div>
                  </div>
                  <div className="summary-card card-disputed">
                    <div className="card-label">Total Disputed Amount</div>
                    <div className="card-value">{formatCurrency(data.total_disputed_amount)}</div>
                  </div>
                  <div className="summary-card card-hold">
                    <div className="card-label">Total Put On Hold Amount</div>
                    <div className="card-value">{formatCurrency(data.total_put_on_hold_amount)}</div>
                  </div>
                  <div className="summary-card card-withdrawal">
                    <div className="card-label">Total Withdrawal Amount</div>
                    <div className="card-value">{formatCurrency(data.total_withdrawal_amount)}</div>
                  </div>
                  <div className="summary-card card-atm">
                    <div className="card-label">Total ATM Withdrawal</div>
                    <div className="card-value">{formatCurrency(data.total_atm_withdrawal)}</div>
                  </div>
                </div>

                {/* Chart View */}
                {view === 'chart' && layers.length > 0 && (
                  <div className="ksp-card chart-section">
                    <h3 className="chart-title">Transaction Amount by Layer</h3>
                    <ResponsiveContainer width="100%" height={400}>
                      <BarChart data={layers} margin={{ top: 30, right: 30, left: 20, bottom: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                        <XAxis
                          dataKey="layer"
                          tickFormatter={(v: number) => `Layer ${v}`}
                          tick={{ fontSize: 13, fontWeight: 600 }}
                        />
                        <YAxis
                          tickFormatter={(v: number) => formatCompact(v)}
                          tick={{ fontSize: 12 }}
                        />
                        <Tooltip
                          formatter={(value) => [formatCurrency(Number(value)), 'Amount']}
                          labelFormatter={(label) => `Layer ${label}`}
                        />
                        <Bar dataKey="amount" radius={[6, 6, 0, 0]} maxBarSize={80}>
                          <LabelList
                            dataKey="amount"
                            position="top"
                            formatter={(v) => formatCurrency(Number(v))}
                            style={{ fontSize: 11, fontWeight: 600, fill: '#333' }}
                          />
                          {layers.map((_entry, idx) => (
                            <Cell key={idx} fill={LAYER_COLORS[idx % LAYER_COLORS.length]} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* Graph View */}
                {view === 'graph' && (
                  <div className="ksp-card chart-section">
                    <h3 className="chart-title">Money Flow Graph</h3>
                    <div className="graph-legend">
                      <span className="legend-title">Layer Colors:</span>
                      <span className="legend-item legend-l0">Victim (L0)</span>
                      <span className="legend-item legend-l1">L1</span>
                      <span className="legend-item legend-l2">L2</span>
                      <span className="legend-item legend-l3">L3</span>
                      <span className="legend-item legend-l4">L4</span>
                      <span className="legend-item legend-l5">L5</span>
                      <span className="legend-item legend-l6">L6</span>
                      <span className="legend-item legend-l7">L7</span>
                      <span className="legend-item legend-l8">L8</span>
                      <span className="legend-item legend-l9">L9</span>
                      <span className="legend-item legend-l10">L10</span>
                      <span className="legend-item legend-l11">L11</span>
                      <span className="legend-item legend-l12">L12</span>
                    </div>
                    {graphStatus && <div className="graph-status-msg">{graphStatus}</div>}
                    {graphError && <div className="error-box" style={{ margin: '12px 0' }}>{graphError}</div>}
                    <div className="graph-canvas" id="kspGraph" ref={graphRef}>
                      {!graphCypher && !graphError && (
                        <div className="graph-placeholder">Graph will render here after search.</div>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* Empty state */}
            {!data && !loading && !error && (
              <div className="empty-state">
                Enter an Acknowledgement Number above to view the financial summary.
              </div>
            )}
          </>
        )}

        {/* ============ FRAUD INVESTIGATION PAGE ============ */}
        {page === 'investigation' && (
          <>
            <div className="ksp-banner">
              <h1 className="ksp-title">Fraud Investigation Assistant</h1>
              <p className="ksp-subtitle">
                AI-powered agent that autonomously analyzes money flow, identifies suspicious patterns, and generates investigation reports.
              </p>
            </div>

            {/* Search */}
            <div className="ksp-card" style={{ marginBottom: 20 }}>
              <div className="search-row">
                <div className="input-group">
                  <label className="ksp-label">Acknowledgement Number</label>
                  <input
                    className="ksp-input"
                    type="text"
                    placeholder="e.g. 21612250083721"
                    value={invAckNo}
                    onChange={e => setInvAckNo(e.target.value)}
                    onKeyDown={handleInvKeyDown}
                    disabled={invLoading}
                  />
                </div>
                <button
                  className="btn-navy"
                  onClick={handleInvestigate}
                  disabled={invLoading || !invAckNo.trim()}
                >
                  {invLoading ? 'Investigating...' : 'Investigate'}
                </button>
              </div>
            </div>

            {/* Status */}
            {invStatus && (
              <div className="inv-status">
                <span className="inv-status-dot" />
                {invStatus}
              </div>
            )}

            {/* Error */}
            {invError && <div className="error-box">{invError}</div>}

            {/* Report */}
            {invReport && (
              <div className="ksp-card inv-report-card">
                <div className="inv-report-top-bar">
                  <div className="inv-report-ack">
                    <span className="inv-report-ack-label">Acknowledgement No.</span>
                    <span className="inv-report-ack-value">{invAckNo}</span>
                  </div>
                  <div className="inv-report-header-right">
                    <h3 className="inv-report-title">Investigation Report</h3>
                    {!invLoading && (
                      <span className="inv-report-badge">
                        <span className="inv-report-badge-dot" />
                        Analysis Complete
                      </span>
                    )}
                    {invLoading && (
                      <span className="inv-report-badge inv-report-badge-progress">
                        <span className="inv-status-dot" />
                        Generating...
                      </span>
                    )}
                  </div>
                </div>
                <div className="inv-report" ref={invReportRef}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {invReport}
                  </ReactMarkdown>
                </div>
              </div>
            )}

            {/* Empty state */}
            {!invReport && !invLoading && !invError && (
              <div className="empty-state">
                Enter an Acknowledgement Number and click Investigate to generate an AI-powered investigation report.
              </div>
            )}
          </>
        )}

        {/* ============ ACCOUNT PROFILER PAGE ============ */}
        {page === 'profiler' && (
          <>
            <div className="ksp-banner">
              <h1 className="ksp-title">Suspect Account Profiler</h1>
              <p className="ksp-subtitle">
                AI agent that profiles suspect accounts — maps all connected cases, counterparties, and generates a risk assessment.
              </p>
            </div>
            <div className="empty-state">
              Coming soon — Enter an Account Number and the AI agent will build a comprehensive profile.
            </div>
          </>
        )}

        {/* ============ COMPLAINT TRIAGE PAGE ============ */}
        {page === 'triage' && (
          <>
            <div className="ksp-banner">
              <h1 className="ksp-title">Complaint Triage Agent</h1>
              <p className="ksp-subtitle">
                AI agent that reads incoming complaints, classifies fraud type, extracts entities, and prioritizes cases automatically.
              </p>
            </div>
            <div className="empty-state">
              Coming soon — Paste or upload a complaint and the AI agent will classify and extract key information.
            </div>
          </>
        )}

        {/* ============ MULTI-SOURCE INTELLIGENCE PAGE ============ */}
        {page === 'intelligence' && (
          <>
            <div className="ksp-banner">
              <h1 className="ksp-title">Multi-Source Intelligence Agent</h1>
              <p className="ksp-subtitle">
                AI agent that correlates data across NCRP tables, bank responses, and telecom records to build unified intelligence.
              </p>
            </div>
            <div className="empty-state">
              Coming soon — Ask questions in natural language and the AI agent will query multiple data sources.
            </div>
          </>
        )}
      </main>
    </div>
  )
}

export default App
