import { useEffect, useRef, useState } from 'react';
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from 'react-router-dom';
import { useIsFetching, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  ArrowRight,
  Bell,
  CalendarDays,
  ChevronDown,
  Command,
  Database,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Maximize2,
  Menu,
  Moon,
  PanelLeft,
  Search,
  Server,
  Settings2,
  ShieldCheck,
  Sun,
  Users,
  Workflow,
  X,
} from 'lucide-react';
import { api, ApiError, setCsrf } from './api/client';
import type { Schema } from './api/client';
import { useLiveEvents } from './api/useLiveEvents';
import { AppContext } from './AppContext';
import { APP_NAME, API_POLL_MS } from './config';
import { ErrorState, Loading, Time } from './components/ui';
import { StatusPill } from './components/StatusPill';
import { Login } from './pages/Login';
import { Overview } from './pages/Overview';
import { Tenants, TenantDetail } from './pages/Tenants';
import { Runs, RunDetail } from './pages/Runs';
import { Errors } from './pages/Errors';
import { Freshness } from './pages/Freshness';
import { Alerts } from './pages/Alerts';
import { Onboarding } from './pages/Onboarding';
import { Admin, Platform, SearchResults } from './pages/System';
import { Quality } from './pages/Quality';
import { Warehouse } from './pages/Warehouse';
import { Account } from './pages/Account';
import { Pipelines } from './pages/Pipelines';
import { Access } from './pages/Access';
import { Dependencies } from './pages/Dependencies';
import { Activity as ActivityPage } from './components/Investigation';

function localInputTime(iso: string | null) {
  if (!iso) return undefined;
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

const NAV = [
  {
    group: 'WORKSPACE',
    items: [
      { path: '/', label: 'Overview', icon: LayoutDashboard },
      { path: '/tenants', label: 'Tenants', icon: Users },
      { path: '/pipelines', label: 'Orchestration', icon: Workflow },
      { path: '/runs', label: 'Pipeline runs', icon: Activity },
      { path: '/activity', label: 'Activity', icon: CalendarDays },
    ],
  },
  {
    group: 'ANALYZE',
    items: [
      { path: '/errors', label: 'Errors', icon: ShieldCheck },
      { path: '/freshness', label: 'Freshness & volume', icon: Database },
      { path: '/warehouse', label: 'Warehouse', icon: Database },
      { path: '/dependencies', label: 'Dependencies', icon: Workflow },
      { path: '/quality', label: 'Data quality', icon: ShieldCheck },
      { path: '/alerts', label: 'Alerts', icon: Bell },
    ],
  },
  {
    group: 'MANAGE',
    items: [
      { path: '/platform', label: 'Platform', icon: Server },
      { path: '/access', label: 'Access & roles', icon: ShieldCheck },
      { path: '/admin', label: 'Administration', icon: Settings2 },
    ],
  },
];

export function App() {
  const runtime = useQuery({
    queryKey: ['config'],
    queryFn: () => api<Schema<'RuntimeConfig'>>('/config'),
    staleTime: Infinity,
    refetchInterval: false,
  });
  const me = useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      const user = await api<Schema<'User'>>('/me');
      setCsrf(user.csrf_token || '');
      return user;
    },
    retry: false,
    staleTime: API_POLL_MS,
  });
  useEffect(() => {
    document.title = APP_NAME;
  }, []);
  if (runtime.isPending)
    return (
      <div className="initial-loading">
        <Loading />
      </div>
    );
  if (runtime.error) return <ErrorState error={runtime.error} />;
  if (me.error instanceof ApiError && me.error.status === 401)
    return <Login config={runtime.data} />;
  if (me.isPending)
    return (
      <div className="initial-loading">
        <Workflow size={28} />
        <Loading />
      </div>
    );
  if (!me.data)
    return me.error instanceof ApiError && me.error.status === 401 ? (
      <Login config={runtime.data} />
    ) : (
      <ErrorState error={me.error || new Error('The API is unavailable.')} />
    );
  return <Workspace user={me.data} runtime={runtime.data} />;
}

