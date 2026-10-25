import Foundation

enum AppConfig {
    /// Next.js 서버 주소. 앱은 FastAPI가 아니라 웹과 같은 `/api` 게이트웨이를 호출한다
    /// (인증·쿼터·프록시가 그 계층에 있다). 운영 쿠키는 Secure라서 https여야 한다.
    /// TODO: 운영 도메인 확인 후 교체. 디버그 빌드는 로컬 서버를 쓴다.
    #if DEBUG
    static let baseURL = URL(string: "http://localhost:3000")!
    #else
    static let baseURL = URL(string: "https://www.nullstock.im")!
    #endif

    /// 파스 요청의 `language` 필드("ko"|"en").
    static let uiLanguage = "ko"
}
