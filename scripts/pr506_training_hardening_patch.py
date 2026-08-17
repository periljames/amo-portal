from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one occurrence, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, *, label: str, flags: int = re.S) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match, found {count}")
    return updated


def patch_record_presentation() -> None:
    path = "backend/amodb/apps/training/record_presentation.py"
    text = read(path)
    text = replace_once(
        text,
        "from . import compliance as training_compliance\nfrom . import models as training_models\n",
        "from . import compliance as training_compliance\nfrom . import course_lifecycle as training_course_lifecycle\nfrom . import models as training_models\n",
        label="record presentation lifecycle import",
    )
    text = regex_once(
        text,
        r"def normalized_training_kind\(value: Any\) -> str:.*?\n\ndef mask_public_phone",
        '''def normalized_training_kind(value: Any) -> str:\n    return training_course_lifecycle.normalized_training_kind(value)\n\n\ndef training_type_label(value: Any) -> str:\n    kind = normalized_training_kind(value)\n    if kind == "INITIAL":\n        return "Initial"\n    if kind == "RECURRENT":\n        return "Recurrent"\n    return "—"\n\n\ndef is_initial_course_explicit(course: training_models.TrainingCourse) -> bool:\n    return training_course_lifecycle.is_initial_course(course)\n\n\ndef is_recurrent_course_explicit(course: training_models.TrainingCourse) -> bool:\n    return training_course_lifecycle.is_recurrent_course(course)\n\n\ndef explicit_recurrence_key(course: training_models.TrainingCourse, courses: Iterable[training_models.TrainingCourse] = ()) -> str:\n    return training_course_lifecycle.explicit_recurrence_key(course, courses)\n\n\ndef mask_public_phone''',
        label="record presentation canonical lifecycle wrappers",
    )
    text = replace_once(
        text,
        'for env_name in ("APP_PUBLIC_BASE_URL", "PUBLIC_APP_URL", "PLATFORM_PUBLIC_BASE_URL", "PUBLIC_BASE_URL"):',
        'for env_name in ("APP_PUBLIC_BASE_URL", "PLATFORM_API_BASE_URL", "PUBLIC_APP_URL", "PLATFORM_PUBLIC_BASE_URL", "PUBLIC_BASE_URL"):',
        label="PLATFORM_API_BASE_URL origin",
    )
    text = text.replace('getattr(record, "training_hours", None)', 'getattr(record, "hours_completed", None)')

    old_filter = '''    rows = _build_requirement_rows(db, amo_id=amo_id, user=user)\n    if record_id:\n        rows = [\n            row for row in rows\n            if any(str(history.get("record_id")) == str(record_id) for history in row.get("history") or [])\n        ]\n'''
    new_filter = '''    legacy_records = list(payload.get("records") or [])\n    rows = _build_requirement_rows(db, amo_id=amo_id, user=user)\n    if record_id:\n        rows = [\n            row for row in rows\n            if any(str(history.get("record_id")) == str(record_id) for history in row.get("history") or [])\n        ]\n        if not rows:\n            selected = next((entry for entry in legacy_records if str(entry.get("record_id")) == str(record_id)), None)\n            if selected is not None:\n                rows = [{\n                    "requirement_key": f"record:{record_id}",\n                    "course_pk": None,\n                    "course_id": str(selected.get("course_id") or ""),\n                    "course_name": str(selected.get("course_name") or "Training record"),\n                    "course_type": "Training",\n                    "last_completed": selected.get("completion_date"),\n                    "next_due": selected.get("valid_until"),\n                    "scheduled": None,\n                    "compliance_status": "Completed",\n                    "evidence_available": False,\n                    "record_count": 1,\n                    "history": [{\n                        "record_id": str(record_id),\n                        "type": "Training",\n                        "course_code": selected.get("course_id"),\n                        "completed": selected.get("completion_date"),\n                        "next_due": selected.get("valid_until"),\n                        "hours": None,\n                        "score": None,\n                        "certificate_reference": selected.get("certificate_reference"),\n                        "evidence_available": False,\n                        "verification_status": selected.get("verification_status"),\n                    }],\n                }]\n'''
    text = replace_once(text, old_filter, new_filter, label="record scoped public fallback")

    canvas_block = '''class _NumberedCanvas(canvas.Canvas):\n    def __init__(self, *args, **kwargs):\n        self._saved_pages = []\n        super().__init__(*args, **kwargs)\n\n    def showPage(self):\n        self._saved_pages.append(dict(self.__dict__))\n        self._startPage()\n\n    def save(self):\n        page_count = len(self._saved_pages)\n        for state in self._saved_pages:\n            self.__dict__.update(state)\n            self.setFont("Helvetica", 7.5)\n            self.setFillColor(colors.HexColor("#667085"))\n            self.drawString(14 * mm, 9 * mm, "Controlled Training Record")\n            self.drawCentredString(A4[0] / 2, 9 * mm, "QAM/49A Rev 00")\n            self.drawRightString(A4[0] - 14 * mm, 9 * mm, f"Page {self._pageNumber} of {page_count}")\n            super().showPage()\n        super().save()\n'''
    new_canvas = '''class _NumberedCanvas(canvas.Canvas):\n    def __init__(self, *args, training_pdf_meta=None, **kwargs):\n        self._saved_pages = []\n        self._training_pdf_meta = training_pdf_meta or {}\n        super().__init__(*args, **kwargs)\n\n    def showPage(self):\n        self._saved_pages.append(dict(self.__dict__))\n        self._startPage()\n\n    def save(self):\n        page_count = len(self._saved_pages)\n        for state in self._saved_pages:\n            self.__dict__.update(state)\n            meta = self._training_pdf_meta or {}\n            self.setFont("Helvetica", 7.5)\n            self.setFillColor(colors.HexColor("#667085"))\n            self.drawString(14 * mm, 9 * mm, str(meta.get("footer_note") or "Controlled Training Record")[:88])\n            form_no = str(meta.get("form_no") or "QAM/49A")\n            revision = str(meta.get("revision") or "00")\n            self.drawCentredString(A4[0] / 2, 9 * mm, f"{form_no} Rev {revision}")\n            self.drawRightString(A4[0] - 14 * mm, 9 * mm, f"Page {self._pageNumber} of {page_count}")\n            super().showPage()\n        super().save()\n\n\ndef _numbered_canvas_maker(meta: dict[str, Any]):\n    def maker(*args, **kwargs):\n        return _NumberedCanvas(*args, training_pdf_meta=meta, **kwargs)\n    return maker\n'''
    text = replace_once(text, canvas_block, new_canvas, label="PDF canvas settings")

    text = replace_once(
        text,
        '''        report_settings = kwargs.get("report_settings") or {}\n        status_items = _group_pdf_status_items(status_items, course_by_id)\n''',
        '''        report_settings = kwargs.get("report_settings") or {}\n        deferrals = kwargs.get("deferrals") or []\n        status_items = _group_pdf_status_items(status_items, course_by_id)\n''',
        label="PDF deferrals input",
    )
    marker = '''    buffer = BytesIO()\n    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=13*mm, bottomMargin=16*mm)\n'''
    settings_block = '''    show_compliance_summary = report_settings.get("show_compliance_summary", True) is not False\n    show_training_history = report_settings.get("show_training_history", True) is not False\n    show_scheduled_events = report_settings.get("show_scheduled_events", True) is not False\n    show_deferrals = report_settings.get("show_deferrals", True) is not False\n    report_title = str(report_settings.get("title") or "Individual Training & Compliance Record")\n    report_subtitle = str(report_settings.get("subtitle") or "")\n    form_no = str(report_settings.get("form_no") or "QAM/49A")\n    issue_date = str(report_settings.get("issue_date") or "")\n    revision = str(report_settings.get("revision") or "00")\n    footer_note = str(report_settings.get("footer_note") or "Controlled Training Record")\n\n    buffer = BytesIO()\n    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=13*mm, bottomMargin=16*mm, title=report_title)\n'''
    text = replace_once(text, marker, settings_block, label="PDF settings variables")
    text = replace_once(
        text,
        '''    masthead = Table([[masthead_left, Paragraph(f"<b>{html.escape(str(getattr(amo,'name',None) or 'Approved Maintenance Organisation'))}</b><br/><b>INDIVIDUAL TRAINING &amp; COMPLIANCE RECORD</b>", body), Paragraph("<b>QAM/49A</b><br/>Rev 00", body)]], colWidths=[30*mm, 118*mm, 28*mm])\n''',
        '''    masthead_title = html.escape(report_title.upper())\n    masthead_meta = f"<b>{html.escape(form_no)}</b><br/>Rev {html.escape(revision)}" + (f"<br/>{html.escape(issue_date)}" if issue_date else "")\n    masthead = Table([[masthead_left, Paragraph(f"<b>{html.escape(str(getattr(amo,'name',None) or 'Approved Maintenance Organisation'))}</b><br/><b>{masthead_title}</b>" + (f"<br/><font color='#667085'>{html.escape(report_subtitle)}</font>" if report_subtitle else ""), body), Paragraph(masthead_meta, body)]], colWidths=[30*mm, 118*mm, 28*mm])\n''',
        label="PDF masthead settings",
    )
    text = replace_once(
        text,
        '''    story.extend([band, Spacer(1,2.5*mm)])\n\n    item_by_code={str(getattr(item,"course_id",'')):item for item in status_items}\n''',
        '''    if show_compliance_summary:\n        story.extend([band, Spacer(1,2.5*mm)])\n\n    item_by_code={str(getattr(item,"course_id",'')):item for item in status_items}\n''',
        label="PDF summary visibility",
    )
    text = replace_once(
        text,
        '''    story.append(training_table)\n\n    doc.build(story, canvasmaker=_NumberedCanvas)\n''',
        '''    story.append(training_table)\n\n    if show_training_history and records:\n        history_data = [[Paragraph("<b>Course</b>", small), Paragraph("<b>Completed</b>", small), Paragraph("<b>Valid until</b>", small), Paragraph("<b>Certificate</b>", small)]]\n        for record in sorted(records, key=lambda row: (getattr(row, "completion_date", None) or date.min, str(getattr(row, "created_at", ""))), reverse=True):\n            course = course_by_id.get(str(getattr(record, "course_id", "")))\n            history_data.append([\n                Paragraph(html.escape(str(getattr(course, "course_name", None) or getattr(record, "course_id", "Training"))), body),\n                Paragraph(_pdf_date(getattr(record, "completion_date", None)), body),\n                Paragraph(_pdf_date(getattr(record, "valid_until", None)), body),\n                Paragraph(html.escape(str(getattr(record, "certificate_reference", None) or "—")), body),\n            ])\n        history_table = Table(history_data, colWidths=[86*mm, 30*mm, 30*mm, 32*mm], repeatRows=1)\n        history_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f2f4f7")),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#d0d5dd")),("VALIGN",(0,0),(-1,-1),"TOP"),("FONTSIZE",(0,0),(-1,-1),6.8)]))\n        story.extend([Spacer(1,2.5*mm), Paragraph("<b>Training record log</b>", body), history_table])\n\n    if show_scheduled_events and upcoming_events:\n        event_data = [[Paragraph("<b>Scheduled training</b>", small), Paragraph("<b>Starts</b>", small), Paragraph("<b>Status</b>", small)]]\n        for event in sorted(upcoming_events, key=lambda row: (getattr(row, "starts_on", None) or date.max, str(getattr(row, "title", "")) )):\n            course = course_by_id.get(str(getattr(event, "course_id", "")))\n            event_data.append([\n                Paragraph(html.escape(str(getattr(event, "title", None) or getattr(course, "course_name", None) or "Training event")), body),\n                Paragraph(_pdf_date(getattr(event, "starts_on", None)), body),\n                Paragraph(html.escape(str(getattr(getattr(event, "status", None), "value", getattr(event, "status", None)) or "—")), body),\n            ])\n        event_table = Table(event_data, colWidths=[108*mm, 34*mm, 36*mm], repeatRows=1)\n        event_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f2f4f7")),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#d0d5dd")),("VALIGN",(0,0),(-1,-1),"TOP")]))\n        story.extend([Spacer(1,2.5*mm), Paragraph("<b>Scheduled training and events</b>", body), event_table])\n\n    if show_deferrals and deferrals:\n        deferral_data = [[Paragraph("<b>Course</b>", small), Paragraph("<b>Original due</b>", small), Paragraph("<b>Extended due</b>", small), Paragraph("<b>Status</b>", small)]]\n        for item in deferrals:\n            course = course_by_id.get(str(getattr(item, "course_id", "")))\n            deferral_data.append([\n                Paragraph(html.escape(str(getattr(course, "course_name", None) or getattr(item, "course_id", "Training"))), body),\n                Paragraph(_pdf_date(getattr(item, "original_due_date", None)), body),\n                Paragraph(_pdf_date(getattr(item, "requested_new_due_date", None)), body),\n                Paragraph(html.escape(str(getattr(getattr(item, "status", None), "value", getattr(item, "status", None)) or "—")), body),\n            ])\n        deferral_table = Table(deferral_data, colWidths=[76*mm, 34*mm, 34*mm, 34*mm], repeatRows=1)\n        deferral_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f2f4f7")),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#d0d5dd")),("VALIGN",(0,0),(-1,-1),"TOP")]))\n        story.extend([Spacer(1,2.5*mm), Paragraph("<b>Deferral and extension history</b>", body), deferral_table])\n\n    doc.build(story, canvasmaker=_numbered_canvas_maker({"form_no": form_no, "revision": revision, "footer_note": footer_note}))\n''',
        label="PDF governed optional sections",
    )
    write(path, text)


