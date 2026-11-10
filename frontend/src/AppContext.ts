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
  const permissions = value.user.permissions ?? [];
  const has = (permission: string) =>
    permissions.length > 0
      ? permissions.includes(permission)
      : value.user.role === 'admin' ||
        (permission !== 'manage_users' &&
          permission !== 'manage_platform' &&
          value.user.role !== 'viewer');
  return {
    ...value,
    permissions,
    hasPermission: has,
    canOperate: has('trigger_pipelines'),
    canMutatePipelines: has('trigger_pipelines') && value.runtime.live_actions_enabled,
    isAdmin: has('manage_users'),
  };
}
