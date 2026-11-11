import type { Schema } from '../../api/client';

export type OnboardDraft = Schema<'OnboardInput'>;
export type DraftErrors = Partial<Record<keyof OnboardDraft | 'sources', string>>;
export const DEMO_DRAFT: OnboardDraft = {
  tenant_id: 'zenith_pay',
  display_name: 'Zenith Pay',
  has_mysql: true,
  has_mongo: true,
  mysql_host: 'mysql.zenith-pay.internal',
  mysql_port: 3306,
  mysql_database: 'payments',
  mysql_user: 'replication_reader',
  mysql_secret_ref: 'demo://zenith/mysql',
  mongo_database: 'payments',
  mongo_secret_ref: 'demo://zenith/mongo',
  warehouse_schema: 'zenith_pay',
  freshness_sla_min: 120,
  owner_email: 'owner@zenith.example',
  run_initial: true,
};
export function initialDraft(mode: 'demo' | 'live'): OnboardDraft {
  const base =
    mode === 'demo'
      ? DEMO_DRAFT
      : {
          ...DEMO_DRAFT,
          tenant_id: '',
          display_name: '',
          mysql_host: '',
          mysql_database: '',
          mongo_database: '',
          mysql_secret_ref: 'aws://observability/',
          mongo_secret_ref: 'aws://observability/',
          warehouse_schema: '',
          owner_email: '',
        };
  try {
    const saved: unknown = JSON.parse(
      sessionStorage.getItem(`obs-onboard-draft-v2-${mode}`) || 'null',
    );
    if (!saved || typeof saved !== 'object') return { ...base };
    // Only known fields with the expected primitive type are accepted from browser storage.
    const result = { ...base };
    for (const key of Object.keys(base) as (keyof OnboardDraft)[]) {
      const value = (saved as Record<string, unknown>)[key];
      if (typeof value === typeof base[key]) Object.assign(result, { [key]: value });
    }
    return result;
  } catch {
    return { ...base };
  }
}
export function blankDraft(): OnboardDraft {
  return {
    ...DEMO_DRAFT,
    tenant_id: '',
    display_name: '',
    mysql_host: '',
    mysql_database: '',
    mongo_database: '',
    mysql_secret_ref: 'aws://observability/',
    mongo_secret_ref: 'aws://observability/',
    warehouse_schema: '',
    owner_email: '',
  };
}

export function slugify(name: string): string {
  return name
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 48);
}
export function validateDraft(
  draft: OnboardDraft,
  stage: 1 | 2,
  mode: 'demo' | 'live',
): DraftErrors {
  const errors: DraftErrors = {};
  if (stage === 1) {
    if (draft.display_name.trim().length < 2 || draft.display_name.length > 100)
      errors.display_name = 'Use a name between 2 and 100 characters.';
    if (!/^[a-z][a-z0-9_]{2,47}$/.test(draft.tenant_id))
      errors.tenant_id = 'Use 3–48 lowercase letters, numbers or underscores; start with a letter.';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.owner_email))
      errors.owner_email = 'Enter a valid owner email address.';
    if (!/^[a-z][a-z0-9_]{0,62}$/.test(draft.warehouse_schema || draft.tenant_id))
      errors.warehouse_schema =
        'Use a schema starting with a letter, up to 63 lowercase letters, numbers or underscores.';
    if (
      !Number.isInteger(draft.freshness_sla_min) ||
      draft.freshness_sla_min < 5 ||
      draft.freshness_sla_min > 10080
    )
      errors.freshness_sla_min = 'Choose a whole number between 5 and 10,080 minutes.';
  } else {
    if (!draft.has_mysql && !draft.has_mongo)
      errors.sources = 'Select at least one source to continue.';
    const secretValid = (value: string) =>
      mode === 'live'
        ? /^aws:\/\/[^\s@]+$/.test(value)
        : /^(demo|aws|secret|vault):\/\/[^\s@]+$/.test(value);
    if (draft.has_mysql) {
      if (
        !draft.mysql_host.trim() ||
        draft.mysql_host.length > 254 ||
        /[\s/@]/.test(draft.mysql_host)
      )
        errors.mysql_host = 'Enter a database hostname without a URL or credentials.';
      if (!Number.isInteger(draft.mysql_port) || draft.mysql_port < 1 || draft.mysql_port > 65535)
        errors.mysql_port = 'Choose a port between 1 and 65,535.';
      if (!draft.mysql_database.trim() || draft.mysql_database.length > 100)
        errors.mysql_database = 'Enter the MySQL database name (up to 100 characters).';
      if (!draft.mysql_user.trim() || draft.mysql_user.length > 100)
        errors.mysql_user = 'Enter the replication user (up to 100 characters).';
      if (!secretValid(draft.mysql_secret_ref))
        errors.mysql_secret_ref =
          mode === 'live'
            ? 'Use an approved aws:// secret reference.'
            : 'Enter a secret-manager reference, such as demo://zenith/mysql.';
    }
    if (draft.has_mongo) {
      if (!draft.mongo_database.trim() || draft.mongo_database.length > 100)
        errors.mongo_database = 'Enter the MongoDB database name (up to 100 characters).';
      if (!secretValid(draft.mongo_secret_ref))
        errors.mongo_secret_ref =
          mode === 'live'
            ? 'Use an approved aws:// secret reference.'
            : 'Enter a secret-manager reference, such as demo://zenith/mongo.';
    }
  }
  return errors;
}
