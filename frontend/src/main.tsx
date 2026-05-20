import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Design token contract — single import point for all --gruvax-* CSS custom properties.
// This is the ONLY place the token file enters the SPA. Components consume via var(--gruvax-*).
import '../../design/gruvax-design-tokens.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
