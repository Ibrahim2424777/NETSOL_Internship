import { useState } from 'react';
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import oneDark from 'react-syntax-highlighter/dist/esm/styles/prism/one-dark';

import { ensureSyntaxLanguagesRegistered } from '../../utils/syntaxLanguages';

ensureSyntaxLanguagesRegistered();

interface CodeBlockProps {
  language?: string;
  code: string;
}

export default function CodeBlock({ language, code }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can fail (permissions, insecure context) - the
      // code is still fully visible and selectable, so this isn't fatal.
    }
  };

  return (
    <div className="rounded-3 overflow-hidden my-2 code-block">
      <div className="d-flex justify-content-between align-items-center px-3 py-1 code-block-header">
        <span className="small text-secondary text-uppercase">{language || 'text'}</span>
        <button type="button" className="btn btn-sm btn-link text-light text-decoration-none py-0" onClick={handleCopy}>
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{ margin: 0, borderRadius: 0, fontSize: '0.875rem' }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
