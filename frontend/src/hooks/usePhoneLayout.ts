import { useSyncExternalStore } from 'react';
const query='(max-width: 700px)';
const subscribe=(change:()=>void)=>{const media=window.matchMedia(query);media.addEventListener('change',change);return()=>media.removeEventListener('change',change);};
export function usePhoneLayout(){return useSyncExternalStore(subscribe,()=>window.matchMedia(query).matches,()=>false);}
