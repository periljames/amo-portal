from __future__ import annotations

import html
import io
from datetime import date
from typing import Any, Optional
from urllib.parse import quote, urlsplit

from fastapi import Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from amodb import storage
from ..accounts import models as accounts_models
from . import models as training_models
from . import record_lifecycle as training_record_lifecycle
from . import record_presentation as _base


_REPORT_SCRIPT = r"""
(() => {
  'use strict';

  const root = document.querySelector('[data-training-report]');
  if (!root) return;

  const feedback = document.querySelector('[data-action-feedback]');
  const viewer = document.getElementById('certificate-viewer');
  const stage = viewer?.querySelector('[data-certificate-stage]');
  const viewerTitle = viewer?.querySelector('[data-viewer-title]');
  const openExternal = viewer?.querySelector('[data-open-certificate]');
  let objectUrl = null;

  const say = (message, isError = false) => {
    if (!feedback) return;
    feedback.textContent = message;
    feedback.classList.toggle('is-error', isError);
    feedback.classList.add('is-visible');
    window.clearTimeout(say.timer);
    say.timer = window.setTimeout(() => feedback.classList.remove('is-visible'), 2800);
  };

  const currentQuery = () => new URL(window.location.href).searchParams;
  const signedParams = () => {
    const source = currentQuery();
    const target = new URLSearchParams();
    ['amo', 'report_token', 'code', 'token'].forEach((key) => {
      const value = source.get(key);
      if (value) target.set(key, value);
    });
    return target;
  };

  const verificationUrl = () => window.location.href;

  const copyText = async (text) => {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_) {
        // Fall through to the selection-based fallback below.
      }
    }
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    let copied = false;
    try { copied = document.execCommand('copy'); } catch (_) { copied = false; }
    textarea.remove();
    return copied;
  };

  document.querySelector('[data-copy-link]')?.addEventListener('click', async () => {
    const copied = await copyText(verificationUrl());
    say(copied ? 'Verification link copied.' : 'Unable to copy the link.', !copied);
  });

  document.querySelector('[data-share-report]')?.addEventListener('click', async () => {
    const shareData = {
      title: document.title,
      text: 'Verified personnel training record',
      url: verificationUrl(),
    };
    if (navigator.share) {
      try {
        await navigator.share(shareData);
        return;
      } catch (error) {
        if (error?.name === 'AbortError') return;
      }
    }
    const copied = await copyText(verificationUrl());
    say(copied ? 'Share link copied.' : 'Unable to share this record.', !copied);
  });

  document.querySelector('[data-download-pdf]')?.addEventListener('click', () => {
    const userId = root.dataset.userId;
    const reportToken = currentQuery().get('report_token');
    if (!userId || !reportToken) {
      say('PDF download is unavailable for this access link.', true);
      return;
    }
    const url = new URL(`/public/training/users/${encodeURIComponent(userId)}/record.pdf`, window.location.origin);
    const params = signedParams();
    params.forEach((value, key) => url.searchParams.set(key, value));
    window.location.assign(url.toString());
  });

  document.querySelector('[data-print-report]')?.addEventListener('click', () => window.print());

  const closeViewer = () => {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    if (stage) stage.replaceChildren();
    if (viewer?.open) viewer.close();
  };

  viewer?.querySelector('[data-close-viewer]')?.addEventListener('click', closeViewer);
  viewer?.addEventListener('click', (event) => {
    if (event.target === viewer) closeViewer();
  });
  viewer?.addEventListener('cancel', (event) => {
    event.preventDefault();
    closeViewer();
  });

  document.querySelectorAll('[data-view-certificate]').forEach((button) => {
    button.addEventListener('click', async () => {
      const userId = root.dataset.userId;
      const recordId = button.dataset.recordId;
      if (!userId || !recordId || !viewer || !stage) return;

      const url = new URL(
        `/public/training/users/${encodeURIComponent(userId)}/records/${encodeURIComponent(recordId)}/certificate`,
        window.location.origin,
      );
      const params = signedParams();
      params.forEach((value, key) => url.searchParams.set(key, value));

      if (viewerTitle) viewerTitle.textContent = button.dataset.courseName || 'Training certificate';
      stage.innerHTML = "<div class='viewer-loading'><span></span><p>Loading verified certificate…</p></div>";
      if (openExternal) openExternal.href = url.toString();
      viewer.showModal();

      try {
        const response = await fetch(url.toString(), { credentials: 'same-origin' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const blob = await response.blob();
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = URL.createObjectURL(blob);
        stage.replaceChildren();

        const type = (blob.type || response.headers.get('content-type') || '').toLowerCase();
        if (type.includes('pdf')) {
          const frame = document.createElement('iframe');
          frame.src = objectUrl;
          frame.title = `${button.dataset.courseName || 'Training'} certificate`;
          frame.className = 'certificate-frame';
          stage.appendChild(frame);
        } else if (type.startsWith('image/')) {
          const image = document.createElement('img');
          image.src = objectUrl;
          image.alt = `${button.dataset.courseName || 'Training'} certificate`;
          image.className = 'certificate-image';
          stage.appendChild(image);
        } else {
          const message = document.createElement('div');
          message.className = 'viewer-message';
          message.textContent = 'This evidence type opens in a separate viewer.';
          stage.appendChild(message);
        }
      } catch (_) {
        stage.innerHTML = "<div class='viewer-message is-error'>The certificate could not be loaded. Use Open original to retry.</div>";
      }
    });
  });
})();
"""


