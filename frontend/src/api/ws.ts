import { z } from 'zod';
import { env } from '../env';
import { request } from './client';
import { StepRecord, Summary, Ticket, WsMessage } from './schemas';

export interface SocketLike {
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onclose: ((event: { code: number }) => void) | null;
  onerror: (() => void) | null;
  close: (code?: number) => void;
}
export type SocketFactory = (url: string) => SocketLike;
export const browserSocket: SocketFactory = (url) =>
  new WebSocket(url) as unknown as SocketLike;
export interface Hello {
  run_id: string;
  n_steps: number;
  dt_s: number;
}
export async function streamRun(
  runId: string,
  handlers: {
    speed?: number;
    signal: AbortSignal;
    factory?: SocketFactory;
    onHello: (message: Hello) => void;
    onSteps: (records: StepRecord[]) => void;
    onSummary: (summary: Summary) => void;
  },
): Promise<void> {
  const ticket = await request('/api/v1/ws-ticket', {
    method: 'POST',
    body: { run_id: runId },
    schema: Ticket,
    signal: handlers.signal,
  });
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = location.host;
  const url = `${protocol}//${host}/ws/simulations/${encodeURIComponent(runId)}?ticket=${encodeURIComponent(ticket.ticket)}&speed=${Math.min(200, Math.max(1, handlers.speed ?? 200))}`;
  const defaultFactory =
    env.demoFixtures
      ? (await import('../mocks/fixtureSocket')).fixtureSocket
      : browserSocket;
  const socket = (handlers.factory ?? defaultFactory)(url);
  let batch: StepRecord[] = [];
  let flushTimer = 0;
  let settled = false;
  const flush = () => {
    if (batch.length) {
      handlers.onSteps(batch);
      batch = [];
    }
    flushTimer = 0;
  };
  const finish = (error?: Error) => {
    if (settled) return;
    settled = true;
    if (flushTimer) window.clearTimeout(flushTimer);
    flush();
    handlers.signal.removeEventListener('abort', abort);
    if (error) reject(error);
    else resolve();
  };
  let resolve!: () => void, reject!: (reason: Error) => void;
  const completed = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  const abort = () => {
    socket.close(1000);
    finish(new Error('Replay stream cancelled'));
  };
  handlers.signal.addEventListener('abort', abort, { once: true });
  socket.onmessage = (event) => {
    try {
      const message = WsMessage.parse(JSON.parse(event.data));
      if (message.type === 'hello') {
        if (message.n_steps > 5760) {
          finish(new Error('Run exceeds the browser replay memory limit'));
          return;
        }
        handlers.onHello(message);
      } else if (message.type === 'step') {
        batch.push(message.data);
        if (!flushTimer) flushTimer = window.setTimeout(flush, 50);
      } else {
        flush();
        handlers.onSummary(message.data);
        finish();
      }
    } catch {
      finish(new Error('The replay stream returned an invalid message'));
    }
  };
  socket.onerror = () =>
    finish(new Error('The replay stream connection failed'));
  socket.onclose = (event) => {
    if (settled) return;
    if (event.code === 1000) finish();
    else if (event.code === 4401)
      finish(
        new Error(
          'Replay ticket expired or was revoked. Load the replay again.',
        ),
      );
    else if (event.code === 4403)
      finish(
        new Error(
          'This site origin is not allowed by the backend (EO_WS_ALLOWED_ORIGINS).',
        ),
      );
    else if (event.code === 4404) finish(new Error('Run not found'));
    else if (event.code === 4408)
      finish(new Error('The run was not ready in time — try again.'));
    else if (event.code === 4429)
      finish(
        new Error('Too many open streams (maximum 3). Close another tab.'),
      );
    else finish(new Error('Replay stream closed unexpectedly.'));
  };
  return completed;
}

export const wsSchema = z
  .object({ ticket: z.string(), expires_in: z.number() })
  .passthrough();
