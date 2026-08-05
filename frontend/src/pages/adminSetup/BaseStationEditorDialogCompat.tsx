import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";

import BaseStationEditorDialogV2, {
  type BaseDraft,
  type BaseEditorState,
} from "./BaseStationEditorDialogV2";
import {
  baseStationIdentityConflictMessage,
  findBaseStationIdentityConflict,
  type BaseStationIdentityConflict,
} from "../../services/foundationBaseIdentity";
import {
  captureBaseStationRequestScope,
  createBaseStation,
  listBaseStations,
  updateBaseStation,
  validateBaseStationRequestScope,
  type BaseStationRequestScope,
} from "../../services/foundations";
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

function parseOptionalNumber(
  value: string,
  label: string,
  minimum: number,
  maximum: number,
): number | null {
  const cleaned = value.trim();
  if (!cleaned) return null;
  const parsed = Number(cleaned);
  if (!Number.isFinite(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${label} must be a valid number between ${minimum} and ${maximum}.`);
  }
  return parsed;
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
  const code = draft.code.trim().toUpperCase();
  const name = draft.name.trim();
  if (!code || !name) throw new Error("Facility code and facility name are required.");

  const latitude = parseOptionalNumber(draft.latitude, "Latitude", -90, 90);
  const longitude = parseOptionalNumber(draft.longitude, "Longitude", -180, 180);
  if ((latitude == null) !== (longitude == null)) {
    throw new Error("Latitude and longitude must both be present or both be empty.");
  }

  const hasCoordinates = latitude != null && longitude != null;
  const coordinateAccuracy = hasCoordinates
    ? parseOptionalNumber(draft.coordinate_accuracy_m, "Coordinate accuracy", 0, 5000)
    : null;
  const geofenceRadius = parseOptionalNumber(draft.geofence_radius_m, "Geofence radius", 50, 5000) ?? 250;

  return {
    code,
    name,
    icao_code: draft.icao_code.trim().toUpperCase() || null,
    iata_code: draft.iata_code.trim().toUpperCase() || null,
    base_type: draft.base_type,
    time_zone: draft.time_zone.trim() || null,
    description: draft.description.trim() || null,
    aliases: draft.aliases.split(",").map((alias) => alias.trim()).filter(Boolean),
    latitude,
    longitude,
    coordinate_accuracy_m: coordinateAccuracy,
    location_source: hasCoordinates ? draft.location_source || "MANUAL" : null,
    airport_reference_ident: hasCoordinates
      ? draft.airport_reference_ident.trim().toUpperCase() || null
      : null,
    geofence_radius_m: geofenceRadius,
    checkin_prompt_enabled: hasCoordinates && draft.checkin_prompt_enabled,
    checkout_reminder_enabled: hasCoordinates && draft.checkout_reminder_enabled,
    suspicious_location_review_enabled: hasCoordinates && draft.suspicious_location_review_enabled,
    is_active: draft.is_active,
  };
}

function identityConflictFromError(error: unknown): BaseStationIdentityConflict | null {
  if (!error || typeof error !== "object") return null;
  const conflict = (error as { conflict?: unknown }).conflict;
  if (!conflict || typeof conflict !== "object") return null;
  const existingBase = (conflict as { existingBase?: unknown }).existingBase;
  if (!existingBase || typeof existingBase !== "object") return null;
  return typeof (existingBase as { id?: unknown }).id === "string"
    ? conflict as BaseStationIdentityConflict
    : null;
}

const BaseStationEditorDialogCompat: React.FC<Props> = ({
  editor,
  saving,
  onChange,
  onClose,
  onLocationChanged,
}) => {
  const [bases, setBases] = useState<BaseStationRead[]>([]);
  const [selectedExisting, setSelectedExisting] = useState<BaseStationRead | null>(null);
  const [writingBase, setWritingBase] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tenantScopeRef = useRef<BaseStationRequestScope | null>(null);

  const capturedRequestScope = useCallback((): BaseStationRequestScope => {
    if (!tenantScopeRef.current) {
      // Capture the setup page's per-tab AMO selection synchronously. Never
      // retrieve the mutable server-side support context for this dialog.
      tenantScopeRef.current = captureBaseStationRequestScope();
    }
    return validateBaseStationRequestScope(tenantScopeRef.current);
  }, []);

  const loadLiveBaseRegister = useCallback(async (): Promise<BaseStationRead[]> => {
    try {
      const scope = capturedRequestScope();
      const items = await listBaseStations({
        include_inactive: true,
        amo_id: scope.amo_id,
      });
      setBases(items);
      return items;
    } catch (cause) {
      setBases([]);
      const message = cause instanceof Error && cause.message.trim()
        ? cause.message
        : "The selected AMO's live base register could not be loaded.";
      setError(`The live base register could not be loaded: ${message}`);
      throw cause;
    }
  }, [capturedRequestScope]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    void loadLiveBaseRegister().catch((cause) => {
      if (cancelled) return;
      const message = cause instanceof Error && cause.message.trim()
        ? cause.message
        : "The selected AMO's live base register could not be loaded.";
      setError((current) => current || message);
    });
    return () => { cancelled = true; };
  }, [editor.id, loadLiveBaseRegister]);

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

  const openConflictOwner = async (
    conflict: BaseStationIdentityConflict,
    availableBases?: readonly BaseStationRead[],
  ): Promise<boolean> => {
    const liveBases = availableBases ? [...availableBases] : await loadLiveBaseRegister();
    const existing = liveBases.find((base) => base.id === conflict.existingBase.id);
    if (!existing) {
      setError(baseStationIdentityConflictMessage(conflict));
      return false;
    }

    setBases(liveBases);
    setSelectedExisting(existing);
    onChange(draftFromBase(existing));
    setError(`${baseStationIdentityConflictMessage(conflict)} The complete existing record is now open for editing.`);
    return true;
  };

  const save = async () => {
    setWritingBase(true);
    setError(null);
    try {
      const scope = capturedRequestScope();
      const payload = payloadFromDraft(editor.draft);
      const liveBases = await loadLiveBaseRegister();
      const targetId = selectedExisting?.id || editor.id || null;

      if (targetId) {
        const current = liveBases.find((base) => base.id === targetId);
        if (!current) throw new Error("The selected base no longer exists in this AMO's live register.");
        setSelectedExisting(current);
        await updateBaseStation(current.id, payload, scope);
        await onLocationChanged();
        onClose();
        return;
      }

      const candidate = {
        code: payload.code,
        aliases: payload.aliases || [],
      };
      const existingConflict = findBaseStationIdentityConflict(liveBases, candidate);
      if (existingConflict) {
        await openConflictOwner(existingConflict, liveBases);
        return;
      }

      try {
        await createBaseStation(payload, scope);
      } catch (cause) {
        const writeConflict = identityConflictFromError(cause);
        if (writeConflict) {
          await openConflictOwner(writeConflict);
          return;
        }
        throw cause;
      }

      await onLocationChanged();
      onClose();
    } catch (cause) {
      const conflict = identityConflictFromError(cause);
      if (conflict) {
        try {
          await openConflictOwner(conflict);
          return;
        } catch {
          // Preserve the original conflict message below if the refresh also failed.
        }
      }
      setError(cause instanceof Error && cause.message.trim()
        ? cause.message
        : "The base could not be saved.");
    } finally {
      setWritingBase(false);
    }
  };

  return (
    <>
      {error ? (
        <div className="setup-resend__toast setup-resend__toast--danger setup-base-editor__compat-error" role="alert" aria-live="assertive">
          <div><strong>Base action requires attention</strong><span>{error}</span></div>
          <button type="button" aria-label="Dismiss notification" onClick={() => setError(null)}><X size={15} /></button>
        </div>
      ) : null}
      <BaseStationEditorDialogV2
        key={selectedExisting?.id || editor.id || "new-base"}
        editor={compatibleEditor}
        existingBases={bases}
        saving={saving || writingBase}
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
