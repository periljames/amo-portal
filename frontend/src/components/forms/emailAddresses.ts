export const isEmailAddress = (value: string): boolean => /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/.test(value.trim());

export function validEmailList(values: string[]): boolean {
  const addresses = values.map(value => value.trim().toLowerCase());
  return addresses.length > 0 && addresses.every(isEmailAddress) && new Set(addresses).size === addresses.length;
}
