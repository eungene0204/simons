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
      "널스페이스(이하 \"회사\")는 정보주체의 자유와 권리 보호를 위해 개인정보 보호법 및 관계 법령이 정한 바를 준수하여 개인정보를 적법하게 처리하고 안전하게 관리하고 있습니다. 회사는 개인정보 보호법 제30조에 따라 정보주체에게 개인정보의 처리와 보호에 관한 절차 및 기준을 안내하고, 이와 관련한 고충을 신속하고 원활하게 처리할 수 있도록 다음과 같이 개인정보처리방침을 수립·공개합니다.",
    ],
  },
  {
    title: "제2조 (처리하는 개인정보 항목)",
    body: [
      "회사는 회원가입과 로그인을 Supabase를 통한 Google 소셜 로그인 방식으로만 제공하며, 이용자의 비밀번호를 직접 수집하거나 저장하지 않습니다.",
    ],
    table: [
      {
        label: "회원가입 및 로그인",
        content:
          "Supabase를 통한 Google 로그인 시 제공되는 이메일 주소, 이름 또는 닉네임, 프로필 이미지 URL, Google OAuth 제공자 식별자, 이메일 인증 여부",
      },
      {
        label: "서비스 이용 정보",
        content:
          "이용자가 입력한 전략명, 전략 설명, 조건식, 투자 유니버스, 백테스트 요청과 결과, 전략 저장 및 검증 결과 이력, 관심종목, 가상계좌명, 가상 주문·체결·보유 기록, AI 분석 기능에 입력한 대화 메시지와 질문 내용",
      },
      {
        label: "자동 생성 정보",
        content:
          "최근 로그인 시각, 서비스 운영 과정에서 생성되는 오류 로그 및 보안 이벤트 기록",
      },
      {
        label: "플랜 및 사용량 정보",
        content:
          "이용 중인 요금제, 월 백테스트 이용 횟수, 유료서비스가 도입되는 경우 결제 상태와 환불 처리에 필요한 최소 정보",
      },
    ],
  },
  {
    title: "제3조 (개인정보의 처리 목적)",
    list: [
      "회원 식별, 로그인 유지, 계정 보호 및 부정 이용 방지",
      "사용자 생성 전략, 백테스트, 과거 성과 분석, 가상계좌, 관심종목 등 서비스 기능 제공",
      "AI 분석 기능의 응답 생성 등 이용자가 요청한 계산·분석 처리",
      "전략 저장, 실행 이력 조회, 서비스 설정 동기화 및 오류 복구",
      "서비스 안정성 확보, 장애 분석, 보안 점검, 비정상 이용 탐지",
      "고객 문의 대응, 약관 또는 정책 변경 고지, 서비스 운영 공지",
      "플랜별 이용 한도 관리, 유료서비스가 도입되는 경우 결제·정산·환불 처리",
    ],
  },
  {
    title: "제4조 (보유 및 이용 기간)",
    list: [
      "회원 정보는 회원 탈퇴 또는 이용계약 종료 시까지 보유합니다. 단, 관계 법령에 따라 보관해야 하는 정보는 해당 기간 동안 분리하여 보관합니다.",
      "전략, 백테스트, 검증 결과, 관심종목, 가상계좌 및 모의투자 기록은 이용자가 삭제하거나 계정이 종료될 때까지 보유합니다. 백업 또는 장애 복구 영역의 삭제 반영에는 합리적인 시간이 걸릴 수 있습니다.",
      "서비스 운영 과정에서 생성되는 오류 로그와 보안 이벤트 기록은 서비스 안정성과 보안 목적 범위에서 제한된 기간 동안 보관한 뒤 파기합니다.",
      "유료서비스가 도입되는 경우 「전자상거래 등에서의 소비자보호에 관한 법률」에 따라 계약 또는 청약철회 기록 5년, 대금결제 및 재화 등의 공급 기록 5년, 소비자 불만 또는 분쟁 처리 기록 3년의 보존 기간을 따릅니다.",
    ],
  },
  {
    title: "제5조 (제3자 제공)",
    list: [
      "회사는 이용자의 개인정보를 이 방침에서 정한 목적 범위를 넘어 제3자에게 제공하지 않습니다.",
      "이용자가 사전에 동의한 경우 또는 법령에 따라 요구되는 경우에는 예외로 하며, 이 경우 제공받는 자, 제공 항목, 이용 목적, 보유 기간을 고지합니다.",
    ],
  },
  {
    title: "제6조 (처리 위탁 및 국외 이전)",
    body: [
      "회사는 서비스 제공에 필요한 업무를 다음과 같이 외부 서비스에 위탁하며, 이 과정에서 개인정보가 국외에서 처리(보관 또는 처리 위탁)될 수 있습니다. 이전 방법은 서비스 이용 시 정보통신망을 통한 전송이며, 보유 기간은 회원 탈퇴 또는 위탁 계약 종료 시까지입니다.",
    ],
    table: [
      {
        label: "회원 인증",
        content:
          "Supabase Inc.(미국 등) — Supabase OAuth 인증과 회사의 JWT 세션 처리를 위한 이메일 주소, 이름, 프로필 정보, OAuth 식별자",
      },
      {
        label: "서버 및 데이터 저장",
        content:
          "클라우드 호스팅 사업자 — 서비스 운영과 데이터 저장을 위한 서비스 이용 정보 전반",
      },
      {
        label: "AI 연산 처리",
        content:
          "AI 연산 인프라 사업자(미국 등) — AI 분석 기능 응답 생성을 위해 이용자가 입력한 대화 메시지와 전략 텍스트를 처리(응답 생성 즉시 처리 목적으로만 사용)",
      },
      {
        label: "결제 처리(도입 시)",
        content:
          "결제대행사 — 카드번호 전체 등 결제수단의 핵심 정보는 회사가 직접 저장하지 않고 결제대행사가 처리하도록 설계합니다.",
      },
    ],
    list: [
      "실제 운영 환경의 수탁사 명칭, 이전 국가, 이전 항목, 연락처는 서비스 화면 또는 별도 고지에서 확정해 안내합니다.",
      "이용자는 개인정보의 국외 이전을 원하지 않는 경우 회원가입을 하지 않거나 고객센터를 통해 이전 중단을 요청할 수 있습니다. 다만, 국외 이전은 서비스 제공에 필수적인 처리이므로 이전을 거부하는 경우 서비스 이용이 제한될 수 있습니다.",
    ],
  },
  {
    title: "제7조 (쿠키와 세션 정보)",
    list: [
      "회사는 로그인 상태 유지, 보안 확인, 화면 설정을 위해 쿠키와 브라우저 저장소를 사용할 수 있습니다. 로그인 상태 유지에 사용하는 세션 토큰(JWT)은 이용자 브라우저의 쿠키에 저장되며, 회사는 이를 서버에 별도로 보관하지 않습니다.",
      "이용자는 브라우저 설정을 통해 쿠키 저장을 거부하거나 삭제할 수 있습니다. 다만, 쿠키 또는 세션 저장을 제한하면 로그인, 전략 작성, 저장, 가상계좌 등 일부 기능이 정상 동작하지 않을 수 있습니다.",
    ],
  },
  {
    title: "제8조 (이용자의 권리와 행사 방법)",
    list: [
      "이용자는 회사에 개인정보 열람, 정정, 삭제, 처리정지, 동의 철회를 요청할 수 있습니다.",
      "회원은 고객센터를 통해 계정 삭제와 서비스 이용 해지를 요청할 수 있습니다.",
      "회사는 요청자의 본인 여부를 확인한 뒤 관계 법령에 따라 지체 없이 조치합니다. 법령상 보존 의무가 있거나 다른 이용자의 권리 보호가 필요한 경우 일부 요청이 제한될 수 있습니다.",
      "회사는 만 14세 미만 아동의 회원가입을 허용하지 않으며, 만 14세 미만 아동의 개인정보를 수집하지 않습니다. 만 14세 미만 아동의 정보가 수집된 사실이 확인되는 경우 지체 없이 파기합니다.",
    ],
  },
  {
    title: "제9조 (개인정보의 파기)",
    list: [
      "회사는 개인정보 보유 기간이 지나거나 처리 목적이 달성된 경우 해당 정보를 지체 없이 파기합니다.",
      "전자적 파일은 복구 또는 재생이 어렵도록 삭제하고, 출력물 등 종이 문서는 분쇄 또는 소각합니다.",
      "관계 법령에 따라 보존해야 하는 정보는 그 보존 근거와 항목을 제4조에 따라 고지하고, 별도 저장 공간으로 분리하거나 접근 권한을 제한하여 보관합니다.",
    ],
  },
  {
    title: "제10조 (안전성 확보 조치)",
    list: [
      "회사는 개인정보 접근 권한을 업무상 필요한 사람으로 제한하고 접근 기록을 관리합니다.",
      "회사는 이용자의 비밀번호를 직접 보관하지 않으며, 인증은 Supabase Google 로그인과 회사가 발급한 세션 토큰으로 처리하고 인증 토큰과 주요 설정값을 안전하게 관리합니다.",
      "전송 구간 암호화, 보안 업데이트, 장애와 침해 사고 모니터링, 백업 및 복구 절차를 통해 개인정보를 보호합니다.",
      "투자 전략, 백테스트 결과, 가상계좌 기록은 이용자의 연구 데이터를 포함하므로 무단 접근과 외부 노출을 방지하기 위한 접근 통제를 적용합니다.",
    ],
  },
  {
    title: "제11조 (자동화된 의사결정 및 AI 기능)",
    list: [
      "서비스의 AI 요약, 설명, 전략 해석, 백테스트 분석 보조 기능은 이용자가 입력한 내용과 과거 데이터 기반 계산 결과를 설명하기 위한 도구입니다.",
      "이용자가 AI 분석 기능에 입력한 대화 내용과 전략 텍스트는 응답 생성을 위해 처리되며, 회사는 이를 이용자의 별도 동의 없이 AI 모델 학습에 사용하지 않습니다.",
      "회사는 AI 기능을 통해 이용자에게 투자 추천, 종목 추천, 포트폴리오 추천, 매수·매도 시점 제안 또는 개인 맞춤형 금융 조언을 제공하지 않습니다.",
      "이용자는 AI 또는 자동화된 처리 결과에 대해 설명을 요청하거나, 필요한 경우 고객센터를 통해 이의를 제기할 수 있습니다.",
    ],
  },
  {
    title: "제12조 (방침의 변경)",
    list: [
      "회사는 법령, 서비스 구조, 개인정보 처리 방식이 변경되는 경우 이 방침을 개정할 수 있습니다.",
      "중요한 변경이 있는 경우 적용일, 변경 내용, 변경 사유를 서비스 화면에 사전 공지합니다.",
    ],
  },
] satisfies PrivacySection[];

