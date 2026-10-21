import { useEffect } from 'react';
import { streamRun } from '../api/ws';
import { useReplay } from './store';
export function useRunStream(runId: string, enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const state = useReplay.getState();
    state.setRun(runId);
    void streamRun(runId, {
      signal: controller.signal,
      speed: 200,
      onHello: (m) => useReplay.getState().setMeta(m.n_steps, m.dt_s),
      onSteps: (rows) => useReplay.getState().append(rows),
      onSummary: (s) => useReplay.getState().setSummary(s),
    }).catch((error) => {
      if (!controller.signal.aborted)
        useReplay
          .getState()
          .setError(
            error instanceof Error ? error.message : 'Replay stream failed',
          );
    });
    return () => controller.abort();
  }, [runId, enabled]);
}
