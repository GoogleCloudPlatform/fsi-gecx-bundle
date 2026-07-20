# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.


# Architecture Documentation

- [Google Analytics Instrumentation (Banking UI)](../docs/architecture/web-experience/google_analytics_banking_ui.md) — how `page_view` and interaction events are emitted, and what to do when adding a route or a clickable element.

# Running
```bash
docker build -t banking-ui .

docker run -p 5173:5173 \
  -e PORT=5173 \
  -e VITE_BANKING_API_URL="http://localhost:8080" \
  -e VITE_CCAI_COMPANY_ID="17762261086439462b8f0b64f6cd0d5e3" \
  -e VITE_CCAI_HOST="https://fsi-test-4000-jz3ioz1.uc1.ccaiplatform.com" \
  banking-ui
```