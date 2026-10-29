type Rules = Record<string, string | number>;
export const defaults: Rules = { audit_prefix: "QAR", car_prefix: "CAR", reliability_car_prefix: "RCAR", finding_prefix: "F", sequence_digits: 3, date_format: "YY" };
export const validNumbering = (value: unknown) => {
  const rules = { ...defaults, ...(value as Rules || {}) };
  return ["YY", "YYYY", "YYYY-MM", "YYYYMM", "YYMM"].includes(String(rules.date_format)) && ["audit_prefix", "car_prefix", "reliability_car_prefix", "finding_prefix"].every(key => /^[A-Z][A-Z0-9]{0,15}$/.test(String(rules[key])) && (key !== "audit_prefix" || String(rules[key]).length >= 2)) && Number.isInteger(rules.sequence_digits) && Number(rules.sequence_digits) >= 3 && Number(rules.sequence_digits) <= 6 && new Set([rules.audit_prefix, rules.car_prefix, rules.reliability_car_prefix]).size === 3;
};

export const referenceDateFormats = ["YY", "YYYY", "YYYY-MM", "YYYYMM", "YYMM"];
export function formatReferenceDate(serverDate: string, format: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(serverDate)) return "—";
  const [year, month] = serverDate.split("-");
  return ({ YY: year.slice(-2), YYYY: year, "YYYY-MM": `${year}-${month}`, YYYYMM: `${year}${month}`, YYMM: `${year.slice(-2)}${month}` } as Record<string,string>)[format] || "—";
}
