import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import type { ChainOverview } from '../types';

dayjs.extend(relativeTime);

interface Props {
  overview: ChainOverview | null;
  blockLatency: number | null;
}

export default function ChainStats({ overview, blockLatency }: Props) {
  return (
    <div className="panel">
      <h3>Network Status</h3>
      {overview ? (
        <div className="stat-grid">
          <div className="stat">
            <span className="stat-label">Validator</span>
            <span className="stat-value">{overview.validatorMoniker}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Latest Block</span>
            <span className="stat-value">#{overview.latestHeight.toLocaleString()}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Block Time</span>
            <span className="stat-value">{blockLatency ? `${blockLatency.toFixed(2)}s` : '—'}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Peers Connected</span>
            <span className="stat-value">{overview.peers}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Last Block Time</span>
            <span className="stat-value">{dayjs(overview.latestTime).fromNow()}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Syncing</span>
            <span className="stat-value">{overview.catchingUp ? 'Catching Up' : 'Healthy'}</span>
          </div>
        </div>
      ) : (
        <p>Loading chain overview…</p>
      )}
    </div>
  );
}
