import { prisma } from "@/lib/prisma";

type SignupMethod = "email" | "google";

// Await a bounded request so serverless runtimes do not discard the notification.
export async function notifySignup(method: SignupMethod, userId: number, email: string): Promise<void> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) return;

  try {
    const signupNumber = await prisma.user.count({ where: { id: { lte: userId } } });
    const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: `nullStock 신규 가입\n가입 계정: ${email}\n가입 순서: ${signupNumber}번째 가입자\n가입자 ID: ${userId}\n가입 방식: ${method === "google" ? "Google" : "이메일"}\n가입 시각: ${new Date().toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })} (한국 시간)`,
      }),
      signal: AbortSignal.timeout(3000),
    });
    const result = await response.json();
    if (!response.ok || result?.ok !== true) {
      console.warn("Signup notification delivery failed");
    }
  } catch {
    // Never log fetch errors: they can contain the bot token in the URL.
    console.warn("Signup notification delivery failed");
  }
}
