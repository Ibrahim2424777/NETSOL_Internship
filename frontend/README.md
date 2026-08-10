# Frontend

React + TypeScript + Vite frontend for the AI Chatbot. For architecture, environment setup, and full
run instructions, see the [project root README](../README.md).

## Quick reference

```powershell
Copy-Item .env.example .env    # then fill in VITE_GOOGLE_CLIENT_ID
npm install
npm run dev                     # http://localhost:5173
```

Other scripts: `npm run build` (type-check + production build), `npm run lint` (oxlint), `npm run preview`
(serve the production build locally).

Requires the backend running at the URL configured in `VITE_API_BASE_URL` (see `.env.example`).
