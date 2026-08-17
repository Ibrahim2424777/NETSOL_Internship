// Minimal footer - only real links (section 20: don't invent Pricing/About/
// Blog pages that don't exist).
export default function LandingFooter() {
  return (
    <footer className="landing-footer py-4">
      <div className="container d-flex flex-column flex-sm-row align-items-center justify-content-between gap-2 text-center text-sm-start">
        <span className="d-inline-flex align-items-center gap-2">
          <span aria-hidden="true">✦</span> Your AI Workspace
        </span>
        <span>Built for conversations that matter. © {new Date().getFullYear()}</span>
      </div>
    </footer>
  );
}
