"""PRD behavior and mathematical edge cases, independent expected values."""
from pathlib import Path
import json
import tempfile
import unittest
import subprocess
import sys

import pandas as pd

from core.automation import interpret, default_settings
from core.analysis import context
from core.csv_loader import load_csv
from core.charts import suggestions, build_figure, spec
from core.data_cleaning import apply_cleaning
from core.demo_data import extended_demo
from core.intelligence import forecast, segmentation, anomalies
from core.insights import findings
from core.kpi import analyze_kpis, compute_dimension_breakdown, compute_sales_growth
from core.reports import assemble_report, html_bytes, csv_bytes
from core.templates import save_template, read_template, compatible_settings, delete_template

ROOT = Path(__file__).resolve().parents[1]


def dataset(contents=None):
    contents = contents or (ROOT / 'data' / 'sample_sales.csv').read_bytes()
    original = load_csv('test.csv', contents)
    working, mapping, log = interpret(original)
    settings = default_settings(working, mapping)
    settings['charts'] = suggestions(working, mapping)
    return dict(name='test.csv', source_id='fixture', revision=1, original=original,
                working=working, history=log, settings=settings)


class ProductTests(unittest.TestCase):
    def test_automatic_sample_exact_totals_preserves_original(self):
        ds = dataset()
        m = context(ds)['metrics']
        self.assertEqual(m['total_revenue'], 5180)
        self.assertEqual(m['total_cost'], 3260)
        self.assertEqual(m['total_profit'], 1920)
        self.assertEqual(m['total_orders'], 8)
        self.assertAlmostEqual(m['profit_margin'], 1920/5180*100)
        self.assertEqual(ds['original'].iloc[0]['quantity'], '3')
        self.assertTrue(ds['settings']['charts'])

    def test_codes_mixed_values_and_ambiguous_roles(self):
        ds = dataset(b'id,postal_code,phone,amount,date,revenue,sales_amount,note\n001,01234,555123,12,03/04/2026,10,20,NA\n002,01234,555125,bad,04/05/2026,11,21,null\n')
        self.assertEqual(ds['working'].iloc[0]['id'], '001')
        self.assertEqual(ds['working'].iloc[0]['postal_code'], '01234')
        self.assertEqual(ds['working'].iloc[0]['phone'], '555123')
        self.assertIsNone(ds['settings']['mapping']['order_date'])
        self.assertIsNone(ds['settings']['mapping']['sales'])
        self.assertEqual(context(ds)['quality']['Missing cells'], 0)

    def test_generic_data_has_charts_not_fictional_kpis(self):
        ds = dataset(b'department,hours\nA,5\nB,7\nA,4\n')
        ctx = context(ds)
        self.assertIsNone(ctx['metrics']['total_revenue'])
        self.assertIsNone(ctx['metrics']['total_orders'])
        fig, table, _ = build_figure(ctx['data'], ds['settings']['charts'][0], ds['settings']['mapping'])
        self.assertEqual(table['y'].sum(), 3)

    def test_total_cost_is_not_multiplied_again(self):
        ds = dataset(b'quantity,unit_price,total_cost,order_id\n2,10,12,A\n3,20,45,B\n')
        m = context(ds)['metrics']
        self.assertEqual(m['total_revenue'], 80)
        self.assertEqual(m['total_cost'], 57)
        self.assertEqual(m['total_profit'], 23)

    def test_incomplete_costs_no_profit_missing_orders_no_aov(self):
        ds = dataset(b'revenue,total_cost,order_id\n10,6,A\n20,,\n')
        m = context(ds)['metrics']
        self.assertEqual(m['total_revenue'], 30)
        self.assertIsNone(m['total_profit'])
        self.assertIsNone(m['profit_margin'])
        self.assertIsNone(m['aov'])
        self.assertEqual(m['total_orders'], 1)

    def test_zero_overflow_returns_and_nonfinite(self):
        ds = dataset(b'revenue,total_cost\n10,5\n-10,-5\n')
        m = context(ds)['metrics']
        self.assertEqual(m['total_revenue'], 0)
        self.assertEqual(m['return_records'], 1)
        self.assertIsNone(m['profit_margin'])
        data = pd.DataFrame({'q':[1e308], 'p':[1e308]})
        self.assertIsNone(analyze_kpis(data, {'quantity':'q','unit_price':'p'})['total_revenue'])

    def test_mixed_currency_filter_and_unknown_label(self):
        ds = dataset(b'revenue,currency\n10,INR\n20,USD\n')
        self.assertIsNone(context(ds)['metrics']['total_revenue'])
        ds['settings']['filters'] = {'currency':dict(kind='category',values=['USD'])}
        ctx = context(ds)
        self.assertEqual(ctx['metrics']['total_revenue'],20)
        self.assertEqual(ctx['metrics']['currency'],'USD')
        self.assertEqual(context(dataset())['metrics']['currency'], 'Currency unspecified')

    def test_share_full_denominator(self):
        ds = dataset(b'revenue,category\n60,A\n30,B\n10,C\n')
        ctx = context(ds)
        table = compute_dimension_breakdown(ctx['data'],'category',ctx['metrics']['revenue_series'],ctx['metrics']['usable_mask'],1)
        self.assertEqual(table.iloc[0]['Share %'],60)

    def test_filters_and_empty_result(self):
        ds=dataset()
        ds['settings']['filters']={'region':dict(kind='category',values=['North']), 'quantity':dict(kind='number',range=[3,3])}
        ctx=context(ds)
        self.assertEqual(len(ctx['data']),1)
        self.assertEqual(ctx['metrics']['total_revenue'],240)
        ds['settings']['filters']['region']['values']=[]
        self.assertEqual(len(context(ds)['data']),0)
        self.assertIsNone(context(ds)['metrics']['total_revenue'])

    def test_growth_requires_complete_consecutive_positive_periods(self):
        dates=pd.to_datetime(['2025-01-01','2025-01-31','2025-02-01','2025-02-28','2025-04-01','2025-04-30'])
        df=pd.DataFrame({'date':dates})
        revenue=pd.Series([50.,50.,100.,100.,50.,50.])
        result=compute_sales_growth(df,'date',revenue,pd.Series(True,index=df.index),today='2026-01-01')
        self.assertEqual(result.iloc[1]['Growth %'],100)
        self.assertTrue(pd.isna(result.iloc[3]['Growth %']))
        revenue.iloc[:2]=0
        self.assertTrue(pd.isna(compute_sales_growth(df,'date',revenue,pd.Series(True,index=df.index)).iloc[1]['Growth %']))

    def test_cleaning_atomic_and_original_record_ids(self):
        ds=dataset(b'id,x\n001,1\n002,bad\n001,1\n')
        before=ds['working'].copy(deep=True)
        with self.assertRaises(ValueError): apply_cleaning(before,'Convert to number',['x'])
        pd.testing.assert_frame_equal(before,ds['working'])
        result=apply_cleaning(before,'Remove duplicate rows')
        self.assertEqual(list(result.index),[0,1])

    def test_every_chart_type_and_fingerprint(self):
        ds=dataset(); ctx=context(ds)
        cases=[spec('Bar','category','@revenue'),spec('Line','date','quantity'),spec('Histogram','quantity'),
               spec('Scatter','quantity','unit_price'),spec('Box','category','unit_price')]
        for chart in cases:
            figure,table,notes=build_figure(ctx['data'],chart,ds['settings']['mapping'])
            self.assertTrue(len(figure.data)); self.assertFalse(table.empty)
        before=ctx['scope']['id']; ds['settings']['currency']='USD'
        self.assertNotEqual(context(ds)['scope']['id'],before)

    def test_forecast_chronology_and_gaps(self):
        ctx=context(dataset(extended_demo()))
        result=forecast(ctx)
        baseline=result['models']['Naive (Last Value)']
        self.assertLess(baseline['train']['Period'].max(),baseline['test']['Period'].min())
        self.assertGreater(baseline['future']['Period'].min(),baseline['test']['Period'].max())
        expected=abs(baseline['test']['Actual']-baseline['train']['Actual'].iloc[-1]).mean()
        self.assertAlmostEqual(baseline['metrics']['mae'],expected)
        ds=dataset(extended_demo()); ds['working']=ds['working'][ds['working']['date'].dt.month!=3]
        with self.assertRaisesRegex(ValueError,'Missing periods'): forecast(context(ds))
        with self.assertRaises(ValueError): forecast(context(dataset()))

    def test_segmentation_customer_level_and_gate(self):
        result=segmentation(context(dataset(extended_demo())))
        self.assertEqual(len(result['customers']),30)
        self.assertEqual(result['profiles']['Customers'].sum(),30)
        self.assertIsNotNone(result['silhouette'])
        self.assertIsNotNone(segmentation(context(dataset()))['reason'])

    def test_anomaly_exact_bounds_and_original_references(self):
        data=pd.DataFrame({'value':list(range(20))+[1000]},index=range(5,26))
        result=anomalies(data,'value')
        self.assertEqual(result['lower'],-10)
        self.assertEqual(result['upper'],30)
        self.assertEqual(result['flagged'].iloc[0]['Original record'],26)
        with self.assertRaises(ValueError): anomalies(pd.DataFrame({'v':[1]*25}),'v')

    def test_templates_restart_compatibility_and_safe_paths(self):
        ds=dataset(); settings=ds['settings']
        with tempfile.TemporaryDirectory() as directory:
            saved=save_template('My layout','',settings,directory=directory)
            args=[sys.executable,'-c','from core.templates import read_template; import sys; print(read_template(sys.argv[1],sys.argv[2])["name"])', saved['id'],directory]
            self.assertEqual(subprocess.check_output(args,cwd=ROOT,text=True).strip(),'My layout')
            other=dataset(b'region,score\nEast,7\nWest,4\n')
            _,updated,warnings=compatible_settings(other['working'],other['settings'],saved)
            self.assertTrue(warnings)
            self.assertFalse(updated['mapping']['quantity'])
            self.assertNotIn('original',json.dumps(saved))
            with self.assertRaises(ValueError): read_template('../outside',directory)
            delete_template(saved['id'],directory)
            self.assertFalse((Path(directory)/(saved['id']+'.json')).exists())

    def test_report_matches_scope_and_escapes_html_and_csv(self):
        ctx=context(dataset()); fs=findings(ctx)
        report=assemble_report(ctx,'<script>alert(1)</script>',[f['id'] for f in fs],[],interpretation='<img src=x onerror=bad>')
        html=html_bytes(report).decode()
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertEqual(report['scope']['rows'],8)
        exported=csv_bytes(pd.DataFrame({'text':['=1+1','@SUM(A1)','-12'], 'number':[-2,-3,-4]})).decode('utf-8-sig')
        self.assertIn("'=1+1",exported)
        self.assertIn('-12,-4',exported)

    def test_report_chart_text_cannot_close_script(self):
        ds=dataset(b'revenue,category\n10,"</script><script>alert(123)</script>"\n20,B\n')
        ds['settings']['charts'][0]['title']='</script><script>alert(456)</script>'
        ctx=context(ds)
        report=assemble_report(ctx,'Escaping check',[],[c['id'] for c in ds['settings']['charts']])
        content=html_bytes(report).decode()
        self.assertNotIn('<script>alert(123)</script>',content)
        self.assertNotIn('<script>alert(456)</script>',content)

    def test_report_preferences_do_not_invalidate_analysis_and_are_reusable(self):
        ds=dataset(); before=context(ds)['scope']['id']
        ds['settings']['report']={'title':'My monthly report','methods':['Forecasting'], 'finding_kinds':['concentration'], 'chart_ids':[ds['settings']['charts'][0]['id']]}
        self.assertEqual(context(ds)['scope']['id'],before)
        with tempfile.TemporaryDirectory() as directory:
            document=save_template('Report style','',ds['settings'],directory=directory)
            _,settings,warnings=compatible_settings(ds['working'],default_settings(ds['working'],ds['settings']['mapping']),document)
            self.assertEqual(settings['report']['title'],'My monthly report')
            self.assertEqual(settings['report']['methods'],['Forecasting'])


if __name__=='__main__': unittest.main()
