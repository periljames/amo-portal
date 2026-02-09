import React from "react";

type InlineErrorProps = {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
};

const InlineError: React.FC<InlineErrorProps> = ({
  message,
  actionLabel = "Retry",
  onAction,
}) => {
  return (
    <div className="inline-error" role="status">
      <span>{message}</span>
      {onAction && (
        <button type="button" className="secondary-chip-btn" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
};

export default InlineError;
