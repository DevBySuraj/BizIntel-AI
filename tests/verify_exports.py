"""Optional real-renderer check; creates only fictional local verification files."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_product import dataset
from core.analysis import context
from core.insights import findings
from core.reports import assemble_report, html_bytes, pdf_bytes
import pymupdf

folder=Path(__file__).resolve().parents[1]/'.verification'
folder.mkdir(exist_ok=True)
ds=dataset((folder.parent/'data'/'sample_sales_catalogue.csv').read_bytes())
ds['name']='sample_sales_catalogue.csv'
ds['settings']['currency']='INR'
ctx=context(ds)
report=assemble_report(ctx,'BizIntel AI - Fictional sales review',
                       [f['id'] for f in findings(ctx)],
                       [c['id'] for c in ctx['settings']['charts']],
                       interpretation='Review stock availability before making any purchasing decision.')
(folder/'sample_report.html').write_bytes(html_bytes(report))
pdf=pdf_bytes(report)
assert pdf.startswith(b'%PDF')
(folder/'sample_report.pdf').write_bytes(pdf)
doc=pymupdf.open(stream=pdf,filetype='pdf')
text='\n'.join(page.get_text() for page in doc)
assert '5,180.00' in text and '1,920.00' in text
assert 'Reported profit' in text and 'Units sold: 17.00' in text
images=sum(len(page.get_images()) for page in doc)
assert images>=3,images
for index,page in enumerate(doc):
    page.get_pixmap(matrix=pymupdf.Matrix(1.2,1.2)).save(str(folder/f'report-page-{index+1}.png'))
print(f'PASS: {len(doc)} PDF pages; {images} chart images; exact sample KPIs verified. HTML includes inline Plotly assets.')
