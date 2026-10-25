import Foundation

/// `POST /api/strategy/parse` 요청. 서버는 무상태라서 이전 턴 응답의 일부를
/// 그대로 되돌려 보내야 한다(에코 계약, backend/main.py::NLParseRequest 참조).
struct ParseRequest: Encodable {
    var prompt: String
    var language: String = AppConfig.uiLanguage
    var previousParsed: JSONValue?
    var previousCoachText: String?
    var pendingAsk: JSONValue?
    var pendingQuestion: String?
    var previousExplicitFields: [String]?
    var previousDeclinedFields: [String]?
    var previousFieldMetadata: JSONValue?
    var previousArtifacts: JSONValue?
    var previousFieldStates: JSONValue?

    enum CodingKeys: String, CodingKey {
        case prompt, language
        case previousParsed = "previous_parsed"
        case previousCoachText = "previous_coach_text"
        case pendingAsk = "pending_ask"
        case pendingQuestion = "pending_question"
        case previousExplicitFields = "previous_explicit_fields"
        case previousDeclinedFields = "previous_declined_fields"
        case previousFieldMetadata = "previous_field_metadata"
        case previousArtifacts = "previous_artifacts"
        case previousFieldStates = "previous_field_states"
    }
}

/// `NLParseResponse`의 앱이 쓰는 부분. 나머지는 불투명 JSON으로 보관해 에코한다.
struct ParseResponse: Decodable {
    let parsed: JSONValue
    let backtestRequest: JSONValue
    let symbolCount: Int
    let clarificationQuestion: String?
    let clarificationSuggestions: [String]?
    let pendingAsk: JSONValue?
    let explicitFields: [String]?
    let declinedFields: [String]?
    let fieldMetadata: JSONValue?
    let artifacts: JSONValue?
    let fieldStates: JSONValue?
    let notices: [String]?

    enum CodingKeys: String, CodingKey {
        case parsed, notices, artifacts
        case backtestRequest = "backtest_request"
        case symbolCount = "symbol_count"
        case clarificationQuestion = "clarification_question"
        case clarificationSuggestions = "clarification_suggestions"
        case pendingAsk = "pending_ask"
        case explicitFields = "explicit_fields"
        case declinedFields = "declined_fields"
        case fieldMetadata = "field_metadata"
        case fieldStates = "field_states"
    }
}

/// `GET /api/backtest/history` 항목(목록용, result 없음).
struct BacktestHistoryItem: Decodable, Identifiable {
    let id: String
    let timestamp: Double
    let strategyName: String
    let universe: JSONValue?
    let metrics: JSONValue?

    var date: Date { Date(timeIntervalSince1970: timestamp / 1000) }
}
