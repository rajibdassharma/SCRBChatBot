/** Account Details -> Duplicate IDs tab (2026-08-04).
 *
 *  Surfaces F1: accounts whose uploaded ID photo is the SAME FILE.
 *
 *  The match is SHA-256 of the file bytes. Nothing is read out of the
 *  document — no name, no Aadhaar number, no date of birth — so this
 *  needs no OCR and raises no identity-extraction question.
 *
 *  SHA-256 rather than a perceptual hash, because the first version got
 *  this wrong in a way worth remembering. It clustered on a 64-bit
 *  dHash and led with two groups of 28 and 23 "matching" documents.
 *  Both were false: 28 and 23 DISTINCT files, under as many different
 *  holder names. ID cards are near-identical by design — same emblem,
 *  same colour bands, same photo box — so a coarse perceptual hash
 *  matches the template and reports every Aadhaar card as a duplicate
 *  of every other one. Exact file identity cannot fail that way.
 *
 *  RANKED BY SPREAD, NOT SIZE. One file on twenty accounts under one
 *  name in one station is probably one person, or one operator
 *  attaching the same file repeatedly. The same file behind many
 *  DIFFERENT holders across several stations is what a mule farm looks
 *  like, and that is what belongs at the top of the screen.
 *
 *  Clusters containing a Victim account are pushed down and marked: a
 *  network does not recruit the people it defrauds, so those read as
 *  placeholder or default images. On the current corpus the single
 *  largest cluster is exactly that — left unranked it would sit at the
 *  top and teach officers the feature is noise.
 */
import { Fragment, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  Fingerprint, AlertTriangle, ChevronRight, ChevronDown,  } from 'lucide-react';
import { getDuplicateIds } from '../../lib/api/dashboard';
import { formatNumber } from '../../lib/utils/format';
import type { DuplicateIdSummary, DuplicateIdCluster } from '../../types';
import CaveatNote from '../common/CaveatNote';

const C_NAVY = '#0b2c4a';
const C_RED = '#8b1919';
const C_ORANGE = '#c67c1d';

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

/** Same pill colours the drill-down panel uses, so an account type
 *  reads identically wherever it appears. */
function typePill(t: string | null) {
  if (t === 'Victim') return { background: '#e6f5eb', color: '#0a6b28' };
  if (t === 'Mule') return { background: '#fbe6e6', color: C_RED };
  if (t === 'Non-Mule') return { background: '#e6ecf5', color: C_NAVY };
  return { background: '#f0f0f0', color: '#444' };
}

function Kpi({ label, value, accent, sub }: {
  label: string; value: string; accent: string; sub?: string;
}) {
  return (
    <div className="rounded-2xl p-4" style={{ ...cardStyle, borderTop: `4px solid ${accent}` }}>
      <p className="text-[11px] uppercase tracking-wide font-bold" style={{ color: accent }}>
        {label}
      </p>
      <p className="text-2xl font-bold" style={{ color: C_NAVY }}>{value}</p>
      {sub && <p className="text-[11px] mt-0.5 opacity-60">{sub}</p>}
    </div>
  );
}

