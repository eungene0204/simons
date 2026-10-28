"use client";

import Link from "next/link";
import { t } from "@/lib/i18n";
import { useRegion, useRegionHref } from "@/lib/geo/useRegion";

// 사업자 정보는 두 줄로 나눠 표시한다 — 대표까지 첫 줄, 주소·연락처는 다음 줄 (2026-09-03 지시).
const BUSINESS_INFO_LINE_1 =
  "상호명 : 널스페이스   사업자등록번호 : 898-50-00737   통신판매업신고번호 : 2026-서울서대문-0758   대표 : 이응준";
const BUSINESS_INFO_LINE_2 =
  "주소 : 서울특별시 서대문구 이화여대7길 37, 3층 S88호   이메일 : support@nullstock.im";
// 글로벌(/us) 푸터 — 사업자 정보(상호·대표·주소·사업자등록번호·통신판매업신고번호)는
// 한국 전자상거래법상 표기라 해외 사용자에게는 표시하지 않고 연락처만 남긴다
// (2026-08-25 지시). 한국 푸터는 법정 표기 유지.
const US_BUSINESS_INFO_TEXT = "E-mail: support@nullstock.im";
const BUSINESS_EMAIL = "support@nullstock.im";

function withEmailLink(info: string) {
  const emailIndex = info.indexOf(BUSINESS_EMAIL);
  if (emailIndex < 0) {
    return <>{info}</>;
  }
  return (
    <>
      {info.slice(0, emailIndex)}
      <a
        href={`mailto:${BUSINESS_EMAIL}`}
        className="underline underline-offset-4 transition-colors hover:text-white"
      >
        {BUSINESS_EMAIL}
      </a>
      {info.slice(emailIndex + BUSINESS_EMAIL.length)}
    </>
  );
}

function BusinessInfoText() {
  const region = useRegion();
  if (region === "us") {
    return withEmailLink(US_BUSINESS_INFO_TEXT);
  }
  return (
    <>
      <span className="block">{t(BUSINESS_INFO_LINE_1)}</span>
      <span className="block">{withEmailLink(t(BUSINESS_INFO_LINE_2))}</span>
    </>
  );
}


/** 예시 카드 노출 순서를 섞는다(Fisher-Yates) — 첫 화면이 항상 같은 예시만 보여주지
 * 않도록. 서버·클라이언트가 다른 순서를 만들면 하이드레이션이 깨지므로 호출은 마운트
 * 이후(useEffect)에만 한다. */
// 전략연구소 이용 안내 — 법정 사업자 정보·약관 링크·투자 유의 문구. 시작 화면과 캔버스 레이아웃(예시 서랍)이
// 같은 컴포넌트를 쓴다.
export function StrategyLabLegalFooter({ className = "" }: { className?: string }) {
  const region = useRegion();
  const regionHref = useRegionHref();
  return (
    <footer
      aria-label={t("전략연구소 이용 안내")}
      className={`border-t border-white/[0.06] pt-4 text-center ${className}`}
    >
      {region !== "us" && (
        <Link
          href="/guide"
          className="mb-3 mr-4 inline-flex text-xs font-black text-gray-400 underline-offset-4 transition-colors hover:text-white hover:underline"
        >
          {t("백테스트 가이드")}
        </Link>
      )}
      {region !== "us" && (
        <Link
          href="/notes"
          className="mb-3 mr-4 inline-flex text-xs font-black text-gray-400 underline-offset-4 transition-colors hover:text-white hover:underline"
        >
          {t("연구노트")}
        </Link>
      )}
      {region !== "us" && (
        <Link href="/board" className="mb-3 mr-4 inline-flex text-xs font-black text-gray-400 underline-offset-4 transition-colors hover:text-white hover:underline">
          {t("자유게시판")}
        </Link>
      )}
      <Link
        href={regionHref("/?legal=terms")}
        className="mb-3 inline-flex text-xs font-black text-gray-400 underline-offset-4 transition-colors hover:text-white hover:underline"
      >
        {t("이용약관")}
      </Link>
      <Link
        href={regionHref("/?legal=privacy")}
        className="mb-3 ml-4 inline-flex text-xs font-black text-gray-400 underline-offset-4 transition-colors hover:text-white hover:underline"
      >
        {t("개인정보처리방침")}
      </Link>
      <div className="mx-auto mb-3 max-w-6xl text-xs font-bold leading-relaxed text-gray-500">
        <BusinessInfoText />
      </div>
      <p className="mx-auto max-w-5xl text-xs font-bold leading-relaxed text-gray-600">
        <span className="block">
          {t("널스탁에서 제공하는 투자 정보는 고객의 투자 판단을 위한 단순 참고용일 뿐입니다. 백테스트 입력 예시에 쓰인 수치는 단순 예시값이며, 투자 추천이나 미래 성과를 의미하지 않습니다.")}
        </span>
        <span className="mt-1 block">
          {t("모든 투자 판단과 그에 따른 책임은 이용자 본인에게 있습니다")}
        </span>
      </p>
      <p className="mt-3 text-xs font-bold text-gray-600">
        © 2026 nullStock. All rights reserved.
      </p>
    </footer>
  );
}
