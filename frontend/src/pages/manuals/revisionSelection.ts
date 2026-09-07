export function resolveNextRevisionId(previousRevisionId: string, revisions: Array<{ id: string }>): string {
  if (!revisions.length) return "";
  if (previousRevisionId && revisions.some((row) => row.id === previousRevisionId)) return previousRevisionId;
  return revisions[0].id;
}
