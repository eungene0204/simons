// 요청이 실제로 들어온 공개 주소(origin) — 외부로 나가는 복귀 URL(결제 승인 후 리다이렉트 등)을
// 만들 때 쓴다.
//
// `new URL(request.url).origin`을 쓰면 안 된다: 컨테이너 안의 Next.js(standalone)는 자기
// 주소를 localhost:3000으로 재구성하므로, Caddy 뒤에서 그 값은 방문자가 본 주소가 아니다 —
// 실제로 PayPal 승인 복귀가 https://localhost:3000 으로 떨어졌다(2026-08-31 prod).
// 방문자가 보낸 Host 헤더(프록시는 그대로 전달)와 X-Forwarded-Proto가 정본이다.
export function publicOriginFrom(request: Request): string {
  const host =
    request.headers.get("x-forwarded-host")?.split(",")[0]?.trim() ||
    request.headers.get("host") ||
    "localhost:3000";
  const proto =
    request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim() ||
    (host.startsWith("localhost") || host.startsWith("127.0.0.1") ? "http" : "https");
  return `${proto}://${host}`;
}
