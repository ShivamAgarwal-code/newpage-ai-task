/**
 * Thin HTTP client over the Part A service.
 *
 * The connector is a connector: it does not re-implement aggregation, it calls
 * the service as its configured actor (X-Actor header). The service enforces
 * permissions independently, so a bug that let a bad request through the
 * connector would still be refused at the backend.
 */

export interface ServiceResponse<T> {
  ok: boolean;
  status: number;
  body: T;
}

export class ServiceClient {
  constructor(
    private readonly baseUrl: string,
    private readonly actorEmail: string,
  ) {}

  private async request<T>(
    method: string,
    path: string,
    opts: { query?: Record<string, string | number | undefined>; body?: unknown } = {},
  ): Promise<ServiceResponse<T>> {
    const url = new URL(path, this.baseUrl);
    for (const [k, v] of Object.entries(opts.query ?? {})) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
    const headers: Record<string, string> = { "X-Actor": this.actorEmail };
    let payload: string | undefined;
    if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(opts.body);
    }
    const res = await fetch(url, { method, headers, body: payload });
    const text = await res.text();
    const body = text ? JSON.parse(text) : {};
    return { ok: res.ok, status: res.status, body };
  }

  usageSummary(group: string, period: string) {
    return this.request<any>("GET", "/api/usage/summary", { query: { group, period } });
  }

  topUsers(group: string, period: string, limit: number) {
    return this.request<any>("GET", "/api/usage/top-users", { query: { group, period, limit } });
  }

  capabilityStatus(group: string) {
    return this.request<any>("GET", "/api/capabilities", { query: { group } });
  }

  setCapability(group: string, capability: string, enabled: boolean) {
    return this.request<any>("POST", "/api/capabilities", { body: { group, capability, enabled } });
  }
}
