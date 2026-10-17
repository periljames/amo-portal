import { defineConfig } from "@playwright/test";
import offline from "./playwright.offline.config";

export default defineConfig({ ...offline, testMatch: ["checklist-table.spec.ts", "checklist-experience.spec.ts", "quality-realtime.spec.ts"] });
