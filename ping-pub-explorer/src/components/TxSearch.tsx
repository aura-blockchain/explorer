import { useState } from 'react';
import type { TxSearchResult } from '../types';

interface Props {
  onSearch: (value: string) => Promise<void>;
  result: TxSearchResult | null;
  error: string | null;
}

export default function TxSearch({ onSearch, result, error }: Props) {
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    try {
      await onSearch(value);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel">
      <h3>Search Blocks & Transactions</h3>
      <form className="tx-search" onSubmit={handleSubmit}>
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Enter block height or Tx hash"
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>
      {error && <p style={{ color: '#f87171', marginTop: '1rem' }}>{error}</p>}
      {result && (
        <div className="tx-result">
          <strong>{result.type === 'block' ? 'Block' : 'Transaction'}</strong> @ height {result.height}
          <br />
          Hash: {result.hash}
        </div>
      )}
    </div>
  );
}