def patch_router() -> None:
    path = "backend/amodb/apps/training/router.py"
    text = read(path)
    text = regex_once(
        text,
        r"def _course_family_key_from_course\(course: training_models\.TrainingCourse\) -> str:.*?\n\ndef _get_amo_logo_path",
        "def _get_amo_logo_path",
        label="remove router heuristic and synthetic seeding functions",
    )
    text = regex_once(
        text,
        r"\n    seeded_refresher_records: list\[training_models\.TrainingRecord\] = \[\]\n    if training_compliance\.is_initial_course\(course\):\n        seeded_refresher_records = _seed_refresher_records_from_initial\(.*?\n        \)\n",
        "\n",
        label="remove synthetic recurrent creation call",
    )
    text = regex_once(
        text,
        r"\n    if seeded_refresher_records:\n        notif_body \+= f\" \{len\(seeded_refresher_records\)\} linked refresher entr\{'y' if len\(seeded_refresher_records\) == 1 else 'ies'\} were auto-seeded from the initial completion\.\"\n",
        "\n",
        label="remove synthetic notification text",
    )
    text = text.replace('            "auto_seeded_refresher_count": len(seeded_refresher_records),\n', "")
    if "_seed_refresher_records_from_initial" in text or "AUTO-SEEDED FROM INITIAL" in text:
        raise RuntimeError("router synthetic recurrence code still present")
    write(path, text)


