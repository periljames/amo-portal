export type DeliveryReceipt = {
  email_status: string;
  email_delivery_status: string;
  email_log_id: string | null;
  provider_message_id: string | null;
  sending_mode: string | null;
  provider_accepted: boolean;
  recipient?: string | null;
  effective_recipient?: string | null;
};

export function invitationNotice(receipt: DeliveryReceipt): { tone: "success" | "warning"; message: string } {
  const intended = receipt.recipient || "the invited representative (address unavailable)";
  if (!receipt.provider_accepted) return {
    tone: "warning",
    message: `Account saved for ${intended}. Invitation email was not accepted (${receipt.email_delivery_status.toLowerCase()}). Check delivery history and mail settings before resending.`,
  };
  const actual = receipt.effective_recipient;
  if (receipt.sending_mode === "SANDBOX") return {
    tone: "warning",
    message: `Test email accepted for ${actual || "a test mailbox (destination not recorded)"}. Invitation intended for ${intended}. Sandbox mode redirects email to the test destination, not automatically to the intended recipient. Enable real recipient sending in platform email settings before resending.`,
  };
  if (!actual) return {
    tone: "warning",
    message: `Invitation for ${intended} accepted by the email provider, but the actual destination was not recorded. Check delivery history before resending.`,
  };
  return {
    tone: "success",
    message: `Invitation email ${receipt.email_delivery_status === "DELIVERED" ? "accepted by the mail server for" : "accepted by the email provider for"} ${actual}. Intended recipient: ${intended}. ${receipt.email_delivery_status === "DELIVERED" ? "Inbox placement is not confirmed." : "Recipient delivery is not yet confirmed."}`,
  };
}
