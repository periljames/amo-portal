import { describe, expect, it } from "vitest";
import { isEmailAddress, validEmailList } from "./emailAddresses";

describe("individual email entry", () => {
  it.each(["broken", "person@", "person@domain", "person@example.com;other@example.com", "person@example.com,other@example.com", "person name@example.com", ""]) ("rejects incomplete and combined addresses: %s", value => expect(isEmailAddress(value)).toBe(false));
  it("accepts one complete address and rejects duplicates regardless of case or surrounding whitespace", () => {
    expect(isEmailAddress(" person+quality@example.com ")).toBe(true);
    expect(validEmailList(["one@example.com", "two@example.com"])).toBe(true);
    expect(validEmailList(["one@example.com", " ONE@example.com "])).toBe(false);
    expect(validEmailList(["one@example.com", ""])).toBe(false);
    expect(validEmailList([])).toBe(false);
  });
});
