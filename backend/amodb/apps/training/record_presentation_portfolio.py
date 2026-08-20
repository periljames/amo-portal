from __future__ import annotations

import html
import mimetypes
from typing import Any, Optional
from urllib.parse import quote

from fastapi import Depends, Response, status
from fastapi.responses import FileResponse, HTMLResponse

from amodb import storage
from ..accounts import models as accounts_models
from . import models as training_models
from . import record_presentation as _base
from . import record_presentation_glass as _glass
from . import record_presentation_table as _table


_PORTFOLIO_SCRIPT = r"""
(() => {
  'use strict';

  const root = document.querySelector('[data-training-portfolio]');
  if (!root) return;

  const tabButtons = Array.from(root.querySelectorAll('[data-tab-button]'));
  const tabPanels = Array.from(root.querySelectorAll('[data-tab-panel]'));

  const activateTab = (name, moveFocus = false) => {
    tabButtons.forEach((button) => {
      const active = button.dataset.tabButton === name;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
      button.tabIndex = active ? 0 : -1;
      if (active && moveFocus) button.focus({ preventScroll: true });
    });
    tabPanels.forEach((panel) => {
      panel.hidden = panel.dataset.tabPanel !== name;
    });
  };

  tabButtons.forEach((button, index) => {
    button.addEventListener('click', () => activateTab(button.dataset.tabButton || 'overview'));
    button.addEventListener('keydown', (event) => {
      if (!['ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      let target = index;
      if (event.key === 'Home') target = 0;
      else if (event.key === 'End') target = tabButtons.length - 1;
      else if (event.key === 'ArrowDown' || event.key === 'ArrowRight') target = (index + 1) % tabButtons.length;
      else target = (index - 1 + tabButtons.length) % tabButtons.length;
      activateTab(tabButtons[target].dataset.tabButton || 'overview', true);
    });
  });

  const table = root.querySelector('[data-paginated-table]');
  if (table) {
    const rows = Array.from(table.querySelectorAll('[data-training-row]'));
    const pageSize = Math.max(1, Number(table.dataset.pageSize || 10));
    const previous = root.querySelector('[data-page-prev]');
    const next = root.querySelector('[data-page-next]');
    const summary = root.querySelector('[data-page-summary]');
    const numbers = root.querySelector('[data-page-numbers]');
    const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
    let page = 1;

    const render = () => {
      const start = (page - 1) * pageSize;
      const end = Math.min(rows.length, start + pageSize);
      rows.forEach((row, rowIndex) => {
        row.hidden = rowIndex < start || rowIndex >= end;
      });
      if (summary) {
        summary.textContent = rows.length ? `Showing ${start + 1}\u2013${end} of ${rows.length}` : 'No training entries';
      }
      if (previous) previous.disabled = page <= 1;
      if (next) next.disabled = page >= pageCount || rows.length === 0;
      if (numbers) {
        numbers.replaceChildren();
        for (let index = 1; index <= pageCount; index += 1) {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'page-number';
          button.textContent = String(index);
          button.setAttribute('aria-label', `Training page ${index}`);
          button.setAttribute('aria-current', index === page ? 'page' : 'false');
          button.classList.toggle('is-active', index === page);
          button.addEventListener('click', () => {
            page = index;
            render();
          });
          numbers.appendChild(button);
        }
      }
    };

    previous?.addEventListener('click', () => {
      if (page > 1) {
        page -= 1;
        render();
      }
    });
    next?.addEventListener('click', () => {
      if (page < pageCount) {
        page += 1;
        render();
      }
    });
    render();
  }

  const logo = root.querySelector('[data-amo-logo]');
  const logoFallback = root.querySelector('[data-amo-logo-fallback]');
  if (logo && logoFallback) {
    const fallback = () => {
      logo.hidden = true;
      logoFallback.hidden = false;
    };
    logo.addEventListener('error', fallback, { once: true });
    if (logo.complete && logo.naturalWidth === 0) fallback();
  }

  const photo = root.querySelector('[data-person-photo]');
  const photoFallback = root.querySelector('[data-person-photo-fallback]');
  if (photo && photoFallback) {
    const fallback = () => {
      photo.hidden = true;
      photoFallback.hidden = false;
    };
    photo.addEventListener('error', fallback, { once: true });
    if (photo.complete && photo.naturalWidth === 0) fallback();
  }
})();
"""


