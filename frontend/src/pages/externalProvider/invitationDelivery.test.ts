import { describe, expect, it } from "vitest";
import { invitationNotice, type DeliveryReceipt } from "./invitationDelivery";
const receipt: DeliveryReceipt = { email_status: "SENT", email_delivery_status: "ACCEPTED", email_log_id: "log", provider_message_id: "id", sending_mode: "SANDBOX", provider_accepted: true, recipient: "vendor@example.test", effective_recipient: "sandbox@example.test" };
describe("invitation destination notice", () => {
  it("names both the test mailbox and intended representative without claiming delivery", () => {
    const notice = invitationNotice(receipt);
    expect(notice.tone).toBe("warning");
    expect(notice.message).toContain("sandbox@example.test");
    expect(notice.message).toContain("vendor@example.test");
    expect(notice.message).toContain("redirects");
  });
  it("does not invent a destination for legacy receipts", () => {
    expect(invitationNotice({...receipt, effective_recipient:null}).message).toContain("destination not recorded");
  });
  it("names the account when email fails", () => {
    const notice = invitationNotice({...receipt, provider_accepted:false, email_delivery_status:"BLOCKED"});
    expect(notice.tone).toBe("warning");
    expect(notice.message).toContain("vendor@example.test");
    expect(notice.message).toContain("not accepted");
  });
  it("distinguishes provider acceptance from recipient delivery", () => {
    const notice = invitationNotice({...receipt, sending_mode:"PRODUCTION", effective_recipient:"vendor@example.test"});
    expect(notice.tone).toBe("success");
    expect(notice.message).toContain("Recipient delivery is not yet confirmed");
  });
});
