const DEFAULT_BACKEND_URLS = [
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];

export function getBackendBaseUrls(): string[] {
  const envUrl = process.env.BACKEND_URL?.trim();
  const urls = envUrl ? [envUrl, ...DEFAULT_BACKEND_URLS] : DEFAULT_BACKEND_URLS;
  return Array.from(new Set(urls));
}

export async function fetchBackend(
  path: string,
  init?: RequestInit & { timeoutMs?: number }
): Promise<Response> {
  const { timeoutMs, ...requestInit } = init ?? {};
  const errors: string[] = [];

  for (const baseUrl of getBackendBaseUrls()) {
    try {
      const response = await fetch(`${baseUrl}${path}`, {
        ...requestInit,
        signal: AbortSignal.timeout(timeoutMs ?? 120_000),
      });
      return response;
    } catch (error: any) {
      errors.push(`${baseUrl}: ${error?.message ?? "fetch failed"}`);
    }
  }

  throw new Error(errors.join(" | "));
}
