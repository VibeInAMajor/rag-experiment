"""Reviewed in-memory Haystack extraction boundary; never receives names or paths."""

from apps.workbench.api.parser_registry import ParseErrorCode, ParsingError


def extract_text(content: bytes) -> str:
    """
    Extract one byte-exact UTF-8-sig document through the existing text converter.

    :param content: Inspected UTF-8 bytes, with no untrusted metadata or filesystem targets.
    :returns: Nonempty text whose character offsets still refer to the decoded source.
    :raises ParsingError: If extraction is empty, emits multiple documents or changes source text.
    """
    from haystack.components.converters import TextFileToDocument
    from haystack.dataclasses import ByteStream

    result = TextFileToDocument().run(sources=[ByteStream(data=content)])
    documents = result.get("documents", [])
    if not documents:
        raise ParsingError(ParseErrorCode.EMPTY_EXTRACTION, reason="NO_DOCUMENTS")
    if len(documents) != 1:
        raise ParsingError(ParseErrorCode.PARSE_FAILED, reason="DOCUMENT_COUNT")
    text = documents[0].content
    if text is None or not text.strip():
        raise ParsingError(ParseErrorCode.EMPTY_EXTRACTION, reason="NO_TEXT")
    if text != content.decode("utf-8-sig"):
        raise ParsingError(ParseErrorCode.STRUCTURE_LOSS, reason="SOURCE_CHANGED")
    return text
