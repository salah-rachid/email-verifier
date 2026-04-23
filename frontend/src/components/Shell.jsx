import { Link, useLocation } from "react-router-dom";

const NAV_ITEMS = [
  { label: "Upload", href: "/" },
  { label: "Progress", href: "/jobs/demo/progress", disabled: true },
  { label: "Results", href: "/jobs/demo/results", disabled: true },
];

export function Shell({ children }) {
  const location = useLocation();

  return (
    <div className="app-shell">
      <div className="app-backdrop app-backdrop-left" />
      <div className="app-backdrop app-backdrop-right" />

      <header className="topbar">
        <Link className="brand" to="/">
          <span className="brand-mark">EV</span>
          <span className="brand-copy">
            <strong>EmailVerifier</strong>
            <span>Bulk email verification for safer sending</span>
          </span>
        </Link>

        <nav className="topnav" aria-label="Primary">
          {NAV_ITEMS.map((item) => {
            const isActive = !item.disabled && location.pathname === item.href;
            if (item.disabled) {
              return (
                <span className="nav-chip nav-chip-disabled" key={item.label}>
                  {item.label}
                </span>
              );
            }

            return (
              <Link
                className={`nav-chip ${isActive ? "nav-chip-active" : ""}`}
                key={item.label}
                to={item.href}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </header>

      <main className="page-shell">{children}</main>
    </div>
  );
}
