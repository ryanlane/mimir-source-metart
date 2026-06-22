// Met Museum Art Manager Web Component for Mimir Platform
const CHANNEL_ID = 'com.metmuseum.art';

const GALLERY_TYPES = [
  { id: 'highlights', name: 'Highlights', description: 'The Met\'s curated highlight artworks' },
  { id: 'department', name: 'Department', description: 'All artworks from a specific department' },
  { id: 'search',     name: 'Search',     description: 'Keyword search across the full collection' },
];

const CSS = `
  :host {
    display: block;
    font-family: "Lato", system-ui, sans-serif;
    font-size: 14px;
    color: var(--color-text, #e0e0e0);
    background: transparent;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }

  .manager { display: flex; flex-direction: column; gap: 16px; padding: 16px 0; }

  .section { display: flex; flex-direction: column; gap: 8px; }
  .section-header { display: flex; align-items: center; justify-content: space-between; }
  .section-title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--color-text-secondary, #888); }

  /* Gallery cards */
  .gallery-list { display: flex; flex-direction: column; gap: 6px; }
  .gallery-card {
    background: var(--color-surface, #162325);
    border: 1px solid var(--color-border, #2a3a3c);
    border-radius: 8px; padding: 12px 14px;
    display: flex; align-items: center; gap: 12px;
  }
  .gallery-info { flex: 1; min-width: 0; }
  .gallery-name { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .gallery-meta { font-size: 12px; color: var(--color-text-secondary, #888); margin-top: 4px; }
  .gallery-actions { display: flex; gap: 6px; flex-shrink: 0; }

  .empty-state {
    padding: 24px; text-align: center; font-size: 13px;
    color: var(--color-text-secondary, #888);
    background: var(--color-surface, #162325);
    border: 1px dashed var(--color-border, #2a3a3c); border-radius: 8px;
  }

  /* Type badges */
  .type-badge {
    display: inline-block; padding: 1px 6px; border-radius: 4px;
    font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
  }
  .type-badge.highlights { background: #0d1a2d; color: #60a5fa; border: 1px solid #1e3a6e; }
  .type-badge.department  { background: #1a1a0a; color: #fbbf24; border: 1px solid #5c4a1a; }
  .type-badge.search      { background: #0a2918; color: #4ade80; border: 1px solid #1a5c38; }

  /* Type selector */
  .type-selector { display: flex; gap: 0; border: 1px solid var(--color-border, #2a3a3c); border-radius: 6px; overflow: hidden; }
  .type-selector button {
    flex: 1; padding: 6px 8px; border: none; background: transparent;
    font-size: 12px; font-family: inherit; cursor: pointer; font-weight: 500;
    color: var(--color-text-secondary, #888); transition: background 0.12s, color 0.12s;
  }
  .type-selector button.active { background: var(--color-accent, #00C851); color: #000; font-weight: 700; }
  .type-selector button:not(.active):hover { background: var(--color-surface-hover, #1e2f31); color: var(--color-text, #e0e0e0); }

  /* Add/edit gallery panel */
  .add-panel {
    background: var(--color-surface, #162325);
    border: 1px solid var(--color-border, #2a3a3c);
    border-radius: 8px; padding: 16px;
    display: flex; flex-direction: column; gap: 12px;
  }
  .add-panel-header { display: flex; align-items: center; justify-content: space-between; }
  .input-row { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; }
  .field { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 120px; }
  .field.field-label { min-width: 160px; }
  .field label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--color-text-secondary, #888); }
  .field select, .field input[type="text"], .field input[type="number"] {
    background: var(--color-background, #0B1314); border: 1px solid var(--color-border, #2a3a3c);
    border-radius: 6px; padding: 8px 10px; font-size: 13px; font-family: inherit;
    color: var(--color-text, #e0e0e0); width: 100%;
  }
  .field select:focus, .field input:focus { outline: 2px solid var(--color-accent, #00C851); border-color: transparent; }
  .field-hint { font-size: 11px; color: var(--color-text-tertiary, #666); margin-top: 2px; }

  .checkbox-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .checkbox-row input[type="checkbox"] { width: 15px; height: 15px; accent-color: var(--color-accent, #00C851); cursor: pointer; }
  .checkbox-row label { cursor: pointer; color: var(--color-text-secondary, #888); }

  /* Settings panel */
  .settings-panel {
    background: var(--color-surface, #162325); border: 1px solid var(--color-border, #2a3a3c);
    border-radius: 8px; padding: 16px; display: flex; flex-direction: column; gap: 14px;
  }
  .settings-row { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
  .settings-row .field { min-width: 130px; }
  .settings-actions { display: flex; justify-content: flex-end; gap: 8px; }

  /* Buttons */
  .btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 14px; border-radius: 6px; border: none;
    font-size: 13px; font-family: inherit; cursor: pointer;
    font-weight: 600; transition: background 0.15s, opacity 0.15s; white-space: nowrap;
  }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn-primary { background: var(--color-accent, #00C851); color: #000; }
  .btn-primary:hover:not(:disabled) { background: var(--color-accent-hover, #00d858); }
  .btn-secondary { background: var(--color-surface, #162325); color: var(--color-text, #e0e0e0); border: 1px solid var(--color-border, #2a3a3c); }
  .btn-secondary:hover:not(:disabled) { background: var(--color-surface-hover, #1e2f31); }
  .btn-danger { background: #c62828; color: #fff; }
  .btn-danger:hover:not(:disabled) { background: #d32f2f; }
  .btn-ghost { background: transparent; color: var(--color-text-secondary, #888); padding: 4px 8px; font-size: 12px; font-weight: 400; }
  .btn-ghost:hover:not(:disabled) { color: var(--color-text, #e0e0e0); }
  .btn-sm { padding: 4px 10px; font-size: 12px; }
  .btn-icon { padding: 5px 8px; }

  /* Status messages */
  .status-msg {
    padding: 8px 12px; border-radius: 6px; font-size: 13px;
    display: flex; align-items: center; gap: 6px;
  }
  .status-msg.success { background: #0a2918; border: 1px solid #1a5c38; color: #4ade80; }
  .status-msg.error   { background: #2a0a0a; border: 1px solid #6b1111; color: #f87171; }
  .status-msg.info    { background: var(--color-surface, #162325); border: 1px solid var(--color-border, #2a3a3c); color: var(--color-text-secondary, #888); }

  /* Attribution */
  .attribution {
    font-size: 11px; color: var(--color-text-tertiary, #666);
    padding: 8px 0; border-top: 1px solid var(--color-border, #2a3a3c);
  }
  .attribution a { color: var(--color-accent, #00C851); text-decoration: none; }
  .attribution a:hover { text-decoration: underline; }

  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner {
    width: 14px; height: 14px; border-radius: 50%;
    border: 2px solid var(--color-border, #2a3a3c);
    border-top-color: var(--color-accent, #00C851);
    animation: spin 0.7s linear infinite; flex-shrink: 0;
  }
`;

