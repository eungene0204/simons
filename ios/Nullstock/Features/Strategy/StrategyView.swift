import SwiftUI

struct StrategyView: View {
    @StateObject private var model = StrategyViewModel()
    @State private var input = ""

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        if model.messages.isEmpty {
                            Text("어떤 전략을 연구해 볼까요? 예) RSI가 30 아래로 내려가면 사고 70 위로 오르면 파는 전략, 코스피200, 최근 10년")
                                .foregroundStyle(.secondary)
                        }
                        ForEach(model.messages) { message in
                            bubble(message)
                        }
                        if model.busy { ProgressView().padding(.leading) }
                        if let error = model.errorMessage {
                            Text(error).foregroundStyle(.red).font(.footnote)
                        }
                    }
                    .padding()
                }
                Divider()
                HStack {
                    TextField("전략을 입력하세요", text: $input, axis: .vertical)
                        .lineLimit(1...4)
                        .textFieldStyle(.roundedBorder)
                    Button("전송") { submit(input) }
                        .disabled(model.busy || input.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                .padding()
            }
            .navigationTitle("전략 연구")
            .toolbar {
                Button("새 대화") { model.reset() }
            }
        }
    }

    private func submit(_ text: String) {
        input = ""
        Task { await model.send(text) }
    }

    @ViewBuilder
    private func bubble(_ message: ChatMessage) -> some View {
        VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 8) {
            Text(message.text)
                .padding(10)
                .background(message.role == .user ? Color.accentColor.opacity(0.2) : Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            if !message.chips.isEmpty {
                // 칩은 누르면 그 문구를 그대로 답으로 보낸다(서버가 pending_ask와 정확히 일치를 본다).
                FlowChips(chips: message.chips) { submit($0) }
            }
        }
        .frame(maxWidth: .infinity, alignment: message.role == .user ? .trailing : .leading)
    }
}

private struct FlowChips: View {
    let chips: [String]
    let onTap: (String) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack {
                ForEach(chips, id: \.self) { chip in
                    Button(chip) { onTap(chip) }
                        .buttonStyle(.bordered)
                }
            }
        }
    }
}
