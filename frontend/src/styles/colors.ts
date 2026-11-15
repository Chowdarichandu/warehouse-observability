const COLOR_HEX = /^#([\da-f]{3}|[\da-f]{6})$/i;

/** Resolve a design token at render time so charts follow the active theme. */
export function cssColor(token: string, opacity = 1): string {
  const value =
    typeof document === 'undefined'
      ? ''
      : getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  if (!value) return `var(${token})`;
  if (opacity >= 1) return value;

  const match = COLOR_HEX.exec(value);
  if (!match) return value;
  const hex = match[1].length === 3 ? [...match[1]].map((part) => part + part).join('') : match[1];
  const [red, green, blue] = [0, 2, 4].map((index) =>
    Number.parseInt(hex.slice(index, index + 2), 16),
  );
  return `rgba(${red}, ${green}, ${blue}, ${Math.max(0, Math.min(1, opacity))})`;
}

/** Resolve the UI font stack from the active design system. */
export function cssFont(): string {
  if (typeof document === 'undefined') return '';
  return getComputedStyle(document.documentElement).getPropertyValue('--font-ui').trim();
}
