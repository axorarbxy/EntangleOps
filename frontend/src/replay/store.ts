import { create } from 'zustand';
import type { StepRecord, Summary } from '../api/schemas';
interface ReplayState {
  runId: string | null;
  records: StepRecord[];
  nSteps: number;
  dtS: number;
  status: 'idle' | 'loading' | 'ready' | 'error';
  error: string | null;
  summary: Summary | null;
  cursor: number;
  playing: boolean;
  rate: number;
  loop: boolean;
  setRun: (id: string) => void;
  setMeta: (n: number, dt: number) => void;
  append: (records: StepRecord[]) => void;
  setSummary: (summary: Summary) => void;
  setError: (message: string) => void;
  seek: (step: number) => void;
  play: () => void;
  pause: () => void;
  step: (by: number) => void;
  setRate: (rate: number) => void;
  clear: () => void;
}
export const useReplay = create<ReplayState>((set, get) => ({
  runId: null,
  records: [],
  nSteps: 0,
  dtS: 60,
  status: 'idle',
  error: null,
  summary: null,
  cursor: 0,
  playing: false,
  rate: 5,
  loop: false,
  setRun: (runId) =>
    set({
      runId,
      records: [],
      status: 'loading',
      error: null,
      summary: null,
      cursor: 0,
      playing: false,
    }),
  setMeta: (nSteps, dtS) => set({ nSteps, dtS }),
  append: (records) =>
    set((s) => ({
      records: [...s.records, ...records],
      status: s.summary ? 'ready' : 'loading',
    })),
  setSummary: (summary) => set({ summary, status: 'ready' }),
  setError: (error) => set({ error, status: 'error', playing: false }),
  seek: (cursor) =>
    set((s) => ({
      cursor: Math.max(0, Math.min(cursor, Math.max(0, s.records.length - 1))),
    })),
  play: () => set({ playing: true }),
  pause: () => set({ playing: false }),
  step: (by) => get().seek(get().cursor + by),
  setRate: (rate) => set({ rate }),
  clear: () =>
    set({
      runId: null,
      records: [],
      nSteps: 0,
      summary: null,
      cursor: 0,
      playing: false,
      status: 'idle',
      error: null,
    }),
}));
