import http from "k6/http";
import { check, sleep } from "k6";
import { randomBytes } from "k6/crypto";

const base = __ENV.BASE_URL || "http://127.0.0.1:8765";
export function setup() {
  const id = Array.from(new Uint8Array(randomBytes(16))).map(x => x.toString(16).padStart(2, "0")).join("");
  const account = { email: id + "@example.com", password: id + "A1" };
  const options = { headers: { "Content-Type": "application/json" } };
  const register = http.post(base + "/api/v1/auth/register", JSON.stringify({
    ...account, full_name: "Load test", tenant_name: id,
  }), options);
  if (register.status !== 201) throw new Error("Load test registration failed");
  const login = http.post(base + "/api/v1/auth/login", JSON.stringify(account), options);
  if (login.status !== 200) throw new Error("Load test authentication failed");
  return { token: login.json("access_token") };
}
export function exercise(data) {
  const options = { headers: { Authorization: "Bearer " + data.token, "Content-Type": "application/json" } };
  for (const path of ["/health", "/api/v1/meta", "/api/v1/companies/AAPL"]) {
    check(http.get(base + path, options), { "successful read": r => r.status === 200 });
  }
  check(http.post(base + "/api/v1/valuation/dcf", JSON.stringify({
    ticker: "user-supplied-model", base_revenue: 1000, revenue_growth: [0.05],
    ebit_margin: [0.2], tax_rate: 0.25, wacc: 0.1, shares_outstanding: 100,
  }), options), { "DCF calculation succeeds": r => r.status === 200 });
  check(http.post(base + "/api/v1/screener/run", "{}", options), {
    "recorded universe available": r => r.status === 200 && r.json().length > 0,
  });
  sleep(1);
}
export const thresholds = {
  http_req_duration: ["p(95)<500"], http_req_failed: ["rate<0.01"], checks: ["rate>0.99"],
};

export function handleSummary(data) {
  // k6 setup data contains the temporary bearer token. Export aggregate metrics only.
  return {
    [__ENV.K6_SUMMARY_PATH || "smoke.json"]: JSON.stringify({ metrics: data.metrics, root_group: data.root_group }, null, 2),
    stdout: "Load summary saved with aggregate metrics only.\n",
  };
}
