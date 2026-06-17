const LAST_DETAIL_ACCOUNT_KEY = "virtual-account:last-detail-account-id";

export function rememberVirtualAccountDetail(accountId: string) {
  if (typeof window === "undefined" || !accountId) return;

  try {
    window.sessionStorage.setItem(LAST_DETAIL_ACCOUNT_KEY, accountId);
  } catch {
    // Navigation memory is best-effort and should never block the page.
  }
}

export function readLastVirtualAccountDetail() {
  if (typeof window === "undefined") return null;

  try {
    return window.sessionStorage.getItem(LAST_DETAIL_ACCOUNT_KEY);
  } catch {
    return null;
  }
}

export function forgetVirtualAccountDetail(accountId?: string) {
  if (typeof window === "undefined") return;

  try {
    if (
      !accountId ||
      window.sessionStorage.getItem(LAST_DETAIL_ACCOUNT_KEY) === accountId
    ) {
      window.sessionStorage.removeItem(LAST_DETAIL_ACCOUNT_KEY);
    }
  } catch {
    // Ignore storage failures; the account list remains the fallback.
  }
}
