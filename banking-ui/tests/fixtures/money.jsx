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

import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import BillPayModal from '../../src/components/BillPayModal.jsx';
import { getAccountsSummary } from '../../src/utils/api.js';
import { formatMoney } from '../../src/utils/money.js';
import { useMoneyLocale } from '../../src/utils/moneyLocale.js';
import '../../src/index.css';

const currency = new URLSearchParams(window.location.search).get('currency') || 'USD';
const value = amount_minor => ({amount_minor, currency_code: currency});
const initial = {
  deposit_accounts: [{account_id:'11111111-1111-4111-8111-111111111111', account_number:'CHECK-1234',
    product_name:'Demo checking', currency_code:currency, cleared_balance:value(10000)}],
  credit_accounts: [{account_id:'22222222-2222-4222-8222-222222222222', currency_code:currency,
    cleared_balance:value(5000), available_credit:value(5000), credit_limit:value(10000)}],
};
function Fixture() {
  const [open, setOpen] = useState(true);
  const [accounts, setAccounts] = useState(initial);
  const [locale] = useMoneyLocale();
  return <main className="p-8"><h1>Money fixture — {currency}</h1>
    <p data-testid="deposit-balance">{formatMoney(accounts.deposit_accounts[0].cleared_balance, locale)}</p>
    <p data-testid="card-balance">{formatMoney(accounts.credit_accounts[0].cleared_balance, locale)}</p>
    <button onClick={() => setOpen(true)}>Open payment</button>
    <BillPayModal isOpen={open} onClose={() => setOpen(false)} accountsData={accounts}
      onPaymentSuccess={async () => setAccounts(await getAccountsSummary())} />
  </main>;
}
createRoot(document.getElementById('root')).render(<BrowserRouter><Fixture /></BrowserRouter>);