_PORTFOLIO_CSS = r"""
:root {
  --font-ui: "Avenir Next", "SF Pro Text", -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Segoe UI", sans-serif;
  --font-display: "Iowan Old Style", Baskerville, "Palatino Linotype", "Book Antiqua", Georgia, serif;
}
body {
  font-family: var(--font-ui);
  font-weight: 450;
  letter-spacing: -.006em;
}
.report { width: min(1240px, 100%); }
.portfolio-header {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) auto;
  align-items: center;
  gap: 24px;
  min-height: 132px;
  padding: 16px 18px;
  border-radius: 34px;
}
.amo-logo-frame {
  width: 220px;
  height: 100px;
  display: grid;
  place-items: center;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.76);
  border-radius: 26px;
  background: rgba(255,255,255,.62);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.88), 0 10px 30px rgba(31,31,41,.05);
}
.amo-logo-frame img {
  width: 100%;
  height: 100%;
  display: block;
  padding: 10px 14px;
  object-fit: contain;
  image-rendering: auto;
}
.amo-logo-fallback {
  font-family: var(--font-display);
  color: var(--accent);
  font-size: 31px;
  font-weight: 700;
  letter-spacing: -.04em;
}
.brand-copy h1 {
  font-family: var(--font-ui);
  font-size: clamp(24px, 3.1vw, 37px);
  font-weight: 680;
  letter-spacing: -.045em;
}
.brand-copy p {
  margin-top: 8px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: .015em;
}
.identity-card {
  display: grid;
  grid-template-columns: auto minmax(0,1fr) auto;
  align-items: center;
  gap: 21px;
  margin-top: 18px;
  padding: 22px 24px;
  border-radius: 30px;
}
.person-photo {
  width: 86px;
  height: 86px;
  display: grid;
  place-items: center;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.78);
  border-radius: 26px;
  background: linear-gradient(145deg, color-mix(in srgb,var(--accent) 58%,white), var(--accent));
  color: white;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.24), 0 13px 28px rgba(30,30,40,.09);
}
.person-photo img { width: 100%; height: 100%; display: block; object-fit: cover; }
.person-photo-fallback { font-size: 28px; font-weight: 650; letter-spacing: -.04em; }
.identity-copy h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(30px, 4vw, 43px);
  line-height: 1;
  font-weight: 600;
  letter-spacing: -.035em;
}
.identity-copy .role {
  margin: 8px 0 0;
  color: var(--secondary);
  font-size: 13px;
  font-weight: 540;
  letter-spacing: .035em;
  text-transform: uppercase;
}
.identity-copy .licence {
  display: block;
  margin-top: 7px;
  color: var(--tertiary);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.identity-inactive {
  display: inline-flex;
  margin-top: 8px;
  padding: 5px 8px;
  border-radius: 999px;
  background: rgba(118,118,128,.10);
  color: var(--secondary);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
}
.portfolio-layout {
  display: grid;
  grid-template-columns: 210px minmax(0,1fr);
  gap: 18px;
  margin-top: 18px;
  align-items: start;
}
.portfolio-rail {
  position: sticky;
  top: 18px;
  padding: 10px;
  border-radius: 26px;
}
.portfolio-rail-title {
  padding: 9px 10px 11px;
  color: var(--tertiary);
  font-size: 9px;
  font-weight: 760;
  letter-spacing: .10em;
  text-transform: uppercase;
}
.portfolio-tab {
  position: relative;
  width: 100%;
  min-height: 52px;
  display: grid;
  grid-template-columns: 28px minmax(0,1fr);
  align-items: center;
  gap: 9px;
  margin: 2px 0;
  padding: 9px 10px;
  border: 0;
  border-radius: 16px;
  background: transparent;
  color: var(--secondary);
  text-align: left;
  cursor: pointer;
  transition: background .15s ease, color .15s ease, transform .12s ease;
}
.portfolio-tab:hover { background: rgba(255,255,255,.34); color: var(--label); }
.portfolio-tab:active { transform: scale(.985); }
.portfolio-tab.is-active {
  background: rgba(255,255,255,.69);
  color: var(--label);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.88), 0 8px 22px rgba(35,35,45,.055);
}
.portfolio-tab.is-active::before {
  position: absolute;
  left: 3px;
  top: 14px;
  bottom: 14px;
  width: 3px;
  content: "";
  border-radius: 999px;
  background: var(--accent);
}
.portfolio-tab svg {
  width: 18px;
  height: 18px;
  justify-self: center;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.portfolio-tab strong { display: block; font-size: 12px; font-weight: 650; letter-spacing: -.01em; }
.portfolio-tab small { display: block; margin-top: 2px; color: var(--tertiary); font-size: 9px; font-weight: 500; }
.portfolio-panels { min-width: 0; }
.portfolio-panel { min-width: 0; }
.portfolio-panel[hidden] { display: none; }
.panel-heading {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 18px;
  margin: 1px 4px 12px;
}
.panel-heading h3 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 27px;
  line-height: 1.05;
  font-weight: 600;
  letter-spacing: -.025em;
}
.panel-heading p { margin: 5px 0 0; color: var(--secondary); font-size: 11px; }
.overview-grid {
  display: grid;
  grid-template-columns: minmax(0,1.25fr) minmax(280px,.75fr);
  gap: 14px;
}
.standing-card, .next-due-card, .metric-card, .certificate-list, .history-list-card { border-radius: 24px; }
.standing-card {
  min-height: 186px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.standing-label { color: var(--tertiary); font-size: 9px; font-weight: 760; letter-spacing: .10em; text-transform: uppercase; }
.standing-card strong {
  display: block;
  margin-top: 8px;
  font-family: var(--font-display);
  font-size: clamp(37px,5vw,55px);
  line-height: .95;
  font-weight: 600;
  letter-spacing: -.045em;
}
.standing-card p { max-width: 34rem; margin: 10px 0 0; color: var(--secondary); font-size: 12px; }
.metric-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 9px; margin-top: 20px; }
.metric-card { padding: 13px 14px; background: rgba(118,118,128,.055); border: 1px solid rgba(255,255,255,.5); }
.metric-card b { display: block; font-size: 23px; line-height: 1; font-weight: 650; font-variant-numeric: tabular-nums; }
.metric-card span { display: block; margin-top: 5px; color: var(--secondary); font-size: 9px; font-weight: 650; letter-spacing: .045em; text-transform: uppercase; }
.next-due-card { min-height: 186px; padding: 24px; }
.next-due-card .date {
  display: block;
  margin-top: 18px;
  font-family: var(--font-display);
  font-size: 31px;
  line-height: 1;
  font-weight: 600;
  letter-spacing: -.03em;
  font-variant-numeric: tabular-nums;
}
.next-due-card .course { display: block; margin-top: 11px; font-size: 13px; font-weight: 650; }
.next-due-card .support { display: block; margin-top: 6px; color: var(--secondary); font-size: 10px; }
.record-shell { border-radius: 24px; }
.record-table thead th { padding-top: 15px; padding-bottom: 12px; font-family: var(--font-ui); }
.record-row td { padding-top: 19px; padding-bottom: 19px; }
.course-title { font-family: var(--font-ui); font-size: 13px; font-weight: 620; }
.record-date { font-family: var(--font-ui); font-size: 12px; font-weight: 560; }
.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 10px;
  padding: 0 4px;
}
.page-summary { color: var(--tertiary); font-size: 10px; font-variant-numeric: tabular-nums; }
.page-controls { display: flex; align-items: center; gap: 6px; }
.page-nav, .page-number {
  min-width: 34px;
  height: 34px;
  display: inline-grid;
  place-items: center;
  border: 1px solid rgba(255,255,255,.60);
  border-radius: 11px;
  background: rgba(255,255,255,.40);
  color: var(--secondary);
  font-size: 10px;
  font-weight: 650;
  cursor: pointer;
}
.page-nav:disabled { opacity: .35; cursor: default; }
.page-number.is-active { background: rgba(255,255,255,.78); color: var(--label); box-shadow: 0 5px 14px rgba(35,35,45,.05); }
.page-numbers { display: flex; gap: 5px; }
.certificate-list, .history-list-card { overflow: hidden; }
.certificate-row, .history-row {
  display: grid;
  grid-template-columns: minmax(0,1fr) 150px auto;
  align-items: center;
  gap: 16px;
  padding: 16px 18px;
}
.certificate-row + .certificate-row, .history-row + .history-row { border-top: 1px solid var(--separator); }
.certificate-row h4, .history-row h4 { margin: 0; font-size: 12px; font-weight: 630; }
.certificate-row p, .history-row p { margin: 4px 0 0; color: var(--secondary); font-size: 9px; }
.certificate-row time, .history-row time { color: var(--secondary); font-size: 11px; font-variant-numeric: tabular-nums; }
.certificate-open {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 10px;
  border: 1px solid rgba(0,122,255,.13);
  border-radius: 12px;
  background: rgba(0,122,255,.075);
  color: var(--blue);
  font-size: 10px;
  font-weight: 650;
  cursor: pointer;
}
.certificate-open svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.empty-portfolio { padding: 34px 24px; text-align: center; color: var(--secondary); font-family: var(--font-display); font-size: 20px; }
.legend { margin: 10px 4px 0; }
@media (max-width: 900px) {
  .portfolio-header { grid-template-columns: 170px minmax(0,1fr); }
  .amo-logo-frame { width: 170px; height: 88px; }
  .action-dock { grid-column: 1 / -1; width: 100%; justify-content: flex-end; }
  .portfolio-layout { grid-template-columns: 1fr; }
  .portfolio-rail {
    position: static;
    display: flex;
    gap: 5px;
    overflow-x: auto;
    padding: 6px;
    scrollbar-width: none;
  }
  .portfolio-rail::-webkit-scrollbar { display: none; }
  .portfolio-rail-title { display: none; }
  .portfolio-tab { min-width: 150px; width: auto; grid-template-columns: 24px auto; }
  .portfolio-tab.is-active::before { left: 14px; right: 14px; top: auto; bottom: 2px; width: auto; height: 3px; }
  .overview-grid { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .portfolio-header { grid-template-columns: 1fr; gap: 12px; padding: 14px; border-radius: 28px; }
  .amo-logo-frame { width: 100%; height: 92px; }
  .brand-copy h1 { font-size: 24px; }
  .action-dock { justify-content: space-between; }
  .action-dock .icon-button { flex: 1; }
  .identity-card { grid-template-columns: auto minmax(0,1fr); gap: 13px; padding: 16px; border-radius: 26px; }
  .person-photo { width: 66px; height: 66px; border-radius: 20px; }
  .person-photo-fallback { font-size: 21px; }
  .identity-copy h2 { font-size: 28px; }
  .verified { grid-column: 1 / -1; justify-self: start; }
  .metric-grid { grid-template-columns: repeat(3,minmax(0,1fr)); }
  .metric-card { padding: 10px; }
  .metric-card b { font-size: 20px; }
  .panel-heading h3 { font-size: 24px; }
  .pagination { align-items: flex-start; flex-direction: column; }
  .page-controls { width: 100%; justify-content: space-between; }
  .certificate-row, .history-row { grid-template-columns: minmax(0,1fr) auto; gap: 10px; }
  .certificate-row time, .history-row time { grid-column: 1 / 2; }
  .certificate-row .certificate-open, .history-row .certificate-open { grid-column: 2 / 3; grid-row: 1 / 3; }
}
@media print {
  .portfolio-header .action-dock, .portfolio-rail, .pagination, .certificate-panel, .history-panel, .legend { display: none !important; }
  .portfolio-layout { display: block; }
  .portfolio-panel[hidden] { display: block !important; }
  .training-panel { margin-top: 18px; }
  .record-row[hidden] { display: table-row !important; }
}
"""


