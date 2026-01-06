import { useMemo, useState } from 'react';
import ChainStats from './components/ChainStats';
import BlocksTable from './components/BlocksTable';
import TxSearch from './components/TxSearch';
import type { BlockSummary, ChainOverview, TxSearchResult } from './types';
import { usePolling } from './hooks/usePolling';
import { fetchChainOverview, fetchRecentBlocks, searchLedger } from './api/aura';

const POLL_INTERVAL = 5000;

export default function App() {
  const [overview, setOverview] = useState<ChainOverview | null>(null);
  const [blocks, setBlocks] = useState<BlockSummary[]>([]);
  const [searchResult, setSearchResult] = useState<TxSearchResult | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  const refreshOverview = async () => {
    const nextOverview = await fetchChainOverview();
    setOverview(nextOverview);
    const recentBlocks = await fetchRecentBlocks(5, nextOverview.latestHeight);
    setBlocks(recentBlocks);
  };

  usePolling(refreshOverview, POLL_INTERVAL);

  const onSearch = async (value: string) => {
    setSearchError(null);
    setSearchResult(null);
    if (!value.trim()) {
      return;
    }
    try {
      const result = await searchLedger(value.trim());
      if (!result) {
        setSearchError('No block or transaction found.');
        return;
      }
      setSearchResult(result);
    } catch (error) {
      setSearchError(error instanceof Error ? error.message : 'Unable to search ledger');
    }
  };

  const blockLatency = useMemo(() => {
    if (!blocks.length) return null;
    const [latest, previous] = blocks;
    if (!latest || !previous) return null;
    const latestTime = new Date(latest.time).getTime();
    const prevTime = new Date(previous.time).getTime();
    if (!latestTime || !prevTime) return null;
    const delta = latestTime - prevTime;
    return delta > 0 ? delta / 1000 : null;
  }, [blocks]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>Aura Ping.pub Explorer</h1>
          <p>Local-first explorer powering validator insights without any cloud dependencies.</p>
        </div>
        {overview && (
          <div className="pill success">
            <span>Chain:</span>
            <strong>{overview.chainId}</strong>
          </div>
        )}
      </header>

      <div className="grid cols-2">
        <ChainStats overview={overview} blockLatency={blockLatency} />
        <TxSearch onSearch={onSearch} error={searchError} result={searchResult} />
      </div>

      <div className="panel" style={{ marginTop: '1.5rem' }}>
        <h3>Recent Blocks</h3>
        <BlocksTable blocks={blocks} />
      </div>
    </div>
  );
}
