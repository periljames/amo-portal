import { useEffect, useRef } from "react";

type ReadingTimerOpts = {
  sectionId: string;
  enabled?: boolean;
  threshold?: number;
  onTick?: (payload: { sectionId: string; activeSecondsSpent: number }) => void;
};

export function useReadingTimer({
  sectionId,
  enabled = true,
  threshold = 0.5,
  onTick,
}: ReadingTimerOpts) {
  const targetRef = useRef<HTMLElement | null>(null);
  const secondsRef = useRef(0);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled || !targetRef.current) return;

    const node = targetRef.current;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.some((entry) => entry.isIntersecting && entry.intersectionRatio >= threshold);
        if (visible && intervalRef.current == null) {
          intervalRef.current = window.setInterval(() => {
            secondsRef.current += 1;
            onTick?.({ sectionId, activeSecondsSpent: secondsRef.current });
          }, 1000);
        } else if (!visible && intervalRef.current != null) {
          window.clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      },
      { threshold: [threshold] },
    );

    observer.observe(node);

    return () => {
      observer.disconnect();
      if (intervalRef.current != null) {
        window.clearInterval(intervalRef.current);
      }
      intervalRef.current = null;
    };
  }, [enabled, onTick, sectionId, threshold]);

  return {
    targetRef,
    getActiveSeconds: () => secondsRef.current,
  };
}
