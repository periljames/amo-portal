import { useSyncExternalStore } from 'react';
import { hasActiveTenantAdminProfile,onAdminProfileChange } from '../services/adminProfileMode';
export function useQmsAdminMode(amoCode:string){return useSyncExternalStore(callback=>onAdminProfileChange(()=>callback()),()=>hasActiveTenantAdminProfile(amoCode),()=>false);}