export function PrivacyPolicyPage() {
  const businessInfoItems = [
    { label: "상호", value: process.env.COMPANY_NAME },
    { label: "대표자", value: process.env.BUSINESS_REPRESENTATIVE_NAME },
    { label: "주소", value: process.env.BUSINESS_ADDRESS },
    { label: "사업자등록번호", value: process.env.BUSINESS_REGISTRATION_NUMBER },
    { label: "이메일", value: process.env.BUSINESS_EMAIL },
  ];

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
            개인정보처리방침
          </h1>
          <p className="mt-5 max-w-2xl text-base font-bold leading-7 text-gray-400">
            이 개인정보처리방침은 널스페이스가 제공하는 nullStock 및 관련
            서비스에서 이용자의 개인정보를 어떻게 처리하고 보호하는지
            안내합니다. 서비스는 소프트웨어 서비스(SaaS) 방식으로 제공되는
            투자 연구 및 시뮬레이션 도구이며, 투자자문, 투자일임,
            금융투자상품 매매·중개 또는 개인 맞춤형 금융 조언을 제공하지
            않습니다.
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
            <p className="font-black text-white">사업자 정보</p>
            <dl className="mt-4 grid gap-3 sm:grid-cols-[140px_1fr]">
              {businessInfoItems.map((item) => (
                <div key={item.label} className="contents">
                  <dt className="text-gray-500">{item.label}</dt>
                  <dd className="text-gray-300">{item.value || "미정"}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </section>
    </main>
  );
}
