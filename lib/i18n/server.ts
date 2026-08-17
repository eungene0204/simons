import { cookies } from "next/headers";
import { DEFAULT_LANGUAGE, isLanguage, LANGUAGE_COOKIE, setLanguage, type Language } from "./index";

/**
 * 서버 컴포넌트·라우트 핸들러 전용 — 요청 쿠키에서 표시 언어를 읽는다.
 * 읽는 김에 모듈 언어도 맞춰 두어, 같은 요청 안에서 이어지는 `t()` 호출이 요청 언어를 쓰게 한다
 * (서버 컴포넌트는 LanguageProvider 렌더 전에 실행되므로 스스로 맞춰야 한다).
 */
export function getRequestLanguage(): Language {
  let language: Language = DEFAULT_LANGUAGE;
  try {
    const value = cookies().get(LANGUAGE_COOKIE)?.value;
    if (isLanguage(value)) language = value;
  } catch {
    // 정적 렌더 등 요청 컨텍스트 밖 — 기본 언어.
  }
  setLanguage(language);
  return language;
}
