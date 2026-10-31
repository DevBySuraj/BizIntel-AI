"""Separate advanced-analysis views, each with prerequisites and methods."""
import streamlit as st
import plotly.express as px
from core.analysis import context
from core.intelligence import forecast, segmentation, anomalies
from core.dashboard import column_groups
from core.catalogue import check_measure
from ui.ui_style import scope_strip


def render_forecasting(dataset, ctx=None):
    ctx = ctx or context(dataset)
    scope_strip(ctx)
    models = dataset["settings"]["models"]

    st.markdown('<div style="margin-bottom: 8px;">', unsafe_allow_html=True)
    mode = st.radio("Analytical Module", ["Forecasting", "Customer segmentation", "Anomalies"], horizontal=True, key="ui_intelligence_mode")
    st.markdown('</div>', unsafe_allow_html=True)

    try:
        if mode == "Forecasting":
            with st.container(border=True):
                st.markdown("#### Baseline Time-Series Forecasting")
                st.caption("Chronological train/test split evaluation of naive, moving average, and trend models. Requires mapped date and sales/numeric columns.")

                f_c1, f_c2, f_c3 = st.columns(3)
                with f_c1:
                    frequency = st.selectbox(
                        "Time interval", ["M", "W", "D"],
                        index=["M", "W", "D"].index(models["frequency"]),
                        format_func=lambda x: {"M": "Monthly (aggregated)", "W": "Weekly (aggregated)", "D": "Daily"}[x],
                        key="ui_forecast_frequency"
                    )
                with f_c2:
                    horizon = st.number_input("Future periods to project", 1, 12, models["horizon"], key="ui_forecast_horizon")
                models.update(frequency=frequency, horizon=horizon)

                targets = [None] + column_groups(ctx["data"])["number"]
                with f_c3:
                    target = st.selectbox(
                        "Target measure", targets,
                        index=targets.index(models.get("target")) if models.get("target") in targets else 0,
                        format_func=lambda x: "Mapped sales revenue" if x is None else x,
                        key="ui_forecast_target"
                    )
                models["target"] = target

                with st.spinner("Evaluating chronological baselines…"):
                    result = forecast(ctx, frequency, horizon, target)

                st.markdown("##### Model Evaluation & Baseline Comparison")
                st.dataframe(result["comparison"], hide_index=True, width="stretch")
                st.caption("Lower error is better. MAE and RMSE use the target's units; neither is prediction accuracy.")

                st.markdown(
                    f'<div style="background:#E0F2FE;border:1px solid #BAE6FD;padding:8px 12px;border-radius:6px;font-size:12px;color:#0369A1;margin:6px 0 12px 0;">'
                    f'<strong>Recommended Baseline:</strong> {result["recommended"]} produced lowest holdout MAE on this dataset.'
                    f'</div>',
                    unsafe_allow_html=True
                )

                name = st.selectbox("Inspect baseline model details", list(result["models"]), key="ui_forecast_model")
                selected = result["models"][name]

                ch_left, ch_right = st.columns(2)
                with ch_left:
                    fig_test = px.line(selected["test"], x="Period", y=["Actual", "Predicted"], markers=True,
                                       title="Holdout Evaluation (Actuals vs Predictions)",
                                       color_discrete_sequence=["#0F172A", "#088395"])
                    fig_test.update_layout(height=260, template="plotly_white", margin=dict(l=25, r=15, t=35, b=25))
                    st.plotly_chart(fig_test, width="stretch")
                with ch_right:
                    fig_fut = px.line(selected["future"], x="Period", y="Forecast", markers=True,
                                      title="Future Projections (Refit on full history)",
                                      color_discrete_sequence=["#088395"])
                    fig_fut.update_layout(height=260, template="plotly_white", margin=dict(l=25, r=15, t=35, b=25))
                    st.plotly_chart(fig_fut, width="stretch")

                with st.expander("Future Projected Values Table", expanded=False):
                    st.dataframe(selected["future"], hide_index=True, width="stretch")

                st.caption(result["notes"])
                st.caption("Method guide: Naive repeats the last observed period. Moving average repeats the trailing 3-period mean. Linear trend fits an OLS regression line across chronological time.")

        elif mode == "Customer segmentation":
            with st.container(border=True):
                st.markdown("#### Customer Segmentation (RFM + K-Means)")
                st.caption("Aggregates Recency, Frequency, and Monetary metrics per unique customer, standardizes scales, and clusters using K-Means.")

                c_top1, c_top2 = st.columns([1, 3])
                with c_top1:
                    clusters = st.number_input("Number of customer groups (k)", 2, 6, models["clusters"], key="ui_clusters")
                    models["clusters"] = clusters

                with st.spinner("Building customer RFM profiles…"):
                    result = segmentation(ctx, clusters)

                # Keep customers table as first dataframe widget for AppTest index compatibility
                st.markdown("##### Customer Assignments & Profiles")
                st.dataframe(result["customers"], hide_index=True, width="stretch")

                if result["reason"]:
                    st.info(result["reason"])
                else:
                    st.markdown("##### Cluster Center Profiles")
                    st.dataframe(result["profiles"], hide_index=True, width="stretch")

                    sc_col, met_col = st.columns([3, 1])
                    with sc_col:
                        fig_sc = px.scatter(
                            result["customers"], x="frequency", y="monetary", color="Group",
                            hover_data=["customer", "recency"],
                            color_discrete_sequence=["#088395", "#0F172A", "#38BDF8", "#F59E0B", "#10B981"],
                            title="Customer Segments: Frequency vs Monetary Value"
                        )
                        fig_sc.update_layout(height=280, template="plotly_white", margin=dict(l=25, r=15, t=35, b=25))
                        st.plotly_chart(fig_sc, width="stretch")
                    with met_col:
                        if result["silhouette"] is not None:
                            st.metric("Silhouette Score", f"{result['silhouette']:.3f}", help="Diagnostic between -1 and +1 measuring separation between clusters. >0.5 indicates strong structure.")
                st.caption(result["notes"])

        else:
            with st.container(border=True):
                st.markdown("#### Statistical Anomaly Detection")
                st.caption("Identifies records beyond the IQR fence [Q1 - k*IQR, Q3 + k*IQR]. Flagged records are candidates for investigation, not necessarily errors.")

                numeric = column_groups(ctx["data"])["number"]
                if not numeric:
                    st.info("Anomaly investigation requires at least one numeric measure.")
                    return

                preferred = next((x for x in (ctx["settings"]["mapping"].get("unit_price"), ctx["settings"]["mapping"].get("quantity")) if x in numeric), numeric[0])
                preferred = models.get("anomaly_column") if models.get("anomaly_column") in numeric else preferred

                a_c1, a_c2, a_c3 = st.columns([2, 1, 1])
                with a_c1:
                    column = st.selectbox("Measure to investigate", numeric, index=numeric.index(preferred), key="ui_anomaly_column")
                with a_c2:
                    multiplier = st.number_input("IQR fence multiplier (k)", .5, 5., float(models["iqr_multiplier"]), .5, key="ui_iqr")
                models.update(iqr_multiplier=multiplier, anomaly_column=column)
                check_measure(column, ctx["settings"]["mapping"], ctx["metrics"]["monetary_ok"])

                result = anomalies(ctx["data"], column, multiplier)

                with a_c3:
                    st.metric("Flagged Records", len(result["flagged"]), help="Rows with values falling outside the lower/upper fences.")

                # Flagged table is first dataframe widget in Anomalies mode
                st.markdown("##### Flagged Records for Review")
                st.dataframe(result["flagged"], hide_index=True, width="stretch")

                st.markdown(
                    f'<div style="background:#F1F5F9;border:1px solid #E2E8F0;padding:6px 12px;border-radius:6px;font-size:12px;color:#334155;margin:6px 0;">'
                    f'<strong>Statistical Bounds:</strong> Lower Fence: <strong>{result["lower"]:,.2f}</strong> &nbsp;·&nbsp; '
                    f'Upper Fence: <strong>{result["upper"]:,.2f}</strong> &nbsp;·&nbsp; '
                    f'Excluded nonfinite values: <strong>{result["excluded"]}</strong>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                st.caption(result["notes"])

    except ValueError as error:
        st.info(f"This analysis is unavailable: {error}")
