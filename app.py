import itertools
import random
import streamlit as st

# ─────────────────────────── CONFIG & GLOBAL CSS ────────────────────────────────
st.set_page_config(page_title="Optimisation des pompes", layout="wide")

st.markdown("""
<style>
/* ──── GLOBAL STYLING ──── */
.block-container             { padding: 0.5rem 0.5rem !important; max-width: 100vw !important; }
.block-container .element-container { margin: 0 !important; }
body                         { background: #f8f9fa; color: #333; font-family: 'Segoe UI', sans-serif; }

/* ──── COMPACT PUMP TABLE ──── */
[data-testid="column"]:nth-child(1){ flex: 0 0 40px !important; max-width: 40px !important; } /* Adjust pump label column width */

/* Header */
.header         { text-align: center; font-size: 0.6rem; font-weight: 600; white-space: nowrap; color: #555; padding-bottom: 0.2rem; }

/* File grouping */
.file-header {
    background: #2c8ac9;
    color: white;
    text-align: center;
    font-weight: 600;
    font-size: 0.7rem; /* Smaller font */
    padding: 0.1rem 0; /* Reduced padding */
    margin: 0.1rem 0;
    border-radius: 4px;
}

/* Cells styling */
.value-cell {
    background: #e9f5fe;
    color: #2c8ac9;
    border: 1px solid #d0e3f4;
    border-radius: 4px;
    font-size: 1rem; /* Smaller font */
    
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 0 0.1rem;
    box-sizing: border-box; /* Include padding/border in element's total width and height */
}

/* Input fields */
.stTextInput input {
    background: #fff !important;
    color: #333 !important;
    border: 0.5px solid #ddd !important;
    height: 30px !important; /* Reduced height */
    font-size: 1rem !important; /* Smaller font */
    padding: 0 0.2rem !important;
}

/* Checkbox */
.stCheckbox {
    transform: scale(0.7); /* Smaller checkbox */
    margin-left: 0.2rem !important; /* Adjust margin */
    padding: 0 !important;
}

/* Selection circle */
.circle {
    width: 12px; /* Smaller circle */
    height: 12px;
    border-radius: 50%;
    margin: 0 auto;
    background: #e0e0e0;
}

/* ──── CONTROL PANEL ──── */
.control-panel {
    background: #fff;
    border-radius: 8px;
    padding: 0.6rem; /* Reduced padding */
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
}

.flow-input-label {
    font-size: 0.75rem; /* Smaller font */
    font-weight: 600;
    color: #2c8ac9;
    margin-bottom: 0.2rem; /* Reduced margin */
    display: block;
}

.flow-input {
    width: 100%;
    margin-bottom: 0.6rem; /* Reduced margin */
}

.stNumberInput input {
    border: 2px solid #2c8ac9 !important;
    font-weight: 600 !important;
    font-size: 0.8rem !important; /* Slightly larger for clarity */
    height: 30px !important; /* Taller for easier interaction */
}

.simulate-btn {
    background: #2c8ac9 !important;
    color: white !important;
    border: none !important;
    font-weight: 600 !important;
    width: 100% !important;
    transition: all 0.2s !important;
    padding: 0.4rem 0.5rem !important; /* Reduced padding */
    font-size: 0.75rem !important; /* Smaller font */
    height: auto !important;
}

.simulate-btn:hover {
    background: #1d6998 !important;
    transform: translateY(-1px);
}

/* Results boxes */
.metric-box {
    background: #e9f5fe;
    color: #2c8ac9;
    border-left: 4px solid #2c8ac9;
    border-radius: 0 4px 4px 0;
    padding: 0.4rem; /* Reduced padding */
    margin-bottom: 0.4rem; /* Reduced margin */
    font-size: 0.7rem; /* Smaller font */
    font-weight: 600;
}

.metric-value {
    font-size: 1rem; /* Slightly smaller */
    font-weight: 700;
    margin-top: 0.1rem; /* Reduced margin */
}

.error-box {
    background: #fee9e9;
    color: #d32f2f;
    border-left: 4px solid #d32f2f;
    border-radius: 0 4px 4px 0;
    padding: 0.4rem; /* Reduced padding */
    margin-bottom: 0.4rem; /* Reduced margin */
    font-size: 0.7rem; /* Smaller font */
    font-weight: 600;
}

.combo-text {
    font-size: 0.7rem; /* Smaller font */
    color: #555;
    margin-top: 0.4rem; /* Reduced margin */
    line-height: 1.2; /* Tighter line spacing */
}

/* Compact spacing */
.element-container:has(.stTextInput),
.element-container:has(.stCheckbox) {
    margin-bottom: -0.8rem !important; /* Further reduce space between elements */
}

/* Adjust column spacing for tight fit */
[data-testid="stVerticalBlock"] > div > div > div {
    gap: 0.2rem; /* Reduce gap between elements in vertical blocks */
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────── NOMINAL PUMP SPECS ────────────────────────────────
pump_specs = {
    f"File {i}_P{j}": (
        15000 if j == 1 else 9000 if j == 2 else 18000,  # débit nominal (m³/h)
        # puissance nominale (kW)
        3800 if j == 1 else 2400 if j == 2 else 4600
    )
    for i in range(1, 5) for j in (1, 2, 3)
}

# ─────────────────────────── OPTIMISATION LOGIC ────────────────────────────────


def optimise_for_flow(pump_data: dict, target_flow: float, allow_random=True):
    """Return combo with the lowest kW that still meets ≥ target_flow (m³/h)."""
    pids = [pid for pid, d in pump_data.items() if d["avail"]]

    # Calculate total available flow
    total_available_flow = sum(
        d["obs_flow"] if d["obs_flow"] is not None else d["nom_flow"]
        for pid, d in pump_data.items() if d["avail"]
    )

    if total_available_flow < target_flow:
        return {"error": "insufficient_flow", "available_flow": total_available_flow}

    # Find all valid combinations
    valid_combos = []
    for combo in itertools.product([0, 1], repeat=len(pids)):
        F = P = 0.0
        active = []
        for flag, pid in zip(combo, pids):
            if not flag:
                continue
            d = pump_data[pid]
            F += d["obs_flow"] if d["obs_flow"] is not None else d["nom_flow"]
            P += d["obs_power"] if d["obs_power"] is not None else d["nom_power"]
            active.append(pid)

        if F >= target_flow:
            valid_combos.append(
                {"pumps_on": active, "total_flow": F, "total_power": P})

    valid_combos.sort(key=lambda x: x["total_power"])

    if not valid_combos:
        return None

    min_power = valid_combos[0]["total_power"]
    best_combos = [c for c in valid_combos if abs(
        c["total_power"] - min_power) < 0.01]

    if allow_random and len(best_combos) > 1:
        if "last_solution_hash" not in st.session_state:
            st.session_state.last_solution_hash = None

        if "reset_selection" in st.session_state and st.session_state.reset_selection:
            selected = random.choice(best_combos)
            st.session_state.last_solution_hash = hash(
                tuple(sorted(selected["pumps_on"])))
            st.session_state.reset_selection = False
            return selected
        else:
            if st.session_state.last_solution_hash is not None:
                for combo in best_combos:
                    if hash(tuple(sorted(combo["pumps_on"]))) == st.session_state.last_solution_hash:
                        return combo
            return best_combos[0]
    else:
        return best_combos[0]


# ─────────────────────────── UI LAYOUT ────────────────────────────────
st.markdown("<h1 style='text-align:center;font-size:4rem;color:#2c8ac9;margin-bottom:0.5rem;'>Optimisation de l'utilisation des pompes</h1>", unsafe_allow_html=True)

# Adjust column ratios for better fit: Left (pump table) and Right (control panel/results)
# Adjusted ratio for more space for pumps
left_col, right_col = st.columns([3, 1])

# ─── PUMP TABLE ───
with left_col:
    # Headers
    headers = ["", "P. Nom.", "D. Nom.",
               "P. Obs.", "D. Obs.", "Dispo", "Sélection"]
    # Adjusted column widths to be very compact
    col_widths = [0.4, 0.9, 0.9, 0.9, 0.9, 0.6, 0.6]
    header_cols = st.columns(col_widths)
    for col, h in zip(header_cols, headers):
        col.markdown(f'<div class="header">{h}</div>', unsafe_allow_html=True)

    pump_data = {}
    placeholders = {}

    # Table body
    for file_num in range(1, 5):
        st.markdown(
            f'<div class="file-header">FILE {file_num}</div>', unsafe_allow_html=True)

        for pump_num in range(1, 4):
            pid = f"File {file_num}_P{pump_num}"
            nom_flow, nom_power = pump_specs[pid]

            cols = st.columns(col_widths)
            # Pump label
            cols[0].markdown(
                f'<div style="text-align:center;font-weight:bold;font-size:0.6rem;">P{pump_num}</div>', unsafe_allow_html=True)
            # Nominal power
            cols[1].markdown(
                f'<div class="value-cell">{nom_power} kW</div>', unsafe_allow_html=True)
            # Nominal flow
            cols[2].markdown(
                f'<div class="value-cell">{nom_flow} m³/h</div>', unsafe_allow_html=True)
            # Observed power
            obs_p_str = cols[3].text_input("", value=str(
                nom_power), key=f"{pid}_obs_p", label_visibility="collapsed")
            # Observed flow
            obs_f_str = cols[4].text_input("", value=str(
                nom_flow), key=f"{pid}_obs_f", label_visibility="collapsed")
            # Availability
            avail = cols[5].checkbox(
                "", value=True, key=f"{pid}_avail", label_visibility="collapsed")
            # Selection circle
            placeholders[pid] = cols[6].empty()

            # Parse observed values
            try:
                obs_p = float(obs_p_str)
            except ValueError:
                obs_p = nom_power
            try:
                obs_f = float(obs_f_str)
            except ValueError:
                obs_f = nom_flow

            pump_data[pid] = {
                "nom_flow": nom_flow, "nom_power": nom_power,
                "obs_flow": None if obs_f == nom_flow else obs_f,
                "obs_power": None if obs_p == nom_power else obs_p,
                "avail": avail
            }

# ─── CONTROL PANEL ───
with right_col:
    st.markdown('<div class="control-panel">', unsafe_allow_html=True)

    # Flow input
    st.markdown('<div class="flow-input-label">DÉBIT DÉSIRÉ (m³/h)</div>',
                unsafe_allow_html=True)
    target_flow = st.number_input(
        "",
        value=30000.0,
        step=1000.0,
        key="target_flow",
        label_visibility="collapsed",
        format="%.0f",
        min_value=0.0,
        max_value=10000000.0
    )

    # Simulate button
    simulate = st.button(
        "SIMULER L'OPTIMISATION",
        key="simulate_btn",
        help="Trouve la combinaison la plus économe en énergie"
    )

    # Results containers
    flow_box = st.empty()
    power_box = st.empty()
    combo_box = st.empty()
    error_box = st.empty()

    st.markdown('</div>', unsafe_allow_html=True)

# ─── OPTIMISATION EXECUTION ───
if simulate:
    st.session_state.reset_selection = True
    res = optimise_for_flow(pump_data, target_flow)
    error_box.empty()  # Clear previous errors

    if not res:
        st.error("Aucune combinaison valide ne permet d'atteindre le débit cible.")
    elif "error" in res and res["error"] == "insufficient_flow":
        for pid, ph in placeholders.items():
            ph.markdown(
                '<div class="circle" style="background:#e0e0e0;"></div>', unsafe_allow_html=True)

        flow_box.markdown(
            f'<div class="metric-box">Débit Disponible<br>'
            f'<span class="metric-value">{res["available_flow"]:.0f} m³/h</span></div>',
            unsafe_allow_html=True
        )
        power_box.empty()
        combo_box.empty()
        error_box.markdown(
            f'<div class="error-box">Débit insuffisant<br>'
            f'Disponible: {res["available_flow"]:.0f} m³/h<br>'
            f'Demandé: {target_flow:.0f} m³/h</div>',
            unsafe_allow_html=True
        )
    else:
        active = set(res["pumps_on"])
        for pid, ph in placeholders.items():
            ph.markdown(
                f'<div class="circle" style="background:{"#2c8ac9" if pid in active else "#e0e0e0"};"></div>',
                unsafe_allow_html=True
            )

        flow_box.markdown(
            f'<div class="metric-box">Débit Total<br>'
            f'<span class="metric-value">{res["total_flow"]:.0f} m³/h</span></div>',
            unsafe_allow_html=True
        )

        power_box.markdown(
            f'<div class="metric-box">Puissance Totale<br>'
            f'<span class="metric-value">{res["total_power"]:.0f} kW</span></div>',
            unsafe_allow_html=True
        )

        combo_text = ", ".join(pid.replace("File ", "F")
                               for pid in res["pumps_on"])
        combo_box.markdown(
            f'<div class="combo-text">Pompes sélectionnées:<br><strong>{combo_text}</strong></div>',
            unsafe_allow_html=True
        )
