import type { VirtualAccount } from "@/types/portfolio";

let cachedAccounts: VirtualAccount[] | null = null;
let inFlightRequest: Promise<VirtualAccount[]> | null = null;

export function getCachedVirtualAccounts() {
  return cachedAccounts;
}

export function setCachedVirtualAccounts(accounts: VirtualAccount[]) {
  cachedAccounts = accounts;
}

export function clearVirtualAccountOverviewCache() {
  cachedAccounts = null;
  inFlightRequest = null;
}

export async function refreshVirtualAccountOverviewCache(options?: {
  force?: boolean;
}) {
  if (inFlightRequest && !options?.force) {
    return inFlightRequest;
  }

  inFlightRequest = fetch("/api/virtual-account")
    .then((response) => (response.ok ? response.json() : cachedAccounts ?? []))
    .then((accounts: unknown) => {
      const nextAccounts = Array.isArray(accounts)
        ? (accounts as VirtualAccount[])
        : [];
      cachedAccounts = nextAccounts;
      return nextAccounts;
    })
    .catch(() => cachedAccounts ?? [])
    .finally(() => {
      inFlightRequest = null;
    });

  return inFlightRequest;
}
