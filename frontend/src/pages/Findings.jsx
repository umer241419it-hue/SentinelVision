import { useEffect, useMemo, useState } from 'react';
import { ListChecks, Search, X } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import DataTable from '../components/DataTable';
import FindingDrawer from '../components/FindingDrawer';
import { SeverityBadge, DispositionBadge } from '../components/Badges';
import { getFindings } from '../services/api';
import './Findings.css';

function fmtTime(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}

const FILTERS = ['All', 'Critical', 'High', 'Medium', 'Low'];

export default function Findings({ onOpenFinding }) {
  const [findings, setFindings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('All');
  const [selected, setSelected] = useState(null);

  const [contributorFilter, setContributorFilter] = useState('All');

  useEffect(() => {
    getFindings().then((f) => {
      setFindings(f);
      setLoading(false);
    });
  }, []);

  // Allow external pages / topbar search to open a finding by id
  useEffect(() => {
    if (onOpenFinding?.target) {
      const f = findings.find(
        (x) => x.id === onOpenFinding.target || x.assetID === onOpenFinding.target
      );
      if (f) setSelected(f);
    }
  }, [onOpenFinding?.target, findings]);

  const contributorsList = useMemo(() => {
    const set = new Set();
    findings.forEach((f) => {
      if (f.contributorName) set.add(f.contributorName);
      else if (f.contributorId) set.add(f.contributorId);
    });
    return Array.from(set);
  }, [findings]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return findings.filter((f) => {
      const matchesFilter = filter === 'All' || f.severity.toLowerCase() === filter.toLowerCase();
      const matchesContrib =
        contributorFilter === 'All' ||
        (f.contributorName && f.contributorName.toLowerCase() === contributorFilter.toLowerCase()) ||
        (f.contributorId && f.contributorId.toLowerCase() === contributorFilter.toLowerCase());
      const matchesQuery =
        !q ||
        f.id.toLowerCase().includes(q) ||
        f.moduleName.toLowerCase().includes(q) ||
        f.reason.toLowerCase().includes(q) ||
        f.assetID.toLowerCase().includes(q) ||
        f.evidenceHash.toLowerCase().includes(q) ||
        (f.contributorName && f.contributorName.toLowerCase().includes(q)) ||
        (f.contributorId && f.contributorId.toLowerCase().includes(q));
      return matchesFilter && matchesContrib && matchesQuery;
    });
  }, [findings, query, filter, contributorFilter]);

  const columns = [
    { key: 'id', label: 'Finding ID', render: (r) => <span className="mono find-id">{r.id}</span> },
    {
      key: 'contributor',
      label: 'Contributor',
      render: (r) => (
        <span className="vendor-chip" title={r.contributorId}>
          {r.contributorName || r.contributorId || 'Vendor Alpha'}
        </span>
      )
    },
    { key: 'moduleName', label: 'Module', render: (r) => <span className="module-chip">{r.moduleName}</span> },
    { key: 'reason', label: 'Reason', render: (r) => <span className="find-reason" title={r.reason}>{r.reason}</span> },
    { key: 'severity', label: 'Severity', render: (r) => <SeverityBadge severity={r.severity} /> },
    { key: 'confidence', label: 'Confidence', render: (r) => `${(r.confidence * 100).toFixed(0)}%` },
    { key: 'disposition', label: 'Disposition', render: (r) => <DispositionBadge disposition={r.disposition} /> },
    { key: 'timestamp', label: 'Timestamp', render: (r) => fmtTime(r.timestamp) },
    {
      key: 'evidenceHash',
      label: 'Evidence',
      render: (r) => (
        <span className="hash-chip" title={r.evidenceHash}>
          #{r.evidenceHash.slice(0, 10)}
        </span>
      )
    },
    {
      key: 'ledgerStatus',
      label: 'Ledger',
      render: (r) => (
        <span className={`ledger-status ${r.ledgerStatus === 'COMMITTED' ? 'ok' : 'pending'}`}>
          {r.ledgerStatus === 'COMMITTED' ? '✓ COMMITTED' : '◌ PENDING'}
        </span>
      )
    }
  ];

  return (
    <div className="anim-fade">
      <GlassCard>
        <div className="card-header">
          <h3>
            <ListChecks size={15} className="hdr-icon" /> All Findings
          </h3>
          <span className="text-muted" style={{ fontSize: 11.5 }}>
            {filtered.length} of {findings.length}
          </span>
        </div>

        <div className="find-toolbar">
          <div className="find-search">
            <Search size={14} />
            <input
              placeholder="Search by ID, module, reason, asset or hash…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {query && (
              <button className="find-clear" onClick={() => setQuery('')} aria-label="Clear search">
                <X size={13} />
              </button>
            )}
          </div>
          <div className="find-filters">
            <select
              style={{
                height: '28px',
                padding: '0 8px',
                background: 'var(--surface-0)',
                border: '1px solid var(--border-medium)',
                color: 'var(--text-secondary)',
                fontSize: '11px',
                borderRadius: '4px',
                outline: 'none',
                fontFamily: 'var(--font-sans)'
              }}
              value={contributorFilter}
              onChange={(e) => setContributorFilter(e.target.value)}
            >
              <option value="All">All Contributors</option>
              {contributorsList.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>

            {FILTERS.map((f) => (
              <button
                key={f}
                className={`filter-btn ${filter === f ? 'active' : ''}`}
                onClick={() => setFilter(f)}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        <DataTable
          columns={columns}
          rows={filtered}
          loading={loading}
          onRowClick={setSelected}
          emptyMessage="No findings match the current search/filter."
        />
      </GlassCard>

      <FindingDrawer finding={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
