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
    mode = st.radio("Analysis", ["Forecasting","Customer segmentation","Anomalies"], horizontal=True, key="ui_intelligence_mode")
    try:
        if mode == "Forecasting":
            a,b = st.columns(2)
            frequency = a.selectbox("Time interval", ["M","W","D"], index=["M","W","D"].index(models["frequency"]),
                                   format_func=lambda x: {"M":"Monthly","W":"Weekly","D":"Daily"}[x], key="ui_forecast_frequency")
            horizon = b.number_input("Future periods", 1, 12, models["horizon"], key="ui_forecast_horizon")
            models.update(frequency=frequency, horizon=horizon)
            targets = [None]+column_groups(ctx["data"])["number"]
            target = st.selectbox("Target measure", targets, index=targets.index(models.get("target")) if models.get("target") in targets else 0,
                                  format_func=lambda x: "Mapped sales" if x is None else x, key="ui_forecast_target")
            models["target"] = target
            with st.spinner("Evaluating chronological baselines…"):
                result = forecast(ctx, frequency, horizon, target)
            st.dataframe(result["comparison"], hide_index=True, width="stretch")
            st.caption("Lower error is better. MAE and RMSE use the target's units; neither is prediction accuracy.")
            st.info(f"Lowest holdout MAE: {result['recommended']}. This recommendation used the same holdout.")
            name = st.selectbox("Inspect model", list(result["models"]), key="ui_forecast_model")
            selected = result["models"][name]
            st.plotly_chart(px.line(selected["test"], x="Period", y=["Actual","Predicted"], markers=True,
                                    title="Held-out actuals vs predictions", color_discrete_sequence=["#173451","#087F8C"]), width="stretch")
            st.plotly_chart(px.line(selected["future"], x="Period", y="Forecast", markers=True, title="Future projections (refit on all history)",
                                    color_discrete_sequence=["#087F8C"]), width="stretch")
            st.dataframe(selected["future"], hide_index=True, width="stretch")
            st.caption(result["notes"])
            st.caption("Naive repeats the last value. Moving average repeats the last 3-period mean. Linear trend fits a straight line to time.")
        elif mode == "Customer segmentation":
            clusters = st.number_input("Customer groups", 2, 6, models["clusters"], key="ui_clusters")
            models["clusters"] = clusters
            with st.spinner("Building customer profiles…"):
                result = segmentation(ctx, clusters)
            st.dataframe(result["customers"], hide_index=True, width="stretch")
            if result["reason"]:
                st.info(result["reason"])
            else:
                st.dataframe(result["profiles"], hide_index=True, width="stretch")
                st.plotly_chart(px.scatter(result["customers"], x="frequency", y="monetary", color="Group",
                                          hover_data=["customer","recency"], color_discrete_sequence=["#087F8C","#173451","#B68132"]),
                                width="stretch")
                if result["silhouette"] is not None:
                    st.metric("Silhouette (separation diagnostic)", f"{result['silhouette']:.3f}")
            st.caption(result["notes"])
        else:
            numeric = column_groups(ctx["data"])["number"]
            if not numeric:
                st.info("Anomaly investigation needs a numeric measure.")
                return
            preferred = next((x for x in (ctx["settings"]["mapping"].get("unit_price"), ctx["settings"]["mapping"].get("quantity")) if x in numeric), numeric[0])
            preferred = models.get("anomaly_column") if models.get("anomaly_column") in numeric else preferred
            column = st.selectbox("Measure to investigate", numeric, index=numeric.index(preferred), key="ui_anomaly_column")
            multiplier = st.number_input("IQR fence multiplier", .5, 5., float(models["iqr_multiplier"]), .5, key="ui_iqr")
            models.update(iqr_multiplier=multiplier, anomaly_column=column)
            check_measure(column, ctx["settings"]["mapping"], ctx["metrics"]["monetary_ok"])
            result = anomalies(ctx["data"], column, multiplier)
            st.metric("Records flagged for investigation", len(result["flagged"]))
            st.dataframe(result["flagged"], hide_index=True, width="stretch")
            st.write(f"Bounds: {result['lower']:,.2f} to {result['upper']:,.2f}. Excluded nonfinite values: {result['excluded']}.")
            st.caption(result["notes"])
    except ValueError as error:
        st.info(f"This analysis is unavailable: {error}")