_GLASS_CSS = r"""
:root {
  --page: #f2f2f7;
  --label: #151517;
  --secondary: rgba(60, 60, 67, .68);
  --tertiary: rgba(60, 60, 67, .48);
  --separator: rgba(60, 60, 67, .13);
  --glass: rgba(255, 255, 255, .56);
  --glass-strong: rgba(255, 255, 255, .72);
  --glass-soft: rgba(255, 255, 255, .38);
  --blue: #007aff;
  --green: #248a3d;
  --orange: #ad5b00;
  --red: #c9262d;
  --radius-xl: 32px;
  --radius-lg: 24px;
  --radius-md: 18px;
  --shadow: 0 20px 55px rgba(35, 35, 45, .08), 0 2px 10px rgba(35, 35, 45, .035);
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; text-rendering: optimizeLegibility; }
body {
  margin: 0;
  min-height: 100vh;
  overflow-x: hidden;
  color: var(--label);
  background:
    radial-gradient(circle at 4% 2%, color-mix(in srgb, var(--accent) 24%, transparent) 0, transparent 29rem),
    radial-gradient(circle at 98% 18%, rgba(0,122,255,.16) 0, transparent 28rem),
    radial-gradient(circle at 52% 105%, rgba(175,82,222,.12) 0, transparent 30rem),
    linear-gradient(150deg, #f7f7fb 0%, #ececf3 58%, #f4f4f8 100%);
  font: 15px/1.45 -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Helvetica Neue", "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
}
body::before, body::after {
  position: fixed;
  z-index: -1;
  width: 34rem;
  height: 34rem;
  content: "";
  border-radius: 50%;
  filter: blur(68px);
  opacity: .42;
  pointer-events: none;
}
body::before { top: -15rem; left: -11rem; background: color-mix(in srgb, var(--accent) 50%, white); }
body::after { right: -14rem; bottom: -16rem; background: #b7d7ff; }
button, a { font: inherit; }
button { color: inherit; }
a { color: inherit; }
.report {
  width: min(1180px, 100%);
  margin: 0 auto;
  padding: max(24px, env(safe-area-inset-top)) max(20px, env(safe-area-inset-right)) max(42px, env(safe-area-inset-bottom)) max(20px, env(safe-area-inset-left));
}
.glass {
  border: 1px solid rgba(255,255,255,.68);
  background: var(--glass);
  -webkit-backdrop-filter: saturate(190%) blur(30px);
  backdrop-filter: saturate(190%) blur(30px);
  box-shadow: var(--shadow), inset 0 1px 0 rgba(255,255,255,.74);
}
.brand-bar {
  display: grid;
  grid-template-columns: auto minmax(0,1fr) auto;
  align-items: center;
  gap: 20px;
  min-height: 122px;
  padding: 16px 18px;
  border-radius: var(--radius-xl);
}
.brand-visual {
  width: 158px;
  height: 88px;
  display: grid;
  place-items: center;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.78);
  border-radius: 24px;
  background: rgba(255,255,255,.68);
  color: var(--accent);
  font-size: 28px;
  font-weight: 760;
  letter-spacing: -.05em;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.9), 0 10px 28px rgba(0,0,0,.05);
}
.brand-visual img { width: 100%; height: 100%; object-fit: contain; padding: 10px 13px; display: block; }
.brand-copy { min-width: 0; }
.brand-copy h1 { margin: 0; font-size: clamp(23px, 3.2vw, 34px); line-height: 1.03; font-weight: 760; letter-spacing: -.045em; }
.brand-copy p { margin: 7px 0 0; color: var(--secondary); font-size: 13px; font-weight: 520; }
.action-dock {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px;
  border: 1px solid rgba(255,255,255,.76);
  border-radius: 18px;
  background: rgba(255,255,255,.45);
  -webkit-backdrop-filter: saturate(190%) blur(26px);
  backdrop-filter: saturate(190%) blur(26px);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.8), 0 9px 24px rgba(0,0,0,.045);
}
.icon-button {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 15px;
  background: transparent;
  color: var(--blue);
  cursor: pointer;
  transition: transform .14s ease, background .14s ease;
}
.icon-button:hover { background: rgba(0,122,255,.095); }
.icon-button:active { transform: scale(.93); background: rgba(0,122,255,.14); }
.icon-button svg, .certificate-button svg, .verified svg, .details-link svg, .close-button svg {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.85;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.profile-hero {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0,1fr) auto;
  align-items: center;
  gap: 22px;
  margin-top: 18px;
  padding: 24px;
  overflow: hidden;
  border-radius: var(--radius-xl);
}
.profile-hero::after {
  position: absolute;
  right: -70px;
  bottom: -100px;
  width: 250px;
  height: 250px;
  content: "";
  border-radius: 50%;
  background: color-mix(in srgb, var(--accent) 17%, transparent);
  filter: blur(28px);
  pointer-events: none;
}
.avatar {
  width: 100px;
  height: 100px;
  display: grid;
  place-items: center;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.78);
  border-radius: 30px;
  background: linear-gradient(145deg, color-mix(in srgb,var(--accent) 58%,white), var(--accent));
  color: white;
  font-size: 31px;
  font-weight: 760;
  letter-spacing: -.045em;
  box-shadow: inset 0 1px rgba(255,255,255,.28), 0 14px 32px rgba(0,0,0,.10);
}
.avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }
.profile-copy { min-width: 0; position: relative; z-index: 1; }
.profile-copy h2 { margin: 0; font-size: clamp(27px, 3.2vw, 38px); line-height: 1.02; font-weight: 760; letter-spacing: -.05em; }
.profile-copy .role { margin: 7px 0 0; color: var(--secondary); font-size: 15px; }
.profile-meta { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 14px; }
.meta-pill {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border: 1px solid rgba(255,255,255,.54);
  border-radius: 11px;
  background: rgba(118,118,128,.08);
  color: var(--secondary);
  font-size: 12px;
  font-weight: 600;
}
.verified {
  position: relative;
  z-index: 1;
  align-self: start;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 12px;
  border: 1px solid rgba(52,199,89,.12);
  border-radius: 999px;
  background: rgba(52,199,89,.13);
  color: #16743c;
  font-size: 12px;
  font-weight: 720;
  white-space: nowrap;
}
.overview {
  display: grid;
  grid-template-columns: minmax(0, .85fr) minmax(0, 1.35fr);
  gap: 14px;
  margin-top: 14px;
}
.compliance-card, .next-card { min-height: 104px; padding: 18px 20px; border-radius: var(--radius-lg); }
.compliance-card { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.current-count strong { display: block; font-size: 36px; line-height: .95; font-weight: 780; letter-spacing: -.055em; }
.current-count span { display: block; margin-top: 7px; color: var(--secondary); font-size: 12px; font-weight: 610; }
.exception-pills { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 7px; }
.exception-pill { padding: 7px 10px; border-radius: 999px; background: rgba(118,118,128,.08); color: var(--secondary); font-size: 12px; font-weight: 650; }
.exception-pill.is-due { color: var(--orange); background: rgba(255,149,0,.11); }
.exception-pill.is-overdue { color: var(--red); background: rgba(255,59,48,.10); }
.exception-pill.is-deferred { color: #755900; background: rgba(255,204,0,.13); }
.next-card { display: flex; align-items: center; gap: 14px; }
.next-orb { width: 46px; height: 46px; flex: 0 0 46px; display: grid; place-items: center; border-radius: 15px; background: color-mix(in srgb,var(--accent) 12%,rgba(255,255,255,.76)); color: var(--accent); font-size: 20px; font-weight: 760; }
.next-copy { min-width: 0; }
.eyebrow { display: block; color: var(--tertiary); font-size: 10px; line-height: 1.2; font-weight: 740; letter-spacing: .08em; text-transform: uppercase; }
.next-copy strong { display: block; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 16px; font-weight: 700; }
.next-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 5px; color: var(--secondary); font-size: 12px; }
.section-head { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin: 28px 3px 12px; }
.section-head h3 { margin: 0; font-size: 19px; line-height: 1.2; font-weight: 740; letter-spacing: -.025em; }
.section-head p { margin: 0; color: var(--secondary); font-size: 12px; }
.training-grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 14px; }
.training-card {
  min-width: 0;
  padding: 19px;
  border: 1px solid rgba(255,255,255,.66);
  border-radius: var(--radius-lg);
  background: rgba(255,255,255,.48);
  -webkit-backdrop-filter: saturate(175%) blur(24px);
  backdrop-filter: saturate(175%) blur(24px);
  box-shadow: 0 12px 30px rgba(35,35,45,.055), inset 0 1px 0 rgba(255,255,255,.72);
}
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.course-copy { min-width: 0; }
.course-copy h4 { margin: 0; font-size: 16px; line-height: 1.22; font-weight: 710; letter-spacing: -.018em; }
.course-copy p { margin: 5px 0 0; color: var(--secondary); font-size: 11px; }
.status-pill { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 6px; min-height: 27px; padding: 4px 9px; border-radius: 999px; font-size: 11px; font-weight: 680; }
.status-pill::before { width: 6px; height: 6px; content: ""; border-radius: 50%; background: currentColor; }
.status-current, .status-completed { color: #16743c; background: rgba(52,199,89,.12); }
.status-due-soon { color: var(--orange); background: rgba(255,149,0,.12); }
.status-overdue, .status-not-completed { color: var(--red); background: rgba(255,59,48,.10); }
.status-deferred { color: #755900; background: rgba(255,204,0,.14); }
.status-scheduled { color: #235ea7; background: rgba(0,122,255,.10); }
.date-pair { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; margin-top: 17px; }
.date-cell { min-width: 0; padding: 11px 12px; border: 1px solid rgba(255,255,255,.55); border-radius: 15px; background: rgba(118,118,128,.055); }
.date-cell span { display: block; color: var(--tertiary); font-size: 10px; font-weight: 650; text-transform: uppercase; letter-spacing: .045em; }
.date-cell strong { display: block; margin-top: 4px; font-size: 13px; font-weight: 650; font-variant-numeric: tabular-nums; }
.card-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.certificate-button {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid rgba(0,122,255,.14);
  border-radius: 13px;
  background: rgba(0,122,255,.09);
  color: var(--blue);
  font-size: 12px;
  font-weight: 680;
  cursor: pointer;
}
.certificate-button:hover { background: rgba(0,122,255,.14); }
.certificate-button svg { width: 17px; height: 17px; }
.row-details { flex: 1; min-width: 120px; }
.row-details > summary { width: max-content; display: inline-flex; align-items: center; gap: 4px; min-height: 40px; list-style: none; color: var(--blue); font-size: 12px; font-weight: 650; cursor: pointer; }
.row-details > summary::-webkit-details-marker { display: none; }
.details-link svg { width: 15px; height: 15px; transition: transform .16s ease; }
.row-details[open] .details-link svg { transform: rotate(90deg); }
.detail-panel { margin-top: 9px; padding: 12px 13px; border-radius: 15px; background: rgba(118,118,128,.055); }
.detail-line { display: flex; justify-content: space-between; gap: 16px; padding: 6px 0; color: var(--secondary); font-size: 11px; }
.detail-line + .detail-line { border-top: 1px solid var(--separator); }
.detail-line strong { color: var(--label); font-weight: 620; text-align: right; }
.history-title { margin: 10px 0 3px; color: var(--tertiary); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
.history-list { margin: 0; padding: 0; list-style: none; }
.history-list li { display: flex; justify-content: space-between; gap: 12px; padding: 7px 0; border-top: 1px solid var(--separator); font-size: 11px; }
.history-list span { color: var(--secondary); }
.empty-state { grid-column: 1/-1; padding: 36px; border-radius: var(--radius-lg); text-align: center; color: var(--secondary); }
.certificate-viewer {
  width: min(1080px, calc(100vw - 28px));
  height: min(820px, calc(100vh - 28px));
  margin: auto;
  padding: 0;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.76);
  border-radius: 30px;
  background: rgba(245,245,250,.68);
  -webkit-backdrop-filter: saturate(190%) blur(34px);
  backdrop-filter: saturate(190%) blur(34px);
  box-shadow: 0 35px 90px rgba(0,0,0,.26), inset 0 1px 0 rgba(255,255,255,.78);
}
.certificate-viewer::backdrop { background: rgba(30,30,35,.26); -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px); }
.viewer-shell { height: 100%; display: grid; grid-template-rows: auto minmax(0,1fr); }
.viewer-bar { display: grid; grid-template-columns: 44px minmax(0,1fr) auto; align-items: center; gap: 10px; min-height: 66px; padding: 9px 12px; border-bottom: 1px solid var(--separator); background: rgba(255,255,255,.48); }
.close-button { width: 40px; height: 40px; display: grid; place-items: center; border: 0; border-radius: 50%; background: rgba(118,118,128,.10); cursor: pointer; }
.viewer-heading { min-width: 0; text-align: center; }
.viewer-heading strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 700; }
.viewer-heading span { display: block; margin-top: 1px; color: var(--secondary); font-size: 10px; }
.open-original { min-height: 38px; display: inline-flex; align-items: center; padding: 7px 11px; border-radius: 12px; color: var(--blue); text-decoration: none; font-size: 12px; font-weight: 660; }
.certificate-stage { min-height: 0; padding: 12px; background: rgba(118,118,128,.07); }
.certificate-frame, .certificate-image { width: 100%; height: 100%; display: block; border: 0; border-radius: 18px; background: white; }
.certificate-image { object-fit: contain; }
.viewer-loading, .viewer-message { height: 100%; display: grid; place-items: center; align-content: center; gap: 10px; color: var(--secondary); text-align: center; }
.viewer-loading span { width: 28px; height: 28px; border: 3px solid rgba(0,122,255,.16); border-top-color: var(--blue); border-radius: 50%; animation: spin .8s linear infinite; }
.viewer-loading p { margin: 0; font-size: 12px; }
.viewer-message.is-error { color: var(--red); }
.action-feedback { position: fixed; z-index: 100; left: 50%; bottom: max(24px, env(safe-area-inset-bottom)); transform: translate(-50%, 18px); padding: 10px 14px; border: 1px solid rgba(255,255,255,.68); border-radius: 999px; background: rgba(38,38,42,.82); color: white; font-size: 12px; font-weight: 630; opacity: 0; pointer-events: none; -webkit-backdrop-filter: blur(20px); backdrop-filter: blur(20px); transition: opacity .18s ease, transform .18s ease; }
.action-feedback.is-visible { opacity: 1; transform: translate(-50%, 0); }
.action-feedback.is-error { background: rgba(160,25,31,.88); }
.icon-button:focus-visible, .certificate-button:focus-visible, .row-details > summary:focus-visible, .close-button:focus-visible, .open-original:focus-visible { outline: 3px solid rgba(0,122,255,.28); outline-offset: 2px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 820px) {
  .brand-bar { grid-template-columns: auto minmax(0,1fr); }
  .action-dock { grid-column: 1/-1; justify-self: stretch; }
  .action-dock .icon-button { flex: 1; }
  .overview { grid-template-columns: 1fr; }
  .training-grid { grid-template-columns: 1fr; }
}
@media (max-width: 600px) {
  .report { padding: max(12px, env(safe-area-inset-top)) max(12px, env(safe-area-inset-right)) max(28px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left)); }
  .brand-bar { gap: 12px; min-height: auto; padding: 13px; border-radius: 27px; }
  .brand-visual { width: 105px; height: 70px; border-radius: 20px; }
  .brand-copy h1 { font-size: 20px; }
  .brand-copy p { font-size: 11px; }
  .action-dock { margin-top: 2px; }
  .profile-hero { grid-template-columns: auto minmax(0,1fr); gap: 13px; padding: 16px; border-radius: 27px; }
  .avatar { width: 68px; height: 68px; border-radius: 20px; font-size: 22px; }
  .profile-copy h2 { font-size: 23px; }
  .verified { grid-column: 1/-1; justify-self: start; }
  .compliance-card, .next-card { padding: 15px; }
  .current-count strong { font-size: 31px; }
  .section-head { margin-top: 24px; }
  .training-card { padding: 16px; border-radius: 22px; }
  .date-pair { grid-template-columns: 1fr 1fr; }
  .certificate-viewer { width: 100vw; height: 100dvh; max-width: none; max-height: none; border-radius: 0; border: 0; }
  .viewer-bar { padding-top: max(9px, env(safe-area-inset-top)); }
  .certificate-stage { padding: 8px; padding-bottom: max(8px, env(safe-area-inset-bottom)); }
}
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; } }
@media print {
  body { background: white; }
  body::before, body::after, .action-dock, .certificate-button, .certificate-viewer, .action-feedback { display: none !important; }
  .report { width: 100%; max-width: none; padding: 0; }
  .glass, .training-card { background: white; box-shadow: none; -webkit-backdrop-filter: none; backdrop-filter: none; border-color: #ddd; }
  .brand-bar, .profile-hero, .compliance-card, .next-card, .training-card { break-inside: avoid; }
}
"""


