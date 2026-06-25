import { Header } from './Header';
import { Sidebar } from './Sidebar';

export function DashboardLayout({ children }) {
  return (
    <div className="min-h-screen bg-background text-primary">
      <Header />
      <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
        <Sidebar />
        <main className="ml-64 flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
