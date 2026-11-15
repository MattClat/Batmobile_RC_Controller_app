//  ContentView.swift
//  Batmobile — iPadOS controller with diagnostics.
//
//  Protocol: ASCII command string over UDP to 192.168.201.1:1051, 10x/sec.
//
//  SETUP IN SWIFT PLAYGROUNDS
//    1. New app project. Replace ContentView.swift with this file.
//    2. Sidebar > App Settings > Capabilities > + > Local Network.
//    3. Join wifi  E6F4-BATMOBILE  password  BATMOBILE1
//    4. Run. Say yes to the Local Network prompt.
//
//  READING THE DIAGNOSTICS PANEL
//    my ip    must be 192.168.201.x . Anything else (169.254.x = no DHCP,
//             192.168.1.x = your home wifi) means the iPad is not on the
//             car's network and nothing can possibly work.
//    state    must reach "ready". Stuck on preparing/waiting usually means
//             the Local Network permission was denied.
//    sent     must climb ~10 per second. Frozen = the timer died.
//    error    anything here is the real problem; it was previously hidden.
//    replies  the car answering back. Nice to have, not required.

import SwiftUI
import Network
import Darwin

// MARK: - Protocol

/// Matches Java's Integer.toHexString: lowercase, no leading zero.
func hx(_ v: Int) -> String {
    String(v & 0xFF, radix: 16)
}

func throttleToken(_ axis: Double) -> String {
    if abs(axis) < deadzone { return "41_80" }
    let mag = max(1, min(100, Int((abs(axis) * 100).rounded())))
    return "41_" + hx(axis > 0 ? mag + 128 : mag)
}

func steerToken(_ axis: Double) -> String {
    if abs(axis) < deadzone { return "31_80" }
    let mag = max(1, min(100, Int((abs(axis) * 100).rounded())))
    return "31_" + hx(axis > 0 ? mag + 128 : mag)
}

let deadzone = 0.10
let carHost = "192.168.201.1"
let carPort: UInt16 = 1051
let trimMarker = "50_F0"

/// The iPad's own IPv4 address on wifi. The single most useful diagnostic:
/// if this isn't 192.168.201.x, the iPad is on the wrong network.
func wifiIPAddress() -> String {
    var result = "none"
    var ifaddr: UnsafeMutablePointer<ifaddrs>?
    guard getifaddrs(&ifaddr) == 0, let first = ifaddr else { return result }
    var ptr: UnsafeMutablePointer<ifaddrs>? = first
    while let cur = ptr {
        let addr = cur.pointee.ifa_addr
        if let addr = addr, addr.pointee.sa_family == UInt8(AF_INET) {
            let name = String(cString: cur.pointee.ifa_name)
            if name == "en0" {
                var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                if getnameinfo(addr, socklen_t(addr.pointee.sa_len),
                               &host, socklen_t(host.count),
                               nil, 0, NI_NUMERICHOST) == 0 {
                    result = String(cString: host)
                }
            }
        }
        ptr = cur.pointee.ifa_next
    }
    freeifaddrs(ifaddr)
    return result
}

// MARK: - Link

@MainActor
final class BatmobileLink: ObservableObject {

    @Published var lastPacket = "—"
    @Published var connState = "not started"
    @Published var sentCount = 0
    @Published var replyCount = 0
    @Published var lastReply = "—"
    @Published var lastError = "none"
    @Published var myIP = "—"

    @Published var lights = false
    @Published var smoke = false
    @Published var armor = false

    var throttle = 0.0
    var steering = 0.0

    private var connection: NWConnection?
    private var timer: Timer?
    private var heartbeat = 0
    private var oneshots: [String] = []

    func start() {
        myIP = wifiIPAddress()

        let conn = NWConnection(
            host: NWEndpoint.Host(carHost),
            port: NWEndpoint.Port(rawValue: carPort)!,
            using: .udp
        )
        connection = conn

        conn.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                switch state {
                case .setup:       self?.connState = "setup"
                case .preparing:   self?.connState = "preparing"
                case .ready:       self?.connState = "ready"
                case .cancelled:   self?.connState = "cancelled"
                case .waiting(let e):
                    self?.connState = "waiting"
                    self?.lastError = "\(e)"
                case .failed(let e):
                    self?.connState = "FAILED"
                    self?.lastError = "\(e)"
                @unknown default:  self?.connState = "unknown"
                }
            }
        }

        conn.start(queue: .global(qos: .userInitiated))
        listen()

        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick() }
        }
        UIApplication.shared.isIdleTimerDisabled = true
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        for _ in 0..<5 { rawSend("41_80_31_80_50_F0_00_00_00") }
        connection?.cancel()
        connection = nil
        UIApplication.shared.isIdleTimerDisabled = false
    }

    func queue(_ token: String) {
        oneshots.append(token)
    }

    /// Fire a short burst of full-throttle-forward, then neutral. If the car
    /// twitches, the whole pipe works and the problem is in the sticks.
    func selfTest() {
        lastError = "none"
        for _ in 0..<8 { rawSend("41_e4_31_80_50_F0_00_00_00") }
        for _ in 0..<4 { rawSend("41_80_31_80_50_F0_00_00_00") }
    }

    private func tick() {
        let packet = build(throttleToken(throttle), steerToken(steering))
        rawSend(packet)
        lastPacket = packet
    }

    private func build(_ thr: String, _ steer: String) -> String {
        var pairs = [thr, steer]
        if !oneshots.isEmpty && pairs.count < 3 {
            pairs.append(oneshots.removeFirst())
        }
        pairs.append(trimMarker)
        while pairs.count < 4 { pairs.append("00_00") }
        heartbeat = (heartbeat + 1) % 10
        return pairs.joined(separator: "_") + "_" + (heartbeat == 0 ? "01" : "00")
    }

    private func rawSend(_ s: String) {
        guard let conn = connection else {
            lastError = "no connection object"
            return
        }
        guard let data = s.data(using: .ascii) else {
            lastError = "packet not ascii-encodable"
            return
        }
        conn.send(content: data, completion: .contentProcessed { [weak self] error in
            Task { @MainActor in
                if let e = error {
                    self?.lastError = "send: \(e)"
                } else {
                    self?.sentCount += 1
                }
            }
        })
    }

    private func listen() {
        connection?.receiveMessage { [weak self] data, _, _, error in
            Task { @MainActor in
                if let d = data, !d.isEmpty {
                    self?.replyCount += 1
                    self?.lastReply = d.prefix(14)
                        .map { String(format: "%02x", $0) }
                        .joined(separator: " ")
                }
                if let e = error { self?.lastError = "recv: \(e)" }
                self?.listen()
            }
        }
    }
}

