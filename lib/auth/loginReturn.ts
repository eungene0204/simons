import { getSupabaseBrowserClient } from "@/lib/firebase";

// Google 로그인 복귀 처리. Supabase implicit flow라 복귀 주소의 해시에 액세스 토큰이 실려 온다.
// 예전에는 Supabase 클라이언트가 해시를 읽으며 토큰 확인 왕복(getUser)을 한 번 더 하고, 상단 내비게이션이
// 결과가 뻔한 `/api/user`를 먼저 물은 뒤에야 `/api/login`을 불러 태평양 왕복이 줄줄이 이어졌다.
// 토큰 검증은 `/api/login`이 서버에서 하므로, 해시의 토큰을 곧바로 넘겨 왕복 하나로 끝낸다.

export type LoginReturnUser = {
  name?: string | null;
  email?: string | null;
  avatarUrl?: string | null;
};

export function isLoginReturn(hash: string, search: string): boolean {
  return /(^|[#&])access_token=/.test(hash) || new URLSearchParams(search).has("code");
}

export function accessTokenFromHash(hash: string): string | null {
  return new URLSearchParams(hash.replace(/^#/, "")).get("access_token");
}

// 가림막(LoginReturnVeil)과 상단 내비게이션이 같은 교환 결과를 기다리도록 토큰별로 한 번만 보낸다.
let pending: { token: string | null; result: Promise<LoginReturnUser | null> } | null = null;

export function completeLoginReturn(): Promise<LoginReturnUser | null> {
  const token = accessTokenFromHash(window.location.hash);
  if (pending && pending.token === token) return pending.result;
  pending = { token, result: exchange(token) };
  return pending.result;
}

async function exchange(hashToken: string | null): Promise<LoginReturnUser | null> {
  try {
    // 해시에 토큰이 없으면(`?code=` PKCE 복귀) Supabase 클라이언트가 코드를 교환해야 한다.
    const accessToken =
      hashToken ?? (await getSupabaseBrowserClient().auth.getSession()).data.session?.access_token;
    if (!accessToken) return null;

    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ supabaseAccessToken: accessToken }),
    });
    const data = (await response.json()) as { user?: LoginReturnUser | null };
    return response.ok && data.user ? data.user : null;
  } catch {
    return null;
  } finally {
    // 토큰을 주소창·방문 기록에 남기지 않는다.
    if (hashToken) {
      window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
    }
  }
}
