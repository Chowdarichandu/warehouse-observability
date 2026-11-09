import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatusPill } from './StatusPill';
import { STATUS_COLORS } from './statusColors';

describe('status semantics', () => {
  it('uses the same danger color for tenant and run failures', () => {
    expect(STATUS_COLORS.down).toBe(STATUS_COLORS.failed);
    expect(STATUS_COLORS.success).toBe(STATUS_COLORS.healthy);
    expect(STATUS_COLORS.running).not.toBe(STATUS_COLORS.failed);
  });
  it('keeps the label visible without depending on color', () => {
    render(<StatusPill status="failed" />);
    expect(screen.getByText('failed')).toBeVisible();
  });
});