def _safe_image_url(*values: Any) -> Optional[str]:
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        if raw.startswith("/") and not raw.startswith("//"):
            return html.escape(raw, quote=True)
        parsed = urlsplit(raw)
        if parsed.scheme.lower() == "https" and parsed.netloc:
            return html.escape(raw, quote=True)
    return None


def _status_class(value: str) -> str:
    return str(value or "not-completed").strip().lower().replace(" ", "-").replace("_", "-")


def _history_details(row: dict[str, Any]) -> str:
    lines: list[str] = []
    if row.get("scheduled"):
        lines.append(
            "<div class='detail-line'><span>Scheduled</span>"
            f"<strong>{_base._fmt_public_date(row.get('scheduled'))}</strong></div>"
        )

    history = list(row.get("history") or [])
    latest = history[0] if history else None
    if latest and latest.get("certificate_reference"):
        lines.append(
            "<div class='detail-line'><span>Certificate reference</span>"
            f"<strong>{html.escape(str(latest.get('certificate_reference')))}</strong></div>"
        )
    if latest and latest.get("hours") is not None:
        lines.append(
            "<div class='detail-line'><span>Hours</span>"
            f"<strong>{html.escape(str(latest.get('hours')))}</strong></div>"
        )
    if latest and latest.get("score") is not None:
        lines.append(
            "<div class='detail-line'><span>Score</span>"
            f"<strong>{html.escape(str(latest.get('score')))}%</strong></div>"
        )

    older = history[1:]
    if older:
        items = "".join(
            "<li><span>"
            f"{html.escape(str(item.get('type') or 'Training'))} · {html.escape(str(item.get('course_code') or ''))}"
            "</span>"
            f"<strong>{_base._fmt_public_date(item.get('completed'))}</strong></li>"
            for item in older
        )
        lines.append(f"<p class='history-title'>Previous completions</p><ul class='history-list'>{items}</ul>")

    if not lines:
        return ""
    return (
        "<details class='row-details'><summary class='details-link'><span>More details</span>"
        "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='m9 18 6-6-6-6'/></svg></summary>"
        f"<div class='detail-panel'>{''.join(lines)}</div></details>"
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

    logo_url = _safe_image_url(tenant.get("logo_url"), tenant.get("brand_logo_url"), tenant.get("public_logo_url"))
    photo_url = _safe_image_url(user.get("photo_url"), user.get("profile_image_url"), user.get("avatar_url"))
    brand_visual = (
        f"<img src='{logo_url}' alt='{org} logo' decoding='async' fetchpriority='high'>"
        if logo_url
        else html.escape(_base._initials(org_raw))
    )
    avatar_visual = (
        f"<img src='{photo_url}' alt='' decoding='async' fetchpriority='high'>"
        if photo_url
        else html.escape(_base._initials(person_raw))
    )

    meta: list[str] = []
    staff = user.get("staff_code") or user.get("staff_no")
    licence = user.get("licence_number") or user.get("license_number")
    if staff:
        meta.append(f"<span class='meta-pill'>Staff {html.escape(str(staff))}</span>")
    if licence:
        meta.append(f"<span class='meta-pill'>Licence {html.escape(str(licence))}</span>")
    meta.append(f"<span class='meta-pill'>{'Active' if user.get('is_active', True) else 'Inactive'}</span>")

    current_total = int(summary.get("current", 0) or 0)
    completed_total = int(summary.get("completed", 0) or 0)
    if completed_total:
        current_label = f"{current_total} current · {completed_total} completed"
    else:
        current_label = f"{current_total} current"

    exceptions: list[str] = []
    due_soon = int(summary.get("due_soon", 0) or 0)
    overdue = int(summary.get("overdue", 0) or 0)
    deferred = int(summary.get("deferred", 0) or 0)
    if due_soon:
        exceptions.append(f"<span class='exception-pill is-due'>{due_soon} due soon</span>")
    if overdue:
        exceptions.append(f"<span class='exception-pill is-overdue'>{overdue} overdue</span>")
    if deferred:
        exceptions.append(f"<span class='exception-pill is-deferred'>{deferred} deferred</span>")
    if not exceptions:
        exceptions.append("<span class='exception-pill'>No exceptions</span>")

    exception = next((row for row in requirements if row.get("compliance_status") == "Overdue"), None)
    candidate = exception or next((row for row in requirements if row.get("next_due")), None)
    next_card = ""
    if candidate:
        eyebrow = "Action required" if exception else "Next recurrent due"
        orb = "!" if exception else "↗"
        due_prefix = "Due" if exception else "Due"
        schedule = ""
        if candidate.get("scheduled"):
            schedule = f"<span>Scheduled {_base._fmt_public_date(candidate.get('scheduled'))}</span>"
        next_card = (
            "<section class='next-card glass' aria-label='Next training action'>"
            f"<div class='next-orb' aria-hidden='true'>{orb}</div><div class='next-copy'>"
            f"<span class='eyebrow'>{eyebrow}</span>"
            f"<strong>{html.escape(str(candidate.get('course_name') or 'Training'))}</strong>"
            f"<div class='next-meta'><span>{due_prefix} {_base._fmt_public_date(candidate.get('next_due'))}</span>{schedule}</div>"
            "</div></section>"
        )
    else:
        next_card = (
            "<section class='next-card glass'><div class='next-orb' aria-hidden='true'>✓</div>"
            "<div class='next-copy'><span class='eyebrow'>Training status</span>"
            "<strong>No recurrent deadline is currently recorded</strong></div></section>"
        )

    cards: list[str] = []
    for row in requirements:
        name_raw = str(row.get("course_name") or "Training")
        name = html.escape(name_raw)
        code = html.escape(str(row.get("course_id") or ""))
        course_type = html.escape(str(row.get("course_type") or "Training"))
        status_raw = str(row.get("compliance_status") or "Not completed")
        status_text = html.escape(status_raw)
        completed = _base._fmt_public_date(row.get("last_completed"))
        next_due = _base._fmt_public_date(row.get("next_due"))

        viewer_record_id = row.get("viewer_record_id")
        viewer_button = ""
        if viewer_record_id:
            label = html.escape(str(row.get("viewer_label") or "View certificate"))
            viewer_button = (
                "<button type='button' class='certificate-button' data-view-certificate "
                f"data-record-id='{html.escape(str(viewer_record_id), quote=True)}' data-course-name='{html.escape(name_raw, quote=True)}'>"
                "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><path d='M14 2v6h6'/><path d='M8 13h8'/><path d='M8 17h5'/></svg>"
                f"<span>{label}</span></button>"
            )

        cards.append(
            "<article class='training-card'>"
            "<div class='card-head'><div class='course-copy'>"
            f"<h4>{name}</h4><p>{code} · {course_type}</p></div>"
            f"<span class='status-pill status-{_status_class(status_raw)}'>{status_text}</span></div>"
            "<div class='date-pair'>"
            f"<div class='date-cell'><span>Completed</span><strong>{completed}</strong></div>"
            f"<div class='date-cell'><span>Next due</span><strong>{next_due}</strong></div>"
            "</div>"
            f"<div class='card-actions'>{viewer_button}{_history_details(row)}</div>"
            "</article>"
        )

    if not cards:
        cards.append("<div class='empty-state glass'>No governed training requirements are published for this personnel record.</div>")

    body = f"""
<main class='report' data-training-report data-user-id='{user_id}' style='--accent:{accent_attr}'>
  <header class='brand-bar glass'>
    <div class='brand-visual'>{brand_visual}</div>
    <div class='brand-copy'><h1>{org}</h1><p>Personnel Training &amp; Compliance Record</p></div>
    <nav class='action-dock' aria-label='Report actions'>
      <button class='icon-button' type='button' data-share-report aria-label='Share report' title='Share report'>
        <svg viewBox='0 0 24 24' aria-hidden='true'><path d='M12 16V3'/><path d='m7 8 5-5 5 5'/><path d='M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7'/></svg>
      </button>
      <button class='icon-button' type='button' data-copy-link aria-label='Copy verification link' title='Copy verification link'>
        <svg viewBox='0 0 24 24' aria-hidden='true'><rect x='9' y='9' width='11' height='11' rx='2'/><path d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1'/></svg>
      </button>
      <button class='icon-button' type='button' data-download-pdf aria-label='Download PDF' title='Download PDF'>
        <svg viewBox='0 0 24 24' aria-hidden='true'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><path d='M14 2v6h6'/><path d='M12 12v6'/><path d='m9 15 3 3 3-3'/></svg>
      </button>
      <button class='icon-button' type='button' data-print-report aria-label='Print report' title='Print report'>
        <svg viewBox='0 0 24 24' aria-hidden='true'><path d='M6 9V2h12v7'/><path d='M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2'/><rect x='6' y='14' width='12' height='8'/></svg>
      </button>
    </nav>
  </header>

  <section class='profile-hero glass'>
    <div class='avatar' role='img' aria-label='Personnel image'>{avatar_visual}</div>
    <div class='profile-copy'><h2>{person}</h2><p class='role'>{role}</p><div class='profile-meta'>{''.join(meta)}</div></div>
    <span class='verified'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M20 6 9 17l-5-5'/></svg>Verified</span>
  </section>

  <div class='overview'>
    <section class='compliance-card glass' aria-label='Training compliance summary'>
      <div class='current-count'><strong>{current_total}</strong><span>{html.escape(current_label)}</span></div>
      <div class='exception-pills'>{''.join(exceptions)}</div>
    </section>
    {next_card}
  </div>

  <div class='section-head'><div><h3>Training record</h3><p>Current governed requirements and verified completions</p></div><p>{len(requirements)} requirements</p></div>
  <section class='training-grid' aria-label='Training requirements'>{''.join(cards)}</section>
</main>

<dialog id='certificate-viewer' class='certificate-viewer' aria-label='Certificate viewer'>
  <div class='viewer-shell'>
    <header class='viewer-bar'>
      <button type='button' class='close-button' data-close-viewer aria-label='Close certificate viewer'>
        <svg viewBox='0 0 24 24' aria-hidden='true'><path d='m6 6 12 12'/><path d='M18 6 6 18'/></svg>
      </button>
      <div class='viewer-heading'><strong data-viewer-title>Training certificate</strong><span>Verified controlled evidence</span></div>
      <a class='open-original' data-open-certificate target='_blank' rel='noopener'>Open original</a>
    </header>
    <div class='certificate-stage' data-certificate-stage></div>
  </div>
</dialog>
<div class='action-feedback' data-action-feedback role='status' aria-live='polite'></div>
"""

    return HTMLResponse(
        content=(
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
            "<meta name='color-scheme' content='light'>"
            f"<meta name='theme-color' content='{accent_attr}'>"
            f"<title>{person} · Training verification</title><style>{_GLASS_CSS}</style>"
            "<script src='/public/training/assets/record-report.js' defer></script>"
            f"</head><body style='--accent:{accent_attr}'>{body}</body></html>"
        )
    )


def _approved_public_file(db, *, amo_id: str, user_id: str, record_id: str):
    rows = (
        db.query(training_models.TrainingFile)
        .filter(
            training_models.TrainingFile.amo_id == amo_id,
            training_models.TrainingFile.owner_user_id == user_id,
            training_models.TrainingFile.record_id == record_id,
            training_models.TrainingFile.kind.in_([
                training_models.TrainingFileKind.CERTIFICATE,
                training_models.TrainingFileKind.EVIDENCE,
            ]),
            training_models.TrainingFile.review_status == training_models.TrainingFileReviewStatus.APPROVED,
        )
        .order_by(training_models.TrainingFile.uploaded_at.desc())
        .all()
    )
    if not rows:
        return None
    return next((row for row in rows if row.kind == training_models.TrainingFileKind.CERTIFICATE), rows[0])


def _materialized_public_logo(db, *, amo_id: str):
    asset = (
        db.query(accounts_models.AMOAsset)
        .filter(
            accounts_models.AMOAsset.amo_id == amo_id,
            accounts_models.AMOAsset.kind == accounts_models.AMOAssetKind.CRS_LOGO,
            accounts_models.AMOAsset.is_active.is_(True),
        )
        .order_by(accounts_models.AMOAsset.created_at.desc())
        .first()
    )
    if not asset or not getattr(asset, "storage_path", None):
        return None, None
    try:
        path = storage.materialize(asset.storage_path, expected_sha256=asset.sha256)
    except (FileNotFoundError, ValueError, OSError):
        return None, None
    return asset, path


def _public_payload_with_viewers(original_payload, db, *, amo_id: str, user_id: str, record_id: Optional[str] = None):
    payload = original_payload(db, amo_id=amo_id, user_id=user_id, record_id=record_id)
    requirements = list(payload.get("requirements") or [])
    record_ids = {
        str(entry.get("record_id"))
        for row in requirements
        for entry in (row.get("history") or [])
        if entry.get("record_id")
    }

    file_kind_by_record: dict[str, str] = {}
    issue_records: set[str] = set()
    if record_ids:
        approved_files = (
            db.query(training_models.TrainingFile)
            .filter(
                training_models.TrainingFile.amo_id == amo_id,
                training_models.TrainingFile.owner_user_id == user_id,
                training_models.TrainingFile.record_id.in_(record_ids),
                training_models.TrainingFile.kind.in_([
                    training_models.TrainingFileKind.CERTIFICATE,
                    training_models.TrainingFileKind.EVIDENCE,
                ]),
                training_models.TrainingFile.review_status == training_models.TrainingFileReviewStatus.APPROVED,
            )
            .all()
        )
        for file_row in approved_files:
            rid = str(file_row.record_id)
            kind = getattr(file_row.kind, "value", file_row.kind)
            if rid not in file_kind_by_record or str(kind) == "CERTIFICATE":
                file_kind_by_record[rid] = str(kind)

        issue_records = {
            str(row[0])
            for row in db.query(training_models.TrainingCertificateIssue.record_id)
            .filter(
                training_models.TrainingCertificateIssue.amo_id == amo_id,
                training_models.TrainingCertificateIssue.record_id.in_(record_ids),
            )
            .all()
            if row[0]
        }

    for row in requirements:
        viewer_record_id = None
        viewer_label = None
        for entry in row.get("history") or []:
            rid = str(entry.get("record_id") or "")
            available = bool(rid and (rid in file_kind_by_record or rid in issue_records))
            entry["viewer_available"] = available
            if available and viewer_record_id is None:
                viewer_record_id = rid
                viewer_label = "View certificate" if file_kind_by_record.get(rid) == "CERTIFICATE" or rid in issue_records else "View evidence"
        row["viewer_record_id"] = viewer_record_id
        row["viewer_label"] = viewer_label
        row["evidence_available"] = bool(viewer_record_id)

    tenant = dict(payload.get("tenant") or {})
    asset = (
        db.query(accounts_models.AMOAsset.id)
        .filter(
            accounts_models.AMOAsset.amo_id == amo_id,
            accounts_models.AMOAsset.kind == accounts_models.AMOAssetKind.CRS_LOGO,
            accounts_models.AMOAsset.is_active.is_(True),
        )
        .first()
    )
    if asset:
        tenant["logo_url"] = f"/public/training/brand/{quote(str(amo_id), safe='')}/logo"
    payload["tenant"] = tenant
    payload["requirements"] = requirements
    return payload


def install_training_record_presentation(router_module) -> None:
    """Install the public glass report without weakening the existing Training controls."""

    if getattr(router_module, "_glass_training_record_presentation_installed", False):
        return

    _base.install_training_record_presentation(router_module)
    base_public_payload = router_module._public_training_profile_payload

    def public_payload(db, *, amo_id: str, user_id: str, record_id: Optional[str] = None):
        return _public_payload_with_viewers(
            base_public_payload,
            db,
            amo_id=amo_id,
            user_id=user_id,
            record_id=record_id,
        )

    router_module._public_training_profile_payload = public_payload
    router_module._training_profile_html = _training_profile_html

    def report_script():
        return Response(
            content=_REPORT_SCRIPT,
            media_type="application/javascript",
            headers={"Cache-Control": "public, max-age=300"},
        )

    def public_brand_logo(
        amo_id: str,
        db=Depends(router_module.get_read_db),
    ):
        asset, path = _materialized_public_logo(db, amo_id=amo_id)
        if not asset or not path:
            return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "public, max-age=60"})
        media_type = str(getattr(asset, "content_type", None) or "application/octet-stream").lower()
        if media_type not in {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported logo type.")
        return FileResponse(
            path=str(path),
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=600",
                "Content-Disposition": f"inline; filename={quote(str(getattr(asset, 'original_filename', None) or 'logo'))}",
            },
        )

    def public_record_pdf(
        user_id: str,
        amo: Optional[str] = Query(None),
        report_token: Optional[str] = Query(None),
        db=Depends(router_module.get_read_db),
    ):
        amo_row = router_module._resolve_public_amo(db, amo, user_id=user_id)
        if not amo_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found.")
        if not report_token or not router_module._verify_training_report_token(
            report_token,
            amo_id=str(amo_row.id),
            user_id=user_id,
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A valid signed report link is required.")

        context = router_module._get_training_user_record_export_context(
            db,
            amo_id=str(amo_row.id),
            user_id=user_id,
        )
        cache_path = router_module._training_user_pdf_cache_path(user_id, context["cache_key"])
        if cache_path.exists():
            pdf_bytes = cache_path.read_bytes()
        else:
            pdf_bytes = router_module._build_training_user_record_pdf_bytes(
                user=context["user"],
                amo=context.get("amo"),
                logo_path=context.get("logo_path"),
                status_items=context["evaluation"].items,
                records=context["records"],
                course_by_id=context["course_by_id"],
                upcoming_events=context["upcoming_events"],
                deferrals=context["deferrals"],
                verification_url=context.get("verification_url"),
                report_settings=context.get("report_settings"),
            )
            router_module._write_training_user_pdf_cache(
                user_id=user_id,
                cache_key=context["cache_key"],
                pdf_bytes=pdf_bytes,
            )
        filename = f"{(context['user'].full_name or user_id).replace(' ', '_')}_training_record.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
            },
        )

    def public_certificate(
        user_id: str,
        record_id: str,
        amo: Optional[str] = Query(None),
        report_token: Optional[str] = Query(None),
        code: Optional[str] = Query(None),
        token: Optional[str] = Query(None),
        db=Depends(router_module.get_read_db),
    ):
        amo_row = router_module._resolve_public_amo(db, amo, user_id=user_id)
        if not amo_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found.")
        amo_id = str(amo_row.id)

        signed = bool(
            report_token
            and router_module._verify_training_report_token(report_token, amo_id=amo_id, user_id=user_id)
        )
        if not signed:
            if not code:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Verified access is required.")
            grant = router_module._validate_training_auditor_access(
                db,
                amo_id=amo_id,
                user_id=user_id,
                access_code=code,
                token=token,
            )
            if grant.target_record_id and str(grant.target_record_id) != str(record_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This auditor link is not authorised for the requested record.")

        record = (
            db.query(training_models.TrainingRecord)
            .filter(
                training_models.TrainingRecord.id == record_id,
                training_models.TrainingRecord.amo_id == amo_id,
                training_models.TrainingRecord.user_id == user_id,
                training_models.TrainingRecord.verification_status == training_models.TrainingRecordVerificationStatus.VERIFIED,
                training_record_lifecycle.active_records_filter(training_models.TrainingRecord),
            )
            .first()
        )
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verified training record not found.")

        file_row = _approved_public_file(db, amo_id=amo_id, user_id=user_id, record_id=record_id)
        if file_row is not None:
            media_type = str(getattr(file_row, "content_type", None) or "application/octet-stream").lower()
            if media_type not in {"application/pdf", "image/png", "image/jpeg", "image/webp"}:
                raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="This evidence format cannot be previewed publicly.")
            path = router_module._materialize_training_file(file_row)
            filename = str(getattr(file_row, "original_filename", None) or "training-evidence")
            return FileResponse(
                path=str(path),
                media_type=media_type,
                headers={
                    "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
                    "Cache-Control": "private, no-store",
                },
            )

        issue = (
            db.query(training_models.TrainingCertificateIssue)
            .filter(
                training_models.TrainingCertificateIssue.amo_id == amo_id,
                training_models.TrainingCertificateIssue.record_id == record.id,
            )
            .first()
        )
        if not issue:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No approved certificate or evidence is available for this record.")

        person = db.query(accounts_models.User).filter(
            accounts_models.User.id == user_id,
            accounts_models.User.amo_id == amo_id,
        ).first()
        course = db.query(training_models.TrainingCourse).filter(
            training_models.TrainingCourse.id == record.course_id,
            training_models.TrainingCourse.amo_id == amo_id,
        ).first()
        if not person or not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate source data is incomplete.")
        event = None
        if getattr(record, "event_id", None):
            event = db.query(training_models.TrainingEvent).filter(
                training_models.TrainingEvent.id == record.event_id,
                training_models.TrainingEvent.amo_id == amo_id,
            ).first()
        _, logo_path = _materialized_public_logo(db, amo_id=amo_id)
        pdf_bytes = router_module._build_training_certificate_pdf_bytes(
            user=person,
            course=course,
            record=record,
            issue=issue,
            amo=amo_row,
            event=event,
            logo_path=str(logo_path) if logo_path else None,
            signatory_name=None,
            signatory_title=None,
            approver_name=None,
            approver_title=None,
        )
        filename = f"{(person.full_name or user_id).replace(' ', '_')}_{course.course_id}_certificate.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Cache-Control": "private, no-store",
            },
        )

    router_module.public_router.add_api_route(
        "/training/assets/record-report.js",
        report_script,
        methods=["GET"],
        include_in_schema=False,
    )
    router_module.public_router.add_api_route(
        "/training/brand/{amo_id}/logo",
        public_brand_logo,
        methods=["GET"],
        include_in_schema=False,
    )
    router_module.public_router.add_api_route(
        "/training/users/{user_id}/record.pdf",
        public_record_pdf,
        methods=["GET"],
        summary="Download a signed public personnel training record PDF",
    )
    router_module.public_router.add_api_route(
        "/training/users/{user_id}/records/{record_id}/certificate",
        public_certificate,
        methods=["GET"],
        summary="Preview approved public training certificate evidence",
    )

    router_module._glass_training_record_presentation_installed = True


__all__ = ["install_training_record_presentation", "_training_profile_html"]
