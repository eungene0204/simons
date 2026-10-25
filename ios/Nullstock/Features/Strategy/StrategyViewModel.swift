import Foundation

struct ChatMessage: Identifiable {
    enum Role { case user, assistant }
    let id = UUID()
    let role: Role
    let text: String
    var chips: [String] = []
}

/// 전략 대화 한 세션. 서버가 무상태라 응답의 에코 대상 필드를 여기 보관했다가
/// 다음 요청에 되돌려 보낸다(웹 프론트와 같은 계약).
@MainActor
final class StrategyViewModel: ObservableObject {
    @Published private(set) var messages: [ChatMessage] = []
    @Published private(set) var busy = false
    @Published var errorMessage: String?
    /// 최신 해석 결과(디버그·요약 표시용). 백테스트 실행 화면의 입력이 된다.
    @Published private(set) var latest: ParseResponse?

    private let api = APIClient.shared
    private var lastCoachText: String?

    func send(_ prompt: String) async {
        let text = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !busy else { return }
        messages.append(ChatMessage(role: .user, text: text))
        busy = true
        errorMessage = nil
        defer { busy = false }

        var request = ParseRequest(prompt: text)
        if let prev = latest {
            request.previousParsed = prev.parsed
            request.previousCoachText = lastCoachText
            request.pendingAsk = prev.pendingAsk
            request.pendingQuestion = prev.pendingAsk?["question"]?.stringValue
            request.previousExplicitFields = prev.explicitFields
            request.previousDeclinedFields = prev.declinedFields
            request.previousFieldMetadata = prev.fieldMetadata
            request.previousArtifacts = prev.artifacts
            request.previousFieldStates = prev.fieldStates
        }

        do {
            // 해석은 LLM 호출이라 오래 걸릴 수 있다(웹 프록시 예산 240초).
            let res: ParseResponse = try await api.post(
                "api/strategy/parse", body: request, timeout: 240)
            latest = res
            let reply = res.clarificationQuestion ?? "전략을 해석했어요. (종목 \(res.symbolCount)개)"
            lastCoachText = reply
            messages.append(ChatMessage(
                role: .assistant, text: reply, chips: res.clarificationSuggestions ?? []))
            for notice in res.notices ?? [] {
                messages.append(ChatMessage(role: .assistant, text: notice))
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func reset() {
        messages = []
        latest = nil
        lastCoachText = nil
        errorMessage = nil
    }
}
