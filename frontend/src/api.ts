import { useEffect, useRef, useState } from 'react';

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const timeout = AbortSignal.timeout(10_000);
  const signal = init?.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
  const response = await fetch(path, { ...init, signal });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const message = body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string'
      ? body.detail : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const resources = ['health', 'cameras', 'scenarios', 'observations', 'aircraft'] as const;
export type Resource = typeof resources[number];

type Connection = 'connecting' | 'online' | 'retrying';

// Events invalidate REST resources. A reconnect always refreshes the complete visible state.
export function useUpdates(refresh: (resources: readonly Resource[]) => void): Connection {
  const latest = useRef(refresh);
  const [connection, setConnection] = useState<Connection>('connecting');
  useEffect(() => { latest.current = refresh; }, [refresh]);
  useEffect(() => {
    let socket: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let watchdog: ReturnType<typeof setTimeout> | undefined;
    let fallback: ReturnType<typeof setInterval> | undefined;
    let stopped = false;
    let delay = 500;
    function connect() {
      const url = new URL('/ws', window.location.href);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      const current = new WebSocket(url);
      socket = current;

      function resetWatchdog() {
        clearTimeout(watchdog);
        watchdog = setTimeout(() => current.close(), 45_000);
      }

      resetWatchdog();
      current.addEventListener('message', (message) => {
        if (stopped || socket !== current || typeof message.data !== 'string') return;
        let payload: unknown;
        try {
          payload = JSON.parse(message.data);
        } catch {
          return;
        }
        if (!payload || typeof payload !== 'object' || !('type' in payload)) return;
        resetWatchdog();
        if (payload.type === 'ready') {
          delay = 500;
          clearInterval(fallback);
          fallback = undefined;
          setConnection('online');
          latest.current(resources);
        } else if (payload.type === 'changed') {
          const affected = 'resources' in payload ? payload.resources : undefined;
          latest.current(Array.isArray(affected)
            ? resources.filter((resource) => affected.includes(resource))
            : resources);
        }
      });
      current.addEventListener('error', () => current.close());
      current.addEventListener('close', () => {
        if (stopped || socket !== current) return;
        clearTimeout(watchdog);
        setConnection('retrying');
        if (fallback === undefined) {
          const pollCameras = () => latest.current(['health', 'cameras']);
          pollCameras();
          fallback = setInterval(pollCameras, 5000);
        }
        retry = setTimeout(connect, delay);
        delay = Math.min(delay * 2, 15_000);
      });
    }
    connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      clearTimeout(watchdog);
      clearInterval(fallback);
      socket?.close();
    };
  }, []);
  return connection;
}

export function useResource<T>(path: string | null, revision: number) {
  const [result, setResult] = useState<{ path: string; data?: T; error?: string }>();
  const reload = useRef<(() => void) | undefined>(undefined);
  useEffect(() => {
    if (!path) return;
    const resource = path;
    const controller = new AbortController();
    let running = false;
    let dirty = false;

    async function load() {
      if (running) {
        dirty = true;
        return;
      }
      running = true;
      do {
        dirty = false;
        try {
          const data = await api<T>(resource, { signal: controller.signal });
          if (!controller.signal.aborted) setResult({ path: resource, data });
        } catch (error) {
          if (!controller.signal.aborted) {
            const message = error instanceof Error ? error.message : 'Błąd połączenia';
            setResult((old) => ({ path: resource, data: old?.path === resource ? old.data : undefined, error: message }));
          }
        }
      } while (dirty && !controller.signal.aborted);
      running = false;
    }

    reload.current = () => { void load(); };
    return () => {
      controller.abort();
      reload.current = undefined;
    };
  }, [path]);
  useEffect(() => { reload.current?.(); }, [path, revision]);
  return result?.path === path ? result : undefined;
}
