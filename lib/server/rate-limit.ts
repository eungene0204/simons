// 인메모리 고정 윈도우 레이트리미터.
//
// 배포 전제: 단일 박스 docker compose(Next 인스턴스 1개) — 프로세스 메모리로 충분하다.
// 다중 인스턴스로 확장하면 외부 저장소(Redis 등)로 교체해야 한다.
// 재시작 시 카운터가 초기화되는 것은 감수한다(보호 목적의 상한이지 과금 목적이 아님).

type Bucket = {
  count: number
  resetAt: number
}

const buckets = new Map<string, Bucket>()

// 만료 버킷이 무한히 쌓이지 않도록 주기적으로 청소한다.
const SWEEP_THRESHOLD = 10_000

function sweep(now: number) {
  for (const [key, bucket] of buckets) {
    if (now >= bucket.resetAt) buckets.delete(key)
  }
}

/**
 * 키별 고정 윈도우 카운터를 1 소비한다.
 * @returns true면 허용, false면 한도 초과(요청 거부)
 */
export function consumeRateLimit(
  key: string,
  limit: number,
  windowMs: number,
  now: number = Date.now()
): boolean {
  if (buckets.size > SWEEP_THRESHOLD) sweep(now)

  const bucket = buckets.get(key)
  if (!bucket || now >= bucket.resetAt) {
    buckets.set(key, { count: 1, resetAt: now + windowMs })
    return true
  }
  if (bucket.count >= limit) return false
  bucket.count += 1
  return true
}

export function __resetRateLimitForTests() {
  buckets.clear()
}
