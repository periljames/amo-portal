import React, { useEffect, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";

import BaseStationEditorDialogV2, {
  type BaseDraft,
  type BaseEditorState,
} from "./BaseStationEditorDialogV2";
import { getCachedUser } from "../../services/auth";
import {
  getAdminContext,
  setAdminContext,
  type AdminContext,
} from "../../services/adminUsers";
import { listBaseStations, updateBaseStation } from "../../services/foundations";
import type { BaseStationCreate, BaseStationRead } from "../../types/foundations";

export type { BaseDraft, BaseEditorState } from "./BaseStationEditorDialogV2";

type Props = {
  editor: BaseEditorState;
  saving: boolean;
  onChange: (draft: BaseDraft) => void;
  onClose: () => void;
  onSave: () => void;
  onLocationChanged: () => Promise<void> | void;
};

function optionalNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function draftFromBase(base: BaseStationRead): BaseDraft {
  return {
    code: base.code,
    name: base.name,
    icao_code: base.icao_code || "",
    iata_code: base.iata_code || "",
    base_type: base.base_type,
    time_zone: base.time_zone || Intl.DateTimeFormat().resolvedOptions().timeZone || "Africa/Nairobi",
    description: base.description || "",
    aliases: (base.aliases || []).map((alias) => alias.alias).join(", "),
    latitude: base.latitude == null ? "" : String(base.latitude),
    longitude: base.longitude == null ? "" : String(base.longitude),
    coordinate_accuracy_m: base.coordinate_accuracy_m == null ? "" : String(base.coordinate_accuracy_m),
    location_source: base.location_source || "",
    airport_reference_ident: base.airport_reference_ident || "",
    geofence_radius_m: String(base.geofence_radius_m || 250),
    checkin_prompt_enabled: base.checkin_prompt_enabled,
    checkout_reminder_enabled: base.checkout_reminder_enabled,
    suspicious_location_review_enabled: base.suspicious_location_review_enabled,
    is_active: base.is_active,
  };
}

function payloadFromDraft(draft: BaseDraft): BaseStationCreate {
  const latitude = optionalNumber(draft.latitude);
  const longitude = optionalNumber(draft.longitude);
  const hasCoordinates = latitude != null && longitude != null;
  return {
    code: draft.code.trim().toUpperCase(),
    name: draft.name.trim(),
    icao_code: draft.icao_code.trim().toUpperCase() || null,
    iata_code: draft.iata_code.trim().toUpperCase() || null,
    base_type: draft.base_type,
    time_zone: draft.time_zone.trim() || null,
    description: draft.description.trim() || null,
    aliases: draft.aliases.split(",").map((alias) => alias.trim()).filter(Boolean),
    latitude,
    longitude,
    coordinate_accuracy_m: hasCoordinates ? optionalNumber(draft.coordinate_accuracy_m) : null,
    location_source: hasCoordinates ? draft.location_source || "MANUAL" : null,
    airport_reference_ident: hasCoordinates
      ? draft.airport_reference_ident.trim().toUpperCase() || null
      : null,
    geofence_radius_m: Math.max(50, Math.min(5000, Number(draft.geofence_radius_m || 250))),
    checkin_prompt_enabled: hasCoordinates && draft.checkin_prompt_enabled,
    checkout_reminder_enabled: hasCoordinates && draft.checkout_reminder_enabled,
    suspicious_location_review_enabled: hasCoordinates && draft.suspicious_location_review_enabled,
    is_active: draft.is_active,
  };
}

const BaseStationEditorDialogCompat: React.FC<Props> = ({
  editor,
  saving,
  onChange,
  onClose,
  onSave,
  onLocationChanged,
}) => {
  const isSuperuser = Boolean(getCachedUser()?.is_superuser);
  const [bases, setBases] = useState<BaseStationRead[]>([]);
  const [selectedExisting, setSelectedExisting] = useState<BaseStationRead | null>(null);
  const [updatingExisting, setUpdatingExisting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tenantContextRef = useRef<AdminContext | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadScopedBases = async () => {
      setError(null);
      try {
        if (isSuperuser) {
          const context = await getAdminContext();
          if (cancelled) return;
          if (!context.active_amo_id) {
            throw new Error("Select an AMO support context before editing its operating bases.");
          }
          tenantContextRef.current = context;
          await setAdminContext({
            active_amo_id: context.active_amo_id,
            data_mode: context.data_mode,
          });
        } else {
          tenantContextRef.current = null;
        }

        const items = await listBaseStations({ include_inactive: true });
        if (!cancelled) setBases(items);
      } catch (cause) {
        if (cancelled) return;
        setBases([]);
        setError(cause instanceof Error && cause.message.trim()
          ? cause.message
          : "The selected AMO's base records could not be loaded.");
      }
    };

    void loadScopedBases();
    return () => { cancelled = true; };
  }, [editor.id, isSuperuser]);

  useEffect(() => {
    setSelectedExisting(null);
    setError(null);
  }, [editor.id]);

  const compatibleEditor = useMemo<BaseEditorState>(() => (
    selectedExisting
      ? { id: selectedExisting.id, draft: editor.draft }
      : editor
  ), [editor, selectedExisting]);

  const editExisting = (base: BaseStationRead) => {
    setSelectedExisting(base);
    setError(null);
    onChange(draftFromBase(base));
  };

  const save = async () => {
    if (!selectedExisting) {
      onSave();
      return;
    }
    setUpdatingExisting(true);
    setError(null);
    try {
      if (isSuperuser) {
        const context = tenantContextRef.current;
        if (!context?.active_amo_id) {
          throw new Error("The AMO context used to open this base is no longer available. Close the dialog and reopen it from the intended tenant.");
        }
        await setAdminContext({
          active_amo_id: context.active_amo_id,
          data_mode: context.data_mode,
        });
      }
      await updateBaseStation(selectedExisting.id, payloadFromDraft(editor.draft));
      await onLocationChanged();
      onClose();
    } catch (cause) {
      setError(cause instanceof Error && cause.message.trim()
        ? cause.message
        : "The existing base could not be updated.");
    } finally {
      setUpdatingExisting(false);
    }
  };

  return (
    <>
      {error ? (
        <div className="setup-resend__toast setup-resend__toast--danger setup-base-editor__compat-error" role="alert" aria-live="assertive">
          <div><strong>Base could not be updated</strong><span>{error}</span></div>
          <button type="button" aria-label="Dismiss notification" onClick={() => setError(null)}><X size={15} /></button>
        </div>
      ) : null}
      <BaseStationEditorDialogV2
        key={selectedExisting?.id || editor.id || "new-base"}
        editor={compatibleEditor}
        existingBases={bases}
        saving={saving || updatingExisting}
        onEditExisting={editExisting}
        onChange={onChange}
        onClose={onClose}
        onSave={() => void save()}
        onLocationChanged={onLocationChanged}
      />
    </>
  );
};

export default BaseStationEditorDialogCompat;
