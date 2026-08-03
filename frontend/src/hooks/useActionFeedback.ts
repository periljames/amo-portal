import { useCallback, useEffect, useState } from "react";

export type FeedbackTone = "success" | "error" | "warning" | "info";
export type ActionFeedback = { tone: FeedbackTone; message: string; detail?: string } | null;

function playCue(tone: FeedbackTone): void {
  if (typeof window === "undefined") return;
  if (window.localStorage.getItem("portal-audio-cues") === "off") return;
  const WindowAudioContext = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!WindowAudioContext) return;
  const context = new WindowAudioContext();
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  const now = context.currentTime;
  const frequencies = tone === "success" ? [620, 820] : tone === "error" ? [260, 180] : tone === "warning" ? [420, 360] : [520];
  oscillator.type = tone === "error" ? "sawtooth" : "sine";
  oscillator.frequency.setValueAtTime(frequencies[0], now);
  if (frequencies[1]) oscillator.frequency.exponentialRampToValueAtTime(frequencies[1], now + 0.16);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.035, now + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.24);
  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start(now);
  oscillator.stop(now + 0.25);
  oscillator.addEventListener("ended", () => void context.close());
}

export function useActionFeedback() {
  const [feedback, setFeedback] = useState<ActionFeedback>(null);
  const [audioEnabled, setAudioEnabled] = useState(() => typeof window === "undefined" || window.localStorage.getItem("portal-audio-cues") !== "off");

  useEffect(() => {
    if (!feedback) return;
    const timer = window.setTimeout(() => setFeedback(null), feedback.tone === "error" ? 9000 : 5500);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  const notify = useCallback((tone: FeedbackTone, message: string, detail?: string) => {
    setFeedback({ tone, message, detail });
    playCue(tone);
  }, []);

  const toggleAudio = useCallback(() => {
    setAudioEnabled((current) => {
      const next = !current;
      window.localStorage.setItem("portal-audio-cues", next ? "on" : "off");
      if (next) playCue("info");
      return next;
    });
  }, []);

  return { feedback, clearFeedback: () => setFeedback(null), notify, audioEnabled, toggleAudio };
}