// MARK: - Thumbstick

struct Thumbstick: View {
    let label: String
    let horizontal: Bool
    let onChange: (Double) -> Void

    @State private var offset: CGSize = .zero
    @State private var active = false

    private let radius: CGFloat = 95

    var body: some View {
        let value: Double = horizontal
            ? Double(offset.width / radius)
            : Double(-offset.height / radius)

        VStack(spacing: 8) {
            ZStack {
                Circle()
                    .stroke(Color.white.opacity(0.15), lineWidth: 3)
                    .frame(width: radius * 2, height: radius * 2)
                Rectangle()
                    .fill(Color.white.opacity(0.08))
                    .frame(width: horizontal ? radius * 2 : 2,
                           height: horizontal ? 2 : radius * 2)
                Circle()
                    .fill(active ? Color.red.opacity(0.85) : Color.white.opacity(0.22))
                    .frame(width: radius * 0.76, height: radius * 0.76)
                    .offset(offset)
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { g in
                        active = true
                        var dx = horizontal ? g.translation.width : 0
                        var dy = horizontal ? 0 : g.translation.height
                        let d = sqrt(dx * dx + dy * dy)
                        if d > radius {
                            dx *= radius / d
                            dy *= radius / d
                        }
                        offset = CGSize(width: dx, height: dy)
                        onChange(horizontal ? Double(dx / radius) : Double(-dy / radius))
                    }
                    .onEnded { _ in
                        active = false
                        offset = .zero
                        onChange(0)
                    }
            )

            Text("\(label)  \(String(format: "%+.2f", abs(value) < deadzone ? 0 : value))")
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(.white.opacity(0.55))
        }
    }
}

// MARK: - Button

struct ActionButton: View {
    let title: String
    var lit: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 12, design: .monospaced))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 10)
                .background(lit ? Color.red.opacity(0.8) : Color.white.opacity(0.12))
                .foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Diagnostics

struct DiagRow: View {
    let key: String
    let value: String
    var warn: Bool = false

    var body: some View {
        HStack(spacing: 8) {
            Text(key)
                .foregroundStyle(.white.opacity(0.45))
                .frame(width: 78, alignment: .leading)
            Text(value)
                .foregroundStyle(warn ? .red : .white.opacity(0.85))
                .lineLimit(2)
            Spacer()
        }
        .font(.system(size: 12, design: .monospaced))
    }
}

// MARK: - Main view

struct ContentView: View {
    @StateObject private var link = BatmobileLink()

    private var ipLooksWrong: Bool {
        !link.myIP.hasPrefix("192.168.201.")
    }

    var body: some View {
        ZStack {
            Color(red: 0.06, green: 0.06, blue: 0.08).ignoresSafeArea()

            VStack(spacing: 0) {
                HStack(spacing: 8) {
                    ActionButton(title: "LIGHTS", lit: link.lights) {
                        link.lights.toggle()
                        link.queue(link.lights ? "A1_10" : "A1_01")
                    }
                    ActionButton(title: "SMOKE", lit: link.smoke) {
                        link.smoke.toggle()
                        link.queue(link.smoke ? "91_10" : "91_01")
                    }
                    ActionButton(title: "GUN") { link.queue("21_E4") }
                    ActionButton(title: "ROTATE") { link.queue("11_E4") }
                    ActionButton(title: "ARMOR", lit: link.armor) {
                        link.armor.toggle()
                        link.queue("21_64")
                    }
                    ActionButton(title: "SELF TEST") { link.selfTest() }
                }
                .padding(.horizontal, 12)
                .padding(.top, 8)

                Spacer()

                HStack {
                    Thumbstick(label: "STEER", horizontal: true) { link.steering = $0 }
                    Spacer()
                    Thumbstick(label: "THROTTLE", horizontal: false) { link.throttle = $0 }
                }
                .padding(.horizontal, 50)

                Spacer()

                VStack(alignment: .leading, spacing: 3) {
                    DiagRow(key: "my ip",
                            value: link.myIP + (ipLooksWrong ? "   << WRONG NETWORK" : "   ok"),
                            warn: ipLooksWrong)
                    DiagRow(key: "target", value: "\(carHost):\(carPort)")
                    DiagRow(key: "state", value: link.connState,
                            warn: link.connState != "ready")
                    DiagRow(key: "sent", value: "\(link.sentCount) packets")
                    DiagRow(key: "packet", value: link.lastPacket)
                    DiagRow(key: "replies", value: "\(link.replyCount)   \(link.lastReply)")
                    DiagRow(key: "error", value: link.lastError,
                            warn: link.lastError != "none")
                }
                .padding(10)
                .background(Color.white.opacity(0.05))
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .padding(.horizontal, 12)
                .padding(.bottom, 10)
            }
        }
        .statusBarHidden()
        .onAppear { link.start() }
        .onDisappear { link.stop() }
    }
}
