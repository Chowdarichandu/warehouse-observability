import { cssColor } from '../styles/colors';

const statusTokens: Record<string, string> = {
  healthy: '--ok',
  success: '--ok',
  pass: '--ok',
  enabled: '--ok',
  up: '--ok',
  resolved: '--ok',
  degraded: '--warn',
  warning: '--warn',
  acked: '--warn',
  medium: '--warn',
  down: '--bad',
  failed: '--bad',
  fail: '--bad',
  error: '--bad',
  critical: '--bad',
  high: '--bad',
  firing: '--bad',
  running: '--run',
  started: '--run',
  queued: '--run',
  configured: '--idle',
  onboarding: '--idle',
  paused: '--idle',
  cancelled: '--idle',
  skipped: '--idle',
  offboarded: '--idle',
  low: '--idle',
};

/** Resolve status colors from the active theme when the screen renders. */
export const STATUS_COLORS: Record<string, string> = new Proxy(Object.create(null), {
  get: (_target, status: string | symbol) => {
    if (typeof status !== 'string') return undefined;
    const token = statusTokens[status.toLowerCase()];
    return token ? cssColor(token) : cssColor('--ink-500');
  },
});
