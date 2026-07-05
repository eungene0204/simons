import Link from "next/link";

type PrivacySection = {
  title: string;
  body?: string[];
  list?: string[];
  table?: Array<{
    label: string;
    content: string;
  }>;
};

const sections = [
  {
    title: "제1조 (목적)",
    body: [
      "이 개인정보처리방침은 널스페이스(이하 \"회사\")가 제공하는 nullStock 및 관련 서비스(이하 \"서비스\")에서 이용자의 개인정보를 어떻게 처리하고 보호하는지 알리기 위한 문서입니다.",
      "서비스는 투자 연구, 사용자 생성 전략, 과거 데이터 기반 백테스트, 가상계좌 및 모의투자 도구를 제공하며, 투자자문, 투자일임, 금융투자상품 매매·중개 또는 개인 맞춤형 금융 조언을 제공하지 않습니다.",
    ],
  },
  {
    title: "제2조 (처리하는 개인정보 항목)",
    table: [
      {
        label: "회원가입 및 로그인",
        content:
          "Supabase를 통한 Google 로그인 시 제공되는 이메일 주소, 이름 또는 닉네임, 프로필 이미지 URL, Google OAuth 제공자 식별자, 이메일 인증 여부",
      },
      {
        label: "서비스 이용 정보",
        content:
          "이용자가 입력한 전략명, 전략 설명, 조건식, 투자 유니버스, 백테스트 요청과 결과, 전략 저장 이력, 연구·최적화 실행 결과, 관심종목, 가상계좌명, 가상 주문·체결·보유 기록",
      },
      {
        label: "자동 생성 정보",
        content:
          "IP 주소, 접속 일시, 브라우저와 기기 정보, 쿠키, 세션 또는 JWT 토큰, 서비스 이용 로그, 오류 로그, 보안 이벤트 기록",
      },
      {
        label: "문의 및 운영 정보",
        content:
          "문의 내용, 답변 이력, 공지 수신 여부, 요금제와 사용량 정보, 유료서비스가 도입되는 경우 결제 상태와 환불 처리에 필요한 최소 정보",
      },
    ],
  },
  {
    title: "제3조 (개인정보의 처리 목적)",
    list: [
      "회원 식별, 로그인 유지, 계정 보호 및 부정 이용 방지",
      "사용자 생성 전략, 백테스트, 과거 성과 분석, 가상계좌, 관심종목 등 서비스 기능 제공",
      "전략 저장, 실행 이력 조회, 서비스 설정 동기화 및 오류 복구",
      "서비스 안정성 확보, 장애 분석, 보안 점검, 비정상 이용 탐지",
      "고객 문의 대응, 약관 또는 정책 변경 고지, 서비스 운영 공지",
      "요금제 한도 관리, 유료서비스가 도입되는 경우 결제·정산·환불 처리",
      "개인을 식별할 수 없는 통계 또는 집계 형태의 서비스 품질 개선",
    ],
  },
  {
    title: "제4조 (보유 및 이용 기간)",
    list: [
      "회원 정보는 회원 탈퇴 또는 이용계약 종료 시까지 보유합니다. 단, 관계 법령에 따라 보관해야 하는 정보는 해당 기간 동안 분리하여 보관할 수 있습니다.",
      "전략, 백테스트, 관심종목, 가상계좌 및 모의투자 기록은 이용자가 삭제하거나 계정이 종료될 때까지 보유합니다. 백업 또는 장애 복구 영역의 삭제 반영에는 합리적인 시간이 걸릴 수 있습니다.",
      "접속 로그, 보안 이벤트, 오류 로그는 서비스 안정성과 보안 목적 범위에서 최대 3개월간 보관할 수 있습니다.",
      "유료서비스가 도입되는 경우 계약 또는 청약철회 기록은 5년, 대금결제 및 재화 등의 공급 기록은 5년, 소비자 불만 또는 분쟁 처리 기록은 3년 등 관계 법령상 보존 기간을 따릅니다.",
    ],
  },
  {
    title: "제5조 (제3자 제공 및 처리 위탁)",
    list: [
      "회사는 이용자의 개인정보를 이 방침에서 정한 목적 범위를 넘어 제3자에게 제공하지 않습니다. 다만, 이용자가 사전에 동의한 경우 또는 법령에 따라 요구되는 경우에는 예외로 합니다.",
      "회사는 로그인, 인증, 데이터 저장, 인프라 운영, 고객 지원, 결제 처리 등 서비스 제공에 필요한 업무를 외부 서비스에 위탁할 수 있습니다.",
      "현재 서비스는 Supabase OAuth 인증과 회사의 JWT 세션을 사용할 수 있습니다. 실제 운영 환경의 수탁사, 이전 국가, 보유 기간, 이전 항목은 서비스 화면 또는 별도 고지에서 확정해 안내합니다.",
      "결제 기능이 도입되는 경우 카드번호 전체 등 결제수단의 핵심 정보는 회사가 직접 저장하지 않고 결제대행사가 처리하도록 설계합니다.",
    ],
  },
  {
    title: "제6조 (쿠키와 세션 정보)",
    list: [
      "회사는 로그인 상태 유지, 보안 확인, 화면 설정, 서비스 이용 통계 산출을 위해 쿠키, 로컬 저장소, 세션 저장소 또는 JWT 토큰을 사용할 수 있습니다.",
      "이용자는 브라우저 설정을 통해 쿠키 저장을 거부하거나 삭제할 수 있습니다. 다만, 쿠키 또는 세션 저장을 제한하면 로그인, 전략 작성, 저장, 가상계좌 등 일부 기능이 정상 동작하지 않을 수 있습니다.",
    ],
  },
  {
    title: "제7조 (이용자의 권리와 행사 방법)",
    list: [
      "이용자는 회사에 개인정보 열람, 정정, 삭제, 처리정지, 동의 철회를 요청할 수 있습니다.",
      "회원은 서비스 내 계정 기능 또는 고객센터를 통해 계정 삭제와 서비스 이용 해지를 요청할 수 있습니다.",
      "회사는 요청자의 본인 여부를 확인한 뒤 관계 법령에 따라 지체 없이 조치합니다. 법령상 보존 의무가 있거나 다른 이용자의 권리 보호가 필요한 경우 일부 요청이 제한될 수 있습니다.",
      "만 14세 미만 아동의 개인정보를 처리해야 하는 경우 회사는 법정대리인의 동의를 받습니다. 서비스는 만 14세 미만 아동을 주된 대상으로 하지 않습니다.",
    ],
  },
  {
    title: "제8조 (개인정보의 파기)",
    list: [
      "회사는 개인정보 보유 기간이 지나거나 처리 목적이 달성된 경우 해당 정보를 지체 없이 파기합니다.",
      "전자적 파일은 복구 또는 재생이 어렵도록 삭제하고, 출력물 등 종이 문서는 분쇄 또는 소각합니다.",
      "관계 법령에 따라 보존해야 하는 정보는 별도 저장 공간으로 분리하거나 접근 권한을 제한하여 보관합니다.",
    ],
  },
  {
    title: "제9조 (안전성 확보 조치)",
    list: [
      "회사는 개인정보 접근 권한을 업무상 필요한 사람으로 제한하고 접근 기록을 관리합니다.",
      "비밀번호는 복호화가 어렵도록 해시 처리하며, 인증 토큰과 주요 설정값은 안전하게 관리합니다.",
      "전송 구간 암호화, 보안 업데이트, 장애와 침해 사고 모니터링, 백업 및 복구 절차를 통해 개인정보를 보호합니다.",
      "투자 전략, 백테스트 결과, 가상계좌 기록은 이용자의 연구 데이터를 포함하므로 무단 접근과 외부 노출을 방지하기 위한 접근 통제를 적용합니다.",
    ],
  },
  {
    title: "제10조 (자동화된 의사결정 및 AI 기능)",
    list: [
      "서비스의 AI 요약, 설명, 전략 해석, 백테스트 분석 보조 기능은 이용자가 입력한 내용과 과거 데이터 기반 계산 결과를 설명하기 위한 도구입니다.",
      "회사는 AI 기능을 통해 이용자에게 투자 추천, 종목 추천, 포트폴리오 추천, 매수·매도 시점 제안 또는 개인 맞춤형 금융 조언을 제공하지 않습니다.",
      "이용자는 AI 또는 자동화된 처리 결과에 대해 설명을 요청하거나, 필요한 경우 고객센터를 통해 이의를 제기할 수 있습니다.",
    ],
  },
  {
    title: "제11조 (개인정보 보호책임자 및 문의)",
    table: [
      { label: "개인정보 보호책임자", content: "운영 전 확정" },
      { label: "문의 채널", content: "운영 전 고객센터 또는 이메일 주소로 확정" },
      { label: "권익침해 신고", content: "개인정보침해 신고센터, 개인정보분쟁조정위원회 등 관계 기관을 통해 상담 또는 분쟁 조정을 신청할 수 있습니다." },
    ],
  },
  {
    title: "제12조 (방침의 변경)",
    list: [
      "회사는 법령, 서비스 구조, 개인정보 처리 방식이 변경되는 경우 이 방침을 개정할 수 있습니다.",
      "중요한 변경이 있는 경우 적용일, 변경 내용, 변경 사유를 서비스 화면에 사전 공지합니다.",
      "이 방침은 2026년 7월 4일부터 시행합니다.",
    ],
  },
] satisfies PrivacySection[];

