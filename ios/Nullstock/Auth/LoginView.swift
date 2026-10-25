import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("이메일", text: $email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("비밀번호", text: $password)
                        .textContentType(.password)
                }
                if let message = auth.errorMessage {
                    Text(message).foregroundStyle(.red).font(.footnote)
                }
                Button {
                    busy = true
                    Task {
                        await auth.login(email: email, password: password)
                        busy = false
                    }
                } label: {
                    if busy { ProgressView() } else { Text("로그인") }
                }
                .disabled(busy || email.isEmpty || password.isEmpty)
            }
            .navigationTitle("널스탁")
        }
    }
}
