import './global-search.css';
import { useEffect, useState, type RefObject } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Search } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api, queryString, type Schema } from '../api/client';
import { matchingPages, type SearchPage } from '../search';

export function GlobalSearch({
  inputRef,
  pages,
}: {
  inputRef: RefObject<HTMLInputElement | null>;
  pages: SearchPage[];
}) {
  const [value, setValue] = useState('');
  const [open, setOpen] = useState(false);
  const [debouncedTerm, setDebouncedTerm] = useState('');
  const term = value.trim();
  const visible = open && term.length >= 2;
  const navigate = useNavigate();
  const { pathname } = useLocation();

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedTerm(term), 180);
    return () => window.clearTimeout(timer);
  }, [term]);
  useEffect(() => setOpen(false), [pathname]);

  const ready = visible && term === debouncedTerm;
  const tenants = useQuery({
    queryKey: ['suggest-tenants', debouncedTerm],
    queryFn: ({ signal }) =>
      api<Schema<'Page_Tenant_'>>(`/tenants?${queryString({ q: debouncedTerm, page_size: 5 })}`, {
        signal,
      }),
    enabled: ready,
    placeholderData: () => undefined,
    refetchInterval: false,
    retry: false,
  });
  const destinations = visible ? matchingPages(pages, term).slice(0, 6) : [];

  function go(path: string, clear = false) {
    setOpen(false);
    if (clear) setValue('');
    navigate(path);
  }
  const resultsPath = `/search?${queryString({ q: term })}`;

  return (
    <div
      className="search-wrap"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(event) => {
        if (!visible) return;
        if (event.key === 'Escape') {
          inputRef.current?.focus();
          setOpen(false);
          return;
        }
        if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
        const targets = Array.from(
          event.currentTarget.querySelectorAll<HTMLButtonElement>('.search-suggest button'),
        );
        if (!targets.length) return;
        event.preventDefault();
        const current = targets.indexOf(document.activeElement as HTMLButtonElement);
        const next =
          event.key === 'ArrowDown' ? current + 1 : (current < 0 ? targets.length : current) - 1;
        if (next < 0 || next >= targets.length) inputRef.current?.focus();
        else targets[next].focus();
      }}
    >
      <form
        className="global-search"
        role="search"
        aria-label="Workspace search"
        onSubmit={(event) => {
          event.preventDefault();
          if (term.length >= 2) go(resultsPath);
        }}
      >
        <input
          ref={inputRef}
          aria-label="Search tenants, logs, pages"
          aria-controls={visible ? 'search-suggestions' : undefined}
          placeholder="Search workspace…"
          maxLength={200}
          value={value}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setValue(event.target.value);
            setOpen(true);
          }}
        />
        <button type="submit" aria-label="Submit global search" disabled={term.length < 2}>
          <Search size={16} aria-hidden="true" />
        </button>
      </form>
      {visible && (
        <section id="search-suggestions" className="search-suggest" aria-label="Search suggestions">
          {ready && tenants.data?.items.length ? (
            <div className="search-suggest-group">
              <h2>Tenants</h2>
              {tenants.data.items.map((tenant) => (
                <button
                  type="button"
                  key={tenant.tenant_id}
                  onClick={() => go(`/tenants/${encodeURIComponent(tenant.tenant_id)}`, true)}
                >
                  <strong>{tenant.display_name}</strong>
                  <small>{tenant.tenant_id}</small>
                </button>
              ))}
            </div>
          ) : null}
          {destinations.length > 0 && (
            <div className="search-suggest-group">
              <h2>Pages</h2>
              {destinations.map((item) => (
                <button key={item.path} type="button" onClick={() => go(item.path, true)}>
                  <strong>{item.label}</strong>
                </button>
              ))}
            </div>
          )}
          <button type="button" className="search-suggest-all" onClick={() => go(resultsPath)}>
            <span>Search for “{term}”</span> <ArrowRight size={14} aria-hidden="true" />
          </button>
        </section>
      )}
    </div>
  );
}
