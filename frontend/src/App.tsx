import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Workflow } from 'lucide-react';
import { api, ApiError, setCsrf } from './api/client';
import type { Schema } from './api/client';
import { APP_NAME, API_POLL_MS } from './config';
import { ErrorState, Loading } from './components/ui';
import { Login } from './pages/Login';
import { Workspace } from './Workspace';

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
