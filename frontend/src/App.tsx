import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Select } from './components/Select';
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
  BadgeCheck,
  Bell,
  CalendarDays,
  ChevronDown,
  Command,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Maximize2,
  Menu,
  Moon,
  Network,
  PanelLeft,
  Search,
  Server,
  Settings2,
  ShieldCheck,
  Siren,
  Sun,
  Timer,
  TriangleAlert,
  Users,
  Warehouse as WarehouseIcon,
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

// Route screens are fetched as they are opened so the workspace shell stays light.
const Overview = lazy(() =>
  import('./pages/Overview').then((page) => ({ default: page.Overview })),
);
const Tenants = lazy(() => import('./pages/Tenants').then((page) => ({ default: page.Tenants })));
const TenantDetail = lazy(() =>
  import('./pages/Tenants').then((page) => ({ default: page.TenantDetail })),
);
const Runs = lazy(() => import('./pages/Runs').then((page) => ({ default: page.Runs })));
const RunDetail = lazy(() => import('./pages/Runs').then((page) => ({ default: page.RunDetail })));
const Errors = lazy(() => import('./pages/Errors').then((page) => ({ default: page.Errors })));
const Freshness = lazy(() =>
  import('./pages/Freshness').then((page) => ({ default: page.Freshness })),
);
const Alerts = lazy(() => import('./pages/Alerts').then((page) => ({ default: page.Alerts })));
const Incidents = lazy(() =>
  import('./pages/Incidents').then((page) => ({ default: page.Incidents })),
);
const Onboarding = lazy(() =>
  import('./pages/Onboarding').then((page) => ({ default: page.Onboarding })),
);
const Admin = lazy(() => import('./pages/System').then((page) => ({ default: page.Admin })));
const Platform = lazy(() => import('./pages/System').then((page) => ({ default: page.Platform })));
const SearchResults = lazy(() =>
  import('./pages/System').then((page) => ({ default: page.SearchResults })),
);
const Quality = lazy(() => import('./pages/Quality').then((page) => ({ default: page.Quality })));
const Warehouse = lazy(() =>
  import('./pages/Warehouse').then((page) => ({ default: page.Warehouse })),
);
const Account = lazy(() => import('./pages/Account').then((page) => ({ default: page.Account })));
const Pipelines = lazy(() =>
  import('./pages/Pipelines').then((page) => ({ default: page.Pipelines })),
);
const Access = lazy(() => import('./pages/Access').then((page) => ({ default: page.Access })));
const Dependencies = lazy(() =>
  import('./pages/Dependencies').then((page) => ({ default: page.Dependencies })),
);
const Styleguide = lazy(() =>
  import('./pages/Styleguide').then((page) => ({ default: page.Styleguide })),
);

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
    ],
  },
  {
    group: 'ANALYZE',
    items: [
      { path: '/errors', label: 'Errors', icon: TriangleAlert },
      { path: '/freshness', label: 'Freshness & volume', icon: Timer },
      { path: '/warehouse', label: 'Warehouse', icon: WarehouseIcon },
      { path: '/dependencies', label: 'Dependencies', icon: Network },
      { path: '/quality', label: 'Data quality', icon: BadgeCheck },
      { path: '/incidents', label: 'Incidents', icon: Siren },
      { path: '/alerts', label: 'Alerts', icon: Bell },
    ],
  },
  {
    group: 'MANAGE',
    items: [
      { path: '/platform', label: 'Platform', icon: Server },
      { path: '/access', label: 'Access & roles', icon: ShieldCheck },
      { path: '/admin', label: 'Administration', icon: Settings2 },
      { path: '/account', label: 'Settings', icon: Settings2 },
    ],
  },
];

