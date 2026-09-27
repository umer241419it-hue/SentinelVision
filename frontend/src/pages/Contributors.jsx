import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Building2, Plus, Search, RefreshCw, X, Database, Cpu, ExternalLink,
  ShieldCheck, FileCode, CheckCircle2, Hash
} from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { StatusBadge } from '../components/Badges';
import { listContributors, getContributor, createContributor } from '../services/workflowApi';
import './Contributors.css';

export default function Contributors({ notify }) {
  const navigate = useNavigate();
  const [contributors, setContributors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [selectedContributor, setSelectedContributor] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Form state
  const [formName, setFormName] = useState('');
  const [formId, setFormId] = useState('');
  const [formType, setFormType] = useState('DEMO_VENDOR');
  const [formDesc, setFormDesc] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listContributors();
      setContributors(data);
    } catch (err) {
      notify?.(err.message || 'Failed to load contributors', 'error');
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const openDetail = async (id) => {
    setDetailLoading(true);
    try {
      const detail = await getContributor(id);
      setSelectedContributor(detail);
    } catch (err) {
      notify?.(err.message || 'Failed to load contributor details', 'error');
    } finally {
      setDetailLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!formName.trim()) {
      notify?.('Please enter a contributor/vendor name', 'error');
      return;
    }
    setSubmitting(true);
    try {
      await createContributor({
        name: formName.trim(),
        id: formId.trim() || undefined,
        type: formType,
        description: formDesc.trim() || undefined
      });
      notify?.(`Contributor "${formName.trim()}" registered successfully`, 'success');
      setShowCreateModal(false);
      setFormName('');
      setFormId('');
      setFormDesc('');
      await loadData();
    } catch (err) {
      notify?.(err.message || 'Failed to create contributor', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const filtered = contributors.filter((c) => {
    const q = query.toLowerCase();
    return (
      c.name.toLowerCase().includes(q) ||
      c.id.toLowerCase().includes(q) ||
      (c.description && c.description.toLowerCase().includes(q))
    );
  });

  const totalDatasets = contributors.reduce((acc, c) => acc + (c.datasetCount || 0), 0);
  const totalModels = contributors.reduce((acc, c) => acc + (c.modelCount || 0), 0);

  return (
    <div className="anim-fade">
      {/* Header */}
      <div className="contrib-header-row">
        <div>
          <h2 style={{ margin: 0, fontSize: '18px', letterSpacing: '0.08em', color: 'var(--text-primary)' }}>
            <Building2 size={18} style={{ display: 'inline', marginRight: 8, verticalAlign: 'text-bottom', color: 'var(--accent-cyan)' }} />
            CONTRIBUTORS & VENDORS
          </h2>
          <span style={{ fontSize: '11.5px', color: 'var(--text-secondary)' }}>
            Multi-vendor asset governance, independent assurance, and source attribution
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="hud-btn icon-only ghost" onClick={loadData} title="Refresh">
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
          <button className="auth-submit" style={{ padding: '6px 14px', fontSize: '12px' }} onClick={() => setShowCreateModal(true)}>
            <Plus size={14} style={{ marginRight: 4 }} /> REGISTER CONTRIBUTOR
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="contrib-kpis">
        <div className="contrib-kpi-card">
          <div className="contrib-kpi-title">Active Contributors</div>
          <div className="contrib-kpi-val">{contributors.length}</div>
        </div>
        <div className="contrib-kpi-card">
          <div className="contrib-kpi-title">Governed Datasets</div>
          <div className="contrib-kpi-val">{totalDatasets}</div>
        </div>
        <div className="contrib-kpi-card">
          <div className="contrib-kpi-title">Governed Models</div>
          <div className="contrib-kpi-val">{totalModels}</div>
        </div>
        <div className="contrib-kpi-card">
          <div className="contrib-kpi-title">Source Attribution</div>
          <div className="contrib-kpi-val" style={{ color: '#34d399', fontSize: '16px', lineHeight: '30px' }}>
            CRYPTOGRAPHIC
          </div>
        </div>
      </div>

      {/* Search Bar */}
      <div className="contrib-toolbar">
        <div className="contrib-search">
          <Search size={14} />
          <input
            placeholder="Search contributors by name, identifier, or description…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button className="find-clear" onClick={() => setQuery('')} aria-label="Clear search">
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Contributors Grid */}
      <div className="contrib-grid">
        {filtered.map((c) => (
          <div key={c.id} className="contrib-card" onClick={() => openDetail(c.id)}>
            <div>
              <div className="contrib-card-head">
                <div>
                  <div className="contrib-name">{c.name}</div>
                  <div className="mono contrib-id">{c.id}</div>
                </div>
                <span className="contrib-type-chip">{c.type || 'VENDOR'}</span>
              </div>
              <div className="contrib-desc">{c.description || 'No description registered.'}</div>
            </div>

            <div>
              <div className="contrib-stats">
                <div className="contrib-stat">
                  <span className="contrib-stat-label">Datasets</span>
                  <span className="contrib-stat-num">{c.datasetCount || 0}</span>
                </div>
                <div className="contrib-stat">
                  <span className="contrib-stat-label">Models</span>
                  <span className="contrib-stat-num">{c.modelCount || 0}</span>
                </div>
              </div>

              <div className="contrib-card-foot">
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  {c.createdAt ? new Date(c.createdAt).toLocaleDateString() : '—'}
                </span>
                <span style={{ fontSize: '11px', color: 'var(--accent-cyan)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  Inspect Assets →
                </span>
              </div>
            </div>
          </div>
        ))}

        {filtered.length === 0 && !loading && (
          <div style={{ gridColumn: '1 / -1', padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            No contributors match the search criteria.
          </div>
        )}
      </div>

      {/* Detail Drawer */}
      {selectedContributor && (
        <>
          <div className="contrib-drawer-backdrop" onClick={() => setSelectedContributor(null)} />
          <aside className="contrib-drawer">
            <header className="contrib-drawer-head">
              <div>
                <div className="contrib-drawer-kicker">Contributor / Vendor Dossier</div>
                <h3 className="contrib-drawer-title">{selectedContributor.name}</h3>
                <span className="mono" style={{ fontSize: '11px', color: 'var(--accent-cyan)' }}>
                  ID: {selectedContributor.id} · Type: {selectedContributor.type}
                </span>
              </div>
              <button className="hud-btn icon-only ghost" onClick={() => setSelectedContributor(null)}>
                <X size={16} />
              </button>
            </header>

            <div className="contrib-drawer-body">
              <div>
                <div className="contrib-section-title">Overview & Context</div>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '6px 0 0 0', lineHeight: 1.5 }}>
                  {selectedContributor.description || 'No additional vendor notes available.'}
                </p>
              </div>

              {/* Datasets Section */}
              <div className="contrib-detail-section">
                <div className="contrib-section-title">
                  <span>Assigned Datasets ({selectedContributor.datasets?.length || 0})</span>
                  <Database size={14} />
                </div>
                <div className="contrib-asset-list">
                  {selectedContributor.datasets && selectedContributor.datasets.length > 0 ? (
                    selectedContributor.datasets.map((d) => (
                      <div key={d.uploadId || d.id} className="contrib-asset-item">
                        <div className="contrib-asset-top">
                          <span className="contrib-asset-name">{d.originalName || d.name}</span>
                          <span className="status-pill ok" style={{ fontSize: '10px' }}>{d.format || 'DATASET'}</span>
                        </div>
                        <div className="contrib-asset-meta">
                          <span className="mono">ID: {d.uploadId || d.id}</span>
                          <span>Size: {d.size ? `${(d.size / (1024 * 1024)).toFixed(1)} MB` : '—'}</span>
                        </div>
                        <div className="mono contrib-asset-hash" title={d.sha256}>
                          <Hash size={11} style={{ display: 'inline', verticalAlign: 'text-top', marginRight: 4 }} />
                          SHA256: {d.sha256 ? `${d.sha256.slice(0, 16)}…${d.sha256.slice(-8)}` : 'unhashed'}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                      No datasets registered under this contributor.
                    </div>
                  )}
                </div>
              </div>

              {/* Models Section */}
              <div className="contrib-detail-section">
                <div className="contrib-section-title">
                  <span>Assigned Models ({selectedContributor.models?.length || 0})</span>
                  <Cpu size={14} />
                </div>
                <div className="contrib-asset-list">
                  {selectedContributor.models && selectedContributor.models.length > 0 ? (
                    selectedContributor.models.map((m) => (
                      <div key={m.uploadId || m.id} className="contrib-asset-item">
                        <div className="contrib-asset-top">
                          <span className="contrib-asset-name">{m.originalName || m.name}</span>
                          <span className="status-pill info" style={{ fontSize: '10px' }}>{m.framework || 'MODEL'}</span>
                        </div>
                        <div className="contrib-asset-meta">
                          <span className="mono">ID: {m.uploadId || m.id}</span>
                          <span>Size: {m.size ? `${(m.size / (1024 * 1024)).toFixed(1)} MB` : '—'}</span>
                        </div>
                        <div className="mono contrib-asset-hash" title={m.sha256}>
                          <Hash size={11} style={{ display: 'inline', verticalAlign: 'text-top', marginRight: 4 }} />
                          SHA256: {m.sha256 ? `${m.sha256.slice(0, 16)}…${m.sha256.slice(-8)}` : 'unhashed'}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                      No models registered under this contributor.
                    </div>
                  )}
                </div>
              </div>

              <div style={{ marginTop: 'auto', paddingTop: '16px' }}>
                <button
                  className="auth-submit"
                  style={{ width: '100%', justifyContent: 'center' }}
                  onClick={() => {
                    navigate(`/workspace?contributorId=${encodeURIComponent(selectedContributor.id)}`);
                  }}
                >
                  <ExternalLink size={14} style={{ marginRight: 6 }} /> RUN ASSURANCE IN ANALYST WORKSPACE
                </button>
              </div>
            </div>
          </aside>
        </>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="contrib-modal-backdrop" onClick={() => setShowCreateModal(false)}>
          <div className="contrib-modal" onClick={(e) => e.stopPropagation()}>
            <div className="contrib-modal-head">
              <h3>REGISTER NEW CONTRIBUTOR / VENDOR</h3>
              <button className="hud-btn icon-only ghost" onClick={() => setShowCreateModal(false)}>
                <X size={15} />
              </button>
            </div>
            <form onSubmit={handleCreate}>
              <div className="contrib-modal-body">
                <div className="contrib-field">
                  <label>Contributor / Vendor Name *</label>
                  <input
                    required
                    placeholder="e.g. Vendor Delta or Research Lab X"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                  />
                </div>
                <div className="contrib-field">
                  <label>Identifier (Optional — auto-generated from name)</label>
                  <input
                    placeholder="e.g. vendor-delta"
                    value={formId}
                    onChange={(e) => setFormId(e.target.value)}
                  />
                </div>
                <div className="contrib-field">
                  <label>Type</label>
                  <select value={formType} onChange={(e) => setFormType(e.target.value)}>
                    <option value="DEMO_VENDOR">Demo Vendor</option>
                    <option value="CERTIFIED_VENDOR">Certified Vendor</option>
                    <option value="ACADEMIC_RESEARCH">Academic / Research</option>
                    <option value="THIRD_PARTY">Third Party External</option>
                  </select>
                </div>
                <div className="contrib-field">
                  <label>Description / Scope of Assets</label>
                  <textarea
                    rows={3}
                    placeholder="Brief description of datasets, weights, or sensors supplied…"
                    value={formDesc}
                    onChange={(e) => setFormDesc(e.target.value)}
                  />
                </div>
              </div>
              <div className="contrib-modal-foot">
                <button type="button" className="hud-btn ghost" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="auth-submit" disabled={submitting}>
                  {submitting ? 'Registering…' : 'Register Contributor'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
