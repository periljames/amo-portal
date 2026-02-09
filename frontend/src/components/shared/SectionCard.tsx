import React from "react";

type SectionCardProps = {
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
};

const SectionCard: React.FC<SectionCardProps> = ({
  title,
  subtitle,
  actions,
  children,
  className,
}) => {
  return (
    <div className={`section-card${className ? ` ${className}` : ""}`}>
      {(title || subtitle || actions) && (
        <div className="section-card__header">
          <div>
            {title && <h3 className="section-card__title">{title}</h3>}
            {subtitle && <p className="section-card__subtitle">{subtitle}</p>}
          </div>
          {actions && <div>{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
};

export default SectionCard;
