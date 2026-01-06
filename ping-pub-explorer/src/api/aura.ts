import type { BlockSummary, ChainOverview, TxSearchResult } from '../types';

const RPC_BASE = '/rpc';

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${response.status} ${response.statusText} - ${message}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchChainOverview(): Promise<ChainOverview> {
  const [status, netInfo] = await Promise.all([
    fetchJson<RpcStatusResponse>(`${RPC_BASE}/status`),
    fetchJson<RpcNetInfoResponse>(`${RPC_BASE}/net_info`),
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

export async function fetchRecentBlocks(count = 5, latestHeight?: number): Promise<BlockSummary[]> {
  let height = latestHeight;
  if (!height) {
    const status = await fetchJson<RpcStatusResponse>(`${RPC_BASE}/status`);
    height = Number(status.result.sync_info.latest_block_height);
  }
  const heights = Array.from({ length: count }, (_, index) => Math.max(height! - index, 1));
  const responses = await Promise.all(heights.map((h) => fetchJson<RpcBlockResponse>(`${RPC_BASE}/block?height=${h}`)));
  return responses.map((block) => ({
    height: Number(block.result.block.header.height),
    time: block.result.block.header.time,
    proposer: block.result.block.header.proposer_address,
    txs: block.result.block.data.txs?.length ?? 0,
    hash: block.result.block_id.hash,
  }));
}

export async function searchLedger(query: string): Promise<TxSearchResult | null> {
  if (/^\d+$/.test(query)) {
    const targetHeight = Number(query);
    const block = await fetchJson<RpcBlockResponse>(`${RPC_BASE}/block?height=${targetHeight}`);
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
    const tx = await fetchJson<RpcTxResponse>(`${RPC_BASE}/tx?hash=${normalized}`);
    return {
      type: 'transaction',
      height: Number(tx.result.height),
      hash: tx.result.hash,
      payload: tx.result,
    };
  } catch (error) {
    console.warn('Tx lookup failed, falling back to block search:', error);
    return null;
  }
}

function normalizeHash(value: string): string | null {
  const hex = value.toLowerCase().startsWith('0x') ? value.slice(2) : value;
  if (!/^[0-9a-f]{64}$/i.test(hex)) {
    return null;
  }
  return `0x${hex.toUpperCase()}`;
}

interface RpcStatusResponse {
  result: {
    node_info: {
      id: string;
      network: string;
      moniker: string;
    };
    sync_info: {
      latest_block_height: string;
      latest_block_time: string;
      catching_up: boolean;
    };
    validator_info: {
      address: string;
      voting_power: string;
    };
  };
}

interface RpcNetInfoResponse {
  result: {
    n_peers: string;
  };
}

interface RpcBlockResponse {
  result: {
    block_id: {
      hash: string;
    };
    block: {
      header: {
        height: string;
        time: string;
        proposer_address: string;
      };
      data: {
        txs?: string[];
      };
    };
  };
}

interface RpcTxResponse {
  result: {
    hash: string;
    height: string;
    tx_result: {
      code: number;
      gas_used: string;
      gas_wanted: string;
      log: string;
    };
    tx: string;
  };
}