def patch_compliance() -> None:
    path = "backend/amodb/apps/training/compliance.py"
    text = read(path)
    text = replace_once(
        text,
        "from . import models as training_models\n",
        "from . import course_lifecycle as training_course_lifecycle\nfrom . import models as training_models\n",
        label="compliance lifecycle import",
    )
    text = regex_once(
        text,
        r"def _normalized_course_text\(course: training_models\.TrainingCourse\) -> str:.*?\n\ndef _should_suppress_refresher_until_initial_exists",
        '''def is_initial_course(course: training_models.TrainingCourse) -> bool:\n    return training_course_lifecycle.is_initial_course(course)\n\n\ndef is_refresher_course(course: training_models.TrainingCourse) -> bool:\n    return training_course_lifecycle.is_recurrent_course(course)\n\n\ndef _course_family_key(course: training_models.TrainingCourse) -> str:\n    return training_course_lifecycle.explicit_recurrence_key(course)\n\n\ndef _should_suppress_refresher_until_initial_exists''',
        label="remove compliance text inference",
    )
    anchor_helper = '''\n\ndef _initial_recurrence_anchors_for_user(\n    db: Session,\n    user: accounts_models.User,\n    courses: Sequence[training_models.TrainingCourse],\n) -> Dict[str, training_models.TrainingRecord]:\n    """Map recurrent course ids to genuine Initial completion anchors.\n\n    The returned TrainingRecord remains the actual Initial event; it is used only\n    to project the recurrent due date and is never copied into a recurrent row.\n    """\n    recurrent = [course for course in courses if is_refresher_course(course)]\n    if not recurrent:\n        return {}\n    catalogue = (\n        db.query(training_models.TrainingCourse)\n        .options(noload("*"))\n        .filter(\n            training_models.TrainingCourse.amo_id == user.amo_id,\n            training_models.TrainingCourse.is_active.is_(True),\n        )\n        .all()\n    )\n    initial_courses = [course for course in catalogue if is_initial_course(course)]\n    initial_ids = [course.id for course in initial_courses]\n    if not initial_ids:\n        return {}\n    rows = (\n        db.query(training_models.TrainingRecord)\n        .options(noload("*"))\n        .filter(\n            training_models.TrainingRecord.amo_id == user.amo_id,\n            training_models.TrainingRecord.user_id == user.id,\n            training_models.TrainingRecord.course_id.in_(initial_ids),\n            training_models.TrainingRecord.verification_status == training_models.TrainingRecordVerificationStatus.VERIFIED,\n            training_record_lifecycle.active_records_filter(training_models.TrainingRecord),\n        )\n        .order_by(training_models.TrainingRecord.completion_date.desc(), training_models.TrainingRecord.created_at.desc())\n        .all()\n    )\n    latest_initial: Dict[str, training_models.TrainingRecord] = {}\n    for row in rows:\n        latest_initial.setdefault(str(row.course_id), row)\n\n    anchors: Dict[str, training_models.TrainingRecord] = {}\n    for course in recurrent:\n        candidates: list[training_models.TrainingRecord] = []\n        prerequisite = str(getattr(course, "prerequisite_course_id", "") or "").strip().casefold()\n        group_code = str(getattr(course, "group_code", "") or "").strip().casefold()\n        for initial in initial_courses:\n            initial_identifiers = {\n                str(getattr(initial, "id", "") or "").strip().casefold(),\n                str(getattr(initial, "course_id", "") or "").strip().casefold(),\n            }\n            initial_group = str(getattr(initial, "group_code", "") or "").strip().casefold()\n            explicitly_related = bool(\n                prerequisite and prerequisite in initial_identifiers\n                or group_code and initial_group and group_code == initial_group\n            )\n            if explicitly_related:\n                record = latest_initial.get(str(initial.id))\n                if record is not None:\n                    candidates.append(record)\n        if candidates:\n            anchors[str(course.id)] = max(\n                candidates,\n                key=lambda row: (getattr(row, "completion_date", None) or date.min, str(getattr(row, "created_at", ""))),\n            )\n    return anchors\n'''
    insert_marker = "\ndef _latest_deferrals_for_user(db: Session, user: accounts_models.User, course_ids: Sequence[str])"
    text = replace_once(text, insert_marker, anchor_helper + insert_marker, label="recurrence anchor helper")
    text = replace_once(
        text,
        "    earliest_event = _earliest_events_for_user(db, user, course_ids, today)\n\n    course_by_code =",
        "    earliest_event = _earliest_events_for_user(db, user, course_ids, today)\n    recurrence_anchors = _initial_recurrence_anchors_for_user(db, user, courses)\n\n    course_by_code =",
        label="load recurrence anchors",
    )
    text = replace_once(
        text,
        '''        due_date = None\n        if record:\n            due_date = record.valid_until or (add_months(record.completion_date, course.frequency_months) if course.frequency_months else None)\n''',
        '''        due_date = None\n        if record:\n            due_date = record.valid_until or (add_months(record.completion_date, course.frequency_months) if course.frequency_months else None)\n        elif course.frequency_months and str(course.id) in recurrence_anchors:\n            anchor = recurrence_anchors[str(course.id)]\n            due_date = add_months(anchor.completion_date, course.frequency_months)\n''',
        label="project recurrent due from initial anchor",
    )
    if "_normalized_course_text" in text:
        raise RuntimeError("compliance text inference helper still present")
    write(path, text)


