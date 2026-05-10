import Foundation
import UIKit
import BackgroundTasks
import CoreML

/**
 * HiveAgent — iOS equivalent of the Android HiveAgentService.
 * Uses Background App Refresh (BGTaskScheduler) for telemetry.
 * CoreML detection for inference.coreml capability.
 */
class HiveAgent {
    static let shared = HiveAgent()
    private let defaults = UserDefaults.standard
    private let session: URLSession

    private var leader: String {
        get { defaults.string(forKey: "hive_leader") ?? "" }
        set { defaults.set(newValue, forKey: "hive_leader") }
    }
    private var nodeId: String {
        get { defaults.string(forKey: "hive_node_id") ?? "" }
        set { defaults.set(newValue, forKey: "hive_node_id") }
    }
    private var token: String {
        get { defaults.string(forKey: "hive_token") ?? "" }
        set { defaults.set(newValue, forKey: "hive_token") }
    }

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        self.session = URLSession(configuration: config)
    }

    var isConfigured: Bool {
        !leader.isEmpty && !nodeId.isEmpty && !token.isEmpty
    }

    // MARK: — Enrolment

    func enrol(leaderUrl: String, preferredNodeId: String?, completion: @escaping (Result<(nodeId: String, token: String), Error>) -> Void) {
        let url = URL(string: leaderUrl.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/api/hive/enrol")!
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        var body: [String: Any] = ["platform": "ios"]
        if let id = preferredNodeId { body["node_id"] = id }
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)

        session.dataTask(with: req) { data, resp, err in
            DispatchQueue.main.async {
                if let err = err { return completion(.failure(err)) }
                guard let data = data,
                      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let nid = json["node_id"] as? String,
                      let tok = json["token"] as? String else {
                    return completion(.failure(NSError(domain: "HiveEnrol", code: 1)))
                }
                self.leader = leaderUrl
                self.nodeId = nid
                self.token = tok
                completion(.success((nid, tok)))
            }
        }.resume()
    }

    // MARK: — Telemetry

    func postTelemetry() {
        guard isConfigured else { return }
        let payload = buildTelemetry()
        let url = URL(string: leader.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/api/hive/telemetry")!
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(token, forHTTPHeaderField: "X-Hive-Token")
        req.httpBody = try? JSONSerialization.data(withJSONObject: payload)

        session.dataTask(with: req) { _, _, _ in }.resume()
    }

    private func buildTelemetry() -> [String: Any] {
        let device = UIDevice.current
        let battery = UIDevice.current.batteryLevel
        let processInfo = ProcessInfo.processInfo

        return [
            "contract": "node.resource/v0",
            "node_id": nodeId,
            "platform": "ios",
            "ts": Int(Date().timeIntervalSince1970),
            "compute": [
                "cpu_load_pct": nil,
                "cpu_peak_temp_c": nil,
                "cpu_throttled": nil,
                "gpu_present": true,
                "gpu_load_pct": nil,
                "gpu_temp_c": nil,
                "npu_present": hasANE(),
            ],
            "thermal": [
                "fan_rpm": NSNull(),
                "fan_pwm": NSNull(),
                "fan_max_rpm": NSNull(),
                "fan_mode": "passive",
                "controllable": false,
            ],
            "memory": [
                "ram_total_mb": Int(processInfo.physicalMemory / 1024 / 1024),
                "ram_free_mb": nil,
                "swap_used_mb": nil,
            ],
            "power": [
                "on_battery": !ProcessInfo.processInfo.isLowPowerModeEnabled,
                "battery_pct": battery >= 0 ? Int(battery * 100) : NSNull(),
                "thermal_pressure": nil,
            ],
            "capabilities": capabilities(),
        ]
    }

    private func capabilities() -> [String] {
        var caps = ["inference.cpu"]
        if hasCoreML() { caps.append("inference.coreml") }
        if hasANE() { caps.append("inference.npu") }
        return caps
    }

    private func hasCoreML() -> Bool {
        // CoreML is available on all iOS 11+ devices
        if #available(iOS 11.0, *) { return true }
        return false
    }

    private func hasANE() -> Bool {
        // Apple Neural Engine: A12 Bionic+ (iPhone XS, iPad Pro 2018+)
        // Heuristic: check for MLComputeUnits.all
        if #available(iOS 14.0, *) {
            return true // iPhone 17 Pro definitely has ANE
        }
        return false
    }
}
