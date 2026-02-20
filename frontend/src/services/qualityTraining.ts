import { apiGet, apiPost } from "./crs";
import { authHeaders } from "./auth";

export const getTrainingDashboard = () => apiGet<Record<string, number>>("/quality/training", { headers: authHeaders() });
export const listTrainingCatalog = () => apiGet<any[]>("/quality/training/catalog", { headers: authHeaders() });
export const getTrainingCourse = (courseId: string) => apiGet<any>(`/quality/training/catalog/${encodeURIComponent(courseId)}`, { headers: authHeaders() });
export const listTrainingSessions = () => apiGet<any[]>("/quality/training/sessions", { headers: authHeaders() });
export const getTrainingSession = (sessionId: string) => apiGet<any>(`/quality/training/sessions/${encodeURIComponent(sessionId)}`, { headers: authHeaders() });
export const listTrainingStaff = () => apiGet<any[]>("/quality/training/staff", { headers: authHeaders() });
export const getTrainingStaff = (staffId: string) => apiGet<any>(`/quality/training/staff/${encodeURIComponent(staffId)}`, { headers: authHeaders() });
export const listTrainingMatrix = () => apiGet<any[]>("/quality/training/matrix", { headers: authHeaders() });
export const getTrainingSettings = () => apiGet<any>("/quality/training/settings", { headers: authHeaders() });
export const updateTrainingSettings = (payload: any) => apiPost<any>("/quality/training/settings", payload, { method: "PUT", headers: authHeaders() } as RequestInit);
