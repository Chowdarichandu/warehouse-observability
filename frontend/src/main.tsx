import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { keepPreviousData, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import { API_POLL_MS } from './config';
import '@fontsource/ibm-plex-sans/latin-400.css';
import '@fontsource/ibm-plex-sans/latin-500.css';
import '@fontsource/ibm-plex-sans/latin-600.css';
import '@fontsource/ibm-plex-mono/latin-400.css';
import '@fontsource/ibm-plex-mono/latin-500.css';
import './styles/tokens.css';
import './app.css';

const client = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: API_POLL_MS,
      staleTime: 15_000,
      retry: 1,
      placeholderData: keepPreviousData,
    },
  },
});
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
