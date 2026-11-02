export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  // Leave time for the proxy's 180-second chat budget to return a useful504.
  // Its signal is combined with the account/request lifecycle, never replaces it.
  const timeoutSignal = path.split("?", 1)[0] === "chat" ? AbortSignal.timeout(195000) : null;
  const signal = timeoutSignal ? AbortSignal.any([...(options.signal ? [options.signal] : []), timeoutSignal]) : options.signal;
  try {
    const response = await fetch(`/api/backend/${path}`, {
      ...options,
      signal,
      headers: { "Content-Type": "application/json", ...options.headers },
      cache: "no-store",
    });
    const result = await response.json().catch(failure => {
      if (signal?.aborted) throw failure;
      return {};
    });
    if (!response.ok) {
      const detail = result.detail;
      throw new ApiError(typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((item: { msg: string }) => item.msg).join("; ") : "The request could not be completed", response.status);
    }
    return result as T;
  } catch (failure) {
    if (options.signal?.aborted) throw failure;
    if (timeoutSignal?.aborted) throw new ApiError("The assistant request timed out. Check the Action inbox and Activity log before retrying; the cloud request may still be running.", 504);
    throw failure;
  }
}

export const post = <T>(path: string, data: unknown = {}) => api<T>(path, { method: "POST", body: JSON.stringify(data) });