def _logo_media_type(asset: accounts_models.AMOAsset) -> Optional[str]:
    supported = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
    declared = str(getattr(asset, "content_type", None) or "").split(";", 1)[0].strip().lower()
    if declared in supported:
        return declared
    guessed, _ = mimetypes.guess_type(str(getattr(asset, "original_filename", None) or ""))
    guessed = str(guessed or "").lower()
    return guessed if guessed in supported else None


def _logo_priority(asset: accounts_models.AMOAsset) -> int:
    kind = str(getattr(getattr(asset, "kind", None), "value", getattr(asset, "kind", ""))).upper()
    if kind == accounts_models.AMOAssetKind.CRS_LOGO.value:
        return 0
    searchable = " ".join(
        str(value or "").casefold()
        for value in (
            getattr(asset, "name", None),
            getattr(asset, "description", None),
            getattr(asset, "original_filename", None),
        )
    )
    if kind == accounts_models.AMOAssetKind.OTHER.value and any(token in searchable for token in ("logo", "brand", "mark")):
        return 1
    return 99


def _materialized_amo_logo(db, *, amo_id: str):
    assets = (
        db.query(accounts_models.AMOAsset)
        .filter(
            accounts_models.AMOAsset.amo_id == amo_id,
            accounts_models.AMOAsset.is_active.is_(True),
        )
        .order_by(accounts_models.AMOAsset.created_at.desc())
        .all()
    )
    candidates = sorted(
        (asset for asset in assets if _logo_priority(asset) < 99 and _logo_media_type(asset)),
        key=_logo_priority,
    )
    for asset in candidates:
        try:
            path = storage.materialize(asset.storage_path, expected_sha256=asset.sha256)
        except (FileNotFoundError, ValueError, OSError):
            continue
        return asset, path, _logo_media_type(asset)
    return None, None, None


