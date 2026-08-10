// Registers a curated set of common languages with the "light" Prism build
// (react-syntax-highlighter's recommended pattern for production use) rather
// than importing the full language bundle, which is considerably larger.
// An unlisted language just falls back to unhighlighted monospace text - it
// still renders correctly, it's just not colorized.
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';

import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import c from 'react-syntax-highlighter/dist/esm/languages/prism/c';
import cpp from 'react-syntax-highlighter/dist/esm/languages/prism/cpp';
import csharp from 'react-syntax-highlighter/dist/esm/languages/prism/csharp';
import css from 'react-syntax-highlighter/dist/esm/languages/prism/css';
import go from 'react-syntax-highlighter/dist/esm/languages/prism/go';
import java from 'react-syntax-highlighter/dist/esm/languages/prism/java';
import javascript from 'react-syntax-highlighter/dist/esm/languages/prism/javascript';
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import jsx from 'react-syntax-highlighter/dist/esm/languages/prism/jsx';
import markdown from 'react-syntax-highlighter/dist/esm/languages/prism/markdown';
import markup from 'react-syntax-highlighter/dist/esm/languages/prism/markup';
import php from 'react-syntax-highlighter/dist/esm/languages/prism/php';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import ruby from 'react-syntax-highlighter/dist/esm/languages/prism/ruby';
import rust from 'react-syntax-highlighter/dist/esm/languages/prism/rust';
import sql from 'react-syntax-highlighter/dist/esm/languages/prism/sql';
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';
import tsx from 'react-syntax-highlighter/dist/esm/languages/prism/tsx';
import yaml from 'react-syntax-highlighter/dist/esm/languages/prism/yaml';

const LANGUAGES: Record<string, unknown> = {
  bash,
  sh: bash,
  shell: bash,
  c,
  cpp,
  csharp,
  css,
  go,
  java,
  javascript,
  js: javascript,
  json,
  jsx,
  markdown,
  md: markdown,
  markup,
  html: markup,
  xml: markup,
  php,
  python,
  py: python,
  ruby,
  rust,
  sql,
  typescript,
  ts: typescript,
  tsx,
  yaml,
  yml: yaml,
};

let registered = false;

export function ensureSyntaxLanguagesRegistered(): void {
  if (registered) return;
  for (const [name, definition] of Object.entries(LANGUAGES)) {
    SyntaxHighlighter.registerLanguage(name, definition as never);
  }
  registered = true;
}
