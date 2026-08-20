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
