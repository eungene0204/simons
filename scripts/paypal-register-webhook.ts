#!/usr/bin/env ts-node
/**
 * PayPal 웹훅 등록 스크립트 (글로벌 /us 정기구독)
 *
 * 웹훅은 PayPal이 결제·구독 상태 변화를 우리 서버로 알려주는 통로다. 등록하면 웹훅 ID가
 * 나오고, 그 값이 있어야 수신 라우트가 서명을 검증할 수 있다(PAYPAL_WEBHOOK_ID).
 *
 * 사용법:
 *   ts-node scripts/paypal-register-webhook.ts --url https://www.nullstock.im/api/payment/paypal/webhook
 *   ts-node scripts/paypal-register-webhook.ts --url <URL> --apply     # 실제 등록
 *   ts-node scripts/paypal-register-webhook.ts --list                  # 등록된 웹훅 조회
 *
 * sandbox/라이브는 서로 다른 웹훅이다 — 라이브 전환 시 라이브 키로 다시 등록해야 한다.
 */

import { readFileSync } from "fs";
import { join } from "path";

const SANDBOX_API_BASE = "https://api-m.sandbox.paypal.com";

/** 수신 라우트가 실제로 처리하는 이벤트만 구독한다(app/api/payment/paypal/webhook/route.ts). */
const EVENT_TYPES = [
  "BILLING.SUBSCRIPTION.ACTIVATED",
  "BILLING.SUBSCRIPTION.UPDATED",
  "BILLING.SUBSCRIPTION.CANCELLED",
  "BILLING.SUBSCRIPTION.SUSPENDED",
  "BILLING.SUBSCRIPTION.EXPIRED",
  "PAYMENT.SALE.COMPLETED",
];

function loadEnv(): Record<string, string> {
  const env: Record<string, string> = { ...(process.env as Record<string, string>) };
  const envPath = join(process.cwd(), ".env");
  let raw: string;
  try {
    raw = readFileSync(envPath, "utf-8");
  } catch {
    console.warn(`(.env를 읽지 못했습니다: ${envPath} — 저장소 루트에서 실행하세요.)`);
    return env;
  }
  for (const line of raw.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    if (!env[key]) env[key] = trimmed.slice(eq + 1).trim();
  }
  return env;
}

async function main() {
  const argv = process.argv.slice(2);
  const urlIndex = argv.indexOf("--url");
  const url = urlIndex === -1 ? undefined : argv[urlIndex + 1];
  const list = argv.includes("--list");
  const apply = argv.includes("--apply");
  if (!list && !url) {
    throw new Error("--url <웹훅 수신 URL> 또는 --list 를 지정하세요.");
  }
  if (url && !url.startsWith("https://")) {
    throw new Error("웹훅 URL은 https여야 합니다.");
  }

  const env = loadEnv();
  const apiBase = env.PAYPAL_API_BASE?.trim() || SANDBOX_API_BASE;
  const clientId = env.PAYPAL_CLIENT_ID;
  const clientSecret = env.PAYPAL_CLIENT_SECRET;
  if (!clientId || !clientSecret) {
    throw new Error("PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET가 없습니다(.env 또는 환경변수).");
  }
  console.log(`대상: ${apiBase.includes("sandbox") ? "sandbox" : "라이브"} (${apiBase})`);

  const auth = Buffer.from(`${clientId}:${clientSecret}`).toString("base64");
  const tokenRes = await fetch(`${apiBase}/v1/oauth2/token`, {
    method: "POST",
    headers: { Authorization: `Basic ${auth}`, "Content-Type": "application/x-www-form-urlencoded" },
    body: "grant_type=client_credentials",
  });
  const tokenBody = (await tokenRes.json().catch(() => null)) as { access_token?: string } | null;
  if (!tokenRes.ok || !tokenBody?.access_token) {
    throw new Error(`PayPal 인증 실패 (HTTP ${tokenRes.status})`);
  }
  const token = tokenBody.access_token;

  async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${apiBase}${path}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const data = (await res.json().catch(() => null)) as
      | { message?: string; details?: Array<{ description?: string }> }
      | null;
    if (!res.ok) {
      const detail = data?.details?.[0]?.description ?? data?.message ?? "요청 실패";
      throw new Error(`${path} 실패 (HTTP ${res.status}): ${detail}`);
    }
    return data as T;
  }

  const existing = await call<{ webhooks?: Array<{ id: string; url: string }> }>(
    "GET",
    "/v1/notifications/webhooks"
  );
  const webhooks = existing.webhooks ?? [];
  console.log(`등록된 웹훅 ${webhooks.length}개:`);
  for (const hook of webhooks) {
    console.log(`  - ${hook.id}  ${hook.url}`);
  }
  if (list) return;

  const duplicate = webhooks.find((hook) => hook.url === url);
  if (duplicate) {
    // 이미 등록된 웹훅이면 구독 이벤트 목록만 현행으로 맞춘다(ID 유지 — env 교체 불필요)
    console.log(`\n같은 URL이 이미 등록돼 있습니다(${duplicate.id}) — 이벤트 목록을 갱신합니다.`);
    if (!apply) {
      console.log("미리보기입니다 — 실제로 갱신하려면 --apply를 붙여 다시 실행하세요.");
      return;
    }
    const res = await fetch(`${apiBase}/v1/notifications/webhooks/${duplicate.id}`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify([
        { op: "replace", path: "/event_types", value: EVENT_TYPES.map((name) => ({ name })) },
      ]),
    });
    if (!res.ok) {
      throw new Error(`웹훅 이벤트 갱신 실패 (HTTP ${res.status})`);
    }
    console.log(`이벤트 갱신 완료: ${EVENT_TYPES.join(", ")}`);
    console.log(`  → PAYPAL_WEBHOOK_ID=${duplicate.id} (변경 없음)`);
    return;
  }

  console.log(`\n등록할 URL: ${url}`);
  console.log(`구독할 이벤트: ${EVENT_TYPES.join(", ")}`);
  if (!apply) {
    console.log("\n미리보기입니다 — 실제로 등록하려면 --apply를 붙여 다시 실행하세요.");
    return;
  }

  const created = await call<{ id: string }>("POST", "/v1/notifications/webhooks", {
    url,
    event_types: EVENT_TYPES.map((name) => ({ name })),
  });
  console.log(`\n웹훅 등록 완료: ${created.id}`);
  console.log(`  → .env에 PAYPAL_WEBHOOK_ID=${created.id}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