def _enrich_history_course_names(db, *, amo_id: str, user_id: str, payload: dict[str, Any]) -> None:
    requirements = list(payload.get("requirements") or [])
    record_ids = {
        str(entry.get("record_id"))
        for row in requirements
        for entry in (row.get("history") or [])
        if entry.get("record_id")
    }
    if not record_ids:
        return
    records = (
        db.query(training_models.TrainingRecord)
        .filter(
            training_models.TrainingRecord.amo_id == amo_id,
            training_models.TrainingRecord.user_id == user_id,
            training_models.TrainingRecord.id.in_(record_ids),
        )
        .all()
    )
    course_ids = {str(record.course_id) for record in records if getattr(record, "course_id", None)}
    courses = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.amo_id == amo_id,
            training_models.TrainingCourse.id.in_(course_ids),
        )
        .all()
        if course_ids
        else []
    )
    course_name_by_id = {str(course.id): str(course.course_name) for course in courses}
    name_by_record = {
        str(record.id): course_name_by_id.get(str(record.course_id))
        for record in records
    }
    for row in requirements:
        for entry in row.get("history") or []:
            course_name = name_by_record.get(str(entry.get("record_id") or ""))
            if course_name:
                entry["course_name"] = course_name


def _certificate_button(*, record_id: str, course_name: str, compact: bool = False) -> str:
    class_name = "certificate-icon-button" if compact else "certificate-open"
    label = "View certificate" if not compact else ""
    return (
        f"<button type='button' class='{class_name}' data-view-certificate "
        f"data-record-id='{html.escape(record_id, quote=True)}' "
        f"data-course-name='{html.escape(course_name, quote=True)}' "
        f"aria-label='View certificate for {html.escape(course_name, quote=True)}' title='View certificate'>"
        "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><path d='M14 2v6h6'/><path d='M8 13h8'/><path d='M8 17h5'/></svg>"
        f"{f'<span>{label}</span>' if label else ''}</button>"
    )


