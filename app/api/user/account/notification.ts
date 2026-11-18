export async function notifyWithdrawal(userId: number, email: string): Promise<void> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) return;

  try {
    const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: `nullStock 회원 탈퇴\n탈퇴 계정: ${email}\n사용자 ID: ${userId}\n탈퇴 시각: ${new Date().toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })} (한국 시간)`,
      }),
      signal: AbortSignal.timeout(3000),
    });
    const result = await response.json();
    if (!response.ok || result?.ok !== true) console.warn("Withdrawal notification delivery failed");
  } catch {
    // Fetch errors may contain the bot token; never log their contents.
    console.warn("Withdrawal notification delivery failed");
  }
}
