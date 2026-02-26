import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { jsPDF } from 'jspdf'
import ForceGraph2D from 'react-force-graph-2d'
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from 'react-simple-maps'
import kspLogo from './assets/ksp_logo.png'
import bannerLogo from './assets/banner_logo.png'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const TABS = ['Document Intelligence', 'Connections Map', 'Activity Timeline'] as const
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

export default function App() {

  const [docQuestion, setDocQuestion] = useState('')
  const [docChat, setDocChat] = useState<ChatMessage[]>([])
  const [docs, setDocs] = useState<DocRecord[]>([])
  const [docStatus, setDocStatus] = useState('')
  const [docLastAnswer, setDocLastAnswer] = useState('')
  const [docLastError, setDocLastError] = useState('')
  const [activeCollection, setActiveCollection] = useState<'SMAC' | 'IR'>('SMAC')
  const [docFiles, setDocFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const folderInputRef = useRef<HTMLInputElement | null>(null)
  const [docLoading, setDocLoading] = useState(false)
  const [docIndexing, setDocIndexing] = useState(false)
  const [failedDocs, setFailedDocs] = useState<{ name: string; error: string }[]>([])
  const [confirmClearDocs, setConfirmClearDocs] = useState(false)

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

  // Load indexed document list from backend on mount & collection change (survives page refresh)
  useEffect(() => {
    let isMounted = true
    apiFetch<{ ok: boolean; docs?: DocRecord[] }>(`/docs/list?collection=${activeCollection}`)
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
  }, [activeCollection])

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
      setDocStatus(`OK Indexed ${indexedCount} document(s). Ready for Q&A.${failures.length ? ` ${failures.length} failed.` : ''} Extracting entities...`)

      // Trigger deferred entity extraction (runs in background on backend)
      try {
        await apiFetch<{ ok?: boolean }>('/docs/extract-entities', { method: 'POST' })
        setDocStatus(`OK Indexed ${indexedCount} document(s). Ready for Q&A.${failures.length ? ` ${failures.length} failed.` : ''} Entity extraction started.`)
      } catch {
        console.warn('[EntityGraph] Failed to trigger entity extraction')
      }
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
      // Pass null to search across ALL indexed documents (not just one)
      const payload = {
        doc_id: null,
        question,
        history: docChat,
        collection: activeCollection,
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

  const handleDocClear = async () => {
    if (!confirmClearDocs) {
      setDocLastError('Please confirm before clearing.')
      return
    }

    setDocLoading(true)
    setDocLastError('')

    try {
      const data = await apiFetch<{ ok?: boolean; error?: string }>(`/docs/clear?collection=${activeCollection}`, {
        method: 'POST',
      })

      if (data?.ok === false) {
        throw new Error(data.error || 'Failed to clear documents.')
      }

      setDocs([])
      setDocChat([])
      setDocLastAnswer('')
      setFailedDocs([])
      setLastIndexSummary(null)
      setDocStatus('OK Documents and vector DB cleared.')
      setConfirmClearDocs(false)
      // Reset graph state
      setGraphNodes([])
      setGraphEdges([])
      setExtractionDone(false)
      setGraphStatus('')
      // Reset timeline state
      setTimelineActivities([])
      setTimelineGroups([])
      setTimelineExtractionDone(false)
      setTimelineStatus('')
      setExpandedActivity(null)
      setBreadcrumbTrail(null)
      // Reset location map state
      setLocationData([])
      setLocationExtractionDone(false)
      setLocationStatus('')
      setSelectedLocation(null)
    } catch (error) {
      setDocLastError(error instanceof Error ? error.message : 'Failed to clear documents.')
    } finally {
      setDocLoading(false)
    }
  }

  // ── Entity Graph ────────────────────────────────────────────────────────
  const loadGraphData = useCallback(async (search?: string) => {
    setGraphLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      params.set('limit', '200')
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
          setGraphStatus(`Extracting entities... ${status.completed || 0}/${status.total || '?'} documents processed`)
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
            setGraphStatus(`Extracting entities... ${status.completed || 0}/${status.total || '?'} documents processed`)
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
      await apiFetch<{ ok: boolean }>('/graph/clear', { method: 'DELETE' })
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
        `/graph/extract-all?collection=${activeCollection}`,
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
      const data = await apiFetch<{ ok?: boolean; groups?: TimelineGroup[] }>('/timeline/groups')
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
        `/timeline/extract-all?collection=${activeCollection}`,
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
          `/timeline/breadcrumb?tms_id=${encodeURIComponent(activity.tms_id)}`
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
        '/locations/data'
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
        '/locations/extract-all?collection=IR',
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

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <img src={kspLogo} alt="KSP" />
        </div>
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
        <div className="banner-wrapper">
          <img src={bannerLogo} alt="ISD-AI Logo" className="ksp-banner-img" />
          <header className="ksp-banner">
            <div className="ksp-banner-left">
              <h1 className="ksp-title">ISD-AI</h1>
              <p className="ksp-tagline">empowering law enforcement with artificial intelligence</p>
            </div>
          </header>
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
                <span className="ksp-chip ksp-chip-spaced ksp-chip-navy">Ask</span>
                <textarea
                  className="ksp-textarea"
                  value={docQuestion}
                  onChange={(event) => setDocQuestion(event.target.value)}
                  placeholder="Ask question on uploaded documents"
                />
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
                    {docLoading ? 'Searching...' : 'Ask Documents'}
                  </button>
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
      </main>
    </div>
  )
}
