import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { jsPDF } from 'jspdf'
import ForceGraph2D from 'react-force-graph-2d'
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from 'react-simple-maps'
import kspLogo from './assets/ksp_logo.png'
import bannerLogo from './assets/banner_logo.png'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8001'

const TABS = ['Document Intelligence', 'Connections Map', 'Activity Timeline', 'QA Testing'] as const
type TabName = (typeof TABS)[number]

const ENTITY_COLORS: Record<string, string> = {
  PERSON: '#2196F3',
  ORGANIZATION: '#F44336',
  LOCATION: '#4CAF50',
  PHONE: '#FF9800',
  VEHICLE: '#9C27B0',
  OTHER: '#9E9E9E',
}

const RELATIONSHIP_COLORS: Record<string, string> = {
  MEMBER_OF: '#4CAF50',
  WORKS_AT: '#2196F3',
  SIBLING: '#FF9800',
  SPOUSE: '#E91E63',
  PARENT_OF: '#FF5722',
  CHILD_OF: '#FF5722',
  LIVES_AT: '#8BC34A',
  COLLEAGUE: '#9C27B0',
  PARTICIPATED_IN: '#00BCD4',
  REPORTS_TO: '#607D8B',
  LOCATED_IN: '#CDDC39',
  RELATED_TO: '#FFC107',
  CO_OCCURRENCE: 'rgba(255,255,255,0.15)',
}

type GraphNode = {
  id: number
  name: string
  type: string
  weight: number
  doc_names: string
  contexts: string
  x?: number
  y?: number
}

type GraphEdge = {
  source: number | GraphNode
  target: number | GraphNode
  type: string
  types?: string[]
  context?: string
}

// ── Activity Timeline types ──────────────────────────────────────────────────
type TimelineActivity = {
  id: number
  tms_id: string
  doc_id: string
  doc_name: string
  activity_date: string
  group_name: string
  subject: string
  description: string
  temporal_status: string
  priority: string
  theatre: string
  participants: string
  xref_count: number
}

type TimelineGroup = {
  group_name: string
  count: number
}

type BreadcrumbTrail = {
  main: TimelineActivity | null
  trail: TimelineActivity[]
  references: { source_tms_id: string; target_tms_id: string; context: string }[]
}

// ── Location Map types ───────────────────────────────────────────────────────
type LocationData = {
  id: number
  doc_id: string
  doc_name: string
  person_name: string
  address_text: string
  city: string
  locality: string
  lat: number
  lng: number
  address_type: string
}

// ── QA Testing types ────────────────────────────────────────────────────────
type QAResult = {
  index: number
  prompt: string
  answer: string
  used_chunks: { doc_name: string; page?: number }[]
  elapsed_ms: number
  error?: string | null
}

const ADDR_TYPE_COLORS: Record<string, string> = {
  PERMANENT: '#2196F3',
  PRESENT: '#4CAF50',
  PREVIOUS: '#FF9800',
  OTHER: '#9E9E9E',
}

const GROUP_COLORS: Record<string, string> = {}
const GROUP_COLOR_PALETTE = [
  '#2196F3', '#4CAF50', '#FF9800', '#9C27B0', '#00BCD4', '#F44336',
  '#607D8B', '#E91E63', '#8BC34A', '#FF5722', '#3F51B5', '#009688',
]

function getGroupColor(groupName: string): string {
  if (!GROUP_COLORS[groupName]) {
    const idx = Object.keys(GROUP_COLORS).length % GROUP_COLOR_PALETTE.length
    GROUP_COLORS[groupName] = GROUP_COLOR_PALETTE[idx]
  }
  return GROUP_COLORS[groupName]
}

// ── Download conversation history as PDF ────────────────────────────────────
type ChatMessage = { role: 'user' | 'assistant'; content: string }

type DocRecord = {
  doc_id?: string
  doc_name?: string
  [key: string]: unknown
}

type AuthUser = {
  id: number
  username: string
  full_name: string
  role: string
}

type Case = {
  id: number
  name: string
  description: string
  collection: 'IR' | 'SMAC'
  created_at: string
}

