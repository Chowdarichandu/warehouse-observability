import { createContext, useContext } from 'react';
import type { Schema } from './api/client';
import type { Activity } from './api/useLiveEvents';

export const AppContext = createContext<{
  user: Schema<'User'>;
  runtime: Schema<'RuntimeConfig'>;
  connected: boolean;
  activity: Activity[];
  notify: (message: string) => void;
} | null>(null);
export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error('Application context is unavailable');
  return {
    ...value,
    canOperate: value.user.role !== 'viewer',
    canMutatePipelines: value.user.role !== 'viewer' && value.runtime.live_actions_enabled,
    isAdmin: value.user.role === 'admin',
  };
}