def patch_training_competence() -> None:
    path = "frontend/src/pages/TrainingCompetencePage.tsx"
    text = read(path)
    text = replace_once(
        text,
        'import { getCachedUser } from "../services/auth";\n',
        'import { getCachedUser } from "../services/auth";\nimport { trainingLifecyclePhase } from "../utils/trainingPresentation";\n',
        label="TrainingCompetence canonical lifecycle import",
    )
    text = text.replace("type CourseFamilyIndex = Record<string, string[]>;\n\n", "")
    text = regex_once(
        text,
        r"function coursePhase\(course: TrainingCourseRead\): .*?\n\nfunction buildCourseLookup",
        "function buildCourseLookup",
        label="remove TrainingCompetence inference helpers",
    )
    text = regex_once(
        text,
        r"function buildRefresherAnomalies\(\n  users: AdminUserSummaryRead\[],\n  courses: TrainingCourseRead\[],\n  records: TrainingRecordRead\[],\n\): RefresherAnomaly\[] \{.*?\n\}\n\ntype TrainingCompetencePageProps",
        '''function buildRefresherAnomalies(\n  users: AdminUserSummaryRead[],\n  courses: TrainingCourseRead[],\n  records: TrainingRecordRead[],\n): RefresherAnomaly[] {\n  const courseLookup = buildCourseLookup(courses);\n  const initialByGroup = new Map<string, TrainingCourseRead[]>();\n  courses.forEach((course) => {\n    if (trainingLifecyclePhase(course) !== "INITIAL") return;\n    const group = String(course.group_code || "").trim().toLocaleLowerCase();\n    if (!group) return;\n    initialByGroup.set(group, [...(initialByGroup.get(group) || []), course]);\n  });\n\n  const latestRecords = new Map<string, TrainingRecordRead>();\n  records.forEach((record) => {\n    const key = `${record.user_id}:${record.course_id}`;\n    const existing = latestRecords.get(key);\n    const recordRank = `${record.valid_until || "0000-00-00"}:${record.completion_date || "0000-00-00"}:${record.created_at || ""}`;\n    const existingRank = existing ? `${existing.valid_until || "0000-00-00"}:${existing.completion_date || "0000-00-00"}:${existing.created_at || ""}` : "";\n    if (!existing || recordRank > existingRank) latestRecords.set(key, record);\n  });\n  const activeRecords = Array.from(latestRecords.values());\n\n  const completedByUser = new Map<string, Set<string>>();\n  activeRecords.forEach((record) => {\n    if (!completedByUser.has(record.user_id)) completedByUser.set(record.user_id, new Set());\n    const completed = completedByUser.get(record.user_id)!;\n    completed.add(String(record.course_id));\n    const resolved = resolveCourse(courseLookup, record.course_id);\n    if (resolved?.id) completed.add(String(resolved.id));\n    if (resolved?.course_id) completed.add(String(resolved.course_id));\n  });\n\n  const userById = new Map(users.map((user) => [user.id, user]));\n  const anomalies: RefresherAnomaly[] = [];\n  const seen = new Set<string>();\n\n  activeRecords.forEach((record) => {\n    const course = resolveCourse(courseLookup, record.course_id);\n    if (!course || trainingLifecyclePhase(course) !== "REFRESHER") return;\n    const prerequisites = new Set<string>();\n    const declared = String(course.prerequisite_course_id || "").trim();\n    if (declared) prerequisites.add(declared);\n    const group = String(course.group_code || "").trim().toLocaleLowerCase();\n    (initialByGroup.get(group) || []).forEach((initial) => {\n      if (initial.id) prerequisites.add(String(initial.id));\n      if (initial.course_id) prerequisites.add(String(initial.course_id));\n    });\n    if (prerequisites.size === 0) return;\n    const completed = completedByUser.get(record.user_id) || new Set<string>();\n    if ([...prerequisites].some((courseId) => completed.has(courseId))) return;\n    const key = `${record.user_id}:${record.course_id}`;\n    if (seen.has(key)) return;\n    seen.add(key);\n    anomalies.push({\n      key,\n      userId: record.user_id,\n      userName: userById.get(record.user_id)?.full_name || userById.get(record.user_id)?.email || record.user_id,\n      coursePk: record.course_id,\n      courseCode: course.course_id,\n      courseName: course.course_name,\n      prerequisiteNames: [...prerequisites].map((id) => resolveCourse(courseLookup, id)?.course_name || resolveCourse(courseLookup, id)?.course_id || id),\n      completionDate: record.completion_date,\n    });\n  });\n\n  return anomalies.sort((a, b) => a.userName.localeCompare(b.userName) || a.courseName.localeCompare(b.courseName));\n}\n\ntype TrainingCompetencePageProps''',
        label="TrainingCompetence explicit anomaly logic",
    )
    text = text.replace("phase: coursePhase(course),", "phase: trainingLifecyclePhase(course),")
    if "function coursePhase" in text or "function familyKey" in text or "familyKey(" in text:
        raise RuntimeError("TrainingCompetence heuristic lifecycle code still present")
    write(path, text)


