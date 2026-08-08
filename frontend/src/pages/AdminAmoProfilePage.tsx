import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel } from "../components/UI/Admin";
import { getCachedUser } from "../services/auth";
import {
  listAdminAmos,
  setAdminContext,
  setActiveAmoId as storeActiveAmoId,
  updateAdminAmo,
  LS_ACTIVE_AMO_ID,
  type AdminAmoRead,
} from "../services/adminUsers";

type UrlParams = { amoCode?: string };

type AmoProfileState = {
  name: string;
  icaoCode: string;
  country: string;
  contactEmail: string;
  contactPhone: string;
  timeZone: string;
  isDemo: boolean;
  isActive: boolean;
};

const emptyProfile = (): AmoProfileState => ({
  name: "",
  icaoCode: "",
  country: "",
  contactEmail: "",
  contactPhone: "",
  timeZone: "",
  isDemo: false,
  isActive: true,
});

const AdminAmoProfilePage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const currentUser = useMemo(() => getCachedUser(), []);
  const isSuperuser = !!currentUser?.is_superuser;

  const [amos, setAmos] = useState<AdminAmoRead[]>([]);
  const [amoLoading, setAmoLoading] = useState(false);
  const [amoError, setAmoError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState<AmoProfileState>(emptyProfile);
  const [activeAmoId, setActiveAmoId] = useState<string | null>(() => {
    const value = localStorage.getItem(LS_ACTIVE_AMO_ID);
    return value?.trim() || null;
  });

  const selectedAmo = useMemo(
    () => amos.find((amo) => amo.id === activeAmoId) || null,
    [amos, activeAmoId],
  );

  useEffect(() => {
    if (!currentUser) return;
    if (isSuperuser) return;
    if (amoCode) {
      navigate(`/maintenance/${amoCode}/admin/overview`, { replace: true });
      return;
    }
    navigate("/login", { replace: true });
  }, [currentUser, isSuperuser, amoCode, navigate]);

  useEffect(() => {
    if (!isSuperuser) return;
    let cancelled = false;
    const load = async () => {
      setAmoLoading(true);
      setAmoError(null);
      try {
        const rows = await listAdminAmos();
        if (cancelled) return;
        setAmos(rows);
        const stored = localStorage.getItem(LS_ACTIVE_AMO_ID)?.trim() || null;
        const storedValid = !!stored && rows.some((amo) => amo.id === stored);
        const preferred = currentUser?.amo_id && rows.some((amo) => amo.id === currentUser.amo_id)
          ? currentUser.amo_id
          : null;
        const next = storedValid ? stored : preferred || rows[0]?.id || null;
        if (next) {
          storeActiveAmoId(next);
          setActiveAmoId(next);
        }
      } catch (caught) {
        if (!cancelled) setAmoError(caught instanceof Error ? caught.message : "Could not load AMOs.");
      } finally {
        if (!cancelled) setAmoLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [isSuperuser, currentUser?.amo_id]);

  useEffect(() => {
    if (!selectedAmo) {
      setProfile(emptyProfile());
      return;
    }
    setProfile({
      name: selectedAmo.name || "",
      icaoCode: selectedAmo.icao_code || "",
      country: selectedAmo.country || "",
      contactEmail: selectedAmo.contact_email || "",
      contactPhone: selectedAmo.contact_phone || "",
      timeZone: selectedAmo.time_zone || "",
      isDemo: !!selectedAmo.is_demo,
      isActive: !!selectedAmo.is_active,
    });
  }, [selectedAmo]);

  useEffect(() => {
    if (!isSuperuser || !activeAmoId) return;
    void setAdminContext({ active_amo_id: activeAmoId }).catch((caught) => {
      setActionError(caught instanceof Error ? caught.message : "Failed to update active AMO context.");
    });
  }, [activeAmoId, isSuperuser]);

  if (currentUser && !isSuperuser) return null;

  const handleAmoChange = (nextAmoId: string) => {
    const id = nextAmoId.trim();
    if (!id) return;
    setActionError(null);
    setActionSuccess(null);
    setActiveAmoId(id);
    storeActiveAmoId(id);
  };

  const handleProfileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, checked, type } = event.target;
    setProfile((current) => ({ ...current, [name]: type === "checkbox" ? checked : value }));
  };

  const saveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedAmo) {
      setActionError("Select an AMO to edit.");
      return;
    }
    setSaving(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      await updateAdminAmo(selectedAmo.id, {
        name: profile.name.trim() || null,
        icao_code: profile.icaoCode.trim() || null,
        country: profile.country.trim() || null,
        contact_email: profile.contactEmail.trim() || null,
        contact_phone: profile.contactPhone.trim() || null,
        time_zone: profile.timeZone.trim() || null,
        is_demo: profile.isDemo,
        is_active: profile.isActive,
      });
      setActionSuccess(`Updated AMO ${selectedAmo.amo_code}.`);
      setAmos(await listAdminAmos());
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Failed to update AMO profile.");
    } finally {
      setSaving(false);
    }
  };

  const billingPath = `/maintenance/${amoCode ?? selectedAmo?.amo_code ?? "UNKNOWN"}/admin/billing`;

  return (
    <DepartmentLayout amoCode={amoCode ?? "UNKNOWN"} activeDepartment="admin-amos">
      <div className="admin-page">
        <PageHeader
          title="AMO Profile"
          subtitle="Manage tenant identity and administrative status. Commercial terms and subscriptions are managed only in Billing."
          actions={<Button type="button" size="sm" variant="secondary" onClick={() => navigate(`/maintenance/${amoCode}/admin/amos`)}>Back to AMO list</Button>}
        />

        {actionError && <InlineAlert tone="danger" title="AMO update failed"><span>{actionError}</span></InlineAlert>}
        {actionSuccess && <InlineAlert tone="success" title="AMO updated"><span>{actionSuccess}</span></InlineAlert>}

        <div className="admin-page__grid">
          <Panel title="Select AMO" subtitle="Choose the tenant whose administrative profile you want to manage.">
            {amoLoading && <p>Loading AMOs…</p>}
            {amoError && <InlineAlert tone="danger" title="Error"><span>{amoError}</span></InlineAlert>}
            {!amoLoading && !amoError && (
              <div className="form-row">
                <label htmlFor="amoSelect">Active AMO</label>
                <select id="amoSelect" value={activeAmoId ?? ""} onChange={(event) => handleAmoChange(event.target.value)} disabled={amos.length === 0}>
                  {amos.map((amo) => <option key={amo.id} value={amo.id}>{amo.amo_code} — {amo.name}</option>)}
                </select>
              </div>
            )}
          </Panel>

          <Panel title="Commercial control" subtitle="There is one authoritative surface for module contracts, negotiated pricing, invoices and collections.">
            {!selectedAmo ? <p className="admin-muted">Select an AMO first.</p> : (
              <>
                <p className="admin-muted">Trial activation, SKU purchase and direct subscription mutation have been removed from this profile page. Use Billing so every commercial change follows the same invoice, payment-verification and audit controls.</p>
                <Button type="button" onClick={() => navigate(billingPath)}>Open Billing & subscriptions</Button>
              </>
            )}
          </Panel>
        </div>

        <div style={{ height: 18 }} />
        <Panel title="AMO profile" subtitle="Update tenant identity, contact information and administrative activation state.">
          {!selectedAmo ? <p className="admin-muted">Select an AMO to view its profile.</p> : (
            <form className="form-grid" onSubmit={saveProfile}>
              <div className="form-row"><label>AMO code</label><input type="text" value={selectedAmo.amo_code} disabled /></div>
              <div className="form-row"><label>Login slug</label><input type="text" value={selectedAmo.login_slug} disabled /></div>
              <div className="form-row"><label htmlFor="profileName">AMO name</label><input id="profileName" name="name" value={profile.name} onChange={handleProfileChange} required /></div>
              <div className="form-row"><label htmlFor="profileIcao">ICAO code</label><input id="profileIcao" name="icaoCode" value={profile.icaoCode} onChange={handleProfileChange} /></div>
              <div className="form-row"><label htmlFor="profileCountry">Country</label><input id="profileCountry" name="country" value={profile.country} onChange={handleProfileChange} /></div>
              <div className="form-row"><label htmlFor="profileEmail">Contact email</label><input id="profileEmail" name="contactEmail" type="email" value={profile.contactEmail} onChange={handleProfileChange} /></div>
              <div className="form-row"><label htmlFor="profilePhone">Contact phone</label><input id="profilePhone" name="contactPhone" type="tel" value={profile.contactPhone} onChange={handleProfileChange} /></div>
              <div className="form-row"><label htmlFor="profileTimeZone">Time zone</label><input id="profileTimeZone" name="timeZone" value={profile.timeZone} onChange={handleProfileChange} placeholder="Africa/Nairobi" /></div>
              <div className="form-row"><label htmlFor="profileDemo"><input id="profileDemo" name="isDemo" type="checkbox" checked={profile.isDemo} onChange={handleProfileChange} /><span style={{ marginLeft: 8 }}>Demo tenant</span></label></div>
              <div className="form-row"><label htmlFor="profileActive"><input id="profileActive" name="isActive" type="checkbox" checked={profile.isActive} onChange={handleProfileChange} /><span style={{ marginLeft: 8 }}>Administratively active</span></label></div>
              <div className="form-actions"><Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save AMO profile"}</Button></div>
            </form>
          )}
        </Panel>
      </div>
    </DepartmentLayout>
  );
};

export default AdminAmoProfilePage;