function Workspace({ user, runtime }: { user: Schema<'User'>; runtime: Schema<'RuntimeConfig'> }) {
  const searchRef = useRef<HTMLInputElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const fetching = useIsFetching({
    predicate: (query) => !['me', 'config'].includes(String(query.queryKey[0])),
  });
  const live = useLiveEvents();
  const access = useQuery({
    queryKey: ['access'],
    queryFn: () => api<Schema<'AccessContext'>>('/access'),
  });
  const [theme, setTheme] = useState(() => localStorage.getItem('obs-theme') || 'light');
  const [textSize, setTextSize] = useState(() =>
    localStorage.getItem('obs-text-size') === 'large' ? 'large' : 'standard',
  );
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('obs-sidebar') === 'collapsed',
  );
  const [panel, setPanel] = useState<'none' | 'workspace' | 'bell' | 'profile'>('none');
  const [pwOpen, setPwOpen] = useState(false);
  const [toast, setToast] = useState('');
  const [menu, setMenu] = useState(false);
  const [search, setSearch] = useState('');
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const tv = params.get('tv') === '1';
  const range = params.get('range') || '24h';
  const logout = useMutation({
    mutationFn: () => api('/auth/logout', { method: 'POST' }),
    onSuccess: () => {
      client.clear();
      window.location.assign('/');
    },
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('obs-theme', theme);
  }, [theme]);
  useEffect(() => {
    document.documentElement.style.setProperty('zoom', textSize === 'large' ? '1.12' : '1');
    localStorage.setItem('obs-text-size', textSize);
  }, [textSize]);
  useEffect(() => {
    localStorage.setItem('obs-sidebar', collapsed ? 'collapsed' : 'open');
  }, [collapsed]);
  const firing = useQuery({
    queryKey: ['alerts', 'firing', 1],
    queryFn: () => api<Schema<'Page_Alert_'>>('/alerts?state=firing&page=1'),
    refetchInterval: 60_000,
  });
  useEffect(() => {
    setMenu(false);
    setPanel('none');
  }, [location.pathname]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(''), 7000);
    return () => clearTimeout(timer);
  }, [toast]);
  const rangeLink = (path: string) => {
    const q = new URLSearchParams();
    for (const k of ['range', 'from', 'to']) if (params.get(k)) q.set(k, params.get(k)!);
    return `${path}${q.size ? `?${q}` : ''}`;
  };
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === 'Escape') {
        setMenu(false);
        setPanel('none');
      }
    };
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, []);
  useEffect(() => {
    mainRef.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }, [location.pathname]);
  const section =
    NAV.flatMap((g) => g.items).find((v) =>
      v.path === '/' ? location.pathname === '/' : location.pathname.startsWith(v.path),
    )?.label || 'Search';
  return (
    <AppContext.Provider value={{ user, runtime, access: access.data, ...live, notify: setToast }}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <div className={`app-shell ${tv ? 'tv-mode' : ''} ${collapsed ? 'sidebar-collapsed' : ''}`}>
        {panel !== 'none' && (
          <div className="popover-scrim" onClick={() => setPanel('none')} aria-hidden />
        )}
        {!tv && (
          <aside
            className={`sidebar ${menu ? 'mobile-open' : ''} ${collapsed ? 'collapsed' : ''} ${panel === 'workspace' || panel === 'profile' ? 'panel-open' : ''}`}
          >
            <NavLink to="/" className="brand">
              <span className="brand-icon">
                <Workflow size={23} />
              </span>
              <span>
                {APP_NAME}
                <small>OPERATIONS PLATFORM</small>
              </span>
            </NavLink>
            <button
              className="workspace-switch"
              onClick={() => setPanel(panel === 'workspace' ? 'none' : 'workspace')}
              aria-expanded={panel === 'workspace'}
              title="Product navigation"
            >
              <span className="workspace-avatar">O</span>
              <div>
                <strong>Observability</strong>
                <small>{runtime.environment}</small>
              </div>
              <ChevronDown size={14} className="switch-chevron" />
            </button>
            {panel === 'workspace' && (
              <div className="popover workspace-pop product-menu">
                <span className="product-menu-label">YOUR PRODUCTS</span>
                <NavLink to="/" className="product-active">
                  <span className="workspace-avatar">O</span>
                  <span>
                    <strong>Observability</strong>
                    <small>Monitor data operations</small>
                  </span>
                  <span className="product-current">Current</span>
                </NavLink>
                <p>Additional business modules can be added here as they become available.</p>
                <NavLink to="/account" className="product-settings">
                  Account settings <ArrowRight size={14} />
                </NavLink>
              </div>
            )}
            <nav>
              {NAV.map((group) => (
                <div className="nav-group" key={group.group}>
                  <span className="nav-label">{group.group}</span>
                  {group.items
                    .filter((item) => item.path !== '/admin' || user.role === 'admin')
                    .filter((item) => item.path !== '/onboarding' || user.role !== 'viewer')
                    .map((item) => (
                      <NavLink key={item.path} to={rangeLink(item.path)} end={item.path === '/'}>
                        <item.icon size={17} />
                        <span>{item.label}</span>
                      </NavLink>
                    ))}
                </div>
              ))}
            </nav>
            <div className="sidebar-bottom">
              <label className="text-size-control">
                <span>Text size</span>
                <select
                  aria-label="Text size"
                  value={textSize}
                  onChange={(event) => setTextSize(event.target.value)}
                >
                  <option value="standard">Standard</option>
                  <option value="large">Large</option>
                </select>
              </label>
              <button
                className="collapse-toggle"
                onClick={() => setCollapsed(!collapsed)}
                title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              >
                <PanelLeft size={15} />
                <span>Collapse</span>
              </button>
              <div className="profile">
                <button
                  className="profile-main"
                  onClick={() => setPanel(panel === 'profile' ? 'none' : 'profile')}
                  aria-expanded={panel === 'profile'}
                  title="Account"
                >
                  <span className="profile-avatar">{user.display_name?.slice(0, 1)}</span>
                  <span className="profile-text">
                    <strong>{user.display_name}</strong>
                    <small>{user.role}</small>
                  </span>
                  <ChevronDown size={14} />
                </button>
                {panel === 'profile' && (
                  <div className="popover profile-pop">
                    <NavLink to="/account" className="button small">
                      Account settings
                    </NavLink>
                    <button
                      onClick={() => {
                        setPanel('none');
                        setPwOpen(true);
                      }}
                    >
                      <KeyRound size={14} /> Change password
                    </button>
                    <button onClick={() => logout.mutate()}>
                      <LogOut size={14} /> Sign out
                    </button>
                  </div>
                )}
              </div>
            </div>
          </aside>
        )}
        <div className="workspace-main">
          <header className="topbar">
            <div className="breadcrumb">
              <button
                className="mobile-menu"
                aria-label="Open navigation"
                onClick={() => setMenu(!menu)}
              >
                <Menu size={19} />
              </button>
              <Workflow size={15} />
              <NavLink to="/">Observability</NavLink>
              <span className="slash">/</span>
              <strong>{section}</strong>
            </div>
            <div className="topbar-actions">
              <form
                className="global-search"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (search.trim()) navigate(`/search?q=${encodeURIComponent(search.trim())}`);
                }}
              >
                <Search size={15} />
                <input
                  ref={searchRef}
                  aria-label="Search errors and logs"
                  placeholder="Search tenants, logs, pages…"
                  maxLength={200}
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                {search.trim() ? (
                  <button
                    type="submit"
                    aria-label="Submit global search"
                    className="global-search-submit"
                  >
                    Search
                  </button>
                ) : (
                  <Command size={12} aria-hidden="true" />
                )}
              </form>
              <span className={`live-indicator ${live.connected ? '' : 'disconnected'}`}>
                <span />
                {live.connected ? 'Live' : 'Polling · 30s'}
              </span>
              <div className="bell-wrap">
                <button
                  className="theme-toggle"
                  title="Notifications"
                  aria-label="Notifications"
                  aria-expanded={panel === 'bell'}
                  onClick={() => setPanel(panel === 'bell' ? 'none' : 'bell')}
                >
                  <Bell size={17} />
                  {firing.data && firing.data.total > 0 && (
                    <span className="bell-badge">{firing.data.total}</span>
                  )}
                </button>
                {panel === 'bell' && (
                  <div className="popover bell-pop">
                    <div className="bell-head">
                      <strong>Firing now</strong>
                      <NavLink to="/alerts">View all alerts</NavLink>
                    </div>
                    {firing.isPending ? (
                      <p className="muted bell-empty">Loading…</p>
                    ) : firing.data?.items.length ? (
                      firing.data.items.slice(0, 5).map((alert) => (
                        <NavLink key={alert.id} to="/alerts" className="bell-item">
                          <StatusPill status={alert.severity} />
                          <span className="bell-text">
                            <strong>{alert.title}</strong>
                            <small>
                              {alert.tenant_id || 'Platform'} ·{' '}
                              <Time value={alert.first_fired_at} relative />
                            </small>
                          </span>
                        </NavLink>
                      ))
                    ) : (
                      <p className="muted bell-empty">Nothing firing. All quiet.</p>
                    )}
                  </div>
                )}
              </div>
              <button
                className="theme-toggle"
                title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
                aria-label="Toggle color theme"
                onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
              >
                {theme === 'light' ? <Moon size={17} /> : <Sun size={17} />}
              </button>
            </div>
          </header>
          <div className="range-bar">
            <div className="demo-tag">
              <span />
              {runtime.environment.toUpperCase()}
              <span className="muted">All times shown in your local timezone</span>
            </div>
            <div className="inline-flex">
              <label className="range-picker">
                <CalendarDays size={14} />
                <select
                  aria-label="Global time range"
                  value={range}
                  onChange={(event) => {
                    const next = new URLSearchParams(params);
                    next.set('range', event.target.value);
                    next.delete('page');
                    setParams(next);
                  }}
                >
                  <option value="1h">Last hour</option>
                  <option value="6h">Last 6 hours</option>
                  <option value="24h">Last 24 hours</option>
                  <option value="7d">Last 7 days</option>
                  <option value="30d">Last 30 days</option>
                  <option value="custom">Custom range</option>
                </select>
              </label>
              <button
                className="icon-button"
                aria-label={tv ? 'Exit TV mode' : 'Open TV mode'}
                title="TV mode"
                onClick={() => {
                  const next = new URLSearchParams(params);
                  if (tv) next.delete('tv');
                  else next.set('tv', '1');
                  navigate(`/?${next}`);
                }}
              >
                {tv ? <X size={16} /> : <Maximize2 size={16} />}
              </button>
            </div>
          </div>
          {range === 'custom' && (
            <form
              className="custom-range"
              onSubmit={(event) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                const next = new URLSearchParams(params);
                next.set('from', new Date(String(data.get('from'))).toISOString());
                next.set('to', new Date(String(data.get('to'))).toISOString());
                setParams(next);
              }}
            >
              <label>
                From
                <input
                  name="from"
                  type="datetime-local"
                  required
                  defaultValue={localInputTime(params.get('from'))}
                />
              </label>
              <label>
                To
                <input
                  name="to"
                  type="datetime-local"
                  required
                  defaultValue={localInputTime(params.get('to'))}
                />
              </label>
              <button className="button primary">Apply range</button>
            </form>
          )}
          <div className={`refresh-progress ${fetching ? 'is-active' : ''}`} aria-hidden="true" />
          <main className="page-content" id="main-content" tabIndex={-1} ref={mainRef}>
            <div key={location.pathname} className="route-enter">
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/tenants" element={<Tenants />} />
                <Route path="/tenants/:id" element={<TenantDetail />} />
                <Route path="/runs" element={<Runs />} />
                <Route path="/runs/:key" element={<RunDetail />} />
                <Route path="/activity" element={<ActivityPage />} />
                <Route path="/pipelines" element={<Pipelines />} />
                <Route path="/workspace" element={<Navigate to="/" replace />} />
                <Route path="/workspace/pipelines" element={<Navigate to="/pipelines" replace />} />
                <Route path="/access" element={<Access />} />
                <Route path="/account" element={<Account />} />
                <Route path="/dependencies" element={<Dependencies />} />
                <Route path="/quality" element={<Quality />} />
                <Route path="/errors" element={<Errors />} />
                <Route path="/freshness" element={<Freshness />} />
                <Route path="/warehouse" element={<Warehouse />} />
                <Route path="/alerts" element={<Alerts />} />
                <Route path="/onboarding" element={<Onboarding />} />
                <Route path="/platform" element={<Platform />} />
                <Route path="/admin" element={<Admin />} />
                <Route path="/search" element={<SearchResults />} />
                <Route
                  path="*"
                  element={
                    <div className="empty">
                      <h1>Page not found</h1>
                      <NavLink to="/">Back to overview</NavLink>
                    </div>
                  }
                />
              </Routes>
            </div>
          </main>
          <footer className="app-footer">
            <span>
              <Workflow size={12} /> {APP_NAME}
            </span>
            <span>
              {runtime.environment} <i />{' '}
              {runtime.mode === 'demo' ? 'Simulated data' : 'Live integrations'}
            </span>
          </footer>
        </div>
        {pwOpen && <ChangePasswordModal onClose={() => setPwOpen(false)} notify={setToast} />}
        {toast && (
          <div className="toast" role="status">
            <ShieldCheck size={19} />
            <span>{toast}</span>
            <button aria-label="Dismiss notification" onClick={() => setToast('')}>
              <X size={15} />
            </button>
          </div>
        )}
      </div>
    </AppContext.Provider>
  );
}

function ChangePasswordModal({
  onClose,
  notify,
}: {
  onClose: () => void;
  notify: (message: string) => void;
}) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const mutation = useMutation({
    mutationFn: () =>
      api<Schema<'Message'>>('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: next }),
      }),
    onSuccess: () => {
      notify('Password changed. Use your new password the next time you sign in.');
      onClose();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not change the password.'),
  });
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    if (next.length < 8) return setError('New password must be at least 8 characters.');
    if (next !== confirm) return setError('New passwords do not match.');
    mutation.mutate();
  };
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Change password"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <strong>Change password</strong>
          <button className="icon-button" aria-label="Close" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <form onSubmit={submit} className="modal-form">
          <label>
            Current password
            <input
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              required
            />
          </label>
          <label>
            New password
            <input
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(event) => setNext(event.target.value)}
              required
            />
          </label>
          <label>
            Confirm new password
            <input
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              required
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="button" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="button primary" disabled={mutation.isPending}>
              {mutation.isPending ? 'Changing…' : 'Change password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
