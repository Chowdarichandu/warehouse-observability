import { Children, isValidElement, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown } from 'lucide-react';

export type SelectChangeEvent = { target: { value: string; name?: string } };

type OptionItem = { value: string; label: string; disabled?: boolean };
type Entry = OptionItem | { group: string; options: OptionItem[] };

function textOf(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return '';
}

function parseEntries(children: ReactNode): Entry[] {
  const entries: Entry[] = [];
  Children.forEach(children, (child) => {
    if (!isValidElement<Record<string, unknown>>(child)) return;
    if (child.type === 'optgroup') {
      const options: OptionItem[] = [];
      Children.forEach(child.props.children as ReactNode, (opt) => {
        if (!isValidElement<Record<string, unknown>>(opt)) return;
        const label = textOf(opt.props.children as ReactNode);
        options.push({
          value: opt.props.value != null ? String(opt.props.value) : label,
          label,
          disabled: Boolean(opt.props.disabled),
        });
      });
      entries.push({ group: String(child.props.label || ''), options });
    } else {
      const label = textOf(child.props.children as ReactNode);
      entries.push({
        value: child.props.value != null ? String(child.props.value) : label,
        label,
        disabled: Boolean(child.props.disabled),
      });
    }
  });
  return entries;
}

const isGroup = (entry: Entry): entry is { group: string; options: OptionItem[] } =>
  'group' in entry;

export function Select({
  value,
  defaultValue,
  onChange,
  name,
  disabled = false,
  required = false,
  id,
  className,
  'aria-label': ariaLabel,
  children,
}: {
  value?: string;
  defaultValue?: string;
  onChange?: (event: SelectChangeEvent) => void;
  name?: string;
  disabled?: boolean;
  required?: boolean;
  id?: string;
  className?: string;
  'aria-label'?: string;
  children: ReactNode;
}) {
  const entries = parseEntries(children);
  const flat = entries.flatMap((entry) => (isGroup(entry) ? entry.options : [entry]));
  const [internal, setInternal] = useState<string>(defaultValue ?? flat[0]?.value ?? '');
  const current = value !== undefined ? value : internal;
  const selected = flat.find((option) => option.value === current) ?? flat[0];
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [panelStyle, setPanelStyle] = useState<Record<string, string>>({});
  const rootRef = useRef<HTMLSpanElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const close = () => setOpen(false);

  useLayoutEffect(() => {
    if (!open || !buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const estimated = Math.min(288, flat.length * 37 + 14);
    const below = window.innerHeight - rect.bottom;
    const style: Record<string, string> = {
      left: `${Math.max(8, Math.min(rect.left, window.innerWidth - rect.width - 8))}px`,
      width: `${rect.width}px`,
      maxHeight: '288px',
    };
    if (below < estimated + 12 && rect.top > below) {
      style.bottom = `${window.innerHeight - rect.top + 6}px`;
    } else {
      style.top = `${rect.bottom + 6}px`;
    }
    setPanelStyle(style);
    const index = flat.findIndex((option) => option.value === current);
    setActive(index >= 0 ? index : 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (
        !rootRef.current?.contains(event.target as Node) &&
        !panelRef.current?.contains(event.target as Node)
      )
        close();
    };
    const onScroll = () => close();
    document.addEventListener('pointerdown', onPointer, true);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onScroll);
    return () => {
      document.removeEventListener('pointerdown', onPointer, true);
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onScroll);
    };
  }, [open]);

  const choose = (option: OptionItem) => {
    if (option.disabled) return;
    if (value === undefined) setInternal(option.value);
    close();
    buttonRef.current?.focus();
    if (option.value !== current) onChange?.({ target: { value: option.value, name } });
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (disabled) return;
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) {
        event.preventDefault();
        setOpen(true);
      }
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((index) => Math.min(flat.length - 1, index + 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((index) => Math.max(0, index - 1));
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (flat[active]) choose(flat[active]);
    } else if (event.key === 'Tab') {
      close();
    }
  };

  let flatIndex = -1;
  return (
    <span ref={rootRef} className={`ui-select ${className || ''}`}>
      {name && <input type="hidden" name={name} value={current} />}
      <button
        ref={buttonRef}
        type="button"
        id={id}
        className="ui-select-btn"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-required={required || undefined}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => !disabled && setOpen(!open)}
        onKeyDown={onKeyDown}
      >
        <span className="ui-select-label">{selected?.label ?? ''}</span>
        <ChevronDown size={15} />
      </button>
      {open &&
        createPortal(
          <div
            ref={panelRef}
            className="ui-select-panel"
            role="listbox"
            aria-label={ariaLabel}
            style={panelStyle}
          >
            {entries.map((entry, entryIndex) => {
              if (isGroup(entry)) {
                return (
                  <div key={`group-${entryIndex}`}>
                    <div className="ui-select-group">{entry.group}</div>
                    {entry.options.map((option) => {
                      flatIndex += 1;
                      const index = flatIndex;
                      return (
                        <button
                          type="button"
                          key={option.value}
                          role="option"
                          aria-selected={option.value === current}
                          disabled={option.disabled}
                          className={`ui-select-option ${index === active ? 'active' : ''} ${option.value === current ? 'selected' : ''}`}
                          onMouseEnter={() => setActive(index)}
                          onClick={() => choose(option)}
                        >
                          <Check size={14} />
                          <span className="ui-select-label">{option.label}</span>
                        </button>
                      );
                    })}
                  </div>
                );
              }
              flatIndex += 1;
              const index = flatIndex;
              return (
                <button
                  type="button"
                  key={entry.value}
                  role="option"
                  aria-selected={entry.value === current}
                  disabled={entry.disabled}
                  className={`ui-select-option ${index === active ? 'active' : ''} ${entry.value === current ? 'selected' : ''}`}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => choose(entry)}
                >
                  <Check size={14} />
                  <span className="ui-select-label">{entry.label}</span>
                </button>
              );
            })}
          </div>,
          document.body,
        )}
    </span>
  );
}