function downloadChatAsPdf(messages: ChatMessage[], title: string) {
  if (!messages.length) return

  const doc = new jsPDF()
  const pageW = doc.internal.pageSize.getWidth()
  const pageH = doc.internal.pageSize.getHeight()
  const margin = 14
  const maxW = pageW - 2 * margin

  doc.setFontSize(16)
  doc.setFont('helvetica', 'bold')
  doc.setTextColor(11, 44, 74)
  doc.text(title, margin, 20)

  doc.setFontSize(10)
  doc.setFont('helvetica', 'normal')
  doc.setTextColor(128, 128, 128)
  doc.text(`Generated: ${new Date().toLocaleString()}`, margin, 28)

  let y = 36

  for (const msg of messages) {
    const isUser = msg.role === 'user'
    const prefix = isUser ? 'Q: ' : 'A: '
    doc.setFont('helvetica', isUser ? 'bold' : 'normal')
    doc.setFontSize(11)
    doc.setTextColor(isUser ? 0 : 51, isUser ? 51 : 51, isUser ? 153 : 51)

    const lines: string[] = doc.splitTextToSize(prefix + msg.content, maxW)
    const blockH = lines.length * 5.5

    if (y + blockH > pageH - 20) {
      doc.addPage()
      y = 20
    }

    doc.text(lines, margin, y)
    y += blockH + 5
  }

  const filename = title.replace(/[^a-zA-Z0-9]/g, '_') + '_' + new Date().toISOString().slice(0, 10) + '.pdf'
  doc.save(filename)
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('isd_token')
  const existingHeaders = (options?.headers as Record<string, string>) || {}
  const headers: Record<string, string> = { ...existingHeaders }
  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
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

export default function App() {

  const [docQuestion, setDocQuestion] = useState('')

  // ── Auth + Case state ────────────────────────────────────────────────────
  const [authToken, setAuthToken] = useState<string | null>(() => localStorage.getItem('isd_token'))
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null)
  const [authView, setAuthView] = useState<'login' | 'register'>('login')
  const [authUsername, setAuthUsername] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authFullName, setAuthFullName] = useState('')
  const [authError, setAuthError] = useState('')
  const [authLoading, setAuthLoading] = useState(false)

  const [cases, setCases] = useState<Case[]>([])
  const [activeCase, setActiveCase] = useState<Case | null>(null)
  const [casesLoading, setCasesLoading] = useState(false)
  const [newCaseName, setNewCaseName] = useState('')
  const [newCaseDescription, setNewCaseDescription] = useState('')
  const [newCaseCollection, setNewCaseCollection] = useState<'IR' | 'SMAC'>('IR')
  const [showNewCaseForm, setShowNewCaseForm] = useState(false)
  const [caseError, setCaseError] = useState('')

  const [docChat, setDocChat] = useState<ChatMessage[]>([])
  const [docs, setDocs] = useState<DocRecord[]>([])
  const [docStatus, setDocStatus] = useState('')
  const [docLastAnswer, setDocLastAnswer] = useState('')
  const [lastRating, setLastRating] = useState<number | null>(null)
  const [ratingSubmitting, setRatingSubmitting] = useState(false)
  const [docLastError, setDocLastError] = useState('')
  const [activeCollection, setActiveCollection] = useState<'SMAC' | 'IR'>('SMAC')
  const [docFiles, setDocFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const folderInputRef = useRef<HTMLInputElement | null>(null)
  const [docLoading, setDocLoading] = useState(false)
  const [docIndexing, setDocIndexing] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)
  const [showQueryHelp, setShowQueryHelp] = useState(false)
  const [spellCorrections, setSpellCorrections] = useState<Record<string, string> | null>(null)
  const skipSpellCheckRef = useRef(false)
  const [failedDocs, setFailedDocs] = useState<{ name: string; error: string }[]>([])
  // const [confirmClearDocs, setConfirmClearDocs] = useState(false)  // disabled — clear docs removed
  const [showSignOutDialog, setShowSignOutDialog] = useState(false)

  // Voice Q&A state
  const [isRecording, setIsRecording] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [voiceStatus, setVoiceStatus] = useState('')
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([])
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('')
  const [micLevel, setMicLevel] = useState(0)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const micLevelIntervalRef = useRef<number | null>(null)

  // Indexing progress state
  const [indexProgress, setIndexProgress] = useState<{ current: number; total: number; startTime: number; fileName: string } | null>(null)
  const [lastIndexSummary, setLastIndexSummary] = useState<{ count: number; seconds: number } | null>(null)

  // TTS pause state
  const [isPaused, setIsPaused] = useState(false)

  // Elapsed seconds timer for indexing progress
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  // Tab state
  const [activeTab, setActiveTab] = useState<TabName>('Document Intelligence')

  // Entity Graph state
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([])
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([])
  const [graphSearch, setGraphSearch] = useState('')
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphExtracting, setGraphExtracting] = useState(false)
  const [graphStatus, setGraphStatus] = useState('')
  const [extractionDone, setExtractionDone] = useState(false)
  const pollRef = useRef<number | null>(null)
  const [graphTypeFilters, setGraphTypeFilters] = useState<Record<string, boolean>>({
    PERSON: true,
    ORGANIZATION: true,
    LOCATION: true,
    PHONE: true,
    VEHICLE: true,
    OTHER: true,
  })
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const graphRef = useRef<any>(null)

  // Activity Timeline state
  const [timelineActivities, setTimelineActivities] = useState<TimelineActivity[]>([])
  const [timelineGroups, setTimelineGroups] = useState<TimelineGroup[]>([])
  const [timelineLoading, setTimelineLoading] = useState(false)
  const [timelineExtracting, setTimelineExtracting] = useState(false)
  const [timelineStatus, setTimelineStatus] = useState('')
  const [timelineExtractionDone, setTimelineExtractionDone] = useState(false)
  const [timelineGroupFilter, setTimelineGroupFilter] = useState<Record<string, boolean>>({})
  const [timelineStatusFilter, setTimelineStatusFilter] = useState<string | null>(null)
  const [timelineSearch, setTimelineSearch] = useState('')
  const [expandedActivity, setExpandedActivity] = useState<number | null>(null)
  const [breadcrumbTrail, setBreadcrumbTrail] = useState<BreadcrumbTrail | null>(null)
  const [breadcrumbLoading, setBreadcrumbLoading] = useState(false)
  const timelinePollRef = useRef<number | null>(null)

  // Connections Map view toggle: 'graph' = Entity Graph, 'map' = Location Map
  const [connectionsView, setConnectionsView] = useState<'graph' | 'map'>('graph')

  // Location Map state
  const [locationData, setLocationData] = useState<LocationData[]>([])
  const [locationLoading, setLocationLoading] = useState(false)
  const [locationExtracting, setLocationExtracting] = useState(false)
  const [locationStatus, setLocationStatus] = useState('')
  const [locationExtractionDone, setLocationExtractionDone] = useState(false)
  const [selectedLocation, setSelectedLocation] = useState<LocationData | null>(null)
  const locationPollRef = useRef<number | null>(null)

  // QA Testing state
  const [qaFile, setQaFile] = useState<File | null>(null)
  const [qaPrompts, setQaPrompts] = useState<string[]>([])
  const [qaCollection, setQaCollection] = useState<'SMAC' | 'IR'>('SMAC')
  const [qaSelectedDocs, setQaSelectedDocs] = useState<string[]>([])
  const [qaDocs, setQaDocs] = useState<DocRecord[]>([])
  const [qaRunning, setQaRunning] = useState(false)
  const [_qaRunId, setQaRunId] = useState('')
  const [qaResults, setQaResults] = useState<QAResult[]>([])
  const [qaCurrent, setQaCurrent] = useState(0)
  const [qaTotal, setQaTotal] = useState(0)
  const [qaStatus, setQaStatus] = useState('')
  const [qaExpandedRows, setQaExpandedRows] = useState<Set<number>>(new Set())
  const qaFileInputRef = useRef<HTMLInputElement | null>(null)
  const qaPollRef = useRef<number | null>(null)

  // ── Auth handlers ────────────────────────────────────────────────────────
  const handleLogin = async () => {
    setAuthError('')
    setAuthLoading(true)
    try {
      const data = await apiFetch<{ok:boolean; token:string; user:AuthUser}>('/auth/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: authUsername, password: authPassword}),
      })
      if (data.ok) {
        localStorage.setItem('isd_token', data.token)
        setAuthToken(data.token)
        setCurrentUser(data.user)
      }
    } catch (e: any) {
      setAuthError(e.message || 'Login failed')
    } finally {
      setAuthLoading(false)
    }
  }

  const handleRegister = async () => {
    setAuthError('')
    setAuthLoading(true)
    try {
      const data = await apiFetch<{ok:boolean; token:string; user:AuthUser}>('/auth/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: authUsername, password: authPassword, full_name: authFullName}),
      })
      if (data.ok) {
        localStorage.setItem('isd_token', data.token)
        setAuthToken(data.token)
        setCurrentUser(data.user)
      }
    } catch (e: any) {
      setAuthError(e.message || 'Registration failed')
    } finally {
      setAuthLoading(false)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('isd_token')
    setAuthToken(null)
    setCurrentUser(null)
    setActiveCase(null)
    setCases([])
    setShowSignOutDialog(false)
  }

  const handleSignOutRequest = () => {
    if (docIndexing || graphExtracting) return   // block during active operations
    setShowSignOutDialog(true)
  }

  // handleSignOutClearAndLogout — disabled to prevent accidental data loss

  // ── Case handlers ────────────────────────────────────────────────────────
  const loadCases = useCallback(async () => {
    setCasesLoading(true)
    try {
      const data = await apiFetch<{ok:boolean; cases:Case[]}>('/cases')
      if (data.ok) setCases(data.cases)
    } catch (e) {
      console.error('[Cases] Load failed:', e)
    } finally {
      setCasesLoading(false)
    }
  }, [])

  const handleCreateCase = async () => {
    if (!newCaseName.trim()) return
    setCaseError('')
    try {
      const data = await apiFetch<{ok:boolean; case:Case}>('/cases', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: newCaseName, description: newCaseDescription, collection: newCaseCollection}),
      })
      if (data.ok) {
        setNewCaseName('')
        setNewCaseDescription('')
        setShowNewCaseForm(false)
        await loadCases()
        // Sync activeCollection with the new case's collection
        setActiveCollection(data.case.collection)
        setActiveCase(data.case)
      }
    } catch (e: any) {
      setCaseError(e.message || 'Failed to create case')
    }
  }

  const handleDeleteCase = async (caseId: number) => {
    if (!window.confirm('Delete this case and all its documents?')) return
    try {
      await apiFetch(`/cases/${caseId}`, {method: 'DELETE'})
      if (activeCase?.id === caseId) setActiveCase(null)
      await loadCases()
    } catch (e: any) {
      setCaseError(e.message || 'Failed to delete case')
    }
  }

  const handleSelectCase = (c: Case) => {
    setActiveCase(c)
    setActiveCollection(c.collection)
    // Reset doc list when switching cases
    setDocs([])
    setDocChat([])
    setDocStatus('')
  }

  // Load indexed document list from backend on mount & collection change (survives page refresh)
  useEffect(() => {
    if (!activeCase) return
    let isMounted = true
    apiFetch<{ ok: boolean; docs?: DocRecord[] }>(`/docs/list?collection=${activeCollection}&case_id=${activeCase!.id}`)
      .then((data) => {
        if (isMounted && data?.ok && data.docs) {
          setDocs(data.docs)
          if (data.docs.length > 0) {
            setDocStatus(`OK ${data.docs.length} document${data.docs.length !== 1 ? 's' : ''} indexed. Ready for Q&A.`)
          }
        }
      })
      .catch(() => {})
    return () => { isMounted = false }
  }, [activeCollection, activeCase])

  // Load user info from token on mount
  useEffect(() => {
    if (!authToken) return
    apiFetch<{ok:boolean; user:AuthUser}>('/auth/me')
      .then(data => { if (data.ok) setCurrentUser(data.user) })
      .catch(() => {
        // Token invalid/expired — clear it
        localStorage.removeItem('isd_token')
        setAuthToken(null)
      })
  }, [authToken])

  // Load cases when authenticated
  useEffect(() => {
    if (authToken) loadCases()
  }, [authToken, loadCases])

  // Enumerate audio input devices
  useEffect(() => {
    const enumerateDevices = async () => {
      try {
        const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true })
        tempStream.getTracks().forEach((t) => t.stop())

        const devices = await navigator.mediaDevices.enumerateDevices()
        const audioInputs = devices.filter((d) => d.kind === 'audioinput')
        setAudioDevices(audioInputs)
        console.log('[Voice] Audio devices:', audioInputs.map((d) => `${d.label} (${d.deviceId.slice(0, 8)})`))
        if (audioInputs.length > 0 && !selectedDeviceId) {
          setSelectedDeviceId(audioInputs[0].deviceId)
        }
      } catch (err) {
        console.warn('[Voice] Could not enumerate audio devices:', err)
      }
    }
    enumerateDevices()
  }, [])

  // Tick elapsed seconds every 1s while indexing
  useEffect(() => {
    if (!docIndexing) {
      setElapsedSeconds(0)
      return
    }
    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [docIndexing])

  const handleDocIndex = async () => {
    setDocStatus('')
    setDocLastError('')
    setDocLastAnswer('')
    setFailedDocs([])

    if (!docFiles.length) {
      setDocLastError('Please choose one or more files (or a folder) to index.')
      return
    }

    const files = docFiles
    setDocIndexing(true)
    setIndexProgress({ current: 0, total: files.length, startTime: Date.now(), fileName: files[0].name })

    let indexedCount = 0
    const failures: { name: string; error: string }[] = []

    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      setIndexProgress((prev) => prev ? { ...prev, fileName: file.name } : null)

      const formData = new FormData()
      formData.append('file', file)
      formData.append('collection', activeCollection)
      formData.append('case_id', String(activeCase!.id))

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
          const detail = (data as any).detail ? `${data.error}: ${(data as any).detail}` : (data.error || 'Indexing failed.')
          failures.push({ name: file.name, error: detail })
        } else {
          indexedCount += 1
          setDocs((prev) => [...prev, data])
        }
      } catch (error) {
        failures.push({ name: file.name, error: error instanceof Error ? error.message : 'Indexing failed.' })
      }

      setIndexProgress((prev) => prev ? { ...prev, current: i + 1 } : null)
    }

    if (indexedCount > 0) {
      setDocStatus(`OK Indexed ${indexedCount} document(s). Ready for Q&A.${failures.length ? ` ${failures.length} failed.` : ''}`)
    }

    if (indexedCount === 0) {
      setDocLastError('All documents failed to index.')
    }

    if (failures.length > 0) {
      setFailedDocs(failures)
    }

    if (indexedCount > 0) {
      setLastIndexSummary({ count: indexedCount, seconds: elapsedSeconds })
    }
    setIndexProgress(null)
    setDocIndexing(false)
  }

  const handleDocAsk = async () => {
    setDocStatus('')
    setDocLastError('')
    setDocLastAnswer('')
    setSpellCorrections(null)

    const question = docQuestion.trim()
    if (!docs.length) {
      setDocLastError('Please index at least one document first.')
      return
    }

    if (!question) {
      setDocLastError('Please type a question.')
      return
    }

    // Spell check before asking (skip if user chose "Ask Anyway")
    if (!skipSpellCheckRef.current) {
      try {
        const spellData = await apiFetch<{ corrections?: Record<string, string> }>(
          '/spell-check',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: question }),
          }
        )
        if (spellData?.corrections && Object.keys(spellData.corrections).length > 0) {
          setSpellCorrections(spellData.corrections)
          return  // Stop here — user decides Fix & Ask or Ask Anyway
        }
      } catch {
        // Spell check failed (backend not running etc.) — proceed with Q&A anyway
      }
    }
    skipSpellCheckRef.current = false

    const controller = new AbortController()
    abortControllerRef.current = controller
    setDocLoading(true)

    try {
      // Pass null to search across ALL indexed documents (not just one)
      const payload = {
        doc_id: null,
        question,
        history: docChat,
        collection: activeCollection,
        case_id: activeCase!.id,
      }

      const data = await apiFetch<{
        ok?: boolean
        answer?: string
        error?: string
      }>('/docs/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
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
        setLastRating(null)
        setDocStatus('OK Answer generated.')
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        setDocStatus('Query stopped.')
      } else {
        setDocLastError(error instanceof Error ? error.message : 'Document query failed.')
      }
    } finally {
      abortControllerRef.current = null
      setDocLoading(false)
    }
  }

  const handleRating = async (rating: number) => {
    if (!docLastAnswer || ratingSubmitting) return
    setRatingSubmitting(true)
    try {
      await apiFetch('/ratings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: docChat.length >= 2 ? docChat[docChat.length - 2].content : '',
          answer: docLastAnswer,
          rating,
          collection: activeCollection,
          case_id: activeCase?.id ?? 0,
        }),
      })
      setLastRating(rating)
    } catch (e) {
      console.error('Rating failed:', e)
    } finally {
      setRatingSubmitting(false)
    }
  }

  const handleSpellFix = () => {
    if (!spellCorrections) return
    let fixed = docQuestion
    for (const [wrong, right] of Object.entries(spellCorrections)) {
      fixed = fixed.replace(new RegExp(wrong, 'gi'), right)
    }
    setDocQuestion(fixed)
    setSpellCorrections(null)
    // Auto-submit with corrected text after a brief tick so state updates
    setTimeout(() => {
      const btn = document.querySelector('.btn-ask') as HTMLButtonElement
      if (btn) btn.click()
    }, 50)
  }

  const handleSpellIgnore = () => {
    setSpellCorrections(null)
    skipSpellCheckRef.current = true
    // Proceed with original text
    setTimeout(() => {
      const btn = document.querySelector('.btn-ask') as HTMLButtonElement
      if (btn) btn.click()
    }, 50)
  }

  const handleDocStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
  }

  // ── Voice Q&A handlers ──────────────────────────────────────────────────

  const speakText = (text: string) => {
    if (!text || !window.speechSynthesis) return
    window.speechSynthesis.cancel()
    const utter = new SpeechSynthesisUtterance(text)
    utter.rate = 1.0
    utter.pitch = 1.0
    utter.onstart = () => setIsSpeaking(true)
    utter.onend = () => setIsSpeaking(false)
    utter.onerror = () => setIsSpeaking(false)
    window.speechSynthesis.speak(utter)
  }

  const stopSpeaking = () => {
    window.speechSynthesis.cancel()
    setIsSpeaking(false)
    setIsPaused(false)
  }

  const pauseSpeaking = () => {
    window.speechSynthesis.pause()
    setIsPaused(true)
  }

  const resumeSpeaking = () => {
    window.speechSynthesis.resume()
    setIsPaused(false)
  }

  const handleVoiceToggle = async () => {
    if (isRecording && mediaRecorderRef.current) {
      mediaRecorderRef.current.stop()
      return
    }

    if (!docs.length) {
      setDocLastError('Please index at least one document before using voice.')
      return
    }

    setDocLastError('')
    setDocLastAnswer('')
    setDocStatus('')
    setVoiceStatus('Requesting microphone...')

    try {
      const audioConstraints: MediaTrackConstraints = {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      }
      if (selectedDeviceId) {
        audioConstraints.deviceId = { exact: selectedDeviceId }
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints })
      console.log(`[Voice] Using device: ${stream.getAudioTracks()[0]?.label}`)

      const audioCtx = new AudioContext()
      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)
      analyserRef.current = analyser
      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      micLevelIntervalRef.current = window.setInterval(() => {
        analyser.getByteFrequencyData(dataArray)
        const avg = dataArray.reduce((sum, v) => sum + v, 0) / dataArray.length
        setMicLevel(avg / 255)
      }, 100)

      const mimeOptions = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
      const selectedMime = mimeOptions.find((m) => MediaRecorder.isTypeSupported(m)) || ''
      console.log(`[Voice] Using MIME type: ${selectedMime || 'default'}`)
      const recorder = selectedMime
        ? new MediaRecorder(stream, { mimeType: selectedMime })
        : new MediaRecorder(stream)
      audioChunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        if (micLevelIntervalRef.current) { clearInterval(micLevelIntervalRef.current); micLevelIntervalRef.current = null }
        audioCtx.close()
        setMicLevel(0)
        setIsRecording(false)
        setVoiceStatus('Transcribing your speech...')

        const mimeType = recorder.mimeType || 'audio/webm'
        const ext = mimeType.includes('webm') ? 'webm' : mimeType.includes('ogg') ? 'ogg' : 'webm'
        const blob = new Blob(audioChunksRef.current, { type: mimeType })
        console.log(`[Voice] Sending ${blob.size} bytes as ${mimeType}`)

        try {
          const formData = new FormData()
          formData.append('audio', blob, `recording.${ext}`)

          const resp = await fetch(`${API_BASE}/docs/transcribe`, {
            method: 'POST',
            body: formData,
          })
          const data = await resp.json()

          if (!data.ok) {
            setDocLastError(data.error || 'Transcription failed.')
            setVoiceStatus('')
            return
          }

          const transcription = data.transcription || ''
          setDocQuestion(transcription)

          setVoiceStatus(`Heard: "${transcription}" — Querying...`)
          setDocLoading(true)

          // Pass null to search across ALL indexed documents
          const askResp = await apiFetch<{
            ok?: boolean
            answer?: string
            error?: string
          }>('/docs/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              doc_id: null,
              question: transcription,
              history: docChat,
              collection: activeCollection,
              case_id: activeCase!.id,
            }),
          })

          if (askResp?.ok === false) {
            setDocLastError(askResp.error || 'Document query failed.')
          } else {
            const answer = (askResp?.answer || '').trim()
            setDocChat((prev) => [
              ...prev,
              { role: 'user', content: transcription },
              { role: 'assistant', content: answer },
            ])

            if (answer.toLowerCase().startsWith('not found')) {
              setDocLastError(answer)
            } else {
              setDocLastAnswer(answer)
              setDocStatus('OK Voice answer generated.')
              speakText(answer)
            }
          }
        } catch (err) {
          setDocLastError(err instanceof Error ? err.message : 'Voice Q&A failed.')
        } finally {
          setDocLoading(false)
          setVoiceStatus('')
        }
      }

      mediaRecorderRef.current = recorder
      recorder.start(250)
      setIsRecording(true)
      setVoiceStatus('Recording... click mic to stop')
    } catch (err) {
      setVoiceStatus('')
      setDocLastError(
        err instanceof Error && err.name === 'NotAllowedError'
          ? 'Microphone access denied. Please allow microphone in browser settings.'
          : 'Failed to access microphone.'
      )
    }
  }

  // handleDocClear — disabled to prevent accidental data loss

  // ── Entity Graph ────────────────────────────────────────────────────────
  const loadGraphData = useCallback(async (search?: string) => {
    setGraphLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      params.set('limit', '1000')
      params.set('case_id', String(activeCase?.id ?? ''))
      const data = await apiFetch<{
        ok?: boolean
        nodes?: GraphNode[]
        edges?: GraphEdge[]
        error?: string
      }>(`/graph/data?${params.toString()}`)
      if (data?.ok !== false) {
        const nodes = data.nodes || []
        const edges = data.edges || []
        setGraphNodes(nodes)
        setGraphEdges(edges)
        // If we loaded data, mark extraction as done so buttons are enabled
        if (nodes.length > 0) {
          setExtractionDone(true)
        }
      }
    } catch (err) {
      console.error('[Graph] Failed to load graph data:', err)
    } finally {
      setGraphLoading(false)
    }
  }, [])

  // Start polling for extraction status (reusable helper)
  const startExtractionPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = window.setInterval(async () => {
      try {
        const status = await apiFetch<{
          ok?: boolean
          running?: boolean
          completed?: number
          total?: number
          done?: boolean
        }>('/graph/extraction-status')

        console.log('[Graph] Poll status:', status)

        if (status.running) {
          const docPart = `Doc ${(status.completed || 0) + 1}/${status.total || '?'}`
          const batchCurrent = (status as any).batch_current || 0
          const batchTotal   = (status as any).batch_total   || 0
          const batchPart    = batchTotal > 0 ? ` — Batch ${batchCurrent}/${batchTotal}` : ''
          const docName      = (status as any).doc_name ? ` (${(status as any).doc_name})` : ''
          setGraphStatus(`Extracting entities... ${docPart}${batchPart}${docName}`)
          // Refresh graph on every poll so nodes/edges appear as each batch commits
          if (batchCurrent > 0) loadGraphData()
        }

        // Check completion: done flag, or not running with completed work
        if (status.done || (!status.running && (status.completed || 0) > 0 && (status.completed || 0) >= (status.total || 1))) {
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
          setGraphExtracting(false)
          setExtractionDone(true)
          setGraphStatus('Extraction completed. Now you can search.')
          loadGraphData()
        }
      } catch (err) {
        console.warn('[Graph] Poll error:', err)
      }
    }, 3000)
  }, [loadGraphData])

  // Check extraction status and graph data when switching to Connections Map tab
  useEffect(() => {
    if (activeTab === 'Connections Map') {
      loadGraphData()
      // Also check extraction status in case extraction was completed or is running
      apiFetch<{
        ok?: boolean
        running?: boolean
        completed?: number
        total?: number
        done?: boolean
      }>('/graph/extraction-status')
        .then((status) => {
          console.log('[Graph] Tab switch status check:', status)
          if (status.done || (!status.running && (status.completed || 0) > 0 && (status.completed || 0) >= (status.total || 1))) {
            setExtractionDone(true)
          } else if (status.running) {
            // Extraction is currently running (e.g. from indexing) — show progress and poll
            setGraphExtracting(true)
            const _batchCurrent = (status as any).batch_current || 0
            const _batchTotal   = (status as any).batch_total   || 0
            const _batchPart    = _batchTotal > 0 ? ` — Batch ${_batchCurrent}/${_batchTotal}` : ''
            setGraphStatus(`Extracting entities... Doc ${(status.completed || 0) + 1}/${status.total || '?'}${_batchPart}`)
            startExtractionPolling()
          }
        })
        .catch(() => {})
    }
  }, [activeTab, loadGraphData, startExtractionPolling])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  // Tune d3-force for better node spacing when graph data changes
  useEffect(() => {
    if (graphRef.current && graphNodes.length > 0) {
      graphRef.current.d3Force('charge')?.strength(-120).distanceMax(300)
      graphRef.current.d3Force('link')?.distance(60)
      graphRef.current.d3Force('center')?.strength(0.05)
    }
  }, [graphNodes])

  const filteredGraphData = useMemo(() => {
    const visibleNodes = graphNodes.filter((n) => graphTypeFilters[n.type] !== false)
    const visibleIds = new Set(visibleNodes.map((n) => n.id))
    const visibleEdges = graphEdges.filter((e) => {
      const srcId = typeof e.source === 'object' ? e.source.id : e.source
      const tgtId = typeof e.target === 'object' ? e.target.id : e.target
      return visibleIds.has(srcId) && visibleIds.has(tgtId)
    })
    return { nodes: visibleNodes, links: visibleEdges }
  }, [graphNodes, graphEdges, graphTypeFilters])

  const handleGraphSearch = () => {
    loadGraphData(graphSearch.trim() || undefined)
  }


  const handleClearGraph = async () => {
    if (!window.confirm('Clear all graph data? You can re-extract entities from indexed documents afterwards.')) return
    try {
      await apiFetch<{ ok: boolean }>(`/graph/clear?case_id=${activeCase!.id}`, { method: 'DELETE' })
      setGraphNodes([])
      setGraphEdges([])
      setExtractionDone(false)
      setGraphStatus('Graph cleared. Click "Extract Entities" to rebuild.')
      setSelectedNode(null)
      setGraphSearch('')
    } catch (err) {
      setGraphStatus(err instanceof Error ? err.message : 'Failed to clear graph.')
    }
  }

  const handleExtractAll = async () => {
    setGraphExtracting(true)
    setGraphStatus('Starting entity extraction from all indexed documents...')
    try {
      const data = await apiFetch<{ ok?: boolean; message?: string; total?: number; error?: string }>(
        `/graph/extract-all?collection=${activeCollection}&case_id=${activeCase!.id}`,
        { method: 'POST' }
      )
      if (data?.ok === false) {
        // If extraction is already running (triggered during indexing), poll for it instead of giving up
        if (data.error?.toLowerCase().includes('already running')) {
          setGraphStatus('Entity extraction is in progress...')
          startExtractionPolling()
          return
        }
        setGraphStatus(data.error || 'Entity extraction failed.')
        setGraphExtracting(false)
        return
      }

      // Start polling for extraction progress
      startExtractionPolling()
    } catch (err) {
      setGraphStatus(err instanceof Error ? err.message : 'Entity extraction failed.')
      setGraphExtracting(false)
    }
  }

  const toggleTypeFilter = (type: string) => {
    setGraphTypeFilters((prev) => ({ ...prev, [type]: !prev[type] }))
  }

  const [hoveredNode, setHoveredNode] = useState<number | null>(null)

  // Build hover tooltip showing group memberships / member lists
  const getNodeTooltip = useCallback((node: any): string => {
    const n = node as GraphNode
    const nodeId = n.id

    // Find all edges connected to this node
    const connected = graphEdges
      .map((e) => {
        const srcId = typeof e.source === 'object' ? (e.source as GraphNode).id : e.source
        const tgtId = typeof e.target === 'object' ? (e.target as GraphNode).id : e.target
        if (srcId !== nodeId && tgtId !== nodeId) return null
        const otherId = srcId === nodeId ? tgtId : srcId
        const otherNode = graphNodes.find((gn) => gn.id === otherId)
        return otherNode ? { edge: e, other: otherNode } : null
      })
      .filter(Boolean) as { edge: GraphEdge; other: GraphNode }[]

    // Classify relationships by type
    const groups: string[] = []       // orgs connected to person
    const members: string[] = []      // persons connected to org
    const colleagues: string[] = []   // COLLEAGUE → person names

    for (const { edge, other } of connected) {
      const types = edge.types || [edge.type]
      const hasExplicit = types.some((t) => t !== 'CO_OCCURRENCE')
      if (!hasExplicit) continue // skip pure co-occurrence

      if (n.type === 'PERSON' && other.type === 'ORGANIZATION') {
        groups.push(other.name)
      } else if (n.type === 'ORGANIZATION' && other.type === 'PERSON') {
        members.push(other.name)
      } else if (types.includes('COLLEAGUE') && other.type === 'PERSON') {
        colleagues.push(other.name)
      }
    }

    // Build HTML tooltip
    const color = ENTITY_COLORS[n.type] || ENTITY_COLORS.OTHER
    let html = `<div style="max-width:280px;font-size:12px;line-height:1.5;background:#1a2744;color:#e8ecf1;padding:10px 12px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);box-shadow:0 4px 12px rgba(0,0,0,0.4)">`
    html += `<b style="font-size:13px;color:#fff">${n.name}</b> `
    html += `<span style="color:${color};font-size:10px;text-transform:uppercase">${n.type}</span>`

    if (n.type === 'PERSON') {
      if (groups.length) html += `<br/><br/><b>Groups:</b><br/>` + groups.map((g) => `&nbsp;&bull; ${g}`).join('<br/>')
      if (colleagues.length) html += `<br/><br/><b>Colleagues:</b><br/>` + colleagues.map((c) => `&nbsp;&bull; ${c}`).join('<br/>')
    } else if (n.type === 'ORGANIZATION') {
      if (members.length) html += `<br/><br/><b>Members (${members.length}):</b><br/>` + members.map((m) => `&nbsp;&bull; ${m}`).join('<br/>')
    } else {
      // For LOCATION etc, show connected persons
      const persons = connected.filter((c) => c.other.type === 'PERSON').slice(0, 10).map((c) => c.other.name)
      if (persons.length) html += `<br/><br/><b>Connected:</b><br/>` + persons.map((nm) => `&nbsp;&bull; ${nm}`).join('<br/>')
      if (connected.filter((c) => c.other.type === 'PERSON').length > 10) html += `<br/>&nbsp;&hellip; and more`
    }

    html += `</div>`
    return html
  }, [graphNodes, graphEdges])

  // ── Activity Timeline ────────────────────────────────────────────────────
  const loadTimelineData = useCallback(async (search?: string, group?: string, status?: string) => {
    setTimelineLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      if (group) params.set('group', group)
      if (status) params.set('status', status)
      if (activeCase?.id) params.set('case_id', String(activeCase!.id))
      const data = await apiFetch<{
        ok?: boolean
        activities?: TimelineActivity[]
        count?: number
        error?: string
      }>(`/timeline/data?${params.toString()}`)
      if (data?.ok !== false) {
        setTimelineActivities(data.activities || [])
        if ((data.activities || []).length > 0) {
          setTimelineExtractionDone(true)
        }
      }
    } catch (err) {
      console.error('[Timeline] Failed to load data:', err)
    } finally {
      setTimelineLoading(false)
    }
  }, [])

  const loadTimelineGroups = useCallback(async () => {
    try {
      const data = await apiFetch<{ ok?: boolean; groups?: TimelineGroup[] }>(`/timeline/groups${activeCase?.id ? `?case_id=${activeCase!.id}` : ''}`)
      if (data?.ok !== false && data.groups) {
        setTimelineGroups(data.groups)
        // Initialize group filters (all enabled)
        const filters: Record<string, boolean> = {}
        for (const g of data.groups) {
          filters[g.group_name] = true
        }
        setTimelineGroupFilter(filters)
      }
    } catch (err) {
      console.error('[Timeline] Failed to load groups:', err)
    }
  }, [])

  const startTimelinePolling = useCallback(() => {
    if (timelinePollRef.current) clearInterval(timelinePollRef.current)
    timelinePollRef.current = window.setInterval(async () => {
      try {
        const status = await apiFetch<{
          ok?: boolean
          running?: boolean
          completed?: number
          total?: number
          done?: boolean
        }>('/timeline/extraction-status')

        if (status.running) {
          setTimelineStatus(`Extracting activities... ${status.completed || 0}/${status.total || '?'} documents processed`)
        }

        if (status.done || (!status.running && (status.completed || 0) > 0 && (status.completed || 0) >= (status.total || 1))) {
          if (timelinePollRef.current) { clearInterval(timelinePollRef.current); timelinePollRef.current = null }
          setTimelineExtracting(false)
          setTimelineExtractionDone(true)
          setTimelineStatus('Extraction completed. Now you can browse and search activities.')
          loadTimelineData()
          loadTimelineGroups()
        }
      } catch (err) {
        console.warn('[Timeline] Poll error:', err)
      }
    }, 3000)
  }, [loadTimelineData, loadTimelineGroups])

  // Check timeline status when switching to Activity Timeline tab
  useEffect(() => {
    if (activeTab === 'Activity Timeline') {
      loadTimelineData()
      loadTimelineGroups()
      apiFetch<{
        ok?: boolean
        running?: boolean
        completed?: number
        total?: number
        done?: boolean
      }>('/timeline/extraction-status')
        .then((status) => {
          if (status.done || (!status.running && (status.completed || 0) > 0 && (status.completed || 0) >= (status.total || 1))) {
            setTimelineExtractionDone(true)
          } else if (status.running) {
            setTimelineExtracting(true)
            setTimelineStatus(`Extracting activities... ${status.completed || 0}/${status.total || '?'} documents processed`)
            startTimelinePolling()
          }
        })
        .catch(() => {})
    }
  }, [activeTab, loadTimelineData, loadTimelineGroups, startTimelinePolling])

  // Cleanup timeline polling on unmount
  useEffect(() => {
    return () => {
      if (timelinePollRef.current) clearInterval(timelinePollRef.current)
    }
  }, [])

  const handleTimelineExtract = async () => {
    setTimelineExtracting(true)
    setTimelineStatus('Starting activity extraction from all indexed documents...')
    try {
      const data = await apiFetch<{ ok?: boolean; message?: string; total?: number; error?: string }>(
        `/timeline/extract-all?collection=${activeCollection}&case_id=${activeCase!.id}`,
        { method: 'POST' }
      )
      if (data?.ok === false) {
        if (data.error?.toLowerCase().includes('already running')) {
          setTimelineStatus('Activity extraction is in progress...')
          startTimelinePolling()
          return
        }
        setTimelineStatus(data.error || 'Activity extraction failed.')
        setTimelineExtracting(false)
        return
      }
      startTimelinePolling()
    } catch (err) {
      setTimelineStatus(err instanceof Error ? err.message : 'Activity extraction failed.')
      setTimelineExtracting(false)
    }
  }

  const handleTimelineSearch = () => {
    const search = timelineSearch.trim() || undefined
    const group = undefined // group filtering done client-side
    const status = timelineStatusFilter || undefined
    loadTimelineData(search, group, status)
  }

  const handleActivityClick = async (activity: TimelineActivity) => {
    if (expandedActivity === activity.id) {
      setExpandedActivity(null)
      setBreadcrumbTrail(null)
      return
    }
    setExpandedActivity(activity.id)
    setBreadcrumbTrail(null)
    if (activity.tms_id && activity.xref_count > 0) {
      setBreadcrumbLoading(true)
      try {
        const data = await apiFetch<{ ok?: boolean } & BreadcrumbTrail>(
          `/timeline/breadcrumb?tms_id=${encodeURIComponent(activity.tms_id)}${activeCase?.id ? `&case_id=${activeCase!.id}` : ''}`
        )
        if (data?.ok !== false) {
          setBreadcrumbTrail({ main: data.main, trail: data.trail, references: data.references })
        }
      } catch (err) {
        console.error('[Timeline] Failed to load breadcrumb:', err)
      } finally {
        setBreadcrumbLoading(false)
      }
    }
  }

  const filteredTimelineActivities = useMemo(() => {
    return timelineActivities.filter((a) => {
      if (a.group_name && timelineGroupFilter[a.group_name] === false) return false
      return true
    })
  }, [timelineActivities, timelineGroupFilter])

  // ── Location Map ─────────────────────────────────────────────────────────
  const loadLocationData = useCallback(async () => {
    setLocationLoading(true)
    try {
      const data = await apiFetch<{ ok?: boolean; locations?: LocationData[]; count?: number }>(
        `/locations/data${activeCase?.id ? `?case_id=${activeCase!.id}` : ''}`
      )
      if (data?.ok !== false) {
        setLocationData(data.locations || [])
        if ((data.locations || []).length > 0) setLocationExtractionDone(true)
      }
    } catch (err) {
      console.error('[Locations] Failed to load:', err)
    } finally {
      setLocationLoading(false)
    }
  }, [])

  const startLocationPolling = useCallback(() => {
    if (locationPollRef.current) clearInterval(locationPollRef.current)
    locationPollRef.current = window.setInterval(async () => {
      try {
        const status = await apiFetch<{
          ok?: boolean; running?: boolean; completed?: number; total?: number; done?: boolean
        }>('/locations/extraction-status')

        if (status.running) {
          setLocationStatus(`Extracting locations... ${status.completed || 0}/${status.total || '?'} documents processed`)
        }

        if (status.done || (!status.running && (status.completed || 0) > 0 && (status.completed || 0) >= (status.total || 1))) {
          if (locationPollRef.current) { clearInterval(locationPollRef.current); locationPollRef.current = null }
          setLocationExtracting(false)
          setLocationExtractionDone(true)
          setLocationStatus('Extraction complete. Locations plotted on map.')
          loadLocationData()
        }
      } catch (err) {
        console.warn('[Locations] Poll error:', err)
      }
    }, 3000)
  }, [loadLocationData])

  const handleLocationExtract = async () => {
    setLocationExtracting(true)
    setLocationStatus('Starting location extraction from IR documents...')
    try {
      const data = await apiFetch<{ ok?: boolean; message?: string; total?: number; error?: string }>(
        `/locations/extract-all?collection=IR&case_id=${activeCase!.id}`,
        { method: 'POST' }
      )
      if (data?.ok === false) {
        if (data.error?.toLowerCase().includes('already running')) {
          setLocationStatus('Location extraction is in progress...')
          startLocationPolling()
          return
        }
        setLocationStatus(data.error || 'Location extraction failed.')
        setLocationExtracting(false)
        return
      }
      startLocationPolling()
    } catch (err) {
      setLocationStatus(err instanceof Error ? err.message : 'Location extraction failed.')
      setLocationExtracting(false)
    }
  }

  // Load location data when switching to Location Map view
  useEffect(() => {
    if (activeTab === 'Connections Map' && connectionsView === 'map') {
      loadLocationData()
      apiFetch<{ ok?: boolean; running?: boolean; completed?: number; total?: number; done?: boolean }>(
        '/locations/extraction-status'
      ).then((status) => {
        if (status.done || (!status.running && (status.completed || 0) > 0)) {
          setLocationExtractionDone(true)
        } else if (status.running) {
          setLocationExtracting(true)
          setLocationStatus(`Extracting locations... ${status.completed || 0}/${status.total || '?'} documents processed`)
          startLocationPolling()
        }
      }).catch(() => {})
    }
  }, [activeTab, connectionsView, loadLocationData, startLocationPolling])

  // Cleanup location polling on unmount
  useEffect(() => {
    return () => { if (locationPollRef.current) clearInterval(locationPollRef.current) }
  }, [])

  // ── QA Testing handlers ─────────────────────────────────────────────────

  // Load docs for the QA collection selector
  useEffect(() => {
    if (activeTab !== 'QA Testing') return
    apiFetch<{ ok: boolean; docs?: DocRecord[] }>(`/docs/list?collection=${qaCollection}`)
      .then((data) => {
        if (data?.ok && data.docs) {
          setQaDocs(data.docs)
        }
      })
      .catch(() => {})
  }, [activeTab, qaCollection])

  // Cleanup QA polling on unmount
  useEffect(() => {
    return () => { if (qaPollRef.current) clearInterval(qaPollRef.current) }
  }, [])

  const handleQaUpload = async () => {
    if (!qaFile) {
      setQaStatus('Please select a PDF or DOCX file containing test prompts.')
      return
    }
    setQaStatus('Extracting prompts...')
    setQaPrompts([])
    setQaResults([])

    const formData = new FormData()
    formData.append('file', qaFile)

    try {
      const data = await apiFetch<{ ok: boolean; prompts?: string[]; count?: number; error?: string }>(
        '/qa/upload-prompts',
        { method: 'POST', body: formData },
      )
      if (data?.ok && data.prompts) {
        setQaPrompts(data.prompts)
        setQaStatus(`Extracted ${data.count} prompt(s). Select documents and click "Run All Tests".`)
      } else {
        setQaStatus(data?.error || 'Failed to extract prompts.')
      }
    } catch (err) {
      setQaStatus(err instanceof Error ? err.message : 'Upload failed.')
    }
  }

  const handleQaRun = async () => {
    if (!qaPrompts.length) {
      setQaStatus('No prompts extracted. Upload a file first.')
      return
    }
    setQaRunning(true)
    setQaResults([])
    setQaCurrent(0)
    setQaTotal(qaPrompts.length)
    setQaStatus('Starting test run...')
    setQaExpandedRows(new Set())

    try {
      const data = await apiFetch<{ ok: boolean; run_id?: string; total?: number; error?: string }>(
        '/qa/run',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompts: qaPrompts,
            doc_ids: qaSelectedDocs.length > 0 ? qaSelectedDocs : null,
            collection: qaCollection,
          }),
        },
      )

      if (!data?.ok || !data.run_id) {
        setQaStatus(data?.error || 'Failed to start test run.')
        setQaRunning(false)
        return
      }

      setQaRunId(data.run_id)
      setQaTotal(data.total || qaPrompts.length)

      // Start polling for progress
      qaPollRef.current = window.setInterval(async () => {
        try {
          const status = await apiFetch<{
            ok: boolean; status?: string; current?: number; total?: number; results?: QAResult[]
          }>(`/qa/status?run_id=${data.run_id}`)

          if (status?.ok) {
            setQaCurrent(status.current || 0)
            setQaTotal(status.total || qaPrompts.length)
            setQaResults(status.results || [])
            setQaStatus(`Running... ${status.current || 0}/${status.total || qaPrompts.length} prompts completed`)

            if (status.status === 'done') {
              if (qaPollRef.current) clearInterval(qaPollRef.current)
              qaPollRef.current = null
              setQaRunning(false)
              setQaStatus(`Done! ${status.total} prompt(s) completed.`)
            }
          }
        } catch {
          // Keep polling on transient errors
        }
      }, 2000)
    } catch (err) {
      setQaStatus(err instanceof Error ? err.message : 'Failed to start test run.')
      setQaRunning(false)
    }
  }

  const toggleQaRow = (index: number) => {
    setQaExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  const downloadQAReport = () => {
    if (!qaResults.length) return

    const pdf = new jsPDF()
    const pageW = pdf.internal.pageSize.getWidth()
    const pageH = pdf.internal.pageSize.getHeight()
    const margin = 14
    const maxW = pageW - 2 * margin

    pdf.setFontSize(16)
    pdf.setFont('helvetica', 'bold')
    pdf.setTextColor(11, 44, 74)
    pdf.text(`QA Testing Report — ${qaCollection}`, margin, 20)

    pdf.setFontSize(10)
    pdf.setFont('helvetica', 'normal')
    pdf.setTextColor(128, 128, 128)
    pdf.text(`Generated: ${new Date().toLocaleString()}  |  Prompts: ${qaResults.length}`, margin, 28)

    let y = 38

    for (const r of qaResults) {
      // Check if we need a new page
      if (y > pageH - 40) {
        pdf.addPage()
        y = 20
      }

      // Prompt
      pdf.setFont('helvetica', 'bold')
      pdf.setFontSize(11)
      pdf.setTextColor(0, 51, 153)
      const pLines: string[] = pdf.splitTextToSize(`Q${r.index + 1}: ${r.prompt}`, maxW)
      pdf.text(pLines, margin, y)
      y += pLines.length * 5.5 + 2

      // Answer
      pdf.setFont('helvetica', 'normal')
      pdf.setFontSize(10)
      pdf.setTextColor(51, 51, 51)
      const ansText = r.error ? `ERROR: ${r.error}` : (r.answer || 'No answer')
      const aLines: string[] = pdf.splitTextToSize(`A: ${ansText}`, maxW)

      // Check page overflow for answer
      if (y + aLines.length * 4.5 > pageH - 20) {
        pdf.addPage()
        y = 20
      }
      pdf.text(aLines, margin, y)
      y += aLines.length * 4.5 + 2

      // Source docs + time
      pdf.setFontSize(8)
      pdf.setTextColor(128, 128, 128)
      const sources = r.used_chunks?.length
        ? r.used_chunks.map((c) => c.doc_name).filter((v, i, a) => a.indexOf(v) === i).join(', ')
        : 'N/A'
      pdf.text(`Sources: ${sources}  |  Time: ${r.elapsed_ms}ms`, margin, y)
      y += 10
    }

    // Summary
    if (y > pageH - 30) {
      pdf.addPage()
      y = 20
    }
    pdf.setFontSize(11)
    pdf.setFont('helvetica', 'bold')
    pdf.setTextColor(11, 44, 74)
    const totalTime = qaResults.reduce((sum, r) => sum + (r.elapsed_ms || 0), 0)
    pdf.text(`Summary: ${qaResults.length} prompts  |  Total time: ${(totalTime / 1000).toFixed(1)}s`, margin, y)

    pdf.save(`QA_Report_${qaCollection}_${new Date().toISOString().slice(0, 10)}.pdf`)
  }

  const nodeCanvasObject = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = node.name as string
      const type = node.type as string
      const weight = (node.weight as number) || 1
      const isSelected = selectedNode?.id === node.id
      const isHovered = hoveredNode === node.id

      // Adaptive radius: smaller base, grows with weight
      const radius = Math.max(3, Math.min(10, 2 + weight * 1.5))

      // Circle with glow for selected/hovered
      if (isSelected || isHovered) {
        ctx.beginPath()
        ctx.arc(node.x, node.y, radius + 3, 0, 2 * Math.PI)
        ctx.fillStyle = isSelected ? 'rgba(255,215,0,0.3)' : 'rgba(255,255,255,0.15)'
        ctx.fill()
      }

      ctx.beginPath()
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
      ctx.fillStyle = ENTITY_COLORS[type] || ENTITY_COLORS.OTHER
      ctx.fill()

      if (isSelected) {
        ctx.strokeStyle = '#FFD700'
        ctx.lineWidth = 1.5
        ctx.stroke()
      }

      // Label: only show when zoomed in enough, or for important/selected/hovered nodes
      const showLabel = globalScale > 2 || isSelected || isHovered || weight >= 3
      if (showLabel) {
        const truncated = label.length > 18 ? label.slice(0, 17) + '\u2026' : label
        const fontSize = Math.max(7, Math.min(11, 9 / globalScale))

        ctx.font = `${fontSize}px Sans-Serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'

        // Dark outline for readability on dark bg
        ctx.strokeStyle = 'rgba(0,0,0,0.7)'
        ctx.lineWidth = 2.5
        ctx.lineJoin = 'round'
        ctx.strokeText(truncated, node.x, node.y + radius + 2)

        ctx.fillStyle = '#E8E8E8'
        ctx.fillText(truncated, node.x, node.y + radius + 2)
      }
    },
    [selectedNode, hoveredNode]
  )

  // ── Not authenticated → show Login / Register screen ─────────────────────
  if (!authToken) {
    return (
      <div style={{minHeight:'100vh',background:'#0b2c4a',display:'flex',alignItems:'center',justifyContent:'center'}}>
        <div style={{background:'#fff',borderRadius:16,width:420,boxShadow:'0 16px 48px rgba(0,0,0,0.4)',border:'3px solid #b10000',overflow:'hidden'}}>
          {/* Yellow header with KSP logo */}
          <div style={{background:'#ffd400',padding:'24px 32px 18px',textAlign:'center',borderBottom:'3px solid #b10000'}}>
            <img src={kspLogo} alt="KSP" style={{width:96,height:76,objectFit:'contain',display:'block',margin:'0 auto 10px'}} />
            <div style={{fontSize:28,fontWeight:800,color:'#b10000',letterSpacing:1}}>ISD-AI</div>
            <div style={{color:'#0b2c4a',marginTop:4,fontSize:13,fontWeight:600,fontStyle:'italic'}}>empowering law enforcement with artificial intelligence</div>
          </div>

          {/* Form area */}
          <div style={{padding:'28px 32px'}}>
            <div style={{display:'flex',marginBottom:20,gap:8}}>
              {(['login','register'] as const).map(v => (
                <button key={v} onClick={()=>{setAuthView(v);setAuthError('')}}
                  style={{flex:1,padding:'8px 0',borderRadius:8,cursor:'pointer',fontWeight:600,fontSize:14,
                    background:authView===v?'#b10000':'transparent',color:authView===v?'#fff':'#555',
                    border:authView===v?'2px solid #b10000':'2px solid #ccc'}}>
                  {v === 'login' ? 'Sign In' : 'Register'}
                </button>
              ))}
            </div>

            <div style={{display:'flex',flexDirection:'column',gap:12}}>
              {authView === 'register' && (
                <input placeholder="Full Name" value={authFullName} onChange={e=>setAuthFullName(e.target.value)}
                  style={{padding:'10px 14px',borderRadius:8,border:'1px solid #ccc',background:'#f6f8fb',color:'#333',fontSize:14,outline:'none'}}/>
              )}
              <input placeholder="Username" value={authUsername} onChange={e=>setAuthUsername(e.target.value)}
                onKeyDown={e=>{if(e.key==='Enter')(authView==='login'?handleLogin:handleRegister)()}}
                style={{padding:'10px 14px',borderRadius:8,border:'1px solid #ccc',background:'#f6f8fb',color:'#333',fontSize:14,outline:'none'}}/>
              <input type="password" placeholder="Password" value={authPassword} onChange={e=>setAuthPassword(e.target.value)}
                onKeyDown={e=>{if(e.key==='Enter')(authView==='login'?handleLogin:handleRegister)()}}
                style={{padding:'10px 14px',borderRadius:8,border:'1px solid #ccc',background:'#f6f8fb',color:'#333',fontSize:14,outline:'none'}}/>

              {authError && <div style={{color:'#b10000',fontSize:13,textAlign:'center',fontWeight:600}}>{authError}</div>}

              <button onClick={authView==='login'?handleLogin:handleRegister} disabled={authLoading}
                style={{padding:'12px 0',borderRadius:8,border:'2px solid rgba(0,0,0,0.2)',background:'#ffd400',color:'#000',fontWeight:700,fontSize:15,cursor:authLoading?'not-allowed':'pointer',opacity:authLoading?0.7:1,marginTop:4}}>
                {authLoading ? 'Please wait...' : (authView === 'login' ? 'Sign In' : 'Create Account')}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ── Authenticated but no active case → show Case Selector ────────────────
  if (!activeCase) {
    return (
      <div style={{minHeight:'100vh',background:'#0b2c4a',padding:'32px 24px'}}>
        <div style={{maxWidth:960,margin:'0 auto'}}>
          {/* Header bar — yellow/red KSP style */}
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:28,background:'#ffd400',borderRadius:14,padding:'20px 28px',border:'3px solid #b10000'}}>
            <div style={{display:'flex',alignItems:'center',gap:20}}>
              <img src={kspLogo} alt="KSP" style={{width:90,height:72,objectFit:'contain'}} />
              <div>
                <div style={{display:'flex',alignItems:'baseline',gap:14}}>
                  <span style={{fontSize:34,fontWeight:800,color:'#b10000',letterSpacing:1}}>ISD-AI</span>
                  <span style={{fontSize:15,fontWeight:600,fontStyle:'italic',color:'#0b2c4a',whiteSpace:'nowrap'}}>empowering law enforcement with artificial intelligence</span>
                </div>
                <div style={{color:'#333',fontSize:15,marginTop:5,fontStyle:'italic'}}>Welcome, {currentUser?.full_name || currentUser?.username}</div>
              </div>
            </div>
            <button onClick={handleLogout}
              style={{padding:'10px 20px',borderRadius:8,border:'2px solid #b10000',background:'#b10000',color:'#ffd400',cursor:'pointer',fontSize:14,fontWeight:700}}>
              Sign Out
            </button>
          </div>

          <div style={{background:'#fff',borderRadius:12,padding:24,marginBottom:20,boxShadow:'0 4px 20px rgba(0,0,0,0.2)'}}>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:16}}>
              <div style={{fontSize:17,fontWeight:600,color:'#0b2c4a'}}>My Cases</div>
              <button onClick={()=>setShowNewCaseForm(v=>!v)}
                style={{padding:'6px 14px',borderRadius:8,border:'2px solid rgba(0,0,0,0.2)',background:'#ffd400',color:'#000',fontWeight:600,cursor:'pointer',fontSize:13}}>
                + New Case
              </button>
            </div>

            {showNewCaseForm && (
              <div style={{background:'#f6f8fb',borderRadius:10,padding:16,marginBottom:16,display:'flex',flexDirection:'column',gap:10,border:'1px solid #ddd'}}>
                <input placeholder="Case name (e.g. Subject: Ravi Kumar)" value={newCaseName} onChange={e=>setNewCaseName(e.target.value)}
                  style={{padding:'9px 12px',borderRadius:8,border:'1px solid #ccc',background:'#fff',color:'#333',fontSize:14,outline:'none'}}/>
                <input placeholder="Description (optional)" value={newCaseDescription} onChange={e=>setNewCaseDescription(e.target.value)}
                  style={{padding:'9px 12px',borderRadius:8,border:'1px solid #ccc',background:'#fff',color:'#333',fontSize:14,outline:'none'}}/>
                <select value={newCaseCollection} onChange={e=>setNewCaseCollection(e.target.value as 'IR'|'SMAC')}
                  style={{padding:'9px 12px',borderRadius:8,border:'1px solid #ccc',background:'#fff',color:'#333',fontSize:14,outline:'none'}}>
                  <option value="IR">IR — Interrogation Report</option>
                  <option value="SMAC">SMAC — Social Media / Intelligence Log</option>
                </select>
                {caseError && <div style={{color:'#b10000',fontSize:13,fontWeight:600}}>{caseError}</div>}
                <div style={{display:'flex',gap:8}}>
                  <button onClick={handleCreateCase}
                    style={{flex:1,padding:'8px 0',borderRadius:8,border:'2px solid rgba(0,0,0,0.2)',background:'#ffd400',color:'#000',fontWeight:600,cursor:'pointer'}}>
                    Create Case
                  </button>
                  <button onClick={()=>setShowNewCaseForm(false)}
                    style={{padding:'8px 16px',borderRadius:8,border:'1px solid #ccc',background:'transparent',color:'#555',cursor:'pointer'}}>
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {casesLoading ? (
              <div style={{color:'#555',textAlign:'center',padding:24}}>Loading cases...</div>
            ) : cases.length === 0 ? (
              <div style={{color:'#888',textAlign:'center',padding:24,fontSize:14}}>
                No cases yet. Create your first case to get started.
              </div>
            ) : (
              <div style={{display:'flex',flexDirection:'column',gap:8}}>
                {cases.map(c => (
                  <div key={c.id}
                    style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'12px 16px',
                      background:'#f6f8fb',borderRadius:10,border:'1px solid #e0e0e0',cursor:'pointer'}}
                    onClick={()=>handleSelectCase(c)}>
                    <div>
                      <div style={{color:'#0b2c4a',fontWeight:600,fontSize:15}}>{c.name}</div>
                      {c.description && <div style={{color:'#555',fontSize:12,marginTop:2}}>{c.description}</div>}
                      <div style={{color:'#888',fontSize:11,marginTop:3}}>
                        {c.collection} · Created {new Date(c.created_at).toLocaleDateString()}
                      </div>
                    </div>
                    <div style={{display:'flex',gap:8,alignItems:'center'}}>
                      <button onClick={e=>{e.stopPropagation();handleSelectCase(c)}}
                        style={{padding:'6px 14px',borderRadius:8,border:'2px solid rgba(0,0,0,0.2)',background:'#ffd400',color:'#000',cursor:'pointer',fontSize:13,fontWeight:600}}>
                        Open
                      </button>
                      <button onClick={e=>{e.stopPropagation();handleDeleteCase(c.id)}}
                        style={{padding:'6px 10px',borderRadius:8,border:'1px solid #b10000',background:'transparent',color:'#b10000',cursor:'pointer',fontSize:12}}>
                        ✕
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">

      {/* ── Sign Out Confirmation Dialog ─────────────────────────────────── */}
      {showSignOutDialog && (
        <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.6)',zIndex:9999,display:'flex',alignItems:'center',justifyContent:'center'}}>
          <div style={{background:'#fff',borderRadius:14,width:400,boxShadow:'0 16px 48px rgba(0,0,0,0.4)',border:'3px solid #b10000',overflow:'hidden'}}>
            <div style={{background:'#ffd400',padding:'16px 24px',borderBottom:'3px solid #b10000'}}>
              <div style={{fontSize:17,fontWeight:700,color:'#0b2c4a'}}>Sign Out</div>
            </div>
            <div style={{padding:'24px'}}>
              {(docIndexing || graphExtracting) && (
                <div style={{background:'#fff3cd',border:'1px solid #e6a817',borderRadius:8,padding:'10px 14px',marginBottom:12,fontSize:13,color:'#7d4e00',fontWeight:600}}>
                  ⚠ {docIndexing ? 'Document indexing' : 'Entity extraction'} is in progress. Please wait for it to finish before signing out.
                </div>
              )}
              <div style={{color:'#333',fontSize:14,marginBottom:20,lineHeight:1.6}}>
                Are you sure you want to sign out?
              </div>
              <div style={{display:'flex',flexDirection:'column',gap:10}}>
                <button onClick={handleLogout}
                  disabled={docIndexing || graphExtracting}
                  style={{padding:'11px 0',borderRadius:8,border:'2px solid rgba(0,0,0,0.2)',background: docIndexing || graphExtracting ? '#ccc':'#ffd400',color:'#000',fontWeight:700,fontSize:14,cursor: docIndexing || graphExtracting ? 'not-allowed':'pointer'}}>
                  Sign Out
                </button>
                <button onClick={()=>setShowSignOutDialog(false)}
                  style={{padding:'11px 0',borderRadius:8,border:'1px solid #ccc',background:'transparent',color:'#555',fontWeight:600,fontSize:14,cursor:'pointer'}}>
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <aside className="sidebar">
        <div className="sidebar-logo">
          <img src={kspLogo} alt="KSP" />
        </div>
        <button type="button" className="btn-yellow" onClick={() => setDocChat([])}>
          Clear Document Chat
        </button>
        {/* Clear Uploaded Docs — disabled to prevent accidental data loss */}
      </aside>

      <main className="main">
        <div className="banner-wrapper">
          <img src={bannerLogo} alt="ISD-AI Logo" className="ksp-banner-img" />
          <header className="ksp-banner">
            <div className="ksp-banner-left">
              <h1 className="ksp-title">ISD-AI</h1>
              <p className="ksp-tagline">empowering law enforcement with artificial intelligence</p>
            </div>
          </header>
        </div>

        {/* Case + User bar */}
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'7px 16px',background:'#0b2c4a',borderBottom:'3px solid #ffd400'}}>
          <div style={{display:'flex',alignItems:'center',gap:10}}>
            <span style={{color:'#ffd400',fontSize:12,fontWeight:600}}>Case:</span>
            <span style={{color:'#fff',fontWeight:700,fontSize:13}}>{activeCase.name}</span>
            <span style={{background:'#ffd400',color:'#0b2c4a',fontWeight:700,fontSize:11,borderRadius:4,padding:'1px 7px'}}>{activeCase.collection}</span>
          </div>
          <div style={{display:'flex',alignItems:'center',gap:10}}>
            <span style={{color:'#e0e0e0',fontSize:12,fontWeight:500}}>{currentUser?.username}</span>
            <button onClick={()=>setActiveCase(null)}
              style={{padding:'4px 12px',borderRadius:6,border:'2px solid #ffd400',background:'transparent',color:'#ffd400',cursor:'pointer',fontSize:12,fontWeight:600}}>
              Switch Case
            </button>
            <button
              onClick={handleSignOutRequest}
              disabled={docIndexing || graphExtracting}
              title={docIndexing ? 'Indexing in progress — please wait before signing out' : graphExtracting ? 'Entity extraction in progress — please wait before signing out' : ''}
              style={{padding:'4px 12px',borderRadius:6,border:'2px solid #b10000',background: docIndexing || graphExtracting ? '#666' : '#b10000',color:'#ffd400',cursor: docIndexing || graphExtracting ? 'not-allowed' : 'pointer',fontSize:12,fontWeight:700,opacity: docIndexing || graphExtracting ? 0.6 : 1}}>
              {docIndexing ? 'Indexing...' : graphExtracting ? 'Extracting...' : 'Sign Out'}
            </button>
          </div>
        </div>

        <nav className="tabs">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              className={`tab${activeTab === tab ? ' active' : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </nav>

        {activeTab === 'Document Intelligence' && (
        <div className="main-panel">
          <section className="ksp-card">
            <div className="two-col">
              <div>
                <span className="ksp-chip ksp-chip-navy">Upload &amp; Index</span>
                {lastIndexSummary && (
                  <span className="index-summary">
                    {lastIndexSummary.count} document{lastIndexSummary.count !== 1 ? 's' : ''} indexed in {lastIndexSummary.seconds}s
                  </span>
                )}
                {!lastIndexSummary && docs.length > 0 && (
                  <span className="index-summary">
                    {docs.length} document{docs.length !== 1 ? 's' : ''} indexed
                  </span>
                )}
                <div className="upload-row">
                  <select
                    className="collection-select"
                    value={activeCollection}
                    onChange={(e) => setActiveCollection(e.target.value as 'SMAC' | 'IR')}
                    title="Select document collection"
                  >
                    <option value="SMAC">SMAC</option>
                    <option value="IR">IR</option>
                  </select>
                  <button
                    type="button"
                    className="btn-yellow"
                    onClick={() => fileInputRef.current?.click()}
                    title="Select one or more files to index"
                  >
                    Choose Files
                  </button>
                  <button
                    type="button"
                    className="btn-yellow"
                    onClick={() => folderInputRef.current?.click()}
                    title="Select a folder to index all documents inside it (including subfolders)"
                  >
                    Select Folder
                  </button>
                  <button
                    type="button"
                    className="btn-yellow"
                    onClick={handleDocIndex}
                    disabled={docIndexing || docLoading || docFiles.length === 0}
                    title={docFiles.length === 0 ? 'Select files first' : ''}
                  >
                    {docIndexing ? 'Indexing...' : 'Index Documents'}
                  </button>
                  <input
                    ref={fileInputRef}
                    className="hidden-input"
                    type="file"
                    multiple
                    accept=".pdf,.docx,.doc,.xlsx,.csv"
                    onChange={(event) => {
                      const fl = event.target.files
                      setDocFiles(fl ? Array.from(fl) : [])
                    }}
                  />
                  <input
                    ref={folderInputRef}
                    className="hidden-input"
                    type="file"
                    {...{ webkitdirectory: '', directory: '' } as React.InputHTMLAttributes<HTMLInputElement>}
                    onChange={(event) => {
                      const fl = event.target.files
                      if (!fl || fl.length === 0) return
                      const supported = ['.pdf', '.docx', '.doc', '.xlsx', '.csv']
                      const filtered = Array.from(fl).filter((f) => {
                        const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase()
                        return supported.includes(ext)
                      })
                      if (filtered.length === 0) {
                        setDocLastError('No supported files (PDF/DOCX/DOC/XLSX/CSV) found in selected folder.')
                        return
                      }
                      setDocFiles(filtered)
                      setDocStatus(`Selected ${filtered.length} document(s) from folder (out of ${fl.length} total files).`)
                    }}
                  />
                </div>
                {docFiles.length > 0 && !docIndexing && (
                  <div className="selected-files-info">
                    {docFiles.length} file(s) selected
                    {docFiles.length <= 10
                      ? ': ' + docFiles.map((f) => f.name).join(', ')
                      : `: ${docFiles.slice(0, 5).map((f) => f.name).join(', ')} ... and ${docFiles.length - 5} more`
                    }
                  </div>
                )}
                {indexProgress && (() => {
                  const pct = Math.round((indexProgress.current / indexProgress.total) * 100)
                  const barWidth = Math.max(pct, 8)
                  return (
                    <div className="index-progress-wrapper">
                      <div className="index-progress-bar">
                        <div
                          className="index-progress-fill"
                          style={{ width: `${barWidth}%` }}
                        />
                      </div>
                      <div className="index-progress-text">
                        {pct < 100
                          ? `Processing: ${indexProgress.fileName} — ${indexProgress.current}/${indexProgress.total} files — ${pct}% — ${elapsedSeconds}s elapsed`
                          : `Done — ${indexProgress.total} file(s) — ${elapsedSeconds}s`
                        }
                      </div>
                    </div>
                  )
                })()}
                <div className="ask-header">
                  <span className="ksp-chip ksp-chip-spaced ksp-chip-navy">Ask</span>
                  <button
                    type="button"
                    className="help-btn"
                    onClick={() => setShowQueryHelp(prev => !prev)}
                    title="How to write questions"
                  >
                    ?
                  </button>
                </div>
                {showQueryHelp && (
                  <div className="help-popover">
                    <strong>How to ask questions</strong>
                    <ul>
                      <li>Be specific &mdash; <em>&quot;Who are the associates?&quot;</em> works better than <em>&quot;Tell me about the document&quot;</em></li>
                      <li>Use names and keywords from the document &mdash; names of people, places, dates</li>
                      <li>Ask one question at a time for the most accurate answers</li>
                      <li>Spell-check your question &mdash; misspelled words may lead to poor results</li>
                    </ul>
                    <strong>Example questions</strong>
                    <ul>
                      <li><em>&quot;What is the date of arrest?&quot;</em></li>
                      <li><em>&quot;List all weapons and hideouts&quot;</em></li>
                      <li><em>&quot;Who are the family members?&quot;</em></li>
                      <li><em>&quot;What criminal cases are registered?&quot;</em></li>
                    </ul>
                  </div>
                )}
                <textarea
                  className="ksp-textarea"
                  value={docQuestion}
                  onChange={(event) => setDocQuestion(event.target.value)}
                  placeholder="Type your question here, e.g. 'Who are the associates?' or 'List all weapons found'"
                  spellCheck={true}
                  lang="en"
                />
                {spellCorrections && Object.keys(spellCorrections).length > 0 && (
                  <div className="spell-banner">
                    <span className="spell-banner-title">Possible spelling errors detected:</span>
                    <div className="spell-corrections">
                      {Object.entries(spellCorrections).map(([wrong, right]) => (
                        <span key={wrong} className="spell-item">
                          <span className="spell-wrong">{wrong}</span> &rarr; <span className="spell-right">{right}</span>
                        </span>
                      ))}
                    </div>
                    <div className="spell-actions">
                      <button type="button" className="btn-spell-fix" onClick={handleSpellFix}>Fix &amp; Ask</button>
                      <button type="button" className="btn-spell-ignore" onClick={handleSpellIgnore}>Ask Anyway</button>
                    </div>
                  </div>
                )}
                {audioDevices.length > 1 && (
                  <div className="mic-selector">
                    <label htmlFor="mic-select">Microphone: </label>
                    <select
                      id="mic-select"
                      value={selectedDeviceId}
                      onChange={(e) => setSelectedDeviceId(e.target.value)}
                      disabled={isRecording}
                    >
                      {audioDevices.map((d) => (
                        <option key={d.deviceId} value={d.deviceId}>
                          {d.label || `Mic ${d.deviceId.slice(0, 8)}`}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="normal-btn voice-btn-row">
                  <button
                    type="button"
                    className={docs.length ? 'btn-ask btn-ask-active' : 'btn-ask'}
                    onClick={handleDocAsk}
                    disabled={docLoading || docIndexing || !docs.length}
                    title={!docs.length ? 'Index documents first' : ''}
                  >
                    {docLoading ? 'Searching...' : 'Ask Question'}
                  </button>
                  {docLoading && (
                    <button type="button" className="btn-stop" onClick={handleDocStop} title="Stop query">
                      Stop
                    </button>
                  )}
                  <button
                    type="button"
                    className={`voice-btn${isRecording ? ' recording' : ''}`}
                    onClick={handleVoiceToggle}
                    disabled={(docLoading || docIndexing) && !isRecording}
                    title={isRecording ? 'Stop recording' : 'Ask with voice'}
                  >
                    {isRecording ? '\u23F9' : '\uD83C\uDFA4'}
                  </button>
                  {isRecording && (
                    <div className="mic-level-container" title={`Mic level: ${Math.round(micLevel * 100)}%`}>
                      <div className="mic-level-bar" style={{ width: `${Math.max(micLevel * 100, 2)}%` }} />
                      <span className="mic-level-text">{Math.round(micLevel * 100)}%</span>
                    </div>
                  )}
                </div>
                {voiceStatus && <div className="voice-status">{voiceStatus}</div>}
                {isRecording && micLevel < 0.01 && (
                  <div className="status warning">
                    No audio detected! Check if the correct microphone is selected and not muted in Windows Sound Settings.
                  </div>
                )}
                <details className="history">
                  <summary>Conversation History</summary>
                  {docChat.length > 0 && (
                    <div className="history-actions">
                      <button type="button" className="btn-navy-compact" onClick={() => downloadChatAsPdf(docChat, 'Document Intelligence')}>
                        Download PDF
                      </button>
                      <button type="button" className="btn-navy-compact" style={{ marginLeft: 6 }} onClick={() => { setDocChat([]); setDocLastAnswer(''); setDocLastError(''); setDocStatus('') }}>
                        Clear History
                      </button>
                    </div>
                  )}
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
              </div>
              <div>
                <span className="ksp-chip ksp-chip-navy">Answer</span>
                <div className="ksp-result answer-panel">
                  {docStatus && <div className="status success">{docStatus}</div>}
                  {docLastError && <div className="status warning">{docLastError}</div>}

                  {docLastAnswer ? (
                    <>
                      <p className="result-title">
                        Answer:
                        {isSpeaking ? (
                          <span className="tts-controls">
                            <button
                              type="button"
                              className="tts-ctrl-btn tts-pause"
                              onClick={() => isPaused ? resumeSpeaking() : pauseSpeaking()}
                              title={isPaused ? 'Resume narration' : 'Pause narration'}
                            >
                              {isPaused ? '\u25B6' : '\u23F8'}
                            </button>
                            <button
                              type="button"
                              className="tts-ctrl-btn tts-stop"
                              onClick={stopSpeaking}
                              title="Stop narration"
                            >
                              {'\u23F9'}
                            </button>
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="voice-btn voice-btn-sm"
                            onClick={() => speakText(docLastAnswer)}
                            title="Read answer aloud"
                          >
                            {'\uD83D\uDD0A'}
                          </button>
                        )}
                      </p>
                      <div className="doc-answer-text">{docLastAnswer}</div>
                      <div className="rating-bar">
                        <span className="rating-label">Rate this answer:</span>
                        {[2, 1, 0, -1, -2].map((r) => (
                          <button
                            key={r}
                            type="button"
                            className={`rating-btn ${lastRating === r ? 'rating-active' : ''} ${r >= 1 ? 'rating-positive' : r === 0 ? 'rating-neutral' : 'rating-negative'}`}
                            onClick={() => handleRating(r)}
                            disabled={ratingSubmitting || lastRating !== null}
                            title={r === 2 ? 'Excellent' : r === 1 ? 'Good' : r === 0 ? 'Neutral' : r === -1 ? 'Poor' : 'Wrong'}
                          >
                            {r === 2 ? '+2' : r === 1 ? '+1' : r === 0 ? '0' : r === -1 ? '-1' : '-2'}
                          </button>
                        ))}
                        {lastRating !== null && <span className="rating-thanks">Thanks for your feedback!</span>}
                      </div>
                    </>
                  ) : (
                    <p>Answers will appear here after you ask a question.</p>
                  )}
                </div>

                <span className="ksp-chip ksp-chip-spaced ksp-chip-navy">Indexed Documents</span>
                <div className="ksp-result doc-list-panel">
                  {docs.length ? (
                    <ul className="doc-list">
                      {docs.map((doc, idx) => (
                        <li key={`doc-${idx}`}>{doc.doc_name || 'Unknown'}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>No documents indexed yet.</p>
                  )}
                </div>

                {failedDocs.length > 0 && (
                  <>
                    <span className="ksp-chip ksp-chip-spaced ksp-chip-error">Failed Documents ({failedDocs.length})</span>
                    <div className="ksp-result doc-list-panel failed-docs-panel">
                      <ul className="doc-list">
                        {failedDocs.map((f, idx) => (
                          <li key={`fail-${idx}`}>
                            <strong>{f.name}</strong> — {f.error}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </>
                )}
              </div>
            </div>
          </section>
        </div>
        )}

        {activeTab === 'Connections Map' && (
        <div className="main-panel">
          <section className="ksp-card">
            {/* ── View toggle ── */}
            <div className="connections-view-toggle">
              <button
                type="button"
                className={`connections-view-btn${connectionsView === 'graph' ? ' active' : ''}`}
                onClick={() => setConnectionsView('graph')}
              >
                Entity Graph
              </button>
              <button
                type="button"
                className={`connections-view-btn${connectionsView === 'map' ? ' active' : ''}`}
                onClick={() => setConnectionsView('map')}
              >
                Location Map
              </button>
            </div>

            {/* ── Entity Graph (hidden in map view via CSS — keeps ForceGraph2D mounted) ── */}
            <div style={{ display: connectionsView === 'graph' ? '' : 'none' }}>
            <div className="graph-controls">
              <div className="graph-search-row">
                <input
                  type="text"
                  className="graph-search-input"
                  placeholder="Search entities..."
                  value={graphSearch}
                  onChange={(e) => setGraphSearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && extractionDone && handleGraphSearch()}
                  disabled={!extractionDone || graphExtracting}
                />
                <button
                  type="button"
                  className="btn-yellow"
                  onClick={handleGraphSearch}
                  disabled={!extractionDone || graphExtracting}
                >
                  Search
                </button>
                <button
                  type="button"
                  className="btn-yellow"
                  onClick={handleExtractAll}
                  disabled={extractionDone || graphExtracting}
                  title="Extract entities from all indexed documents"
                >
                  {graphExtracting ? 'Extracting...' : 'Extract Entities'}
                </button>
                <button
                  type="button"
                  className="btn-red"
                  onClick={handleClearGraph}
                  disabled={graphExtracting}
                  title="Clear all graph data (entities and relationships)"
                >
                  Clear Graph
                </button>
              </div>
              {graphStatus && (
                <div className={`status ${extractionDone ? 'success' : 'warning'}`}>
                  {graphStatus}
                </div>
              )}

              <div className="graph-filters">
                {Object.keys(ENTITY_COLORS).map((type) => (
                  <label key={type} className="graph-filter-label">
                    <input
                      type="checkbox"
                      checked={graphTypeFilters[type] !== false}
                      onChange={() => toggleTypeFilter(type)}
                    />
                    <span
                      className="graph-filter-dot"
                      style={{ backgroundColor: ENTITY_COLORS[type] }}
                    />
                    {type}
                  </label>
                ))}
              </div>
            </div>

            <div className="graph-stats">
              {filteredGraphData.nodes.length} entities, {filteredGraphData.links.length} relationships
              {graphLoading && ' — Loading...'}
            </div>

            <div className="graph-container">
              {filteredGraphData.nodes.length > 0 ? (
                <ForceGraph2D
                  ref={graphRef}
                  graphData={filteredGraphData}
                  nodeId="id"
                  nodeCanvasObject={nodeCanvasObject}
                  nodeLabel={getNodeTooltip}
                  nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
                    const radius = Math.max(3, Math.min(10, 2 + ((node.weight as number) || 1) * 1.5))
                    ctx.beginPath()
                    ctx.arc(node.x, node.y, radius + 4, 0, 2 * Math.PI)
                    ctx.fillStyle = color
                    ctx.fill()
                  }}
                  linkColor={(link: any) => {
                    const rtype = link.type as string
                    if (rtype === 'CO_OCCURRENCE') return 'rgba(255,255,255,0.04)'
                    const c = RELATIONSHIP_COLORS[rtype] || 'rgba(255,255,255,0.2)'
                    return c
                  }}
                  linkWidth={(link: any) => link.type === 'CO_OCCURRENCE' ? 0.3 : 0.8}
                  linkLabel={(link: any) => {
                    const types = (link.types as string[] || [link.type]).filter((t: string) => t !== 'CO_OCCURRENCE')
                    const label = types.length > 0 ? types.join(', ') : link.type
                    const ctx = link.context ? `\n${link.context}` : ''
                    return `${label}${ctx}`
                  }}
                  linkDirectionalParticles={(link: any) => link.type !== 'CO_OCCURRENCE' ? 1 : 0}
                  linkDirectionalParticleWidth={1.5}
                  linkDirectionalParticleSpeed={0.005}
                  onNodeClick={(node: any) => setSelectedNode(node as GraphNode)}
                  onNodeHover={(node: any) => setHoveredNode(node ? node.id : null)}
                  d3AlphaDecay={0.02}
                  d3VelocityDecay={0.3}
                  backgroundColor="#0d1117"
                  width={undefined}
                  height={650}
                  cooldownTicks={200}
                  warmupTicks={50}
                />
              ) : (
                <div className="graph-empty">
                  {graphLoading
                    ? 'Loading graph data...'
                    : 'No entities found. Index documents first, then click "Extract Entities" and wait for extraction to complete.'}
                </div>
              )}
            </div>

            {selectedNode && (() => {
              // Find all relationships connected to this node
              const nodeId = selectedNode.id
              const connectedEdges = graphEdges.filter((e) => {
                const srcId = typeof e.source === 'object' ? e.source.id : e.source
                const tgtId = typeof e.target === 'object' ? e.target.id : e.target
                return srcId === nodeId || tgtId === nodeId
              }).filter((e) => e.type !== 'CO_OCCURRENCE' || (e.types && e.types.some((t) => t !== 'CO_OCCURRENCE')))

              return (
                <div className="graph-detail-panel">
                  <div className="graph-detail-header">
                    <span
                      className="graph-detail-type-badge"
                      style={{ backgroundColor: ENTITY_COLORS[selectedNode.type] || ENTITY_COLORS.OTHER }}
                    >
                      {selectedNode.type}
                    </span>
                    <strong>{selectedNode.name}</strong>
                    <button
                      type="button"
                      className="graph-detail-close"
                      onClick={() => setSelectedNode(null)}
                    >
                      x
                    </button>
                  </div>
                  <div className="graph-detail-body">
                    <p><strong>Mentioned in:</strong> {selectedNode.doc_names || 'Unknown'}</p>
                    <p><strong>Mentions:</strong> {selectedNode.weight} document(s)</p>
                    {selectedNode.contexts && (
                      <p><strong>Context:</strong> {selectedNode.contexts}</p>
                    )}
                    {connectedEdges.length > 0 && (
                      <div className="graph-detail-relationships">
                        <p><strong>Relationships ({connectedEdges.length}):</strong></p>
                        <ul className="graph-rel-list">
                          {connectedEdges.map((edge, idx) => {
                            const srcNode = typeof edge.source === 'object' ? edge.source : graphNodes.find((n) => n.id === edge.source)
                            const tgtNode = typeof edge.target === 'object' ? edge.target : graphNodes.find((n) => n.id === edge.target)
                            const otherNode = srcNode?.id === nodeId ? tgtNode : srcNode
                            const types = (edge.types || [edge.type]).filter((t) => t !== 'CO_OCCURRENCE')
                            if (types.length === 0) return null
                            return (
                              <li key={idx} className="graph-rel-item">
                                <span
                                  className="graph-rel-type"
                                  style={{ color: RELATIONSHIP_COLORS[types[0]] || '#aaa' }}
                                >
                                  {types.join(', ').replace(/_/g, ' ')}
                                </span>
                                {' '}
                                <strong>{otherNode?.name || '?'}</strong>
                                {edge.context && (
                                  <span className="graph-rel-context"> - {edge.context}</span>
                                )}
                              </li>
                            )
                          })}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )
            })()}
            </div> {/* end graph view wrapper */}

            {/* ── Location Map View ── */}
            <div className="location-map-section" style={{ display: connectionsView === 'map' ? '' : 'none' }}>
              <div className="location-map-controls">
                <button
                  type="button"
                  className="btn-yellow"
                  onClick={handleLocationExtract}
                  disabled={locationExtracting}
                  title="Extract addresses from IR documents and plot on map (incremental)"
                >
                  {locationExtracting ? 'Extracting...' : 'Extract Locations'}
                </button>
                <span className="location-map-note">IR collection only — uses bundled India geocoding</span>
              </div>
              {locationStatus && (
                <div className={`status ${locationExtractionDone ? 'success' : 'warning'}`}>
                  {locationStatus}
                </div>
              )}

              {/* Legend */}
              <div className="location-legend">
                <span className="location-legend-title">Address type:</span>
                {Object.entries(ADDR_TYPE_COLORS).map(([type, color]) => (
                  <span key={type} className="location-legend-item">
                    <span className="location-legend-dot" style={{ backgroundColor: color }} />
                    {type}
                  </span>
                ))}
              </div>

              <div className="location-map-stats">
                {locationData.length} location{locationData.length !== 1 ? 's' : ''} plotted
                {locationLoading && ' — Loading...'}
              </div>

              {/* Map container */}
              <div className="location-map-container">
                {locationData.length > 0 ? (
                  <>
                    <ComposableMap
                      projection="geoMercator"
                      projectionConfig={{ center: [82, 22], scale: 1000 }}
                      width={900}
                      height={580}
                      style={{ width: '100%', height: '100%' }}
                    >
                      <ZoomableGroup center={[82, 22]} zoom={1} minZoom={0.5} maxZoom={12}>
                        <Geographies geography="/geo/countries-110m.json">
                          {({ geographies }: { geographies: any[] }) =>
                            geographies.map((geo) => (
                              <Geography
                                key={geo.rsmKey}
                                geography={geo}
                                fill="#1a3a5c"
                                stroke="#2d5986"
                                strokeWidth={0.5}
                                style={{
                                  default: { outline: 'none' },
                                  hover: { fill: '#1e4570', outline: 'none' },
                                  pressed: { outline: 'none' },
                                }}
                              />
                            ))
                          }
                        </Geographies>
                        {locationData.map((loc) => (
                          <Marker
                            key={loc.id}
                            coordinates={[loc.lng, loc.lat]}
                            onClick={() => setSelectedLocation(loc.id === selectedLocation?.id ? null : loc)}
                          >
                            <circle
                              r={selectedLocation?.id === loc.id ? 7 : 5}
                              fill={ADDR_TYPE_COLORS[loc.address_type] || ADDR_TYPE_COLORS.OTHER}
                              stroke={selectedLocation?.id === loc.id ? '#FFD700' : '#fff'}
                              strokeWidth={selectedLocation?.id === loc.id ? 2 : 1}
                              style={{ cursor: 'pointer', opacity: 0.9 }}
                            />
                            <title>{loc.person_name || 'Unknown'} — {loc.city}{loc.locality ? ', ' + loc.locality : ''} ({loc.address_type})</title>
                          </Marker>
                        ))}
                      </ZoomableGroup>
                    </ComposableMap>
                    <div className="location-map-hint">Scroll to zoom · Drag to pan · Click pin for details</div>
                  </>
                ) : (
                  <div className="location-map-empty">
                    {locationLoading
                      ? 'Loading location data...'
                      : 'No locations found. Index IR documents first, then click "Extract Locations".'}
                  </div>
                )}
              </div>

              {/* Selected location detail panel */}
              {selectedLocation && (
                <div className="location-detail-panel">
                  <div className="location-detail-header">
                    <span
                      className="location-addr-type-badge"
                      style={{ backgroundColor: ADDR_TYPE_COLORS[selectedLocation.address_type] || '#9E9E9E' }}
                    >
                      {selectedLocation.address_type}
                    </span>
                    <strong>{selectedLocation.person_name || 'Unknown Person'}</strong>
                    <button
                      type="button"
                      className="location-detail-close"
                      onClick={() => setSelectedLocation(null)}
                    >
                      x
                    </button>
                  </div>
                  <div className="location-detail-grid">
                    <p><strong>Document:</strong> {selectedLocation.doc_name}</p>
                    <p><strong>City:</strong> {selectedLocation.city}{selectedLocation.locality ? ` — ${selectedLocation.locality}` : ''}</p>
                    <p><strong>Coordinates:</strong> {selectedLocation.lat.toFixed(4)}, {selectedLocation.lng.toFixed(4)}</p>
                    {selectedLocation.address_text && (
                      <div className="location-detail-address">
                        <strong>Address:</strong> {selectedLocation.address_text}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>
        )}

        {activeTab === 'Activity Timeline' && (
        <div className="main-panel">
          <section className="ksp-card">
            <div className="timeline-controls">
              <div className="timeline-search-row">
                <input
                  type="text"
                  className="timeline-search-input"
                  placeholder="Search activities..."
                  value={timelineSearch}
                  onChange={(e) => setTimelineSearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && timelineExtractionDone && handleTimelineSearch()}
                  disabled={!timelineExtractionDone || timelineExtracting}
                />
                <button
                  type="button"
                  className="btn-yellow"
                  onClick={handleTimelineSearch}
                  disabled={!timelineExtractionDone || timelineExtracting}
                >
                  Search
                </button>
                <button
                  type="button"
                  className="btn-yellow"
                  onClick={handleTimelineExtract}
                  disabled={timelineExtracting}
                  title="Extract activities from indexed documents (incremental — skips already-extracted docs)"
                >
                  {timelineExtracting ? 'Extracting...' : 'Extract Activities'}
                </button>
              </div>
              {timelineStatus && (
                <div className={`status ${timelineExtractionDone ? 'success' : 'warning'}`}>
                  {timelineStatus}
                </div>
              )}
            </div>

            <div className="timeline-layout">
              {/* ── Left sidebar: groups + status filters ── */}
              {timelineGroups.length > 0 && (
                <aside className="timeline-sidebar">
                  <div className="timeline-sidebar-section">
                    <div className="timeline-sidebar-heading">Groups</div>
                    <div className="timeline-group-list">
                      {timelineGroups.map((g) => (
                        <label key={g.group_name} className="timeline-group-label">
                          <input
                            type="checkbox"
                            checked={timelineGroupFilter[g.group_name] !== false}
                            onChange={() => setTimelineGroupFilter((prev) => ({
                              ...prev,
                              [g.group_name]: !prev[g.group_name],
                            }))}
                          />
                          <span
                            className="timeline-group-dot"
                            style={{ backgroundColor: getGroupColor(g.group_name) }}
                          />
                          <span className="timeline-group-name">{g.group_name}</span>
                          <span className="timeline-group-count">{g.count}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="timeline-sidebar-stats">
                    {filteredTimelineActivities.length} activities
                    {timelineGroups.length > 0 && ` across ${timelineGroups.length} groups`}
                  </div>
                </aside>
              )}

              {/* ── Right: timeline ── */}
              <div className="timeline-main">
                <div className="timeline-header-bar">
                  <div className="timeline-stats">
                    <span className="timeline-stats-count">{filteredTimelineActivities.length}</span> activities
                    {timelineGroups.length > 0 && (
                      <> across <span className="timeline-stats-count">{timelineGroups.length}</span> groups</>
                    )}
                    {timelineLoading && ' — Loading...'}
                  </div>
                  <div className="timeline-status-pills">
                    <button
                      type="button"
                      className={`timeline-status-pill${timelineStatusFilter === null ? ' active' : ''}`}
                      onClick={() => {
                        setTimelineStatusFilter(null)
                        loadTimelineData(
                          timelineSearch.trim() || undefined,
                          undefined,
                          undefined,
                        )
                      }}
                    >
                      ALL
                    </button>
                    {['PAST', 'CURRENT', 'FUTURE'].map((s) => (
                      <button
                        key={s}
                        type="button"
                        className={`timeline-status-pill${timelineStatusFilter === s ? ' active' : ''}`}
                        onClick={() => {
                          const newFilter = timelineStatusFilter === s ? null : s
                          setTimelineStatusFilter(newFilter)
                          loadTimelineData(
                            timelineSearch.trim() || undefined,
                            undefined,
                            newFilter || undefined,
                          )
                        }}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>

                {filteredTimelineActivities.length > 0 ? (
                  <div className="timeline-container">
                    <div className="timeline-line" />
                    {filteredTimelineActivities.map((activity) => {
                      const isExpanded = expandedActivity === activity.id
                      const groupColor = getGroupColor(activity.group_name || 'Unknown')
                      return (
                        <div key={activity.id} className="timeline-item">
                          <div className="timeline-dot" style={{ backgroundColor: groupColor }} />
                          <div
                            className={`timeline-card${isExpanded ? ' expanded' : ''}`}
                            style={{ borderLeftColor: groupColor }}
                            onClick={() => handleActivityClick(activity)}
                          >
                            <div className="timeline-card-header">
                              {activity.activity_date && (
                                <span className="timeline-date">{activity.activity_date}</span>
                              )}
                              {activity.group_name && (
                                <span className="timeline-group-tag" style={{ backgroundColor: groupColor }}>
                                  {activity.group_name}
                                </span>
                              )}
                              <span className={`timeline-status-badge ${activity.temporal_status.toLowerCase()}`}>
                                {activity.temporal_status}
                              </span>
                              {activity.priority && (
                                <span className="timeline-priority-badge">{activity.priority}</span>
                              )}
                            </div>
                            <div className="timeline-subject">{activity.subject || 'Untitled Activity'}</div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              {activity.tms_id && (
                                <span className="timeline-tms-id">{activity.tms_id}</span>
                              )}
                              {activity.xref_count > 0 && (
                                <span className="timeline-tms-id" style={{ color: '#1565c0' }}>
                                  {activity.xref_count} cross-ref{activity.xref_count !== 1 ? 's' : ''}
                                </span>
                              )}
                            </div>
                            {activity.participants && (
                              <div className="timeline-participants">
                                {activity.participants.length > 100
                                  ? activity.participants.slice(0, 100) + '...'
                                  : activity.participants}
                              </div>
                            )}

                            {isExpanded && (
                              <>
                                {activity.description && (
                                  <div className="timeline-description">{activity.description}</div>
                                )}

                                {activity.tms_id && activity.xref_count > 0 && (
                                  <div className="timeline-breadcrumb">
                                    <div className="timeline-breadcrumb-title">Bread Crumb Trail</div>
                                    {breadcrumbLoading ? (
                                      <div style={{ fontSize: 13, color: '#888' }}>Loading trail...</div>
                                    ) : breadcrumbTrail && breadcrumbTrail.trail.length > 0 ? (
                                      <div className="timeline-breadcrumb-chain">
                                        {[...breadcrumbTrail.trail, ...(breadcrumbTrail.main ? [breadcrumbTrail.main] : [])]
                                          .sort((a, b) => (a.activity_date || '').localeCompare(b.activity_date || ''))
                                          .map((item, idx) => {
                                            const isCurrent = item.tms_id === activity.tms_id
                                            const ref = breadcrumbTrail.references.find(
                                              (r) =>
                                                (r.source_tms_id === activity.tms_id && r.target_tms_id === item.tms_id) ||
                                                (r.target_tms_id === activity.tms_id && r.source_tms_id === item.tms_id)
                                            )
                                            return (
                                              <div key={item.tms_id || idx}>
                                                {idx > 0 && (
                                                  <div className="timeline-breadcrumb-arrow">|</div>
                                                )}
                                                <div
                                                  className={`timeline-breadcrumb-item${isCurrent ? ' current-item' : ''}`}
                                                  onClick={(e) => {
                                                    e.stopPropagation()
                                                    if (!isCurrent) {
                                                      const target = timelineActivities.find((a) => a.tms_id === item.tms_id)
                                                      if (target) handleActivityClick(target)
                                                    }
                                                  }}
                                                >
                                                  <span className="timeline-breadcrumb-tms">{item.tms_id}</span>
                                                  <span className="timeline-breadcrumb-subject">
                                                    {item.subject || 'Unknown'}
                                                  </span>
                                                  <span className="timeline-breadcrumb-date">
                                                    {item.activity_date || ''}
                                                  </span>
                                                </div>
                                                {ref && ref.context && !isCurrent && (
                                                  <div className="timeline-breadcrumb-context">
                                                    {ref.context}
                                                  </div>
                                                )}
                                              </div>
                                            )
                                          })}
                                      </div>
                                    ) : (
                                      !breadcrumbLoading && (
                                        <div style={{ fontSize: 13, color: '#888' }}>
                                          No linked activities found.
                                        </div>
                                      )
                                    )}
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <div className="timeline-empty">
                    {timelineLoading
                      ? 'Loading timeline data...'
                      : 'No activities found. Index documents first, then click "Extract Activities" and wait for extraction to complete.'}
                  </div>
                )}
              </div>
            </div>
          </section>
        </div>
        )}

        {activeTab === 'QA Testing' && (
        <div className="main-panel">
          <section className="ksp-card">
            <span className="ksp-chip ksp-chip-navy">QA Testing Agent</span>
            <p className="main-help">
              Upload a PDF or Word file containing test prompts, select which indexed documents to query against,
              and run all prompts in batch to validate data accuracy.
            </p>

            {/* Upload & Collection Row */}
            <div className="qa-upload-row">
              <input
                ref={qaFileInputRef}
                type="file"
                accept=".pdf,.docx,.doc"
                className="hidden-input"
                onChange={(e) => {
                  const f = e.target.files?.[0] || null
                  setQaFile(f)
                  if (f) setQaStatus(`Selected: ${f.name}`)
                }}
              />
              <button
                type="button"
                className="btn-folder"
                onClick={() => qaFileInputRef.current?.click()}
              >
                Choose Prompt File
              </button>
              {qaFile && (
                <span style={{ fontSize: 13, color: '#555' }}>{qaFile.name}</span>
              )}
              <button
                type="button"
                className="btn-index"
                onClick={handleQaUpload}
                disabled={!qaFile || qaRunning}
              >
                Upload &amp; Extract
              </button>
              <select
                className="qa-collection-select"
                value={qaCollection}
                onChange={(e) => {
                  setQaCollection(e.target.value as 'SMAC' | 'IR')
                  setQaSelectedDocs([])
                }}
              >
                <option value="SMAC">SMAC</option>
                <option value="IR">IR</option>
              </select>
            </div>

            {/* Extracted Prompts Summary */}
            {qaPrompts.length > 0 && (
              <div className="qa-prompts-summary">
                {qaPrompts.length} prompt(s) extracted
              </div>
            )}

            {/* Document Selector */}
            {qaDocs.length > 0 && qaPrompts.length > 0 && (
              <div className="qa-doc-selector">
                <div className="qa-doc-select-actions">
                  <strong style={{ fontSize: 13, marginRight: 8 }}>Test against:</strong>
                  <button type="button" onClick={() => setQaSelectedDocs(qaDocs.map((d) => d.doc_id as string).filter(Boolean))}>
                    Select All
                  </button>
                  <button type="button" onClick={() => setQaSelectedDocs([])}>
                    Deselect All
                  </button>
                  <span style={{ fontSize: 12, color: '#888', marginLeft: 8 }}>
                    {qaSelectedDocs.length === 0 ? '(all documents)' : `${qaSelectedDocs.length} selected`}
                  </span>
                </div>
                {qaDocs.map((d) => (
                  <label key={d.doc_id as string}>
                    <input
                      type="checkbox"
                      checked={qaSelectedDocs.includes(d.doc_id as string)}
                      onChange={(e) => {
                        const id = d.doc_id as string
                        if (e.target.checked) {
                          setQaSelectedDocs((prev) => [...prev, id])
                        } else {
                          setQaSelectedDocs((prev) => prev.filter((x) => x !== id))
                        }
                      }}
                    />
                    {d.doc_name as string}
                  </label>
                ))}
              </div>
            )}

            {/* Action Row */}
            <div className="qa-action-row">
              <button
                type="button"
                className="btn-ask"
                onClick={handleQaRun}
                disabled={qaRunning || qaPrompts.length === 0}
              >
                {qaRunning ? 'Running...' : 'Run All Tests'}
              </button>
              <button
                type="button"
                className="btn-navy-compact"
                onClick={downloadQAReport}
                disabled={qaResults.length === 0}
              >
                Download Report PDF
              </button>
              {qaStatus && (
                <span style={{ fontSize: 13, fontWeight: 600, color: '#1565c0' }}>{qaStatus}</span>
              )}
            </div>

            {/* Progress Bar */}
            {qaRunning && qaTotal > 0 && (
              <div>
                <div className="qa-progress-bar">
                  <div className="qa-progress-fill" style={{ width: `${(qaCurrent / qaTotal) * 100}%` }} />
                </div>
                <div className="qa-progress-text">{qaCurrent}/{qaTotal} prompts completed</div>
              </div>
            )}

            {/* Results Table */}
            {(qaResults.length > 0 || qaRunning) && (
              <table className="qa-results-table">
                <thead>
                  <tr>
                    <th style={{ width: 40 }}>#</th>
                    <th>Prompt</th>
                    <th>Response</th>
                    <th style={{ width: 120 }}>Source</th>
                    <th style={{ width: 70 }}>Time</th>
                    <th style={{ width: 40 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {qaPrompts.map((prompt, idx) => {
                    const result = qaResults.find((r) => r.index === idx)
                    const isRunningRow = !result && idx === qaCurrent && qaRunning
                    const isPending = !result && !isRunningRow
                    const isError = result?.error
                    const isExpanded = qaExpandedRows.has(idx)

                    let rowClass = 'qa-row-done'
                    if (isPending) rowClass = 'qa-row-pending'
                    else if (isRunningRow) rowClass = 'qa-row-running'
                    else if (isError) rowClass = 'qa-row-error'

                    return (
                      <tr key={idx} className={rowClass}>
                        <td>{idx + 1}</td>
                        <td className="qa-prompt-cell">{prompt}</td>
                        <td
                          className="qa-answer-cell"
                          onClick={() => result && toggleQaRow(idx)}
                        >
                          {isRunningRow && <em>Processing...</em>}
                          {isPending && <em>Pending</em>}
                          {result && (
                            <div className={isExpanded ? 'qa-answer-expanded' : 'qa-answer-truncated'}>
                              {isError ? `Error: ${result.error}` : result.answer}
                            </div>
                          )}
                        </td>
                        <td>
                          {result?.used_chunks?.length
                            ? result.used_chunks
                                .map((c) => c.doc_name)
                                .filter((v, i, a) => a.indexOf(v) === i)
                                .join(', ')
                            : ''}
                        </td>
                        <td className="qa-time-cell">
                          {result ? `${(result.elapsed_ms / 1000).toFixed(1)}s` : ''}
                        </td>
                        <td className="qa-status-icon">
                          {isPending && '\u23F3'}
                          {isRunningRow && '\u23F3'}
                          {result && !isError && '\u2705'}
                          {isError && '\u274C'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}

            {qaPrompts.length === 0 && qaResults.length === 0 && !qaRunning && (
              <div className="qa-empty">
                Upload a PDF or DOCX file containing test prompts to get started.
              </div>
            )}
          </section>
        </div>
        )}
      </main>
    </div>
  )
}
