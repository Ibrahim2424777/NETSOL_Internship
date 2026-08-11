export default function TypingIndicator() {
  return (
    <div className="mb-4" aria-label="Assistant is typing">
      <div className="d-flex align-items-center gap-2 mb-2">
        <span className="assistant-avatar d-inline-flex align-items-center justify-content-center" aria-hidden="true">
          ✦
        </span>
        <span className="small fw-medium text-secondary">Thinking</span>
      </div>
      <div className="d-flex align-items-center gap-1 ps-1">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
    </div>
  );
}
