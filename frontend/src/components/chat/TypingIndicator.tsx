export default function TypingIndicator() {
  return (
    <div className="d-flex justify-content-start mb-3">
      <div
        className="px-3 py-2 rounded-3 bg-body-secondary d-flex align-items-center gap-1"
        aria-label="Assistant is typing"
      >
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
    </div>
  );
}
