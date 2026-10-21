import { create } from 'zustand';
import { queryClient } from '../queryClient';
import { useReplay } from '../replay/store';

export interface Principal {
  keyId: string;
  name: string;
  role: 'viewer' | 'operator' | 'admin' | 'unknown';
}
interface SessionState {
  apiKey: string | null;
  principal: Principal | null;
  setSession: (key: string, principal: Principal, remember: boolean) => void;
  expire: () => void;
}
export const useSession = create<SessionState>((set) => ({
  apiKey: null,
  principal: null,
  setSession: (apiKey, principal, remember) => {
    set({ apiKey, principal });
    if (remember)
      sessionStorage.setItem(
        'eo.session',
        JSON.stringify({ apiKey, principal }),
      );
    else sessionStorage.removeItem('eo.session');
  },
  expire: () => {
    set({ apiKey: null, principal: null });
    sessionStorage.removeItem('eo.session');
    queryClient.clear();
    useReplay.getState().clear();
    window.dispatchEvent(new Event('eo:expired'));
  },
}));
