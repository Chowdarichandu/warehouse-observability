import { useEffect, useState } from 'react';
import { PageHeader, Panel } from '../components/ui';
import { Select } from '../components/Select';
import { StatusPill } from '../components/StatusPill';
import './styleguide.css';

const COLORS = [
  ['Paper', '--paper'],
  ['Surface', '--surface'],
  ['Sunken', '--sunken'],
  ['Ink', '--ink-900'],
  ['Accent', '--accent'],
  ['Healthy', '--ok'],
  ['Degraded', '--warn'],
  ['Down', '--bad'],
  ['Running', '--run'],
  ['Idle', '--idle'],
] as const;

const TEXT = [
  ['Display', '--text-display'],
  ['Title', '--text-title'],
  ['Heading', '--text-heading'],
  ['Body', '--text-body'],
  ['Label', '--text-label'],
  ['Meta', '--text-meta'],
] as const;

export function Styleguide() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() =>
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  );

  useEffect(() => {
    const previous = document.documentElement.dataset.theme;
    document.documentElement.dataset.theme = theme;
    return () => {
      if (previous) document.documentElement.dataset.theme = previous;
      else delete document.documentElement.dataset.theme;
    };
  }, [theme]);

  const [density, setDensity] = useState('Comfortable');
  return (
    <div className="styleguide-page">
      <PageHeader
        title="Design system"
        description="Pravah interface tokens and component states."
        actions={
          <button
            className="button secondary"
            type="button"
            onClick={() => setTheme((current) => (current === 'light' ? 'dark' : 'light'))}
          >
            Switch to {theme === 'light' ? 'dark' : 'light'} theme
          </button>
        }
      />

      <div className="styleguide-grid">
        <Panel
          title="Color tokens"
          subtitle="State colors carry meaning; neutral surfaces carry structure."
        >
          <div className="token-swatches">
            {COLORS.map(([label, token]) => (
              <div className="token-swatch" key={token}>
                <span style={{ background: `var(${token})` }} />
                <strong>{label}</strong>
                <code>{token}</code>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          title="Typography"
          subtitle="IBM Plex Sans for interface text; IBM Plex Mono for identifiers and logs."
        >
          <div className="type-specimens">
            {TEXT.map(([label, token]) => (
              <div key={token}>
                <span>{label}</span>
                <strong style={{ fontSize: `var(${token})` }}>Pipeline health at a glance</strong>
                <code>{token}</code>
              </div>
            ))}
            <p className="mono">run_mysql_cdc__2026-11-11T10:00Z</p>
          </div>
        </Panel>

        <Panel
          title="Buttons"
          subtitle="A single primary action leads each view. Destructive actions are explicit."
        >
          <div className="styleguide-controls">
            <button className="button primary" type="button">
              Save changes
            </button>
            <button className="button secondary" type="button">
              Secondary
            </button>
            <button className="button ghost" type="button">
              Toolbar action
            </button>
            <button className="button danger" type="button">
              Pause tenant
            </button>
            <button className="button primary" type="button" disabled>
              Disabled
            </button>
          </div>
        </Panel>

        <Panel
          title="Inputs and selection"
          subtitle="Fields use visible labels, matched control heights, and clear states."
        >
          <div className="styleguide-form">
            <label>
              Tenant name
              <input aria-label="Tenant name example" defaultValue="Acme Retail" />
            </label>
            <label>
              Display density
              <Select
                aria-label="Display density example"
                value={density}
                onChange={(event) => setDensity(event.target.value)}
              >
                <option>Comfortable</option>
                <option>Compact</option>
              </Select>
            </label>
            <label>
              Invalid field
              <input
                aria-label="Invalid field example"
                aria-invalid="true"
                defaultValue="invalid"
              />
              <small className="danger-text">Enter a valid value.</small>
            </label>
          </div>
        </Panel>

        <Panel
          title="Status and spacing"
          subtitle="Status text pairs with a glyph. Spacing follows a four-pixel base."
        >
          <div className="styleguide-controls">
            <StatusPill status="healthy" />
            <StatusPill status="degraded" />
            <StatusPill status="down" />
            <StatusPill status="running" />
          </div>
          <div className="spacing-scale" aria-label="Spacing token scale">
            {[1, 2, 3, 4, 5, 6, 8, 10, 12, 16].map((unit) => (
              <div key={unit}>
                <span style={{ width: `var(--space-${unit})` }} />
                <code>--space-{unit}</code>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
