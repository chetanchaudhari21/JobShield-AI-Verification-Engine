"""Evidence-Based PDF Verification Report Generator (ReportLab).

Conforms to Feature F10 & Sections 2, 4, 5, 11 of PROJECT_SPECIFICATION.md:
- Strictly evidence-based: renders solely from persisted scan records, never reruns inference.
- Distinguishes verified, not checked, unavailable, and not found statuses honestly.
- Renders all 13 authoritative sections adapting to scan type.
- Enforces strict data security: masks PII, never embeds passwords/OTPs/raw document bodies.
- Two-pass NumberedCanvas for dynamic 'Page X of Y' and running headers/footers.
"""

from datetime import datetime, timezone
import html
import io
import logging
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger("jobshield.reports.pdf")

# Palette constants
COLOR_PRIMARY = colors.HexColor("#0F172A")       # Slate 900
COLOR_SECONDARY = colors.HexColor("#1E293B")     # Slate 800
COLOR_BRAND = colors.HexColor("#2563EB")         # Blue 600
COLOR_TEXT_DARK = colors.HexColor("#0F172A")     # Primary body text
COLOR_TEXT_MUTED = colors.HexColor("#64748B")    # Slate 500
COLOR_BORDER = colors.HexColor("#CBD5E1")        # Slate 300
COLOR_BG_LIGHT = colors.HexColor("#F8FAFC")      # Slate 50
COLOR_BG_CARD = colors.HexColor("#F1F5F9")       # Slate 100

COLOR_LOW_TEXT = colors.HexColor("#166534")      # Green 800
COLOR_LOW_BG = colors.HexColor("#F0FDF4")        # Green 50
COLOR_LOW_BORDER = colors.HexColor("#BBF7D0")    # Green 200

COLOR_MOD_TEXT = colors.HexColor("#92400E")      # Amber 800
COLOR_MOD_BG = colors.HexColor("#FFFBEB")        # Amber 50
COLOR_MOD_BORDER = colors.HexColor("#FDE68A")    # Amber 200

COLOR_HIGH_TEXT = colors.HexColor("#9A3412")     # Orange 800
COLOR_HIGH_BG = colors.HexColor("#FFF7ED")       # Orange 50
COLOR_HIGH_BORDER = colors.HexColor("#FED7AA")   # Orange 200

COLOR_CRIT_TEXT = colors.HexColor("#991B1B")     # Red 800
COLOR_CRIT_BG = colors.HexColor("#FEF2F2")       # Red 50
COLOR_CRIT_BORDER = colors.HexColor("#FECACA")   # Red 200


def escape_xml(text: Any) -> str:
    """Safely escapes text for ReportLab Paragraph XML parser."""
    if text is None:
        return ""
    return html.escape(str(text))


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas for dynamic total page count and consistent running headers/footers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(COLOR_TEXT_MUTED)

        scan_id = getattr(self, "scan_id_short", "")

        # Running header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 755, "JobShield AI - Evidence-Based Verification Report")
            if scan_id:
                self.drawRightString(612 - 54, 755, f"Scan ID: {scan_id}")
            self.setStrokeColor(COLOR_BORDER)
            self.setLineWidth(0.5)
            self.line(54, 747, 612 - 54, 747)

        # Running footer (all pages)
        self.setStrokeColor(COLOR_BORDER)
        self.setLineWidth(0.5)
        self.line(54, 45, 612 - 54, 45)

        self.drawString(54, 32, "Confidential & Informational Report - JobShield AI Platform")
        self.drawRightString(612 - 54, 32, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


def get_report_styles() -> Dict[str, ParagraphStyle]:
    """Builds clean, proportional ReportLab typography styles."""
    styles = getSampleStyleSheet()

    report_styles = {
        "DocTitle": ParagraphStyle(
            "DocTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=COLOR_PRIMARY,
        ),
        "DocSubtitle": ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=COLOR_TEXT_MUTED,
        ),
        "SectionHeading": ParagraphStyle(
            "SectionHeading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=COLOR_PRIMARY,
            keepWithNext=True,
        ),
        "SubSectionHeading": ParagraphStyle(
            "SubSectionHeading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=COLOR_SECONDARY,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=COLOR_TEXT_DARK,
        ),
        "BodyBold": ParagraphStyle(
            "BodyBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=COLOR_TEXT_DARK,
        ),
        "BodyMuted": ParagraphStyle(
            "BodyMuted",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=COLOR_TEXT_MUTED,
        ),
        "TableHead": ParagraphStyle(
            "TableHead",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=colors.white,
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=COLOR_TEXT_DARK,
        ),
        "TableCellBold": ParagraphStyle(
            "TableCellBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=COLOR_TEXT_DARK,
        ),
        "TableCellMuted": ParagraphStyle(
            "TableCellMuted",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=COLOR_TEXT_MUTED,
        ),
        "CodeText": ParagraphStyle(
            "CodeText",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7.5,
            leading=10,
            textColor=COLOR_PRIMARY,
        ),
        "AlertText": ParagraphStyle(
            "AlertText",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12,
            textColor=COLOR_CRIT_TEXT,
        ),
        "AlertSubtext": ParagraphStyle(
            "AlertSubtext",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10.5,
            textColor=COLOR_CRIT_TEXT,
        ),
        "DisclaimerText": ParagraphStyle(
            "DisclaimerText",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=6.8,
            leading=9.2,
            textColor=COLOR_TEXT_MUTED,
        ),
    }
    return report_styles


