import React from "react";

type TabItem = { id: string; label: string };

type Props = {
  tabs: TabItem[];
  value: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
};

const AvionicsTabs: React.FC<Props> = ({ tabs, value, onChange, ariaLabel = "Tabs" }) => {
  return (
    <div className="production-avionics-tabs" role="tablist" aria-label={ariaLabel}>
      {tabs.map((tab, idx) => {
        const active = tab.id === value;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            className={`production-avionics-tabs__tab${active ? " is-active" : ""}`}
            onClick={() => onChange(tab.id)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                e.preventDefault();
                const nextIdx = e.key === "ArrowRight" ? (idx + 1) % tabs.length : (idx - 1 + tabs.length) % tabs.length;
                onChange(tabs[nextIdx].id);
                return;
              }
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onChange(tab.id);
              }
            }}
          >
            <span className="production-avionics-tabs__led" aria-hidden="true" />
            <span className="production-avionics-tabs__label">{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
};

export default AvionicsTabs;
