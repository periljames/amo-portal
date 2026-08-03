import React, { useEffect, useRef, useState } from "react";

import { getCachedUser } from "../../services/auth";
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
  const currentUserId = getCachedUser()?.id || "anonymous";
  const [profileRevision, setProfileRevision] = useState(0);
  const signatureRef = useRef(stateSignature(readCachedAdminProfileState(props.amoCode)));

  useEffect(() => {
    signatureRef.current = stateSignature(readCachedAdminProfileState(props.amoCode));
    return onAdminProfileChange(({ amoCode, userId, state }) => {
      if (userId !== currentUserId) return;
      if (amoCode.trim().toLowerCase() !== props.amoCode.trim().toLowerCase()) return;
      const nextSignature = stateSignature(state);
      if (nextSignature === signatureRef.current) return;
      signatureRef.current = nextSignature;
      setProfileRevision((value) => value + 1);
    });
  }, [currentUserId, props.amoCode]);

  return (
    <DepartmentLayoutImpl
      key={`${props.amoCode}:${currentUserId}:${profileRevision}`}
      {...props}
    />
  );
};

export default DepartmentLayout;
