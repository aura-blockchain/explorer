export interface ChainOverview {
  chainId: string;
  validatorMoniker: string;
  latestHeight: number;
  latestTime: string;
  catchingUp: boolean;
  peers: number;
}

export interface BlockSummary {
  height: number;
  time: string;
  proposer: string;
  txs: number;
  hash: string;
}

export interface TxSearchResult {
  type: 'block' | 'transaction';
  height: number;
  hash: string;
  payload: unknown;
}
