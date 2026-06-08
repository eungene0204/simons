import GoogleLoginButton from "./GoogleLoginButton";

export default function CTASection() {
  return (
    <section
      aria-labelledby="landing-cta-title"
      className="rounded-[32px] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.04),rgba(255,255,255,0.02))] px-5 py-8 sm:px-8 sm:py-10 lg:px-12"
    >
      <div className="mx-auto flex max-w-3xl flex-col items-start gap-6 text-left">
        <p className="text-xs font-bold uppercase tracking-[0.24em] text-gray-500">
          Start Now
        </p>
        <div>
          <h2
            id="landing-cta-title"
            className="text-3xl font-black text-white sm:text-4xl"
          >
            지금 바로 시작하세요
          </h2>
          <p className="mt-4 max-w-2xl text-base leading-7 text-gray-300">
            복잡한 투자 전략 개발 과정을 AI와 함께 단순하게 만드세요.
          </p>
        </div>
        <GoogleLoginButton className="sm:min-w-[220px]" />
      </div>
    </section>
  );
}
