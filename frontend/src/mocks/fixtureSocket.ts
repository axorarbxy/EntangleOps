import type { SocketLike } from '../api/ws';
import { demoResponse } from './handlers';
export const fixtureSocket = (url: string): SocketLike => {
  const socket: SocketLike = {
    onopen: null,
    onmessage: null,
    onclose: null,
    onerror: null,
    close: () => {
      socket.onclose?.({ code: 1000 });
    },
  };
  const id = url.split('/ws/simulations/')[1]?.split('?')[0] ?? 'demo-run-001';
  window.setTimeout(() => {
    socket.onopen?.();
    void demoResponse(`/api/v1/simulations/${id}/steps`, 'GET', undefined)
      .then((rows) => {
        const values = rows as import('../api/schemas').StepRecord[];
        socket.onmessage?.({
          data: JSON.stringify({
            type: 'hello',
            run_id: id,
            n_steps: values.length,
            dt_s: 300,
          }),
        });
        let i = 0;
        const timer = window.setInterval(() => {
          if (i >= values.length) {
            window.clearInterval(timer);
            void demoResponse(
              '/api/v1/simulations/demo-run-001',
              'GET',
              undefined,
            ).then((run) => {
              const summary = (run as { summary: unknown }).summary;
              socket.onmessage?.({
                data: JSON.stringify({ type: 'summary', data: summary }),
              });
              socket.onclose?.({ code: 1000 });
            });
            return;
          }
          socket.onmessage?.({
            data: JSON.stringify({ type: 'step', data: values[i] }),
          });
          i++;
        }, 5);
      })
      .catch(() => socket.onerror?.());
  }, 0);
  return socket;
};
