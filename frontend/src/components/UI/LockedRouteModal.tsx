// src/components/UI/LockedRouteModal.tsx
import React from "react";
import Button from "./Button";

type LockedRouteModalProps = {
  open: boolean;
  featureName?: string;
  onClose: () => void;
  onViewPlans?: () => void;
  onStartTrial?: () => void;
};

const LockedRouteModal: React.FC<LockedRouteModalProps> = ({
  open,
  featureName,
  onClose,
  onViewPlans,
  onStartTrial,
}) => {
  if (!open) return null;

  return (
    <div className="upsell-modal__backdrop" role="dialog" aria-modal="true">
      <div className="upsell-modal">
        <div className="upsell-modal__header">
          <div>
            <p className="upsell-modal__eyebrow">Locked route</p>
            <h3 className="upsell-modal__title">
              {featureName || "This area"} requires a paid module
            </h3>
            <p className="upsell-modal__subtitle">
              Start a 30-day trial or explore pricing without leaving your workflow.
            </p>
          </div>
          <button
            type="button"
            className="upsell-modal__close"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <div className="upsell-modal__actions">
          <Button onClick={onStartTrial}>Start free trial</Button>
          <button type="button" className="btn-secondary" onClick={onViewPlans}>
            View plans
          </button>
        </div>
      </div>
    </div>
  );
};

export default LockedRouteModal;
