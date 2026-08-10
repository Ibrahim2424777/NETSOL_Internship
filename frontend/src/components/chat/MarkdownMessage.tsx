import { isValidElement } from 'react';
import type { ReactNode } from 'react';
import Markdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';

import CodeBlock from './CodeBlock';

// Gemini often writes math as LaTeX ($x^2$, $\rightarrow$, etc.) - plain
// remark-gfm has no idea what `$...$` means and renders it as literal text
// (dollar signs, backslashes and all). remark-math parses those delimiters
// into math nodes, rehype-katex renders them; katex.css (imported once here)
// is what actually makes the rendered output look like math instead of
// unstyled HTML.
import 'katex/dist/katex.min.css';

// Only `pre` is overridden, not `code`. A fenced code block is always
// <pre><code>...</code></pre>, while inline code is a bare <code> with no
// <pre> wrapper - so overriding `pre` unambiguously means "this is a block",
// regardless of whether a language was given after the triple backticks.
// (Overriding `code` instead can't make that distinction: an unlabeled
// fenced block ```like this``` gets no className, identical to inline code.)
function extractText(node: ReactNode): string {
  if (typeof node === 'string') return node;
  if (Array.isArray(node)) return node.map(extractText).join('');
  return '';
}

function PreOverride({ children }: { children?: ReactNode }) {
  if (isValidElement<{ className?: string; children?: ReactNode }>(children)) {
    const { className, children: codeChildren } = children.props;
    const match = /language-(\w+)/.exec(className ?? '');
    const code = extractText(codeChildren).replace(/\n$/, '');
    return <CodeBlock language={match?.[1]} code={code} />;
  }
  return <pre>{children}</pre>;
}

export default function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="markdown-content">
      <Markdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          pre: PreOverride,
          a: ({ href, children, ...props }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
              {children}
            </a>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}
