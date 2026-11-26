// 가입 유입 경로(first-touch UTM, 2026-11-26) — 처음 들어온 링크의 utm 세 칸을 쿠키에 남겼다가
// 가입할 때 User.signupUtm*에 옮긴다. 채널별 가입 → 첫 백테스트 → 결제를 DB에서 잇기 위해서다
// (GA에는 로그인 사용자 ID를 보내지 않아 결제까지 이을 수 없다 — docs/KPI.md §7).
//
// 값은 우리가 단 링크의 캠페인 표기(x·naver_blog·myth-23 등)뿐이라 개인 정보가 아니다. 그래도
// 임의 문자열이 DB에 들어가지 않게 허용 문자·길이로 자른다(형식 정규화).

export const SIGNUP_UTM_COOKIE = "ns_first_utm";
export const SIGNUP_UTM_MAX_AGE_SEC = 30 * 24 * 60 * 60;
const MAX_LEN = 64;
const SAFE = /^[A-Za-z0-9_.\-]+$/;

export interface SignupUtm {
  source: string;
  medium: string | null;
  campaign: string | null;
}

function clean(value: string | null | undefined): string | null {
  const v = value?.trim().slice(0, MAX_LEN);
  return v && SAFE.test(v) ? v : null;
}

/** URL 쿼리 → 저장할 UTM. utm_source가 없거나 허용 형식이 아니면 null(기록하지 않음). */
export function utmFromSearchParams(params: Pick<URLSearchParams, "get">): SignupUtm | null {
  const source = clean(params.get("utm_source"));
  if (!source) return null;
  return { source, medium: clean(params.get("utm_medium")), campaign: clean(params.get("utm_campaign")) };
}

/** 쿠키 값 직렬화 — "source|medium|campaign" */
export function serializeSignupUtm(utm: SignupUtm): string {
  return [utm.source, utm.medium ?? "", utm.campaign ?? ""].join("|");
}

/** 쿠키 값 → User 생성 데이터(signupUtm*). 형식이 어긋나면 빈 객체. */
export function signupUtmFields(cookieValue: string | null | undefined): {
  signupUtmSource?: string;
  signupUtmMedium?: string | null;
  signupUtmCampaign?: string | null;
} {
  if (!cookieValue) return {};
  let raw = cookieValue;
  try {
    raw = decodeURIComponent(cookieValue);
  } catch {
    return {};
  }
  const [s, m, c] = raw.split("|");
  const source = clean(s);
  if (!source) return {};
  return { signupUtmSource: source, signupUtmMedium: clean(m), signupUtmCampaign: clean(c) };
}
