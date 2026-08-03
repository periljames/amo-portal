import { AlertTriangle, BadgeCheck, BellRing, Info, Volume2, VolumeX, X } from "lucide-react";
import type { ActionFeedback as Feedback } from "../../hooks/useActionFeedback";

const icons = { success: BadgeCheck, error: AlertTriangle, warning: BellRing, info: Info };

export default function ActionFeedback({
  feedback,
  onDismiss,
  audioEnabled,
  onToggleAudio,
}: {
  feedback: Feedback;
  onDismiss: () => void;
  audioEnabled: boolean;
  onToggleAudio: () => void;
}) {
  const Icon = feedback ? icons[feedback.tone] : Info;
  return (
    <div className="proc-feedback-region" aria-live="assertive" aria-atomic="true">
      <button type="button" className="proc-audio-toggle" onClick={onToggleAudio} aria-pressed={audioEnabled} title="Toggle action audio cues">
        {audioEnabled ? <Volume2 size={16} /> : <VolumeX size={16} />}
        <span>Action sounds</span>
      </button>
      {feedback && (
        <div className={`proc-feedback proc-feedback--${feedback.tone}`} role={feedback.tone === "error" ? "alert" : "status"}>
          <Icon size={20} />
          <div><strong>{feedback.message}</strong>{feedback.detail && <span>{feedback.detail}</span>}</div>
          <button type="button" onClick={onDismiss} aria-label="Dismiss notification"><X size={16} /></button>
        </div>
      )}
    </div>
  );
}
