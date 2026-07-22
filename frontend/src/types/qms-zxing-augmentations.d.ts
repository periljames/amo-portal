import "@zxing/library";
import "../services/qms";

declare module "@zxing/library" {
  interface QRCodeWriter {
    /**
     * The installed runtime accepts omitted encode hints. The upstream
     * declaration currently marks the hints map as mandatory.
     */
    encode(contents: string, format: BarcodeFormat, width: number, height: number): unknown;
  }
}

declare module "../services/qms" {
  interface CARInviteOut {
    /** Optional public audit-report link returned for audit-linked CARs. */
    audit_report_download_url?: string | null;
  }
}
