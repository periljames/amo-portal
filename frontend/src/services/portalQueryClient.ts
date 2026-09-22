import type { QueryClient } from "@tanstack/react-query";

let portalQueryClient: QueryClient | null = null;

/** Registered from main so post-auth login warmup can prefetch into the live cache. */
export function registerPortalQueryClient(client: QueryClient): void {
  portalQueryClient = client;
}

export function getPortalQueryClient(): QueryClient | null {
  return portalQueryClient;
}
