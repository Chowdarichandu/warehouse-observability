-- Enable the registered product modules (product decision, 2026-11-11).
-- Migration 014 registered hrms/finance/sap/pos/inventory/support/hospitality
-- with enabled=false, so the product picker hid them from everyone, admins
-- included. The modules are still "Planned" (no screens behind them yet);
-- enabling only controls picker visibility, which module_access then gates
-- per role and per user as before.
UPDATE obs.modules
SET enabled = true
WHERE module_id IN (
    'hrms',
    'finance',
    'sap',
    'pos',
    'inventory',
    'support',
    'hospitality'
);
