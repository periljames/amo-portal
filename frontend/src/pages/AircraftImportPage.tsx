// frontend/src/pages/AircraftImportPage.tsx
import React, { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const AircraftImportPage: React.FC = () => {
  const [aircraftFile, setAircraftFile] = useState<File | null>(null);
  const [componentsFile, setComponentsFile] = useState<File | null>(null);
  const [componentAircraftSerial, setComponentAircraftSerial] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAircraftFileChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setAircraftFile(e.target.files?.[0] ?? null);
  };

  const handleComponentsFileChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setComponentsFile(e.target.files?.[0] ?? null);
  };

  const uploadAircraft = async () => {
    if (!aircraftFile) {
      setMessage("Select an aircraft file first.");
      return;
    }
    setLoading(true);
    setMessage(null);

    const formData = new FormData();
    formData.append("file", aircraftFile);

    try {
      const res = await fetch(`${API_BASE}/aircraft/import`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Import failed");
      }
      setMessage(
        `Aircraft import OK. Created: ${data.created}, Updated: ${data.updated}`
      );
    } catch (err: any) {
      setMessage(err.message ?? "Error importing aircraft.");
    } finally {
      setLoading(false);
    }
  };

  const uploadComponents = async () => {
    if (!componentAircraftSerial.trim()) {
      setMessage("Enter the aircraft serial number for components.");
      return;
    }
    if (!componentsFile) {
      setMessage("Select a component file first.");
      return;
    }
    setLoading(true);
    setMessage(null);

    const formData = new FormData();
    formData.append("file", componentsFile);

    try {
      const res = await fetch(
        `${API_BASE}/aircraft/${encodeURIComponent(
          componentAircraftSerial.trim()
        )}/components/import`,
        {
          method: "POST",
          body: formData,
        }
      );

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Component import failed");
      }
      setMessage(
        `Components import OK for aircraft ${data.aircraft_serial_number}. ` +
          `New components: ${data.components_created}`
      );
    } catch (err: any) {
      setMessage(err.message ?? "Error importing components.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 flex flex-col items-center py-10">
      <div className="w-full max-w-3xl space-y-8">
        <h1 className="text-2xl font-semibold">Aircraft Loader / Setup</h1>

        {/* AIRCRAFT MASTER IMPORT */}
        <section className="bg-slate-900 rounded-2xl p-6 shadow">
          <h2 className="text-lg font-semibold mb-2">
            1. Import Aircraft Master List
          </h2>
          <p className="text-sm text-slate-300 mb-4">
            Upload a CSV or Excel file containing all aircraft
            (serial, registration, type, model, base, hours, cycles).
          </p>

          <input
            type="file"
            accept=".csv,.txt,.xlsx,.xlsm,.xls,.pdf"
            onChange={handleAircraftFileChange}
            className="block mb-3"
          />

          <button
            onClick={uploadAircraft}
            disabled={loading}
            className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50"
          >
            {loading ? "Uploading..." : "Upload Aircraft File"}
          </button>
        </section>

        {/* COMPONENT IMPORT */}
        <section className="bg-slate-900 rounded-2xl p-6 shadow">
          <h2 className="text-lg font-semibold mb-2">
            2. Import Components for One Aircraft
          </h2>
          <p className="text-sm text-slate-300 mb-4">
            Upload CSV/Excel with component positions (e.g. L ENGINE, R ENGINE,
            APU), part and serial numbers, installed values, etc.
          </p>

          <div className="mb-3">
            <label className="block text-sm mb-1">
              Aircraft Serial Number (e.g. 574, 510, 331)
            </label>
            <input
              type="text"
              value={componentAircraftSerial}
              onChange={(e) => setComponentAircraftSerial(e.target.value)}
              className="w-full rounded-xl px-3 py-2 bg-slate-950 border border-slate-700"
            />
          </div>

          <input
            type="file"
            accept=".csv,.txt,.xlsx,.xlsm,.xls,.pdf"
            onChange={handleComponentsFileChange}
            className="block mb-3"
          />

          <button
            onClick={uploadComponents}
            disabled={loading}
            className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-50"
          >
            {loading ? "Uploading..." : "Upload Components File"}
          </button>
        </section>

        {message && (
          <div className="mt-4 text-sm bg-slate-900 border border-slate-700 rounded-2xl p-3">
            {message}
          </div>
        )}
      </div>
    </div>
  );
};

export default AircraftImportPage;
