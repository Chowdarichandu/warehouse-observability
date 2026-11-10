export interface OnboardingDag {
  id: string;
  name: string;
  source: 'mysql' | 'mongo' | null;
  steps: string[];
}

/**
 * Tenant onboarding runs seven DAGs in sequence: the onboarding DAG, one
 * provisioning DAG per source, one initial-load DAG per source, and one CDC
 * DAG per source. Activation closes the sequence. Step names match the
 * backend onboarding plan (obs.onboarding.service.STEPS) event-for-event.
 */
export const ONBOARDING_DAGS: OnboardingDag[] = [
  {
    id: 'onboarding',
    name: 'Onboarding DAG',
    source: null,
    steps: [
      'Validate onboarding request',
      'Create tenant record',
      'Create warehouse schema',
      'Create Airbyte connections',
    ],
  },
  {
    id: 'mysql-provisioning',
    name: 'MySQL Provisioning DAG',
    source: 'mysql',
    steps: ['Create dedicated MySQL database', 'Provision MySQL user and grants'],
  },
  {
    id: 'mongo-provisioning',
    name: 'MongoDB Provisioning DAG',
    source: 'mongo',
    steps: ['Register shared MongoDB cluster', 'Configure tenant document key'],
  },
  {
    id: 'mysql-initial',
    name: 'MySQL Initial Load DAG',
    source: 'mysql',
    steps: ['Begin initial load (MySQL)', 'Snapshot tables to warehouse', 'Verify row counts'],
  },
  {
    id: 'mongo-initial',
    name: 'MongoDB Initial Load DAG',
    source: 'mongo',
    steps: [
      'Begin initial load (MongoDB)',
      'Snapshot collections to warehouse',
      'Verify document counts',
    ],
  },
  {
    id: 'mysql-cdc',
    name: 'MySQL CDC DAG',
    source: 'mysql',
    steps: ['Enable binlog CDC', 'Start MySQL CDC sync'],
  },
  {
    id: 'mongo-cdc',
    name: 'MongoDB CDC DAG',
    source: 'mongo',
    steps: ['Enable change-stream CDC', 'Start MongoDB CDC sync'],
  },
];

export const ONBOARDING_FINAL_STEP = 'Activate tenant';

export function dagsFor(sources: { has_mysql?: boolean; has_mongo?: boolean }): OnboardingDag[] {
  return ONBOARDING_DAGS.filter(
    (dag) =>
      dag.source === null || (dag.source === 'mysql' ? sources.has_mysql : sources.has_mongo),
  );
}
