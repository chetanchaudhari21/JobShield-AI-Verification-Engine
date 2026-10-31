import React, { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Shield, Activity, Menu, X, LogIn, LogOut, User } from 'lucide-react';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';

export function Navbar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, role, isAuthenticated, logout } = useAuth();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [healthStatus, setHealthStatus] = useState({ state: 'checking', text: 'Checking API...' });

  useEffect(() => {
    let isMounted = true;
    async function verifyHealth() {
      try {
        const res = await api.checkHealth();
        if (isMounted) {
          if (res && res.status === 'healthy') {
            setHealthStatus({ state: 'online', text: 'Backend: Online' });
          } else {
            setHealthStatus({ state: 'degraded', text: 'Backend: Degraded' });
          }
        }
      } catch {
        if (isMounted) {
          setHealthStatus({ state: 'offline', text: 'Backend: Disconnected' });
        }
      }
    }
    verifyHealth();
    const interval = setInterval(verifyHealth, 15000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  const navLinks = [
    { to: '/', label: 'Home' },
    { to: '/analyze', label: 'Analyze Job' },
    { to: '/results', label: 'Analysis Results' },
  ];

  if (isAuthenticated) {
    navLinks.push({ to: '/my-scans', label: 'My Scans' });
  }

  if (role === 'MODERATOR' || role === 'ADMIN') {
    navLinks.push({ to: '/moderation', label: 'Moderation' });
  }

  if (role === 'ADMIN') {
    navLinks.push({ to: '/admin', label: 'Admin' });
  }

  navLinks.push({ to: '/about', label: 'About & Disclaimer' });

  const getStatusBadge = () => {
    if (healthStatus.state === 'online') {
      return (
        <span
          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-50 text-emerald-800 border border-emerald-300"
          title="Backend API server is running and responding to /health"
        >
          <span className="h-2 w-2 rounded-full bg-emerald-600 animate-pulse" aria-hidden="true" />
          <span>{healthStatus.text}</span>
        </span>
      );
    }
    if (healthStatus.state === 'checking') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full bg-slate-100 text-slate-700 border border-slate-300">
          <Activity className="h-3 w-3 animate-spin text-slate-500" aria-hidden="true" />
          <span>{healthStatus.text}</span>
        </span>
      );
    }
    return (
      <span
        className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-50 text-amber-900 border border-amber-300"
        title="Backend API server offline at port 8000"
      >
        <span className="h-2 w-2 rounded-full bg-amber-600" aria-hidden="true" />
        <span>{healthStatus.text}</span>
      </span>
    );
  };

  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200 print:static">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Brand */}
          <Link
            to="/"
            className="flex items-center gap-2.5 text-slate-900 font-extrabold text-lg tracking-tight hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 rounded-md p-1"
          >
            <div className="h-9 w-9 rounded-lg bg-blue-700 flex items-center justify-center text-white shadow-sm">
              <Shield className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="flex flex-col">
              <span className="leading-tight">JobShield AI</span>
              <span className="text-[10px] font-medium text-slate-500 tracking-normal uppercase">Verification Engine</span>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-1" aria-label="Main Navigation">
            {navLinks.map((link) => {
              const isActive = location.pathname === link.to;
              return (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 font-semibold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                  aria-current={isActive ? 'page' : undefined}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>

          {/* Status pill & Auth & Mobile hamburger */}
          <div className="flex items-center gap-3">
            <div className="hidden lg:block">{getStatusBadge()}</div>

            {/* Auth Buttons */}
            <div className="hidden sm:flex items-center gap-2">
              {isAuthenticated ? (
                <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg p-1 pl-2.5">
                  <div className="flex items-center gap-1.5 text-xs text-slate-700">
                    <User className="h-3.5 w-3.5 text-slate-400" />
                    <span className="font-semibold max-w-[120px] truncate">
                      {user?.full_name || user?.email?.split('@')[0]}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-800 font-bold uppercase">
                      {role}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="p-1 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors cursor-pointer"
                    title="Sign Out"
                    aria-label="Sign out of account"
                  >
                    <LogOut className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <Link
                  to="/login"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-xs transition-colors"
                >
                  <LogIn className="h-3.5 w-3.5" />
                  <span>Sign In</span>
                </Link>
              )}
            </div>

            {/* Mobile menu button */}
            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
              aria-expanded={mobileMenuOpen}
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
            </button>
          </div>
        </div>

        {/* Mobile menu dropdown */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-slate-200 py-3 space-y-1">
            <div className="px-3 pb-2 sm:hidden">{getStatusBadge()}</div>
            {navLinks.map((link) => {
              const isActive = location.pathname === link.to;
              return (
                <Link
                  key={link.to}
                  to={link.to}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`block px-3 py-2 text-base font-medium rounded-lg ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 font-semibold'
                      : 'text-slate-700 hover:bg-slate-100'
                  }`}
                  aria-current={isActive ? 'page' : undefined}
                >
                  {link.label}
                </Link>
              );
            })}

            <div className="pt-2 border-t border-slate-100 px-3">
              {isAuthenticated ? (
                <button
                  type="button"
                  onClick={() => {
                    setMobileMenuOpen(false);
                    handleLogout();
                  }}
                  className="w-full text-left py-2 text-sm text-red-600 font-medium flex items-center gap-2"
                >
                  <LogOut className="h-4 w-4" />
                  <span>Sign Out ({user?.email})</span>
                </button>
              ) : (
                <Link
                  to="/login"
                  onClick={() => setMobileMenuOpen(false)}
                  className="block text-center py-2 text-sm font-semibold text-white bg-blue-600 rounded-lg"
                >
                  Sign In / Create Account
                </Link>
              )}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}

export default Navbar;