def _training_profile_html(payload: dict[str, Any]) -> HTMLResponse:
    user = payload.get("user") or {}
    tenant = payload.get("tenant") or {}
    summary = payload.get("summary") or {}
    requirements = list(payload.get("requirements") or [])

    org_raw = str(tenant.get("name") or tenant.get("organisation_name") or "Approved Maintenance Organisation")
    person_raw = str(user.get("full_name") or user.get("name") or "Personnel record")
    role_raw = str(user.get("position_title") or user.get("job_title") or user.get("position") or "Personnel")
    org = html.escape(org_raw)
    person = html.escape(person_raw)
    role = html.escape(role_raw)
    user_id = html.escape(str(user.get("user_id") or ""), quote=True)

    accent = str(tenant.get("brand_accent") or "#8a6f20").strip()
    if not accent.startswith("#") or len(accent) not in (4, 7):
        accent = "#8a6f20"
    accent_attr = html.escape(accent, quote=True)

    logo_url = _glass._safe_image_url(tenant.get("logo_url"), tenant.get("brand_logo_url"), tenant.get("public_logo_url"))
    logo_fallback = html.escape(_base._initials(org_raw))
    if logo_url:
        logo_markup = (
            f"<img src='{logo_url}' alt='' data-amo-logo decoding='async' fetchpriority='high'>"
            f"<span class='amo-logo-fallback' data-amo-logo-fallback hidden>{logo_fallback}</span>"
        )
    else:
        logo_markup = f"<span class='amo-logo-fallback'>{logo_fallback}</span>"

    photo_url = _glass._safe_image_url(user.get("photo_url"), user.get("profile_image_url"), user.get("avatar_url"))
    photo_fallback = html.escape(_base._initials(person_raw))
    if photo_url:
        photo_markup = (
            f"<img src='{photo_url}' alt='' data-person-photo decoding='async' fetchpriority='high'>"
            f"<span class='person-photo-fallback' data-person-photo-fallback hidden>{photo_fallback}</span>"
        )
    else:
        photo_markup = f"<span class='person-photo-fallback'>{photo_fallback}</span>"

    licence = user.get("licence_number") or user.get("license_number")
    licence_markup = f"<span class='licence'>Licence {html.escape(str(licence))}</span>" if licence else ""
    inactive_markup = "<span class='identity-inactive'>Inactive personnel record</span>" if user.get("is_active", True) is False else ""

    current_total = int(summary.get("current", 0) or 0)
    due_soon = int(summary.get("due_soon", 0) or 0)
    overdue = int(summary.get("overdue", 0) or 0)
    deferred = int(summary.get("deferred", 0) or 0)
    standing = "Action required" if overdue else "Current"
    standing_note = f"{overdue} overdue training requirement{'s' if overdue != 1 else ''}." if overdue else "No overdue training requirements are recorded."
    if deferred:
        standing_note += f" {deferred} approved deferral{'s are' if deferred != 1 else ' is'} recorded."

    candidate = next((row for row in requirements if row.get("compliance_status") == "Overdue"), None)
    candidate = candidate or next((row for row in requirements if row.get("next_due") and row.get("due_tone") != "discontinued"), None)
    if candidate:
        next_date = _base._fmt_public_date(candidate.get("next_due"))
        next_course = html.escape(str(candidate.get("course_name") or "Training"))
        next_due_markup = (
            "<section class='next-due-card glass'>"
            "<span class='standing-label'>Next recurrent due</span>"
            f"<span class='date'>{next_date}</span><span class='course'>{next_course}</span>"
            "<span class='support'>Derived from the governed recurrent requirement.</span></section>"
        )
    else:
        next_due_markup = (
            "<section class='next-due-card glass'><span class='standing-label'>Next recurrent due</span>"
            "<span class='date'>—</span><span class='course'>No recurrent deadline recorded</span></section>"
        )

    table_rows: list[str] = []
    certificate_rows: list[str] = []
    history_entries: list[dict[str, Any]] = []

    for row in requirements:
        name_raw = str(row.get("course_name") or "Training")
        name = html.escape(name_raw)
        completed = _base._fmt_public_date(row.get("last_completed"))
        next_due = _base._fmt_public_date(row.get("next_due"))
        tone = str(row.get("due_tone") or "neutral")
        discontinued = tone == "discontinued"
        viewer_record_id = str(row.get("viewer_record_id") or "")
        certificate = _certificate_button(record_id=viewer_record_id, course_name=name_raw, compact=True) if viewer_record_id else "<span class='no-certificate' aria-label='No certificate available'>—</span>"

        table_rows.append(
            f"<tr class='record-row{' is-discontinued' if discontinued else ''}' data-training-row>"
            f"<td class='course-cell'><span class='course-title'>{name}</span></td>"
            f"<td class='completed-cell'><span class='record-date'>{completed}</span></td>"
            f"<td class='due-cell'><span class='record-date due-date due-{html.escape(tone, quote=True)}'>{next_due}</span></td>"
            f"<td class='certificate-cell'>{certificate}</td></tr>"
        )

        if viewer_record_id:
            certificate_rows.append(
                "<div class='certificate-row'>"
                f"<div><h4>{name}</h4><p>Verified training evidence</p></div>"
                f"<time>{completed}</time>{_certificate_button(record_id=viewer_record_id, course_name=name_raw)}</div>"
            )

        for entry in row.get("history") or []:
            history_entries.append({
                "course_name": str(entry.get("course_name") or name_raw),
                "type": str(entry.get("type") or "Training"),
                "completed": entry.get("completed"),
                "record_id": str(entry.get("record_id") or ""),
                "viewer_available": bool(entry.get("viewer_available")),
            })

    if not table_rows:
        table_rows.append("<tr class='record-row' data-training-row><td colspan='4' class='empty-state'>No governed training requirements are published for this personnel record.</td></tr>")

    history_entries.sort(key=lambda entry: str(entry.get("completed") or ""), reverse=True)
    history_rows: list[str] = []
    for entry in history_entries:
        course_raw = str(entry.get("course_name") or "Training")
        course_name = html.escape(course_raw)
        training_type = html.escape(str(entry.get("type") or "Training"))
        completed = _base._fmt_public_date(entry.get("completed"))
        record_id = str(entry.get("record_id") or "")
        action = _certificate_button(record_id=record_id, course_name=course_raw) if record_id and entry.get("viewer_available") else ""
        history_rows.append(
            "<div class='history-row'>"
            f"<div><h4>{course_name}</h4><p>{training_type}</p></div><time>{completed}</time>{action}</div>"
        )

    certificate_content = "".join(certificate_rows) if certificate_rows else "<div class='empty-portfolio glass'>No public certificate evidence is available for these records.</div>"
    history_content = "".join(history_rows) if history_rows else "<div class='empty-portfolio glass'>No verified completion history is available.</div>"

    body = f"""
<main class='report' data-training-report data-training-portfolio data-user-id='{user_id}' style='--accent:{accent_attr}'>
  <header class='portfolio-header glass'>
    <div class='amo-logo-frame'>{logo_markup}</div>
    <div class='brand-copy'><h1>{org}</h1><p>Personnel Training &amp; Compliance Record</p></div>
    <nav class='action-dock' aria-label='Report actions'>
      <button class='icon-button' type='button' data-share-report aria-label='Share report' title='Share report'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M12 16V3'/><path d='m7 8 5-5 5 5'/><path d='M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7'/></svg></button>
      <button class='icon-button' type='button' data-copy-link aria-label='Copy verification link' title='Copy verification link'><svg viewBox='0 0 24 24' aria-hidden='true'><rect x='9' y='9' width='11' height='11' rx='2'/><path d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1'/></svg></button>
      <button class='icon-button' type='button' data-download-pdf aria-label='Download PDF' title='Download PDF'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><path d='M14 2v6h6'/><path d='M12 12v6'/><path d='m9 15 3 3 3-3'/></svg></button>
      <button class='icon-button' type='button' data-print-report aria-label='Print report' title='Print report'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M6 9V2h12v7'/><path d='M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2'/><rect x='6' y='14' width='12' height='8'/></svg></button>
    </nav>
  </header>

  <section class='identity-card glass'>
    <div class='person-photo'>{photo_markup}</div>
    <div class='identity-copy'><h2>{person}</h2><p class='role'>{role}</p>{licence_markup}{inactive_markup}</div>
    <span class='verified'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M20 6 9 17l-5-5'/></svg>Verified</span>
  </section>

  <div class='portfolio-layout'>
    <aside class='portfolio-rail glass' role='tablist' aria-orientation='vertical' aria-label='Training record sections'>
      <div class='portfolio-rail-title'>Record</div>
      <button class='portfolio-tab is-active' type='button' role='tab' aria-selected='true' aria-controls='panel-overview' data-tab-button='overview'><svg viewBox='0 0 24 24' aria-hidden='true'><circle cx='12' cy='8' r='4'/><path d='M4 21a8 8 0 0 1 16 0'/></svg><span><strong>Overview</strong><small>Compliance standing</small></span></button>
      <button class='portfolio-tab' type='button' role='tab' aria-selected='false' aria-controls='panel-training' tabindex='-1' data-tab-button='training'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M4 5h16'/><path d='M4 12h16'/><path d='M4 19h16'/></svg><span><strong>Training record</strong><small>Completion &amp; due dates</small></span></button>
      <button class='portfolio-tab' type='button' role='tab' aria-selected='false' aria-controls='panel-certificates' tabindex='-1' data-tab-button='certificates'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><path d='M14 2v6h6'/><path d='M8 13h8'/></svg><span><strong>Certificates</strong><small>Verified evidence</small></span></button>
      <button class='portfolio-tab' type='button' role='tab' aria-selected='false' aria-controls='panel-history' tabindex='-1' data-tab-button='history'><svg viewBox='0 0 24 24' aria-hidden='true'><circle cx='12' cy='12' r='9'/><path d='M12 7v5l3 2'/></svg><span><strong>History</strong><small>Previous completions</small></span></button>
    </aside>

    <div class='portfolio-panels'>
      <section class='portfolio-panel overview-panel' id='panel-overview' role='tabpanel' data-tab-panel='overview'>
        <div class='panel-heading'><div><h3>Overview</h3><p>Current compliance position for this personnel record.</p></div></div>
        <div class='overview-grid'>
          <section class='standing-card glass'>
            <div><span class='standing-label'>Compliance standing</span><strong>{html.escape(standing)}</strong><p>{html.escape(standing_note)}</p></div>
            <div class='metric-grid'>
              <div class='metric-card'><b>{current_total}</b><span>Current</span></div>
              <div class='metric-card'><b>{due_soon}</b><span>Due soon</span></div>
              <div class='metric-card'><b>{overdue}</b><span>Overdue</span></div>
            </div>
          </section>
          {next_due_markup}
        </div>
      </section>

      <section class='portfolio-panel training-panel' id='panel-training' role='tabpanel' data-tab-panel='training' hidden>
        <div class='panel-heading'><div><h3>Training record</h3><p>Verified completions and recurrent due dates.</p></div></div>
        <section class='record-shell glass' aria-label='Training record table'>
          <table class='record-table' data-paginated-table data-page-size='10'>
            <colgroup><col class='course'><col class='completed'><col class='due'><col class='certificate'></colgroup>
            <thead><tr><th scope='col'>Course</th><th scope='col'>Completed</th><th scope='col'>Next due</th><th scope='col'>Certificate</th></tr></thead>
            <tbody>{''.join(table_rows)}</tbody>
          </table>
        </section>
        <div class='pagination' aria-label='Training table pagination'>
          <span class='page-summary' data-page-summary></span>
          <div class='page-controls'><button class='page-nav' type='button' data-page-prev aria-label='Previous training page'>‹</button><div class='page-numbers' data-page-numbers></div><button class='page-nav' type='button' data-page-next aria-label='Next training page'>›</button></div>
        </div>
        <div class='legend' aria-label='Due date colour key'><span class='current'><i></i>Current</span><span class='overdue'><i></i>Overdue</span><span class='scheduled'><i></i>Scheduled</span><span class='discontinued'><i></i>Discontinued</span></div>
      </section>

      <section class='portfolio-panel certificate-panel' id='panel-certificates' role='tabpanel' data-tab-panel='certificates' hidden>
        <div class='panel-heading'><div><h3>Certificates</h3><p>Approved certificate evidence available on the public record.</p></div></div>
        <div class='certificate-list glass'>{certificate_content}</div>
      </section>

      <section class='portfolio-panel history-panel' id='panel-history' role='tabpanel' data-tab-panel='history' hidden>
        <div class='panel-heading'><div><h3>History</h3><p>Verified completion history across governed training lifecycles.</p></div></div>
        <div class='history-list-card glass'>{history_content}</div>
      </section>
    </div>
  </div>
</main>

<dialog id='certificate-viewer' class='certificate-viewer' aria-label='Certificate viewer'>
  <div class='viewer-shell'>
    <header class='viewer-bar'>
      <button type='button' class='close-button' data-close-viewer aria-label='Close certificate viewer'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='m6 6 12 12'/><path d='M18 6 6 18'/></svg></button>
      <div class='viewer-heading'><strong data-viewer-title>Training certificate</strong><span>Verified controlled evidence</span></div>
      <a class='open-original' data-open-certificate target='_blank' rel='noopener'>Open original</a>
    </header>
    <div class='certificate-stage' data-certificate-stage></div>
  </div>
</dialog>
<div class='action-feedback' data-action-feedback role='status' aria-live='polite'></div>
"""

    css = f"{_glass._GLASS_CSS}\n{_table._TABLE_CSS}\n{_PORTFOLIO_CSS}"
    return HTMLResponse(
        content=(
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
            "<meta name='color-scheme' content='light'>"
            f"<meta name='theme-color' content='{accent_attr}'>"
            f"<title>{person} · Training verification</title><style>{css}</style>"
            "<script src='/public/training/assets/record-report.js' defer></script>"
            "<script src='/public/training/assets/record-portfolio.js' defer></script>"
            f"</head><body style='--accent:{accent_attr}'>{body}</body></html>"
        )
    )


