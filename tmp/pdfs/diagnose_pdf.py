from pathlib import Path
from pydantic import ValidationError
from apps.workbench.api.pdf_worker import _convert,_restrict_runtime
from apps.workbench.api.pdf_models import PdfLimits
limits=PdfLimits()
_restrict_runtime(limits)
try:
    doc=_convert(Path('tmp/pdfs/ca-warn-first-two-pages.pdf').read_bytes(),Path('.cache/workbench-pdf/models').resolve(),limits)
    Path('tasks/evidence/pdf-layout-2026-11-22/qualified-projection.json').write_text(doc.model_dump_json(),encoding='utf-8')
    print(dict(pages=len(doc.pages),blocks=len(doc.blocks),seconds=doc.parser_seconds))
except ValidationError as error:
    print([(item['loc'],item['type'],item['msg']) for item in error.errors(include_input=False)])
except Exception as error:
    print(type(error).__name__)
