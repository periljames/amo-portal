import React, { useEffect, useMemo, useRef, useState } from "react";
import { Camera, Building2, Bell, Shield, Mail, Phone, RefreshCw, BadgeCheck, UserSquare2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import PageHeader from "../components/shared/PageHeader";
import SectionCard from "../components/shared/SectionCard";
import Button from "../components/UI/Button";
import { useToast } from "../components/feedback/ToastProvider";
import {
  endSession,
  fetchCurrentUser,
  getCachedUser,
  getContext,
  type PortalUser,
} from "../services/auth";
import {
  getNotificationPreferences,
  setNotificationPreferences,
  type NotificationPreferences,
} from "../services/notificationPreferences";

const PROFILE_META_PREFIX = "amo_portal_profile_meta";
const PROFILE_AVATAR_PREFIX = "amo_portal_profile_avatar";

type LocalProfileMeta = {
  title: string;
  bio: string;
  emergencyName: string;
  emergencyPhone: string;
  officeLocation: string;
};

const EMPTY_META: LocalProfileMeta = {
  title: "",
  bio: "",
  emergencyName: "",
  emergencyPhone: "",
  officeLocation: "",
};

function metaStorageKey(userId?: string | null): string {
  return `${PROFILE_META_PREFIX}:${userId || "anonymous"}`;
}

function avatarStorageKey(userId?: string | null): string {
  return `${PROFILE_AVATAR_PREFIX}:${userId || "anonymous"}`;
}

function readLocalProfileMeta(userId?: string | null): LocalProfileMeta {
  if (typeof window === "undefined") return EMPTY_META;
  const raw = window.localStorage.getItem(metaStorageKey(userId));
  if (!raw) return EMPTY_META;
  try {
    return { ...EMPTY_META, ...(JSON.parse(raw) as Partial<LocalProfileMeta>) };
  } catch {
    return EMPTY_META;
  }
}

function readStoredAvatar(userId?: string | null): string | null {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(avatarStorageKey(userId));
  return value && value.trim() ? value : null;
}

function saveLocalProfileMeta(userId: string, value: LocalProfileMeta): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(metaStorageKey(userId), JSON.stringify(value));
}

function saveStoredAvatar(userId: string, value: string | null): void {
  if (typeof window === "undefined") return;
  const key = avatarStorageKey(userId);
  if (value) {
    window.localStorage.setItem(key, value);
  } else {
    window.localStorage.removeItem(key);
  }
}

