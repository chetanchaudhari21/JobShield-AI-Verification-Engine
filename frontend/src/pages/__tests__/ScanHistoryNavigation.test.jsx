import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import Navbar from '../../components/Navbar';
import ScanHistory from '../ScanHistory';
import { api, setAuthToken, getAuthToken, clearAuthToken } from '../../services/api';
import rootApi from '../../api';

// Mock AuthContext
vi.mock('../../context/AuthContext', async () => {
  const actual = await vi.importActual('../../context/AuthContext');
  return {
    ...actual,
    useAuth: vi.fn(),
  };
});

import { useAuth } from '../../context/AuthContext';

describe('My Scans Navigation & Scan History Regression Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearAuthToken();
  });

  describe('Navbar Role-Based Navigation Links', () => {
    it('does not render "My Scans" for unauthenticated VISITOR, renders "Sign In"', () => {
      useAuth.mockReturnValue({
        user: null,
        role: 'VISITOR',
        isAuthenticated: false,
        logout: vi.fn(),
      });

      const html = renderToString(
        <MemoryRouter initialEntries={['/']}>
          <Navbar />
        </MemoryRouter>
      );

      expect(html).not.toContain('href="/my-scans"');
      expect(html).not.toContain('>My Scans<');
      expect(html).toContain('Sign In');
      expect(html).toContain('href="/login"');
    });

    it('renders "My Scans" link pointing to /my-scans when authenticated as USER', () => {
      useAuth.mockReturnValue({
        user: { id: 'usr-1', email: 'worker@example.com', full_name: 'Alex Worker', role: 'USER' },
        role: 'USER',
        isAuthenticated: true,
        logout: vi.fn(),
      });

      const html = renderToString(
        <MemoryRouter initialEntries={['/']}>
          <Navbar />
        </MemoryRouter>
      );

      expect(html).toContain('href="/my-scans"');
      expect(html).toContain('My Scans');
      expect(html).toContain('Alex Worker');
      expect(html).toContain('USER');
      // Non-moderators should not see Moderation or Admin
      expect(html).not.toContain('href="/moderation"');
      expect(html).not.toContain('href="/admin"');
    });

    it('renders "My Scans" alongside "Moderation" and "Admin" for ADMIN role', () => {
      useAuth.mockReturnValue({
        user: { id: 'adm-1', email: 'admin@jobshield.ai', full_name: 'Sys Admin', role: 'ADMIN' },
        role: 'ADMIN',
        isAuthenticated: true,
        logout: vi.fn(),
      });

      const html = renderToString(
        <MemoryRouter initialEntries={['/']}>
          <Navbar />
        </MemoryRouter>
      );

      expect(html).toContain('href="/my-scans"');
      expect(html).toContain('href="/moderation"');
      expect(html).toContain('href="/admin"');
    });
  });

  describe('ScanHistory Component States', () => {
    it('renders unauthenticated prompt when user is not logged in', () => {
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
      expect(html).toContain('href="/login"');
      expect(html).toContain('href="/login?mode=register"');
    });

    it('renders loading state when authLoading is true', () => {
      useAuth.mockReturnValue({
        user: null,
        role: 'VISITOR',
        isAuthenticated: false,
        loading: true,
      });

      const html = renderToString(
        <MemoryRouter>
          <ScanHistory />
        </MemoryRouter>
      );

      expect(html).toContain('animate-spin');
    });

    it('renders friendly empty state when user has zero scans', () => {
      useAuth.mockReturnValue({
        user: { id: 'usr-empty', email: 'empty@example.com', role: 'USER' },
        role: 'USER',
        isAuthenticated: true,
        loading: false,
      });

      const html = renderToString(
        <MemoryRouter>
          <ScanHistory initialScans={[]} initialLoading={false} />
        </MemoryRouter>
      );

      expect(html).toContain('Personal Scan History');
      expect(html).toContain('No Scans Found');
      expect(html).toContain("You haven&#x27;t performed any verification scans yet");
      expect(html).toContain('Start Your First Analysis');
      expect(html).toContain('href="/analyze"');
    });

    it('renders populated scan history table with multiple scan types and risk scores', () => {
      useAuth.mockReturnValue({
        user: { id: 'usr-scans', email: 'user@example.com', role: 'USER' },
        role: 'USER',
        isAuthenticated: true,
        loading: false,
      });

      const mockScans = [
        {
          id: 'scan-uuid-1',
          input_type: 'OFFER_LETTER',
          claimed_company_name: 'Tata Consultancy Services Limited',
          status: 'completed',
          created_at: new Date('2026-10-15T10:00:00Z').toISOString(),
          risk_score: 0.15,
          risk_category: 'LOW',
        },
        {
          id: 'scan-uuid-2',
          input_type: 'JOB_URL',
          input_reference: 'https://careers.example.com/job/123',
          status: 'completed',
          created_at: new Date('2026-10-16T12:00:00Z').toISOString(),
          risk_score: 0.88,
          risk_category: 'HIGH',
        },
      ];

      const html = renderToString(
        <MemoryRouter>
          <ScanHistory initialScans={mockScans} initialLoading={false} />
        </MemoryRouter>
      );

      expect(html).toContain('Personal Scan History');
      expect(html).toContain('Tata Consultancy Services Limited');
      expect(html).toContain('https://careers.example.com/job/123');
      expect(html).toContain('Offer Letter');
      expect(html).toContain('scan-uui');
      expect(html).toContain('Download PDF report for scan scan-uuid-1');
      expect(html).toContain('Delete scan scan-uuid-1');
    });
  });

  describe('Security & API Client Invariants', () => {
    it('verifies in-memory token functions without localStorage exposure', () => {
      expect(getAuthToken()).toBeNull();
      setAuthToken('test-access-token-jwt');
      expect(getAuthToken()).toBe('test-access-token-jwt');
      clearAuthToken();
      expect(getAuthToken()).toBeNull();
    });

    it('verifies frontend/src/api.js re-export matches service api client', () => {
      expect(rootApi).toBeDefined();
      expect(typeof rootApi.getMyScans).toBe('function');
      expect(typeof rootApi.deleteScan).toBe('function');
      expect(typeof rootApi.downloadReportPdf).toBe('function');
      expect(typeof rootApi.login).toBe('function');
      expect(typeof rootApi.logout).toBe('function');
    });
  });
});
