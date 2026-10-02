/**
 * Front-end entry point: loads the global stylesheet and mounts `<App />` into `#root` in
 * `index.html`, inside StrictMode (which double-runs effects in development only).
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
