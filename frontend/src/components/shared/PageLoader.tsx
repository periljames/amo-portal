import React, { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { useGlobalLoadingCount } from "../../services/loading";

type PageLoaderProps = {
  fullscreen?: boolean;
  label?: string;
};

export const PageLoader: React.FC<PageLoaderProps> = ({ fullscreen = false, label = "Loading" }) => {
  return (
    <div className={`page-loader${fullscreen ? " page-loader--fullscreen" : ""}`} role="status" aria-live="polite">
      <div className="page-loader__card">
        <div className="page-loader__spinner" aria-hidden="true">
          <LoaderCircle size={22} />
        </div>
        <div className="page-loader__content">
          <div className="page-loader__title">{label}</div>
          <div className="page-loader__subtitle">Please wait while the portal catches up.</div>
        </div>
      </div>
    </div>
  );
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

  return (
    <>
      <div className={`global-loading-bar${count > 0 ? " global-loading-bar--active" : ""}`} aria-hidden="true">
        <span className="global-loading-bar__line" />
      </div>
      {visible ? <PageLoader label="Loading workspace" /> : null}
    </>
  );
};

export default PageLoader;
