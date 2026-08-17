import http from "k6/http";
import { check, fail, sleep } from "k6";
import { SharedArray } from "k6/data";
import exec from "k6/execution";
import { Trend } from "k6/metrics";

const queryCount = new Trend("db_query_count", true);
const bulkQueueAge = new Trend("bulk_queue_age_seconds", true);
const commandQueueAge = new Trend("command_queue_age_seconds", true);

const identities = new SharedArray("20,000 production-shaped identities", () => {
  const path = __ENV.IDENTITY_TOKEN_FILE;
  if (!path) return [];
  return JSON.parse(open(path));
});

export const options = {
  scenarios: {
    twenty_tenant_concurrency: {
      executor: "ramping-arrival-rate",
      startRate: 50,
      timeUnit: "1s",
      preAllocatedVUs: 1000,
      maxVUs: 5000,
      stages: [
        { target: 500, duration: "2m" },
        { target: 1500, duration: "8m" },
        { target: 2500, duration: "10m" },
        { target: 0, duration: "2m" },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.005"],
    http_req_duration: ["p(95)<600", "p(99)<1200"],
    db_query_count: ["p(95)<25", "p(99)<40"],
    bulk_queue_age_seconds: ["p(95)<30", "max<120"],
    command_queue_age_seconds: ["p(95)<10", "max<60"],
    checks: ["rate>0.995"],
  },
};

const BASE_URL = (__ENV.BASE_URL || "http://localhost:8080").replace(/\/$/, "");
const READ_PATH = __ENV.READ_PATH || "/workforce/permissions/current";

export function setup() {
  if (identities.length < 20000) fail("IDENTITY_TOKEN_FILE must contain at least 20,000 {tenant_id,user_id,token} records");
  const tenants = new Set(identities.slice(0, 20000).map((item) => item.tenant_id));
  if (tenants.size < 20) fail("Load dataset must represent at least 20 tenants");
  const ready = http.get(`${BASE_URL}/readyz`);
  if (ready.status !== 200) fail(`Backend is not ready (${ready.status})`);
}

export default function () {
  const identity = identities[exec.scenario.iterationInTest % 20000];
  const params = {
    headers: {
      Authorization: `Bearer ${identity.token}`,
      "X-Load-Tenant": identity.tenant_id,
      "X-Load-Identity": identity.user_id,
    },
    tags: { tenant: identity.tenant_id },
  };
  const response = http.get(`${BASE_URL}${READ_PATH}`, params);
  check(response, {
    "request succeeds": (value) => value.status >= 200 && value.status < 400,
    "tenant does not leak": (value) => !value.body || !value.body.includes("cross_tenant_leak"),
  });
  queryCount.add(Number(response.headers["X-Db-Query-Count"] || 0));

  if (exec.scenario.iterationInTest % 20 === 0) {
    const metrics = http.get(`${BASE_URL}/resilience/metrics`, params);
    if (metrics.status === 200) {
      const payload = metrics.json();
      bulkQueueAge.add(Number(payload.bulk_queue_age_seconds || 0));
      commandQueueAge.add(Number(payload.command_processing_age_seconds || 0));
    }
  }
  sleep(Math.random() * 0.2);
}
