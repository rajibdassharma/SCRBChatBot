import { useState, useEffect, useRef } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer, LabelList } from 'recharts'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import html2pdf from 'html2pdf.js'
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

const MULE_PAGE_SIZE = 10

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

  // Profiler state
  const [muleAccounts, setMuleAccounts] = useState<any[]>([])
  const [muleSummary, setMuleSummary] = useState<any>(null)
  const [muleLoading, setMuleLoading] = useState(false)
  const [muleError, setMuleError] = useState('')
  const [muleLoaded, setMuleLoaded] = useState(false)
  const [profileAccount, setProfileAccount] = useState('')
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileStatus, setProfileStatus] = useState('')
  const [profileReport, setProfileReport] = useState('')
  const [profileError, setProfileError] = useState('')
  const [muleSortBy, setMuleSortBy] = useState<'case_count' | 'total_amount' | 'risk'>('case_count')
  const [mulePage, setMulePage] = useState(0)
  const [profilerView, setProfilerView] = useState<'list' | 'profile'>('list')
  const profileReportRef = useRef<HTMLDivElement | null>(null)
  const muleListRef = useRef<HTMLDivElement | null>(null)

  // Triage state
  type TriageView = 'paste' | 'batch'
  const [triageView, setTriageView] = useState<TriageView>('paste')
  const [triageText, setTriageText] = useState('')
  const [triageLoading, setTriageLoading] = useState(false)
  const [triageStatus, setTriageStatus] = useState('')
  const [triageReport, setTriageReport] = useState('')
  const [triageError, setTriageError] = useState('')
  const [triageEntities, setTriageEntities] = useState<any>(null)
  const triageReportRef = useRef<HTMLDivElement | null>(null)

  // Batch triage state
  const [batchCases, setBatchCases] = useState<any[]>([])
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchError, setBatchError] = useState('')
  const [batchLoaded, setBatchLoaded] = useState(false)
  const [batchSortBy, setBatchSortBy] = useState<'auto_score' | 'total_amount' | 'mule_account_count'>('auto_score')
  const [batchPage, setBatchPage] = useState(0)
  const BATCH_PAGE_SIZE = 15

  // Intelligence state
  const [intelQuestion, setIntelQuestion] = useState('')
  const [intelLoading, setIntelLoading] = useState(false)
  const [intelStatus, setIntelStatus] = useState('')
  const [intelReport, setIntelReport] = useState('')
  const [intelError, setIntelError] = useState('')
  const [intelQueries, setIntelQueries] = useState<{sql?: string, cypher?: string, explanation?: string} | null>(null)
  const [intelShowQueries, setIntelShowQueries] = useState(false)
  const [intelHistory, setIntelHistory] = useState<Array<{question: string, report: string, queries: any}>>([])
  const intelReportRef = useRef<HTMLDivElement | null>(null)

  const INTEL_SUGGESTED_QUESTIONS = [
    'Which banks have the most fraud cases?',
    'Top 10 mule accounts by transaction amount',
    'Cases with highest unrecovered amounts',
    'Total amount frozen vs total disputed',
    'Accounts connected to more than 5 cases',
    'ATM withdrawal hotspots',
    'Money flow depth analysis across all cases',
  ]

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

  // ── Profiler functions ──

  async function loadMuleAccounts() {
    setMuleLoading(true)
    setMuleError('')
    setMuleAccounts([])
    setMuleSummary(null)

    try {
      const res = await fetch('/api/profiler/mule-accounts')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setMuleSummary(json.summary)
      setMuleAccounts(json.accounts)
      setMuleLoaded(true)
    } catch (err) {
      setMuleError(err instanceof Error ? err.message : 'Failed to load mule accounts')
    } finally {
      setMuleLoading(false)
    }
  }

  // Auto-load mule accounts when profiler page is opened
  useEffect(() => {
    if (page === 'profiler' && !muleLoaded && !muleLoading) {
      loadMuleAccounts()
    }
  }, [page])

  function getSortedMuleAccounts() {
    const sorted = [...muleAccounts]
    if (muleSortBy === 'case_count') {
      sorted.sort((a, b) => b.case_count - a.case_count || b.total_amount - a.total_amount)
    } else if (muleSortBy === 'total_amount') {
      sorted.sort((a, b) => b.total_amount - a.total_amount)
    } else if (muleSortBy === 'risk') {
      const riskOrder: Record<string, number> = { CRITICAL: 3, HIGH: 2, MEDIUM: 1 }
      sorted.sort((a, b) => (riskOrder[b.risk] || 0) - (riskOrder[a.risk] || 0) || b.case_count - a.case_count)
    }
    return sorted
  }

  function handleDownloadPdf(element: HTMLElement | null, filename: string) {
    if (!element) return
    const opt = {
      margin: [10, 10, 10, 10] as [number, number, number, number],
      filename,
      image: { type: 'jpeg' as const, quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true, scrollY: 0 },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'landscape' as const },
    }
    html2pdf().set(opt).from(element).save()
  }

  // ── Triage functions ──

  async function handleTriage() {
    const trimmed = triageText.trim()
    if (!trimmed) return

    setTriageLoading(true)
    setTriageStatus('Starting complaint triage...')
    setTriageReport('')
    setTriageError('')
    setTriageEntities(null)

    try {
      const response = await fetch('/api/triage/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

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
              setTriageStatus(event.message)
            } else if (event.type === 'entities') {
              setTriageEntities(event.data)
            } else if (event.type === 'token') {
              setTriageReport(prev => prev + event.content)
              if (triageReportRef.current) {
                triageReportRef.current.scrollTop = triageReportRef.current.scrollHeight
              }
            } else if (event.type === 'error') {
              setTriageError(event.message)
              setTriageStatus('')
            } else if (event.type === 'done') {
              setTriageStatus('')
            }
          } catch {
            // skip malformed SSE lines
          }
        }
      }
    } catch (err) {
      setTriageError(err instanceof Error ? err.message : 'Triage failed')
    } finally {
      setTriageLoading(false)
      setTriageStatus('')
    }
  }

  async function loadBatchCases() {
    setBatchLoading(true)
    setBatchError('')
    setBatchCases([])

    try {
      const res = await fetch('/api/triage/cases')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setBatchCases(json.cases)
      setBatchLoaded(true)
    } catch (err) {
      setBatchError(err instanceof Error ? err.message : 'Failed to load cases')
    } finally {
      setBatchLoading(false)
    }
  }

  useEffect(() => {
    if (page === 'triage' && triageView === 'batch' && !batchLoaded && !batchLoading) {
      loadBatchCases()
    }
  }, [page, triageView])

  function getSortedBatchCases() {
    const sorted = [...batchCases]
    if (batchSortBy === 'auto_score') {
      sorted.sort((a, b) => b.auto_score - a.auto_score)
    } else if (batchSortBy === 'total_amount') {
      sorted.sort((a, b) => b.total_amount - a.total_amount)
    } else if (batchSortBy === 'mule_account_count') {
      sorted.sort((a, b) => b.mule_account_count - a.mule_account_count || b.auto_score - a.auto_score)
    }
    return sorted
  }

  // ── Intelligence functions ──

  async function handleIntelQuery(question?: string) {
    const q = (question || intelQuestion).trim()
    if (!q) return

    setIntelLoading(true)
    setIntelStatus('Understanding your question...')
    setIntelReport('')
    setIntelError('')
    setIntelQueries(null)
    setIntelShowQueries(false)
    if (!question) setIntelQuestion(q)

    try {
      const response = await fetch('/api/intelligence/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response stream')

      const decoder = new TextDecoder()
      let buffer = ''
      let finalReport = ''
      let finalQueries: any = null

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
              setIntelStatus(event.message)
            } else if (event.type === 'queries') {
              finalQueries = event.data
              setIntelQueries(event.data)
            } else if (event.type === 'token') {
              finalReport += event.content
              setIntelReport(prev => prev + event.content)
              if (intelReportRef.current) {
                intelReportRef.current.scrollTop = intelReportRef.current.scrollHeight
              }
            } else if (event.type === 'error') {
              setIntelError(event.message)
              setIntelStatus('')
            } else if (event.type === 'done') {
              setIntelStatus('')
            }
          } catch {
            // skip malformed SSE lines
          }
        }
      }

      // Save to history
      if (finalReport) {
        setIntelHistory(prev => [{ question: q, report: finalReport, queries: finalQueries }, ...prev])
      }
    } catch (err) {
      setIntelError(err instanceof Error ? err.message : 'Intelligence query failed')
    } finally {
      setIntelLoading(false)
      setIntelStatus('')
    }
  }

  function handleIntelKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleIntelQuery()
  }

  function handleBackToMuleList() {
    setProfilerView('list')
    setProfileReport('')
    setProfileStatus('')
    setProfileError('')
    setProfileAccount('')
  }

  async function handleProfileAccount(accountNo: string) {
    setProfileAccount(accountNo)
    setProfilerView('profile')
    setProfileLoading(true)
    setProfileStatus('Starting account profiling...')
    setProfileReport('')
    setProfileError('')

    try {
      const response = await fetch(`/api/profiler/account/${encodeURIComponent(accountNo)}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

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
              setProfileStatus(event.message)
            } else if (event.type === 'token') {
              setProfileReport(prev => prev + event.content)
              if (profileReportRef.current) {
                profileReportRef.current.scrollTop = profileReportRef.current.scrollHeight
              }
            } else if (event.type === 'error') {
              setProfileError(event.message)
              setProfileStatus('')
            } else if (event.type === 'done') {
              setProfileStatus('')
            }
          } catch {
            // skip malformed SSE lines
          }
        }
      }
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : 'Profiling failed')
    } finally {
      setProfileLoading(false)
      if (!profileError) setProfileStatus('')
    }
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
        {page === 'profiler' && profilerView === 'list' && (
          <>
            <div className="profiler-top-actions">
              <div className="ksp-banner" style={{ flex: 1, marginBottom: 0 }}>
                <h1 className="ksp-title">Suspect Account Profiler</h1>
                <p className="ksp-subtitle">
                  Auto-detects mule accounts involved in multiple fraud cases. Click any account for AI-powered deep profiling.
                </p>
              </div>
              {muleAccounts.length > 0 && (
                <button
                  className="pdf-download-btn"
                  onClick={() => handleDownloadPdf(muleListRef.current, 'Mule_Accounts_Report.pdf')}
                >
                  Download PDF
                </button>
              )}
            </div>

            <div ref={muleListRef}>
            {/* Summary cards */}
            {muleSummary && (
              <div className="profiler-summary-cards">
                <div className="profiler-stat-card profiler-stat-total">
                  <div className="profiler-stat-label">Total Mule Accounts</div>
                  <div className="profiler-stat-value">{muleSummary.total_mule_accounts.toLocaleString()}</div>
                  <div className="profiler-stat-sub">Involved in 2+ cases</div>
                </div>
                <div className="profiler-stat-card profiler-stat-critical">
                  <div className="profiler-stat-label">Critical Risk</div>
                  <div className="profiler-stat-value">{muleSummary.critical.toLocaleString()}</div>
                  <div className="profiler-stat-sub">5+ cases</div>
                </div>
                <div className="profiler-stat-card profiler-stat-high">
                  <div className="profiler-stat-label">High Risk</div>
                  <div className="profiler-stat-value">{muleSummary.high.toLocaleString()}</div>
                  <div className="profiler-stat-sub">3-4 cases</div>
                </div>
                <div className="profiler-stat-card profiler-stat-medium">
                  <div className="profiler-stat-label">Medium Risk</div>
                  <div className="profiler-stat-value">{muleSummary.medium.toLocaleString()}</div>
                  <div className="profiler-stat-sub">2 cases</div>
                </div>
                <div className="profiler-stat-card profiler-stat-amount">
                  <div className="profiler-stat-label">Total Amount Involved</div>
                  <div className="profiler-stat-value">{formatCurrency(muleSummary.total_amount_involved)}</div>
                </div>
              </div>
            )}

            {/* Loading */}
            {muleLoading && <div className="loading">Scanning database for mule accounts...</div>}

            {/* Error */}
            {muleError && (
              <div className="error-box">
                {muleError}
                <button className="btn-navy" style={{ marginLeft: 12 }} onClick={loadMuleAccounts}>Retry</button>
              </div>
            )}

            {/* Sort controls */}
            {muleAccounts.length > 0 && (
              <div className="ksp-card" style={{ marginBottom: 16 }}>
                <div className="profiler-controls">
                  <span className="profiler-controls-label">Sort by:</span>
                  <button
                    className={`profiler-sort-btn ${muleSortBy === 'case_count' ? 'profiler-sort-active' : ''}`}
                    onClick={() => { setMuleSortBy('case_count'); setMulePage(0) }}
                  >
                    Case Count
                  </button>
                  <button
                    className={`profiler-sort-btn ${muleSortBy === 'total_amount' ? 'profiler-sort-active' : ''}`}
                    onClick={() => { setMuleSortBy('total_amount'); setMulePage(0) }}
                  >
                    Amount
                  </button>
                  <button
                    className={`profiler-sort-btn ${muleSortBy === 'risk' ? 'profiler-sort-active' : ''}`}
                    onClick={() => { setMuleSortBy('risk'); setMulePage(0) }}
                  >
                    Risk Level
                  </button>
                  <span className="profiler-count-label">
                    Showing {mulePage * MULE_PAGE_SIZE + 1}–{Math.min((mulePage + 1) * MULE_PAGE_SIZE, muleAccounts.length)} of {muleAccounts.length} accounts
                  </span>
                </div>
              </div>
            )}

            {/* Mule accounts table */}
            {muleAccounts.length > 0 && (
              <div className="ksp-card">
                <div className="profiler-table-wrap">
                  <table className="profiler-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Account No</th>
                        <th>Bank</th>
                        <th>Cases</th>
                        <th>Appearances</th>
                        <th>Total Amount</th>
                        <th>Layers</th>
                        <th>Risk</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {getSortedMuleAccounts().slice(mulePage * MULE_PAGE_SIZE, (mulePage + 1) * MULE_PAGE_SIZE).map((acct, idx) => (
                        <tr key={acct.account_no} className={`profiler-row profiler-row-${acct.risk.toLowerCase()}`}>
                          <td className="profiler-cell-idx">{mulePage * MULE_PAGE_SIZE + idx + 1}</td>
                          <td className="profiler-cell-account">{acct.account_no}</td>
                          <td>{acct.bank}</td>
                          <td className="profiler-cell-cases">{acct.case_count}</td>
                          <td>{acct.total_appearances}</td>
                          <td className="profiler-cell-amount">{formatCurrency(acct.total_amount)}</td>
                          <td>{acct.min_layer === acct.max_layer ? `L${acct.min_layer}` : `L${acct.min_layer}-L${acct.max_layer}`}</td>
                          <td>
                            <span className={`profiler-risk-badge profiler-risk-${acct.risk.toLowerCase()}`}>
                              {acct.risk === 'CRITICAL' ? '🔴' : acct.risk === 'HIGH' ? '🟠' : '🟡'} {acct.risk}
                            </span>
                          </td>
                          <td>
                            <button
                              className="profiler-profile-btn"
                              onClick={() => handleProfileAccount(acct.account_no)}
                              disabled={profileLoading}
                            >
                              Profile
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination controls */}
                {muleAccounts.length > MULE_PAGE_SIZE && (
                  <div className="profiler-pagination">
                    <button
                      className="profiler-page-btn"
                      onClick={() => setMulePage(p => p - 1)}
                      disabled={mulePage === 0}
                    >
                      ← Back
                    </button>
                    <span className="profiler-page-info">
                      Page {mulePage + 1} of {Math.ceil(muleAccounts.length / MULE_PAGE_SIZE)}
                    </span>
                    <button
                      className="profiler-page-btn"
                      onClick={() => setMulePage(p => p + 1)}
                      disabled={(mulePage + 1) * MULE_PAGE_SIZE >= muleAccounts.length}
                    >
                      Next →
                    </button>
                  </div>
                )}
              </div>
            )}
            </div>
          </>
        )}

        {/* ============ ACCOUNT PROFILE REPORT VIEW ============ */}
        {page === 'profiler' && profilerView === 'profile' && (
          <>
            <div className="ksp-banner">
              <h1 className="ksp-title">Suspect Account Profiler</h1>
              <p className="ksp-subtitle">
                AI-powered deep profile for account <strong>{profileAccount}</strong>
              </p>
            </div>

            <div className="profiler-action-row">
              <button className="profiler-back-btn" onClick={handleBackToMuleList}>
                ← Back to Mule Accounts
              </button>
              {profileReport && !profileLoading && (
                <button
                  className="pdf-download-btn"
                  onClick={() => handleDownloadPdf(profileReportRef.current, `Profile_${profileAccount}.pdf`)}
                >
                  Download PDF
                </button>
              )}
            </div>

            {/* Status */}
            {profileStatus && (
              <div className="inv-status">
                <span className="inv-status-dot" />
                {profileStatus}
              </div>
            )}

            {/* Error */}
            {profileError && <div className="error-box">{profileError}</div>}

            {/* Report */}
            {profileReport && (
              <div className="ksp-card inv-report-card">
                <div className="inv-report-top-bar profiler-report-top-bar">
                  <div className="inv-report-ack">
                    <span className="inv-report-ack-label">Account No.</span>
                    <span className="inv-report-ack-value">{profileAccount}</span>
                  </div>
                  <div className="inv-report-header-right">
                    <h3 className="inv-report-title">Account Profile Report</h3>
                    {!profileLoading && (
                      <span className="inv-report-badge">
                        <span className="inv-report-badge-dot" />
                        Analysis Complete
                      </span>
                    )}
                    {profileLoading && (
                      <span className="inv-report-badge inv-report-badge-progress">
                        <span className="inv-status-dot" />
                        Generating...
                      </span>
                    )}
                  </div>
                </div>
                <div className="inv-report" ref={profileReportRef}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {profileReport}
                  </ReactMarkdown>
                </div>
              </div>
            )}
          </>
        )}

        {/* ============ COMPLAINT TRIAGE PAGE ============ */}
        {page === 'triage' && (
          <>
            <div className="ksp-banner">
              <h1 className="ksp-title">Complaint Triage Agent</h1>
              <p className="ksp-subtitle">
                AI agent that reads incoming complaints, classifies fraud type, extracts entities,
                cross-references with NCRP database, and prioritizes cases.
              </p>
            </div>

            {/* Tab bar */}
            <div className="triage-tabs">
              <button
                className={`triage-tab ${triageView === 'paste' ? 'triage-tab-active' : ''}`}
                onClick={() => setTriageView('paste')}
              >
                Paste &amp; Triage
              </button>
              <button
                className={`triage-tab ${triageView === 'batch' ? 'triage-tab-active' : ''}`}
                onClick={() => setTriageView('batch')}
              >
                Case Priority Dashboard
              </button>
            </div>

            {/* === PASTE & TRIAGE VIEW === */}
            {triageView === 'paste' && (
              <>
                <div className="ksp-card" style={{ marginBottom: 20 }}>
                  <label className="ksp-label">Paste Complaint Text</label>
                  <textarea
                    className="triage-textarea"
                    placeholder="Paste the complaint text from NCRP portal, victim email, or FIR here..."
                    value={triageText}
                    onChange={e => setTriageText(e.target.value)}
                    disabled={triageLoading}
                    rows={8}
                  />
                  <div className="triage-actions">
                    <button
                      className="btn-navy"
                      onClick={handleTriage}
                      disabled={triageLoading || !triageText.trim()}
                    >
                      {triageLoading ? 'Analyzing...' : 'Analyze Complaint'}
                    </button>
                    <span className="triage-char-count">
                      {triageText.length.toLocaleString()} characters
                    </span>
                  </div>
                </div>

                {/* Status */}
                {triageStatus && (
                  <div className="inv-status">
                    <span className="inv-status-dot" />
                    {triageStatus}
                  </div>
                )}

                {/* Error */}
                {triageError && <div className="error-box">{triageError}</div>}

                {/* Entities card */}
                {triageEntities && (
                  <div className="triage-entities-card">
                    <div className="triage-priority-header">
                      <div className="triage-priority-badge-wrap">
                        <span className={`triage-priority-badge triage-priority-${triageEntities.priority?.priority?.toLowerCase()}`}>
                          {triageEntities.priority?.priority}
                        </span>
                        <span className="triage-priority-score">
                          Score: {triageEntities.priority?.score}/100
                        </span>
                      </div>
                      <span className="triage-fraud-type">
                        {triageEntities.extracted?.fraud_type?.replace(/_/g, ' ').toUpperCase() || 'UNCLASSIFIED'}
                      </span>
                    </div>

                    <div className="triage-entities-grid">
                      {triageEntities.extracted?.accounts?.length > 0 && (
                        <div className="triage-entity-group">
                          <div className="triage-entity-label">Accounts Extracted</div>
                          {triageEntities.extracted.accounts.map((a: string) => (
                            <span key={a} className="triage-entity-chip triage-chip-account">{a}</span>
                          ))}
                        </div>
                      )}
                      {triageEntities.extracted?.bank_names?.length > 0 && (
                        <div className="triage-entity-group">
                          <div className="triage-entity-label">Banks</div>
                          {triageEntities.extracted.bank_names.map((b: string) => (
                            <span key={b} className="triage-entity-chip triage-chip-bank">{b}</span>
                          ))}
                        </div>
                      )}
                      {triageEntities.extracted?.upi_ids?.length > 0 && (
                        <div className="triage-entity-group">
                          <div className="triage-entity-label">UPI IDs</div>
                          {triageEntities.extracted.upi_ids.map((u: string) => (
                            <span key={u} className="triage-entity-chip triage-chip-upi">{u}</span>
                          ))}
                        </div>
                      )}
                      {triageEntities.extracted?.amounts?.length > 0 && (
                        <div className="triage-entity-group">
                          <div className="triage-entity-label">Amounts</div>
                          {triageEntities.extracted.amounts.map((a: number, i: number) => (
                            <span key={i} className="triage-entity-chip triage-chip-amount">
                              {formatCurrency(a)}
                            </span>
                          ))}
                        </div>
                      )}
                      {triageEntities.extracted?.phone_numbers?.length > 0 && (
                        <div className="triage-entity-group">
                          <div className="triage-entity-label">Phone Numbers</div>
                          {triageEntities.extracted.phone_numbers.map((p: string) => (
                            <span key={p} className="triage-entity-chip triage-chip-account">{p}</span>
                          ))}
                        </div>
                      )}
                      {triageEntities.extracted?.payment_methods?.length > 0 && (
                        <div className="triage-entity-group">
                          <div className="triage-entity-label">Payment Methods</div>
                          {triageEntities.extracted.payment_methods.map((m: string) => (
                            <span key={m} className="triage-entity-chip triage-chip-bank">{m}</span>
                          ))}
                        </div>
                      )}
                      {triageEntities.mssql_xref?.total_matched_accounts > 0 && (
                        <div className="triage-entity-group triage-entity-alert">
                          <div className="triage-entity-label">Database Matches</div>
                          <span className="triage-match-alert">
                            {triageEntities.mssql_xref.total_matched_accounts} account(s) found in {triageEntities.mssql_xref.total_cases} existing case(s)
                          </span>
                        </div>
                      )}
                      {triageEntities.graph_xref?.mule_count > 0 && (
                        <div className="triage-entity-group triage-entity-alert">
                          <div className="triage-entity-label">Mule Account Alerts</div>
                          <span className="triage-match-alert">
                            {triageEntities.graph_xref.mule_count} account(s) flagged as mule (multi-case)
                          </span>
                        </div>
                      )}
                    </div>

                    {triageEntities.priority?.reasons?.length > 0 && (
                      <div className="triage-reasons">
                        <div className="triage-entity-label" style={{ marginBottom: 4 }}>Priority Factors</div>
                        {triageEntities.priority.reasons.map((r: string, i: number) => (
                          <span key={i} className="triage-reason-chip">{r}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Streaming report */}
                {triageReport && (
                  <div className="ksp-card inv-report-card">
                    <div className="inv-report-top-bar triage-report-top-bar">
                      <div className="inv-report-ack">
                        <span className="inv-report-ack-label">Complaint Triage</span>
                        <span className="inv-report-ack-value">
                          {triageEntities?.extracted?.fraud_type?.replace(/_/g, ' ').toUpperCase() || 'Analysis'}
                        </span>
                      </div>
                      <div className="inv-report-header-right">
                        <h3 className="inv-report-title">Triage Report</h3>
                        {!triageLoading && (
                          <span className="inv-report-badge">
                            <span className="inv-report-badge-dot" />
                            Analysis Complete
                          </span>
                        )}
                        {triageLoading && (
                          <span className="inv-report-badge inv-report-badge-progress">
                            <span className="inv-status-dot" />
                            Generating...
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="inv-report" ref={triageReportRef}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {triageReport}
                      </ReactMarkdown>
                    </div>
                  </div>
                )}

                {/* Empty state */}
                {!triageReport && !triageLoading && !triageError && !triageEntities && (
                  <div className="empty-state">
                    Paste a complaint above and click Analyze to run AI-powered triage.
                  </div>
                )}
              </>
            )}

            {/* === BATCH CASE PRIORITY DASHBOARD === */}
            {triageView === 'batch' && (
              <>
                {batchLoading && <div className="loading">Loading case priority data...</div>}
                {batchError && (
                  <div className="error-box">
                    {batchError}
                    <button className="btn-navy" style={{ marginLeft: 12 }} onClick={loadBatchCases}>Retry</button>
                  </div>
                )}

                {/* Summary stats */}
                {batchCases.length > 0 && (
                  <div className="profiler-summary-cards">
                    <div className="profiler-stat-card profiler-stat-total">
                      <div className="profiler-stat-label">Total Cases</div>
                      <div className="profiler-stat-value">{batchCases.length.toLocaleString()}</div>
                    </div>
                    <div className="profiler-stat-card profiler-stat-critical">
                      <div className="profiler-stat-label">Critical</div>
                      <div className="profiler-stat-value">{batchCases.filter(c => c.auto_priority === 'CRITICAL').length}</div>
                    </div>
                    <div className="profiler-stat-card profiler-stat-high">
                      <div className="profiler-stat-label">High</div>
                      <div className="profiler-stat-value">{batchCases.filter(c => c.auto_priority === 'HIGH').length}</div>
                    </div>
                    <div className="profiler-stat-card profiler-stat-medium">
                      <div className="profiler-stat-label">Medium</div>
                      <div className="profiler-stat-value">{batchCases.filter(c => c.auto_priority === 'MEDIUM').length}</div>
                    </div>
                    <div className="profiler-stat-card profiler-stat-amount">
                      <div className="profiler-stat-label">Low</div>
                      <div className="profiler-stat-value">{batchCases.filter(c => c.auto_priority === 'LOW').length}</div>
                    </div>
                  </div>
                )}

                {/* Sort controls */}
                {batchCases.length > 0 && (
                  <div className="ksp-card" style={{ marginBottom: 16 }}>
                    <div className="profiler-controls">
                      <span className="profiler-controls-label">Sort by:</span>
                      <button
                        className={`profiler-sort-btn ${batchSortBy === 'auto_score' ? 'profiler-sort-active' : ''}`}
                        onClick={() => { setBatchSortBy('auto_score'); setBatchPage(0) }}
                      >
                        Priority Score
                      </button>
                      <button
                        className={`profiler-sort-btn ${batchSortBy === 'total_amount' ? 'profiler-sort-active' : ''}`}
                        onClick={() => { setBatchSortBy('total_amount'); setBatchPage(0) }}
                      >
                        Amount
                      </button>
                      <button
                        className={`profiler-sort-btn ${batchSortBy === 'mule_account_count' ? 'profiler-sort-active' : ''}`}
                        onClick={() => { setBatchSortBy('mule_account_count'); setBatchPage(0) }}
                      >
                        Mule Accounts
                      </button>
                      <span className="profiler-count-label">
                        Showing {batchPage * BATCH_PAGE_SIZE + 1}–{Math.min((batchPage + 1) * BATCH_PAGE_SIZE, batchCases.length)} of {batchCases.length} cases
                      </span>
                    </div>
                  </div>
                )}

                {/* Cases table */}
                {batchCases.length > 0 && (
                  <div className="ksp-card">
                    <div className="profiler-table-wrap">
                      <table className="profiler-table">
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>Ack No</th>
                            <th>Amount</th>
                            <th>Disputed</th>
                            <th>Held</th>
                            <th>Recovery</th>
                            <th>Accounts</th>
                            <th>Layers</th>
                            <th>Banks</th>
                            <th>Mules</th>
                            <th>Priority</th>
                            <th>Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {getSortedBatchCases().slice(batchPage * BATCH_PAGE_SIZE, (batchPage + 1) * BATCH_PAGE_SIZE).map((c, idx) => (
                            <tr key={c.ack_no} className={`profiler-row profiler-row-${c.auto_priority.toLowerCase()}`}>
                              <td className="profiler-cell-idx">{batchPage * BATCH_PAGE_SIZE + idx + 1}</td>
                              <td className="profiler-cell-account">{c.ack_no}</td>
                              <td className="profiler-cell-amount">{formatCurrency(c.total_amount)}</td>
                              <td className="profiler-cell-amount">{formatCurrency(c.disputed_amount)}</td>
                              <td className="profiler-cell-amount">{formatCurrency(c.held_amount)}</td>
                              <td>
                                <span className={
                                  c.recovery_pct >= 50 ? 'triage-batch-recovery-good' :
                                  c.recovery_pct >= 20 ? 'triage-batch-recovery-partial' :
                                  'triage-batch-recovery-low'
                                }>
                                  {c.recovery_pct.toFixed(1)}%
                                </span>
                              </td>
                              <td>{c.unique_accounts}</td>
                              <td>L0-L{c.max_layer}</td>
                              <td>{c.unique_banks}</td>
                              <td className="profiler-cell-cases">{c.mule_account_count}</td>
                              <td>
                                <span className={`profiler-risk-badge profiler-risk-${c.auto_priority.toLowerCase()}`}>
                                  {c.auto_priority}
                                </span>
                              </td>
                              <td>
                                <button
                                  className="profiler-profile-btn"
                                  onClick={() => { setInvAckNo(c.ack_no); setPage('investigation') }}
                                >
                                  Investigate
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Pagination */}
                    {batchCases.length > BATCH_PAGE_SIZE && (
                      <div className="profiler-pagination">
                        <button
                          className="profiler-page-btn"
                          onClick={() => setBatchPage(p => p - 1)}
                          disabled={batchPage === 0}
                        >
                          ← Back
                        </button>
                        <span className="profiler-page-info">
                          Page {batchPage + 1} of {Math.ceil(batchCases.length / BATCH_PAGE_SIZE)}
                        </span>
                        <button
                          className="profiler-page-btn"
                          onClick={() => setBatchPage(p => p + 1)}
                          disabled={(batchPage + 1) * BATCH_PAGE_SIZE >= batchCases.length}
                        >
                          Next →
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Empty state */}
                {!batchLoading && !batchError && batchCases.length === 0 && batchLoaded && (
                  <div className="empty-state">No cases found in the database.</div>
                )}
              </>
            )}
          </>
        )}

        {/* ============ MULTI-SOURCE INTELLIGENCE PAGE ============ */}
        {page === 'intelligence' && (
          <>
            <div className="ksp-banner">
              <h1 className="ksp-title">Multi-Source Intelligence Agent</h1>
              <p className="ksp-subtitle">
                Ask questions in natural language. The AI agent queries MSSQL and Neo4j databases, then synthesizes an intelligence report.
              </p>
            </div>

            {/* Input row */}
            <div className="ksp-card" style={{ marginBottom: 20 }}>
              <div className="intel-input-row">
                <input
                  className="intel-input"
                  type="text"
                  placeholder="Ask a question about the fraud data..."
                  value={intelQuestion}
                  onChange={e => setIntelQuestion(e.target.value)}
                  onKeyDown={handleIntelKeyDown}
                  disabled={intelLoading}
                />
                <button
                  className="btn-navy intel-send-btn"
                  onClick={() => handleIntelQuery()}
                  disabled={intelLoading || !intelQuestion.trim()}
                >
                  {intelLoading ? 'Querying...' : 'Send'}
                </button>
              </div>
            </div>

            {/* Suggested questions — always visible except during loading */}
            {!intelLoading && (
              <div className="intel-suggestions">
                <span className="intel-suggestions-label">Suggested questions:</span>
                {INTEL_SUGGESTED_QUESTIONS.map(q => (
                  <button
                    key={q}
                    className="intel-chip"
                    onClick={() => { setIntelQuestion(q); handleIntelQuery(q) }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}

            {/* Status */}
            {intelStatus && (
              <div className="inv-status">
                <span className="inv-status-dot" />
                {intelStatus}
              </div>
            )}

            {/* Error */}
            {intelError && <div className="error-box">{intelError}</div>}

            {/* Collapsible queries section */}
            {intelQueries && (
              <div className="intel-queries-section">
                <button
                  className="intel-queries-toggle"
                  onClick={() => setIntelShowQueries(prev => !prev)}
                >
                  {intelShowQueries ? '\u25BC' : '\u25B6'} View Generated Queries
                </button>
                {intelShowQueries && (
                  <div className="intel-queries-content">
                    {intelQueries.explanation && (
                      <p className="intel-queries-explanation">{intelQueries.explanation}</p>
                    )}
                    {intelQueries.sql && (
                      <div className="intel-query-block">
                        <div className="intel-query-label">SQL Query</div>
                        <pre className="intel-query-code">{intelQueries.sql}</pre>
                      </div>
                    )}
                    {intelQueries.cypher && (
                      <div className="intel-query-block">
                        <div className="intel-query-label">Cypher Query</div>
                        <pre className="intel-query-code">{intelQueries.cypher}</pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Streaming report */}
            {intelReport && (
              <div className="ksp-card inv-report-card">
                <div className="inv-report-top-bar intel-report-top-bar">
                  <div className="inv-report-ack">
                    <span className="inv-report-ack-label">Intelligence Query</span>
                    <span className="inv-report-ack-value" style={{ fontSize: 14, fontFamily: 'inherit' }}>
                      {intelQuestion || 'Analysis'}
                    </span>
                  </div>
                  <div className="inv-report-header-right">
                    <h3 className="inv-report-title">Intelligence Report</h3>
                    {!intelLoading && (
                      <span className="inv-report-badge">
                        <span className="inv-report-badge-dot" />
                        Analysis Complete
                      </span>
                    )}
                    {intelLoading && (
                      <span className="inv-report-badge inv-report-badge-progress">
                        <span className="inv-status-dot" />
                        Generating...
                      </span>
                    )}
                  </div>
                </div>
                <div className="inv-report" ref={intelReportRef}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {intelReport}
                  </ReactMarkdown>
                </div>
              </div>
            )}

            {/* Previous queries history */}
            {intelHistory.length > 0 && !intelLoading && (
              <div className="intel-history-section">
                <h3 className="intel-history-title">Previous Queries</h3>
                {intelHistory.map((item, idx) => (
                  <button
                    key={idx}
                    className="intel-history-item"
                    onClick={() => {
                      setIntelQuestion(item.question)
                      setIntelReport(item.report)
                      setIntelQueries(item.queries)
                      setIntelError('')
                      setIntelShowQueries(false)
                    }}
                  >
                    <span className="intel-history-q">{item.question}</span>
                    <span className="intel-history-preview">
                      {item.report.slice(0, 120).replace(/[#*_]/g, '')}...
                    </span>
                  </button>
                ))}
              </div>
            )}

            {/* Empty state */}
            {!intelReport && !intelLoading && !intelError && intelHistory.length === 0 && (
              <div className="empty-state">
                Ask a question above or click a suggested question to generate an intelligence report.
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}

export default App
