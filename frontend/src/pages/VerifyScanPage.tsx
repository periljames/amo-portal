import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Flashlight, FlashlightOff, ScanLine } from "lucide-react";
import { createHardwareScannerListener, parseScannedCertificate } from "../utils/verificationScan";

const VerifyScanPage: React.FC = () => {
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const detectorRef = useRef<any>(null);
  const controlsRef = useRef<any>(null);

  const [error, setError] = useState<string | null>(null);
  const [manual, setManual] = useState("");
  const [torchOn, setTorchOn] = useState(false);
  const [status, setStatus] = useState("Ready to scan");
  const secure = useMemo(() => window.isSecureContext || location.hostname === "localhost", []);

  const routeWithScan = (raw: string) => {
    const parsed = parseScannedCertificate(raw);
    if (parsed) {
      setStatus(`Detected ${parsed}`);
      navigate(`/verify/certificate/${encodeURIComponent(parsed)}`);
    }
  };

  useEffect(() => {
    const listener = createHardwareScannerListener(routeWithScan);
    const handle = (e: KeyboardEvent) => listener.onKeyDown(e);
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const start = async () => {
      if (!secure) {
        setError("Camera scanning requires HTTPS or localhost.");
        setStatus("Camera unavailable");
        return;
      }
      try {
        setStatus("Starting camera…");
        if ("BarcodeDetector" in window) {
          const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
          streamRef.current = stream;
          if (!videoRef.current) return;
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
          detectorRef.current = new (window as any).BarcodeDetector({ formats: ["qr_code", "code_128", "ean_13", "ean_8"] });
          setStatus("Scanning");

          const tick = async () => {
            if (cancelled || !videoRef.current || !detectorRef.current) return;
            try {
              const codes = await detectorRef.current.detect(videoRef.current);
              if (codes?.[0]?.rawValue) {
                routeWithScan(codes[0].rawValue);
                return;
              }
            } catch {
              // no-op
            }
            window.setTimeout(tick, 200);
          };
          tick();
          return;
        }

        const { BrowserMultiFormatReader } = await import("@zxing/browser");
        if (cancelled || !videoRef.current) return;
        const reader = new BrowserMultiFormatReader();
        setStatus("Scanning");
        controlsRef.current = await reader.decodeFromVideoDevice(undefined, videoRef.current, (result: any) => {
          if (result?.getText?.()) routeWithScan(result.getText());
        });
      } catch {
        setError("Camera permission needed. Allow access and retry.");
        setStatus("Permission required");
      }
    };

    void start();
    return () => {
      cancelled = true;
      controlsRef.current?.stop?.();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [secure]);

  const toggleTorch = async () => {
    const track = streamRef.current?.getVideoTracks?.()[0];
    if (!track) return;
    const caps: any = track.getCapabilities ? track.getCapabilities() : {};
    if (!caps.torch) return;
    await track.applyConstraints({ advanced: [{ torch: !torchOn } as any] });
    setTorchOn((x) => !x);
  };

  return (
    <main style={{ maxWidth: 760, margin: "16px auto", padding: 16 }}>
      <section className="card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 12 }}>
          <button type="button" className="secondary-chip-btn" aria-label="Back" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} />
          </button>
          <h1 style={{ margin: 0, fontSize: "1.2rem" }}>Scan Certificate</h1>
          <button type="button" className="secondary-chip-btn" aria-label="Toggle flashlight" title="Toggle flashlight" onClick={toggleTorch}>
            {torchOn ? <FlashlightOff size={16} /> : <Flashlight size={16} />}
          </button>
        </div>

        <p className="text-muted" style={{ marginTop: 0 }}>QR, barcode, hardware scanner, or manual entry.</p>

        <div style={{ borderRadius: 12, overflow: "hidden", border: "1px solid var(--line)", background: "#000", position: "relative", aspectRatio: "3 / 4", maxHeight: 480 }}>
          <video ref={videoRef} style={{ width: "100%", height: "100%", objectFit: "cover" }} playsInline muted />
          <div aria-hidden style={{ position: "absolute", inset: 24, border: "2px solid rgba(255,255,255,0.8)", borderRadius: 12 }} />
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10 }}>
          <span className="text-muted" style={{ fontSize: 13 }}>{status}</span>
          {error ? <span style={{ color: "#b42318", fontSize: 13 }}>{error}</span> : null}
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
          <input
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            placeholder="Certificate number"
            aria-label="Manual certificate input"
          />
          <button type="button" className="secondary-chip-btn" aria-label="Submit manual certificate" onClick={() => routeWithScan(manual)}>
            <ScanLine size={16} />
          </button>
        </div>
      </section>
    </main>
  );
};

export default VerifyScanPage;
