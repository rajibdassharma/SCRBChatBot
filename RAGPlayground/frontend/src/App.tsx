import { useState, useEffect, useRef } from 'react'
import './App.css'

const API = 'http://localhost:8006'

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  stats?: string
}

interface DocInfo {
  doc_id: string
  doc_name: string
  chunks: number
  type?: string
  case_name?: string
  fields?: number
  details?: {
    subtype?: string
    accused_count?: number
    pending_count?: number
    brief_desc_chars?: number
    fields?: number
    statement_chars?: number
    accused_name?: string
    parser?: string
  }
}

interface PipelineInfo {
  name: string
  description: string
}

interface ScanTestPreview {
  ok: boolean
  filename?: string
  elapsed_seconds?: number
  full_text_chars?: number
  full_text_preview?: string
  header_fields?: { serial_no: string; field_name: string; value: string }[]
  accused_persons?: { serial_no?: string; person_name: string; person_type: string; details?: string }[]
  pending_persons?: { person_name: string; person_type: string; details?: string }[]
  accused_details_text?: string
  absconder_details_text?: string
  suspect_details_text?: string
  brief_description_preview?: string
  brief_description_chars?: number
  summary?: Record<string, number>
  error?: string
}

function App() {
  // Mode: main pipelines vs scan test
  const [mode, setMode] = useState<'pipelines' | 'scantest'>('pipelines')

  // Config
  const [pipelines, setPipelines] = useState<PipelineInfo[]>([])
  const [selectedPipeline, setSelectedPipeline] = useState('BasicRAG')
  const [models, setModels] = useState<string[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [ollamaOk, setOllamaOk] = useState(false)

  // Upload & index
  const [docFiles, setDocFiles] = useState<File[]>([])
  const [indexing, setIndexing] = useState(false)
  const [indexStatus, setIndexStatus] = useState('')
  const [docs, setDocs] = useState<DocInfo[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const [docType, setDocType] = useState<'IR' | 'SMAC'>('SMAC')
  const [useLlmParser, setUseLlmParser] = useState(false)

  // Cases
  const [cases, setCases] = useState<string[]>([])
  const [selectedCase, setSelectedCase] = useState('')

  // Q&A
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastError, setLastError] = useState('')
  const chatEndRef = useRef<HTMLDivElement>(null)

  // Scan Test state
  const scanFileRef = useRef<HTMLInputElement>(null)
  const [scanFile, setScanFile] = useState<File | null>(null)
  const [scanLoading, setScanLoading] = useState(false)
  const [scanPreview, setScanPreview] = useState<ScanTestPreview | null>(null)
  const [scanDocs, setScanDocs] = useState<{ doc_id: string; doc_name: string; full_text_chars: number }[]>([])
  const [scanChromaChunks, setScanChromaChunks] = useState(0)
  const [scanChat, setScanChat] = useState<ChatMsg[]>([])
  const [scanQuestion, setScanQuestion] = useState('')
  const [scanQueryLoading, setScanQueryLoading] = useState(false)
  const [scanStatus, setScanStatus] = useState('')
  const scanChatEndRef = useRef<HTMLDivElement>(null)

  // Init
  useEffect(() => {
    fetchPipelines()
    fetchModels()
    checkHealth()
  }, [])

  useEffect(() => {
    fetchDocs()
    fetchCases()
  }, [selectedPipeline])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])

  async function checkHealth() {
    try {
      const r = await fetch(`${API}/health`)
      const d = await r.json()
      setOllamaOk(d.ollama_connected)
    } catch { setOllamaOk(false) }
  }

  async function fetchPipelines() {
    try {
      const r = await fetch(`${API}/api/pipelines`)
      const d = await r.json()
      if (d.ok) setPipelines(d.pipelines)
    } catch {}
  }

  async function fetchModels() {
    try {
      const r = await fetch(`${API}/api/models`)
      const d = await r.json()
      if (d.ok) {
        setModels(d.models)
        if (d.default) setSelectedModel(d.default)
        else if (d.models.length > 0) setSelectedModel(d.models[0])
      }
    } catch {}
  }

  async function fetchDocs() {
    try {
      const r = await fetch(`${API}/api/docs?pipeline=${selectedPipeline}`)
      const d = await r.json()
      if (d.ok) setDocs(d.docs)
    } catch {}
  }

  async function fetchCases() {
    try {
      const r = await fetch(`${API}/api/cases`)
      const d = await r.json()
      if (d.ok) setCases(d.cases || [])
    } catch {}
  }

  // ── Index ──

  async function handleIndex() {
    if (docFiles.length === 0) return
    setIndexing(true)
    setIndexStatus('')
    setLastError('')

    let indexed = 0
    let failed = 0
    for (const f of docFiles) {
      setIndexStatus(`Indexing ${indexed + failed + 1}/${docFiles.length}: ${f.name}...`)
      const fd = new FormData()
      fd.append('file', f)
      fd.append('pipeline', selectedPipeline)
      fd.append('model', selectedModel)
      fd.append('doc_type', docType)
      fd.append('use_llm_parser', String(useLlmParser))
      // Send relative path so backend can extract case name from folder structure
      const relativePath = (f as any).webkitRelativePath || f.name
      fd.append('relative_path', relativePath)

      try {
        const r = await fetch(`${API}/api/index`, { method: 'POST', body: fd })
        const d = await r.json()
        if (d.ok) {
          indexed++
          // Show richer status for chargesheet vs IR
          const det = d.details || {}
          if (det.subtype === 'chargesheet') {
            const persons = (det.accused_count || 0) + (det.pending_count || 0)
            setIndexStatus(`Indexed ${f.name} [Chargesheet] — ${persons} persons, ${d.chunks} chunks (${d.elapsed_seconds}s)`)
          } else if (det.type === 'IR') {
            const name = det.accused_name ? ` — ${det.accused_name}` : ''
            setIndexStatus(`Indexed ${f.name} [IR${name}] — ${d.fields} fields, ${d.chunks} chunks (${d.elapsed_seconds}s)`)
          } else {
            setIndexStatus(`Indexed ${f.name} — ${d.chunks} chunks (${d.elapsed_seconds}s)`)
          }
        } else {
          failed++
          setLastError(d.error || 'Index failed')
        }
      } catch (e) {
        failed++
        setLastError(String(e))
      }
    }

    setIndexStatus(`Done: ${indexed} indexed, ${failed} failed`)
    setDocFiles([])
    setIndexing(false)
    fetchDocs()
    fetchCases()
  }

  // ── Query ──

  async function handleQuery() {
    if (!question.trim()) return
    const q = question.trim()
    setChatMessages(prev => [...prev, { role: 'user', content: q }])
    setQuestion('')
    setLoading(true)
    setLastError('')

    try {
      const r = await fetch(`${API}/api/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q,
          pipeline: selectedPipeline,
          model: selectedModel,
          case_name: selectedCase || null,
        }),
      })
      const d = await r.json()
      const stats = `${d.pipeline} | ${d.search_method || ''} | ${d.elapsed_seconds}s`
      setChatMessages(prev => [...prev, { role: 'assistant', content: d.answer || d.error || 'No answer', stats }])
    } catch (e) {
      setChatMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e}` }])
    } finally {
      setLoading(false)
    }
  }

  // ── Clear ──

  async function handleClear() {
    try {
      await fetch(`${API}/api/clear?pipeline=${selectedPipeline}`, { method: 'POST' })
      setChatMessages([])
      setDocs([])
      setIndexStatus('')
      setLastError('')
    } catch {}
  }

  // ── Scan Test functions ──

  async function fetchScanDocs() {
    try {
      const r = await fetch(`${API}/api/scantest/docs`)
      const d = await r.json()
      if (d.ok) { setScanDocs(d.docs || []); setScanChromaChunks(d.chroma_chunks || 0) }
    } catch {}
  }

  async function handleScanPreview() {
    if (!scanFile) return
    setScanLoading(true)
    setScanPreview(null)
    setScanStatus('Parsing...')
    const fd = new FormData()
    fd.append('file', scanFile)
    try {
      const r = await fetch(`${API}/api/scantest/parse-preview`, { method: 'POST', body: fd })
      const d = await r.json()
      setScanPreview(d)
      setScanStatus(d.ok ? `Parsed in ${d.elapsed_seconds}s` : d.error || 'Parse failed')
    } catch (e) {
      setScanStatus(`Error: ${e}`)
    } finally {
      setScanLoading(false)
    }
  }

  async function handleScanIndex() {
    if (!scanFile) return
    setScanLoading(true)
    setScanStatus('Indexing...')
    const fd = new FormData()
    fd.append('file', scanFile)
    try {
      const r = await fetch(`${API}/api/scantest/index`, { method: 'POST', body: fd })
      const d = await r.json()
      if (d.ok) {
        setScanStatus(`Indexed: ${d.chunks} chunks, ${d.summary?.header_fields || 0} fields, ${d.summary?.accused_count || 0} accused, ${d.summary?.pending_count || 0} pending (${d.elapsed_seconds}s)`)
        fetchScanDocs()
      } else {
        setScanStatus(d.error || 'Index failed')
      }
    } catch (e) {
      setScanStatus(`Error: ${e}`)
    } finally {
      setScanLoading(false)
    }
  }

  async function handleScanQuery() {
    if (!scanQuestion.trim()) return
    const q = scanQuestion.trim()
    setScanChat(prev => [...prev, { role: 'user', content: q }])
    setScanQuestion('')
    setScanQueryLoading(true)
    try {
      const r = await fetch(`${API}/api/scantest/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, model: selectedModel }),
      })
      const d = await r.json()
      const stats = `scantest | ${d.search_method || 'vector'} | ${d.elapsed_seconds}s`
      setScanChat(prev => [...prev, { role: 'assistant', content: d.answer || d.error || 'No answer', stats }])
    } catch (e) {
      setScanChat(prev => [...prev, { role: 'assistant', content: `Error: ${e}` }])
    } finally {
      setScanQueryLoading(false)
    }
  }

  async function handleScanClear() {
    try {
      await fetch(`${API}/api/scantest/clear`, { method: 'POST' })
      setScanDocs([])
      setScanChromaChunks(0)
      setScanChat([])
      setScanPreview(null)
      setScanStatus('Cleared')
    } catch {}
  }

  useEffect(() => {
    if (mode === 'scantest') fetchScanDocs()
  }, [mode])

  useEffect(() => {
    scanChatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [scanChat])

  // ── Render ──

  const pipelineDesc = pipelines.find(p => p.name === selectedPipeline)?.description || ''

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header style={{
        background: '#1e293b', borderBottom: '2px solid #059669', padding: '10px 20px',
        display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap',
      }}>
        <h1 style={{ margin: 0, fontSize: '1.1rem', color: '#10b981', fontWeight: 700 }}>RAG Playground</h1>

        {/* Mode toggle */}
        <div style={{ display: 'flex', gap: '2px', background: '#0a1628', borderRadius: '8px', padding: '2px' }}>
          <button onClick={() => setMode('pipelines')} style={{
            background: mode === 'pipelines' ? '#059669' : 'transparent', color: mode === 'pipelines' ? '#fff' : '#94a3b8',
            border: 'none', borderRadius: '6px', padding: '4px 12px', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer',
          }}>Pipelines</button>
          <button onClick={() => setMode('scantest')} style={{
            background: mode === 'scantest' ? '#b45309' : 'transparent', color: mode === 'scantest' ? '#fff' : '#94a3b8',
            border: 'none', borderRadius: '6px', padding: '4px 12px', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer',
          }}>Scan Test</button>
        </div>

        {/* Pipeline controls — hidden in scantest mode */}
        {mode === 'pipelines' && <>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Pipeline:</span>
            <select
              value={selectedPipeline}
              onChange={(e) => { setSelectedPipeline(e.target.value); setChatMessages([]) }}
              style={{ background: '#0a1628', color: '#10b981', border: '1px solid #334155', borderRadius: '6px', padding: '5px 10px', fontSize: '0.8rem', fontWeight: 600 }}
            >
              {pipelines.map(p => (
                <option key={p.name} value={p.name}>{p.name}</option>
              ))}
            </select>
          </div>

          {cases.length > 0 && (selectedPipeline === 'StructuredRAG' || selectedPipeline === 'AgenticRAG') && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Case:</span>
              <select
                value={selectedCase}
                onChange={(e) => setSelectedCase(e.target.value)}
                style={{ background: '#0a1628', color: '#10b981', border: '1px solid #334155', borderRadius: '6px', padding: '5px 10px', fontSize: '0.8rem', fontWeight: 600, maxWidth: '250px' }}
              >
                <option value="">All Cases</option>
                {cases.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          )}

          <span style={{ fontSize: '0.7rem', color: '#64748b', fontStyle: 'italic' }}>{pipelineDesc}</span>
        </>}

        {mode === 'scantest' && (
          <span style={{ fontSize: '0.8rem', color: '#b45309', fontWeight: 600 }}>Chargesheet Scan Test — Parse, Index & Query scanned PDFs</span>
        )}

        {/* Model selector — always visible */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Model:</span>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            style={{ background: '#0a1628', color: '#e2e8f0', border: '1px solid #334155', borderRadius: '6px', padding: '5px 10px', fontSize: '0.8rem' }}
          >
            {models.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        {/* Status */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem' }}>
          <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: ollamaOk ? '#22c55e' : '#ef4444', display: 'inline-block' }} />
          <span style={{ color: '#94a3b8' }}>Ollama</span>
        </div>
      </header>

      {/* Main content */}
      {mode === 'pipelines' && <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '380px 1fr', overflow: 'hidden' }}>

        {/* Left panel: Upload & Docs */}
        <div style={{ background: '#111827', borderRight: '1px solid #1e293b', padding: '16px', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 90px)', overflow: 'hidden' }}>
          {/* Upload section */}
          <div style={{ marginBottom: '16px' }}>
            <h3 style={{ color: '#10b981', fontSize: '0.85rem', marginBottom: '10px', fontWeight: 700 }}>Upload & Index</h3>

            {/* Document Type + LLM Parser toggle (visible for StructuredRAG) */}
            <div style={{ display: 'flex', gap: '10px', marginBottom: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Doc Type:</span>
                <select
                  value={docType}
                  onChange={(e) => setDocType(e.target.value as 'IR' | 'SMAC')}
                  style={{ background: '#0a1628', color: '#10b981', border: '1px solid #334155', borderRadius: '6px', padding: '4px 8px', fontSize: '0.78rem', fontWeight: 600 }}
                >
                  <option value="SMAC">SMAC</option>
                  <option value="IR">IR</option>
                </select>
              </div>
              {selectedPipeline === 'StructuredRAG' && docType === 'IR' && (
                <label style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.75rem', color: '#94a3b8', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={useLlmParser}
                    onChange={(e) => setUseLlmParser(e.target.checked)}
                    style={{ accentColor: '#059669' }}
                  />
                  Use LLM Parser
                </label>
              )}
            </div>
            {selectedPipeline === 'StructuredRAG' && docType === 'IR' && (
              <div style={{ fontSize: '0.68rem', color: '#64748b', marginBottom: '8px', lineHeight: '1.4' }}>
                Files with "chargesheet" in the name are auto-detected and parsed separately (OCR for scanned PDFs, accused list extraction).
              </div>
            )}

            <div style={{ display: 'flex', gap: '6px', marginBottom: '8px', flexWrap: 'wrap' }}>
              <button
                onClick={() => fileInputRef.current?.click()}
                style={{ background: '#059669', color: '#fff', border: 'none', borderRadius: '8px', padding: '6px 14px', fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer' }}
              >
                Choose Files
              </button>
              <button
                onClick={() => folderInputRef.current?.click()}
                style={{ background: '#059669', color: '#fff', border: 'none', borderRadius: '8px', padding: '6px 14px', fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer' }}
              >
                Select Folder
              </button>
              <button
                onClick={handleIndex}
                disabled={indexing || docFiles.length === 0}
                style={{ background: '#047857', color: '#fff', border: 'none', borderRadius: '8px', padding: '6px 14px', fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer', opacity: indexing || docFiles.length === 0 ? 0.5 : 1 }}
              >
                {indexing ? 'Indexing...' : 'Index'}
              </button>
            </div>
            <input ref={fileInputRef} className="hidden-input" type="file" multiple accept=".pdf,.docx,.doc,.xlsx,.csv"
              onChange={(e) => setDocFiles(e.target.files ? Array.from(e.target.files) : [])} />
            <input ref={folderInputRef} className="hidden-input" type="file"
              {...{ webkitdirectory: '', directory: '' } as React.InputHTMLAttributes<HTMLInputElement>}
              onChange={(e) => {
                const fl = e.target.files
                if (!fl) return
                const supported = ['.pdf', '.docx', '.doc', '.xlsx', '.csv']
                const filtered = Array.from(fl).filter(f => supported.includes(f.name.slice(f.name.lastIndexOf('.')).toLowerCase()))
                setDocFiles(filtered)
              }} />
            {docFiles.length > 0 && (
              <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '4px' }}>
                {docFiles.length} file{docFiles.length > 1 ? 's' : ''} selected
              </div>
            )}
            {indexStatus && (
              <div style={{ fontSize: '0.75rem', color: '#10b981', marginBottom: '4px' }}>{indexStatus}</div>
            )}
            {lastError && (
              <div style={{ fontSize: '0.75rem', color: '#ef4444', marginBottom: '4px' }}>{lastError}</div>
            )}
          </div>

          {/* Indexed docs */}
          <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <h3 style={{ color: '#10b981', fontSize: '0.85rem', fontWeight: 700 }}>
                Indexed Documents ({docs.length})
              </h3>
              {docs.length > 0 && (
                <button
                  onClick={handleClear}
                  style={{ background: '#7f1d1d', color: '#fca5a5', border: 'none', borderRadius: '6px', padding: '4px 10px', fontSize: '0.7rem', cursor: 'pointer' }}
                >
                  Clear All
                </button>
              )}
            </div>
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {docs.length === 0 ? (
                <p style={{ color: '#475569', fontSize: '0.8rem' }}>No documents indexed yet</p>
              ) : (
                docs.map((d) => {
                  const isChargesheet = d.doc_name.toLowerCase().includes('chargesheet') || d.doc_name.toLowerCase().includes('charge_sheet')
                  return (
                    <div key={d.doc_id} style={{
                      background: '#1e293b', borderRadius: '8px', padding: '8px 12px', marginBottom: '6px',
                      fontSize: '0.78rem', border: `1px solid ${isChargesheet ? '#b45309' : '#334155'}`,
                    }}>
                      <div style={{ color: '#e2e8f0', fontWeight: 600, wordBreak: 'break-all', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {d.doc_name}
                        {isChargesheet && (
                          <span style={{ background: '#b45309', color: '#fff', fontSize: '0.6rem', padding: '1px 6px', borderRadius: '4px', fontWeight: 700, whiteSpace: 'nowrap' }}>
                            CHARGESHEET
                          </span>
                        )}
                      </div>
                      <div style={{ color: '#64748b', fontSize: '0.7rem', marginTop: '2px' }}>
                        {d.chunks} chunks
                        {d.case_name ? ` | Case: ${d.case_name}` : ''}
                        {d.type ? ` | ${d.type}` : ''}
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>

        {/* Right panel: Q&A */}
        <div style={{ display: 'flex', flexDirection: 'column', padding: '16px', overflow: 'hidden' }}>
          {/* Chat messages */}
          <div style={{ flex: 1, overflowY: 'auto', marginBottom: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {chatMessages.length === 0 && (
              <div style={{ textAlign: 'center', color: '#475569', marginTop: '40px', fontSize: '0.85rem' }}>
                Index documents and ask questions using <strong style={{ color: '#10b981' }}>{selectedPipeline}</strong>
              </div>
            )}
            {chatMessages.map((m, i) => (
              <div key={i}>
                <div
                  style={{
                    alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                    background: m.role === 'user' ? '#059669' : '#1e293b',
                    borderRadius: '12px',
                    padding: '10px 16px',
                    maxWidth: '85%',
                    fontSize: '0.85rem',
                    lineHeight: '1.7',
                    whiteSpace: 'pre-wrap',
                    border: m.role === 'assistant' ? '1px solid #334155' : 'none',
                    marginLeft: m.role === 'user' ? 'auto' : '0',
                  }}
                >
                  {m.content}
                </div>
                {m.stats && (
                  <div style={{
                    fontSize: '0.65rem', color: '#475569', marginTop: '2px',
                    marginLeft: m.role === 'user' ? 'auto' : '0',
                    textAlign: m.role === 'user' ? 'right' : 'left',
                  }}>
                    {m.stats}
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div style={{ color: '#10b981', fontSize: '0.85rem', padding: '10px 16px' }}>
                Searching & generating answer...
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div style={{ display: 'flex', gap: '8px' }}>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleQuery() } }}
              placeholder="Ask a question about the indexed documents... (Shift+Enter for new line)"
              style={{
                flex: 1, background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155',
                borderRadius: '10px', padding: '12px', fontSize: '0.85rem', resize: 'none',
                minHeight: '50px', maxHeight: '120px', fontFamily: 'inherit', lineHeight: '1.5',
              }}
            />
            <button
              onClick={handleQuery}
              disabled={loading || !question.trim()}
              style={{
                background: '#059669', color: '#fff', border: 'none', borderRadius: '10px',
                padding: '0 20px', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer',
                opacity: loading || !question.trim() ? 0.5 : 1,
              }}
            >
              Ask
            </button>
          </div>
        </div>
      </div>}

      {/* ═══ Scan Test Mode ═══ */}
      {mode === 'scantest' && (
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '400px 1fr', overflow: 'hidden' }}>

          {/* Left: Upload, Preview, Docs */}
          <div style={{ background: '#111827', borderRight: '1px solid #1e293b', padding: '16px', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 90px)', overflow: 'hidden' }}>
            {/* Upload */}
            <div style={{ marginBottom: '16px' }}>
              <h3 style={{ color: '#b45309', fontSize: '0.85rem', marginBottom: '10px', fontWeight: 700 }}>Upload Chargesheet</h3>
              <div style={{ display: 'flex', gap: '6px', marginBottom: '8px', flexWrap: 'wrap' }}>
                <button onClick={() => scanFileRef.current?.click()}
                  style={{ background: '#b45309', color: '#fff', border: 'none', borderRadius: '8px', padding: '6px 14px', fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer' }}>
                  Choose File
                </button>
                <button onClick={handleScanPreview} disabled={scanLoading || !scanFile}
                  style={{ background: '#92400e', color: '#fff', border: 'none', borderRadius: '8px', padding: '6px 14px', fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer', opacity: scanLoading || !scanFile ? 0.5 : 1 }}>
                  {scanLoading ? 'Processing...' : 'Parse Preview'}
                </button>
                <button onClick={handleScanIndex} disabled={scanLoading || !scanFile}
                  style={{ background: '#78350f', color: '#fff', border: 'none', borderRadius: '8px', padding: '6px 14px', fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer', opacity: scanLoading || !scanFile ? 0.5 : 1 }}>
                  Index
                </button>
              </div>
              <input ref={scanFileRef} style={{ display: 'none' }} type="file" accept=".pdf,.docx,.doc"
                onChange={(e) => { setScanFile(e.target.files?.[0] || null); setScanPreview(null) }} />
              {scanFile && <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '4px' }}>{scanFile.name}</div>}
              {scanStatus && <div style={{ fontSize: '0.75rem', color: '#b45309', marginBottom: '4px' }}>{scanStatus}</div>}
            </div>

            {/* Parse Preview Results */}
            {scanPreview && scanPreview.ok && (
              <div style={{ flex: 1, overflowY: 'auto', marginBottom: '12px' }}>
                <h3 style={{ color: '#b45309', fontSize: '0.85rem', marginBottom: '8px', fontWeight: 700 }}>Parse Results</h3>

                {/* Summary */}
                <div style={{ background: '#1e293b', borderRadius: '8px', padding: '8px 12px', marginBottom: '8px', fontSize: '0.75rem', border: '1px solid #b45309' }}>
                  <div style={{ color: '#fbbf24', fontWeight: 700, marginBottom: '4px' }}>Summary</div>
                  <div style={{ color: '#94a3b8' }}>Full text: {scanPreview.full_text_chars?.toLocaleString()} chars</div>
                  <div style={{ color: '#94a3b8' }}>Header fields: {scanPreview.summary?.header_fields || 0}</div>
                  <div style={{ color: '#94a3b8' }}>Accused: {scanPreview.summary?.accused_count || 0}</div>
                  <div style={{ color: '#94a3b8' }}>Pending persons: {scanPreview.summary?.pending_count || 0}</div>
                  <div style={{ color: '#94a3b8' }}>Brief description: {scanPreview.summary?.brief_desc_chars || 0} chars</div>
                </div>

                {/* Header Fields */}
                {(scanPreview.header_fields?.length || 0) > 0 && (
                  <div style={{ background: '#1e293b', borderRadius: '8px', padding: '8px 12px', marginBottom: '8px', fontSize: '0.72rem', border: '1px solid #334155' }}>
                    <div style={{ color: '#fbbf24', fontWeight: 700, marginBottom: '4px' }}>Header Fields</div>
                    {scanPreview.header_fields!.map((f, i) => (
                      <div key={i} style={{ color: '#e2e8f0', marginBottom: '2px' }}>
                        <span style={{ color: '#64748b' }}>[{f.serial_no}]</span> {f.field_name}: <span style={{ color: '#10b981' }}>{f.value}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Accused Persons */}
                {(scanPreview.accused_persons?.length || 0) > 0 && (
                  <div style={{ background: '#1e293b', borderRadius: '8px', padding: '8px 12px', marginBottom: '8px', fontSize: '0.72rem', border: '1px solid #334155' }}>
                    <div style={{ color: '#fbbf24', fontWeight: 700, marginBottom: '4px' }}>Accused Persons ({scanPreview.accused_persons!.length})</div>
                    {scanPreview.accused_persons!.map((p, i) => (
                      <div key={i} style={{ color: '#e2e8f0', marginBottom: '2px' }}>
                        {p.serial_no && <span style={{ color: '#64748b' }}>[{p.serial_no}] </span>}
                        {p.person_name} <span style={{ color: '#64748b' }}>({p.person_type})</span>
                        {p.details && <span style={{ color: '#94a3b8' }}> — {p.details}</span>}
                      </div>
                    ))}
                  </div>
                )}

                {/* Pending Persons */}
                {(scanPreview.pending_persons?.length || 0) > 0 && (
                  <div style={{ background: '#1e293b', borderRadius: '8px', padding: '8px 12px', marginBottom: '8px', fontSize: '0.72rem', border: '1px solid #334155' }}>
                    <div style={{ color: '#fbbf24', fontWeight: 700, marginBottom: '4px' }}>Pending Persons ({scanPreview.pending_persons!.length})</div>
                    {scanPreview.pending_persons!.map((p, i) => (
                      <div key={i} style={{ color: '#e2e8f0', marginBottom: '2px' }}>
                        {p.person_name} <span style={{ color: '#64748b' }}>({p.person_type})</span>
                        {p.details && <span style={{ color: '#94a3b8' }}> — {p.details}</span>}
                      </div>
                    ))}
                  </div>
                )}

                {/* Brief Description Preview */}
                {(scanPreview.brief_description_chars || 0) > 0 && (
                  <div style={{ background: '#1e293b', borderRadius: '8px', padding: '8px 12px', marginBottom: '8px', fontSize: '0.72rem', border: '1px solid #334155' }}>
                    <div style={{ color: '#fbbf24', fontWeight: 700, marginBottom: '4px' }}>Brief Description ({scanPreview.brief_description_chars} chars)</div>
                    <div style={{ color: '#94a3b8', whiteSpace: 'pre-wrap', maxHeight: '200px', overflow: 'auto' }}>{scanPreview.brief_description_preview}</div>
                  </div>
                )}

                {/* Full Text Preview */}
                <div style={{ background: '#1e293b', borderRadius: '8px', padding: '8px 12px', marginBottom: '8px', fontSize: '0.72rem', border: '1px solid #334155' }}>
                  <div style={{ color: '#fbbf24', fontWeight: 700, marginBottom: '4px' }}>Full Text Preview (first 3000 chars)</div>
                  <div style={{ color: '#94a3b8', whiteSpace: 'pre-wrap', maxHeight: '300px', overflow: 'auto', fontSize: '0.68rem' }}>{scanPreview.full_text_preview}</div>
                </div>
              </div>
            )}

            {/* Indexed Docs */}
            {!scanPreview && (
              <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <h3 style={{ color: '#b45309', fontSize: '0.85rem', fontWeight: 700 }}>
                    Indexed ({scanDocs.length} docs, {scanChromaChunks} chunks)
                  </h3>
                  {scanDocs.length > 0 && (
                    <button onClick={handleScanClear}
                      style={{ background: '#7f1d1d', color: '#fca5a5', border: 'none', borderRadius: '6px', padding: '4px 10px', fontSize: '0.7rem', cursor: 'pointer' }}>
                      Clear All
                    </button>
                  )}
                </div>
                <div style={{ flex: 1, overflowY: 'auto' }}>
                  {scanDocs.length === 0 ? (
                    <p style={{ color: '#475569', fontSize: '0.8rem' }}>No scantest documents indexed</p>
                  ) : (
                    scanDocs.map((d) => (
                      <div key={d.doc_id} style={{ background: '#1e293b', borderRadius: '8px', padding: '8px 12px', marginBottom: '6px', fontSize: '0.78rem', border: '1px solid #b45309' }}>
                        <div style={{ color: '#e2e8f0', fontWeight: 600, wordBreak: 'break-all' }}>{d.doc_name}</div>
                        <div style={{ color: '#64748b', fontSize: '0.7rem' }}>{d.full_text_chars?.toLocaleString()} chars</div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Right: Q&A */}
          <div style={{ display: 'flex', flexDirection: 'column', padding: '16px', overflow: 'hidden' }}>
            <div style={{ flex: 1, overflowY: 'auto', marginBottom: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {scanChat.length === 0 && (
                <div style={{ textAlign: 'center', color: '#475569', marginTop: '40px', fontSize: '0.85rem' }}>
                  Index a chargesheet and ask questions in <strong style={{ color: '#b45309' }}>Scan Test</strong> mode
                </div>
              )}
              {scanChat.map((m, i) => (
                <div key={i}>
                  <div style={{
                    alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                    background: m.role === 'user' ? '#b45309' : '#1e293b',
                    borderRadius: '12px', padding: '10px 16px', maxWidth: '85%',
                    fontSize: '0.85rem', lineHeight: '1.7', whiteSpace: 'pre-wrap',
                    border: m.role === 'assistant' ? '1px solid #334155' : 'none',
                    marginLeft: m.role === 'user' ? 'auto' : '0',
                  }}>
                    {m.content}
                  </div>
                  {m.stats && (
                    <div style={{ fontSize: '0.65rem', color: '#475569', marginTop: '2px',
                      marginLeft: m.role === 'user' ? 'auto' : '0', textAlign: m.role === 'user' ? 'right' : 'left' }}>
                      {m.stats}
                    </div>
                  )}
                </div>
              ))}
              {scanQueryLoading && (
                <div style={{ color: '#b45309', fontSize: '0.85rem', padding: '10px 16px' }}>Searching & generating answer...</div>
              )}
              <div ref={scanChatEndRef} />
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <textarea
                value={scanQuestion}
                onChange={(e) => setScanQuestion(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleScanQuery() } }}
                placeholder="Ask a question about the scanned chargesheet..."
                style={{
                  flex: 1, background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155',
                  borderRadius: '10px', padding: '12px', fontSize: '0.85rem', resize: 'none',
                  minHeight: '50px', maxHeight: '120px', fontFamily: 'inherit', lineHeight: '1.5',
                }}
              />
              <button onClick={handleScanQuery} disabled={scanQueryLoading || !scanQuestion.trim()}
                style={{
                  background: '#b45309', color: '#fff', border: 'none', borderRadius: '10px',
                  padding: '0 20px', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer',
                  opacity: scanQueryLoading || !scanQuestion.trim() ? 0.5 : 1,
                }}>
                Ask
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
