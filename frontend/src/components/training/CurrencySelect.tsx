import React, { useMemo } from "react";

const FALLBACK_CURRENCIES = [
  "AED", "AUD", "BRL", "CAD", "CHF", "CNY", "DKK", "EGP", "ETB", "EUR", "GBP", "GHS",
  "HKD", "INR", "JPY", "KES", "MAD", "MUR", "MWK", "NAD", "NGN", "NOK", "NZD", "QAR",
  "RWF", "SAR", "SEK", "SGD", "TZS", "UGX", "USD", "XAF", "XOF", "ZAR", "ZMW", "ZWL",
];

type Props = Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "value" | "onChange"> & {
  value: string;
  onChange: (currency: string) => void;
};

function supportedCurrencies(): string[] {
  const intl = Intl as typeof Intl & { supportedValuesOf?: (key: "currency") => string[] };
  try {
    const values = intl.supportedValuesOf?.("currency");
    if (values?.length) return values;
  } catch {
    // Older browsers use the governed fallback list.
  }
  return FALLBACK_CURRENCIES;
}

const CurrencySelect: React.FC<Props> = ({ value, onChange, ...selectProps }) => {
  const currencies = useMemo(() => {
    const normalized = value.trim().toUpperCase();
    return Array.from(new Set([...supportedCurrencies(), normalized].filter(Boolean))).sort();
  }, [value]);

  return (
    <select {...selectProps} value={value.toUpperCase()} onChange={(event) => onChange(event.target.value)}>
      {currencies.map((currency) => <option key={currency} value={currency}>{currency}</option>)}
    </select>
  );
};

export default CurrencySelect;
