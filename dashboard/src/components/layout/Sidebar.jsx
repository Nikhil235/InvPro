import { 
  LayoutDashboard, Activity, BookOpen, 
  Settings, Terminal, Briefcase, 
  TrendingUp, ShieldAlert, Bell, Brain
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '../../lib/utils';

const items = [
  { title: "Dashboard", icon: LayoutDashboard, path: "/" },
  { title: "Signals", icon: Activity, path: "/signals" },
  { title: "Intelligence", icon: Brain, path: "/intelligence" },
  { title: "Paper Trades", icon: Briefcase, path: "/trades" },
  { title: "Journal", icon: BookOpen, path: "/journal" },
  { title: "Performance", icon: TrendingUp, path: "/performance" },
  { title: "Risk", icon: ShieldAlert, path: "/risk" },
  { title: "Alerts", icon: Bell, path: "/alerts" },
  { title: "Logs", icon: Terminal, path: "/logs" },
  { title: "Settings", icon: Settings, path: "/settings" },
];

export function Sidebar() {
  return (
    <aside className="fixed left-0 top-16 z-40 h-[calc(100vh-4rem)] w-64 border-r border-border bg-background">
      <nav className="flex flex-col gap-2 p-4">
        {items.map((item) => (
          <NavLink
            key={item.title}
            to={item.path}
            className={({ isActive }) => 
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                isActive 
                  ? "bg-surface text-white" 
                  : "text-secondary hover:bg-surface/50 hover:text-white"
              )
            }
          >
            {({ isActive }) => (
              <>
                <item.icon className={cn("h-4 w-4", isActive ? "text-gold" : "text-secondary")} />
                {item.title}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
