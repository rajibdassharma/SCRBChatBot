import { useState, useRef, useEffect } from 'react';
import { MessageSquare, Send, Loader2, Database, ChevronDown, ChevronUp } from 'lucide-react';
import { toast } from 'sonner';
import { askChat } from '../lib/api/chat';
import type { ChatResponse } from '../types';

/** A turn in the conversation — the user's question + the assistant's reply.
 *  Reply is null while we're waiting for the API. error supersedes reply. */
interface Turn {
  question: string;
  reply: ChatResponse | null;
  error: string | null;
}

const STARTER_PROMPTS: string[] = [
  'How many cases were registered this month?',
  'Show me the top 5 districts by amount lien marked',
  'List the most recent 10 cases with their FIR numbers',
  'How many arrests in Bangalore City?',
  'Total amount lost across all victims this year',
  'Which banks appear most in lien accounts?',
];

export function ChatPage() {
  const [input, setInput] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom whenever a new turn lands.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, busy]);

  const submit = async (questionRaw: string) => {
    const question = questionRaw.trim();
    if (!question || busy) return;

    setInput('');
    setBusy(true);
    setTurns(prev => [...prev, { question, reply: null, error: null }]);

    try {
      const reply = await askChat(question);
      setTurns(prev => {
        const next = [...prev];
        next[next.length - 1] = { question, reply, error: null };
        return next;
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Chat request failed';
      setTurns(prev => {
        const next = [...prev];
        next[next.length - 1] = { question, reply: null, error: msg };
        return next;
      });
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit(input);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)]">
      {/* Header */}
      <div className="rounded-2xl p-5 mb-4" style={cardStyle}>
        <h1 className="text-[22px] font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
          <MessageSquare className="w-6 h-6" /> Ask the Data
        </h1>
        <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
          Ask any question about cases, arrests, victims, petitions, lien accounts, or refunds — in plain English.
        </p>
        <p className="text-xs mt-1 opacity-60">
          Chat sees data across ALL police stations regardless of your assigned PS. Every question is logged.
        </p>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-4 px-1 pb-4">
        {turns.length === 0 && (
          <div className="rounded-2xl p-6" style={cardStyle}>
            <p className="text-sm font-semibold mb-3" style={{ color: 'var(--ksp-navy)' }}>Try one of these:</p>
            <div className="flex flex-wrap gap-2">
              {STARTER_PROMPTS.map((p, i) => (
                <button
                  key={i}
                  onClick={() => submit(p)}
                  disabled={busy}
                  className="text-xs px-3 py-2 rounded-xl text-left transition disabled:opacity-50"
                  style={{ background: 'rgba(11,44,74,0.04)', border: '1px solid rgba(11,44,74,0.12)', color: 'var(--ksp-navy)' }}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) => (
          <Turn key={i} turn={t} isLast={i === turns.length - 1} busy={busy} onAsk={submit} />
        ))}
      </div>

      {/* Input */}
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={busy ? 'Thinking…' : 'Ask a question about the data…'}
          disabled={busy}
          className="flex-1 px-4 py-3 rounded-xl text-sm outline-none disabled:opacity-60"
          style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }}
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="flex items-center gap-2 px-5 py-3 rounded-xl text-sm font-bold transition disabled:opacity-50"
          style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          {busy ? 'Asking' : 'Ask'}
        </button>
      </form>
    </div>
  );
}

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

function Turn({ turn, isLast, busy, onAsk }: { turn: Turn; isLast: boolean; busy: boolean; onAsk: (q: string) => void }) {
  const waiting = isLast && busy && turn.reply === null && turn.error === null;
  return (
    <div className="space-y-2">
      {/* User question — right-aligned chip */}
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl px-4 py-2 text-sm"
             style={{ background: 'var(--ksp-yellow)', color: 'var(--ksp-navy)' }}>
          {turn.question}
        </div>
      </div>

      {/* Assistant reply — left-aligned card */}
      <div className="flex justify-start">
        <div className="max-w-[90%] rounded-2xl p-4 space-y-3" style={cardStyle}>
          {waiting ? (
            <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--ksp-navy)' }}>
              <Loader2 className="w-4 h-4 animate-spin" /> Generating SQL, running the query, and summarising the result…
            </div>
          ) : turn.error ? (
            <p className="text-sm" style={{ color: 'var(--ksp-red)' }}>
              {turn.error}
            </p>
          ) : turn.reply ? (
            <ReplyView reply={turn.reply} busy={busy} onAsk={onAsk} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ReplyView({ reply, busy, onAsk }: { reply: ChatResponse; busy: boolean; onAsk: (q: string) => void }) {
  const [showData, setShowData] = useState(reply.row_count > 0 && reply.row_count <= 5);
  const [showSql, setShowSql] = useState(false);

  return (
    <>
      <p className="text-sm leading-relaxed" style={{ color: 'var(--ksp-navy)' }}>
        {reply.answer}
      </p>
      {reply.followups && reply.followups.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wide font-bold opacity-50 mb-1.5" style={{ color: 'var(--ksp-navy)' }}>
            Related follow-ups
          </p>
          <div className="flex flex-wrap gap-1.5">
            {reply.followups.map((q, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onAsk(q)}
                disabled={busy}
                className="text-xs px-3 py-1.5 rounded-full transition disabled:opacity-50 text-left"
                style={{ background: 'rgba(11,44,74,0.06)', border: '1px solid rgba(11,44,74,0.18)', color: 'var(--ksp-navy)' }}
                title="Click to ask this follow-up"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
      {reply.row_count > 0 && (
        <div>
          <button
            onClick={() => setShowData(s => !s)}
            className="text-xs flex items-center gap-1 font-semibold"
            style={{ color: 'var(--ksp-navy)' }}
          >
            <Database className="w-3.5 h-3.5" />
            {showData ? 'Hide' : 'Show'} data ({reply.row_count} row{reply.row_count === 1 ? '' : 's'})
            {showData ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {showData && <ResultTable rows={reply.rows} />}
        </div>
      )}
      {reply.sql && (
        <div>
          <button
            onClick={() => setShowSql(s => !s)}
            className="text-xs flex items-center gap-1 opacity-50 hover:opacity-100"
            style={{ color: 'var(--ksp-navy)' }}
          >
            {showSql ? 'Hide' : 'Show'} SQL
            {showSql ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {showSql && (
            <pre className="mt-2 p-3 rounded-lg text-[11px] overflow-x-auto"
                 style={{ background: 'rgba(0,0,0,0.04)', color: 'var(--ksp-navy)' }}>
              {reply.sql}
            </pre>
          )}
        </div>
      )}
      <p className="text-[10px] opacity-50">Completed in {reply.latency_ms} ms</p>
    </>
  );
}

function ResultTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (rows.length === 0) return null;
  const cols = Object.keys(rows[0]);
  return (
    <div className="mt-2 overflow-x-auto rounded-lg" style={{ border: '1px solid rgba(0,0,0,0.08)' }}>
      <table className="w-full text-xs text-left">
        <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
          <tr>
            {cols.map((c) => (
              <th key={c} className="px-3 py-2 text-[10px] uppercase font-bold">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
              {cols.map((c) => (
                <td key={c} className="px-3 py-2 font-mono text-[11px]" style={{ color: 'var(--ksp-navy)' }}>
                  {formatCell(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return v.toLocaleString('en-IN');
  return String(v);
}
