// 널스탁 다국어(i18n) 코어.
//
// 설계 요약
// - 소스 코드의 원문은 한국어 그대로 두고, 표시 지점에서 `t("한국어 원문")`으로 감싼다.
//   한국어 원문 자체가 사전 키다(별도 키 네이밍 없음). 사전에 없는 키는 원문(한국어)을
//   그대로 돌려주므로 번역 누락이 빈칸이나 깨진 화면으로 번지지 않는다.
// - 치환은 `{0}`, `{1}` … 위치 인자다: `t("총 {0}회 거래", n)`.
// - 언어는 쿠키(`nullstock.lang`)와 localStorage에 함께 저장한다. 쿠키는 서버 렌더링(SSR /
//   서버 컴포넌트)이 요청 언어를 알기 위한 것이고, localStorage는 클라이언트 초기화용이다.
// - 전환은 페이지 새로고침으로 반영한다(LanguageToggle 참조). 모듈 상수·useMemo·캐시에
//   남은 옛 언어 문자열이 새 언어로 섞여 보이는 상태를 구조적으로 배제하기 위해서다.
//
// 규칙
// - `t()`는 렌더·이벤트 핸들러 안에서만 호출한다. 모듈 최상위 상수(`const TABS = [{ label:
//   t("...") }]`)에서 호출하면 서버 프로세스 수명 동안 첫 언어로 고정된다. 상수에는 한국어
//   키를 두고 표시 지점에서 `t(item.label)`로 감싼다.
// - 백엔드로 보내는 값(파서 프롬프트·칩 에코·비교 대상 문자열)은 감싸지 않는다 — 번역은
//   표시 전용이다.
import { en } from "./en";

export type Language = "ko" | "en";

export const LANGUAGE_COOKIE = "nullstock.lang";
export const LANGUAGE_STORAGE_KEY = "nullstock.lang";
export const DEFAULT_LANGUAGE: Language = "ko";
export const SUPPORTED_LANGUAGES: readonly Language[] = ["ko", "en"];

const dictionaries: Record<Language, Record<string, string>> = {
  ko: {},
  en,
};

let currentLanguage: Language | null = null;

export function isLanguage(value: unknown): value is Language {
  return value === "ko" || value === "en";
}

function readCookieLanguage(): Language | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${LANGUAGE_COOKIE.replace(".", "\\.")}=([^;]*)`)
  );
  const value = match ? decodeURIComponent(match[1]) : null;
  return isLanguage(value) ? value : null;
}

function readStoredLanguage(): Language | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return isLanguage(value) ? value : null;
  } catch {
    return null;
  }
}

/** 현재 표시 언어. 클라이언트에선 쿠키 → localStorage → 기본값(ko) 순으로 초기화한다. */
export function getLanguage(): Language {
  if (currentLanguage) return currentLanguage;
  const detected = readCookieLanguage() ?? readStoredLanguage() ?? DEFAULT_LANGUAGE;
  currentLanguage = detected;
  return detected;
}

/**
 * 프로세스(서버) 또는 탭(클라이언트)의 현재 언어를 지정한다.
 * LanguageProvider가 렌더 시점에 호출해 SSR과 클라이언트가 같은 언어로 그리게 한다.
 * 영속(쿠키·localStorage)은 하지 않는다 — 그건 persistLanguage의 몫이다.
 */
export function setLanguage(language: Language): void {
  currentLanguage = language;
}

/** 브라우저에 언어를 영속한다(쿠키 1년 + localStorage). */
export function persistLanguage(language: Language): void {
  if (typeof document !== "undefined") {
    const maxAge = 60 * 60 * 24 * 365;
    document.cookie = `${LANGUAGE_COOKIE}=${language}; path=/; max-age=${maxAge}; samesite=lax`;
  }
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    } catch {
      // localStorage 접근 불가(프라이버시 모드 등) — 쿠키만으로 충분하다.
    }
  }
  currentLanguage = language;
}

/** 숫자·날짜 포맷용 BCP 47 로케일. */
export function getLocale(): "ko-KR" | "en-US" {
  return getLanguage() === "en" ? "en-US" : "ko-KR";
}

function interpolate(template: string, args: unknown[]): string {
  if (args.length === 0) return template;
  return template.replace(/\{(\d+)\}/g, (match, index) => {
    const value = args[Number(index)];
    return value === undefined || value === null ? match : String(value);
  });
}

/**
 * 한국어 원문을 현재 언어로 옮긴다. 사전에 없으면 원문을 그대로 돌려준다.
 * `{0}`, `{1}` … 자리표시자는 뒤따르는 인자로 치환한다.
 */
export function t(text: string, ...args: unknown[]): string {
  const language = getLanguage();
  const translated = language === "ko" ? text : dictionaries[language][text] ?? text;
  return interpolate(translated, args);
}

/** 사전 등록 여부(테스트·커버리지 점검용). */
export function hasTranslation(language: Language, text: string): boolean {
  return language === "ko" || Object.prototype.hasOwnProperty.call(dictionaries[language], text);
}

/** 테스트 전용 — 캐시된 언어를 초기화한다. */
export function __resetLanguageForTests(): void {
  currentLanguage = null;
}

/**
 * 원화 금액의 짧은 표기. 한국어는 호출자가 억/만 단위로 만들고, 영어는 여기서 compact
 * 표기(1.5M, 320K)로 만든다 — "{0}억"을 사전으로 옮기면 소수 자릿수가 어긋나기 때문이다.
 * 반환값이 null이면 호출자의 한국어 표기를 쓴다.
 */
export function formatCompactNumberEn(value: number, options?: { withCurrency?: boolean }): string | null {
  if (getLanguage() !== "en" || !Number.isFinite(value)) return null;
  const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
  return options?.withCurrency ? `₩${compact}` : compact;
}
