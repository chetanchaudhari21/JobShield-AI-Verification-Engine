import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldAlert,
  Search,
  Lock,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';

export default function AdminPortal() {
  const { user, role, loading: authLoading } = useAuth();
  const isAdmin = role === 'ADMIN';

  const [activeTab, setActiveTab] = useState('users'); // 'users' | 'security_audit'
  const [users, setUsers] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);
  const [actionInProgress, setActionInProgress] = useState(false);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getAdminUsers({
        search: searchQuery || undefined,
        limit: 50,
        offset: 0,
      });
      setUsers(data?.items || []);
    } catch (err) {
      setError(err.message || 'Failed to load user records.');
    } finally {
      setLoading(false);
    }
  }, [searchQuery]);

  const fetchSecurityAuditLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getSecurityAuditLogs({ limit: 50, offset: 0 });
      setAuditLogs(data?.items || []);
    } catch (err) {
      setError(err.message || 'Failed to load security audit logs.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && isAdmin) {
      if (activeTab === 'users') {
        fetchUsers();
      } else if (activeTab === 'security_audit') {
        fetchSecurityAuditLogs();
      }
    } else if (!authLoading && !isAdmin) {
      setLoading(false);
    }
  }, [authLoading, isAdmin, activeTab, fetchUsers, fetchSecurityAuditLogs]);

  const handleRoleChange = async (targetUserId, newRole) => {
    setActionInProgress(true);
    setError(null);
    try {
      await api.updateUserRole(targetUserId, newRole);
      setActionSuccess(`User role updated to ${newRole}.`);
      fetchUsers();
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err) {
      setError(err.message || 'Failed to update user role.');
    } finally {
      setActionInProgress(false);
    }
  };

  const handleStatusToggle = async (targetUserId, currentStatus) => {
    const action = currentStatus ? 'suspend' : 'activate';
    if (!window.confirm(`Are you sure you want to ${action} this account? Suspending will terminate all active sessions.`)) {
      return;
    }
    setActionInProgress(true);
    setError(null);
    try {
      await api.updateUserStatus(targetUserId, !currentStatus);
      setActionSuccess(`User account ${!currentStatus ? 'activated' : 'suspended and sessions terminated'}.`);
      fetchUsers();
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err) {
      setError(err.message || 'Failed to update user status.');
    } finally {
      setActionInProgress(false);
    }
  };

  if (authLoading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 flex items-center justify-center">
        <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="bg-white rounded-2xl border border-red-200 p-8 shadow-sm">
          <ShieldAlert className="h-12 w-12 text-red-600 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-slate-900 mb-2">Administrator Access Required</h1>
          <p className="text-slate-600 text-sm mb-4">
            The Administration Console is strictly restricted to accounts with the ADMIN role.
          </p>
          <span className="text-xs text-slate-400">
            Current role: {role || 'VISITOR'}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-red-50 text-red-700 flex items-center justify-center">
              <Lock className="h-5 w-5" />
            </div>
            <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Admin Console</h1>
            <span className="text-xs px-2.5 py-0.5 rounded-full font-bold bg-red-100 text-red-800">
              ADMIN
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            System governance, role assignments, account suspensions, and append-only audit trail
          </p>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm flex items-start gap-2.5">
          <AlertCircle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm flex items-start gap-2.5">
          <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-slate-200">
        <button
          type="button"
          onClick={() => setActiveTab('users')}
          className={`px-5 py-3 text-sm font-semibold border-b-2 transition-colors cursor-pointer ${
            activeTab === 'users'
              ? 'border-red-600 text-red-700'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          User Accounts &amp; RBAC ({users.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('security_audit')}
          className={`px-5 py-3 text-sm font-semibold border-b-2 transition-colors cursor-pointer ${
            activeTab === 'security_audit'
              ? 'border-red-600 text-red-700'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          Append-Only Security Audit Trail
        </button>
      </div>

      {/* User Management Tab */}
      {activeTab === 'users' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 bg-white p-3.5 rounded-xl border border-slate-200">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search users by email or name..."
              className="w-full text-xs text-slate-900 focus:outline-none"
            />
          </div>

          {loading ? (
            <div className="py-16 text-center">
              <Loader2 className="h-8 w-8 text-red-600 animate-spin mx-auto mb-2" />
              <p className="text-sm text-slate-500">Loading user accounts...</p>
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-slate-600">
                  <thead className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    <tr>
                      <th scope="col" className="px-6 py-3.5">User</th>
                      <th scope="col" className="px-6 py-3.5">Role</th>
                      <th scope="col" className="px-6 py-3.5">Status</th>
                      <th scope="col" className="px-6 py-3.5">Created</th>
                      <th scope="col" className="px-6 py-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {users.map((u) => (
                      <tr key={u.id} className="hover:bg-slate-50/70">
                        <td className="px-6 py-4">
                          <div className="font-semibold text-slate-900">{u.full_name || 'Anonymous User'}</div>
                          <div className="text-xs text-slate-500">{u.email}</div>
                          <div className="text-[10px] text-slate-400 font-mono">{u.id.slice(0, 8)}...</div>
                        </td>
                        <td className="px-6 py-4">
                          <select
                            value={u.role}
                            disabled={actionInProgress || u.id === user?.id}
                            onChange={(e) => handleRoleChange(u.id, e.target.value)}
                            className="text-xs font-semibold px-2.5 py-1 rounded-md border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-red-500"
                          >
                            <option value="USER">USER</option>
                            <option value="MODERATOR">MODERATOR</option>
                            <option value="ADMIN">ADMIN</option>
                          </select>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                            u.is_active
                              ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                              : 'bg-red-50 text-red-800 border border-red-200'
                          }`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${u.is_active ? 'bg-emerald-600' : 'bg-red-600'}`} />
                            {u.is_active ? 'Active' : 'Suspended'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-xs text-slate-500 whitespace-nowrap">
                          {new Date(u.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-6 py-4 text-right">
                          {u.id !== user?.id && (
                            <button
                              type="button"
                              disabled={actionInProgress}
                              onClick={() => handleStatusToggle(u.id, u.is_active)}
                              className={`text-xs font-semibold px-3 py-1.5 rounded-lg border transition-colors cursor-pointer ${
                                u.is_active
                                  ? 'border-red-200 text-red-700 hover:bg-red-50'
                                  : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'
                              }`}
                            >
                              {u.is_active ? 'Suspend User' : 'Activate User'}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Security Audit Trail Tab */}
      {activeTab === 'security_audit' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
              Immutable Security Audit Records ({auditLogs.length})
            </span>
            <span className="text-xs text-slate-400 italic">
              Mandatory Append-Only Audit Logging
            </span>
          </div>

          {loading ? (
            <div className="py-16 text-center">
              <Loader2 className="h-8 w-8 text-red-600 animate-spin mx-auto mb-2" />
              <p className="text-sm text-slate-500">Loading audit records...</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-600">
                <thead className="bg-slate-100 border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  <tr>
                    <th scope="col" className="px-6 py-3">Timestamp</th>
                    <th scope="col" className="px-6 py-3">Action</th>
                    <th scope="col" className="px-6 py-3">Actor (User ID)</th>
                    <th scope="col" className="px-6 py-3">Target</th>
                    <th scope="col" className="px-6 py-3">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono text-xs">
                  {auditLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-slate-50/70">
                      <td className="px-6 py-3.5 text-slate-500 whitespace-nowrap">
                        {new Date(log.created_at).toLocaleString()}
                      </td>
                      <td className="px-6 py-3.5">
                        <span className="px-2 py-0.5 rounded-full font-bold text-[10px] bg-slate-200 text-slate-800">
                          {log.action}
                        </span>
                      </td>
                      <td className="px-6 py-3.5 text-slate-800 font-medium">
                        {log.user_id ? log.user_id.slice(0, 12) + '...' : 'System / Anonymous'}
                      </td>
                      <td className="px-6 py-3.5">
                        <span className="text-slate-600 font-bold block">{log.target_type || 'N/A'}</span>
                        <span className="text-slate-400 text-[10px]">{log.target_id || ''}</span>
                      </td>
                      <td className="px-6 py-3.5 font-sans text-xs text-slate-600 max-w-xs truncate">
                        {log.details ? JSON.stringify(log.details) : 'None'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
