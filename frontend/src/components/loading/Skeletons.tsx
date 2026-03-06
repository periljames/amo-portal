import React from "react";

export const SkeletonBlock: React.FC<{ className?: string }> = ({ className = "" }) => (
  <div className={`loader-skeleton loader-skeleton--block ${className}`.trim()} aria-hidden />
);

export const SkeletonCard: React.FC = () => (
  <div className="loader-skeleton-card" aria-hidden>
    <SkeletonBlock className="loader-skeleton-card__title" />
    <SkeletonBlock className="loader-skeleton-card__line" />
    <SkeletonBlock className="loader-skeleton-card__line short" />
  </div>
);

export const SkeletonTable: React.FC<{ rows?: number }> = ({ rows = 4 }) => (
  <div className="loader-skeleton-table" aria-hidden>
    <SkeletonBlock className="loader-skeleton-table__head" />
    {Array.from({ length: rows }).map((_, idx) => (
      <SkeletonBlock key={idx} className="loader-skeleton-table__row" />
    ))}
  </div>
);