class MetArtManager extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.state = {
      loading: true,
      saving: false,
      refreshing: false,
      loadingDepts: false,
      galleries: [],
      departments: [],
      cacheStats: {},
      settings: null,
      // add/edit form
      editGalleryId: null,   // null = create mode, string = edit mode
      newType: 'highlights',
      newLabel: '',
      newDeptId: '',
      newDeptName: '',
      newQ: '',
      newPublicDomain: true,
      newDateBegin: '',
      newDateEnd: '',
      newMedium: '',
      showAddPanel: false,
      showSettings: false,
      message: null,
    };
  }

  get channelId() { return this.getAttribute('channel-id') || CHANNEL_ID; }
  get apiBase() { return `/api/channels/${this.channelId}`; }

  async connectedCallback() {
    this.render();
    await this.loadStatus();
  }

  async loadStatus() {
    this.setState({ loading: true });
    try {
      const resp = await fetch(`${this.apiBase}/status`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      this.setState({
        loading: false,
        galleries: data.settings?.galleries || [],
        cacheStats: data.cache_stats || {},
        settings: data.settings || {},
      });
    } catch (err) {
      this.setState({ loading: false, message: { type: 'error', text: `Failed to load: ${err.message}` } });
    }
  }

  async loadDepartments() {
    if (this.state.departments.length > 0) return;
    this.setState({ loadingDepts: true });
    try {
      const resp = await fetch(`${this.apiBase}/departments`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      this.setState({ departments: data, loadingDepts: false });
    } catch (err) {
      this.setState({ loadingDepts: false, message: { type: 'error', text: `Failed to load departments: ${err.message}` } });
    }
  }

  setState(updates) {
    Object.assign(this.state, updates);
    this.render();
  }

  _openAddPanel() {
    this.setState({
      showAddPanel: true,
      editGalleryId: null,
      newType: 'highlights',
      newLabel: '',
      newDeptId: '',
      newDeptName: '',
      newQ: '',
      newPublicDomain: true,
      newDateBegin: '',
      newDateEnd: '',
      newMedium: '',
      message: null,
    });
  }

  _openEditPanel(gallery) {
    this.setState({
      showAddPanel: true,
      editGalleryId: gallery.id,
      newType: gallery.type || 'highlights',
      newLabel: gallery.label || '',
      newDeptId: gallery.department_id ? String(gallery.department_id) : '',
      newDeptName: gallery.department_name || '',
      newQ: gallery.q || '',
      newPublicDomain: gallery.is_public_domain !== false,
      newDateBegin: gallery.date_begin ? String(gallery.date_begin) : '',
      newDateEnd: gallery.date_end ? String(gallery.date_end) : '',
      newMedium: gallery.medium || '',
      message: null,
    });
    // Pre-load departments if this gallery uses them
    if (gallery.type === 'department' || (gallery.type === 'search' && gallery.department_id)) {
      this.loadDepartments();
    }
  }

  _buildGalleryPayload() {
    const { newType, newLabel, newDeptId, newDeptName, newQ, newPublicDomain, newDateBegin, newDateEnd, newMedium } = this.state;

    // Resolve department name from loaded list if available
    let deptName = newDeptName;
    if (newDeptId && this.state.departments.length > 0) {
      const found = this.state.departments.find(d => String(d.departmentId) === String(newDeptId));
      if (found) deptName = found.displayName;
    }

    return {
      label: newLabel.trim(),
      type: newType,
      department_id: newDeptId ? parseInt(newDeptId, 10) : null,
      department_name: deptName || null,
      q: newQ.trim(),
      is_public_domain: newPublicDomain,
      date_begin: newDateBegin ? parseInt(newDateBegin, 10) : null,
      date_end: newDateEnd ? parseInt(newDateEnd, 10) : null,
      medium: newMedium.trim(),
    };
  }

  async addGallery() {
    const { newType, newLabel, newDeptId, newQ } = this.state;
    const label = newLabel.trim();
    if (!label) { this.setState({ message: { type: 'error', text: 'Gallery name is required' } }); return; }
    if (newType === 'department' && !newDeptId) { this.setState({ message: { type: 'error', text: 'Select a department' } }); return; }
    if (newType === 'search' && !newQ.trim()) { this.setState({ message: { type: 'error', text: 'Enter a search keyword' } }); return; }

    this.setState({ saving: true, message: null });
    try {
      const resp = await fetch(`${this.apiBase}/galleries`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this._buildGalleryPayload()),
      });
      if (!resp.ok) { const d = await resp.json(); throw new Error(d.detail || `HTTP ${resp.status}`); }
      const data = await resp.json();
      this.setState({
        saving: false,
        galleries: data.settings?.galleries || [],
        showAddPanel: false,
        editGalleryId: null,
        message: { type: 'success', text: `Gallery "${label}" created — fetching artworks in background…` },
      });
      setTimeout(() => this.loadStatus(), 3000);
    } catch (err) {
      this.setState({ saving: false, message: { type: 'error', text: `Failed to create gallery: ${err.message}` } });
    }
  }

  async saveEditGallery() {
    const { editGalleryId, newType, newLabel, newDeptId, newQ } = this.state;
    const label = newLabel.trim();
    if (!label) { this.setState({ message: { type: 'error', text: 'Gallery name is required' } }); return; }
    if (newType === 'department' && !newDeptId) { this.setState({ message: { type: 'error', text: 'Select a department' } }); return; }
    if (newType === 'search' && !newQ.trim()) { this.setState({ message: { type: 'error', text: 'Enter a search keyword' } }); return; }

    this.setState({ saving: true, message: null });
    try {
      const resp = await fetch(`${this.apiBase}/galleries/${encodeURIComponent(editGalleryId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this._buildGalleryPayload()),
      });
      if (!resp.ok) { const d = await resp.json(); throw new Error(d.detail || `HTTP ${resp.status}`); }
      const data = await resp.json();
      this.setState({
        saving: false,
        galleries: data.settings?.galleries || [],
        showAddPanel: false,
        editGalleryId: null,
        message: { type: 'success', text: `Gallery "${label}" updated — refreshing artworks in background…` },
      });
      setTimeout(() => this.loadStatus(), 3000);
    } catch (err) {
      this.setState({ saving: false, message: { type: 'error', text: `Failed to save gallery: ${err.message}` } });
    }
  }

  async deleteGallery(galleryId, label) {
    if (!confirm(`Remove gallery "${label}"?`)) return;
    this.setState({ saving: true, message: null });
    try {
      const resp = await fetch(`${this.apiBase}/galleries/${encodeURIComponent(galleryId)}`, { method: 'DELETE' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      this.setState({
        saving: false,
        galleries: data.settings?.galleries || [],
        message: { type: 'success', text: `Removed gallery "${label}"` },
      });
    } catch (err) {
      this.setState({ saving: false, message: { type: 'error', text: `Remove failed: ${err.message}` } });
    }
  }

  async refreshAll() {
    this.setState({ refreshing: true, message: null });
    try {
      await fetch(`${this.apiBase}/refresh`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      this.setState({ message: { type: 'info', text: 'Cache refresh started — may take a minute per gallery…' } });
      setTimeout(() => this.loadStatus(), 4000);
    } catch (err) {
      this.setState({ message: { type: 'error', text: `Refresh failed: ${err.message}` } });
    } finally {
      this.setState({ refreshing: false });
    }
  }

  async refreshGallery(galleryId) {
    try {
      await fetch(`${this.apiBase}/refresh`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ gallery: galleryId }) });
      this.setState({ message: { type: 'info', text: 'Refreshing gallery…' } });
      setTimeout(() => this.loadStatus(), 4000);
    } catch (err) {
      this.setState({ message: { type: 'error', text: `Refresh failed: ${err.message}` } });
    }
  }

  async saveDisplaySettings() {
    const root = this.shadowRoot;
    const patch = {
      fit_mode: root.querySelector('#setting-fit-mode')?.value || 'letterbox',
      image_quality: root.querySelector('#setting-image-quality')?.value || 'primary',
      cache_max_per_gallery: parseInt(root.querySelector('#setting-cache-max')?.value || '200', 10),
      refresh_interval_hours: parseInt(root.querySelector('#setting-refresh-hours')?.value || '168', 10),
    };
    this.setState({ saving: true, message: null });
    try {
      const payload = { ...(this.state.settings || {}), ...patch };
      const resp = await fetch(`${this.apiBase}/settings`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      this.setState({ saving: false, settings: data.settings, message: { type: 'success', text: 'Settings saved' } });
    } catch (err) {
      this.setState({ saving: false, message: { type: 'error', text: `Save failed: ${err.message}` } });
    }
  }

  _formatAge(fetchedAt) {
    if (!fetchedAt) return 'never';
    const mins = Math.round((Date.now() / 1000 - fetchedAt) / 60);
    if (mins < 2) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.round(hrs / 24)}d ago`;
  }

  _galleryDescription(g) {
    const parts = [];
    if (g.type === 'highlights') {
      parts.push('Met Highlights');
    } else if (g.type === 'department') {
      const deptLabel = g.department_name || (g.department_id ? `Dept ${g.department_id}` : 'All Departments');
      parts.push(deptLabel);
    } else if (g.type === 'search') {
      if (g.q) parts.push(`"${g.q}"`);
      if (g.department_name) parts.push(`in ${g.department_name}`);
      else if (g.department_id) parts.push(`in Dept ${g.department_id}`);
    }
    if (g.medium) parts.push(g.medium);
    if (g.date_begin || g.date_end) {
      parts.push(`${g.date_begin || '?'}–${g.date_end || 'present'}`);
    }
    if (!g.is_public_domain) parts.push('all rights');
    return parts.join(' · ');
  }

  _esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ------------------------------------------------------------------
  // Builders

  buildGalleryList() {
    const { galleries, cacheStats } = this.state;
    if (!galleries.length) {
      return `<div class="empty-state">No galleries configured. Add one below.</div>`;
    }
    return `<div class="gallery-list">${galleries.map(g => {
      const stat = cacheStats[g.id] || {};
      const count = (stat.count || 0).toLocaleString();
      const age = this._formatAge(stat.fetched_at);
      const typeClass = g.type || 'highlights';
      const typeLabel = GALLERY_TYPES.find(t => t.id === typeClass)?.name || typeClass;
      const desc = this._galleryDescription(g);
      const meta = `${desc ? desc + ' · ' : ''}${count} artworks · cached ${age}`;
      return `
        <div class="gallery-card">
          <div class="gallery-info">
            <div class="gallery-name">
              ${this._esc(g.label)}
              <span class="type-badge ${typeClass}">${typeLabel}</span>
            </div>
            <div class="gallery-meta">${meta}</div>
          </div>
          <div class="gallery-actions">
            <button class="btn btn-secondary btn-sm btn-icon" data-action="edit-gallery" data-id="${this._esc(g.id)}" title="Edit">✎</button>
            <button class="btn btn-secondary btn-sm btn-icon" data-action="refresh-gallery" data-id="${this._esc(g.id)}" title="Refresh">↻</button>
            <button class="btn btn-danger btn-sm btn-icon" data-action="delete-gallery" data-id="${this._esc(g.id)}" data-label="${this._esc(g.label)}" title="Remove">✕</button>
          </div>
        </div>`;
    }).join('')}</div>`;
  }

  buildAddPanel() {
    const {
      editGalleryId, newType, newLabel, newDeptId, newQ, newPublicDomain,
      newDateBegin, newDateEnd, newMedium, saving, departments, loadingDepts,
    } = this.state;
    const isEdit = !!editGalleryId;

    const deptOptions = loadingDepts
      ? `<option value="">Loading…</option>`
      : departments.length === 0
        ? `<option value="">— click to load —</option>`
        : [`<option value="">— ${newType === 'department' ? 'select department' : 'any department'} —</option>`,
           ...departments.map(d => `<option value="${d.departmentId}" ${String(newDeptId) === String(d.departmentId) ? 'selected' : ''}>${this._esc(d.displayName)}</option>`)
          ].join('');

    // Department field: required for 'department' type, optional filter for 'search'
    const deptField = `
      <div class="field">
        <label>${newType === 'department' ? 'Department' : 'Department (optional filter)'}</label>
        <select data-field="newDeptId" data-action="load-depts-on-focus">
          ${deptOptions}
        </select>
      </div>`;

    const searchField = `
      <div class="field" style="min-width:200px">
        <label>Keyword</label>
        <input type="text" placeholder="e.g. impressionism, portrait, armor…" value="${this._esc(newQ)}" data-field="newQ" />
      </div>`;

    // Search: keyword (required) + optional department on same row
    // Department: just department selector
    // Highlights: nothing
    let typeSpecificRow = '';
    if (newType === 'search') {
      typeSpecificRow = `<div class="input-row">${searchField}${deptField}</div>`;
    } else if (newType === 'department') {
      typeSpecificRow = `<div class="input-row">${deptField}</div>`;
    }

    return `
      <div class="add-panel">
        <div class="add-panel-header">
          <span class="section-title">${isEdit ? 'Edit Gallery' : 'Add Gallery'}</span>
          <button class="btn btn-ghost btn-sm" data-action="cancel-add">Cancel</button>
        </div>
        <div class="input-row">
          <div class="field field-label">
            <label>Gallery Name</label>
            <input type="text" placeholder="e.g. Japanese Art, Portraits…" value="${this._esc(newLabel)}" data-field="newLabel" />
          </div>
          <div class="field">
            <label>Type</label>
            <div class="type-selector">
              ${GALLERY_TYPES.map(t => `<button data-action="set-type" data-type="${t.id}" class="${newType === t.id ? 'active' : ''}" title="${t.description}">${t.name}</button>`).join('')}
            </div>
          </div>
        </div>
        ${typeSpecificRow}
        <div class="input-row" style="flex-wrap:wrap;gap:14px;align-items:flex-start">
          <div class="checkbox-row">
            <input type="checkbox" id="new-public-domain" ${newPublicDomain ? 'checked' : ''} data-field-check="newPublicDomain" />
            <label for="new-public-domain">Public domain only (recommended)</label>
          </div>
        </div>
        <div class="input-row">
          <div class="field">
            <label>Date From (year)</label>
            <input type="number" placeholder="e.g. 1800" min="1" max="2100" value="${this._esc(newDateBegin)}" data-field="newDateBegin" />
          </div>
          <div class="field">
            <label>Date To (year)</label>
            <input type="number" placeholder="e.g. 1900" min="1" max="2100" value="${this._esc(newDateEnd)}" data-field="newDateEnd" />
          </div>
          <div class="field">
            <label>Medium (optional)</label>
            <input type="text" placeholder="e.g. Oil on canvas" value="${this._esc(newMedium)}" data-field="newMedium" />
            <span class="field-hint">Filters to a specific material or technique</span>
          </div>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:8px">
          <button class="btn btn-primary" data-action="submit-gallery" ${saving ? 'disabled' : ''}>
            ${saving ? `<span class="spinner"></span> ${isEdit ? 'Saving…' : 'Creating…'}` : (isEdit ? 'Save Changes' : '+ Create Gallery')}
          </button>
        </div>
      </div>`;
  }

  buildSettingsPanel() {
    const s = this.state.settings || {};
    if (!this.state.showSettings) return '';
    return `
      <div class="settings-panel">
        <div class="section-title">Display Settings</div>
        <div class="settings-row">
          <div class="field">
            <label for="setting-fit-mode">Fit Mode</label>
            <select id="setting-fit-mode">
              <option value="letterbox" ${(!s.fit_mode || s.fit_mode === 'letterbox') ? 'selected' : ''}>Letterbox</option>
              <option value="crop"      ${s.fit_mode === 'crop'    ? 'selected' : ''}>Crop</option>
              <option value="stretch"   ${s.fit_mode === 'stretch' ? 'selected' : ''}>Stretch</option>
            </select>
          </div>
          <div class="field">
            <label for="setting-image-quality">Image Quality</label>
            <select id="setting-image-quality">
              <option value="primary" ${(!s.image_quality || s.image_quality === 'primary') ? 'selected' : ''}>Full Resolution</option>
              <option value="small"   ${s.image_quality === 'small' ? 'selected' : ''}>Web Thumbnail (faster)</option>
            </select>
          </div>
          <div class="field">
            <label for="setting-cache-max">Max Artworks / Gallery</label>
            <input id="setting-cache-max" type="number" min="20" max="500" value="${s.cache_max_per_gallery || 200}" />
          </div>
          <div class="field">
            <label for="setting-refresh-hours">Refresh (hours)</label>
            <input id="setting-refresh-hours" type="number" min="1" max="720" value="${s.refresh_interval_hours || 168}" />
          </div>
        </div>
        <div class="settings-actions">
          <button class="btn btn-primary btn-sm" data-action="save-settings">Save Settings</button>
        </div>
      </div>`;
  }

  render() {
    const { loading, refreshing, message, showAddPanel, showSettings } = this.state;
    const msgHtml = message ? `
      <div class="status-msg ${message.type}">
        <span>${message.type === 'success' ? '✓' : message.type === 'error' ? '✕' : '⟳'}</span>
        ${this._esc(message.text)}
      </div>` : '';

    if (loading) {
      this.shadowRoot.innerHTML = `<style>${CSS}</style>
        <div class="manager"><div class="status-msg info"><span class="spinner"></span> Loading…</div></div>`;
      return;
    }

    this.shadowRoot.innerHTML = `
      <style>${CSS}</style>
      <div class="manager">
        <div class="section">
          <div class="section-header">
            <span class="section-title">Galleries</span>
            <div style="display:flex;gap:6px">
              <button class="btn btn-ghost btn-sm" data-action="toggle-settings">${showSettings ? 'Hide Settings' : 'Settings'}</button>
              <button class="btn btn-secondary btn-sm" data-action="refresh-all" ${refreshing ? 'disabled' : ''}>
                ${refreshing ? '<span class="spinner"></span>' : '↻'} Refresh All
              </button>
              ${!showAddPanel ? `<button class="btn btn-primary btn-sm" data-action="show-add">+ Add Gallery</button>` : ''}
            </div>
          </div>
          ${this.buildGalleryList()}
        </div>
        ${msgHtml}
        ${showAddPanel ? this.buildAddPanel() : ''}
        ${this.buildSettingsPanel()}
        <div class="attribution">
          Artwork data from the <a href="https://www.metmuseum.org/art/collection" target="_blank">Metropolitan Museum of Art Open Access Collection</a>.
          Images in the public domain via <a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank">CC0</a>.
        </div>
      </div>`;

    this._attachListeners();
  }

  _attachListeners() {
    const root = this.shadowRoot;

    root.querySelectorAll('[data-action]').forEach(el => {
      el.addEventListener('click', async () => {
        const a = el.dataset.action;
        if (a === 'show-add') {
          this._openAddPanel();
        } else if (a === 'cancel-add') {
          this.setState({ showAddPanel: false, editGalleryId: null, message: null });
        } else if (a === 'submit-gallery') {
          if (this.state.editGalleryId) {
            await this.saveEditGallery();
          } else {
            await this.addGallery();
          }
        } else if (a === 'edit-gallery') {
          const gallery = this.state.galleries.find(g => g.id === el.dataset.id);
          if (gallery) this._openEditPanel(gallery);
        } else if (a === 'delete-gallery') {
          await this.deleteGallery(el.dataset.id, el.dataset.label);
        } else if (a === 'refresh-all') {
          await this.refreshAll();
        } else if (a === 'refresh-gallery') {
          await this.refreshGallery(el.dataset.id);
        } else if (a === 'toggle-settings') {
          this.setState({ showSettings: !this.state.showSettings, message: null });
        } else if (a === 'save-settings') {
          await this.saveDisplaySettings();
        } else if (a === 'set-type') {
          const newType = el.dataset.type;
          this.setState({ newType, newDeptId: '', newDeptName: '', newQ: '', message: null });
          if (newType === 'department' || newType === 'search') this.loadDepartments();
        }
      });
    });

    // Load departments when department select is focused/clicked
    const deptSelect = root.querySelector('[data-action="load-depts-on-focus"]');
    if (deptSelect) {
      deptSelect.addEventListener('focus', () => this.loadDepartments());
      deptSelect.addEventListener('mousedown', () => this.loadDepartments());
    }

    // Two-way bind all text/select/number inputs
    root.querySelectorAll('[data-field]').forEach(el => {
      el.addEventListener('input', () => { this.state[el.dataset.field] = el.value; });
      el.addEventListener('change', () => { this.state[el.dataset.field] = el.value; });
    });

    // Checkbox binding
    root.querySelectorAll('[data-field-check]').forEach(el => {
      el.addEventListener('change', () => { this.state[el.dataset.fieldCheck] = el.checked; });
    });
  }
}

customElements.define('x-met-art-manager', MetArtManager);
export default MetArtManager;
