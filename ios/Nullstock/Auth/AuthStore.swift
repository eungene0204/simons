import Foundation

@MainActor
final class AuthStore: ObservableObject {
    enum State: Equatable {
        case unknown
        case signedOut
        case signedIn(User)
    }

    @Published private(set) var state: State = .unknown
    @Published var errorMessage: String?

    private let api = APIClient.shared

    /// 앱 시작 시 저장된 쿠키로 세션을 복원한다. 웹과 같이 비로그인은 `{user:null}` 200이다.
    func restoreSession() async {
        do {
            let env: UserEnvelope = try await api.get("api/user")
            state = env.user.map { .signedIn($0) } ?? .signedOut
        } catch {
            state = .signedOut
        }
    }

    /// 이메일 로그인은 서버 킬 스위치(EMAIL_SIGNUP_ENABLED)가 꺼지면 404가 된다.
    /// 운영 로그인은 Google(Supabase 토큰)·Sign in with Apple 연동이 필요하다(미구현).
    func login(email: String, password: String) async {
        errorMessage = nil
        do {
            let res: LoginResponse = try await api.post(
                "api/login", body: LoginRequest(email: email, password: password))
            state = .signedIn(res.user)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func logout() async {
        struct Ack: Decodable {}
        struct Empty: Encodable {}
        let _: Ack? = try? await api.post("api/logout", body: Empty())
        HTTPCookieStorage.shared.cookies?.forEach(HTTPCookieStorage.shared.deleteCookie)
        state = .signedOut
    }
}
