"""End-to-end Streamlit state and navigation checks for the automatic product."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from test_product import dataset

ROOT=Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
        self.app.button(key='use_sample').click().run(timeout=30)
        self.assertFalse(self.app.exception)

    def go(self,page):
        self.app.button(key='nav_'+page).click().run(timeout=30)
        self.assertFalse(self.app.exception,[e.message for e in self.app.exception])

    def test_all_pages_have_no_exceptions(self):
        for page in ['Dashboard','Prepare','Explore','Intelligence','Reports','Data']:
            with self.subTest(page=page): self.go(page)

    def test_sample_dashboard_and_shared_filter_navigation(self):
        self.go('Dashboard')
        self.assertEqual(self.app.metric[0].value,'5,180.00')
        self.app.multiselect(key='ui_filter_columns').set_value(['region']).run(timeout=30)
        self.app.multiselect(key='ui_values_region').set_value(['North']).run(timeout=30)
        self.assertEqual(self.app.metric[0].value,'480.00')
        self.go('Explore'); self.go('Dashboard')
        self.assertEqual(self.app.metric[0].value,'480.00')
        self.app.multiselect(key='ui_values_region').set_value([]).run(timeout=30)
        self.assertEqual(len(self.app.metric),0)
        self.assertTrue(any('No records' in x.value for x in self.app.info))

    def test_preparation_reset_reanalysis_and_original(self):
        self.go('Prepare')
        self.app.button(key='reset_data').click().run(timeout=30)
        self.assertEqual(self.app.session_state['dataset']['working'].iloc[0]['quantity'],'3')
        next(b for b in self.app.button if b.label=='Re-run safe interpretation').click().run(timeout=30)
        self.assertEqual(self.app.session_state['dataset']['working'].iloc[0]['quantity'],3)
        self.assertEqual(self.app.session_state['dataset']['original'].iloc[0]['quantity'],'3')

    def test_report_invalidates_after_filters_change(self):
        self.go('Reports')
        self.app.text_area(key='ui_report_interpretation').set_value('Review supply carefully.').run(timeout=30)
        self.go('Dashboard')
        self.app.multiselect(key='ui_filter_columns').set_value(['region']).run(timeout=30)
        self.app.multiselect(key='ui_values_region').set_value(['North']).run(timeout=30)
        self.go('Reports')
        self.assertTrue(any('outdated draft' in w.value for w in self.app.warning))
        self.assertFalse(self.app.get('download_button'))
        next(b for b in self.app.button if b.label=='Start fresh report for current scope').click().run(timeout=30)
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.text_area(key='ui_report_interpretation').value,'')

    def test_extended_demo_models_and_reports(self):
        self.app.button(key='use_demo').click().run(timeout=30)
        self.go('Intelligence')
        self.assertTrue(self.app.get('plotly_chart'))
        self.app.radio(key='ui_intelligence_mode').set_value('Customer segmentation').run(timeout=30)
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.app.dataframe[0].value),30)
        self.app.radio(key='ui_intelligence_mode').set_value('Anomalies').run(timeout=30)
        self.assertFalse(self.app.exception)
        self.go('Reports')
        self.app.multiselect(key='ui_report_methods').set_value(['Forecasting','Customer segmentation','Anomalies']).run(timeout=30)
        self.assertFalse(self.app.exception)

    def test_chart_customization_saved_on_navigation(self):
        self.go('Explore')
        self.app.text_input(key='ui_chart_new_title').set_value('My category overview').run(timeout=30)
        self.app.selectbox(key='ui_chart_new_x').set_value('category').run(timeout=30)
        next(b for b in self.app.button if b.label=='Save chart to dashboard').click().run(timeout=30)
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state['dataset']['settings']['charts'][-1]['title'],'My category overview')
        self.go('Dashboard')
        self.assertEqual(len(self.app.get('plotly_chart')),4)

    def test_invalid_upload_clears_results(self):
        from io import BytesIO
        upload=BytesIO(b'a,b\n1,2,3'); upload.name='bad.csv'
        with patch('streamlit.file_uploader',return_value=upload): self.app.run(timeout=30)
        self.assertFalse(self.app.exception)
        self.assertNotIn('dataset',self.app.session_state)
        self.assertTrue(self.app.error)

    def test_template_save_load_and_incompatible_upload(self):
        from core.templates import list_templates, save_template, delete_template
        from functools import partial
        with tempfile.TemporaryDirectory() as directory:
            with patch('ui.template_ui.list_templates',side_effect=partial(list_templates,directory=directory)), \
                 patch('ui.template_ui.save_template',side_effect=partial(save_template,directory=directory)), \
                 patch('ui.template_ui.delete_template',side_effect=partial(delete_template,directory=directory)):
                self.app.run(timeout=30)
                self.app.text_input(key='ui_template_name').set_value('Reusable sales view').run(timeout=30)
                next(b for b in self.app.button if b.label=='Save as new template').click().run(timeout=30)
                saved,_=list_templates(directory)
                self.assertEqual(len(saved),1)
                self.app.run(timeout=30)
                self.app.selectbox(key='ui_template').set_value(saved[0]['id']).run(timeout=30)
                next(b for b in self.app.button if b.label=='Load template on this dataset').click().run(timeout=30)
                self.assertFalse(self.app.exception)
                self.go('Dashboard')
                self.assertEqual(self.app.metric[0].value,'5,180.00')
                self.go('Data')
                self.app.session_state['dataset']=dataset(b'region,score\nEast,2\nWest,5\n')
                self.app.run(timeout=30)
                self.app.selectbox(key='ui_template').set_value(saved[0]['id']).run(timeout=30)
                next(b for b in self.app.button if b.label=='Load template on this dataset').click().run(timeout=30)
                self.assertFalse(self.app.exception)
                self.assertTrue(any('skipped' in i.value for i in self.app.info))

    def test_cleaning_preview_apply_and_failure(self):
        self.app.session_state['dataset']=dataset(b'id,quantity,region\n001,1,N\n001,1,N\n002,bad,\n')
        self.go('Prepare')
        self.assertEqual(len(self.app.session_state['dataset']['working']),3)
        self.app.button(key='clean_apply').click().run(timeout=30)
        self.assertEqual(len(self.app.session_state['dataset']['working']),2)
        self.assertEqual(len(self.app.session_state['dataset']['original']),3)
        self.app.selectbox(key='ui_clean_action').set_value('Convert to number').run(timeout=30)
        self.app.selectbox(key='ui_clean_column').set_value('quantity').run(timeout=30)
        self.assertTrue(any('Conversion blocked' in i.value for i in self.app.info))
        self.assertFalse(any(b.key=='clean_apply' for b in self.app.button))

    def test_export_failure_has_html_alternative_and_edit_invalidates_download(self):
        self.go('Reports')
        with patch('ui.reports_ui.pdf_bytes',side_effect=RuntimeError('Renderer unavailable')):
            next(b for b in self.app.button if b.label=='Prepare HTML and PDF downloads').click().run(timeout=30)
        self.assertFalse(self.app.exception)
        self.assertTrue(any('PDF export failed' in e.value for e in self.app.error))
        self.assertIn('html',self.app.session_state['report_files'])
        self.assertNotIn('pdf',self.app.session_state['report_files'])
        self.app.text_input(key='ui_report_title').set_value('Revised report').run(timeout=30)
        self.assertTrue(any('choices changed' in i.value for i in self.app.info))


if __name__=='__main__': unittest.main()
