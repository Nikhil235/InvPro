import { TradingChart } from '../dashboard/TradingChart';
import { SignalCard } from '../dashboard/SignalCard';
import { PositionCard } from '../dashboard/PositionCard';
import { RiskMetricsCard } from '../dashboard/RiskMetricsCard';
import { TradeJournalTable } from '../dashboard/TradeJournalTable';

export function DashboardHome() {
  return (
    <div className="grid grid-cols-12 gap-6 max-w-7xl mx-auto">
      <TradingChart />
      
      <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
        <SignalCard />
        <PositionCard />
        <RiskMetricsCard />
      </div>

      <TradeJournalTable />
    </div>
  );
}
