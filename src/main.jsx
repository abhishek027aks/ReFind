import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Bell, CheckCircle2, ChevronRight, ClipboardCheck, Clock3, FileSearch, MapPin, Menu, Plus, Search, ShieldCheck, Sparkles, X } from 'lucide-react';
import './styles.css';
import './additions.css';

const fallbackReports = [
  { id: 1, kind: 'found', name: 'Black Samsung Galaxy', category: 'Electronics', location: 'Central Library', description: 'Black phone with a slim protective case, found near the reading desks.', status: 'possible_match', created_at: '2026-09-04T10:24:00+00:00', photo_url: null },
  { id: 2, kind: 'lost', name: 'Blue Hydro Flask', category: 'Personal items', location: 'Room 204, Science Block', description: 'Blue bottle with a small superhero sticker and metal cap.', status: 'possible_match', created_at: '2026-09-03T12:00:00+00:00', photo_url: null },
  { id: 3, kind: 'found', name: 'Student ID card', category: 'Documents', location: 'North Canteen', description: 'ID safely held by the campus security desk.', status: 'open', created_at: '2026-09-03T08:45:00+00:00', photo_url: null },
  { id: 4, kind: 'lost', name: 'Canvas tote bag', category: 'Bags', location: 'Parking area', description: 'Cream canvas tote with class notes and a green keychain.', status: 'open', created_at: '2026-09-02T14:10:00+00:00', photo_url: null },
];

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001';
const CACHE_TTL = 300000;

const readCache = (key) => {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || !data.expiresAt || data.expiresAt < Date.now()) {
      localStorage.removeItem(key);
      return null;
    }
    return data.value;
  } catch {
    return null;
  }
};

const writeCache = (key, value) => {
  localStorage.setItem(key, JSON.stringify({ value, expiresAt: Date.now() + CACHE_TTL }));
};

const fetchJson = async (url, options = {}, cacheKey = null) => {
  if (cacheKey) {
    const cached = readCache(cacheKey);
    if (cached) return cached;
  }

  let lastError;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await fetch(url, options);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Request failed');
      if (cacheKey) writeCache(cacheKey, payload);
      return payload;
    } catch (error) {
      lastError = error;
      if (attempt === 2) break;
      await new Promise(resolve => setTimeout(resolve, 200 * (attempt + 1)));
    }
  }
  throw lastError || new Error('Request failed');
};

const formatReport = (report) => ({
  ...report,
  type: report.kind,
  place: report.location,
  detail: report.description,
  date: new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(new Date(report.created_at)),
  tag: ({ Electronics: 'Phone', Documents: 'ID card', Bags: 'Bag', 'Personal items': 'Bottle', Keys: 'Key' }[report.category] || 'Item'),
  score: report.status === 'possible_match' ? 87 : 0,
  image: report.photo_url ? `${API}${report.photo_url}` : null,
});