export function PrivacyPolicyPage() {
  return (
    <main className="min-h-screen bg-[#0f0f0f] text-white">
      <section className="border-b border-white/[0.08] px-6 py-12">
        <div className="mx-auto max-w-4xl">
          <Link
            href="/"
            className="text-sm font-bold text-gray-400 transition-colors hover:text-white"
          >
            nullStock으로 돌아가기
          </Link>
          <p className="mt-10 text-sm font-black uppercase tracking-widest text-gray-500">
            널스페이스
          </p>
          <h1 className="mt-3 text-4xl font-black tracking-normal text-white sm:text-5xl">
            nullStock 개인정보처리방침
          </h1>
          <p className="mt-5 max-w-2xl text-base font-bold leading-7 text-gray-400">
            널스페이스(이하 &quot;회사&quot;)는 정보주체의 자유와 권리 보호를 위해
            개인정보 보호법 및 관계 법령이 정한 바를 준수하여 개인정보를
            적법하게 처리하고 안전하게 관리하고 있습니다. 회사는 개인정보
            보호법 제30조에 따라 정보주체에게 개인정보의 처리와 보호에 관한
            절차 및 기준을 안내하고, 이와 관련한 고충을 신속하고 원활하게
            처리할 수 있도록 다음과 같이 개인정보처리방침을 수립·공개합니다.
          </p>
        </div>
      </section>

      <section className="px-6 py-10">
        <div className="mx-auto max-w-4xl">
          <div className="grid gap-4">
            {sections.map((section) => (
              <article
                key={section.title}
                className="border-b border-white/[0.08] py-6"
              >
                <h2 className="text-xl font-black tracking-normal text-white">
                  {section.title}
                </h2>
                {section.body?.map((paragraph) => (
                  <p
                    key={paragraph}
                    className="mt-3 text-base font-bold leading-7 text-gray-400"
                  >
                    {paragraph}
                  </p>
                ))}
                {section.table && (
                  <div className="mt-4 divide-y divide-white/[0.08] border border-white/[0.08]">
                    {section.table.map((row) => (
                      <div
                        key={row.label}
                        className="grid gap-2 px-4 py-4 sm:grid-cols-[180px_1fr]"
                      >
                        <p className="text-sm font-black text-gray-300">
                          {row.label}
                        </p>
                        <p className="text-sm font-bold leading-6 text-gray-400">
                          {row.content}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
                {section.list && (
                  <ol className="mt-4 list-decimal space-y-3 pl-5 text-base font-bold leading-7 text-gray-400">
                    {section.list.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ol>
                )}
              </article>
            ))}
          </div>

          <div className="mt-10 border border-white/[0.08] bg-white/[0.02] p-5 text-sm font-bold leading-6 text-gray-400">
            <p className="font-black text-white">운영 전 확정 항목</p>
            <p className="mt-2">
              개인정보 보호책임자, 고객센터, 실제 수탁사, 국외 이전 세부 사항,
              유료서비스 결제대행사 정보는 운영 환경과 법무 검토 결과에 맞춰
              최종 고지해야 합니다.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
