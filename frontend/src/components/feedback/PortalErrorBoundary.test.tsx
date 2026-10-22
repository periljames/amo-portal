import { describe, expect, it, vi } from "vitest";
import PortalErrorBoundary from "./PortalErrorBoundary";

describe("shared surface route recovery", () => {
  it("does not reset healthy shared controls when the route changes", () => {
    const boundary = new PortalErrorBoundary({ resetKey: "new", children: null });
    boundary.setState = vi.fn();
    boundary.componentDidUpdate({ resetKey: "old", children: null });
    expect(boundary.setState).not.toHaveBeenCalled();
  });
  it("recovers a failed section on a different route", () => {
    const boundary = new PortalErrorBoundary({ resetKey: "new", children: null });
    boundary.state = { error: new Error("module failed") };
    boundary.setState = vi.fn();
    boundary.componentDidUpdate({ resetKey: "old", children: null });
    expect(boundary.setState).toHaveBeenCalledWith({ error: null });
  });
  it("retains the retry controls while a failed route remains active", () => {
    const boundary = new PortalErrorBoundary({ resetKey: "same", children: null });
    boundary.state = { error: new Error("module failed") };
    boundary.setState = vi.fn();
    boundary.componentDidUpdate({ resetKey: "same", children: null });
    expect(boundary.setState).not.toHaveBeenCalled();
  });
});
