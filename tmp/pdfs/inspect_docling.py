import io
import json
import os
import time
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
from docling.datamodel.base_models import InputFormat, DocumentStream
from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

options = PdfPipelineOptions(artifacts_path=Path('.cache/workbench-pdf/models').resolve(), do_ocr=False, do_table_structure=True,
    document_timeout=120, accelerator_options=AcceleratorOptions(device='cpu', num_threads=4), enable_remote_services=False,
    allow_external_plugins=False, do_picture_classification=False, do_picture_description=False,
    do_code_enrichment=False, do_formula_enrichment=False)
converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
started = time.perf_counter()
result = converter.convert(DocumentStream(name='input.pdf', stream=io.BytesIO(Path('tmp/pdfs/ca-warn-report.pdf').read_bytes())),
    max_num_pages=32, max_file_size=8388608, raises_on_error=False, page_range=(1, 1))
doc = result.document
print(json.dumps(dict(status=str(result.status), seconds=time.perf_counter()-started, pages=list(doc.pages),
    items=[dict(type=type(item).__name__,label=str(getattr(item,'label','')),page=[p.page_no for p in getattr(item,'prov',[])],
    text=getattr(item,'text','')[:120]) for item,level in doc.iterate_items()][:15],
    tables=[dict(rows=t.data.num_rows, cols=t.data.num_cols, cells=len(t.data.table_cells),first=[c.model_dump(mode='json') for c in t.data.table_cells[:3]]) for t in doc.tables],
    confidence=result.confidence.model_dump(mode='json')), indent=2,default=str))
Path('tasks/evidence/pdf-layout-2026-11-22/characterized-docling.json').write_text(doc.model_dump_json(),encoding='utf-8')
