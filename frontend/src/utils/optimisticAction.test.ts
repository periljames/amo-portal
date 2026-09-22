import { describe, expect, it, vi } from "vitest";

import { queueOptimisticAction, runOptimisticAction } from "./optimisticAction";

describe("runOptimisticAction", () => {
  it("applies local state before awaiting the commit", async () => {
    const order: string[] = [];
    const apply = vi.fn(() => order.push("apply"));
    const commit = vi.fn(async () => {
      order.push("commit");
      return "saved";
    });
    const onSuccess = vi.fn((value: string) => order.push(`success:${value}`));

    const outcome = await runOptimisticAction({ apply, revert: vi.fn(), commit, onSuccess });

    expect(outcome).toEqual({ ok: true, result: "saved" });
    expect(order).toEqual(["apply", "commit", "success:saved"]);
    expect(apply.mock.invocationCallOrder[0]).toBeLessThan(commit.mock.invocationCallOrder[0]);
  });

  it("reverts local state when the commit fails", async () => {
    const revert = vi.fn();
    const onError = vi.fn();
    const failure = new Error("rejected");

    const outcome = await runOptimisticAction({
      apply: vi.fn(),
      revert,
      commit: async () => {
        throw failure;
      },
      onError,
    });

    expect(outcome).toEqual({ ok: false, error: failure });
    expect(revert).toHaveBeenCalledOnce();
    expect(onError).toHaveBeenCalledWith(failure);
  });

  it("returns from queueOptimisticAction before the commit settles", async () => {
    let resolveCommit: (value: string) => void = () => undefined;
    const commit = vi.fn(() => new Promise<string>((resolve) => {
      resolveCommit = resolve;
    }));
    const apply = vi.fn();
    queueOptimisticAction({ apply, revert: vi.fn(), commit });
    expect(apply).toHaveBeenCalledOnce();
    expect(commit).toHaveBeenCalledOnce();
    resolveCommit("done");
    await Promise.resolve();
  });
});
