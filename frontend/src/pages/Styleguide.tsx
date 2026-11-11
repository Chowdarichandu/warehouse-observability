import { useEffect, useState } from 'react';
import { Copy, LoaderCircle } from 'lucide-react';
import { Empty, ErrorState, Loading, PageHeader, Pagination, Panel } from '../components/ui';
import { Select } from '../components/Select';
import { StatusPill } from '../components/StatusPill';
import './styleguide.css';

const COLORS = [
  ['Paper', 'paper'],
  ['Surface', 'surface'],
  ['Sunken', 'sunken'],
  ['Ink', 'ink-900'],
  ['Accent', 'accent'],
  ['Healthy', 'ok'],
  ['Degraded', 'warn'],
  ['Down', 'bad'],
  ['Running', 'run'],
  ['Idle', 'idle'],
] as const;

const TEXT = [
  ['Display', 'display'],
  ['Title', 'title'],
  ['Heading', 'heading'],
  ['Body', 'body'],
  ['Label', 'label'],
  ['Meta', 'meta'],
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
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [toast, setToast] = useState('');
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
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
                <span className={`token-color token-${token}`} />
                <strong>{label}</strong>
                <code>--{token}</code>
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
                <strong className={`type-${token}`}>Pipeline health at a glance</strong>
                <code>--text-{token}</code>
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
              View details
            </button>
            <button className="button ghost" type="button">
              Open run history
            </button>
            <button className="button danger" type="button">
              Pause tenant
            </button>
            <button
              className="button icon-button"
              type="button"
              aria-label="Copy run key"
              title="Copy run key"
            >
              <Copy size={15} />
            </button>
          </div>
          <div className="styleguide-state-grid" aria-label="Button states">
            <div>
              <span>Hover</span>
              <button className="button secondary demo-hover" type="button">
                Inspect run
              </button>
            </div>
            <div>
              <span>Active</span>
              <button className="button primary demo-active" type="button">
                Save settings
              </button>
            </div>
            <div>
              <span>Focus visible</span>
              <button className="button ghost demo-focus" type="button">
                Review changes
              </button>
            </div>
            <div>
              <span>Disabled</span>
              <button
                className="button secondary"
                type="button"
                title="Requires the administrator role"
                disabled
              >
                Disable user
              </button>
            </div>
            <div>
              <span>Loading</span>
              <button className="button primary" type="button" disabled aria-busy="true">
                <LoaderCircle className="styleguide-spinner" size={15} />
                Saving changes
              </button>
            </div>
          </div>
          <div className="styleguide-controls styleguide-overlay-controls">
            <button
              className="button secondary"
              type="button"
              aria-expanded={popoverOpen}
              onClick={() => setPopoverOpen((open) => !open)}
            >
              {popoverOpen ? 'Close active syncs' : 'Show active syncs'}
            </button>
            <button className="button secondary" type="button" onClick={() => setDialogOpen(true)}>
              Preview confirmation
            </button>
            <button
              className="button ghost"
              type="button"
              onClick={() => setToast('Changes saved.')}
            >
              Show success toast
            </button>
          </div>
          {popoverOpen && (
            <div className="styleguide-popover" role="status">
              <strong>Active syncs</strong>
              <span>Acme Retail · MySQL CDC</span>
              <span>Estimated progress · 74%</span>
            </div>
          )}
          {toast && (
            <div className="styleguide-toast" role="status">
              {toast}
              <button type="button" aria-label="Dismiss notification" onClick={() => setToast('')}>
                Dismiss
              </button>
            </div>
          )}
          {dialogOpen && (
            <div className="styleguide-dialog-backdrop" onMouseDown={() => setDialogOpen(false)}>
              <section
                aria-labelledby="styleguide-dialog-title"
                aria-modal="true"
                className="styleguide-dialog"
                onMouseDown={(event) => event.stopPropagation()}
                role="dialog"
              >
                <h3 id="styleguide-dialog-title">Pause Acme Retail?</h3>
                <p>New runs will stop until an operator resumes this tenant.</p>
                <div className="styleguide-controls">
                  <button
                    className="button danger"
                    type="button"
                    onClick={() => setDialogOpen(false)}
                  >
                    Pause tenant
                  </button>
                  <button
                    className="button secondary"
                    type="button"
                    onClick={() => setDialogOpen(false)}
                  >
                    Cancel
                  </button>
                </div>
              </section>
            </div>
          )}
        </Panel>

        <Panel
          title="Inputs and selection"
          subtitle="Fields use visible labels, matched control heights, and clear states."
        >
          <div className="styleguide-form">
            <label>
              Tenant name
              <input
                aria-label="Tenant name example"
                className="demo-focus"
                defaultValue="Acme Retail"
              />
            </label>
            <label>
              Display density
              <Select
                aria-label={`Display density ${density}`}
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
                aria-describedby="styleguide-invalid-help"
                defaultValue="invalid"
              />
              <small className="danger-text" id="styleguide-invalid-help">
                Enter a valid value.
              </small>
            </label>
            <label>
              Password
              <span className="styleguide-password">
                <input
                  aria-label="Password example"
                  autoComplete="off"
                  onKeyUp={(event) => setCapsLock(event.getModifierState('CapsLock'))}
                  type={passwordVisible ? 'text' : 'password'}
                  value="Pravah-demo-password"
                  readOnly
                />
                <button
                  className="button ghost"
                  type="button"
                  onClick={() => setPasswordVisible((visible) => !visible)}
                >
                  {passwordVisible ? 'Hide' : 'Show'}
                </button>
              </span>
              {capsLock && <small role="status">Caps Lock is on.</small>}
              <small>Use a unique password for each account.</small>
            </label>
            <label>
              Disabled field
              <input aria-label="Disabled field example" disabled value="Managed by SSO" />
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
                <span className={`space-unit-${unit}`} />
                <code>--space-{unit}</code>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          title="Data display"
          subtitle="Loading, empty, error, and pagination states keep their layout."
        >
          <div className="styleguide-display-grid">
            <section aria-label="Loading state">
              <h3>Loading</h3>
              <Loading />
            </section>
            <section aria-label="Empty state">
              <h3>Empty</h3>
              <Empty title="No active syncs">All source pipelines are up to date.</Empty>
            </section>
            <section aria-label="Error state">
              <h3>Error</h3>
              <ErrorState
                error={new Error('Airflow is not responding. Check the service and try again.')}
              />
            </section>
          </div>
          <Pagination total={312} page={2} onChange={() => undefined} />
        </Panel>
      </div>
    </div>
  );
}
