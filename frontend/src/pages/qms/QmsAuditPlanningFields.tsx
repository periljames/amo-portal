import React from "react";
import { Eye, UserPlus, X } from "lucide-react";

import type {
  PlannerLocationOption,
  PlannerPersonOption,
} from "../../services/qmsAuditProgramme";
import "../../styles/qms-audit-programme-polish.css";

type LocationSelectProps = {
  id: string;
  value: string;
  locations: readonly PlannerLocationOption[];
  onChange: (value: string) => void;
  required?: boolean;
};

export const ProgrammeLocationSelect: React.FC<LocationSelectProps> = ({
  id,
  value,
  locations,
  onChange,
  required = false,
}) => {
  const hasLegacyValue = Boolean(
    value && !locations.some((location) => location.code === value),
  );
  return (
    <label htmlFor={id}>
      <span>Location</span>
      <select
        id={id}
        value={value}
        required={required}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">
          {locations.length
            ? "Select tenant location"
            : "No tenant locations configured"}
        </option>
        {hasLegacyValue ? (
          <option value={value}>{value} · previously saved</option>
        ) : null}
        {locations.map((location) => (
          <option key={location.id} value={location.code}>
            {location.code} · {location.name}
          </option>
        ))}
      </select>
    </label>
  );
};

type AuditorPickerProps = {
  id: string;
  people: readonly PlannerPersonOption[];
  leadAuditorUserId?: string | null;
  excludedUserIds?: readonly string[];
  value: readonly string[];
  onChange: (userIds: string[]) => void;
};

export const SupportingAuditorPicker: React.FC<AuditorPickerProps> = ({
  id,
  people,
  leadAuditorUserId,
  excludedUserIds = [],
  value,
  onChange,
}) => {
  const selected = new Set(value);
  const excluded = new Set(excludedUserIds);
  const available = people.filter(
    (person) =>
      person.id !== leadAuditorUserId &&
      !excluded.has(person.id) &&
      !selected.has(person.id),
  );

  return (
    <div className="is-wide qms-programme-auditor-picker">
      <label htmlFor={id}>
        <span>Supporting auditors</span>
        <span className="qms-programme-auditor-picker__select">
          <UserPlus size={15} aria-hidden="true" />
          <select
            id={id}
            value=""
            onChange={(event) => {
              const userId = event.target.value;
              if (userId) onChange([...value, userId]);
            }}
          >
            <option value="">Add auditor</option>
            {available.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
                {person.department_name ? ` · ${person.department_name}` : ""}
              </option>
            ))}
          </select>
        </span>
      </label>
      {value.length ? (
        <div
          className="qms-programme-auditor-picker__members"
          aria-label="Selected supporting auditors"
        >
          {value.map((userId) => {
            const person = people.find((candidate) => candidate.id === userId);
            return (
              <span key={userId}>
                {person?.full_name || "Assigned auditor"}
                <button
                  type="button"
                  aria-label={`Remove ${person?.full_name || "auditor"}`}
                  onClick={() =>
                    onChange(value.filter((candidate) => candidate !== userId))
                  }
                >
                  <X size={13} />
                </button>
              </span>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};

type ObserverSelectProps = {
  id: string;
  people: readonly PlannerPersonOption[];
  leadAuditorUserId?: string | null;
  supportingAuditorUserIds?: readonly string[];
  value?: string | null;
  onChange: (userId: string) => void;
};

export const ProgrammeObserverSelect: React.FC<ObserverSelectProps> = ({
  id,
  people,
  leadAuditorUserId,
  supportingAuditorUserIds = [],
  value,
  onChange,
}) => {
  const supporting = new Set(supportingAuditorUserIds);
  return (
    <label htmlFor={id}>
      <span>Observer</span>
      <span className="qms-programme-observer-select">
        <Eye size={15} aria-hidden="true" />
        <select
          id={id}
          value={value || ""}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">No observer</option>
          {people
            .filter(
              (person) =>
                person.id !== leadAuditorUserId &&
                (!supporting.has(person.id) || person.id === value),
            )
            .map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
              </option>
            ))}
        </select>
      </span>
    </label>
  );
};
