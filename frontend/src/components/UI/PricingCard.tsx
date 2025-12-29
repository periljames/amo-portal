// src/components/UI/PricingCard.tsx
import React from "react";
import { clsx } from "clsx";
import Button from "./Button";

type PricingCardProps = {
  title: string;
  description: string;
  priceLabel: string;
  termLabel: string;
  deltaLabel?: string | null;
  badge?: string | null;
  features: string[];
  trialLabel?: string | null;
  highlight?: boolean;
  onPrimary?: () => void;
  primaryLabel?: string;
  onSecondary?: () => void;
  secondaryLabel?: string;
  disabled?: boolean;
};

const PricingCard: React.FC<PricingCardProps> = ({
  title,
  description,
  priceLabel,
  termLabel,
  deltaLabel,
  badge,
  features,
  trialLabel,
  highlight,
  onPrimary,
  primaryLabel = "Select",
  onSecondary,
  secondaryLabel,
  disabled,
}) => {
  return (
    <div className={clsx("pricing-card", highlight && "pricing-card--highlight")}>
      <div className="pricing-card__header">
        <div>
          <p className="pricing-card__eyebrow">{termLabel}</p>
          <h3 className="pricing-card__title">{title}</h3>
          <p className="pricing-card__description">{description}</p>
        </div>
        {badge && <span className="pricing-card__badge">{badge}</span>}
      </div>

      <div className="pricing-card__price">
        <span className="pricing-card__amount">{priceLabel}</span>
        {deltaLabel && <span className="pricing-card__delta">{deltaLabel}</span>}
        {trialLabel && <span className="pricing-card__trial">{trialLabel}</span>}
      </div>

      <ul className="pricing-card__features">
        {features.map((feature) => (
          <li key={feature}>
            <span aria-hidden="true">✔</span> {feature}
          </li>
        ))}
      </ul>

      <div className="pricing-card__actions">
        <Button onClick={onPrimary} disabled={disabled}>
          {primaryLabel}
        </Button>
        {onSecondary && secondaryLabel && (
          <button
            type="button"
            className="btn-secondary"
            onClick={onSecondary}
            disabled={disabled}
          >
            {secondaryLabel}
          </button>
        )}
      </div>
    </div>
  );
};

export default PricingCard;
