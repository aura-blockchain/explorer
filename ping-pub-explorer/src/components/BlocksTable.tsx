import type { BlockSummary } from '../types';

interface Props {
  blocks: BlockSummary[];
}

export default function BlocksTable({ blocks }: Props) {
  if (!blocks.length) {
    return <p>No blocks yet. Ensure the local validators are running via docker-compose.testnet.</p>;
  }

  return (
    <table className="blocks-table">
      <thead>
        <tr>
          <th>Height</th>
          <th>Time</th>
          <th>Txs</th>
          <th>Proposer</th>
          <th>Hash</th>
        </tr>
      </thead>
      <tbody>
        {blocks.map((block) => (
          <tr key={block.height}>
            <td>#{block.height.toLocaleString()}</td>
            <td>{new Date(block.time).toLocaleTimeString()}</td>
            <td>{block.txs}</td>
            <td>{block.proposer.slice(0, 12)}…</td>
            <td>{block.hash.slice(0, 12)}…</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
