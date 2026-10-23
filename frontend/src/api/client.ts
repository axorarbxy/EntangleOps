import { z } from 'zod';
import { env } from '../env';
import { useSession } from '../auth/store';
import { ApiError } from './errors';
export { ApiError } from './errors';
export async function request<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    schema: z.ZodType<T>;
    signal?: AbortSignal;
    auth?: boolean;
  },
): Promise<T> {
  if (env.demoFixtures) {
    const module = await import('../mocks/handlers');
    return options.schema.parse(
      await module.demoResponse(path, options.method ?? 'GET', options.body),
    );
  }
  const key = useSession.getState().apiKey;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (key && options.auth !== false) headers['X-API-Key'] = key;
  let response: Response;
  try {
    response = await fetch(`${env.apiBase}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
      credentials: 'omit',
      cache: 'no-store',
    });
  } catch {
    throw new ApiError(0, 'network', 'Cannot reach the EntangleOps backend');
  }
  const requestId = response.headers.get('X-Request-ID') ?? undefined;
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    const record =
      typeof body === 'object' && body !== null
        ? (body as Record<string, unknown>)
        : {};
    const retry = Number(response.headers.get('Retry-After'));
    const status = response.status;
    const code =
      status === 401
        ? 'unauthorized'
        : status === 403
          ? 'forbidden'
          : status === 404
            ? 'not_found'
            : status === 409
              ? 'conflict'
              : status === 422
                ? 'validation'
                : status === 429
                  ? 'rate_limited'
                  : status === 503
                    ? 'unavailable'
                    : status === 413
                      ? 'too_large'
                      : status >= 500
                        ? 'internal'
                        : 'network';
    const detail =
      typeof record.detail === 'string'
        ? record.detail
        : typeof record.error === 'string'
          ? record.error
          : status === 404
            ? 'Run not found'
            : `Request failed (${status})`;
    if (status === 401 && options.auth !== false)
      useSession.getState().expire();
    throw new ApiError(
      status,
      code,
      detail,
      requestId,
      Number.isFinite(retry) && retry > 0 ? retry : undefined,
      Array.isArray(record.fields)
        ? (record.fields as { loc: (string | number)[]; msg: string }[])
        : undefined,
    );
  }
  try {
    return options.schema.parse(await response.json());
  } catch (error) {
    if (error instanceof z.ZodError && import.meta.env.DEV)
      devWarn(error.issues.length);
    throw new ApiError(
      response.status,
      'parse',
      'Unexpected response from server',
      requestId,
    );
  }
}
function devWarn(issueCount: number): void {
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.warn(
      `EntangleOps API response failed validation (${issueCount} issues)`,
    );
  }
}
