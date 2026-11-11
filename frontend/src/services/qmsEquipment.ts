// src/services/qmsEquipment.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsListResponse } from "../types/qms";

export function getQmsEquipment(amoCode: string): Promise<QmsListResponse> {
  return apiRequest<QmsListResponse>(qmsPath(amoCode, "/equipment-calibration"));
}


/** Canonical equipment/calibration governance; Inventory owns serialized stock records. */
export type CalibratedAsset = {
  id: string; title: string; description: string; status: string;
  owner_user_id: string; due_date: string | null;
  payload: {
    version: number; asset_reference: string; inventory_serial_id?: number | null;
    verified_calibration_id?: string | null; pending_calibration_id?: string | null;
  };
};
export type CalibrationItem = {
  id: string; title: string; description: string; status: string; created_by: string;
  due_date?: string | null;
  payload: {
    equipment_id: string; result?: "IN_TOLERANCE" | "OUT_OF_TOLERANCE";
    certificate_evidence_ids?: string[]; certificate_number?: string;
    detected_on?: string; impact_assessment?: string; disposition?: string;
  };
};
export type CalibrationEligibility = {
  equipment_id: string; eligible: boolean; reason: string;
  status?: string; next_due?: string | null; verified_calibration_id?: string | null;
};
export type EquipmentDetail = {
  asset: CalibratedAsset; eligibility: CalibrationEligibility;
  calibrations: CalibrationItem[]; certificates: CalibrationItem[];
  out_of_tolerance: CalibrationItem[];
};
function equipmentGovernancePath(amoCode: string, suffix: string) {
  return qmsPath(amoCode, "/equipment-calibration/governance" + suffix);
}
function equipmentPost<T>(amoCode: string, path: string, payload: object): Promise<T> {
  return apiRequest<T>(equipmentGovernancePath(amoCode, path), {
    method: "POST", body: JSON.stringify(payload), cacheTtlMs: 0, timeoutMs: 20000,
  });
}
function equipmentPath(assetId: string, path = ""): string {
  return "/assets/" + encodeURIComponent(assetId) + path;
}
export const listCalibrationAssets = (amoCode: string, offset = 0) =>
  apiRequest<{ items: Array<CalibratedAsset & { eligibility: CalibrationEligibility }>; total: number }>(
    equipmentGovernancePath(amoCode, "/assets?limit=25&offset=" + offset), { cacheTtlMs: 0 },
  );
export const getCalibrationParticipants = (amoCode: string) =>
  apiRequest<{ items: Array<{ id: string; name: string }> }>(equipmentGovernancePath(amoCode, "/participants"));
export const getInventorySerialChoices = (amoCode: string, search = "") =>
  apiRequest<{ items: Array<{ id: number; serial: string; part_number: string }> }>(
    equipmentGovernancePath(amoCode, "/inventory-serials?q=" + encodeURIComponent(search)),
  );
export const readCalibrationAsset = (amoCode: string, assetId: string) =>
  apiRequest<EquipmentDetail>(equipmentGovernancePath(amoCode, equipmentPath(assetId)), { cacheTtlMs: 0 });
export const getCalibrationEligibility = (amoCode: string, inventorySerialId: number) =>
  apiRequest<CalibrationEligibility>(equipmentGovernancePath(amoCode,
    "/eligibility?inventory_serial_id=" + encodeURIComponent(String(inventorySerialId))), { cacheTtlMs: 0 });
export const createCalibrationAsset = (amoCode: string, payload: object) =>
  equipmentPost<{ asset: CalibratedAsset }>(amoCode, "/assets", payload);
export const submitCalibration = (amoCode: string, assetId: string, payload: object) =>
  equipmentPost<{ asset: CalibratedAsset; calibration: CalibrationItem }>(
    amoCode, equipmentPath(assetId, "/calibrations"), payload);
export const verifyCalibration = (amoCode: string, assetId: string, payload: object) =>
  equipmentPost<{ asset: CalibratedAsset }>(amoCode, equipmentPath(assetId, "/calibrations/verify"), payload);
export const reportOutOfTolerance = (amoCode: string, assetId: string, payload: object) =>
  equipmentPost<{ asset: CalibratedAsset; event: CalibrationItem }>(
    amoCode, equipmentPath(assetId, "/out-of-tolerance"), payload);
export const dispositionOutOfTolerance = (amoCode: string, assetId: string, payload: object) =>
  equipmentPost<{ asset: CalibratedAsset }>(
    amoCode, equipmentPath(assetId, "/out-of-tolerance/disposition"), payload);
export const releaseCalibratedEquipment = (amoCode: string, assetId: string, payload: object) =>
  equipmentPost<{ asset: CalibratedAsset }>(
    amoCode, equipmentPath(assetId, "/return-to-service"), payload);
