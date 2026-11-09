import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { keepPreviousData, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import { API_POLL_MS } from './config';
import './style.css';

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
