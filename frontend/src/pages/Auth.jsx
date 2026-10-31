import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { Shield, Lock, Mail, User, AlertCircle, CheckCircle2, ArrowRight } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function Auth() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register } = useAuth();

  const isRegisterParam = new URLSearchParams(location.search).get('mode') === 'register';
  const [isRegister, setIsRegister] = useState(isRegisterParam);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Password complexity checks
  const hasMinLen = password.length >= 8;
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasDigit = /[0-9]/.test(password);
  const isPasswordValid = hasMinLen && hasUpper && hasLower && hasDigit;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (isRegister && !isPasswordValid) {
      setError('Password must meet all complexity requirements.');
      return;
    }

    setSubmitting(true);
    try {
      if (isRegister) {
        await register(email, password, fullName);
        setSuccess('Account created successfully! Logging you in...');
        // Auto-login after registration
        await login(email, password);
        const redirectPath = location.state?.from?.pathname || '/analyze';
        navigate(redirectPath, { replace: true });
      } else {
        await login(email, password);
        const redirectPath = location.state?.from?.pathname || '/analyze';
        navigate(redirectPath, { replace: true });
      }
    } catch (err) {
      setError(err.message || 'Authentication failed. Please verify your credentials.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-md mx-auto px-4 py-12 sm:px-6">
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 sm:p-8">
        <div className="text-center mb-6">
          <div className="h-12 w-12 rounded-xl bg-blue-700 text-white flex items-center justify-center mx-auto mb-3 shadow-sm">
            <Shield className="h-7 w-7" aria-hidden="true" />
          </div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
            {isRegister ? 'Create JobShield Account' : 'Sign in to JobShield AI'}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {isRegister
              ? 'Join to access scan history, community reviews, and report appeals'
              : 'Enter your credentials to access your verification dashboard'}
          </p>
        </div>

        {/* Tab switcher */}
        <div className="flex border-b border-slate-200 mb-6" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={!isRegister}
            onClick={() => {
              setIsRegister(false);
              setError(null);
              setSuccess(null);
            }}
            className={`flex-1 pb-3 text-sm font-semibold border-b-2 text-center transition-colors ${
              !isRegister
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={isRegister}
            onClick={() => {
              setIsRegister(true);
              setError(null);
              setSuccess(null);
            }}
            className={`flex-1 pb-3 text-sm font-semibold border-b-2 text-center transition-colors ${
              isRegister
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            Create Account
          </button>
        </div>

        {error && (
          <div
            className="mb-5 p-3 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm flex items-start gap-2.5"
            role="alert"
          >
            <AlertCircle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div
            className="mb-5 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm flex items-start gap-2.5"
            role="status"
          >
            <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
            <span>{success}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {isRegister && (
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Full Name (Optional)
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <User className="h-4 w-4" />
                </div>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="e.g. Jane Doe"
                  className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-slate-900"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              Email Address
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                <Mail className="h-4 w-4" />
              </div>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.com"
                className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-slate-900"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              Password
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                <Lock className="h-4 w-4" />
              </div>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-slate-900"
              />
            </div>
          </div>

          {/* Password complexity checklist during registration */}
          {isRegister && (
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-1.5 text-slate-600">
              <span className="font-semibold block text-slate-700">Password requirements:</span>
              <div className="grid grid-cols-2 gap-1 text-[11px]">
                <div className={`flex items-center gap-1.5 ${hasMinLen ? 'text-emerald-700 font-medium' : 'text-slate-500'}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${hasMinLen ? 'bg-emerald-600' : 'bg-slate-300'}`} />
                  8+ characters
                </div>
                <div className={`flex items-center gap-1.5 ${hasUpper ? 'text-emerald-700 font-medium' : 'text-slate-500'}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${hasUpper ? 'bg-emerald-600' : 'bg-slate-300'}`} />
                  1 uppercase (A-Z)
                </div>
                <div className={`flex items-center gap-1.5 ${hasLower ? 'text-emerald-700 font-medium' : 'text-slate-500'}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${hasLower ? 'bg-emerald-600' : 'bg-slate-300'}`} />
                  1 lowercase (a-z)
                </div>
                <div className={`flex items-center gap-1.5 ${hasDigit ? 'text-emerald-700 font-medium' : 'text-slate-500'}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${hasDigit ? 'bg-emerald-600' : 'bg-slate-300'}`} />
                  1 number (0-9)
                </div>
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || (isRegister && !isPasswordValid)}
            className="w-full mt-2 py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white font-medium rounded-lg shadow-sm transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
          >
            <span>{submitting ? 'Processing...' : isRegister ? 'Register Account' : 'Sign In'}</span>
            {!submitting && <ArrowRight className="h-4 w-4" />}
          </button>
        </form>

        <div className="mt-6 pt-5 border-t border-slate-100 text-center text-xs text-slate-500">
          <span>Protected by JobShield AI Argon2id zero-knowledge credential isolation. </span>
          <Link to="/about" className="text-blue-600 hover:underline">
            Learn more
          </Link>
        </div>
      </div>
    </div>
  );
}
