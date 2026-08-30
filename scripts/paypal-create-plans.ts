#!/usr/bin/env ts-node
/**
 * PayPal 빌링 플랜 생성 스크립트 (글로벌 /us 정기구독)
 *
 * PayPal 구독은 상품(Catalog Product) → 빌링 플랜(Billing Plan) → 구독(Subscription)
 * 3계층이다. 상품·플랜은 사용자마다 만드는 게 아니라 플랜당 1개씩 미리 만들어 두고,
 * 그 plan_id를 환경변수로 주입해 구독 생성 때 참조한다.
 *
 * 사용법:
 *   ts-node scripts/paypal-create-plans.ts --pro 19 --premium 39            # 미리보기(생성 안 함)
 *   ts-node scripts/paypal-create-plans.ts --pro 19 --premium 39 --apply    # 실제 생성
 *
 * ⚠️ --apply로 만든 플랜의 금액은 PayPal 쪽에 고정된다. 나중에 바꾸려면 가격 개정
 *    절차(기존 구독자 통지·동의)가 별도로 필요하므로 출시 가격을 확정하고 실행할 것.
 *
 * 자격증명은 환경변수(PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET/PAYPAL_API_BASE)에서 읽고,
 * 없으면 프로젝트 루트 .env에서 읽는다. API_BASE 미설정 시 sandbox다.
 */

import { readFileSync } from "fs";
import { join } from "path";

const SANDBOX_API_BASE = "https://api-m.sandbox.paypal.com";

/** 저장소 루트의 .env를 읽어 환경변수에 채운다(ts-node는 Next와 달리 .env를 자동 로드하지 않는다). */
function loadEnv(): Record<string, string> {
  const env: Record<string, string> = { ...(process.env as Record<string, string>) };
  const envPath = join(process.cwd(), ".env");
  let raw: string;
  try {
    raw = readFileSync(envPath, "utf-8");
  } catch {
    // 읽지 못한 사실을 조용히 넘기지 않는다 — 자격증명 누락 원인이 여기일 수 있다
    console.warn(`(.env를 읽지 못했습니다: ${envPath} — 환경변수만 사용합니다. 저장소 루트에서 실행하세요.)`);
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

/** --pro 19 --premium 39 --apply 형태의 인자를 읽는다. 가격은 생략 불가(기본값 없음). */
function parseArgs(argv: string[]) {
  const get = (flag: string): string | undefined => {
    const i = argv.indexOf(flag);
    return i === -1 ? undefined : argv[i + 1];
  };
  const pro = get("--pro");
  const premium = get("--premium");
  if (!pro || !premium) {
    throw new Error(
      "월 구독 금액을 지정해야 합니다: --pro <USD> --premium <USD> (예: --pro 19 --premium 39)"
    );
  }
  const toAmount = (raw: string, label: string): string => {
    const value = Number(raw);
    if (!Number.isFinite(value) || value <= 0) {
      throw new Error(`${label} 금액이 올바르지 않습니다: ${raw}`);
    }
    return value.toFixed(2);
  };
  return {
    pro: toAmount(pro, "PRO"),
    premium: toAmount(premium, "PREMIUM"),
    apply: argv.includes("--apply"),
  };
}

async function main() {
  const { pro, premium, apply } = parseArgs(process.argv.slice(2));
  const env = loadEnv();
  const apiBase = env.PAYPAL_API_BASE?.trim() || SANDBOX_API_BASE;
  const clientId = env.PAYPAL_CLIENT_ID;
  const clientSecret = env.PAYPAL_CLIENT_SECRET;
  const isLive = !apiBase.includes("sandbox");

  console.log(`대상: ${isLive ? "라이브" : "sandbox"} (${apiBase})`);
  console.log(`자격증명: ${clientId && clientSecret ? "확인됨" : "없음"}`);
  console.log(`플랜: Pro $${pro}/월, Premium $${premium}/월`);
  if (!apply) {
    console.log("\n미리보기입니다 — 실제로 만들려면 --apply를 붙여 다시 실행하세요.");
    return;
  }
  if (!clientId || !clientSecret) {
    throw new Error("PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET가 없습니다(.env 또는 환경변수).");
  }

  const auth = Buffer.from(`${clientId}:${clientSecret}`).toString("base64");
  const tokenRes = await fetch(`${apiBase}/v1/oauth2/token`, {
    method: "POST",
    headers: {
      Authorization: `Basic ${auth}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: "grant_type=client_credentials",
  });
  const tokenBody = (await tokenRes.json().catch(() => null)) as { access_token?: string } | null;
  if (!tokenRes.ok || !tokenBody?.access_token) {
    throw new Error(`PayPal 인증 실패 (HTTP ${tokenRes.status})`);
  }
  const token = tokenBody.access_token;

  async function post<T>(path: string, body: unknown, requestId: string): Promise<T> {
    const res = await fetch(`${apiBase}${path}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        // 같은 스크립트를 다시 돌려도 자원이 중복 생성되지 않게 한다
        "PayPal-Request-Id": requestId,
        Prefer: "return=representation",
      },
      body: JSON.stringify(body),
    });
    const data = (await res.json().catch(() => null)) as
      | { id?: string; message?: string; details?: Array<{ description?: string }> }
      | null;
    if (!res.ok) {
      const detail = data?.details?.[0]?.description ?? data?.message ?? "요청 실패";
      throw new Error(`${path} 실패 (HTTP ${res.status}): ${detail}`);
    }
    return data as T;
  }

  const product = await post<{ id: string }>(
    "/v1/catalogs/products",
    {
      name: "NullStock Subscription",
      description: "Strategy research and backtesting platform subscription",
      type: "SERVICE",
      category: "SOFTWARE",
    },
    "nullstock-product-v1"
  );
  console.log(`\n상품 생성: ${product.id}`);

  for (const [planId, amount] of [
    ["PRO", pro],
    ["PREMIUM", premium],
  ] as const) {
    const plan = await post<{ id: string }>(
      "/v1/billing/plans",
      {
        product_id: product.id,
        name: `NullStock ${planId === "PRO" ? "Pro" : "Premium"} Monthly`,
        description: `NullStock ${planId === "PRO" ? "Pro" : "Premium"} plan, billed monthly`,
        status: "ACTIVE",
        billing_cycles: [
          {
            frequency: { interval_unit: "MONTH", interval_count: 1 },
            tenure_type: "REGULAR",
            sequence: 1,
            total_cycles: 0, // 0 = 해지할 때까지 무기한 갱신
            pricing_scheme: { fixed_price: { value: amount, currency_code: "USD" } },
          },
        ],
        payment_preferences: {
          auto_bill_outstanding: true,
          setup_fee: { value: "0", currency_code: "USD" },
          setup_fee_failure_action: "CONTINUE",
          payment_failure_threshold: 3, // 연속 실패 한도 — 한국 빌링(BILLING_MAX_FAIL_COUNT)과 동일
        },
      },
      `nullstock-plan-${planId.toLowerCase()}-${amount}`
    );
    console.log(`플랜 생성 ${planId} ($${amount}/월): ${plan.id}`);
    console.log(`  → .env에 PAYPAL_PLAN_${planId}=${plan.id}`);
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
