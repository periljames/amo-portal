import { useLocation } from "react-router-dom";

import AdminCrsAssetsPage from "./AdminCrsAssetsPage";
import AdminOperatingStructurePage from "./AdminOperatingStructurePage";

export default function AdminAmoAssetsPage() {
  const location = useLocation();
  const section = new URLSearchParams(location.search).get("section");

  if (section === "operating-structure") {
    return <AdminOperatingStructurePage />;
  }

  return <AdminCrsAssetsPage />;
}
