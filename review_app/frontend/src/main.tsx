import React from 'react'
import { createRoot } from 'react-dom/client'
import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import App from './App'

const theme = createTheme({
  palette: { mode: 'light' },
  typography: {
    fontFamily: ['"Segoe UI"', 'Meiryo', '"Hiragino Kaku Gothic ProN"', 'sans-serif'].join(','),
    fontSize: 13,
  },
  components: {
    MuiChip: { defaultProps: { size: 'small' } },
    MuiButton: { defaultProps: { size: 'small' } },
    MuiTextField: { defaultProps: { size: 'small' } },
  },
})

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>,
)
