import { getRequestRegion } from "@/lib/geo/server";
import { REGION_LANGUAGE } from "@/lib/geo/region";
import { setLanguage, type Language } from "./index";

/**
 * 서버 컴포넌트·라우트 핸들러 전용 — 요청 지역(경로 파생, lib/geo)에서 표시 언어를 정한다.
 * 읽는 김에 모듈 언어도 맞춰 두어, 같은 요청 안에서 이어지는 `t()` 호출이 요청 언어를 쓰게 한다
 * (서버 컴포넌트는 LanguageProvider 렌더 전에 실행되므로 스스로 맞춰야 한다).
 */
export function getRequestLanguage(): Language {
  const language = REGION_LANGUAGE[getRequestRegion()];
  setLanguage(language);
  return language;
}
