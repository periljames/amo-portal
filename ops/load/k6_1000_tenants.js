import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

const baseUrl = (__ENV.BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const fixturePath = __ENV.TENANT_FIXTURES || "./tenant-fixtures.json";
const tenants = new SharedArray("tenant-auth-fixtures", () => JSON.parse(open(fixturePath)));

if (tenants.length < 1000) {
  throw new Error(`The 1,000-tenant gate requires at least 1,000 unique tenant fixtures; received ${tenants.length}.`);
}

export const options = {
  scenarios: {
    tenant_concurrency_gate: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 100 },
        { duration: "3m", target: 500 },
        { duration: "5m", target: 1000 },
        { duration: "10m", target: 1000 },
        { duration: "2m", target: 0 },
      ],
      gracefulRampDown: "30s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<750", "p(99)<1500"],
    checks: ["rate>0.99"],
  },
};

function authHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/json",
    "User-Agent": "amo-portal-k6-tenant-gate/1.0",
  };
}

export default function () {
  const fixture = tenants[(__VU - 1) % tenants.length];
  if (!fixture?.token || !fixture?.tenant_id) {
    throw new Error(`Invalid fixture for VU ${__VU}; tenant_id and token are required.`);
  }
  const params = {
    headers: authHeaders(fixture.token),
    tags: { tenant_id: fixture.tenant_id },
    timeout: "10s",
  };

  const responses = http.batch([
    ["GET", `${baseUrl}/auth/me`, null, { ...params, tags: { ...params.tags, endpoint: "auth_me" } }],
    ["GET", `${baseUrl}/billing/access-status`, null, { ...params, tags: { ...params.tags, endpoint: "billing_access" } }],
    ["GET", `${baseUrl}/billing/entitlements`, null, { ...params, tags: { ...params.tags, endpoint: "billing_entitlements" } }],
  ]);

  check(responses[0], { "auth/me succeeds": (r) => r.status === 200 });
  check(responses[1], { "billing access succeeds": (r) => r.status === 200 });
  check(responses[2], { "entitlements succeed": (r) => r.status === 200 });

  sleep(1);
}