def patch_validation_workflow() -> None:
    path = ".github/workflows/training-record-redesign-validation.yml"
    text = '''name: Training Record Redesign Validation\n\non:\n  push:\n    branches:\n      - codex/training-record-redesign-20260817\n  pull_request:\n    paths:\n      - "backend/amodb/apps/training/**"\n      - "frontend/src/**/training/**"\n      - "frontend/src/pages/TrainingCompetencePage.tsx"\n      - "frontend/src/utils/trainingPresentation*"\n      - ".github/workflows/training-record-redesign-validation.yml"\n\npermissions:\n  contents: read\n\nconcurrency:\n  group: training-record-redesign-validation-${{ github.ref }}\n  cancel-in-progress: true\n\njobs:\n  validate:\n    runs-on: ubuntu-latest\n    timeout-minutes: 45\n    env:\n      APP_ENV: test\n      ALLOW_SQLITE_FOR_TESTS: "1"\n      DATABASE_URL: "sqlite+pysqlite:///:memory:"\n      DATABASE_WRITE_URL: "sqlite+pysqlite:///:memory:"\n      SECRET_KEY: training-record-redesign-validation-secret\n    steps:\n      - uses: actions/checkout@v6\n        with:\n          show-progress: false\n      - uses: actions/setup-python@v6\n        with:\n          python-version: "3.12"\n          cache: pip\n          cache-dependency-path: backend/requirements.txt\n      - name: Install backend dependencies\n        working-directory: backend\n        run: pip install --disable-pip-version-check -r requirements.txt opencv-python-headless\n      - name: Compile changed Training backend\n        working-directory: backend\n        run: python -m compileall -q amodb/apps/training scripts/reconcile_training_synthetic_recurrent.py\n      - name: Run Training domain, privacy, QR and PDF tests\n        working-directory: backend\n        run: >-\n          pytest -q\n          amodb/apps/training/tests/test_course_lifecycle.py\n          amodb/apps/training/tests/test_record_presentation.py\n          amodb/apps/training/tests/test_record_presentation_privacy_and_grouping.py\n          amodb/apps/training/tests/test_no_heuristic_course_family.py\n          amodb/apps/training/tests/test_training_record_pdf_layout.py\n          amodb/apps/training/tests/test_integration_status.py\n          amodb/apps/training/tests/test_operating_rules.py\n      - uses: actions/setup-node@v6\n        with:\n          node-version: "22"\n          cache: npm\n          cache-dependency-path: frontend/package-lock.json\n      - name: Install frontend dependencies\n        working-directory: frontend\n        run: npm ci --prefer-offline --no-audit --fund=false\n      - name: Run Training presentation unit tests\n        working-directory: frontend\n        run: npx vitest run src/utils/trainingPresentation.test.ts\n      - name: Lint changed Training frontend\n        working-directory: frontend\n        run: >-\n          npx eslint\n          src/utils/trainingPresentation.ts\n          src/utils/trainingPresentation.test.ts\n          src/components/training/TrainingRequirementList.tsx\n          src/components/training/TrainingPlanMatrix.tsx\n          src/pages/TrainingCompetencePage.tsx\n      - name: Typecheck and production build\n        working-directory: frontend\n        run: npm run build\n'''
    write(path, text)


def main() -> None:
    patch_record_presentation()
    patch_router()
    patch_compliance()
    patch_training_competence()
    patch_validation_workflow()
    Path(__file__).unlink()


if __name__ == "__main__":
    main()
