import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Select } from './Select';

describe('custom select', () => {
  it('shows the selected label and reports changes with a select-like event', () => {
    const onChange = vi.fn();
    render(
      <Select aria-label="Health" value="down" onChange={onChange}>
        <option value="healthy">Healthy</option>
        <option value="down">Down</option>
      </Select>,
    );
    expect(screen.getByRole('button', { name: 'Health' })).toHaveTextContent('Down');
    fireEvent.click(screen.getByRole('button', { name: 'Health' }));
    fireEvent.click(screen.getByRole('option', { name: /Healthy/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ target: expect.objectContaining({ value: 'healthy' }) }),
    );
  });

  it('keeps a hidden input in sync so form data reads the value', () => {
    render(
      <form>
        <Select name="role" defaultValue="viewer" aria-label="Role">
          <option value="viewer">viewer</option>
          <option value="admin">admin</option>
        </Select>
      </form>,
    );
    const input = document.querySelector('input[name="role"]') as HTMLInputElement;
    expect(input.value).toBe('viewer');
    fireEvent.click(screen.getByRole('button', { name: 'Role' }));
    fireEvent.click(screen.getByRole('option', { name: /admin/ }));
    expect(input.value).toBe('admin');
  });

  it('renders group headings for optgroups', () => {
    render(
      <Select aria-label="Grouped" defaultValue="a">
        <optgroup label="Built-in roles">
          <option value="a">Alpha</option>
        </optgroup>
      </Select>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Grouped' }));
    expect(screen.getByText('Built-in roles')).toBeVisible();
    expect(screen.getByRole('option', { name: /Alpha/ })).toBeVisible();
  });
});
