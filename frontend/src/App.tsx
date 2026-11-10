import { useEffect, useRef, useState } from 'react';
import {
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from 'react-router-dom';
import { useIsFetching, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  ArrowUpRight,
  Bell,
  CalendarDays,
  Command,
  Database,
  LayoutDashboard,
  LogOut,
  Maximize2,
  Menu,
  Moon,
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
import { ErrorState, Loading } from './components/ui';
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
    setMenu(false);
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
      if (event.key === 'Escape') setMenu(false);
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
      <div className={`app-shell ${tv ? 'tv-mode' : ''}`}>
        {!tv && (
          <aside className={`sidebar ${menu ? 'mobile-open' : ''}`}>
            <NavLink to="/" className="brand">
              <span className="brand-icon">
                <Workflow size={23} />
              </span>
              <span>
                {APP_NAME}
                <small>PIPELINE CONSOLE</small>
              </span>
            </NavLink>
            <NavLink className="workspace-switch" to="/tenants" aria-label="Open tenant workspace">
              <span className="workspace-avatar">D</span>
              <div>
                <strong>Data workspace</strong>
                <small>{runtime.environment}</small>
              </div>
            </NavLink>
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
              <div className="environment-note">
                <ShieldCheck size={17} />
                <div>
                  <strong>
                    {runtime.mode === 'demo' ? 'Safe to explore' : 'Operations workspace'}
                  </strong>
                  <small>
                    {runtime.mode === 'demo'
                      ? 'Demo actions stay local.'
                      : runtime.live_actions_enabled
                        ? 'Live actions enabled'
                        : 'Read-only connections'}
                  </small>
                </div>
                <ArrowUpRight size={13} />
              </div>
              <div className="profile">
                <span className="profile-avatar">{user.display_name?.slice(0, 1)}</span>
                <div>
                  <strong>{user.display_name}</strong>
                  <small>{user.role}</small>
                </div>
                <button title="Sign out" aria-label="Sign out" onClick={() => logout.mutate()}>
                  <LogOut size={16} />
                </button>
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
              <span>Workspace</span>
              <span className="slash">/</span>
              <strong>{section}</strong>
            </div>
            <div className="topbar-actions">
              <form
                className="global-search"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (search.trim().length > 1)
                    navigate(`/search?q=${encodeURIComponent(search.trim())}`);
                }}
              >
                <Search size={15} />
                <input
                  ref={searchRef}
                  aria-label="Search errors and logs"
                  placeholder="Search errors & logs…"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                <Command size={12} />
              </form>
              <NavLink
                to="/alerts?state=firing"
                className="icon-button"
                aria-label="Open alerts"
                title="Open alerts"
              >
                <Bell size={18} />
              </NavLink>
              <NavLink
                to="/account"
                className="icon-button"
                aria-label="Account settings"
                title="Account settings"
              >
                <Settings2 size={18} />
              </NavLink>
              <span className={`live-indicator ${live.connected ? '' : 'disconnected'}`}>
                <span />
                {live.connected ? 'Live' : 'Polling · 30s'}
              </span>
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
                <Route path="/dependencies" element={<Dependencies />} />
                <Route path="/quality" element={<Quality />} />
                <Route path="/errors" element={<Errors />} />
                <Route path="/freshness" element={<Freshness />} />
                <Route path="/alerts" element={<Alerts />} />
                <Route path="/onboarding" element={<Onboarding />} />
                <Route path="/platform" element={<Platform />} />
                <Route path="/account" element={<Account />} />
                <Route path="/access" element={<Access />} />
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
