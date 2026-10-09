"""SolarPumpSizer - Application de dimensionnement de stations de pompage solaire off-grid."""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from calculations import (
    MotorSpecs, PanelSpecs, InverterSpecs, EnvironmentSpecs,
    PVConfig, SizingResult, compute_optimal_config, run_sizing,
)
from diagrams import generate_installation_diagram, generate_wiring_diagram
from report import generate_report
from pdf_extractor import (
    extract_panel_specs, extract_inverter_specs, extract_motor_specs,
    ExtractedPanelSpecs, ExtractedInverterSpecs, ExtractedMotorSpecs,
)

# --- Page config ---
st.set_page_config(
    page_title="SolarPumpSizer",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CSS ---
st.markdown("""
<style>
    .main-title { font-size: 2.2rem; font-weight: 700; color: #003366; text-align: center; }
    .sub-title { font-size: 1rem; color: #666; text-align: center; margin-bottom: 2rem; }
    .verdict-ok { background: #d4edda; color: #155724; padding: 10px 20px; border-radius: 8px;
                  font-weight: bold; font-size: 1.1rem; text-align: center; }
    .verdict-warn { background: #fff3cd; color: #856404; padding: 10px 20px; border-radius: 8px;
                    font-weight: bold; font-size: 1.1rem; text-align: center; }
    .verdict-fail { background: #f8d7da; color: #721c24; padding: 10px 20px; border-radius: 8px;
                    font-weight: bold; font-size: 1.1rem; text-align: center; }
    div[data-testid="stSidebar"] { background-color: #f0f4f8; }
    .extraction-ok { color: #155724; font-weight: bold; }
    .extraction-missing { color: #856404; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- Title ---
st.markdown('<p class="main-title">☀️ SolarPumpSizer</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Dimensionnement de stations de pompage solaire off-grid<br>'
            'Importez vos fiches techniques PDF (toutes marques) ou saisissez les specs manuellement</p>',
            unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Configuration generale")
    num_stations = st.number_input("Nombre de stations", min_value=1, max_value=10, value=1, step=1)
    st.divider()
    st.header("🌡️ Environnement")
    temp_min = st.number_input("Temperature min ambiante (°C)", value=-10.0, step=1.0)
    temp_max = st.number_input("Temperature max ambiante (°C)", value=50.0, step=1.0)
    bifacial_gain = st.number_input(
        "Gain bifacial estime (%)", value=10.0, min_value=0.0, max_value=40.0, step=5.0,
        help="Gain de courant face arriere des panneaux bifaciaux (typique: 10-25%)"
    )
    env = EnvironmentSpecs(temp_min_c=temp_min, temp_max_c=temp_max, bifacial_gain_pct=bifacial_gain)


def render_extraction_status(value, label, unit=""):
    """Show extraction status for a field."""
    if value is not None:
        return f"✅ {label}: **{value}{unit}**"
    return f"⚠️ {label}: *non detecte*"


def panel_input_block(station_idx: int) -> PanelSpecs:
    """Panel input: upload PDF or manual entry."""
    st.subheader("☀️ Panneau Solaire")

    mode = st.radio(
        "Mode de saisie", ["📄 Importer fiche technique PDF", "✏️ Saisie manuelle"],
        key=f"panel_mode_{station_idx}", horizontal=True
    )

    if mode == "📄 Importer fiche technique PDF":
        uploaded = st.file_uploader(
            "Fiche technique panneau (PDF)", type=['pdf'],
            key=f"panel_pdf_{station_idx}",
            help="Importez la fiche technique du panneau solaire de n'importe quel fabricant"
        )

        if uploaded:
            with st.spinner("Extraction des specifications en cours (OCR)..."):
                pdf_bytes = uploaded.read()
                # Store raw bytes for re-extraction
                st.session_state[f'panel_pdf_bytes_{station_idx}'] = pdf_bytes

                target_p = st.number_input(
                    "Puissance cible (Wc)", value=460, min_value=50, max_value=900, step=5,
                    key=f"panel_target_{station_idx}",
                    help="Si la fiche contient plusieurs variantes, selectionnez la puissance souhaitee"
                )

                extracted = extract_panel_specs(pdf_bytes, target_pmax=float(target_p))
                st.session_state[f'panel_extracted_{station_idx}'] = extracted

            # Show extraction results
            conf_pct = int(extracted.confidence * 100)
            if conf_pct >= 80:
                st.success(f"Extraction reussie ({conf_pct}% des parametres detectes)")
            elif conf_pct >= 50:
                st.warning(f"Extraction partielle ({conf_pct}%) - completez les champs manquants")
            else:
                st.error(f"Extraction faible ({conf_pct}%) - verifiez et completez les champs")

            if extracted.all_pmax_values:
                st.info(f"Variantes detectees: {', '.join(str(int(p)) + ' Wc' for p in extracted.all_pmax_values)}")

            with st.expander("Voir le texte extrait (debug)", expanded=False):
                st.text(extracted.raw_text[:3000])

            # Editable fields pre-filled with extracted values
            c1, c2 = st.columns(2)
            with c1:
                panel_model = st.text_input("Modele", value=extracted.model or "",
                                            key=f"pe_model_{station_idx}")
                panel_pmax = st.number_input("Pmax (W)", value=extracted.pmax_w or 400.0,
                                             step=5.0, key=f"pe_pmax_{station_idx}")
                panel_voc = st.number_input("Voc (V)", value=extracted.voc_v or 45.0,
                                            step=0.01, format="%.2f", key=f"pe_voc_{station_idx}")
                panel_vmp = st.number_input("Vmp (V)", value=extracted.vmp_v or 38.0,
                                            step=0.01, format="%.2f", key=f"pe_vmp_{station_idx}")
                panel_isc = st.number_input("Isc (A)", value=extracted.isc_a or 11.0,
                                            step=0.01, format="%.2f", key=f"pe_isc_{station_idx}")
            with c2:
                panel_imp = st.number_input("Imp (A)", value=extracted.imp_a or 10.5,
                                            step=0.01, format="%.2f", key=f"pe_imp_{station_idx}")
                panel_coeff_voc = st.number_input("Coeff Voc (%/°C)", value=extracted.coeff_voc_pct or -0.27,
                                                  step=0.001, format="%.3f", key=f"pe_cvoc_{station_idx}")
                panel_coeff_isc = st.number_input("Coeff Isc (%/°C)", value=extracted.coeff_isc_pct or 0.045,
                                                  step=0.001, format="%.3f", key=f"pe_cisc_{station_idx}")
                panel_coeff_pmax = st.number_input("Coeff Pmax (%/°C)", value=extracted.coeff_pmax_pct or -0.35,
                                                   step=0.001, format="%.3f", key=f"pe_cpmax_{station_idx}")
                panel_noct = st.number_input("NOCT (°C)", value=extracted.noct_c or 45.0,
                                             step=1.0, key=f"pe_noct_{station_idx}")

            c3, c4 = st.columns(2)
            with c3:
                panel_bifacial = st.checkbox("Bifacial", value=extracted.bifacial,
                                             key=f"pe_bif_{station_idx}")
                panel_bifaciality = 0.0
                if panel_bifacial:
                    panel_bifaciality = st.number_input("Bifacialite (%)",
                                                        value=extracted.bifaciality_pct or 80.0,
                                                        step=5.0, key=f"pe_bifpct_{station_idx}")
            with c4:
                panel_max_fuse = st.number_input("Fusible max serie (A)",
                                                  value=extracted.max_series_fuse_a or 20.0,
                                                  step=1.0, key=f"pe_fuse_{station_idx}")
        else:
            st.info("Importez un fichier PDF pour extraire automatiquement les specifications")
            return None
    else:
        # Full manual entry
        c1, c2 = st.columns(2)
        with c1:
            panel_model = st.text_input("Modele", value="", key=f"pm_model_{station_idx}")
            panel_pmax = st.number_input("Pmax (W)", value=400.0, step=5.0, key=f"pm_pmax_{station_idx}")
            panel_voc = st.number_input("Voc (V)", value=45.0, step=0.01, format="%.2f",
                                        key=f"pm_voc_{station_idx}")
            panel_vmp = st.number_input("Vmp (V)", value=38.0, step=0.01, format="%.2f",
                                        key=f"pm_vmp_{station_idx}")
            panel_isc = st.number_input("Isc (A)", value=11.0, step=0.01, format="%.2f",
                                        key=f"pm_isc_{station_idx}")
        with c2:
            panel_imp = st.number_input("Imp (A)", value=10.5, step=0.01, format="%.2f",
                                        key=f"pm_imp_{station_idx}")
            panel_coeff_voc = st.number_input("Coeff Voc (%/°C)", value=-0.270, step=0.001,
                                              format="%.3f", key=f"pm_cvoc_{station_idx}")
            panel_coeff_isc = st.number_input("Coeff Isc (%/°C)", value=0.045, step=0.001,
                                              format="%.3f", key=f"pm_cisc_{station_idx}")
            panel_coeff_pmax = st.number_input("Coeff Pmax (%/°C)", value=-0.350, step=0.001,
                                               format="%.3f", key=f"pm_cpmax_{station_idx}")
            panel_noct = st.number_input("NOCT (°C)", value=45.0, step=1.0, key=f"pm_noct_{station_idx}")

        c3, c4 = st.columns(2)
        with c3:
            panel_bifacial = st.checkbox("Bifacial", value=False, key=f"pm_bif_{station_idx}")
            panel_bifaciality = 0.0
            if panel_bifacial:
                panel_bifaciality = st.number_input("Bifacialite (%)", value=80.0, step=5.0,
                                                    key=f"pm_bifpct_{station_idx}")
        with c4:
            panel_max_fuse = st.number_input("Fusible max serie (A)", value=20.0, step=1.0,
                                              key=f"pm_fuse_{station_idx}")

    return PanelSpecs(
        model=panel_model, pmax_w=panel_pmax, voc_v=panel_voc, vmp_v=panel_vmp,
        isc_a=panel_isc, imp_a=panel_imp, coeff_voc_pct=panel_coeff_voc,
        coeff_isc_pct=panel_coeff_isc, coeff_pmax_pct=panel_coeff_pmax,
        noct_c=panel_noct, bifacial=panel_bifacial, bifaciality_pct=panel_bifaciality,
        max_series_fuse_a=panel_max_fuse,
    )


def inverter_input_block(station_idx: int) -> InverterSpecs:
    """Inverter input: upload PDF or manual entry."""
    st.subheader("⚡ Variateur / Onduleur")

    mode = st.radio(
        "Mode de saisie", ["📄 Importer fiche technique PDF", "✏️ Saisie manuelle"],
        key=f"inv_mode_{station_idx}", horizontal=True
    )

    if mode == "📄 Importer fiche technique PDF":
        uploaded = st.file_uploader(
            "Fiche technique variateur (PDF)", type=['pdf'],
            key=f"inv_pdf_{station_idx}",
            help="Importez le catalogue ou la fiche technique du variateur de n'importe quel fabricant"
        )

        if uploaded:
            with st.spinner("Extraction des specifications (OCR)..."):
                pdf_bytes = uploaded.read()
                extracted = extract_inverter_specs(pdf_bytes, max_pages=15)
                st.session_state[f'inv_extracted_{station_idx}'] = extracted

            conf_pct = int(extracted.confidence * 100)
            if conf_pct >= 60:
                st.success(f"Extraction reussie ({conf_pct}%)")
            elif conf_pct >= 30:
                st.warning(f"Extraction partielle ({conf_pct}%) - completez les champs")
            else:
                st.error(f"Extraction faible ({conf_pct}%) - "
                         "les catalogues multi-pages sont difficiles a parser, "
                         "saisissez les valeurs manuellement")

            with st.expander("Texte extrait (debug)", expanded=False):
                st.text(extracted.raw_text[:2000])

            c1, c2 = st.columns(2)
            with c1:
                inv_model = st.text_input("Modele", value=extracted.model or "",
                                          key=f"ie_model_{station_idx}")
                inv_power = st.number_input("Puissance (kW)", value=extracted.power_kw or 22.0,
                                            step=0.5, key=f"ie_power_{station_idx}")
                inv_vdc_max = st.number_input("Vdc max (V)", value=extracted.vdc_max or 900.0,
                                              step=10.0, key=f"ie_vdcmax_{station_idx}")
                inv_vdc_range_min = st.number_input("Plage Vdc min (V)",
                                                    value=extracted.vdc_range_min or 300.0,
                                                    step=10.0, key=f"ie_vdcmin_{station_idx}")
                inv_vdc_range_max = st.number_input("Plage Vdc max (V)",
                                                    value=extracted.vdc_range_max or 750.0,
                                                    step=10.0, key=f"ie_vdcmax2_{station_idx}")
            with c2:
                inv_vdc_mpp = st.number_input("Tension MPP (V)", value=extracted.vdc_mpp or 550.0,
                                              step=10.0, key=f"ie_mpp_{station_idx}")
                inv_vdc_start = st.number_input("V demarrage (V)", value=extracted.vdc_start or 300.0,
                                                step=10.0, key=f"ie_start_{station_idx}")
                inv_vdc_min_work = st.number_input("V min fonctionnement (V)",
                                                   value=extracted.vdc_min_work or 250.0,
                                                   step=10.0, key=f"ie_minw_{station_idx}")
                inv_in_nom = st.number_input("I entree nominale (A)",
                                             value=extracted.input_current_nominal or 51.0,
                                             step=1.0, key=f"ie_inom_{station_idx}")
                inv_in_max = st.number_input("I entree max DC (A)",
                                             value=extracted.input_current_max or 60.0,
                                             step=1.0, key=f"ie_imax_{station_idx}")
            inv_out_nom = st.number_input("I sortie nominale (A)",
                                          value=extracted.output_current_nominal or 45.0,
                                          step=1.0, key=f"ie_onom_{station_idx}")
        else:
            st.info("Importez un fichier PDF pour extraire automatiquement les specifications")
            return None
    else:
        # Full manual entry
        c1, c2 = st.columns(2)
        with c1:
            inv_model = st.text_input("Modele", value="", key=f"im_model_{station_idx}")
            inv_power = st.number_input("Puissance (kW)", value=22.0, step=0.5,
                                        key=f"im_power_{station_idx}")
            inv_vdc_max = st.number_input("Vdc max (V)", value=900.0, step=10.0,
                                          key=f"im_vdcmax_{station_idx}")
            inv_vdc_range_min = st.number_input("Plage Vdc min (V)", value=300.0, step=10.0,
                                                key=f"im_vdcmin_{station_idx}")
            inv_vdc_range_max = st.number_input("Plage Vdc max (V)", value=750.0, step=10.0,
                                                key=f"im_vdcmax2_{station_idx}")
        with c2:
            inv_vdc_mpp = st.number_input("Tension MPP (V)", value=550.0, step=10.0,
                                          key=f"im_mpp_{station_idx}")
            inv_vdc_start = st.number_input("V demarrage (V)", value=300.0, step=10.0,
                                            key=f"im_start_{station_idx}")
            inv_vdc_min_work = st.number_input("V min fonctionnement (V)", value=250.0,
                                               step=10.0, key=f"im_minw_{station_idx}")
            inv_in_nom = st.number_input("I entree nominale (A)", value=51.0, step=1.0,
                                         key=f"im_inom_{station_idx}")
            inv_in_max = st.number_input("I entree max DC (A)", value=60.0, step=1.0,
                                         key=f"im_imax_{station_idx}")
        inv_out_nom = st.number_input("I sortie nominale (A)", value=45.0, step=1.0,
                                      key=f"im_onom_{station_idx}")

    return InverterSpecs(
        model=inv_model, power_kw=inv_power, vdc_max=inv_vdc_max,
        vdc_range_min=inv_vdc_range_min, vdc_range_max=inv_vdc_range_max,
        vdc_mpp=inv_vdc_mpp, vdc_start=inv_vdc_start, vdc_min_work=inv_vdc_min_work,
        input_current_nominal=inv_in_nom, input_current_max=inv_in_max,
        output_current_nominal=inv_out_nom,
    )


def motor_input_block(station_idx: int) -> MotorSpecs:
    """Motor input: upload PDF or manual entry."""
    st.subheader("🔌 Moteur / Pompe")

    mode = st.radio(
        "Mode de saisie", ["📄 Importer fiche technique PDF", "✏️ Saisie manuelle"],
        key=f"mot_mode_{station_idx}", horizontal=True
    )

    if mode == "📄 Importer fiche technique PDF":
        uploaded = st.file_uploader(
            "Fiche technique moteur (PDF)", type=['pdf'],
            key=f"mot_pdf_{station_idx}",
            help="Importez la fiche technique du moteur de n'importe quel fabricant"
        )

        if uploaded:
            with st.spinner("Extraction des specifications (OCR)..."):
                pdf_bytes = uploaded.read()
                extracted = extract_motor_specs(pdf_bytes)

            conf_pct = int(extracted.confidence * 100)
            if conf_pct >= 60:
                st.success(f"Extraction reussie ({conf_pct}%)")
            else:
                st.warning(f"Extraction partielle ({conf_pct}%) - verifiez les valeurs")

            c1, c2 = st.columns(2)
            with c1:
                motor_power = st.number_input("Puissance (kW)", value=extracted.power_kw or 18.5,
                                              min_value=0.1, step=0.5, key=f"me_power_{station_idx}")
                motor_current = st.number_input("Courant nominal (A)", value=extracted.current_a or 43.0,
                                                min_value=0.1, step=1.0, key=f"me_current_{station_idx}")
            with c2:
                motor_voltage = st.number_input("Tension (V)", value=extracted.voltage_v or 380.0,
                                                step=10.0, key=f"me_voltage_{station_idx}")
        else:
            st.info("Importez un fichier PDF pour extraire automatiquement les specifications")
            return None
    else:
        # Manual entry
        c1, c2 = st.columns(2)
        with c1:
            motor_power = st.number_input("Puissance (kW)", value=18.5, min_value=0.1, step=0.5,
                                          key=f"mm_power_{station_idx}")
            motor_current = st.number_input("Courant nominal (A)", value=43.0, min_value=0.1,
                                            step=1.0, key=f"mm_current_{station_idx}")
        with c2:
            motor_voltage = st.number_input("Tension (V)", value=380.0, step=10.0,
                                            key=f"mm_voltage_{station_idx}")

    return MotorSpecs(power_kw=motor_power, current_a=motor_current, voltage_v=motor_voltage)


def station_input_block(station_idx: int):
    """Full station input block."""
    st.header(f"📋 Station N°{station_idx + 1}")

    tab_motor, tab_panel, tab_inverter = st.tabs([
        "🔌 Moteur / Pompe", "☀️ Panneau Solaire", "⚡ Variateur"
    ])

    with tab_motor:
        motor = motor_input_block(station_idx)

    with tab_panel:
        panel = panel_input_block(station_idx)

    with tab_inverter:
        inverter = inverter_input_block(station_idx)

    # Check all components are defined
    if motor is None or panel is None or inverter is None:
        st.warning("Completez tous les composants (moteur, panneau, variateur) pour lancer le dimensionnement")
        return None

    # --- PV Configuration ---
    st.subheader("🔧 Configuration du champ PV")
    col_auto, col_config = st.columns([1, 2])

    with col_auto:
        auto_config = st.checkbox(
            "Dimensionnement automatique", value=True, key=f"auto_{station_idx}",
            help="Calcule le nombre optimal de panneaux par string et de strings"
        )

    if auto_config:
        config = compute_optimal_config(panel, inverter, motor, env)
        with col_config:
            st.info(f"**Configuration calculee:** {config.num_strings} string(s) x "
                    f"{config.panels_per_string} panneaux = {config.total_panels} panneaux "
                    f"({config.total_panels * panel.pmax_w / 1000:.2f} kWc)")
    else:
        with col_config:
            c1, c2 = st.columns(2)
            with c1:
                n_panels_str = st.number_input("Panneaux par string", value=14,
                                               min_value=1, max_value=50, step=1,
                                               key=f"n_panels_{station_idx}")
            with c2:
                n_strings = st.number_input("Nombre de strings", value=3,
                                            min_value=1, max_value=20, step=1,
                                            key=f"n_strings_{station_idx}")
            config = PVConfig(panels_per_string=n_panels_str, num_strings=n_strings)

    return {
        'name': f"Station N°{station_idx + 1}",
        'motor': motor,
        'panel': panel,
        'inverter': inverter,
        'config': config,
        'env': env,
    }


# === MAIN ===
stations_input = []
for i in range(num_stations):
    with st.container():
        station_data = station_input_block(i)
        if station_data:
            stations_input.append(station_data)
    if i < num_stations - 1:
        st.divider()

# === RUN ANALYSIS ===
st.divider()

can_run = len(stations_input) == num_stations
if not can_run:
    st.warning("Completez les specifications de toutes les stations avant de lancer l'analyse")

run_btn = st.button("🚀 Lancer le dimensionnement", type="primary",
                     use_container_width=True, disabled=not can_run)

if run_btn and can_run:
    stations_results = []
    installation_diagrams = {}
    wiring_diagrams = {}

    with st.spinner("Calcul en cours..."):
        for st_data in stations_input:
            name = st_data['name']
            result = run_sizing(
                st_data['panel'], st_data['inverter'], st_data['motor'],
                st_data['env'], st_data['config'],
            )
            st_data['result'] = result
            stations_results.append(st_data)

            installation_diagrams[name] = generate_installation_diagram(
                st_data['panel'], st_data['inverter'], st_data['motor'],
                st_data['config'], result, name
            )
            wiring_diagrams[name] = generate_wiring_diagram(
                st_data['panel'], st_data['inverter'], st_data['motor'],
                st_data['config'], result, name
            )

    st.session_state['stations_results'] = stations_results
    st.session_state['installation_diagrams'] = installation_diagrams
    st.session_state['wiring_diagrams'] = wiring_diagrams

    # === DISPLAY RESULTS ===
    for st_data in stations_results:
        name = st_data['name']
        result: SizingResult = st_data['result']
        config: PVConfig = st_data['config']
        panel: PanelSpecs = st_data['panel']
        inverter: InverterSpecs = st_data['inverter']
        motor: MotorSpecs = st_data['motor']

        st.divider()
        st.header(f"📊 Resultats - {name}")

        # Verdict
        if result.overall_verdict == "CONFORME":
            st.markdown(f'<div class="verdict-ok">✅ {result.overall_verdict} - '
                        f'Configuration validee</div>', unsafe_allow_html=True)
        elif result.overall_verdict == "NON CONFORME":
            st.markdown(f'<div class="verdict-fail">❌ {result.overall_verdict} - '
                        f'Actions correctives requises</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="verdict-warn">⚠️ {result.overall_verdict} - '
                        f'Verifier les points en alerte</div>', unsafe_allow_html=True)

        st.write("")

        # Key metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Puissance PV", f"{result.total_power_w/1000:.2f} kWc",
                   f"{config.total_panels} panneaux")
        m2.metric("Ratio PV/Variateur", f"{result.ratio_pv_inverter:.2f}x",
                   "Ideal" if 1.2 <= result.ratio_pv_inverter <= 1.6 else "A verifier")
        m3.metric("Voc max (froid)", f"{result.voc_max_cold:.1f} V",
                   f"Limite: {inverter.vdc_range_max:.0f} V")
        m4.metric("Vmp STC", f"{result.vmp_stc:.1f} V",
                   f"MPP: {inverter.vdc_mpp:.0f} V")

        tab_checks, tab_install, tab_wiring, tab_detail = st.tabs([
            "🔍 Verifications", "🏗️ Schema d'installation",
            "🔌 Schema de cablage", "📋 Details"
        ])

        with tab_checks:
            st.subheader("Tableau de compatibilite")
            check_data = []
            for c in result.checks:
                icon = "✅" if c.verdict in ("OK", "EXCELLENT") else "⚠️" if c.verdict == "LIMITE" else "❌"
                check_data.append({
                    "": icon, "Verification": c.name,
                    "Valeur calculee": c.calculated_str, "Limite": c.limit_str,
                    "Verdict": c.verdict, "Detail": c.detail,
                })
            st.dataframe(check_data, use_container_width=True, hide_index=True)

            st.subheader("Plages recommandees")
            r1, r2 = st.columns(2)
            with r1:
                st.write(f"**Panneaux par string:** "
                         f"{result.recommended_panels_per_string_min} a "
                         f"{result.recommended_panels_per_string_max} "
                         f"(actuel: **{config.panels_per_string}**)")
            with r2:
                st.write(f"**Max strings parallele:** "
                         f"{result.recommended_max_strings} "
                         f"(actuel: **{config.num_strings}**)")

        with tab_install:
            installation_diagrams[name].seek(0)
            st.image(installation_diagrams[name], use_container_width=True)

        with tab_wiring:
            wiring_diagrams[name].seek(0)
            st.image(wiring_diagrams[name], use_container_width=True)

        with tab_detail:
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Conditions STC (25°C)**")
                st.write(f"- Voc = {result.voc_stc:.1f} V")
                st.write(f"- Vmp = {result.vmp_stc:.1f} V")
                st.write(f"- Isc = {result.isc_stc:.2f} A")
                st.write(f"- Imp = {result.imp_stc:.2f} A")
                st.write(f"- Pmax = {result.total_power_w:.0f} W")
            with col2:
                st.write("**Conditions extremes**")
                st.write(f"- Voc max ({st_data['env'].temp_min_c:.0f}°C) = "
                         f"{result.voc_max_cold:.1f} V")
                st.write(f"- Vmp min ({st_data['env'].temp_max_c:.0f}°C amb.) = "
                         f"{result.vmp_min_hot:.1f} V")
                st.write(f"- Tcell froid = {result.tcell_cold:.1f}°C")
                st.write(f"- Tcell chaud = {result.tcell_hot:.1f}°C")
                if panel.bifacial:
                    st.write(f"- Isc bifacial (+{st_data['env'].bifacial_gain_pct:.0f}%) = "
                             f"{result.isc_bifacial:.2f} A")

    # === REPORT ===
    st.divider()
    st.header("📄 Telecharger le rapport")
    report_buf = generate_report(
        stations_results,
        installation_diagrams=installation_diagrams,
        wiring_diagrams=wiring_diagrams,
    )
    st.download_button(
        label="📥 Telecharger le rapport Word (.docx)",
        data=report_buf.getvalue(),
        file_name="Rapport_Dimensionnement_Solaire.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary", use_container_width=True,
    )
