import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

const baseUrl = (__ENV.BASE_URL || "http://127.0.0.1:8080").replace(/\/$/, "");
const platformToken = __ENV.PLATFORM_TOKEN || "";
const tenantContexts = new SharedArray("tenant contexts", () => {
  try {
    const parsed = JSON.parse(__ENV.TENANT_CONTEXTS_JSON || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
});

export const options = {
  discardResponseBodies: true,
  scenarios: {
    platform_control_reads: {
      executor: "constant-arrival-rate",
      exec: "platformControlReads",
      rate: Number(__ENV.PLATFORM_RPS || 150),
      timeUnit: "1s",
      duration: __ENV.DURATION || "5m",
      preAllocatedVUs: 200,
      maxVUs: 1000,
    },
    tenant_quality_training_reads: {
      executor: "per-vu-iterations",
      exec: "tenantQualityTrainingReads",
      vus: Number(__ENV.TENANT_VUS || 1000),
      iterations: Number(__ENV.ITERATIONS_PER_TENANT || 10),
      maxDuration: __ENV.MAX_DURATION || "15m",
      startTime: "5s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<800", "p(99)<1500"],
    "http_req_duration{surface:platform}": ["p(95)<700"],
    "http_req_duration{surface:quality-calendar}": ["p(95)<900"],
    checks: ["rate>0.99"],
  },
};

function headers(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/json",
  };
}

export function platformControlReads() {
  if (!platformToken) {
    sleep(1);
    return;
  }
  const paths = [
    "/platform/saas/capabilities",
    "/platform/saas/jobs?limit=25&offset=0",
    "/platform/tenants?data_mode=REAL&limit=25&offset=0",
    "/platform/saas/integration-health",
  ];
  const path = paths[(__VU + __ITER) % paths.length];
  const response = http.get(`${baseUrl}${path}`, {
    headers: headers(platformToken),
    tags: { surface: "platform" },
    timeout: "10s",
  });
  check(response, {
    "platform response is successful": (result) => result.status >= 200 && result.status < 300,
    "platform response is not HTML": (result) => !(result.headers["Content-Type"] || "").includes("text/html"),
  });
}

export function tenantQualityTrainingReads() {
  if (!tenantContexts.length) {
    sleep(1);
    return;
  }
  const context = tenantContexts[(__VU - 1) % tenantContexts.length];
  const amoCode = encodeURIComponent(String(context.amoCode || context.amo_code || ""));
  const token = String(context.token || "");
  if (!amoCode || !token) {
    sleep(1);
    return;
  }
  const today = new Date();
  const end = new Date(today.getTime() + 90 * 24 * 60 * 60 * 1000);
  const startDate = today.toISOString().slice(0, 10);
  const endDate = end.toISOString().slice(0, 10);
  const calendar = http.get(
    `${baseUrl}/api/maintenance/${amoCode}/quality/calendar?start=${startDate}&end=${endDate}&limit=50&offset=0`,
    {
      headers: headers(token),
      tags: { surface: "quality-calendar" },
      timeout: "10s",
    },
  );
  check(calendar, {
    "quality calendar is successful": (result) => result.status >= 200 && result.status < 300,
    "quality calendar has JSON": (result) => (result.headers["Content-Type"] || "").includes("application/json"),
  });

  if ((__ITER + __VU) % 3 === 0) {
    const training = http.get(`${baseUrl}/training/competence/summary`, {
      headers: headers(token),
      tags: { surface: "training" },
      timeout: "10s",
    });
    check(training, {
      "training endpoint is bounded": (result) => [200, 403, 404].includes(result.status),
    });
  }
  sleep(Math.random() * 0.5);
}

export function handleSummary(data) {
  const output = JSON.stringify(data, null, 2);
  return {
    stdout: output,
    "loadtest-results/saas-control-plane-summary.json": output,
  };
}
