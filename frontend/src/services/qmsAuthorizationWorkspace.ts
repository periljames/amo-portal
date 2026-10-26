import { readCompleteRegister } from "./qmsCompleteRegister";
import { getQmsAuthorizationOverview, listQmsAuthorizationPeople, listQmsAuthorizationCases, listQmsAuthorizationReviews, listQmsAuthorizations, listQmsPrivilegeRules } from "./qmsPeople";

export async function loadQmsAuthorizationWorkspace(amoCode: string, signal: AbortSignal) {
  const overview = await getQmsAuthorizationOverview(amoCode, signal);
  if (!overview?.permissions || !overview.metrics || !Array.isArray(overview.attention)) {
    throw new Error("Authorization overview could not be read. Refresh to retry.");
  }
  const canReadPolicy = overview.permissions.can_prepare || overview.permissions.can_manage_policy;
  const results = await Promise.allSettled([
    readCompleteRegister(async offset => { const page = await listQmsAuthorizationPeople(amoCode, { limit: 100, offset }, signal); return { ...page, items: page.items.map(item => ({ ...item, id: item.key })) }; }, signal).then(items => ({ items })),
    readCompleteRegister(offset => listQmsAuthorizationCases(amoCode, { limit: 100, offset }, signal), signal).then(items => ({ items })),
    listQmsAuthorizationReviews(amoCode, {}, signal),
    listQmsAuthorizations(amoCode, {}, signal),
    canReadPolicy ? listQmsPrivilegeRules(amoCode, { includeInactive: true }, signal) : Promise.resolve({ items: [] }),
  ] as const);
  signal.throwIfAborted();
  const names = ["People", "Authorization cases", "Reviews", "Authorizations", "Policy"];
  const errors = results.flatMap((result, index) => result.status === "rejected"
    ? [`${names[index]}: ${result.reason instanceof Error ? result.reason.message : "Could not be loaded."}`]
    : !Array.isArray(result.value?.items) ? [`${names[index]}: The response is incomplete.`] : []);
  const items = <T,>(result: PromiseSettledResult<{ items: T[] }>): T[] => result.status === "fulfilled" && Array.isArray(result.value?.items) ? result.value.items : [];
  return { overview, people: items(results[0]), cases: items(results[1]), reviews: items(results[2]), authorizations: items(results[3]), rules: items(results[4]), errors };
}
