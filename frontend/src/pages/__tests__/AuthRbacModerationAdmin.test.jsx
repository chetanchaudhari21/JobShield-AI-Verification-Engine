import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import Auth from '../Auth';
import ScanHistory from '../ScanHistory';
import ModerationPortal from '../ModerationPortal';
import AdminPortal from '../AdminPortal';
import { AuthProvider } from '../../context/AuthContext';
import { api } from '../../services/api';

// Mock AuthContext hook values for testing different roles
vi.mock('../../context/AuthContext', async () => {
  const actual = await vi.importActual('../../context/AuthContext');
  return {
    ...actual,
    useAuth: vi.fn(),
  };
});

import { useAuth } from '../../context/AuthContext';

describe('Auth, RBAC, Moderation & Admin UI Components', () => {
  it('renders Auth page with login fields, security notice, and password complexity', () => {
    useAuth.mockReturnValue({
      user: null,
      role: 'VISITOR',
      isAuthenticated: false,
      login: vi.fn(),
      register: vi.fn(),
    });

    const html = renderToString(
      <MemoryRouter initialEntries={['/login']}>
        <Auth />
      </MemoryRouter>
    );

    expect(html).toContain('Sign in to JobShield AI');
    expect(html).toContain('Email Address');
    expect(html).toContain('Password');
    expect(html).toContain('Sign In');
    expect(html).toContain('Create Account');
    expect(html).toContain('Argon2id zero-knowledge credential isolation');
  });

  it('renders ScanHistory unauthenticated state prompting user login', () => {
    useAuth.mockReturnValue({
      user: null,
      role: 'VISITOR',
      isAuthenticated: false,
      loading: false,
    });

    const html = renderToString(
      <MemoryRouter>
        <ScanHistory />
      </MemoryRouter>
    );

    expect(html).toContain('Scan History &amp; Records');
    expect(html).toContain('Sign in to securely access your personal verification history');
    expect(html).toContain('Sign In');
    expect(html).toContain('Create Account');
  });

  it('renders ModerationPortal access restriction for standard USER', () => {
    useAuth.mockReturnValue({
      user: { id: 'usr-123', email: 'user@example.com', role: 'USER' },
      role: 'USER',
      isAuthenticated: true,
      loading: false,
    });

    const html = renderToString(
      <MemoryRouter>
        <ModerationPortal />
      </MemoryRouter>
    );

    expect(html).toContain('Access Restricted');
    expect(html).toContain('The Moderation Portal requires verified Moderator or Administrator privileges');
    expect(html).toContain('Current role:');
    expect(html).toContain('USER');
  });

  it('renders ModerationPortal with queue, training-isolation invariant, and audit trail for MODERATOR', () => {
    useAuth.mockReturnValue({
      user: { id: 'mod-123', email: 'mod@jobshield.ai', role: 'MODERATOR' },
      role: 'MODERATOR',
      isAuthenticated: true,
      loading: false,
    });

    const html = renderToString(
      <MemoryRouter>
        <ModerationPortal />
      </MemoryRouter>
    );

    expect(html).toContain('Moderation Portal');
    expect(html).toContain('MODERATOR');
    expect(html).toContain('Training Isolation Invariant');
    expect(html).toContain('never');
    expect(html).toContain('modify ML training labels');
    expect(html).toContain('Pending Review Queue');
    expect(html).toContain('Append-Only Audit Trail');
  });

  it('renders AdminPortal access restriction for non-admin accounts', () => {
    useAuth.mockReturnValue({
      user: { id: 'mod-123', email: 'mod@jobshield.ai', role: 'MODERATOR' },
      role: 'MODERATOR',
      isAuthenticated: true,
      loading: false,
    });

    const html = renderToString(
      <MemoryRouter>
        <AdminPortal />
      </MemoryRouter>
    );

    expect(html).toContain('Administrator Access Required');
    expect(html).toContain('The Administration Console is strictly restricted to accounts with the ADMIN role');
  });

  it('renders AdminPortal with user management and immutable security audit logs for ADMIN', () => {
    useAuth.mockReturnValue({
      user: { id: 'admin-123', email: 'admin@jobshield.ai', role: 'ADMIN' },
      role: 'ADMIN',
      isAuthenticated: true,
      loading: false,
    });

    const html = renderToString(
      <MemoryRouter>
        <AdminPortal />
      </MemoryRouter>
    );

    expect(html).toContain('Admin Console');
    expect(html).toContain('ADMIN');
    expect(html).toContain('User Accounts &amp; RBAC');
    expect(html).toContain('Append-Only Security Audit Trail');
  });

  it('verifies all API methods for Auth, Scans, Appeals, Moderation, and Admin exist on api client', () => {
    expect(typeof api.login).toBe('function');
    expect(typeof api.register).toBe('function');
    expect(typeof api.logout).toBe('function');
    expect(typeof api.getMe).toBe('function');
    expect(typeof api.changePassword).toBe('function');
    expect(typeof api.refreshToken).toBe('function');
    expect(typeof api.getMyScans).toBe('function');
    expect(typeof api.deleteScan).toBe('function');
    expect(typeof api.submitAppeal).toBe('function');
    expect(typeof api.getMyAppeals).toBe('function');
    expect(typeof api.getModerationQueue).toBe('function');
    expect(typeof api.submitModerationDecision).toBe('function');
    expect(typeof api.resolveAppeal).toBe('function');
    expect(typeof api.getModerationAuditTrail).toBe('function');
    expect(typeof api.getAdminUsers).toBe('function');
    expect(typeof api.updateUserRole).toBe('function');
    expect(typeof api.updateUserStatus).toBe('function');
    expect(typeof api.getSecurityAuditLogs).toBe('function');
  });
});
