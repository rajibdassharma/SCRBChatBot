import { useEffect, useMemo, useRef, useState } from 'react'
import kspLogo from './assets/ksp_logo.png'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const NEO4J_URI = import.meta.env.VITE_NEO4J_URI || 'bolt://localhost:7687'
const NEO4J_USERNAME = import.meta.env.VITE_NEO4J_USERNAME || 'neo4j'
const NEO4J_PASSWORD = import.meta.env.VITE_NEO4J_PASSWORD || 'sandy411'

const TABS = [
  'Database Intelligence',
  'Document Intelligence',
  'Graph Intelligence',
] as const

type ChatMessage = { role: 'user' | 'assistant'; content: string }

type DocRecord = {
  doc_id?: string
  doc_name?: string
  [key: string]: unknown
}

declare global {
  interface Window {
    NeoVis?: any
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options)
  let payload: any = null

  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    const detail = payload?.detail || payload?.error || response.statusText
    throw new Error(detail)
  }

  return payload as T
}

async function loadNeovisScript(): Promise<void> {
  if (typeof window === 'undefined') return
  if (window.NeoVis) return

  await new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-neovis]')
    if (existing) {
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

export default function App() {
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>(TABS[0])
  const [isOnline, setIsOnline] = useState<boolean>(false)

  const [dbQuestion, setDbQuestion] = useState('')
  const [dbChat, setDbChat] = useState<ChatMessage[]>([])
  const [dbAnswer, setDbAnswer] = useState('')
  const [dbSql, setDbSql] = useState('')
  const [dbLoading, setDbLoading] = useState(false)
  const [dbError, setDbError] = useState('')

  const [docQuestion, setDocQuestion] = useState('')
  const [docChat, setDocChat] = useState<ChatMessage[]>([])
  const [docs, setDocs] = useState<DocRecord[]>([])
  const [docStatus, setDocStatus] = useState('')
  const [docLastAnswer, setDocLastAnswer] = useState('')
  const [docLastError, setDocLastError] = useState('')
  const [docFiles, setDocFiles] = useState<FileList | null>(null)
  const [docLoading, setDocLoading] = useState(false)
  const [confirmClearDocs, setConfirmClearDocs] = useState(false)

  const [crimeNo, setCrimeNo] = useState('')
  const [expandAccused, setExpandAccused] = useState(true)
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphStatus, setGraphStatus] = useState('')
  const [graphError, setGraphError] = useState('')
  const [graphQuestion, setGraphQuestion] = useState('')
  const [graphAnswer, setGraphAnswer] = useState('')
  const [graphAskError, setGraphAskError] = useState('')
  const [graphChat, setGraphChat] = useState<ChatMessage[]>([])
  const [graphCypher, setGraphCypher] = useState('')
  const [graphReady, setGraphReady] = useState(false)

  const graphRef = useRef<HTMLDivElement | null>(null)
  const graphVizRef = useRef<any>(null)

  useEffect(() => {
    let isMounted = true
    apiFetch<{ ok: boolean }>('/health')
      .then((data) => {
        if (isMounted) {
          setIsOnline(Boolean(data?.ok))
        }
      })
      .catch(() => {
        if (isMounted) {
          setIsOnline(false)
        }
      })

    loadNeovisScript()
      .then(() => {
        if (isMounted) setGraphReady(true)
      })
      .catch((error) => {
        if (isMounted) setGraphError(error instanceof Error ? error.message : 'Neovis failed to load.')
      })

    return () => {
      isMounted = false
    }
  }, [])

  useEffect(() => {
    if (!graphCypher || !graphReady || !graphRef.current) return

    if (!window.NeoVis) {
      setGraphError('Neovis is not available in the browser.')
      return
    }

    try {
      graphRef.current.innerHTML = ''

      const config = {
        containerId: graphRef.current.id,
        neo4j: {
          serverUrl: NEO4J_URI,
          serverUser: NEO4J_USERNAME,
          serverPassword: NEO4J_PASSWORD,
        },
        visConfig: {
          interaction: {
            hover: true,
            tooltipDelay: 50,
            hoverConnectedEdges: true,
          },
          nodes: {
            shape: 'dot',
            size: 16,
            font: {
              size: 9,
              face: 'arial',
              color: '#111',
            },
          },
          edges: {
            arrows: {
              to: { enabled: true, scaleFactor: 0.7 },
            },
            smooth: false,
            font: { size: 9 },
          },
          physics: {
            stabilization: true,
          },
        },
        labels: {
          Account: {
            label: 'name',
            group: 'level',
          },
        },
        relationships: {
          TRANSFERRED_TO: {
            label: 'amount',
            thickness: 'amount',
          },
        },
        groups: {
          '0': { color: '#ffd400' },
          '1': { color: '#43A047' },
          '2': { color: '#FB8C00' },
          '3': { color: '#E53935' },
          '4': { color: '#8E24AA' },
          '5': { color: '#6D4C41' },
        },
        initialCypher: graphCypher,
      }

      const NeoVisClass = window.NeoVis?.default || window.NeoVis
      const viz = new NeoVisClass(config)
      graphVizRef.current = viz
      viz.render()
    } catch (error) {
      setGraphError(error instanceof Error ? error.message : 'Failed to render graph.')
    }
  }, [graphCypher, graphReady])

  const handleDbAsk = async () => {
    const question = dbQuestion.trim()
    if (!question) {
      setDbError('Please type a question.')
      return
    }

    setDbLoading(true)
    setDbError('')

    try {
      const payload = {
        question,
        history: dbChat,
      }

      const data = await apiFetch<{
        ok?: boolean
        answer?: string
        sql?: string
        error?: string
      }>('/db/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (data?.ok === false) {
        throw new Error(data.error || 'Database query failed.')
      }

      const answer = data?.answer || ''
      setDbChat((prev) => [
        ...prev,
        { role: 'user', content: question },
        { role: 'assistant', content: answer },
      ])
      setDbAnswer(answer)
      setDbSql(data?.sql || '')
    } catch (error) {
      setDbError(error instanceof Error ? error.message : 'Database query failed.')
    } finally {
      setDbLoading(false)
    }
  }

  const handleDocIndex = async () => {
    setDocStatus('')
    setDocLastError('')
    setDocLastAnswer('')

    if (!docFiles || docFiles.length === 0) {
      setDocLastError('Please choose one or more files to index.')
      return
    }

    setDocLoading(true)

    let indexedCount = 0
    let lastError = ''

    for (const file of Array.from(docFiles)) {
      const formData = new FormData()
      formData.append('file', file)

      try {
        const data = await apiFetch<{
          ok?: boolean
          error?: string
          [key: string]: unknown
        }>('/docs/upload', {
          method: 'POST',
          body: formData,
        })

        if (data?.ok === false) {
          lastError = `${file.name}: ${data.error || 'Indexing failed.'}`
          continue
        }

        indexedCount += 1
        setDocs((prev) => [...prev, data])
      } catch (error) {
        lastError = `${file.name}: ${error instanceof Error ? error.message : 'Indexing failed.'}`
      }
    }

    if (indexedCount > 0) {
      setDocStatus(`OK Indexed ${indexedCount} document(s). Ready for Q&A.`)
    }

    if (indexedCount === 0 && !lastError) {
      lastError = 'Indexing failed.'
    }

    if (lastError) {
      setDocLastError(lastError)
    }

    setDocLoading(false)
  }

  const handleDocAsk = async () => {
    setDocStatus('')
    setDocLastError('')
    setDocLastAnswer('')

    const question = docQuestion.trim()
    if (!docs.length) {
      setDocLastError('Please index at least one document first.')
      return
    }

    if (!question) {
      setDocLastError('Please type a question.')
      return
    }

    setDocLoading(true)

    try {
      const activeDocId = docs[docs.length - 1]?.doc_id
      const payload = {
        doc_id: activeDocId ?? null,
        question,
        history: docChat,
      }

      const data = await apiFetch<{
        ok?: boolean
        answer?: string
        error?: string
      }>('/docs/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (data?.ok === false) {
        throw new Error(data.error || 'Document query failed.')
      }

      const answer = (data?.answer || '').trim()

      setDocChat((prev) => [
        ...prev,
        { role: 'user', content: question },
        { role: 'assistant', content: answer },
      ])

      if (answer.toLowerCase().startsWith('not found')) {
        setDocLastError(answer)
      } else {
        setDocLastAnswer(answer)
        setDocStatus('OK Answer generated.')
      }
    } catch (error) {
      setDocLastError(error instanceof Error ? error.message : 'Document query failed.')
    } finally {
      setDocLoading(false)
    }
  }

  const handleDocClear = async () => {
    if (!confirmClearDocs) {
      setDocLastError('Please confirm before clearing.')
      return
    }

    setDocLoading(true)
    setDocLastError('')

    try {
      const data = await apiFetch<{ ok?: boolean; error?: string }>('/docs/clear', {
        method: 'POST',
      })

      if (data?.ok === false) {
        throw new Error(data.error || 'Failed to clear documents.')
      }

      setDocs([])
      setDocChat([])
      setDocLastAnswer('')
      setDocStatus('OK Documents and vector DB cleared.')
      setConfirmClearDocs(false)
    } catch (error) {
      setDocLastError(error instanceof Error ? error.message : 'Failed to clear documents.')
    } finally {
      setDocLoading(false)
    }
  }

  const fetchGraphStatus = async (crime: string) => {
    try {
      const data = await apiFetch<{ ok?: boolean; records?: unknown[]; error?: string }>(
        `/graph/crime/${encodeURIComponent(crime)}`
      )

      if (data?.ok === false) {
        throw new Error(data.error || 'Failed to load graph data.')
      }

      const recordCount = Array.isArray(data?.records) ? data.records.length : 0
      return { recordCount }
    } catch (error) {
      throw new Error(error instanceof Error ? error.message : 'Failed to load graph data.')
    }
  }

  const buildGraphCypher = (crime: string, mode: 'flow' | 'accounts') => {
    if (mode === 'accounts') {
      return `
        MATCH (a:Account)
        WHERE a.crime_no = '${crime}'
        RETURN a
      `
    }

    if (expandAccused) {
      return `
        MATCH (v0:Account)-[r0:TRANSFERRED_TO]->(a0:Account)
        WHERE r0.crime_no = '${crime}' AND a0.level > 0
        WITH collect(DISTINCT a0) AS accused
        UNWIND accused AS acc
        MATCH (v:Account)-[r:TRANSFERRED_TO]->(acc)
        WHERE v.level = 0
        RETURN v AS p, r AS r, acc AS c
        UNION
        MATCH (v0:Account)-[r0:TRANSFERRED_TO]->(a0:Account)
        WHERE r0.crime_no = '${crime}' AND a0.level > 0
        WITH collect(DISTINCT a0) AS accused
        UNWIND accused AS acc
        MATCH (acc)-[r:TRANSFERRED_TO]->(x:Account)
        RETURN acc AS p, r AS r, x AS c
        LIMIT 500
      `
    }

    return `
      MATCH (p:Account)-[r:TRANSFERRED_TO]->(c:Account)
      WHERE r.crime_no = '${crime}'
      RETURN p,r,c
    `
  }

  const handleGraphRender = async (mode: 'flow' | 'accounts') => {
    const crime = crimeNo.trim()
    if (!crime) {
      setGraphError('Crime Number is required.')
      return
    }

    setGraphLoading(true)
    setGraphError('')
    setGraphStatus('')

    try {
      const { recordCount } = await fetchGraphStatus(crime)
      const modeLabel = mode === 'accounts' ? 'Accounts only view' : 'Money flow view'
      setGraphStatus(`${modeLabel}. Loaded ${recordCount} transfer records.`)
      setGraphCypher(buildGraphCypher(crime, mode))
    } catch (error) {
      setGraphError(error instanceof Error ? error.message : 'Failed to load graph data.')
    } finally {
      setGraphLoading(false)
    }
  }

  const handleGraphAsk = async () => {
    const question = graphQuestion.trim()
    if (!question) {
      setGraphAskError('Please type a question.')
      return
    }

    setGraphAskError('')
    setGraphAnswer('')

    try {
      const payload = {
        question,
        history: graphChat,
      }

      const data = await apiFetch<{
        ok?: boolean
        answer?: string
        error?: string
      }>('/graph/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (data?.ok === false) {
        throw new Error(data.error || 'Graph Q&A failed.')
      }

      const answer = data?.answer || ''
      setGraphAnswer(answer)
      setGraphChat((prev) => [
        ...prev,
        { role: 'user', content: question },
        { role: 'assistant', content: answer },
      ])
    } catch (error) {
      setGraphAskError(error instanceof Error ? error.message : 'Graph Q&A failed.')
    }
  }

  const tabContent = useMemo(() => {
    if (activeTab === 'Database Intelligence') {
      return (
        <section className="ksp-card">
          <div className="main-title">Database Intelligence</div>
          <div className="main-help">
            Ask questions in natural language. The system generates safe SQL and
            returns answers.
          </div>
          <div className="two-col">
            <div>
              <span className="ksp-chip">Ask</span>
              <textarea
                className="ksp-textarea"
                value={dbQuestion}
                onChange={(event) => setDbQuestion(event.target.value)}
                placeholder="Ask in natural language"
              />
              <div className="normal-btn">
                <button
                  type="button"
                  className="btn-navy"
                  onClick={handleDbAsk}
                  disabled={dbLoading}
                >
                  {dbLoading ? 'Querying...' : 'Query Database'}
                </button>
              </div>
              {dbError && <div className="status error">{dbError}</div>}
            </div>
            <div>
              <span className="ksp-chip">Results</span>
              <div className="ksp-result">
                {dbAnswer ? (
                  <>
                    <p className="result-title">Answer:</p>
                    <p>{dbAnswer}</p>
                  </>
                ) : (
                  <p>Results will appear here after you query the database.</p>
                )}

                {dbSql && (
                  <details className="sql-panel">
                    <summary>Generated SQL</summary>
                    <pre>{dbSql}</pre>
                  </details>
                )}
              </div>
            </div>
          </div>
          <details className="history">
            <summary>Conversation History</summary>
            <div className="history-list">
              {dbChat.map((msg, idx) => (
                <div
                  key={`db-${idx}`}
                  className={msg.role === 'user' ? 'chat-user' : 'chat-ai'}
                >
                  {msg.content}
                </div>
              ))}
            </div>
          </details>
        </section>
      )
    }

    if (activeTab === 'Document Intelligence') {
      return (
        <section className="ksp-card">
          <div className="main-title">Document Intelligence</div>
          <div className="main-help">
            Upload PDF / Word / Excel / CSV files, index them into the vector
            database, then ask questions across all uploaded documents.
          </div>
          <div className="two-col">
            <div>
              <span className="ksp-chip">Upload &amp; Index</span>
              <input
                className="ksp-file"
                type="file"
                multiple
                onChange={(event) => setDocFiles(event.target.files)}
              />
              <div className="normal-btn">
                <button
                  type="button"
                  className="btn-navy"
                  onClick={handleDocIndex}
                  disabled={docLoading}
                >
                  {docLoading ? 'Indexing...' : 'Index Documents'}
                </button>
              </div>
              <span className="ksp-chip ksp-chip-spaced">Ask</span>
              <textarea
                className="ksp-textarea"
                value={docQuestion}
                onChange={(event) => setDocQuestion(event.target.value)}
                placeholder="Ask question on uploaded documents"
              />
              <div className="normal-btn">
                <button
                  type="button"
                  className="btn-navy"
                  onClick={handleDocAsk}
                  disabled={docLoading}
                >
                  {docLoading ? 'Searching...' : 'Ask Documents'}
                </button>
              </div>
            </div>
            <div>
              <span className="ksp-chip">Results</span>
              <div className="ksp-result">
                {docStatus && <div className="status success">{docStatus}</div>}
                {docLastError && <div className="status warning">{docLastError}</div>}

                {docs.length ? (
                  <>
                    <p className="result-title">Indexed Documents:</p>
                    <ul className="doc-list">
                      {docs.slice(-10).map((doc, idx) => (
                        <li key={`doc-${idx}`}>{doc.doc_name || 'Unknown'}</li>
                      ))}
                    </ul>
                    {docs.length > 10 && (
                      <div className="doc-more">+ {docs.length - 10} more</div>
                    )}
                  </>
                ) : (
                  <p>No documents indexed yet.</p>
                )}

                <hr />

                {docLastAnswer ? (
                  <>
                    <p className="result-title">Answer:</p>
                    <p>{docLastAnswer}</p>
                  </>
                ) : (
                  <p>Answers will appear here after you ask a question.</p>
                )}
              </div>
            </div>
          </div>
          <details className="history">
            <summary>Conversation History</summary>
            <div className="history-list">
              {docChat.map((msg, idx) => (
                <div
                  key={`doc-${idx}`}
                  className={msg.role === 'user' ? 'chat-user' : 'chat-ai'}
                >
                  {msg.content}
                </div>
              ))}
            </div>
          </details>
        </section>
      )
    }

    return (
      <section className="ksp-card">
        <div className="main-title">Graph Intelligence</div>
        <div className="main-help">
          Visual investigation of money flow using Neo4j Graph.
        </div>
        <label className="ksp-label" htmlFor="crimeNo">
          Crime Number
        </label>
        <input
          id="crimeNo"
          className="ksp-input"
          placeholder="Enter Crime_No exactly as in MSSQL"
          value={crimeNo}
          onChange={(event) => setCrimeNo(event.target.value)}
        />
        <label className="ksp-check">
          <input
            type="checkbox"
            checked={expandAccused}
            onChange={(event) => setExpandAccused(event.target.checked)}
          />
          <span>Expand accused across crimes</span>
        </label>
        <div className="btn-row">
          <button
            type="button"
            className="btn-navy"
            onClick={() => handleGraphRender('flow')}
            disabled={graphLoading}
          >
            {graphLoading ? 'Loading...' : 'Show Money Flow'}
          </button>
          <button
            type="button"
            className="btn-navy"
            onClick={() => handleGraphRender('accounts')}
            disabled={graphLoading}
          >
            {graphLoading ? 'Loading...' : 'Show Accounts Only'}
          </button>
        </div>
        <div className="divider" />
        <div className="graph-panel">
          <div className="graph-legend">
            <span className="legend-title">Layer Color Index:</span>
            <span className="legend-item legend-l0">Victim (L0)</span>
            <span className="legend-item legend-l1">L1</span>
            <span className="legend-item legend-l2">L2</span>
            <span className="legend-item legend-l3">L3</span>
            <span className="legend-item legend-l4">L4</span>
            <span className="legend-item legend-l5">L5+</span>
          </div>
          {graphError && <div className="status warning">{graphError}</div>}
          {graphStatus && !graphError && <div className="graph-status">{graphStatus}</div>}
          <div className="graph-canvas" id="kspGraph" ref={graphRef}>
            {!graphCypher && !graphError && (
              <div className="graph-placeholder">Graph will render here after query.</div>
            )}
          </div>
        </div>
        <div className="gqa">
          <div className="gqa-title">Graph Q&amp;A (Natural Language)</div>
          <textarea
            className="ksp-textarea"
            value={graphQuestion}
            onChange={(event) => setGraphQuestion(event.target.value)}
            placeholder="e.g., Who are the top receivers for the last generated graph?"
          />
          <button type="button" className="btn-navy-compact" onClick={handleGraphAsk}>
            Ask Graph (AI -&gt; Answer)
          </button>
          {graphAskError && <div className="status warning">{graphAskError}</div>}
          {graphAnswer && <div className="gqa-answer">{graphAnswer}</div>}
          {!graphAnswer && !graphAskError && (
            <div className="gqa-answer">Answer will appear here.</div>
          )}
        </div>
      </section>
    )
  }, [
    activeTab,
    dbAnswer,
    dbChat,
    dbError,
    dbLoading,
    dbQuestion,
    dbSql,
    docChat,
    docFiles,
    docLastAnswer,
    docLastError,
    docLoading,
    docQuestion,
    docStatus,
    docs,
    expandAccused,
    graphAnswer,
    graphAskError,
    graphError,
    graphLoading,
    graphQuestion,
    graphStatus,
    graphCypher,
    crimeNo,
  ])

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <img src={kspLogo} alt="KSP" />
        </div>
        <button type="button" className="btn-yellow" onClick={() => setDbChat([])}>
          Clear Database Chat
        </button>
        <button type="button" className="btn-yellow" onClick={() => setDocChat([])}>
          Clear Document Chat
        </button>
        <div className="ksp-danger-divider" />
        <label className="ksp-check">
          <input
            type="checkbox"
            checked={confirmClearDocs}
            onChange={(event) => setConfirmClearDocs(event.target.checked)}
          />
          <span>Confirm: clear uploaded docs</span>
        </label>
        <button type="button" className="btn-yellow" onClick={handleDocClear}>
          Clear Uploaded Docs
        </button>
      </aside>

      <main className="main">
        <header className="ksp-banner">
          <div>
            <h1 className="ksp-title">Karnataka State Police - AI Assistant</h1>
            <p className="ksp-subtitle">
              Cyber Fraud Database (MSSQL) + Case Documents (PDF/DOCX) - Local
              AI (Ollama)
            </p>
            <div className="ksp-pills">
              <span className="ksp-pill">
                System: <b>{isOnline ? 'ONLINE' : 'OFFLINE'}</b>
              </span>
              <span className="ksp-pill">DB: MSSQL</span>
              <span className="ksp-pill">Docs: Vector DB</span>
            </div>
          </div>
        </header>

        <nav className="tabs">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              className={`tab ${activeTab === tab ? 'active' : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </nav>

        <div className="main-panel">{tabContent}</div>
      </main>
    </div>
  )
}
