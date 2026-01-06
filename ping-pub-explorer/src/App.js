import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo, useState } from 'react';
import ChainStats from './components/ChainStats';
import BlocksTable from './components/BlocksTable';
import TxSearch from './components/TxSearch';
import { usePolling } from './hooks/usePolling';
import { fetchChainOverview, fetchRecentBlocks, searchLedger } from './api/aura';
const POLL_INTERVAL = 5000;
export default function App() {
    const [overview, setOverview] = useState(null);
    const [blocks, setBlocks] = useState([]);
    const [searchResult, setSearchResult] = useState(null);
    const [searchError, setSearchError] = useState(null);
    const refreshOverview = async () => {
        const nextOverview = await fetchChainOverview();
        setOverview(nextOverview);
        const recentBlocks = await fetchRecentBlocks(5, nextOverview.latestHeight);
        setBlocks(recentBlocks);
    };
    usePolling(refreshOverview, POLL_INTERVAL);
    const onSearch = async (value) => {
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
        }
        catch (error) {
            setSearchError(error instanceof Error ? error.message : 'Unable to search ledger');
        }
    };
    const blockLatency = useMemo(() => {
        if (!blocks.length)
            return null;
        const [latest, previous] = blocks;
        if (!latest || !previous)
            return null;
        const latestTime = new Date(latest.time).getTime();
        const prevTime = new Date(previous.time).getTime();
        if (!latestTime || !prevTime)
            return null;
        const delta = latestTime - prevTime;
        return delta > 0 ? delta / 1000 : null;
    }, [blocks]);
    return (_jsxs("div", { className: "app-shell", children: [_jsxs("header", { className: "app-header", children: [_jsxs("div", { children: [_jsx("h1", { children: "Aura Ping.pub Explorer" }), _jsx("p", { children: "Local-first explorer powering validator insights without any cloud dependencies." })] }), overview && (_jsxs("div", { className: "pill success", children: [_jsx("span", { children: "Chain:" }), _jsx("strong", { children: overview.chainId })] }))] }), _jsxs("div", { className: "grid cols-2", children: [_jsx(ChainStats, { overview: overview, blockLatency: blockLatency }), _jsx(TxSearch, { onSearch: onSearch, error: searchError, result: searchResult })] }), _jsxs("div", { className: "panel", style: { marginTop: '1.5rem' }, children: [_jsx("h3", { children: "Recent Blocks" }), _jsx(BlocksTable, { blocks: blocks })] })] }));
}
