import { NavLink, Outlet } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { useUiStore } from '../stores/uiStore';
import ThemeToggle from './ThemeToggle';
import AccountBadge from './AccountBadge';

const navLinks = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/live', label: 'Live' },
  { to: '/settings', label: 'Settings' },
] as const;

function NavItems({ onClick }: { onClick?: () => void }) {
  return (
    <>
      {navLinks.map(({ to, label }) => (
        <li key={to}>
          <NavLink
            to={to}
            onClick={onClick}
            className={({ isActive }) =>
              isActive ? 'active font-semibold' : ''
            }
          >
            {label}
          </NavLink>
        </li>
      ))}
    </>
  );
}

export default function Layout() {
  const accountA = useAuthStore((s) => s.accountA);
  const accountB = useAuthStore((s) => s.accountB);
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUiStore((s) => s.setSidebarOpen);

  const drawerId = 'app-drawer';

  return (
    <div className="drawer lg:drawer-open">
      <input
        id={drawerId}
        type="checkbox"
        className="drawer-toggle"
        checked={sidebarOpen}
        onChange={(e) => setSidebarOpen(e.target.checked)}
      />

      {/* Main content */}
      <div className="drawer-content flex flex-col">
        {/* Navbar */}
        <div className="navbar bg-base-100 shadow-sm lg:hidden">
          <div className="flex-none">
            <label
              htmlFor={drawerId}
              className="btn btn-square btn-ghost drawer-button"
              aria-label="Open navigation"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              </svg>
            </label>
          </div>
          <div className="flex-1">
            <span className="text-lg font-bold px-2">TG Migrator</span>
          </div>
          <div className="flex-none">
            <ThemeToggle />
          </div>
        </div>

        {/* Page content */}
        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>

      {/* Sidebar */}
      <div className="drawer-side z-40">
        <label
          htmlFor={drawerId}
          className="drawer-overlay"
          aria-label="Close navigation"
        />
        <aside className="bg-base-200 min-h-full w-64 flex flex-col">
          {/* Logo */}
          <div className="p-4 flex items-center justify-between">
            <span className="text-xl font-bold">TG Migrator</span>
            <div className="hidden lg:block">
              <ThemeToggle />
            </div>
          </div>

          {/* Navigation */}
          <ul className="menu menu-md flex-1 px-2">
            <NavItems onClick={() => setSidebarOpen(false)} />
          </ul>

          {/* Account badges */}
          <div className="p-4 space-y-2 border-t border-base-300">
            <AccountBadge account="A" info={accountA} />
            <AccountBadge account="B" info={accountB} />
          </div>
        </aside>
      </div>
    </div>
  );
}