export function DuplicateIdsTab() {
  const [data, setData] = useState<DuplicateIdSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [hideVictim, setHideVictim] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getDuplicateIds(2, 2000)
      .then((d) => { if (alive) { setData(d); setLoading(false); } })
      .catch((e: unknown) => {
        if (!alive) return;
        setData(null);
        setLoading(false);
        toast.error(e instanceof Error ? e.message : 'Failed to load duplicate-ID analysis');
      });
    return () => { alive = false; };
  }, []);

  const rows = useMemo(
    () => (data?.rows ?? []).filter((c) => !(hideVictim && c.has_victim)),
    [data, hideVictim],
  );

  function toggle(fp: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(fp)) next.delete(fp); else next.add(fp);
      return next;
    });
  }

  if (loading) {
    return (
      <div className="text-center py-16 font-semibold" style={{ color: C_NAVY }}>
        Analysing ID photo fingerprints…
      </div>
    );
  }

  if (!data || data.total_hashed === 0) {
    return (
      <div className="rounded-2xl p-8" style={cardStyle}>
        <p className="text-sm font-bold mb-1" style={{ color: C_NAVY }}>
          No fingerprints have been computed yet.
        </p>
        <p className="text-xs opacity-70">
          ID photos are fingerprinted by a batch job, not on upload. Until it has
          run there is nothing to compare. Ask your administrator to run{' '}
          <code>analysis/hash_id_photos.py</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <Kpi label="ID photos analysed" value={formatNumber(data.total_hashed)}
          accent={C_NAVY} sub="fingerprinted, not read" />
        <Kpi label="Shared-file groups" value={formatNumber(data.clusters)}
          accent={C_NAVY} sub="2+ accounts, identical file" />
        <Kpi label="Different names" value={formatNumber(data.with_multiple_holders)}
          accent={C_ORANGE} sub="same file, 2+ holders" />
        <Kpi label="Across stations" value={formatNumber(data.across_police_stations)}
          accent={C_RED} sub="2+ police stations" />
        <Kpi label="Strong signal" value={formatNumber(data.strong_signal)}
          accent={C_RED} sub="2+ a/c nos AND 2+ names" />
      </div>

      {/* `clusters` is counted before the row limit is applied, so this
           compares what arrived against what exists. Without it a table
           showing 100 of 243 groups looks like the whole finding. */}
      {(data.rows?.length ?? 0) < data.clusters && (
        <div className="rounded-xl px-4 py-3 text-xs font-semibold"
          style={{ background: 'rgba(198,124,29,0.10)',
                   border: '1px solid rgba(198,124,29,0.35)', color: C_RED }}>
          ⚠ Showing {formatNumber(data.rows?.length ?? 0)} of{' '}
          {formatNumber(data.clusters)} groups. The remaining{' '}
          {formatNumber(data.clusters - (data.rows?.length ?? 0))} are not listed.
        </div>
      )}

      {/* The caveat travels with the finding, always. A shared image is
           a reason to look, never a conclusion. */}
        <CaveatNote summary="A shared ID file is a lead, not proof">
          It can also mean one person legitimately holds several accounts, or an
          operator attached the same file to more than one record. Open each group
          and verify before acting. Every account in a group has the{' '}
          <b>byte-for-byte identical file</b> attached — matching is on a checksum
          of the file, so no name, number or date of birth is read from the
          document.
        </CaveatNote>

      <div className="rounded-2xl overflow-hidden" style={cardStyle}>
        <div className="px-5 py-4 flex items-start justify-between gap-4 flex-wrap"
          style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
          <div>
            <h3 className="text-sm font-bold flex items-center gap-1.5" style={{ color: C_NAVY }}>
              <Fingerprint className="w-4 h-4" /> Accounts sharing the same ID file
            </h3>
            <div className="mt-1">
              <CaveatNote summary="Ranked by spread, not by upload count">
                Spread is how many distinct account numbers, police stations and
                holder names one file reaches. Different names on the SAME account
                number is an entry-quality issue; different names on DIFFERENT
                account numbers is identity reuse.
              </CaveatNote>
            </div>
          </div>
          <label className="text-xs flex items-center gap-2 font-semibold"
            style={{ color: C_NAVY }}>
            <input type="checkbox" checked={hideVictim}
              onChange={(e) => setHideVictim(e.target.checked)} />
            Hide groups containing Victim accounts
          </label>
        </div>

        {rows.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm opacity-60">
            No groups to show{hideVictim ? ' — try unchecking the Victim filter.' : '.'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead style={{ background: C_NAVY, color: 'var(--ksp-yellow)' }}>
                <tr>
                  <th className="px-3 py-3 text-xs uppercase font-bold w-8" />
                  <th className="px-3 py-3 text-xs uppercase font-bold">#</th>
                  <th className="px-3 py-3 text-xs uppercase font-bold">Image</th>
                  <th className="px-3 py-3 text-xs uppercase font-bold text-right">Accounts</th>
                  {/* A/C nos sits next to Accounts on purpose. When it
                      reads 1, every "different name" below it is the
                      SAME account typed differently — an entry-quality
                      problem, not identity reuse. Without this column
                      the Names figure reads as three people. */}
                  <th className="px-3 py-3 text-xs uppercase font-bold text-right">A/C nos</th>
                  <th className="px-3 py-3 text-xs uppercase font-bold text-right">Names</th>
                  <th className="px-3 py-3 text-xs uppercase font-bold text-right">FIRs</th>
                  <th className="px-3 py-3 text-xs uppercase font-bold text-right">Stations</th>
                  <th className="px-3 py-3 text-xs uppercase font-bold text-right">Districts</th>
                  <th className="px-3 py-3 text-xs uppercase font-bold">Types</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c, i) => {
                  const isOpen = open.has(c.fingerprint);
                  const strong = c.distinct_account_nos >= 2 && c.distinct_holders >= 2
                    && !c.has_victim;
                  return (
                    <Fragment key={c.fingerprint}>
                      <tr onClick={() => toggle(c.fingerprint)}
                        className="border-t cursor-pointer transition"
                        style={{
                          borderColor: 'rgba(11,44,74,0.08)',
                          background: isOpen ? 'rgba(11,44,74,0.04)' : undefined,
                        }}>
                        <td className="px-3 py-2">
                          {isOpen ? <ChevronDown className="w-4 h-4" style={{ color: C_NAVY }} />
                            : <ChevronRight className="w-4 h-4" style={{ color: C_NAVY }} />}
                        </td>
                        <td className="px-3 py-2 font-bold" style={{ color: C_NAVY }}>
                          {i + 1}
                          {strong && (
                            <AlertTriangle className="inline w-3.5 h-3.5 ml-1.5"
                              style={{ color: C_RED }} aria-label="strong signal" />
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {/* Small on purpose. Enough to tell a real
                              document from a blank page at a glance,
                              not enough to read someone's Aadhaar
                              number off a dashboard over a shoulder.
                              Expand the row for a proper look. */}
                          {c.image_url ? (
                            <img src={`/${c.image_url}`} alt=""
                              loading="lazy"
                              style={{ width: 46, height: 34, objectFit: 'cover',
                                       borderRadius: 4,
                                       border: '1px solid rgba(11,44,74,0.25)' }} />
                          ) : (
                            <span className="text-[10px] opacity-50">n/a</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right font-bold">{formatNumber(c.accounts)}</td>
                        <td className="px-3 py-2 text-right font-bold"
                          style={{ color: c.distinct_account_nos >= 2 ? C_RED : undefined }}>
                          {formatNumber(c.distinct_account_nos)}
                        </td>
                        <td className="px-3 py-2 text-right font-bold"
                          style={{ color: c.distinct_account_nos >= 2 && c.distinct_holders >= 2
                                     ? C_RED : undefined }}>
                          {formatNumber(c.distinct_holders)}
                        </td>
                        <td className="px-3 py-2 text-right">{formatNumber(c.distinct_firs)}</td>
                        <td className="px-3 py-2 text-right font-bold"
                          style={{ color: c.distinct_ps >= 2 ? C_RED : undefined }}>
                          {formatNumber(c.distinct_ps)}
                        </td>
                        <td className="px-3 py-2 text-right">{formatNumber(c.distinct_districts)}</td>
                        <td className="px-3 py-2">
                          <span className="inline-flex gap-1 flex-wrap">
                            {c.account_types.map((t) => (
                              <span key={t} className="px-2 py-0.5 rounded text-[10px] font-bold"
                                style={typePill(t)}>{t}</span>
                            ))}
                          </span>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={10} className="px-3 py-3" style={{ background: '#fafbfd' }}>
                            <MemberTable cluster={c} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function MemberTable({ cluster }: { cluster: DuplicateIdCluster }) {
  return (
    <>
      <div className="flex items-start gap-4 mb-3 flex-wrap">
        {cluster.image_url && (
          <div>
            <a href={`/${cluster.image_url}`} target="_blank" rel="noopener noreferrer"
               title="Open the full image in a new tab">
              <img src={`/${cluster.image_url}`} alt="Shared ID document"
                style={{ maxWidth: 220, maxHeight: 160, objectFit: 'contain',
                         borderRadius: 6, background: '#fff',
                         border: '2px solid rgba(11,44,74,0.25)' }} />
            </a>
            <p className="text-[10px] opacity-55 mt-1" style={{ maxWidth: 220 }}>
              The file attached to every account below — identical bytes, not
              merely a similar-looking document. Click to enlarge. If this is
              blank or a placeholder, the group is a data-entry artefact rather
              than identity reuse.
            </p>
          </div>
        )}
        <div className="flex-1 min-w-[280px]">
          <p className="text-xs font-bold mb-2" style={{ color: C_NAVY }}>
            {formatNumber(cluster.members.length)} account
            {cluster.members.length === 1 ? '' : 's'} share this exact file
          </p>
          <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: 'rgba(11,44,74,0.06)' }}>
              <th className="px-2 py-1.5 text-left font-bold">Account holder</th>
              <th className="px-2 py-1.5 text-left font-bold">Account no</th>
              <th className="px-2 py-1.5 text-left font-bold">Bank</th>
              <th className="px-2 py-1.5 text-left font-bold">FIR No</th>
              <th className="px-2 py-1.5 text-left font-bold">Type</th>
              <th className="px-2 py-1.5 text-left font-bold">Police Station</th>
              <th className="px-2 py-1.5 text-left font-bold">District</th>
            </tr>
          </thead>
          <tbody>
            {cluster.members.map((m) => (
              <tr key={m.account_id} className="border-t" style={{ borderColor: 'rgba(11,44,74,0.08)' }}>
                <td className="px-2 py-1.5 font-semibold" style={{ color: C_NAVY }}>
                  {m.account_holder_name || '—'}
                </td>
                <td className="px-2 py-1.5">{m.account_no || '—'}</td>
                <td className="px-2 py-1.5">{m.bank_name || '—'}</td>
                <td className="px-2 py-1.5">{m.fir_no || '—'}</td>
                <td className="px-2 py-1.5">
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold"
                    style={typePill(m.account_type)}>{m.account_type || '—'}</span>
                </td>
                <td className="px-2 py-1.5">{m.ps_name || '—'}</td>
                <td className="px-2 py-1.5">{m.district || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
          </div>
        </div>
      </div>
    </>
  );
}
