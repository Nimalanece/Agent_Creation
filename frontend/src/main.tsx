import React from 'react'
import { createRoot } from 'react-dom/client'
import AnalyzePage from './pages/AnalyzePage'
import './index.css'

const container = document.getElementById('root')!
const root = createRoot(container)
root.render(
  <React.StrictMode>
    <AnalyzePage />
  </React.StrictMode>
)
