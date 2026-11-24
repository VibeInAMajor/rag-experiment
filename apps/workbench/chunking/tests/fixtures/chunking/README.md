# Curated chunking inputs

`manifest.json` is UTF-8 source data for deterministic parser/chunking tests. It is not an application policy configuration. Each case contains `case_id`, `filename`, `language`, descriptive `tags`, and bounded `parts` with literal `text` and an integer `repeat` count. Build source text as:

```text
''.join(part['text'] * part['repeat'] for part in case['parts'])
```

Encode the result as UTF-8, pass it through the real parser, and supply the case language as the application's explicit language hint. `expected_error`, where present, is the stable refusal expected before a publishable result exists. Names, text, language hints and tags cannot select arbitrary parser/strategy imports.

The 25 cases cover ordinary/long paragraphs, long sentences, English/Russian/Ukrainian, no-space Unicode, literal punctuation, CRLF, repeated occurrences, Markdown heading hierarchy and heading-only documents, Setext/no-heading input, protected fences/tables/frontmatter/container syntax, prompt-injection text and empty input. Only language hints `en`, `ru` and `uk` are qualified: EN/RU use provisioned NLTK sentence resources; UK uses the explicit token-budgeted structural fallback. Other languages are deferred/refused. Arbitrary Unicode characters in safety/offset stress cases do not qualify another language. Repeat counts keep large cases readable in review while exercising real 500-token splits; tests must enforce a bounded expansion and never evaluate fixture content as code.

Assertions belong in tests: token ceilings and actual counter identity, source coverage and repeatable spans, section/structure isolation, explicit language/resource fallback, deterministic identities and safe refusal. Model-tokenizer assets are configured separately and are not stored with fixture texts. These fixtures alone do not measure retrieval recall or prove HTTP upload/database publication.