function App() {
  const [tab, setTab] = useState('discover');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('All');
  const [modal, setModal] = useState(null);
  const [notice, setNotice] = useState('');
  const [reports, setReports] = useState(fallbackReports.map(formatReport));
  const [online, setOnline] = useState(false);
  const [auth, setAuth] = useState(null);
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('refind-user')); } catch { return null; }
  });
  const [notifications, setNotifications] = useState([]);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [dashboard, setDashboard] = useState({ reports: [], claims: [], matches: [] });
  const [sortMode, setSortMode] = useState('newest');
  const [discoverStats, setDiscoverStats] = useState({
    total_reports: 0,
    lost_reports: 0,
    found_reports: 0,
    possible_matches: 0,
    pending_claims: 0,
    successful_returns: 0,
  });
  const [loadingReports, setLoadingReports] = useState(true);

  const loadReports = async () => {
    setLoadingReports(true);
    try {
      const data = await fetchJson(`${API}/reports`, {}, 'refind-reports');
      setReports(data.map(formatReport));
      setOnline(true);
    } catch {
      setReports(fallbackReports.map(formatReport));
      setOnline(false);
    } finally {
      setLoadingReports(false);
    }
  };

  const loadSummary = async () => {
    try {
      const stats = await fetchJson(`${API}/reports/summary`, {}, 'refind-summary');
      setDiscoverStats(stats);
    } catch {
      setDiscoverStats({ total_reports: 0, lost_reports: 0, found_reports: 0, possible_matches: 0, pending_claims: 0, successful_returns: 0 });
    }
  };

  const loadDashboard = async () => {
    const token = localStorage.getItem('refind-token');
    if (!token || !user) return;
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [reportsRes, claimsRes, matchesRes] = await Promise.all([
        fetchJson(`${API}/reports/my`, { headers }, `refind-my-reports-${user.id}`),
        fetchJson(`${API}/claims/my`, { headers }, `refind-my-claims-${user.id}`),
        fetchJson(`${API}/matches`, { headers }, `refind-my-matches-${user.id}`),
      ]);
      setDashboard({ reports: reportsRes, claims: claimsRes, matches: matchesRes });
    } catch {
      setDashboard({ reports: [], claims: [], matches: [] });
    }
  };

  const loadNotifications = async () => {
    const token = localStorage.getItem('refind-token');
    if (!token) {
      setAuth('login');
      return;
    }

    try {
      const response = await fetch(`${API}/notifications`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error();
      setNotifications(await response.json());
      setNotificationsOpen(true);
    } catch {
      setNotice('Unable to load notifications. Please sign in again.');
    }
  };

  useEffect(() => { loadReports(); loadSummary(); }, []);
  useEffect(() => { if (user && tab === 'dashboard') loadDashboard(); }, [user, tab]);

  const filtered = useMemo(() => {
    const next = reports.filter(item => {
      const matchesFilter = filter === 'All' || item.type === filter;
      const matchesText = `${item.name} ${item.category} ${item.place} ${item.detail}`.toLowerCase().includes(query.toLowerCase());
      return matchesFilter && matchesText;
    });

    return next.sort((a, b) => {
      if (sortMode === 'match') return (b.score || 0) - (a.score || 0);
      if (sortMode === 'oldest') return new Date(a.created_at) - new Date(b.created_at);
      return new Date(b.created_at) - new Date(a.created_at);
    });
  }, [reports, query, filter, sortMode]);

  const submit = async (event) => {
    event.preventDefault();
    const token = localStorage.getItem('refind-token');
    if (!token) {
      setModal(null);
      setAuth('login');
      setNotice('Please sign in before submitting a report or claim.');
      return;
    }

    const form = new FormData(event.currentTarget);
    const target = typeof modal === 'object' ? modal : { type: modal, report_id: 1 };
    const isClaim = target.type === 'claim';
    const payload = isClaim
      ? { report_id: target.report_id, ownership_detail: form.get('description'), return_point: form.get('location') }
      : { kind: target.type, name: form.get('name'), category: form.get('category'), location: form.get('location'), description: form.get('description'), photo_url: null };

    try {
      const photo = form.get('photo');
      if (!isClaim && photo && photo.size) {
        const upload = new FormData();
        upload.append('file', photo);
        const uploadResponse = await fetch(`${API}/uploads`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: upload,
        });
        const uploaded = await uploadResponse.json();
        if (!uploadResponse.ok) throw new Error(uploaded.detail || 'Photo upload failed');
        payload.photo_url = uploaded.photo_url;
      }

      const response = await fetch(`${API}${isClaim ? '/claims' : '/reports'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Unable to submit');

      setModal(null);
      localStorage.removeItem('refind-reports');
      localStorage.removeItem('refind-summary');
      await loadReports();
      if (user && tab === 'dashboard') await loadDashboard();
      setNotice(isClaim ? 'Secure claim submitted for admin verification.' : result.possible_matches?.length ? `Report submitted - ${result.possible_matches.length} possible match(es) found.` : 'Report submitted. We will alert you when a safe possible match is found.');
    } catch (problem) {
      setNotice(problem.message);
    }
  };

  return <div>
    <header className="nav">
      <a className="brand" onClick={() => setTab('discover')}><span>R</span>ReFind</a>
      <nav>
        <a className={tab === 'discover' ? 'active' : ''} onClick={() => setTab('discover')}>Discover</a>
        {user && <a className={tab === 'dashboard' ? 'active' : ''} onClick={() => setTab('dashboard')}>Dashboard</a>}
        <a className={tab === 'how' ? 'active' : ''} onClick={() => setTab('how')}>How it works</a>
        {user?.role === 'admin' && <a className={tab === 'admin' ? 'active' : ''} onClick={() => setTab('admin')}>Admin</a>}
      </nav>
      <div className="nav-actions">
        <span style={{ fontSize: 11, color: online ? '#216142' : '#8b6c46' }}>{online ? '? Live' : '? Demo'}</span>
        <button className="icon" aria-label="Notifications" onClick={loadNotifications}><Bell size={19} /><i /></button>
        <button className="avatar" title={user ? `Sign out ${user.name}` : 'Sign in'} onClick={() => {
          if (user) {
            localStorage.removeItem('refind-token');
            localStorage.removeItem('refind-user');
            setUser(null);
            setDashboard({ reports: [], claims: [], matches: [] });
            setNotice('You have been signed out.');
          } else {
            setAuth('login');
          }
        }}>{user ? user.name.split(' ').map(part => part[0]).join('').slice(0, 2).toUpperCase() : 'IN'}</button>
      </div>
    </header>

    {notice && <div className="toast"><CheckCircle2 size={19} />{notice}<button onClick={() => setNotice('')}><X size={17} /></button></div>}

    {tab === 'discover' && <main>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow"><Sparkles size={15} /> SMART CAMPUS LOST & FOUND</p>
          <h1>Lost something?<br /><em>Let?s bring it home.</em></h1>
          <p className="lede">ReFind helps your campus reconnect people with what matters ? through secure reports, smart matching, and safe verification.</p>
          <div className="hero-buttons">
            <button className="primary" onClick={() => setModal({ type: 'lost' })}><Plus size={18} /> Report lost item</button>
            <button className="secondary" onClick={() => setModal({ type: 'found' })}><Search size={18} /> Report found item</button>
          </div>
          <div className="trust"><ShieldCheck size={20} /><span>Your contact details are never shown publicly.</span></div>
          <div className="stat-strip">
            <div className="stat-pill"><b>{discoverStats.total_reports ?? 0}</b><span>Campus reports</span></div>
            <div className="stat-pill"><b>{discoverStats.possible_matches ?? 0}</b><span>Live matches</span></div>
            <div className="stat-pill"><b>{discoverStats.successful_returns ?? 0}</b><span>Returns</span></div>
          </div>
        </div>
        <div className="hero-art">
          <div className="orbit orbit1" />
          <div className="orbit orbit2" />
          <div className="match-card">
            <div className="match-head"><span className="mini-icon">?</span><div><b>Potential match found</b><small>We found something similar</small></div><span className="score">91%</span></div>
            <div className="item-preview"><div className="phone"><div /></div><div><b>Black Samsung Galaxy</b><p><MapPin size={14} /> Central Library</p><p><Clock3 size={14} /> Found 18 min ago</p></div></div>
            <button onClick={() => setModal({ type: 'claim', report_id: 1 })}>Review match <ChevronRight size={16} /></button>
          </div>
          <div className="floating found">? Found</div>
          <div className="floating safe"><ShieldCheck size={17} /> Private & secure</div>
        </div>
      </section>

      <section className="finder">
        <div>
          <p className="eyebrow">FIND WHAT YOU NEED</p>
          <h2>Browse campus reports</h2>
          <p>Search recent lost and found reports. Details that could identify an owner stay private until a claim is verified.</p>
        </div>
        <div className="searchbox"><Search size={20} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search items, places, categories..." /><button>Search</button></div>
      </section>

      <section className="content">
        <div className="filters">
          <button className={filter === 'All' ? 'selected' : ''} onClick={() => setFilter('All')}>All reports</button>
          <button className={filter === 'lost' ? 'selected' : ''} onClick={() => setFilter('lost')}>Lost</button>
          <button className={filter === 'found' ? 'selected' : ''} onClick={() => setFilter('found')}>Found</button>
          <div className="filters-right">
            <select value={sortMode} onChange={e => setSortMode(e.target.value)}>
              <option value="newest">Newest</option>
              <option value="oldest">Oldest</option>
              <option value="match">Best match</option>
            </select>
            <span>{filtered.length} reports</span>
          </div>
        </div>
        {loadingReports ? <div className="empty-state">Loading campus reports...</div> : filtered.length ? <div className="grid">{filtered.map(item => <article className="report" key={item.id}><div className={`visual ${item.tag.replace(' ', '').toLowerCase()}`}>{item.image ? <img src={item.image} alt={item.name} /> : null}<span>{item.tag}</span>{item.score > 0 && <b><Sparkles size={13} />{item.score}% match</b>}</div><div className="report-body"><div className="report-meta"><span className={item.type}>{item.type}</span><small>{item.category}</small></div><h3>{item.name}</h3><p className="place"><MapPin size={15} />{item.place}</p><p className="detail">{item.detail}</p><footer><span><Clock3 size={14} />{item.date}</span><button onClick={() => setModal({ type: item.score ? 'claim' : 'details', report_id: item.id, report: item })}>{item.score ? 'View match' : 'View safely'} <ChevronRight size={15} /></button></footer></div></article>)}</div> : <div className="empty-state">No reports match your search. Try another keyword or filter.</div>}
      </section>

      <section className="steps">
        <div><p className="eyebrow">SIMPLE, SAFE, HUMAN</p><h2>How ReFind works</h2></div>
        <div className="step-list">
          <div><span>01</span><h3>Report</h3><p>Share a few non-sensitive details and where you last saw it.</p></div>
          <div><span>02</span><h3>Match</h3><p>Our matching engine looks for promising connections.</p></div>
          <div><span>03</span><h3>Verify & return</h3><p>Prove ownership privately, then arrange a safe return.</p></div>
        </div>
      </section>
    </main>}

    {tab === 'dashboard' && <Dashboard user={user} data={dashboard} openReportModal={() => setModal({ type: 'lost' })} />}
    {tab === 'how' && <InfoPage title="A safer path from lost to found" text="ReFind keeps sensitive details private, notifies the right people when reports align, and puts a campus administrator in the verification loop." />}
    {tab === 'admin' && <Admin user={user} />}

    {modal && <Modal type={modal} close={() => setModal(null)} openClaim={reportId => setModal({ type: 'claim', report_id: reportId })} submit={submit} />}
    {auth && <AuthModal mode={auth} close={() => setAuth(null)} success={loggedIn => { setUser(loggedIn); localStorage.setItem('refind-user', JSON.stringify(loggedIn)); setAuth(null); setNotice(`Welcome, ${loggedIn.name}.`); }} />}
    {notificationsOpen && <NotificationPanel items={notifications} close={() => setNotificationsOpen(false)} />}

    <footer className="site-footer"><span className="brand"><span>R</span>ReFind</span><p>Find it. Verify it. Get it back.</p><small>Built for a kinder, more connected campus.</small></footer>
  </div>;
}

function Dashboard({ user, data, openReportModal }) {
  if (!user) return <main className="page"><p className="eyebrow">MY DASHBOARD</p><h1>Sign in to manage your campus activity</h1><p className="lede">Track your reports, claims, and secure match updates from one place.</p></main>;

  return <main className="admin">
    <div>
      <p className="eyebrow">USER DASHBOARD</p>
      <h1>Welcome back, {user.name}</h1>
      <p>Keep track of your reports, alerts, and secure return progress.</p>
    </div>
    <section className="stats">
      <Stat value={data.reports.length} label="My reports" />
      <Stat value={data.claims.length} label="My claims" />
      <Stat value={data.matches.filter(match => match.status === 'open').length} label="Open matches" />
      <Stat value={user.role === 'admin' ? 'Admin' : 'Student'} label="Role" />
    </section>
    <section className="admin-grid">
      <div className="panel">
        <h2>Recent reports</h2>
        {data.reports.length ? data.reports.map(report => <div className="claim" key={report.id}><span>{report.kind[0].toUpperCase()}</span><div><b>{report.name}</b><small>{report.category} ? {report.status}</small></div><button onClick={openReportModal}>Update</button></div>) : <p className="detail">You have not posted any reports yet.</p>}
      </div>
      <div className="panel">
        <h2>My claims</h2>
        {data.claims.length ? data.claims.map(claim => <div className="claim" key={claim.id}><span>?</span><div><b>{claim.report_name}</b><small>{claim.status}</small></div></div>) : <p className="detail">No claims submitted yet.</p>}
      </div>
    </section>
    <section className="panel" style={{ marginTop: '18px' }}>
      <h2>Possible matches</h2>
      {data.matches.length ? data.matches.map(match => <div className="claim" key={match.id}><span>{match.score}%</span><div><b>{match.lost_name} ? {match.found_name}</b><small>{match.status}</small></div></div>) : <p className="detail">No active matches are available right now.</p>}
    </section>
  </main>;
}

function InfoPage({ title, text }) {
  return <main className="page"><p className="eyebrow">HOW IT WORKS</p><h1>{title}</h1><p className="lede">{text}</p><div className="process"><ClipboardCheck /><ChevronRight /><FileSearch /><ChevronRight /><ShieldCheck /></div></main>;
}

function Admin({ user }) {
  const [summary, setSummary] = useState(null);
  const [claims, setClaims] = useState([]);
  const [error, setError] = useState('');

  const refresh = async () => {
    const token = localStorage.getItem('refind-token');
    if (!token || user?.role !== 'admin') return;
    const headers = { Authorization: `Bearer ${token}` };
    try {
      const responses = await Promise.all([
        fetch(`${API}/admin/summary`, { headers }),
        fetch(`${API}/admin/claims`, { headers }),
      ]);
      if (!responses[0].ok) throw new Error('Admin access required');
      setSummary(await responses[0].json());
      setClaims(await responses[1].json());
    } catch (problem) {
      setError(problem.message);
    }
  };

  const updateStatus = async (claimId, status) => {
    const token = localStorage.getItem('refind-token');
    if (!token) return;
    try {
      const response = await fetch(`${API}/admin/claims/${claimId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) throw new Error('Failed to update claim');
      await refresh();
    } catch (problem) {
      setError(problem.message);
    }
  };

  useEffect(() => { refresh(); }, [user]);

  if (user?.role !== 'admin') return <main className="page"><p className="eyebrow">ADMIN AREA</p><h1>Administrator access required</h1><p className="lede">Sign in with an administrator account to review claims, flag reports, and track campus returns.</p></main>;
  if (error) return <main className="page"><h1>{error}</h1></main>;

  return <main className="admin">
    <div>
      <p className="eyebrow">ADMIN DASHBOARD</p>
      <h1>Campus overview</h1>
      <p>Review activity, protect the community, and make returns happen.</p>
    </div>
    <section className="stats">
      <Stat value={summary?.total_users ?? '-'} label="Total users" />
      <Stat value={summary?.lost_reports ?? '-'} label="Lost reports" />
      <Stat value={summary?.found_reports ?? '-'} label="Found reports" />
      <Stat value={summary?.successful_returns ?? '-'} label="Successful returns" />
    </section>
    <section className="admin-grid">
      <div className="panel">
        <h2>Claims requiring review</h2>
        {claims.length ? claims.map((claim, i) => <div className="claim" key={claim.id}><span>{i + 1}</span><div><b>{claim.report_name}</b><small>{claim.claimant} ? {claim.status} ? {claim.return_point}</small></div><div style={{ display: 'flex', gap: '6px' }}><button onClick={() => updateStatus(claim.id, 'verified')}>Approve</button><button style={{ color: '#a65535', borderColor: '#a65535' }} onClick={() => updateStatus(claim.id, 'flagged')}>Flag</button></div></div>) : <p className="detail">No claims are waiting for review.</p>}
      </div>
      <div className="panel">
        <h2>Report health</h2>
        <div className="metric"><b>{summary?.pending_claims ?? '-'}</b><span>Pending claims</span></div>
        <div className="metric"><b>{summary?.flagged_reports ?? '-'}</b><span>Flagged reports</span></div>
        <div className="metric"><b>{summary?.total_reports ?? '-'}</b><span>Total reports</span></div>
        <div className="metric"><b>Private</b><span>Contact details protected</span></div>
      </div>
    </section>
  </main>;
}

