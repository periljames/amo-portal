import React from "react";

type DrawerProps = {
  title: string;
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
};

const Drawer: React.FC<DrawerProps> = ({ title, isOpen, onClose, children }) => {
  if (!isOpen) return null;
  return (
    <div className="drawer-overlay" role="dialog" aria-modal="true">
      <div className="drawer">
        <div className="drawer__header">
          <h3 className="drawer__title">{title}</h3>
          <button type="button" className="drawer__close" onClick={onClose}>
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

export default Drawer;