def install_training_record_presentation(router_module) -> None:
    """Install the portfolio UI above the canonical signed Training report."""
    if getattr(router_module, "_portfolio_training_record_presentation_installed", False):
        return

    _table.install_training_record_presentation(router_module)
    table_payload = router_module._public_training_profile_payload

    def public_payload(db, *, amo_id: str, user_id: str, record_id: Optional[str] = None):
        payload = table_payload(db, amo_id=amo_id, user_id=user_id, record_id=record_id)
        _enrich_history_course_names(db, amo_id=amo_id, user_id=user_id, payload=payload)
        tenant = dict(payload.get("tenant") or {})
        tenant.pop("logo_url", None)
        tenant.pop("brand_logo_url", None)
        tenant.pop("public_logo_url", None)
        asset, path, _ = _materialized_amo_logo(db, amo_id=amo_id)
        if asset is not None and path is not None:
            tenant["logo_url"] = f"/public/training/brand/{quote(str(amo_id), safe='')}/identity-logo"
        payload["tenant"] = tenant
        return payload

    def portfolio_script():
        return Response(
            content=_PORTFOLIO_SCRIPT,
            media_type="application/javascript",
            headers={"Cache-Control": "public, max-age=300"},
        )

    def public_identity_logo(
        amo_id: str,
        db=Depends(router_module.get_read_db),
    ):
        asset, path, media_type = _materialized_amo_logo(db, amo_id=amo_id)
        if asset is None or path is None or media_type is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "public, max-age=60"})
        filename = str(getattr(asset, "original_filename", None) or "amo-logo")
        return FileResponse(
            path=str(path),
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=600",
                "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
            },
        )

    router_module._public_training_profile_payload = public_payload
    router_module._training_profile_html = _training_profile_html
    router_module.public_router.add_api_route(
        "/training/assets/record-portfolio.js",
        portfolio_script,
        methods=["GET"],
        include_in_schema=False,
    )
    router_module.public_router.add_api_route(
        "/training/brand/{amo_id}/identity-logo",
        public_identity_logo,
        methods=["GET"],
        include_in_schema=False,
    )
    router_module._portfolio_training_record_presentation_installed = True


__all__ = [
    "_PORTFOLIO_CSS",
    "_PORTFOLIO_SCRIPT",
    "_materialized_amo_logo",
    "_training_profile_html",
    "install_training_record_presentation",
]
