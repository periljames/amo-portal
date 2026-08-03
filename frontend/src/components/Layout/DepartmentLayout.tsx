import React, { useEffect, useRef, useState } from "react";

import {
  onAdminProfileChange,
  readCachedAdminProfileState,
  type AdminProfileState,
} from "../../services/adminProfileMode";
import DepartmentLayoutImpl from "./DepartmentLayoutImpl";

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
  showPollingErrorBanner?: boolean;
};

function stateSignature(state: AdminProfileState | null): string {
  return JSON.stringify([
    Boolean(state?.eligible),
    Boolean(state?.active),
    state?.session_id || null,
    state?.expires_at || null,
    state?.grant_type || null,
  ]);
}

const DepartmentLayout: React.FC<Props> = (props) => {
  const [profileRevision, setProfileRevision] = useState(0);
  const signatureRef = useRef(stateSignature(readCachedAdminProfileState(props.amoCode)));

  useEffect(() => {
    signatureRef.current = stateSignature(readCachedAdminProfileState(props.amoCode));
    return onAdminProfileChange(({ amoCode, state }) => {
      if (amoCode.trim().toLowerCase() !== props.amoCode.trim().toLowerCase()) return;
      const nextSignature = stateSignature(state);
      if (nextSignature === signatureRef.current) return;
      signatureRef.current = nextSignature;
      setProfileRevision((value) => value + 1);
    });
  }, [props.amoCode]);

  return (
    <DepartmentLayoutImpl
      key={`${props.amoCode}:${profileRevision}`}
      {...props}
    />
  );
};

export default DepartmentLayout;
