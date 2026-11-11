import { createContext, useContext } from 'react';
import type { Schema } from './api/client';
import type { Activity } from './api/useLiveEvents';

export const AppContext = createContext<{
  user: Schema<'User'>;
  runtime: Schema<'RuntimeConfig'>;
  access?: Schema<'AccessContext'>;
  connected: boolean;
  activity: Activity[];
  notify: (message: string) => void;
  textSize: string;
  setTextSize: (value: string) => void;
} | null>(null);

export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error('Application context is unavailable');
  const permissions = value.user.permissions;
  const has = (permission: string) =>
    Array.isArray(permissions)
      ? permissions.includes(permission)
      : permission.startsWith('view_module_')
        ? value.user.role === 'admin'
        : value.user.role === 'admin' ||
          (permission !== 'manage_users' &&
            permission !== 'manage_platform' &&
            value.user.role !== 'viewer');
  const related: Record<string, string> = {
    'workspace.read': 'view_console',
    'investigations.save': 'view_console',
    'pipelines.retry': 'trigger_pipelines',
    'alerts.respond': 'manage_alerts',
    'onboarding.start': 'manage_tenants',
    'tenants.configure': 'manage_tenants',
    'alerts.configure': 'manage_alerts',
    'quality.run': 'trigger_pipelines',
    'quality.configure': 'manage_platform',
    'audit.read': 'manage_users',
    'operations.reconcile': 'manage_platform',
    'access.assign_roles': 'manage_users',
    'access.revoke_sessions': 'manage_users',
  };
  const can = (permission: string) =>
    Boolean(
      value.access?.capabilities.includes(permission) &&
        related[permission] &&
        has(related[permission]),
    );
  return {
    ...value,
    permissions: permissions || [],
    hasPermission: has,
    can,
    canOperate: has('trigger_pipelines'),
    canMutatePipelines: can('pipelines.retry'),
    isMetricsOnly: has('metrics_only'),
    isAdmin: has('manage_users'),
  };
}
