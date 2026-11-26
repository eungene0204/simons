// 트랜잭션 메일 발송 (이메일 가입 인증번호 등).
//
// 설정: SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / SMTP_FROM(선택, 기본 SMTP_USER)
// - 프로덕션에서 SMTP 미설정이면 던진다(Fail Fast) — 인증 없는 가입이 조용히 열리면 안 된다.
// - 개발에서 미설정이면 콘솔에 내용을 출력하고 성공으로 처리한다(로컬 UX용).

import nodemailer from 'nodemailer'
import type { Transporter } from 'nodemailer'

let cachedTransporter: Transporter | null = null

export function isMailerConfigured(): boolean {
  return Boolean(
    process.env.SMTP_HOST && process.env.SMTP_USER && process.env.SMTP_PASS
  )
}

function getTransporter(): Transporter {
  if (cachedTransporter) return cachedTransporter
  const port = Number(process.env.SMTP_PORT || 587)
  cachedTransporter = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port,
    secure: port === 465,
    auth: {
      user: process.env.SMTP_USER,
      pass: process.env.SMTP_PASS,
    },
  })
  return cachedTransporter
}

async function sendMail(to: string, subject: string, text: string): Promise<void> {
  if (!isMailerConfigured()) {
    if (process.env.NODE_ENV === 'production') {
      throw new Error('SMTP is not configured (SMTP_HOST/SMTP_USER/SMTP_PASS)')
    }
    console.log(`[mailer:dev] to=${to} subject=${subject}\n${text}`)
    return
  }
  await getTransporter().sendMail({
    from: process.env.SMTP_FROM || process.env.SMTP_USER,
    to,
    subject,
    text,
  })
}

export async function sendVerificationEmail(to: string, code: string): Promise<void> {
  await sendMail(
    to,
    '[널스탁] 이메일 인증번호',
    [
      `널스탁 회원가입 인증번호는 ${code} 입니다.`,
      '',
      '인증번호는 10분간 유효합니다.',
      '본인이 요청하지 않았다면 이 메일을 무시해 주세요.',
    ].join('\n')
  )
}

// 이미 가입된 이메일로 인증번호가 요청되면 코드 대신 안내 메일을 보낸다.
// (요청자에게는 가입 여부를 드러내지 않기 위해 API 응답은 동일하게 유지한다)
export async function sendAlreadyRegisteredEmail(to: string): Promise<void> {
  await sendMail(
    to,
    '[널스탁] 가입 안내',
    [
      '이 이메일 주소는 이미 널스탁에 가입되어 있습니다.',
      '본인이 가입을 시도한 것이 아니라면 이 메일을 무시해 주세요.',
      '비밀번호를 잊으셨다면 고객센터로 문의해 주세요.',
    ].join('\n')
  )
}

// 저장 전략 월간 재검증 리포트(lib/server/strategyReport.ts) — 사용자가 설정에서 켠 경우에만 보낸다.
// 본문은 호출부가 사실 수치만으로 만든다(광고·추천 문구 없음).
export async function sendStrategyReportEmail(to: string, subject: string, text: string): Promise<void> {
  await sendMail(to, subject, text)
}

function formatKstDateTime(date: Date): string {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

// 자동결제(토스 빌링) 청구 실패 안내 — 계약 이행에 관한 거래 안내다(광고 아님).
// 카드 교체 화면이 아직 없어 결제 수단 변경은 고객센터 안내로 둔다.
export async function sendBillingFailedEmail(
  to: string,
  planName: string,
  failCount: number,
  maxFailCount: number,
  nextRetryAt: Date
): Promise<void> {
  await sendMail(
    to,
    '[널스탁] 자동결제가 처리되지 않았습니다',
    [
      `널스탁 ${planName} 플랜 정기결제가 처리되지 않았습니다. (${failCount}/${maxFailCount}회)`,
      '',
      `${formatKstDateTime(nextRetryAt)}에 같은 카드로 다시 결제를 시도합니다.`,
      `${maxFailCount}회 연속으로 처리되지 않으면 Free 플랜으로 전환됩니다.`,
      '',
      '카드 한도·유효기간·해외/온라인 결제 차단 여부를 확인해 주세요.',
      '결제 수단을 바꾸려면 고객센터로 문의해 주세요.',
    ].join('\n')
  )
}

// 청구 실패 한도 도달로 Free 전환된 뒤의 안내.
export async function sendBillingDowngradedEmail(to: string, planName: string, pricingUrl: string): Promise<void> {
  await sendMail(
    to,
    '[널스탁] 결제가 처리되지 않아 Free 플랜으로 전환되었습니다',
    [
      `${planName} 플랜 정기결제가 연속으로 처리되지 않아 Free 플랜으로 전환되었습니다.`,
      '저장한 전략과 백테스트 기록은 그대로 남아 있으며, Free 플랜 한도 안에서 계속 이용할 수 있습니다.',
      '',
      `다시 구독하려면 요금제 페이지에서 결제해 주세요: ${pricingUrl}`,
    ].join('\n')
  )
}