function formatDateTime(value?: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function ProfileStat({ icon: Icon, label, value }: { icon: typeof Mail; label: string; value: string }) {
  return (
    <div className="profile-stat">
      <div className="profile-stat__icon">
        <Icon size={18} />
      </div>
      <div>
        <div className="profile-stat__label">{label}</div>
        <div className="profile-stat__value">{value}</div>
      </div>
    </div>
  );
}

const UserProfilePage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const { pushToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";

  const userQuery = useQuery<PortalUser>({
    queryKey: ["current-user-profile"],
    queryFn: fetchCurrentUser,
    initialData: getCachedUser() ?? undefined,
    staleTime: 60_000,
  });

  const user = userQuery.data ?? getCachedUser();
  const [profileMeta, setProfileMeta] = useState<LocalProfileMeta>(() => readLocalProfileMeta(user?.id));
  const [notificationPrefs, setNotificationPrefsState] = useState<NotificationPreferences>(() => getNotificationPreferences());
  const [avatar, setAvatar] = useState<string | null>(() => readStoredAvatar(user?.id));

  useEffect(() => {
    if (!user?.id) return;
    setProfileMeta(readLocalProfileMeta(user.id));
    setAvatar(readStoredAvatar(user.id));
  }, [user?.id]);

  const displayTitle = profileMeta.title || user?.position_title || user?.role || "Portal user";
  const fullName = user?.full_name || "User profile";
  const departmentName = user?.department_id || ctx.department || "Department not set";

  const accountMeta = useMemo(
    () => [
      { label: "Staff code", value: user?.staff_code || "Not assigned" },
      { label: "Department", value: departmentName },
      { label: "Role", value: user?.role || "Not assigned" },
      { label: "AMO", value: amoCode },
      { label: "Last sign in", value: formatDateTime(user?.last_login_at) },
      { label: "Account status", value: user?.is_active ? "Active" : "Disabled" },
    ],
    [amoCode, departmentName, user]
  );

  const handleAvatarSelection = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !user?.id) return;
    if (!file.type.startsWith("image/")) {
      pushToast({ title: "Unsupported image", message: "Choose a PNG, JPG, WEBP, or SVG image.", variant: "warning" });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const next = typeof reader.result === "string" ? reader.result : null;
      setAvatar(next);
      saveStoredAvatar(user.id, next);
      pushToast({ title: "Profile picture updated", message: "The avatar is stored in this browser until a backend media endpoint is wired.", variant: "success", sound: true });
    };
    reader.readAsDataURL(file);
  };

  const handleSaveProfileMeta = () => {
    if (!user?.id) return;
    saveLocalProfileMeta(user.id, profileMeta);
    pushToast({
      title: "Profile preferences saved",
      message: "Local profile notes and contact preferences were saved for this browser.",
      variant: "success",
      sound: true,
    });
  };

  const updatePreference = <K extends keyof NotificationPreferences>(key: K, value: NotificationPreferences[K]) => {
    const next = setNotificationPreferences({ [key]: value });
    setNotificationPrefsState(next);
    pushToast({
      title: "Notification preferences updated",
      message: "Your portal alerts were updated successfully.",
      variant: "success",
      sound: true,
      duration: 2600,
    });
  };

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={ctx.department ?? "planning"}>
      <div className="profile-page">
        <PageHeader
          eyebrow="Portal profile"
          title={fullName}
          subtitle="Professional account viewer with quick profile media, preferences, contact information, and session controls."
          breadcrumbs={[
            { label: amoCode, to: `/maintenance/${amoCode}/${ctx.department ?? "planning"}` },
            { label: "Profile" },
          ]}
          meta={<span className="profile-page__meta-badge">{displayTitle}</span>}
          actions={
            <>
              <Button variant="secondary" onClick={() => userQuery.refetch()}>
                <RefreshCw size={16} />
                Refresh profile
              </Button>
              <Button variant="secondary" onClick={() => navigate(-1)}>
                Back
              </Button>
            </>
          }
        />

        <div className="profile-page__grid profile-page__grid--hero">
          <SectionCard
            variant="hero"
            className="profile-hero-card"
            footer={
              <div className="profile-hero-card__footer-note">
                Profile image and the profile notes below are saved in this browser for now. Core account identity still comes from the authenticated user record.
              </div>
            }
          >
            <div className="profile-hero">
              <div className="profile-hero__avatar-block">
                <div className="profile-hero__avatar">
                  {avatar ? (
                    <img src={avatar} alt={fullName} className="profile-hero__avatar-image" />
                  ) : (
                    <span>{fullName.split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "U"}</span>
                  )}
                </div>
                <div className="profile-hero__avatar-actions">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="profile-hero__file-input"
                    onChange={handleAvatarSelection}
                  />
                  <Button variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()}>
                    <Camera size={16} />
                    Upload photo
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (!user?.id) return;
                      setAvatar(null);
                      saveStoredAvatar(user.id, null);
                    }}
                  >
                    Remove
                  </Button>
                </div>
              </div>

              <div className="profile-hero__content">
                <div>
                  <p className="profile-hero__eyebrow">Current account</p>
                  <h2 className="profile-hero__name">{fullName}</h2>
                  <p className="profile-hero__role">{displayTitle}</p>
                  <p className="profile-hero__description">
                    {profileMeta.bio || "Add a short bio, certification scope, or operational responsibilities to help supervisors and auditors understand this user at a glance."}
                  </p>
                </div>
                <div className="profile-hero__stats">
                  <ProfileStat icon={Mail} label="Email" value={user?.email || "Not available"} />
                  <ProfileStat icon={Phone} label="Phone" value={user?.phone || "Not available"} />
                  <ProfileStat icon={Building2} label="Department" value={departmentName} />
                  <ProfileStat icon={BadgeCheck} label="Authority" value={user?.regulatory_authority || "Not captured"} />
                </div>
              </div>
            </div>
          </SectionCard>
        </div>

        <div className="profile-page__grid">
          <SectionCard
            title="Professional overview"
            subtitle="Core employment and account information surfaced in a clean, audit-friendly layout."
            eyebrow="Identity"
            actions={<span className="profile-page__section-tag">Read only</span>}
          >
            <div className="profile-facts-grid">
              {accountMeta.map((item) => (
                <div key={item.label} className="profile-fact">
                  <span className="profile-fact__label">{item.label}</span>
                  <strong className="profile-fact__value">{item.value}</strong>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard
            title="Notifications and alert behavior"
            subtitle="Keep sounds, popups, and polling frequency consistent across the portal."
            eyebrow="Preferences"
            actions={<Bell size={16} />}
          >
            <div className="profile-preferences">
              <label className="profile-toggle-row">
                <span>
                  <strong>Audio alerts</strong>
                  <small>Play a chirp when attention-worthy portal notifications arrive.</small>
                </span>
                <input
                  type="checkbox"
                  checked={notificationPrefs.audioEnabled}
                  onChange={(event) => updatePreference("audioEnabled", event.target.checked)}
                />
              </label>
              <label className="profile-toggle-row">
                <span>
                  <strong>Desktop notifications</strong>
                  <small>Allow browser popups for alerts when the tab is not front-most.</small>
                </span>
                <input
                  type="checkbox"
                  checked={notificationPrefs.desktopEnabled}
                  onChange={(event) => updatePreference("desktopEnabled", event.target.checked)}
                />
              </label>
              <label className="profile-toggle-row">
                <span>
                  <strong>Evidence photo uploads</strong>
                  <small>Permit image uploads in evidence flows from this device.</small>
                </span>
                <input
                  type="checkbox"
                  checked={notificationPrefs.enablePhotoUploads}
                  onChange={(event) => updatePreference("enablePhotoUploads", event.target.checked)}
                />
              </label>
              <label className="profile-toggle-row">
                <span>
                  <strong>Evidence video uploads</strong>
                  <small>Permit video uploads in supported workflows from this device.</small>
                </span>
                <input
                  type="checkbox"
                  checked={notificationPrefs.enableVideoUploads}
                  onChange={(event) => updatePreference("enableVideoUploads", event.target.checked)}
                />
              </label>
              <label className="profile-inline-field">
                <span>Polling interval in seconds</span>
                <input
                  className="input"
                  type="number"
                  min={15}
                  max={600}
                  step={15}
                  value={notificationPrefs.pollIntervalSeconds}
                  onChange={(event) => updatePreference("pollIntervalSeconds", Number(event.target.value || 60))}
                />
              </label>
            </div>
          </SectionCard>

          <SectionCard
            title="Profile notes"
            subtitle="Local notes make the profile feel complete while a backend profile endpoint is still pending."
            eyebrow="Editable"
            actions={<UserSquare2 size={16} />}
            footer={
              <div className="profile-form__footer-actions">
                <Button variant="secondary" onClick={() => setProfileMeta(readLocalProfileMeta(user?.id))}>
                  Reset draft
                </Button>
                <Button onClick={handleSaveProfileMeta}>Save local profile notes</Button>
              </div>
            }
          >
            <div className="profile-form-grid">
              <label className="profile-inline-field">
                <span>Professional title</span>
                <input
                  className="input"
                  value={profileMeta.title}
                  onChange={(event) => setProfileMeta((prev) => ({ ...prev, title: event.target.value }))}
                  placeholder="e.g. Quality Auditor, Planning Engineer"
                />
              </label>
              <label className="profile-inline-field">
                <span>Office or base location</span>
                <input
                  className="input"
                  value={profileMeta.officeLocation}
                  onChange={(event) => setProfileMeta((prev) => ({ ...prev, officeLocation: event.target.value }))}
                  placeholder="e.g. Nairobi Hangar 2"
                />
              </label>
              <label className="profile-inline-field profile-inline-field--full">
                <span>Professional summary</span>
                <textarea
                  className="input profile-textarea"
                  rows={4}
                  value={profileMeta.bio}
                  onChange={(event) => setProfileMeta((prev) => ({ ...prev, bio: event.target.value }))}
                  placeholder="Summarize responsibilities, authorizations, or special competence areas."
                />
              </label>
              <label className="profile-inline-field">
                <span>Emergency contact name</span>
                <input
                  className="input"
                  value={profileMeta.emergencyName}
                  onChange={(event) => setProfileMeta((prev) => ({ ...prev, emergencyName: event.target.value }))}
                  placeholder="Contact name"
                />
              </label>
              <label className="profile-inline-field">
                <span>Emergency contact phone</span>
                <input
                  className="input"
                  value={profileMeta.emergencyPhone}
                  onChange={(event) => setProfileMeta((prev) => ({ ...prev, emergencyPhone: event.target.value }))}
                  placeholder="Phone number"
                />
              </label>
            </div>
          </SectionCard>

          <SectionCard
            title="Licensing and compliance identifiers"
            subtitle="Useful for authorization reviews and inspection preparation."
            eyebrow="Credentials"
            actions={<Shield size={16} />}
          >
            <div className="profile-facts-grid">
              <div className="profile-fact">
                <span className="profile-fact__label">Licence number</span>
                <strong className="profile-fact__value">{user?.licence_number || "Not recorded"}</strong>
              </div>
              <div className="profile-fact">
                <span className="profile-fact__label">State or country</span>
                <strong className="profile-fact__value">{user?.licence_state_or_country || "Not recorded"}</strong>
              </div>
              <div className="profile-fact">
                <span className="profile-fact__label">Licence expiry</span>
                <strong className="profile-fact__value">{user?.licence_expires_on || "Not recorded"}</strong>
              </div>
              <div className="profile-fact">
                <span className="profile-fact__label">Must change password</span>
                <strong className="profile-fact__value">{user?.must_change_password ? "Yes" : "No"}</strong>
              </div>
              <div className="profile-fact">
                <span className="profile-fact__label">Last sign-in IP</span>
                <strong className="profile-fact__value">{user?.last_login_ip || "Not recorded"}</strong>
              </div>
              <div className="profile-fact">
                <span className="profile-fact__label">Office location note</span>
                <strong className="profile-fact__value">{profileMeta.officeLocation || "Not set"}</strong>
              </div>
            </div>
          </SectionCard>

          <SectionCard
            title="Security actions"
            subtitle="Fast actions for session hygiene and credential support."
            eyebrow="Access"
          >
            <div className="profile-security-actions">
              <Button variant="secondary" onClick={() => navigate("/reset-password")}>Reset password</Button>
              <Button variant="ghost" onClick={() => navigate(`/maintenance/${amoCode}/${ctx.department ?? "planning"}/tasks`)}>
                Open my tasks
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  endSession("manual");
                  navigate(`/maintenance/${amoCode}/login`, { replace: true });
                }}
              >
                Sign out
              </Button>
            </div>
          </SectionCard>
        </div>
      </div>
    </DepartmentLayout>
  );
};

export default UserProfilePage;
