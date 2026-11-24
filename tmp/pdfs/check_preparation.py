from pathlib import Path
from apps.workbench.chunking.chunking import ChunkingInput, prepare_chunks
from apps.workbench.chunking.chunking_profiles import ChunkingError
from apps.workbench.parsing.parsing import parse_source

parsed = parse_source(Path('tasks/evidence/pdf-layout-2026-11-22/live/california-warn-report-page-1.pdf').read_bytes(),
    safe_basename='california-warn-report-page-1.pdf', declared_type='application/pdf')
Path('tasks/evidence/pdf-layout-2026-11-22/live/actual-page-one.projection.json').write_text(parsed.pdf_document.model_dump_json(), encoding='utf-8')
try:
    chunks = prepare_chunks(ChunkingInput(parsed_document=parsed, normalized_content=parsed.extracted_text,
        workspace_id='development', source_id='probe', source_version_id='probe'))
    print([(chunk.page, chunk.effective_size, len(str(chunk.metadata()))) for chunk in chunks])
except ChunkingError as error:
    print(error.code.value, error.reason)
