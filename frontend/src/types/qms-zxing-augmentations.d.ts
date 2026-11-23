import "@zxing/library";
import "../services/qms";

declare module "../services/qms" {
  interface CARInviteOut {
    /** Optional public audit-report link returned for audit-linked CARs. */
    audit_report_download_url?: string | null;
  }
}
