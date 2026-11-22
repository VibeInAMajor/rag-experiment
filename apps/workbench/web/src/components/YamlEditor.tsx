import { useEffect, useRef } from "react";
import { Annotation, Compartment, EditorState } from "@codemirror/state";
import {
  EditorView,
  drawSelection,
  highlightActiveLine,
  keymap,
  lineNumbers,
} from "@codemirror/view";
import {
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
} from "@codemirror/commands";
import {
  defaultHighlightStyle,
  indentOnInput,
  indentUnit,
  syntaxHighlighting,
} from "@codemirror/language";
import { yaml } from "@codemirror/lang-yaml";
import { lintGutter, setDiagnostics } from "@codemirror/lint";
import type { ConfigurationIssue } from "../api/contracts";

const externalChange = Annotation.define<boolean>();
const theme = EditorView.theme({
  "&": {
    height: "100%",
    fontSize: "13px",
    backgroundColor: "var(--bg-surface)",
  },
  ".cm-scroller": {
    fontFamily: '"JetBrains Mono", monospace',
    lineHeight: "1.85",
    overflow: "auto",
  },
  ".cm-content": { padding: "18px 0", minHeight: "100%" },
  ".cm-line": { padding: "0 24px 0 10px" },
  ".cm-gutters": {
    backgroundColor: "var(--bg-card-muted)",
    color: "var(--text-muted)",
    border: "none",
    paddingLeft: "8px",
  },
  ".cm-activeLine": { backgroundColor: "#254edb06" },
  ".cm-activeLineGutter": { backgroundColor: "#254edb0b" },
  "&.cm-focused": { outline: "none" },
  ".cm-cursor": { borderLeftColor: "var(--accent-blue)" },
});

export function YamlEditor({
  value,
  readOnly,
  issues,
  onChange,
  focusLine,
}: {
  value: string;
  readOnly: boolean;
  issues: ConfigurationIssue[];
  onChange: (value: string) => void;
  focusLine?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const editor = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const readonly = useRef(new Compartment());
  const initial = useRef(value);
  useEffect(() => {
    if (!host.current) return;
    const view = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: initial.current,
        extensions: [
          lineNumbers(),
          drawSelection(),
          highlightActiveLine(),
          history(),
          indentOnInput(),
          indentUnit.of("  "),
          keymap.of([indentWithTab, ...defaultKeymap, ...historyKeymap]),
          yaml(),
          syntaxHighlighting(defaultHighlightStyle),
          lintGutter(),
          theme,
          readonly.current.of(EditorState.readOnly.of(false)),
          EditorView.contentAttributes.of({
            "aria-label": "YAML configuration",
            "aria-describedby": "configuration-editor-help",
            "aria-multiline": "true",
            spellcheck: "false",
          }),
          EditorView.updateListener.of((update) => {
            if (
              update.docChanged &&
              !update.transactions.every((transaction) =>
                transaction.annotation(externalChange),
              )
            )
              onChangeRef.current(update.state.doc.toString());
          }),
        ],
      }),
    });
    editor.current = view;
    return () => {
      editor.current = null;
      view.destroy();
    };
  }, []);
  useEffect(() => {
    const view = editor.current;
    if (view && view.state.doc.toString() !== value)
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: value },
        annotations: externalChange.of(true),
      });
  }, [value]);
  useEffect(() => {
    editor.current?.dispatch({
      effects: readonly.current.reconfigure([
        EditorState.readOnly.of(readOnly),
        EditorView.contentAttributes.of({ "aria-readonly": String(readOnly) }),
      ]),
    });
  }, [readOnly]);
  useEffect(() => {
    const view = editor.current;
    if (!view) return;
    const diagnostics = issues.flatMap((issue) => {
      if (issue.line === null || issue.line > view.state.doc.lines) return [];
      const line = view.state.doc.line(issue.line);
      const from = Math.min(
        line.to,
        line.from + Math.max(0, (issue.column ?? 1) - 1),
      );
      return [
        {
          from,
          to: Math.min(from + 1, line.to),
          severity: "error" as const,
          message: issue.message,
        },
      ];
    });
    view.dispatch(setDiagnostics(view.state, diagnostics));
  }, [issues, value]);
  useEffect(() => {
    const view = editor.current;
    if (!view || !focusLine || focusLine > view.state.doc.lines) return;
    view.dispatch({
      selection: { anchor: view.state.doc.line(focusLine).from },
      scrollIntoView: true,
    });
    view.focus();
  }, [focusLine]);
  return <div className="configuration-code" ref={host} />;
}
