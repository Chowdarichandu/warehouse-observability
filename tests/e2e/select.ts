import { expect, type Locator } from "@playwright/test";

// The console's dropdowns are a custom component — a button that opens a
// listbox panel — not native <select> elements, so selectOption() cannot
// drive them. These helpers interact the way a user does: open the panel,
// then click the option.

export async function chooseSelectOption(
  control: Locator,
  name: string | RegExp,
): Promise<void> {
  await control.click();
  await control.page().getByRole("option", { name }).click();
}

export async function chooseSelectIndex(
  control: Locator,
  index: number,
): Promise<void> {
  await control.click();
  await control
    .page()
    .getByRole("option")
    .nth(index)
    .click();
}

export async function expectSelectOptionCount(
  control: Locator,
  count: number,
): Promise<void> {
  await control.click();
  await expect(control.page().getByRole("option")).toHaveCount(count);
  await control.page().keyboard.press("Escape");
}

export async function expectSelectOptionNamed(
  control: Locator,
  name: string | RegExp,
  count: number,
): Promise<void> {
  await control.click();
  await expect(control.page().getByRole("option", { name })).toHaveCount(count);
  await control.page().keyboard.press("Escape");
}