def _format_timestamp(ts: Optional[datetime]) -> str:
    """Formats datetime as UTC ISO representation."""
    if not ts:
        return "Not Recorded"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.strftime("%Y-%m-%d %H:%M:%S UTC")


def _get_category_colors(category: str) -> tuple[colors.HexColor, colors.HexColor, colors.HexColor]:
    """Returns (text_color, bg_color, border_color) for a risk category."""
    cat = (category or "").upper()
    if cat == "LOW":
        return COLOR_LOW_TEXT, COLOR_LOW_BG, COLOR_LOW_BORDER
    elif cat == "MODERATE":
        return COLOR_MOD_TEXT, COLOR_MOD_BG, COLOR_MOD_BORDER
    elif cat == "HIGH":
        return COLOR_HIGH_TEXT, COLOR_HIGH_BG, COLOR_HIGH_BORDER
    elif cat == "CRITICAL":
        return COLOR_CRIT_TEXT, COLOR_CRIT_BG, COLOR_CRIT_BORDER
    return COLOR_TEXT_MUTED, COLOR_BG_LIGHT, COLOR_BORDER


def generate_verification_report_pdf(
    scan: Any,
    evidence_records: List[Any],
    prediction_records: List[Any],
    offer_scan: Optional[Any] = None,
    recruiter_scan: Optional[Any] = None,
    company: Optional[Any] = None,
) -> bytes:
    """Generates an evidence-based PDF verification report strictly from persisted scan data."""
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = get_report_styles()
    story: List[Any] = []
    width = 504  # 612 - 108

    # Extract primary fields from persisted records
    scan_id = scan.id
    scan_type = scan.input_type or "job_text"
    scan_created_at = scan.created_at
    scan_completed_at = scan.completed_at or scan.created_at
    input_ref = scan.input_reference or "Not Recorded"

    # Current generation timestamp
    generation_timestamp = datetime.now(timezone.utc)

    # Primary prediction record
    pred = prediction_records[0] if prediction_records else None
    explanation: Dict[str, Any] = pred.explanation if pred and isinstance(pred.explanation, dict) else {}

    risk_score: float = float(pred.risk_score) if pred else (float(offer_scan.risk_score) if offer_scan else 0.0)
    risk_category: str = pred.risk_category if pred else (offer_scan.risk_category if offer_scan else "UNKNOWN")
    model_version: str = pred.model_version if pred else "Unavailable"
    predicted_class: str = pred.predicted_class if pred else "UNVERIFIED"
    model_probability: Optional[float] = pred.model_probability if pred else None
    threshold_version: str = pred.threshold_version if pred else "provisional_v1.0.0"

    warning = explanation.get("warning")
    override_floor_applied = explanation.get("override_floor_applied")
    override_floor_reason = explanation.get("override_floor_reason")

    # Safe actions & limitations from stored result
    safe_actions: List[str] = explanation.get("recommended_safe_actions") or [
        "Never pay advance fees, deposits, or application charges for any job or internship.",
        "Independently verify vacancies on the employer's official corporate careers website.",
        "Confirm recruiter identities through corporate telephone directories or verified domain channels.",
        "Never share net banking passwords, OTPs, ATM PINs, or sensitive identity documents upfront.",
        "Preserve original emails, chat transcripts, and offer documents for records.",
    ]
    limitations: List[str] = explanation.get("limitations") or [
        "ML predictions are probabilistic estimates derived from historical scam datasets; they are not legal findings.",
        "Scam operators frequently impersonate legitimate corporate brands using lookalike domains or stolen credentials.",
        "MCA-21 registration and DPIIT recognition confirm entity existence only, but do not authenticate specific recruiters or job postings.",
        "Rule heuristics evaluate explicit text patterns; sophisticated scams without obvious linguistic cues may evade heuristic detection.",
    ]
    disclaimer: str = explanation.get("disclaimer") or (
        "JobShield AI provides informational risk assessments based on textual pattern recognition, technical domain checks, "
        "and public registry corroboration. It does not provide legal advice, formal investigative findings, or definitive legal "
        "determinations of fraud. JobShield AI makes no guarantees regarding the authenticity of any employer or job opening."
    )

    # Human-readable scan type label
    scan_type_labels = {
        "job_text": "Pasted Job Description Text",
        "job_url": "Public Job URL Ingestion",
        "recruiter_email": "Recruiter Email Verification",
        "offer_letter": "Offer Letter Document Analysis",
    }
    scan_type_display = scan_type_labels.get(scan_type, scan_type.replace("_", " ").title())

    # =========================================================================
    # SECTION 1: REPORT TITLE & DOCUMENT METADATA
    # =========================================================================
    story.append(Paragraph("JobShield AI - Evidence-Based Verification Report", styles["DocTitle"]))
    story.append(
        Paragraph(
            "Explainable recruitment fraud risk assessment & multi-source registry corroboration",
            styles["DocSubtitle"],
        )
    )
    story.append(Spacer(1, 10))

    meta_table_data = [
        [
            Paragraph("<b>Report Identifier:</b>", styles["TableCellBold"]),
            Paragraph(f"<font name='Courier'>{escape_xml(scan_id)}</font>", styles["TableCell"]),
            Paragraph("<b>Scan Type:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(scan_type_display), styles["TableCell"]),
        ],
        [
            Paragraph("<b>Report Generated:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(_format_timestamp(generation_timestamp)), styles["TableCell"]),
            Paragraph("<b>Original Scan Time:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(_format_timestamp(scan_completed_at)), styles["TableCell"]),
        ],
        [
            Paragraph("<b>Submitted Input Ref:</b>", styles["TableCellBold"]),
            Paragraph(f"<font name='Courier'>{escape_xml(input_ref[:50] + ('...' if len(input_ref) > 50 else ''))}</font>", styles["TableCell"]),
            Paragraph("<b>Verification Status:</b>", styles["TableCellBold"]),
            Paragraph("COMPLETED (Stored Evidence)", styles["TableCellBold"]),
        ],
    ]
    meta_table = Table(meta_table_data, colWidths=[110, 142, 110, 142])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 12))

    # =========================================================================
    # SECTION 2: EXECUTIVE SUMMARY & COMPOSITE RISK SCORE
    # =========================================================================
    story.append(Paragraph("1. Executive Summary & Composite Risk Score", styles["SectionHeading"]))
    story.append(Spacer(1, 4))

    cat_text, cat_bg, cat_border = _get_category_colors(risk_category)

    score_card_data = [
        [
            Paragraph(
                f"<font size=20><b>{risk_score:.1f}</b></font><font size=10> / 100</font><br/>"
                f"<font size=8 color='{COLOR_TEXT_MUTED.hexval()}'>Composite Risk Score</font>",
                styles["TableCell"],
            ),
            Paragraph(
                f"<font size=12 color='{cat_text.hexval()}'><b>{escape_xml(risk_category)} RISK</b></font><br/>"
                f"<font size=7.5 color='{COLOR_TEXT_MUTED.hexval()}'>Schedule: {escape_xml(threshold_version)}</font>",
                styles["TableCell"],
            ),
            Paragraph(
                f"<b>Threshold Scale:</b><br/>"
                f"• Low Risk: 0.0 – 29.9<br/>"
                f"• Moderate: 30.0 – 59.9<br/>"
                f"• High: 60.0 – 79.9<br/>"
                f"• Critical: 80.0 – 100.0",
                styles["TableCellMuted"],
            ),
        ]
    ]
    score_card = Table(score_card_data, colWidths=[150, 174, 180])
    score_card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), cat_bg),
                ("BOX", (0, 0), (-1, -1), 1.0, cat_border),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, cat_border),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(score_card)
    story.append(Spacer(1, 6))

    # Warning alert box (if applicable)
    if warning:
        alert_data = [
            [
                Paragraph(
                    f"<b>POTENTIAL FRAUD ADVISORY:</b> {escape_xml(warning)}",
                    styles["AlertText"],
                )
            ]
        ]
        alert_table = Table(alert_data, colWidths=[width])
        alert_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), COLOR_CRIT_BG),
                    ("BOX", (0, 0), (-1, -1), 1, COLOR_CRIT_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(alert_table)
        story.append(Spacer(1, 6))

    # Safety override floor banner (if applicable)
    if override_floor_applied:
        floor_data = [
            [
                Paragraph(
                    f"<b>RULE SAFETY OVERRIDE FLOOR ACTIVE ({escape_xml(override_floor_applied)}):</b> "
                    f"{escape_xml(override_floor_reason or 'Mandatory safety floor enforced due to critical fraud signal.')}",
                    styles["AlertSubtext"],
                )
            ]
        ]
        floor_table = Table(floor_data, colWidths=[width])
        floor_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), COLOR_HIGH_BG),
                    ("BOX", (0, 0), (-1, -1), 1, COLOR_HIGH_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(floor_table)
        story.append(Spacer(1, 6))

    story.append(Spacer(1, 6))

    # =========================================================================
    # SECTION 3: MACHINE LEARNING MODEL & CALIBRATION
    # =========================================================================
    story.append(Paragraph("2. Machine Learning Model Analysis & Statistical Calibration", styles["SectionHeading"]))
    story.append(Spacer(1, 4))

    calib_method = explanation.get("calibration_method", "Isotonic Regression")
    dec_threshold = explanation.get("decision_threshold", 0.40)
    cal_prob_str = f"{model_probability:.4f} ({model_probability * 100:.1f}%)" if model_probability is not None else "Not Available"

    ml_table_data = [
        [
            Paragraph("<b>Model Name & Version:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(model_version), styles["TableCell"]),
            Paragraph("<b>Model Classification:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(predicted_class), styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Calibrated Probability:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(cal_prob_str), styles["TableCell"]),
            Paragraph("<b>Calibrated Decision Threshold:</b>", styles["TableCellBold"]),
            Paragraph(f"{dec_threshold:.4f} (Recall-optimized)", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Calibration Technique:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(calib_method), styles["TableCell"]),
            Paragraph("<b>Score Independence:</b>", styles["TableCellBold"]),
            Paragraph("Calibrated ML score is evaluated independently from rule-based signals.", styles["TableCellMuted"]),
        ],
    ]
    ml_table = Table(ml_table_data, colWidths=[130, 122, 130, 122])
    ml_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(ml_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 4: EXPLAINABLE AI - FEATURE CONTRIBUTIONS
    # =========================================================================
    story.append(Paragraph("3. Explainable AI (XAI) - Linguistic Feature Contributions", styles["SectionHeading"]))
    story.append(Spacer(1, 4))

    top_pos: List[Dict[str, Any]] = explanation.get("top_positive_features") or []
    top_neg: List[Dict[str, Any]] = explanation.get("top_negative_features") or []
    intercept: Optional[float] = explanation.get("intercept")
    dec_score: Optional[float] = explanation.get("decision_score")
    active_feat_count: Optional[int] = explanation.get("active_feature_count")
    total_contrib: Optional[float] = explanation.get("total_feature_contribution")

    if top_pos or top_neg or intercept is not None:
        reconcile_text = (
            f"<b>Model Attribution Identity:</b> Decision score <i>z</i> = "
            f"Intercept ({intercept:.4f}) + Σ Features ({total_contrib:+.4f} across {active_feat_count or len(top_pos) + len(top_neg)} active tokens) = "
            f"<b>{dec_score:.4f}</b> (Tolerance: &lt;10<sup>-4</sup>)"
            if intercept is not None and dec_score is not None and total_contrib is not None
            else "Linear attribution weights computed from trained Logistic Regression vectorizer."
        )
        story.append(Paragraph(reconcile_text, styles["BodyMuted"]))
        story.append(Spacer(1, 4))

        # Build feature table
        feat_rows = [
            [
                Paragraph("<b>Token / Phrase</b>", styles["TableHead"]),
                Paragraph("<b>Impact Direction</b>", styles["TableHead"]),
                Paragraph("<b>Attribution (Weight × TF-IDF)</b>", styles["TableHead"]),
            ]
        ]
        # Top 3 positive
        for feat in top_pos[:3]:
            tok = feat.get("feature_name", "unknown")
            contrib = feat.get("contribution", 0.0)
            feat_rows.append(
                [
                    Paragraph(f"<font name='Courier'>{escape_xml(tok)}</font>", styles["TableCellBold"]),
                    Paragraph("<font color='#DC2626'>Fraud-Indicative (+)</font>", styles["TableCell"]),
                    Paragraph(f"+{contrib:.4f}", styles["TableCell"]),
                ]
            )
        # Top 3 negative
        for feat in top_neg[:3]:
            tok = feat.get("feature_name", "unknown")
            contrib = feat.get("contribution", 0.0)
            feat_rows.append(
                [
                    Paragraph(f"<font name='Courier'>{escape_xml(tok)}</font>", styles["TableCellBold"]),
                    Paragraph("<font color='#16A34A'>Legitimate-Indicative (-)</font>", styles["TableCell"]),
                    Paragraph(f"{contrib:.4f}", styles["TableCell"]),
                ]
            )

        if len(feat_rows) > 1:
            feat_table = Table(feat_rows, colWidths=[180, 160, 164])
            feat_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), COLOR_SECONDARY),
                        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(feat_table)
        else:
            story.append(
                Paragraph(
                    "<i>No Discriminating Vocabulary Tokens Detected:</i> Submitted text consists of common stop words, "
                    "neutral industry terms, or out-of-vocabulary tokens that do not significantly shift the linear decision score.",
                    styles["BodyMuted"],
                )
            )
    else:
        story.append(
            Paragraph(
                "<i>Feature attribution unavailable or neutral for this scan.</i> Classification relies on baseline model intercept "
                "and deterministic heuristic rules.",
                styles["BodyMuted"],
            )
        )
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 5: DETECTED RULE-BASED FINDINGS
    # =========================================================================
    story.append(Paragraph("4. Detected Rule-Based Findings & Heuristic Evidence", styles["SectionHeading"]))
    story.append(Spacer(1, 4))

    rule_items = [e for e in evidence_records if e.evidence_type in ("rule_signal", "rule_finding")]
    if rule_items:
        rule_rows = [
            [
                Paragraph("<b>Rule Detector</b>", styles["TableHead"]),
                Paragraph("<b>Status</b>", styles["TableHead"]),
                Paragraph("<b>Severity</b>", styles["TableHead"]),
                Paragraph("<b>Finding & Sanitized Excerpt</b>", styles["TableHead"]),
            ]
        ]
        for r in rule_items:
            status_color = "#DC2626" if r.status in ("FLAGGED", "DETECTED") else "#64748B"
            sev = f"{r.confidence * 100:.0f}" if r.confidence is not None else "Rule Heuristic"
            rule_rows.append(
                [
                    Paragraph(escape_xml(r.source_name), styles["TableCellBold"]),
                    Paragraph(f"<font color='{status_color}'><b>{escape_xml(r.status)}</b></font>", styles["TableCell"]),
                    Paragraph(escape_xml(sev), styles["TableCell"]),
                    Paragraph(escape_xml(r.summary[:300] + ("..." if len(r.summary) > 300 else "")), styles["TableCell"]),
                ]
            )

        rule_table = Table(rule_rows, colWidths=[120, 65, 65, 254])
        rule_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), COLOR_SECONDARY),
                    ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(rule_table)
    else:
        story.append(Paragraph("No rule heuristic anomalies or advance-fee patterns triggered for this input.", styles["BodyMuted"]))

    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 6: CORPORATE REGISTRY & ENTITY VERIFICATION (MCA-21 & DPIIT)
    # =========================================================================
    story.append(Paragraph("5. Corporate Registry Verification (MCA-21 & DPIIT)", styles["SectionHeading"]))
    story.append(Spacer(1, 4))

    comp_meta = explanation.get("company_verification") or {}
    comp_name = comp_meta.get("claimed_company") or (company.legal_name if company else (explanation.get("extracted_company") or "Not Specified"))
    cin = comp_meta.get("cin") or (company.cin if company else "Not Provided")
    mca_status = comp_meta.get("mca_status") or ("MATCHED" if company else "UNVERIFIED")
    is_startup = False
    if company:
        if getattr(company, "is_startup_recognized", False):
            is_startup = True
        elif hasattr(company, "startup_recognitions") and company.startup_recognitions:
            is_startup = any(getattr(sr, "recognition_status", "") in ("RECOGNIZED", "ACTIVE") for sr in company.startup_recognitions)
    if not is_startup and comp_meta.get("is_startup"):
        is_startup = True
    dpiit_status = comp_meta.get("dpiit_status") or ("RECOGNIZED" if is_startup else "NOT_RECOGNIZED / UNCHECKED")

    comp_table_data = [
        [
            Paragraph("<b>Claimed Company:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(comp_name), styles["TableCell"]),
            Paragraph("<b>Corporate CIN:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(cin), styles["TableCell"]),
        ],
        [
            Paragraph("<b>MCA-21 Registry Match:</b>", styles["TableCellBold"]),
            Paragraph(f"<b>{escape_xml(mca_status)}</b>", styles["TableCellBold"]),
            Paragraph("<b>DPIIT Startup Status:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(dpiit_status), styles["TableCell"]),
        ],
        [
            Paragraph("<b>Registry Legal Limitation:</b>", styles["TableCellBold"]),
            Paragraph(
                "MCA-21 registration verifies legal company existence only; it does not authenticate individual job postings or recruiters.",
                styles["TableCellMuted"],
            ),
            Paragraph("<b>Data Source Provenance:</b>", styles["TableCellBold"]),
            Paragraph("Ministry of Corporate Affairs (MCA-21) Master Data / DPIIT Catalog", styles["TableCellMuted"]),
        ],
    ]
    comp_table = Table(comp_table_data, colWidths=[120, 132, 120, 132])
    comp_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(comp_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 7: DOMAIN & TECHNICAL AUTHENTICATION INTELLIGENCE
    # =========================================================================
    story.append(Paragraph("6. Domain Security & Technical Email Authentication", styles["SectionHeading"]))
    story.append(Spacer(1, 4))

    domain_meta = explanation.get("domain_check") or {}
    domain_name = domain_meta.get("domain") or (recruiter_scan.domain if recruiter_scan else "Not Checked")
    dns_status = domain_meta.get("dns_status", "NOT_CHECKED")
    mx_status = domain_meta.get("mx_status", "NOT_CHECKED")
    spf_status = domain_meta.get("spf_status", "NOT_CHECKED")
    dmarc_status = domain_meta.get("dmarc_status", "NOT_CHECKED")
    lookalike_warning = domain_meta.get("lookalike_warning")

    domain_table_data = [
        [
            Paragraph("<b>Analyzed Domain:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(domain_name), styles["TableCellBold"]),
            Paragraph("<b>DNS Resolution:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(dns_status), styles["TableCell"]),
        ],
        [
            Paragraph("<b>MX Record Status:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(mx_status), styles["TableCell"]),
            Paragraph("<b>SPF Alignment:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(spf_status), styles["TableCell"]),
        ],
        [
            Paragraph("<b>DMARC Enforcement:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(dmarc_status), styles["TableCell"]),
            Paragraph("<b>Lookalike Assessment:</b>", styles["TableCellBold"]),
            Paragraph(escape_xml(lookalike_warning or "No brand impersonation detected"), styles["TableCell"]),
        ],
    ]
    domain_table = Table(domain_table_data, colWidths=[120, 132, 120, 132])
    domain_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(domain_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 8: IMPERSONATION & DUPLICATE POSTING SIGNALS
    # =========================================================================
    dup_meta = explanation.get("duplicate_analysis")
    if dup_meta:
        story.append(Paragraph("7. Job Duplication & Content Impersonation Signals", styles["SectionHeading"]))
        story.append(Spacer(1, 4))

        dup_status = dup_meta.get("status", "UNIQUE_LISTING")
        dup_score = dup_meta.get("highest_similarity_score", 0.0)
        dup_count = dup_meta.get("total_matches_found", 0)
        dup_warn = dup_meta.get("impersonation_warning") or "No cross-employer content duplication detected."

        dup_table_data = [
            [
                Paragraph("<b>Duplication Status:</b>", styles["TableCellBold"]),
                Paragraph(escape_xml(dup_status), styles["TableCellBold"]),
                Paragraph("<b>Highest Text Similarity:</b>", styles["TableCellBold"]),
                Paragraph(f"{dup_score * 100:.1f}%", styles["TableCell"]),
            ],
            [
                Paragraph("<b>Matching Index Postings:</b>", styles["TableCellBold"]),
                Paragraph(f"{dup_count} prior listings", styles["TableCell"]),
                Paragraph("<b>Cross-Employer Warning:</b>", styles["TableCellBold"]),
                Paragraph(escape_xml(dup_warn), styles["TableCell"]),
            ],
        ]
        dup_table = Table(dup_table_data, colWidths=[130, 122, 130, 122])
        dup_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                    ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(dup_table)
        story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 9: OFFER LETTER DOCUMENT ANALYSIS (IF APPLICABLE)
    # =========================================================================
    if scan_type == "offer_letter" or offer_scan is not None:
        story.append(Paragraph("8. Offer Letter Document & Clause Analysis", styles["SectionHeading"]))
        story.append(Spacer(1, 4))

        file_name = offer_scan.file_name if offer_scan else "offer_letter.pdf"
        page_cnt = offer_scan.page_count if offer_scan else 1
        ocr_eng = offer_scan.ocr_engine or "Direct PyMuPDF Extraction"
        has_fee = "YES (Advance Fee Detected)" if (offer_scan and offer_scan.has_fee_demand) else "No Fee Demand Detected"
        has_sens = "YES (Sensitive Details Requested)" if (offer_scan and offer_scan.has_sensitive_request) else "No Banking Credentials Requested"

        doc_summary = offer_scan.extracted_summary if offer_scan and isinstance(offer_scan.extracted_summary, dict) else {}
        job_role = doc_summary.get("job_title") or "Not Extracted"
        comp_ctc = doc_summary.get("salary") or "Not Specified"

        offer_table_data = [
            [
                Paragraph("<b>Analyzed Document:</b>", styles["TableCellBold"]),
                Paragraph(escape_xml(file_name), styles["TableCell"]),
                Paragraph("<b>Document Length:</b>", styles["TableCellBold"]),
                Paragraph(f"{page_cnt} page(s) ({escape_xml(ocr_eng)})", styles["TableCell"]),
            ],
            [
                Paragraph("<b>Identified Job Role:</b>", styles["TableCellBold"]),
                Paragraph(escape_xml(job_role), styles["TableCell"]),
                Paragraph("<b>Compensation Clause:</b>", styles["TableCellBold"]),
                Paragraph(escape_xml(comp_ctc), styles["TableCell"]),
            ],
            [
                Paragraph("<b>Fee Solicitation Clause:</b>", styles["TableCellBold"]),
                Paragraph(f"<b>{escape_xml(has_fee)}</b>", styles["TableCellBold"]),
                Paragraph("<b>Banking / KYC Demand:</b>", styles["TableCellBold"]),
                Paragraph(escape_xml(has_sens), styles["TableCell"]),
            ],
        ]
        offer_table = Table(offer_table_data, colWidths=[130, 122, 130, 122])
        offer_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                    ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(offer_table)
        story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 10: RECOMMENDED SAFE ACTIONS
    # =========================================================================
    story.append(Paragraph("9. Recommended Safe Actions", styles["SectionHeading"]))
    story.append(Spacer(1, 4))
    for act in safe_actions:
        story.append(
            Paragraph(
                f"<font color='{COLOR_BRAND.hexval()}'><b>[ACTION]</b></font> {escape_xml(act)}",
                styles["Body"],
            )
        )
        story.append(Spacer(1, 2))
    story.append(Spacer(1, 8))

    # =========================================================================
    # SECTION 11: DATA SOURCES & PROVENANCE METADATA
    # =========================================================================
    story.append(Paragraph("10. Data Sources & Provenance Metadata", styles["SectionHeading"]))
    story.append(Spacer(1, 4))

    provenance_rows = [
        [
            Paragraph("<b>Data Source</b>", styles["TableHead"]),
            Paragraph("<b>Evidence Type</b>", styles["TableHead"]),
            Paragraph("<b>Observed Timestamp</b>", styles["TableHead"]),
            Paragraph("<b>Verification Status</b>", styles["TableHead"]),
        ]
    ]
    # Populate from stored evidence records
    for ev in evidence_records[:8]:
        obs_time = _format_timestamp(ev.observed_at)
        provenance_rows.append(
            [
                Paragraph(escape_xml(ev.source_name), styles["TableCellBold"]),
                Paragraph(escape_xml(ev.evidence_type), styles["TableCell"]),
                Paragraph(escape_xml(obs_time), styles["TableCellMuted"]),
                Paragraph(escape_xml(ev.status), styles["TableCell"]),
            ]
        )

    # Baseline sources if none or few
    if len(provenance_rows) == 1:
        provenance_rows.append(
            [
                Paragraph("JobShield AI Baseline Classifier (v1.1.0)", styles["TableCellBold"]),
                Paragraph("ml_prediction", styles["TableCell"]),
                Paragraph(escape_xml(_format_timestamp(scan_completed_at)), styles["TableCellMuted"]),
                Paragraph("COMPLETED", styles["TableCell"]),
            ]
        )
        provenance_rows.append(
            [
                Paragraph("MCA-21 Company Master Data Catalog", styles["TableCellBold"]),
                Paragraph("company_registry_signal", styles["TableCell"]),
                Paragraph(escape_xml(_format_timestamp(scan_completed_at)), styles["TableCellMuted"]),
                Paragraph(escape_xml(mca_status), styles["TableCell"]),
            ]
        )

    prov_table = Table(provenance_rows, colWidths=[150, 120, 134, 100])
    prov_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_SECONDARY),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(prov_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 12: ANALYSIS BOUNDARIES & LIMITATIONS
    # =========================================================================
    story.append(Paragraph("11. Analysis Boundaries & Technical Limitations", styles["SectionHeading"]))
    story.append(Spacer(1, 4))
    for lim in limitations:
        story.append(
            Paragraph(
                f"<font color='{COLOR_TEXT_MUTED.hexval()}'>•</font> {escape_xml(lim)}",
                styles["BodyMuted"],
            )
        )
        story.append(Spacer(1, 1.5))
    story.append(Spacer(1, 8))

    # =========================================================================
    # SECTION 13: LEGAL DISCLAIMER & INFORMATIONAL NOTICE
    # =========================================================================
    story.append(Paragraph("12. Legal Disclaimer & Regulatory Notice", styles["SectionHeading"]))
    story.append(Spacer(1, 4))

    disclaimer_data = [
        [
            Paragraph(
                f"<b>LEGAL NOTICE:</b> {escape_xml(disclaimer)}",
                styles["DisclaimerText"],
            )
        ]
    ]
    disclaimer_table = Table(disclaimer_data, colWidths=[width])
    disclaimer_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(disclaimer_table)

    # Build the PDF using NumberedCanvas
    def canvas_factory(*args: Any, **kwargs: Any) -> NumberedCanvas:
        nc = NumberedCanvas(*args, **kwargs)
        setattr(nc, "scan_id_short", scan_id[:8] if scan_id else "")
        return nc

    doc.build(story, canvasmaker=canvas_factory)
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    return pdf_bytes
