import { useEffect } from 'react';
import { useReplay } from './store';
export function usePlayback() {
  const playing = useReplay((s) => s.playing);
  useEffect(() => {
    if (!playing) return;
    let frame = 0,
      last = 0;
    const tick = (time: number) => {
      if (document.hidden) {
        last = time;
        frame = requestAnimationFrame(tick);
        return;
      }
      if (last) {
        const state = useReplay.getState(),
          inc = ((time - last) / 1000) * state.rate;
        const end = state.records.length - 1;
        const next = state.cursor + inc;
        if (next >= end) {
          if (state.loop) state.seek(0);
          else if (state.status === 'ready') state.pause();
          else state.seek(end);
        } else state.seek(next);
      }
      last = time;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);
}
