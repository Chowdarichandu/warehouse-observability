export type SearchPage = { path: string; label: string };

const keywords: Record<string, string> = {
  '/': 'health dashboard',
  '/tenants': 'customers sources',
  '/pipelines': 'dag workflow pipelines',
  '/runs': 'logs jobs execution',
  '/errors': 'failures investigation',
  '/freshness': 'sla data age',
  '/alerts': 'notifications',
  '/quality': 'checks validation',
  '/warehouse': 'database tables',
  '/access': 'permissions security',
  '/account': 'account profile password',
  '/admin': 'users roles settings',
};

export function matchingPages(pages: SearchPage[], term: string) {
  const query = term.toLowerCase();
  return pages.filter(({ label, path }) =>
    `${label} ${keywords[path] ?? ''}`.toLowerCase().includes(query),
  );
}
