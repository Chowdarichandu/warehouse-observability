import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEMO_DRAFT, initialDraft, slugify, validateDraft } from './draft';

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe('tenant onboarding validation', () => {
  it('starts with the System Engines demonstration and an empty live identity', () => {
    expect(initialDraft('demo').tenant_id).toBe('system_engines');
    expect(initialDraft('live').tenant_id).toBe('');
    expect(initialDraft('live').mysql_secret_ref).toBe('aws://observability/');
  });
  it('accepts only known primitive fields from stored drafts', () => {
    sessionStorage.setItem(
      'obs-onboard-draft-v2-demo',
      JSON.stringify({
        display_name: 'Saved client',
        mysql_port: 'not a number',
        unknown: 'ignored',
      }),
    );
    const draft = initialDraft('demo');
    expect(draft.display_name).toBe('Saved client');
    expect(draft.mysql_port).toBe(3306);
    expect(draft).not.toHaveProperty('unknown');
  });
  it('retains a usable draft when storage is corrupt or blocked', () => {
    sessionStorage.setItem('obs-onboard-draft-v2-demo', 'invalid JSON');
    expect(initialDraft('demo')).toEqual(DEMO_DRAFT);
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Blocked');
    });
    expect(initialDraft('live').display_name).toBe('');
  });
  it('normalizes a readable slug without changing permanent identifiers', () => {
    expect(slugify('Café & System Engines')).toBe('cafe_system_engines');
    expect(slugify('x'.repeat(80))).toHaveLength(48);
    expect(validateDraft({ ...DEMO_DRAFT, tenant_id: '1_bad' }, 1, 'demo').tenant_id).toBeTruthy();
  });
  it('validates identity, ownership and SLA bounds per field', () => {
    expect(validateDraft(DEMO_DRAFT, 1, 'demo')).toEqual({});
    const errors = validateDraft(
      {
        ...DEMO_DRAFT,
        display_name: ' ',
        owner_email: 'invalid',
        freshness_sla_min: 0,
        warehouse_schema: 'bad-schema',
      },
      1,
      'demo',
    );
    expect(Object.keys(errors).sort()).toEqual([
      'display_name',
      'freshness_sla_min',
      'owner_email',
      'warehouse_schema',
    ]);
  });
  it('requires at least one source and validates only enabled inputs', () => {
    expect(
      validateDraft({ ...DEMO_DRAFT, has_mysql: false, has_mongo: false }, 2, 'demo').sources,
    ).toBeTruthy();
    expect(
      validateDraft(
        { ...DEMO_DRAFT, has_mysql: false, mysql_host: '', mysql_port: 0, mysql_secret_ref: '' },
        2,
        'demo',
      ),
    ).toEqual({});
    expect(validateDraft({ ...DEMO_DRAFT, mysql_port: 65536 }, 2, 'demo').mysql_port).toBeTruthy();
  });
  it('requires references and refuses URL or credential text in source fields', () => {
    expect(validateDraft(DEMO_DRAFT, 2, 'demo')).toEqual({});
    expect(
      validateDraft({ ...DEMO_DRAFT, mysql_host: 'mysql://reader:password@host' }, 2, 'demo')
        .mysql_host,
    ).toBeTruthy();
    expect(
      validateDraft({ ...DEMO_DRAFT, mysql_secret_ref: 'plain-password' }, 2, 'demo')
        .mysql_secret_ref,
    ).toBeTruthy();
    expect(
      validateDraft(
        {
          ...DEMO_DRAFT,
          mysql_secret_ref: 'aws://company/custom/mysql',
          mongo_secret_ref: 'aws://company/custom/mongo',
        },
        2,
        'live',
      ),
    ).toEqual({});
  });
});
