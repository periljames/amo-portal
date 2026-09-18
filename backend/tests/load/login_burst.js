// Dedicated staging identities only; each VU owns its own rotating cookie jar.
import http from "k6/http";
import { check, fail, sleep } from "k6";
import { SharedArray } from "k6/data";
import exec from "k6/execution";

const base = (__ENV.BASE_URL || "http://localhost:8080").replace(/\/$/, "");
const users = Number(__ENV.USERS || 1000);
const rampSeconds = Number(__ENV.LOGIN_SPREAD_SECONDS || 60);
const identities = new SharedArray("login identities", () =>
  __ENV.LOGIN_IDENTITIES_FILE ? JSON.parse(open(__ENV.LOGIN_IDENTITIES_FILE)) : []);

export const options = {
  scenarios: {
    morning_login: { executor: "per-vu-iterations", vus: users, iterations: 1, maxDuration: "10m" },
  },
  thresholds: {
    checks: ["rate>0.99"],
    http_req_failed: ["rate<0.01"],
    "http_req_duration{endpoint:login}": ["p(95)<3000", "p(99)<5000"],
    "http_req_duration{endpoint:refresh}": ["p(95)<1500"],
    iterations: [`count>=${users}`],
  },
};

export function setup() {
  if (!Number.isInteger(users) || users < 1 || !Number.isFinite(rampSeconds) || rampSeconds < 0) {
    fail("USERS must be positive and LOGIN_SPREAD_SECONDS must be non-negative");
  }
  if (identities.length < users) fail(`Provide ${users} distinct staging login identities`);
  const unique = new Set(identities.slice(0, users).map((item) => `${item.amo_slug}:${item.email}`));
  if (unique.size !== users || identities.slice(0, users).some((item) => !item.email || !item.password)) {
    fail("Each identity needs a distinct {amo_slug,email,password}");
  }
  if (http.get(`${base}/readyz`).status !== 200) fail("Staging API is not ready");
}

export default function () {
  const identity = identities[exec.vu.idInTest - 1];
  sleep(Math.random() * rampSeconds);
  const login = http.post(`${base}/auth/login`, JSON.stringify(identity), {
    headers: { "Content-Type": "application/json" }, tags: { endpoint: "login" },
  });
  if (!check(login, { "login succeeds": (r) => r.status === 200 })) return;
  const token = login.json("access_token");
  const reads = ["/auth/me", "/auth/portal-preferences/", "/api/notifications/me/unread-count"];
  const responses = http.batch(reads.map((path) => ["GET", `${base}${path}`, null, {
    headers: { Authorization: `Bearer ${token}` }, tags: { endpoint: "bootstrap" },
  }]));
  responses.forEach((response) => check(response, { "bootstrap succeeds": (r) => r.status === 200 }));
  sleep(1 + Math.random() * 5);
  const refresh = http.post(`${base}/auth/refresh`, null, { tags: { endpoint: "refresh" } });
  if (check(refresh, { "refresh succeeds": (r) => r.status === 200 })) {
    const me = http.get(`${base}/auth/me`, {
      headers: { Authorization: `Bearer ${refresh.json("access_token")}` }, tags: { endpoint: "refreshed-read" },
    });
    check(me, { "refreshed token works": (r) => r.status === 200 });
  }
  const logout = http.post(`${base}/auth/logout-session`, null, { tags: { endpoint: "logout" } });
  check(logout, { "session cleaned up": (r) => r.status >= 200 && r.status < 300 });
}
