// src/components/UI/PricingToggle.tsx
import React from "react";
import { clsx } from "clsx";
import type { BillingTerm } from "../../types/billing";

type PricingToggleProps = {
  value: BillingTerm;
  onChange: (value: BillingTerm) => void;
  options?: BillingTerm[];
  subtitle?: string;
};

const LABELS: Record<BillingTerm, string> = {
  MONTHLY: "Monthly",
  ANNUAL: "Annual",
  BI_ANNUAL: "Bi-Annual",
};

const PricingToggle: React.FC<PricingToggleProps> = ({
  value,
  onChange,
  options = ["MONTHLY", "ANNUAL", "BI_ANNUAL"],
  subtitle,
}) => {
  return (
    <div className="pricing-toggle">
      <div className="pricing-toggle__header">
        <div>
          <p className="pricing-toggle__eyebrow">Billing term</p>
          <h3 className="pricing-toggle__title">Choose a cadence</h3>
          {subtitle && <p className="pricing-toggle__subtitle">{subtitle}</p>}
        </div>
      </div>
      <div className="pricing-toggle__chips" role="group" aria-label="Billing term">
        {options.map((opt) => (
          <button
            key={opt}
            type="button"
            className={clsx(
              "pricing-toggle__chip",
              value === opt && "pricing-toggle__chip--active"
            )}
            onClick={() => onChange(opt)}
            aria-pressed={value === opt}
          >
            {LABELS[opt]}
          </button>
        ))}
      </div>
    </div>
  );
};

export default PricingToggle;