function Stat({ value, label }) {
  return <div><b>{value}</b><span>{label}</span></div>;
}

function Modal({ type, close, openClaim, submit }) {
  const modalType = typeof type === 'object' ? type.type : type;
  const report = typeof type === 'object' ? type.report : null;
  const title = modalType === 'claim' ? 'Claim this item' : modalType === 'details' ? 'Protected report details' : modalType === 'lost' ? 'Report a lost item' : 'Report a found item';
  return <div className="overlay" onMouseDown={close}><form className="modal" onSubmit={submit} onMouseDown={e => e.stopPropagation()}><button type="button" className="close" onClick={close}><X /></button><p className="eyebrow">REFIND SECURE FLOW</p><h2>{title}</h2>{modalType === 'claim' ? <><p>Help us confirm ownership without posting private details.</p><label>What detail would only the owner know?<textarea required name="description" placeholder="For example: case color, a small mark, lock-screen detail..." /></label><label>Preferred safe return point<select required name="location"><option value="">Choose a point</option><option>Campus security office</option><option>Central library help desk</option><option>Student services</option></select></label></> : modalType === 'details' ? <><p>Review the report privately and choose whether to file a verified claim.</p>{report && <div className="detail-panel"><h3>{report.name}</h3><p><strong>Type:</strong> {report.kind}</p><p><strong>Location:</strong> {report.place}</p><p><strong>Category:</strong> {report.category}</p><p><strong>Description:</strong> {report.detail}</p></div>}<button className="primary submit" type="button" onClick={() => openClaim(type.report_id)}>Start secure claim</button></> : <><label>Item name<input required name="name" placeholder="e.g. Black Samsung Galaxy" /></label><label>Category<select name="category"><option>Electronics</option><option>Documents</option><option>Bags</option><option>Personal items</option><option>Keys</option></select></label><label>Where was it {modalType === 'lost' ? 'last seen' : 'found'}?<input required name="location" placeholder="e.g. Central Library" /></label><label>Helpful description<textarea required name="description" placeholder="Colour, time, and non-sensitive identifying details..." /></label><label>Item photo (optional)<input type="file" name="photo" accept="image/png,image/jpeg,image/webp" /></label></> }{modalType !== 'details' && <button className="primary submit" type="submit">{modalType === 'claim' ? 'Submit secure claim' : 'Submit report'}<ChevronRight size={18} /></button>}</form></div>;
}

