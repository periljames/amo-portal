import React, { useMemo, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { listAdminUsers } from "../../services/adminUsers";
import { qmsCreateDistribution, qmsDeleteCarAttachment, qmsListCarAttachments, qmsListDistributions, qmsUploadCarAttachment, qmsUpdateCar, type CARStatus } from "../../services/qms";
import { addTrainingEventParticipant, downloadTrainingFile, listTrainingEvents, listTrainingFiles, uploadTrainingFile } from "../../services/training";
import type { AdminUserRead } from "../../services/adminUsers";
import type { TrainingEventRead } from "../../types/training";
import { updateAdminUser, deactivateAdminUser, type AccountRole } from "../../services/adminUsers";
import { motionTokens } from "../../utils/motion";
import { getEvidenceAcceptString, isEvidenceFileAllowed } from "../../services/notificationPreferences";

export type ActionPanelContext =
  | { type: "car"; id: string; title: string; status?: CARStatus; ownerId?: string | null }
  | { type: "training"; userId: string; courseId?: string | null; courseName?: string | null }
  | { type: "document"; docId: string; title: string }
  | { type: "user"; userId: string; name: string; role?: AccountRole };

type Props = {
  isOpen: boolean;
  context: ActionPanelContext | null;
  onClose: () => void;
};

const ActionPanel: React.FC<Props> = ({ isOpen, context, onClose }) => {
  const reduceMotion = useReducedMotion();
  const queryClient = useQueryClient();
  const [selectedAssignee, setSelectedAssignee] = useState<string>("");
  const [selectedStatus, setSelectedStatus] = useState<CARStatus | "">("");
  const [selectedEventId, setSelectedEventId] = useState<string>("");
  const [distributionUserId, setDistributionUserId] = useState<string>("");
  const [roleSelection, setRoleSelection] = useState<AccountRole | "">("");
  const [selectedEvidenceFile, setSelectedEvidenceFile] = useState<File | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  const { data: adminUsers = [] } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => listAdminUsers({ limit: 50 }),
  });

  const { data: trainingEvents = [] } = useQuery({
    queryKey: ["training-events"],
    queryFn: () => listTrainingEvents(),
  });



  const { data: carAttachments = [] } = useQuery({
    queryKey: ["qms-car-attachments", context?.type === "car" ? context.id : "none"],
    queryFn: () => qmsListCarAttachments((context as { type: "car"; id: string }).id),
    enabled: context?.type === "car",
  });

  const { data: trainingFiles = [] } = useQuery({
    queryKey: ["training-files", context?.type === "training" ? context.userId : "none"],
    queryFn: () => listTrainingFiles(),
    enabled: context?.type === "training",
  });

  const { data: documentAcks = [] } = useQuery({
    queryKey: ["qms-distributions", context?.type === "document" ? context.docId : "none", "acks"],
    queryFn: () => qmsListDistributions({ doc_id: (context as { type: "document"; docId: string }).docId }),
    enabled: context?.type === "document",
  });

  const uploadEvidenceMutation = useMutation({
    mutationFn: async () => {
      if (!context || !selectedEvidenceFile) return;
      if (context.type === "car") {
        return qmsUploadCarAttachment(context.id, selectedEvidenceFile);
      }
      if (context.type === "training") {
        const fd = new FormData();
        fd.append("file", selectedEvidenceFile);
        fd.append("owner_user_id", context.userId);
        return uploadTrainingFile(fd);
      }
      return null;
    },
    onSuccess: () => {
      if (context?.type === "car") queryClient.invalidateQueries({ queryKey: ["qms-car-attachments", context.id] });
      if (context?.type === "training") queryClient.invalidateQueries({ queryKey: ["training-files", context.userId] });
      setSelectedEvidenceFile(null);
    },
  });

  const deleteCarAttachmentMutation = useMutation({
    mutationFn: async (attachmentId: string) => {
      if (!context || context.type !== "car") return;
      await qmsDeleteCarAttachment(context.id, attachmentId);
    },
    onSuccess: () => {
      if (context?.type === "car") queryClient.invalidateQueries({ queryKey: ["qms-car-attachments", context.id] });
    },
  });

  const closeAndReset = () => {
    setSelectedAssignee("");
    setSelectedStatus("");
    setSelectedEventId("");
    setDistributionUserId("");
    setRoleSelection("");
    setSelectedEvidenceFile(null);
    setEvidenceError(null);
    onClose();
  };

  const handleEvidenceSelection = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      setSelectedEvidenceFile(null);
      setEvidenceError(null);
      return;
    }
    if (!isEvidenceFileAllowed(file)) {
      setSelectedEvidenceFile(null);
      setEvidenceError("File blocked by multimedia policy settings (photo/video/pdf).");
      return;
    }
    setEvidenceError(null);
    setSelectedEvidenceFile(file);
  };

  const assignees = useMemo(() => adminUsers, [adminUsers]);

  const handleCarUpdate = async () => {
    if (!context || context.type !== "car") return;
    await qmsUpdateCar(context.id, {
      assigned_to_user_id: selectedAssignee || context.ownerId || undefined,
      status: (selectedStatus || context.status) as CARStatus,
    });
    queryClient.invalidateQueries({ queryKey: ["qms-cars"] });
    closeAndReset();
  };

  const handleTrainingAssign = async () => {
    if (!context || context.type !== "training" || !selectedEventId) return;
    await addTrainingEventParticipant({
      event_id: selectedEventId,
      user_id: context.userId,
      status: "INVITED",
    });
    queryClient.invalidateQueries({ queryKey: ["training-events"] });
    closeAndReset();
  };

  const handleDistribution = async () => {
    if (!context || context.type !== "document" || !distributionUserId) return;
    await qmsCreateDistribution({
      doc_id: context.docId,
      recipient_user_id: distributionUserId,
      requires_ack: true,
    });
    queryClient.invalidateQueries({ queryKey: ["qms-distributions"] });
    closeAndReset();
  };

  const handleUserUpdate = async () => {
    if (!context || context.type !== "user") return;
    if (roleSelection) {
      await updateAdminUser(context.userId, { role: roleSelection });
    }
    queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    closeAndReset();
  };

  const handleUserDeactivate = async () => {
    if (!context || context.type !== "user") return;
    await deactivateAdminUser(context.userId);
    queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    closeAndReset();
  };

  return (
    <AnimatePresence>
      {isOpen && context && (
        <div className="action-panel__overlay" onClick={closeAndReset}>
          <motion.aside
            className="action-panel"
            onClick={(event) => event.stopPropagation()}
            initial={reduceMotion ? false : { x: 320, opacity: 0 }}
            animate={reduceMotion ? { opacity: 1 } : { x: 0, opacity: 1 }}
            exit={reduceMotion ? { opacity: 0 } : { x: 320, opacity: 0 }}
            transition={motionTokens.panel}
          >
            <div className="action-panel__header">
              <div>
                <div className="action-panel__title">Quick actions</div>
                <div className="action-panel__subtitle">{context.type.toUpperCase()}</div>
              </div>
              <button type="button" className="action-panel__close" onClick={closeAndReset}>
                Close
              </button>
            </div>

            {context.type === "car" && (
              <div className="action-panel__body">
                <div className="action-panel__section">
                  <div className="action-panel__label">Assign owner</div>
                  <select
                    value={selectedAssignee}
                    onChange={(event) => setSelectedAssignee(event.target.value)}
                  >
                    <option value="">Select assignee</option>
                    {assignees.map((user: AdminUserRead) => (
                      <option key={user.id} value={user.id}>
                        {user.full_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="action-panel__section">
                  <div className="action-panel__label">Status</div>
                  <select
                    value={selectedStatus || context.status || ""}
                    onChange={(event) => setSelectedStatus(event.target.value as CARStatus)}
                  >
                    {[
                      "DRAFT",
                      "OPEN",
                      "IN_PROGRESS",
                      "PENDING_VERIFICATION",
                      "CLOSED",
                      "ESCALATED",
                    ].map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="action-panel__section">
                  <div className="action-panel__label">Evidence</div>
                  <input type="file" accept={getEvidenceAcceptString()} onChange={handleEvidenceSelection} />
                  {evidenceError ? <div className="action-panel__label">{evidenceError}</div> : null}
                  <button type="button" className="btn btn-secondary" onClick={() => uploadEvidenceMutation.mutate()} disabled={!selectedEvidenceFile || uploadEvidenceMutation.isPending}>
                    Upload evidence
                  </button>
                  <ul>
                    {carAttachments.map((a) => (
                      <li key={a.id}>
                        <a href={a.download_url} target="_blank" rel="noreferrer">{a.filename}</a> ({a.size_bytes ?? 0} bytes)
                        <button type="button" className="btn btn-secondary" onClick={() => deleteCarAttachmentMutation.mutate(a.id)}>Delete</button>
                      </li>
                    ))}
                  </ul>
                </div>
                <button type="button" className="btn btn-primary" onClick={handleCarUpdate}>
                  Apply CAR updates
                </button>
              </div>
            )}

            {context.type === "training" && (
              <div className="action-panel__body">
                <div className="action-panel__section">
                  <div className="action-panel__label">Assign to event</div>
                  <select
                    value={selectedEventId}
                    onChange={(event) => setSelectedEventId(event.target.value)}
                  >
                    <option value="">Select event</option>
                    {trainingEvents.map((event: TrainingEventRead) => (
                      <option key={event.id} value={event.id}>
                        {event.title} · {event.starts_on}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="action-panel__section">
                  <div className="action-panel__label">Evidence</div>
                  <input type="file" accept={getEvidenceAcceptString()} onChange={handleEvidenceSelection} />
                  {evidenceError ? <div className="action-panel__label">{evidenceError}</div> : null}
                  <button type="button" className="btn btn-secondary" onClick={() => uploadEvidenceMutation.mutate()} disabled={!selectedEvidenceFile || uploadEvidenceMutation.isPending}>
                    Upload evidence
                  </button>
                  <ul>
                    {trainingFiles.filter((f) => f.owner_user_id === context.userId).map((f) => (
                      <li key={f.id}>
                        <button type="button" className="btn btn-secondary" onClick={() => downloadTrainingFile(f.id)}>{f.original_filename}</button> ({f.size_bytes ?? 0} bytes)
                      </li>
                    ))}
                  </ul>
                </div>
                <button type="button" className="btn btn-primary" onClick={handleTrainingAssign}>
                  Schedule training
                </button>
              </div>
            )}

            {context.type === "document" && (
              <div className="action-panel__body">
                <div className="action-panel__section">
                  <div className="action-panel__label">Request acknowledgement</div>
                  <select
                    value={distributionUserId}
                    onChange={(event) => setDistributionUserId(event.target.value)}
                  >
                    <option value="">Select recipient</option>
                    {assignees.map((user: AdminUserRead) => (
                      <option key={user.id} value={user.id}>
                        {user.full_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="action-panel__section">
                  <div className="action-panel__label">Acknowledgement status</div>
                  <ul>
                    {documentAcks.map((ack) => (
                      <li key={ack.id}>{ack.recipient_user_id} · {ack.acked_at ? "Acknowledged" : "Pending"}</li>
                    ))}
                  </ul>
                </div>
                <button type="button" className="btn btn-primary" onClick={handleDistribution}>
                  Send acknowledgement request
                </button>
              </div>
            )}

            {context.type === "user" && (
              <div className="action-panel__body">
                <div className="action-panel__section">
                  <div className="action-panel__label">Update role</div>
                  <select
                    value={roleSelection || context.role || ""}
                    onChange={(event) => setRoleSelection(event.target.value as AccountRole)}
                  >
                    <option value="">Select role</option>
                    {[
                      "SUPERUSER",
                      "AMO_ADMIN",
                      "QUALITY_MANAGER",
                      "SAFETY_MANAGER",
                      "PLANNING_ENGINEER",
                      "PRODUCTION_ENGINEER",
                      "CERTIFYING_ENGINEER",
                      "CERTIFYING_TECHNICIAN",
                      "TECHNICIAN",
                      "AUDITOR",
                      "STORES",
                      "VIEW_ONLY",
                    ].map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="action-panel__actions">
                  <button type="button" className="btn btn-secondary" onClick={handleUserDeactivate}>
                    Revoke access
                  </button>
                  <button type="button" className="btn btn-primary" onClick={handleUserUpdate}>
                    Apply role update
                  </button>
                </div>
              </div>
            )}
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
};

export default ActionPanel;
