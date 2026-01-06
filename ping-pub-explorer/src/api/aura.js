const RPC_BASE = '/rpc';
async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        const message = await response.text();
        throw new Error(`${response.status} ${response.statusText} - ${message}`);
    }
    return response.json();
}
export async function fetchChainOverview() {
    const [status, netInfo] = await Promise.all([
        fetchJson(`${RPC_BASE}/status`),
        fetchJson(`${RPC_BASE}/net_info`),
    ]);
    const { node_info, sync_info, validator_info } = status.result;
    return {
        chainId: node_info.network,
        validatorMoniker: node_info.moniker,
        latestHeight: Number(sync_info.latest_block_height),
        latestTime: sync_info.latest_block_time,
        catchingUp: sync_info.catching_up,
        peers: Number(netInfo.result.n_peers),
    };
}
export async function fetchRecentBlocks(count = 5, latestHeight) {
    let height = latestHeight;
    if (!height) {
        const status = await fetchJson(`${RPC_BASE}/status`);
        height = Number(status.result.sync_info.latest_block_height);
    }
    const heights = Array.from({ length: count }, (_, index) => Math.max(height - index, 1));
    const responses = await Promise.all(heights.map((h) => fetchJson(`${RPC_BASE}/block?height=${h}`)));
    return responses.map((block) => ({
        height: Number(block.result.block.header.height),
        time: block.result.block.header.time,
        proposer: block.result.block.header.proposer_address,
        txs: block.result.block.data.txs?.length ?? 0,
        hash: block.result.block_id.hash,
    }));
}
export async function searchLedger(query) {
    if (/^\d+$/.test(query)) {
        const targetHeight = Number(query);
        const block = await fetchJson(`${RPC_BASE}/block?height=${targetHeight}`);
        return {
            type: 'block',
            height: targetHeight,
            hash: block.result.block_id.hash,
            payload: block.result,
        };
    }
    const normalized = normalizeHash(query);
    if (!normalized) {
        return null;
    }
    try {
        const tx = await fetchJson(`${RPC_BASE}/tx?hash=${normalized}`);
        return {
            type: 'transaction',
            height: Number(tx.result.height),
            hash: tx.result.hash,
            payload: tx.result,
        };
    }
    catch (error) {
        console.warn('Tx lookup failed, falling back to block search:', error);
        return null;
    }
}
function normalizeHash(value) {
    const hex = value.toLowerCase().startsWith('0x') ? value.slice(2) : value;
    if (!/^[0-9a-f]{64}$/i.test(hex)) {
        return null;
    }
    return `0x${hex.toUpperCase()}`;
}
