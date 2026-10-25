import SwiftUI

@MainActor
final class HistoryViewModel: ObservableObject {
    @Published private(set) var items: [BacktestHistoryItem] = []
    @Published private(set) var loading = false
    @Published var errorMessage: String?

    func load() async {
        loading = true
        defer { loading = false }
        do {
            items = try await APIClient.shared.get("api/backtest/history")
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct HistoryView: View {
    @StateObject private var model = HistoryViewModel()

    var body: some View {
        NavigationStack {
            List(model.items) { item in
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.strategyName).font(.headline)
                    Text(item.date.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .overlay {
                if model.loading && model.items.isEmpty {
                    ProgressView()
                } else if let error = model.errorMessage {
                    Text(error).foregroundStyle(.secondary)
                } else if model.items.isEmpty {
                    Text("저장된 백테스트가 없습니다.").foregroundStyle(.secondary)
                }
            }
            .navigationTitle("기록")
            .refreshable { await model.load() }
            .task { await model.load() }
        }
    }
}
