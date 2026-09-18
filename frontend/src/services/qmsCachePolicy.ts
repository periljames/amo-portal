/** Live authority must not be resurrected from a persisted or stale cache. */
export function isQmsLiveAuthority(value: string): boolean {
  return /(?:assignment[-/]eligibility|auditor[-/]eligibility|preparation[-/]readiness|approval[-/]authority|independence|active[-/]privilege)/i.test(value);
}

export function withoutQmsAuthority<T extends { clientState: { queries: Array<{ queryKey: readonly unknown[] }> } }>(client: T | undefined): T | undefined {
  if (!client) return client;
  return { ...client, clientState: { ...client.clientState, queries: client.clientState.queries.filter(
    (query) => !isQmsLiveAuthority(query.queryKey.map(String).join(":")),
  ) } };
}
