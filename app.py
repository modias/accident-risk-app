import datetime
from pathlib import Path

import streamlit as st

from risk_calculator import LOOKUP_PATH, calculate_risk, get_baseline

LEVEL_COLORS = {
    "Low": "#22c55e",
    "Moderate": "#eab308",
    "High": "#f97316",
    "Very High": "#ef4444",
}

st.set_page_config(
    page_title="Accident Risk Checker",
    page_icon="🚗",
    layout="wide",
)

st.title("🚗 Accident Risk Checker")
st.caption(
    "Risk is estimated from real US accident records matching your driving conditions."
)

if not LOOKUP_PATH.exists():
    st.warning(
        "Accident data has not been processed yet. Run "
        "`python preprocess_data.py` in the project folder, then refresh this page."
    )
else:
    @st.cache_resource
    def _warm_data_cache() -> bool:
        get_baseline()
        return True

    _warm_data_cache()
    baseline = get_baseline()
    st.caption(
        f"Loaded **{baseline['total_accidents']:,}** US accident records "
        f"(avg severity {baseline['avg_severity']}/4)."
    )

col_form, col_result = st.columns([1, 1], gap="large")

with col_form:
    st.subheader("Driving conditions")

    weather = st.selectbox(
        "Weather",
        options=["clear", "cloudy", "rain", "snow", "fog", "ice"],
        format_func=lambda x: x.title(),
    )

    visibility_mi = st.number_input(
        "Visibility (miles)",
        min_value=0.0,
        max_value=20.0,
        value=10.0,
        step=0.1,
        help="How far you can clearly see ahead.",
    )

    time_value = st.time_input("Time of day", value=datetime.time(12, 0))
    hour = time_value.hour

    place_type = st.selectbox(
        "Place / road type",
        options=["highway", "urban", "intersection", "rural", "parking_lot"],
        format_func=lambda x: x.replace("_", " ").title(),
    )

    calculate = st.button("Calculate Risk", type="primary", use_container_width=True)

with col_result:
    st.subheader("Risk assessment")

    if calculate:
        if not LOOKUP_PATH.exists():
            st.error("Process the dataset first with `python preprocess_data.py`.")
        else:
            try:
                result = calculate_risk(weather, visibility_mi, hour, place_type)
            except FileNotFoundError as exc:
                st.error(str(exc))
            else:
                pct = int(result.score * 100)
                color = LEVEL_COLORS[result.level]

                st.markdown(
                    f"<h2 style='color:{color}; margin-bottom:0;'>{pct}% — {result.level}</h2>",
                    unsafe_allow_html=True,
                )
                st.progress(result.score)

                st.markdown("**Dataset match**")
                if result.accident_count > 0:
                    st.markdown(
                        f"- **{result.accident_count:,}** accidents recorded for: "
                        f"{result.matched_conditions}"
                    )
                    st.markdown(
                        f"- Average accident severity: **{result.avg_severity} / 4**"
                    )
                    st.markdown(
                        f"- Relative frequency: **{result.relative_risk:.1f}×** "
                        f"vs other buckets at this hour on this road type"
                    )
                else:
                    st.markdown(
                        f"- No accidents found for: {result.matched_conditions}"
                    )
                    st.markdown(
                        "- Risk is based on how dangerous these conditions are, "
                        "since this exact combination is rare in the dataset."
                    )

                if result.factors:
                    condition_factors = [
                        f for f in result.factors
                        if f.name in {"weather", "visibility", "time", "place"}
                    ]
                    data_factors = [
                        f for f in result.factors
                        if f.name in {"accidents", "severity", "frequency", "data", "match"}
                    ]

                    if condition_factors:
                        st.markdown("**Condition risk**")
                        for factor in condition_factors:
                            contrib_pct = int(factor.contribution * 100)
                            st.markdown(
                                f"- **{factor.label}** (+{contrib_pct}%)"
                            )

                    if data_factors:
                        st.markdown("**Dataset evidence**")
                        for factor in data_factors:
                            if factor.contribution > 0:
                                contrib_pct = int(factor.contribution * 100)
                                st.markdown(
                                    f"- **{factor.label}** (+{contrib_pct}%)"
                                )
                            else:
                                st.markdown(f"- {factor.label}")

                st.markdown("**Suggestions**")
                for tip in result.suggestions:
                    st.markdown(f"- {tip}")

    else:
        st.info("Enter your conditions on the left and click **Calculate Risk**.")