function NotificationPanel({ items, close }) {
  return <div className="overlay" onMouseDown={close}><section className="modal" onMouseDown={event => event.stopPropagation()}><button className="close" onClick={close}><X /></button><p className="eyebrow">YOUR NOTIFICATIONS</p><h2>Updates</h2>{items.length ? items.map(item => <div className="claim" key={item.id}><span>?</span><div><b>{item.kind}</b><small>{item.message}</small></div></div>) : <p className="detail">You are all caught up. New match and claim updates will appear here.</p>}</section></div>;
}

function AuthModal({ mode, close, success }) {
  const [register, setRegister] = useState(mode === 'register');
  const [error, setError] = useState('');

  const send = async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = { email: form.get('email'), password: form.get('password') };
    if (register) body.name = form.get('name');

    try {
      const response = await fetch(`${API}/auth/${register ? 'register' : 'login'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Unable to continue');
      localStorage.setItem('refind-token', result.token);
      success(result.user);
    } catch (problem) {
      setError(problem.message);
    }
  };

  return <div className="overlay" onMouseDown={close}><form className="modal" onSubmit={send} onMouseDown={event => event.stopPropagation()}><button type="button" className="close" onClick={close}><X /></button><p className="eyebrow">REFIND ACCOUNT</p><h2>{register ? 'Create your account' : 'Welcome back'}</h2><p>{register ? 'Join your campus community to report and securely claim items.' : 'Sign in to keep track of your reports and claims.'}</p>{register && <label>Your name<input required name="name" placeholder="Your full name" /></label>}<label>Campus email<input required type="email" name="email" placeholder="you@college.edu" /></label><label>Password<input required type="password" name="password" minLength="8" placeholder="At least 8 characters" /></label>{error && <p style={{ color: '#a65535' }}>{error}</p>}<button className="primary submit" type="submit">{register ? 'Create account' : 'Sign in'}<ChevronRight size={18} /></button><button type="button" style={{ display: 'block', margin: '14px auto 0', border: 0, background: 'transparent', color: 'var(--green)', fontSize: 12, fontWeight: 700 }} onClick={() => { setRegister(!register); setError(''); }}>{register ? 'Already have an account? Sign in' : 'New here? Create an account'}</button></form></div>;
}

createRoot(document.getElementById('root')).render(<App />);
