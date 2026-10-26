import React, { useEffect, useState } from "react";
import WorkspaceLoading from "./WorkspaceLoading";
import { useGlobalLoadingCount } from "../../services/loading";

type PageLoaderProps = {
  fullscreen?: boolean;
  label?: string;
};

export const PageLoader: React.FC<PageLoaderProps> = ({ fullscreen = false, label = "Loading" }) => {
  return <div className={fullscreen ? "page-loader--fullscreen" : undefined}><WorkspaceLoading label={label} /></div>;
};

export const GlobalLoadingOverlay: React.FC = () => {
  const count = useGlobalLoadingCount();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (count > 0) {
      const timer = window.setTimeout(() => setVisible(true), 140);
      return () => window.clearTimeout(timer);
    }
    setVisible(false);
    return undefined;
  }, [count]);

  // Global requests must never replace usable page content with a workspace splash.
  return <div className={`global-loading-bar${visible ? " global-loading-bar--active" : ""}`} role={visible ? "status" : undefined} aria-label={visible ? "Updating" : undefined} aria-hidden={!visible}>
    <span className="global-loading-bar__line" />
  </div>;
};

export default PageLoader;