const PRODUCT_MODULES = [
  {
    mark: 'H',
    name: 'HRMS',
    description: 'People operations',
    moduleId: 'hrms',
  },
  {
    mark: 'F',
    name: 'Finance',
    description: 'Finance operations',
    moduleId: 'finance',
  },
  {
    mark: 'S',
    name: 'SAP',
    description: 'ERP operations',
    moduleId: 'sap',
  },
  {
    mark: 'P',
    name: 'POS',
    description: 'Point-of-sale operations',
    moduleId: 'pos',
  },
  {
    mark: 'I',
    name: 'Inventory',
    description: 'Inventory operations',
    moduleId: 'inventory',
  },
  {
    mark: 'S',
    name: 'Support',
    description: 'Customer support',
    moduleId: 'support',
  },
  {
    mark: 'H',
    name: 'Hospitality',
    description: 'Hospitality operations',
    moduleId: 'hospitality',
  },
] as const;

function ActivityRedirect() {
  const [params] = useSearchParams();
  const activityParams = new URLSearchParams(params);
  activityParams.set('section', 'activity');
  return <Navigate to={`/admin?${activityParams.toString()}`} replace />;
}

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
  const permissions = Array.isArray(user.permissions) ? user.permissions : undefined;
  const metricsOnly = permissions?.includes('metrics_only') ?? false;
  const access = useQuery({
    queryKey: ['access'],
    queryFn: () => api<Schema<'AccessContext'>>('/access'),
  });
  const allowedModuleIds = new Set(access.data?.modules?.map((module) => module.module_id) ?? []);
  const availableModules = PRODUCT_MODULES.filter((module) =>
    allowedModuleIds.has(module.moduleId),
  );
  const searchRef = useRef<HTMLInputElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const fetching = useIsFetching({
    predicate: (query) => !['me', 'config'].includes(String(query.queryKey[0])),
  });
  const live = useLiveEvents();
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
  const [searchOpen, setSearchOpen] = useState(false);
  const searchTerm = search.trim();
  const suggestTenants = useQuery({
    queryKey: ['suggest-tenants', searchTerm],
    queryFn: () =>
      api<Schema<'Page_Tenant_'>>(`/tenants?q=${encodeURIComponent(searchTerm)}&page_size=5`),
    enabled: !metricsOnly && searchOpen && searchTerm.length >= 2,
  });
  const suggestPages =
    !metricsOnly && searchTerm.length >= 2
      ? NAV.flatMap((g) => g.items).filter((item) =>
          item.label.toLowerCase().includes(searchTerm.toLowerCase()),
        )
      : [];
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const tv = params.get('tv') === '1';
  const range = params.get('range') || '24h';
  const rangeLabel =
    {
      '1h': 'Last hour',
      '6h': 'Last 6 hours',
      '24h': 'Last 24 hours',
      '7d': 'Last 7 days',
      '30d': 'Last 30 days',
      custom: 'Custom range',
    }[range] || 'Last 24 hours';
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
    enabled: !metricsOnly,
    refetchInterval: 60_000,
  });
  useEffect(() => {
    setMenu(false);
    setPanel('none');
    setSearchOpen(false);
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
        setSearchOpen(false);
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
    <AppContext.Provider
      value={{
        user,
        runtime,
        access: access.data,
        ...live,
        notify: setToast,
        textSize,
        setTextSize,
      }}
    >
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
              aria-controls="workspace-product-menu"
              aria-haspopup="true"
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
              <div
                className="popover workspace-pop product-menu"
                id="workspace-product-menu"
                aria-label="Product modules"
              >
                <span className="product-menu-label">YOUR MODULES</span>
                <NavLink to="/" className="product-active">
                  <span className="workspace-avatar">O</span>
                  <span>
                    <strong>Observability</strong>
                    <small>Monitor data operations</small>
                  </span>
                  <span className="product-current">Open</span>
                </NavLink>
                {availableModules.map((module) => (
                  <button
                    type="button"
                    className="product-planned"
                    key={module.moduleId}
                    title={`${module.name} module is not available yet`}
                    onClick={() => {
                      setPanel('none');
                      setToast(
                        `${module.name} access is assigned. This module is not available yet.`,
                      );
                    }}
                  >
                    <span className="workspace-avatar planned">{module.mark}</span>
                    <span>
                      <strong>{module.name}</strong>
                      <small>{module.description}</small>
                    </span>
                    <span className="product-planned-tag">Planned</span>
                  </button>
                ))}
                <p className="product-menu-note">Module access is managed by your administrator.</p>
              </div>
            )}
            <nav>
              {NAV.map((group) => {
                const items = group.items
                  .filter((item) => !metricsOnly || item.path === '/')
                  .filter(
                    (item) =>
                      item.path !== '/admin' ||
                      (permissions ? permissions.includes('manage_users') : user.role === 'admin'),
                  )
                  .filter((item) => item.path !== '/onboarding' || user.role !== 'viewer');
                return items.length ? (
                  <div className="nav-group" key={group.group}>
                    <span className="nav-label">{metricsOnly ? 'METRICS' : group.group}</span>
                    {items.map((item) => (
                      <NavLink key={item.path} to={rangeLink(item.path)} end={item.path === '/'}>
                        <item.icon size={17} />
                        <span>{item.label}</span>
                      </NavLink>
                    ))}
                  </div>
                ) : null;
              })}
            </nav>
            <div className="sidebar-bottom">
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
              {!metricsOnly && (
                <div
                  className="search-wrap"
                  onBlur={(event) => {
                    if (!event.currentTarget.contains(event.relatedTarget as Node))
                      setSearchOpen(false);
                  }}
                >
                  <form
                    className="global-search"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (search.trim()) {
                        setSearchOpen(false);
                        navigate(`/search?q=${encodeURIComponent(search.trim())}`);
                      }
                    }}
                  >
                    <Search size={15} />
                    <input
                      ref={searchRef}
                      aria-label="Search tenants, logs, pages"
                      placeholder="Search tenants, logs, pages…"
                      maxLength={200}
                      value={search}
                      onFocus={() => setSearchOpen(true)}
                      onChange={(event) => {
                        setSearch(event.target.value);
                        setSearchOpen(true);
                      }}
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
                  {searchOpen && searchTerm.length >= 2 && (
                    <div
                      className={`search-suggest${suggestTenants.isPlaceholderData ? ' is-fetching' : ''}`}
                      role="listbox"
                      aria-label="Search suggestions"
                    >
                      {suggestTenants.data && suggestTenants.data.items.length > 0 && (
                        <>
                          <span className="search-suggest-label">Tenants</span>
                          {suggestTenants.data.items.map((tenant) => (
                            <button
                              type="button"
                              key={tenant.tenant_id}
                              className="search-suggest-item"
                              onClick={() => {
                                setSearchOpen(false);
                                setSearch('');
                                navigate(`/tenants/${tenant.tenant_id}`);
                              }}
                            >
                              <strong>{tenant.display_name}</strong>
                              <small>{tenant.tenant_id}</small>
                            </button>
                          ))}
                        </>
                      )}
                      {suggestPages.length > 0 && (
                        <>
                          <span className="search-suggest-label">Pages</span>
                          {suggestPages.map((item) => (
                            <button
                              type="button"
                              key={item.path}
                              className="search-suggest-item"
                              onClick={() => {
                                setSearchOpen(false);
                                setSearch('');
                                navigate(item.path);
                              }}
                            >
                              <strong>{item.label}</strong>
                            </button>
                          ))}
                        </>
                      )}
                      <button
                        type="button"
                        className="search-suggest-all"
                        onClick={() => {
                          setSearchOpen(false);
                          navigate(`/search?q=${encodeURIComponent(searchTerm)}`);
                        }}
                      >
                        See all results for “{searchTerm}” <ArrowRight size={13} />
                      </button>
                    </div>
                  )}
                </div>
              )}
              <span className={`live-indicator ${live.connected ? '' : 'disconnected'}`}>
                <span />
                {live.connected ? 'Live' : 'Polling · 30s'}
              </span>
              {!metricsOnly && (
                <div className="bell-wrap">
                  <button
                    className="theme-toggle"
                    title="Notifications"
                    aria-label={
                      firing.data && firing.data.total > 0
                        ? `Notifications, ${firing.data.total} firing`
                        : 'Notifications'
                    }
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
                        <>
                          {firing.data.items.slice(0, 5).map((alert) => (
                            <NavLink key={alert.id} to="/alerts" className="bell-item">
                              <StatusPill status={alert.severity} />
                              <span className="bell-text">
                                <strong>
                                  {alert.tenant_id && alert.title.endsWith(` · ${alert.tenant_id}`)
                                    ? alert.title.slice(0, -(alert.tenant_id.length + 3))
                                    : alert.title}
                                </strong>
                                <small>
                                  {alert.tenant_id || 'Platform'} ·{' '}
                                  <Time value={alert.first_fired_at} relative />
                                </small>
                              </span>
                            </NavLink>
                          ))}
                          {firing.data.total > 5 && (
                            <p className="muted bell-empty">
                              and {firing.data.total - 5} more firing — View all alerts
                            </p>
                          )}
                        </>
                      ) : (
                        <p className="muted bell-empty">Nothing firing. All quiet.</p>
                      )}
                    </div>
                  )}
                </div>
              )}
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
              {metricsOnly && <strong>METRICS ONLY · READ ONLY</strong>}
              <span className="muted">All times shown in your local timezone</span>
            </div>
            <div className="inline-flex">
              <label className="range-picker">
                <CalendarDays size={14} />
                <Select
                  aria-label={`Global time range ${rangeLabel}`}
                  value={range}
                  onChange={(event) => {
                    const next = new URLSearchParams(params);
                    next.set('range', event.target.value);
                    next.delete('page');
                    if (event.target.value === 'custom' && !next.get('from')) {
                      const now = new Date();
                      next.set('to', now.toISOString());
                      next.set('from', new Date(now.getTime() - 86400000).toISOString());
                    }
                    setParams(next);
                  }}
                >
                  <option value="1h">Last hour</option>
                  <option value="6h">Last 6 hours</option>
                  <option value="24h">Last 24 hours</option>
                  <option value="7d">Last 7 days</option>
                  <option value="30d">Last 30 days</option>
                  <option value="custom">Custom range</option>
                </Select>
              </label>
              <button
                className="icon-button"
                aria-label={tv ? 'Exit TV mode' : 'Open TV mode'}
                title="TV mode"
                onClick={() => {
                  const next = new URLSearchParams(params);
                  if (tv) next.delete('tv');
                  else next.set('tv', '1');
                  navigate(`${location.pathname}?${next}`);
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
              {metricsOnly && location.pathname !== '/' && location.pathname !== '/account' ? (
                <div className="notice info" role="status">
                  <ShieldCheck size={21} />
                  <div>
                    <strong>Metrics-only access</strong>
                    <p>This role can view workspace metrics and account settings only.</p>
                  </div>
                  <NavLink className="button small" to="/">
                    Return to metrics
                  </NavLink>
                </div>
              ) : (
                <Suspense
                  fallback={
                    <div className="route-loading" aria-live="polite">
                      <Loading />
                    </div>
                  }
                >
                  <Routes>
                    <Route path="/" element={<Overview />} />
                    <Route path="/tenants" element={<Tenants />} />
                    <Route path="/tenants/:id" element={<TenantDetail />} />
                    <Route path="/runs" element={<Runs />} />
                    <Route path="/runs/:key" element={<RunDetail />} />
                    <Route path="/activity" element={<ActivityRedirect />} />
                    <Route path="/pipelines" element={<Pipelines />} />
                    <Route path="/workspace" element={<Navigate to="/" replace />} />
                    <Route
                      path="/workspace/pipelines"
                      element={<Navigate to="/pipelines" replace />}
                    />
                    <Route path="/access" element={<Access />} />
                    <Route path="/account" element={<Account />} />
                    <Route path="/dependencies" element={<Dependencies />} />
                    <Route path="/quality" element={<Quality />} />
                    <Route path="/errors" element={<Errors />} />
                    <Route path="/freshness" element={<Freshness />} />
                    <Route path="/warehouse" element={<Warehouse />} />
                    <Route path="/incidents" element={<Incidents />} />
                    <Route path="/alerts" element={<Alerts />} />
                    <Route path="/onboarding" element={<Onboarding />} />
                    <Route path="/platform" element={<Platform />} />
                    <Route path="/admin" element={<Admin />} />
                    <Route path="/search" element={<SearchResults />} />
                    <Route path="/styleguide" element={<Styleguide />} />
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
                </Suspense>
              )}
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
