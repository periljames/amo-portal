import React from "react";

type SectionCardVariant = "default" | "hero" | "subtle" | "attention";

type SectionCardProps = {
  title?: string;
  subtitle?: string;
  eyebrow?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  footer?: React.ReactNode;
  variant?: SectionCardVariant;
};

const SectionCard: React.FC<SectionCardProps> = ({
  title,
  subtitle,
  eyebrow,
  actions,
  children,
  className,
  footer,
  variant = "default",
}) => {
  return (
    <section className={`section-card section-card--${variant}${className ? ` ${className}` : ""}`}>
      {(eyebrow || title || subtitle || actions) && (
        <header className="section-card__header">
          <div className="section-card__header-copy">
            {eyebrow ? <p className="section-card__eyebrow">{eyebrow}</p> : null}
            {title ? <h3 className="section-card__title">{title}</h3> : null}
            {subtitle ? <p className="section-card__subtitle">{subtitle}</p> : null}
          </div>
          {actions ? <div className="section-card__actions">{actions}</div> : null}
        </header>
      )}
      <div className="section-card__body">{children}</div>
      {footer ? <footer className="section-card__footer">{footer}</footer> : null}
    </section>
  );
};

export default SectionCard;
