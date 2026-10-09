"""Generate Word report for solar pumping station sizing."""

import io
import datetime
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from calculations import (
    PanelSpecs, InverterSpecs, MotorSpecs, EnvironmentSpecs,
    PVConfig, SizingResult, CheckResult,
)


def set_cell_shading(cell, color):
    shading = OxmlElement('w:shd')
    shading.set(qn('w:fill'), color)
    shading.set(qn('w:val'), 'clear')
    cell._tc.get_or_add_tcPr().append(shading)


def add_table(doc, headers, rows, verdict_col=None):
    """Add a formatted table to the document."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for j, h in enumerate(headers):
        cell = table.rows[0].cells[j]
        cell.text = h
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.bold = True
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(255, 255, 255)
        set_cell_shading(cell, '003366')

    for i, row_data in enumerate(rows):
        for j, val in enumerate(row_data):
            cell = table.rows[i + 1].cells[j]
            cell.text = str(val)
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in p.runs:
                    run.font.size = Pt(9)

            if verdict_col is not None and j == verdict_col:
                v = str(val).upper()
                if 'NON CONFORME' in v or 'RISQUE' in v:
                    set_cell_shading(cell, 'FFCCCC')
                    for p in cell.paragraphs:
                        for run in p.runs:
                            run.font.color.rgb = RGBColor(180, 0, 0)
                            run.bold = True
                elif 'LIMITE' in v:
                    set_cell_shading(cell, 'FFF2CC')
                    for p in cell.paragraphs:
                        for run in p.runs:
                            run.font.color.rgb = RGBColor(180, 120, 0)
                            run.bold = True
                elif 'OK' in v or 'EXCELLENT' in v or 'CONFORME' in v:
                    set_cell_shading(cell, 'D9F2D9')
                    for p in cell.paragraphs:
                        for run in p.runs:
                            run.font.color.rgb = RGBColor(0, 120, 0)
                            run.bold = True
            else:
                if i % 2 == 0:
                    set_cell_shading(cell, 'E8F0FE')

    doc.add_paragraph()
    return table


def generate_report(
    stations: list,
    installation_diagrams: dict = None,
    wiring_diagrams: dict = None,
) -> io.BytesIO:
    """
    Generate a Word report for one or more stations.

    stations: list of dicts with keys:
        name, panel, inverter, motor, env, config, result
    installation_diagrams: dict of {station_name: BytesIO}
    wiring_diagrams: dict of {station_name: BytesIO}
    """
    doc = Document()

    # Styles
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(10)
    for i in range(1, 4):
        doc.styles[f'Heading {i}'].font.color.rgb = RGBColor(0, 51, 102)
        doc.styles[f'Heading {i}'].font.name = 'Calibri'

    # === COVER PAGE ===
    for _ in range(5):
        doc.add_paragraph()
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("RAPPORT DE DIMENSIONNEMENT")
    r.bold = True
    r.font.size = Pt(26)
    r.font.color.rgb = RGBColor(0, 51, 102)

    s = doc.add_paragraph()
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = s.add_run("Stations de Pompage Solaire Off-Grid")
    r.font.size = Pt(16)
    r.font.color.rgb = RGBColor(0, 102, 153)

    doc.add_paragraph()
    for label, value in [
        ("Date", datetime.date.today().strftime("%d/%m/%Y")),
        ("Stations", f"{len(stations)} station(s) analysee(s)"),
    ]:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(f"{label} : ")
        r.bold = True
        r.font.size = Pt(12)
        p.add_run(value).font.size = Pt(12)

    doc.add_page_break()

    # === EACH STATION ===
    for idx, st in enumerate(stations):
        name = st['name']
        panel: PanelSpecs = st['panel']
        inverter: InverterSpecs = st['inverter']
        motor: MotorSpecs = st['motor']
        env: EnvironmentSpecs = st['env']
        config: PVConfig = st['config']
        result: SizingResult = st['result']

        doc.add_heading(f"{name} - Analyse de dimensionnement", level=1)

        # Overall verdict
        p = doc.add_paragraph()
        r = p.add_run(f"Verdict global : {result.overall_verdict}")
        r.bold = True
        r.font.size = Pt(14)
        if result.overall_verdict == "CONFORME":
            r.font.color.rgb = RGBColor(0, 120, 0)
        elif result.overall_verdict == "NON CONFORME":
            r.font.color.rgb = RGBColor(180, 0, 0)
        else:
            r.font.color.rgb = RGBColor(180, 120, 0)

        # Configuration
        doc.add_heading("Configuration", level=2)
        add_table(doc,
            ['Element', 'Specification'],
            [
                ['Moteur', f'{motor.power_kw:.1f} kW / {motor.current_a:.0f} A'],
                ['Panneaux PV', f'{panel.model} - {panel.pmax_w:.0f} Wc'
                 + (' bifacial' if panel.bifacial else ' mono')],
                ['Configuration PV',
                 f'{config.num_strings} string(s) x {config.panels_per_string} panneaux'],
                ['Total panneaux', f'{config.total_panels}'],
                ['Puissance crete', f'{result.total_power_w/1000:.2f} kWc'],
                ['Variateur', f'{inverter.model} - {inverter.power_kw:.0f} kW'],
                ['Temperature', f'{env.temp_min_c:.0f} C a {env.temp_max_c:.0f} C'],
            ]
        )

        # PV characteristics
        doc.add_heading("Caracteristiques du champ PV", level=2)
        add_table(doc,
            ['Parametre', 'Valeur STC', 'Min (chaud)', 'Max (froid)'],
            [
                ['Voc (V)', f'{result.voc_stc:.1f}', '-', f'{result.voc_max_cold:.1f}'],
                ['Vmp (V)', f'{result.vmp_stc:.1f}', f'{result.vmp_min_hot:.1f}', '-'],
                ['Isc (A)', f'{result.isc_stc:.2f}',
                 '-', f'{result.isc_max_hot:.2f}'],
                ['Imp (A)', f'{result.imp_stc:.2f}', '-', '-'],
                ['Puissance (kWc)', f'{result.total_power_w/1000:.2f}', '-', '-'],
            ]
        )

        if panel.bifacial:
            doc.add_paragraph(
                f"Avec gain bifacial estime de {env.bifacial_gain_pct:.0f}% : "
                f"Isc = {result.isc_bifacial:.2f} A, Imp = {result.imp_bifacial:.2f} A"
            )

        # Ratios
        doc.add_heading("Ratios de dimensionnement", level=2)
        add_table(doc,
            ['Ratio', 'Valeur', 'Plage ideale'],
            [
                ['PV / Variateur', f'{result.ratio_pv_inverter:.2f}x', '1.2x - 1.6x'],
                ['PV / Moteur', f'{result.ratio_pv_motor:.2f}x', '1.3x - 2.0x'],
                ['Sortie variateur / Moteur',
                 f'{result.ratio_inverter_motor_current:.2f}x', '> 1.0x'],
            ]
        )

        # Checks table
        doc.add_heading("Verifications de compatibilite", level=2)
        check_rows = []
        for c in result.checks:
            check_rows.append([c.name, c.calculated_str, c.limit_str, c.verdict, c.detail])
        add_table(doc,
            ['Verification', 'Calcule', 'Limite', 'Verdict', 'Detail'],
            check_rows,
            verdict_col=3
        )

        # Recommended range
        doc.add_heading("Plages recommandees", level=2)
        doc.add_paragraph(
            f"Nombre de panneaux par string : "
            f"{result.recommended_panels_per_string_min} a "
            f"{result.recommended_panels_per_string_max} "
            f"(actuel: {config.panels_per_string})"
        )
        doc.add_paragraph(
            f"Nombre max de strings : {result.recommended_max_strings} "
            f"(actuel: {config.num_strings})"
        )

        # Installation diagram
        if installation_diagrams and name in installation_diagrams:
            doc.add_heading("Schema d'installation", level=2)
            installation_diagrams[name].seek(0)
            doc.add_picture(installation_diagrams[name], width=Inches(6.5))

        # Wiring diagram
        if wiring_diagrams and name in wiring_diagrams:
            doc.add_heading("Schema de cablage", level=2)
            wiring_diagrams[name].seek(0)
            doc.add_picture(wiring_diagrams[name], width=Inches(6.5))

        if idx < len(stations) - 1:
            doc.add_page_break()

    # Save to buffer
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
