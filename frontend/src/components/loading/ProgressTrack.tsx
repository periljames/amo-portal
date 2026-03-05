import React from "react";

const ProgressTrack: React.FC<{ percent?: number | null; indeterminate?: boolean }> = ({ percent, indeterminate }) => {
  if (indeterminate || percent === null || percent === undefined) {
    return (
      <div className="loading-progress-track" aria-hidden>
        <div className="loading-progress-track__indeterminate" />
      </div>
    );
  }
  const value = Math.max(0, Math.min(100, percent));
  return (
    <div className="loading-progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}>
      <div className="loading-progress-track__determinate" style={{ width: `${value}%` }} />
    </div>
  );
};

export default ProgressTrack;
