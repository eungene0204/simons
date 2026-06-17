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
    .then((response) => {
      if (response.ok) return response.json();
      if (cachedAccounts) return cachedAccounts;
      throw new Error("Failed to load virtual accounts");
    })
    .then((accounts: unknown) => {
      const nextAccounts = Array.isArray(accounts)
        ? (accounts as VirtualAccount[])
        : [];
      cachedAccounts = nextAccounts;
      return nextAccounts;
    })
    .catch((error) => {
      if (cachedAccounts) return cachedAccounts;
      throw error;
    })
    .finally(() => {
      inFlightRequest = null;
    });

  return inFlightRequest;
}
