// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

import HomeView from './components/HomeView.jsx';
import SettingsView from './components/SettingsView.jsx';
import CreditCardsView from './components/CreditCardsView.jsx';
import CheckingAccountsView from './components/CheckingAccountsView.jsx';
import CertificateAccountsView from './components/CertificateAccountsView.jsx';
import SavingsAccountsView from './components/SavingsAccountsView.jsx';
import MortgagesView from './components/MortgagesView.jsx';
import MortgageRatesView from './components/MortgageRatesView.jsx';
import HelpCenterView from './components/HelpCenterView.jsx';
import FeeScheduleView from './components/FeeScheduleView.jsx';
import DisclosuresView from './components/DisclosuresView.jsx';
import EditProfileView from './components/EditProfileView.jsx';
import SearchView from './components/SearchView.jsx';
import SecureMessagingView from './components/SecureMessagingView.jsx';
import DebugView from './components/DebugView.jsx';
import AdminMessagingView from './components/AdminMessagingView.jsx';
import ApplyCreditCardView from './components/ApplyCreditCardView.jsx';
import AdminUnderwritingView from './components/AdminUnderwritingView.jsx';
import AdminDashboardView from './components/AdminDashboardView.jsx';
import VoiceSupportView from './components/VoiceSupportView.jsx';
import AgentSupportDashboard from './components/AgentSupportDashboard.jsx';

/**
 * Reusable wrapper to protect authenticated routes
 */
const ProtectedRoute = ({ isReady, fbUser, children }) => {
  if (!isReady) return null; // Prevent redirects while firebase auth is loading
  return fbUser ? children : <Navigate to="/" replace />;
};

export default function AppRoutes({
  fbUser,
  isReady,
  customerProfile,
  setCustomerProfile,
  loanAmount,
  setLoanAmount,
  loanTerm,
  setLoanTerm,
  activeBot,
  setActiveBot,
  calculateMonthlyPayment,
  interestRate
}) {
  return (
    <Routes>
      <Route path="/" element={
        <HomeView
          loanAmount={loanAmount}
          setLoanAmount={setLoanAmount}
          loanTerm={loanTerm}
          setLoanTerm={setLoanTerm}
          activeBot={activeBot}
          setActiveBot={setActiveBot}
          calculateMonthlyPayment={calculateMonthlyPayment}
          interestRate={interestRate}
        />
      } />
      <Route path="/checking-accounts" element={
        <CheckingAccountsView activeBot={activeBot} setActiveBot={setActiveBot} />
      } />
      <Route path="/savings-accounts" element={
        <SavingsAccountsView />
      } />
      <Route path="/certificate-accounts" element={
        <CertificateAccountsView />
      } />
      <Route path="/credit-cards" element={
        <CreditCardsView activeBot={activeBot} setActiveBot={setActiveBot} />
      } />
      <Route path="/mortgages" element={
        <MortgagesView activeBot={activeBot} setActiveBot={setActiveBot} />
      } />
      <Route path="/mortgage-rates" element={
        <MortgageRatesView />
      } />
      <Route path="/help-center" element={
        <HelpCenterView activeBot={activeBot} setActiveBot={setActiveBot} />
      } />
      <Route path="/fee-schedule" element={
        <FeeScheduleView activeBot={activeBot} setActiveBot={setActiveBot} />
      } />
      <Route path="/disclosures" element={
        <DisclosuresView />
      } />
      <Route path="/settings" element={
        <SettingsView />
      } />

      {/* Protected routes gated by fbUser session */}
      <Route path="/edit-profile" element={
        <ProtectedRoute isReady={isReady} fbUser={fbUser}>
          <EditProfileView
            customerProfile={customerProfile}
            setCustomerProfile={setCustomerProfile}
            fbUser={fbUser}
          />
        </ProtectedRoute>
      } />
      <Route path="/apply/credit-card" element={
        <ProtectedRoute isReady={isReady} fbUser={fbUser}>
          <ApplyCreditCardView
            customerProfile={customerProfile}
            fbUser={fbUser}
          />
        </ProtectedRoute>
      } />
      <Route path="/secure-messaging" element={
        <ProtectedRoute isReady={isReady} fbUser={fbUser}>
          <SecureMessagingView
            customerProfile={customerProfile}
            fbUser={fbUser}
          />
        </ProtectedRoute>
      } />
      <Route path="/debug" element={
        <ProtectedRoute isReady={isReady} fbUser={fbUser}>
          <DebugView
            customerProfile={customerProfile}
            fbUser={fbUser}
          />
        </ProtectedRoute>
      } />
      <Route path="/admin" element={
        <ProtectedRoute isReady={isReady} fbUser={fbUser}>
          <AdminDashboardView />
        </ProtectedRoute>
      } />
      <Route path="/admin/messaging" element={
        <ProtectedRoute isReady={isReady} fbUser={fbUser}>
          <AdminMessagingView
            fbUser={fbUser}
          />
        </ProtectedRoute>
      } />
      <Route path="/admin/underwriting" element={
        <ProtectedRoute isReady={isReady} fbUser={fbUser}>
          <AdminUnderwritingView
            fbUser={fbUser}
          />
        </ProtectedRoute>
      } />
      <Route path="/search" element={
        <ProtectedRoute isReady={isReady} fbUser={fbUser}>
          <SearchView />
        </ProtectedRoute>
      } />
      <Route path="/support/voice" element={
        <ProtectedRoute isReady={isReady} fbUser={fbUser}>
          <VoiceSupportView />
        </ProtectedRoute>
      } />
      <Route path="/admin/support" element={
        <ProtectedRoute isReady={isReady} fbUser={fbUser}>
          <AgentSupportDashboard />
        </ProtectedRoute>
      } />
    </Routes>
  );
}
