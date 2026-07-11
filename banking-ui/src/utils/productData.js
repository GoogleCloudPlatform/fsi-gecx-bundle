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

export const checkingAccounts = [
  {
    name: "Nova Classic Everyday",
    tag: "Core Digital Convenience",
    apy: "0.02% APY",
    monthlyFee: "$0",
    feeWaiver: "No minimum balance or direct deposit required",
    minOpen: "$0",
    atmAccess: "Up to 12 out-of-network fee reimbursements monthly",
    rewards: "Standard rewards points on signature debit purchases",
    loanDiscount: "None",
    bestFor: "Students, young professionals, and simple transparent day-to-day banking",
    cardStyle: "from-slate-900 via-teal-950 to-slate-900 border-teal-500/30 text-teal-400",
    chipStyle: "bg-teal-400/20 border-teal-500/40 text-teal-300",
    accentColor: "#14b8a6",
    badgeBg: "bg-teal-500/10 border-teal-500/20 text-teal-600 dark:text-teal-400",
    botName: "Checking Support Bot",
    features: [
      "Zero monthly maintenance fees or hidden tier thresholds",
      "Complimentary multi-layer overdraft protection integration",
      "Instant digital debit card provisioning for Apple Pay® & Google Wallet™",
      "Free specialized paper check supply for members aged 65 or older"
    ]
  },
  {
    name: "Horizon Apex Premier",
    tag: "High-Yield & Elite Rewards",
    apy: "0.05% APY",
    monthlyFee: "$15",
    feeWaiver: "Waived with $15,000 combined balance + $1,000 monthly direct deposit",
    minOpen: "$0",
    atmAccess: "Unlimited global out-of-network ATM fee reimbursements",
    rewards: "Additional 25% bonus reward multiplier on paired credit cards",
    loanDiscount: "0.25% APR discount on vehicle and home equity lines",
    bestFor: "Members seeking optimized yield, premium loan rates, and full fee waivers",
    cardStyle: "from-slate-950 via-emerald-950 to-teal-950 border-emerald-500/30 text-emerald-400",
    chipStyle: "bg-emerald-400/20 border-emerald-500/40 text-emerald-300",
    accentColor: "#10b981",
    badgeBg: "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400",
    botName: "Premier Wealth Bot",
    features: [
      "0.25% automated discount triggers on select consumer lending products",
      "25% accelerated portfolio reward point accruals credited monthly",
      "$350 dedicated credit towards primary mortgage origination costs",
      "Waived incoming wire transfer fees and expedited card replacement delivery"
    ]
  },
  {
    name: "Vanguard Ascend Teen",
    tag: "Empowered Early Access",
    apy: "0.02% APY",
    monthlyFee: "$0",
    feeWaiver: "No fees ever for active members aged 13-17",
    minOpen: "$0",
    atmAccess: "Access to 30,000+ standard network fee-free machines",
    rewards: "Gamified savings milestones and automated round-up targets",
    loanDiscount: "N/A",
    bestFor: "Ages 13-17 developing strong lifelong budgeting and spending habits",
    cardStyle: "from-indigo-950 via-slate-900 to-purple-950 border-indigo-500/30 text-indigo-400",
    chipStyle: "bg-indigo-400/20 border-indigo-500/40 text-indigo-300",
    accentColor: "#6366f1",
    badgeBg: "bg-indigo-500/10 border-indigo-500/20 text-indigo-600 dark:text-indigo-400",
    botName: "Youth Banking Bot",
    features: [
      "Joint adult security oversight layer requiring parental/guardian sign-off",
      "Real-time instant spending threshold alert notifications via SMS/push",
      "Automated integration with tailored educational micro-literacy chapters",
      "Zero minimum opening deposit to start building a secure future today"
    ]
  },
  {
    name: "Aura Health Reserve",
    tag: "Triple-Tax Advantaged HSA",
    apy: "Tiered Premium APY",
    monthlyFee: "$0",
    feeWaiver: "No maintenance fees when linked to qualifying health plans",
    minOpen: "$0",
    atmAccess: "Direct point-of-sale pharmacy network terminal optimization",
    rewards: "Tax-free principal accumulation and zero-cost investment tier access",
    loanDiscount: "N/A",
    bestFor: "Managing high-deductible out-of-pocket clinical and preventative care expenses",
    cardStyle: "from-cyan-950 via-slate-900 to-sky-950 border-cyan-500/30 text-cyan-400",
    chipStyle: "bg-cyan-400/20 border-cyan-500/40 text-cyan-300",
    accentColor: "#06b6d4",
    badgeBg: "bg-cyan-500/10 border-cyan-500/20 text-cyan-600 dark:text-cyan-400",
    botName: "Health Advisor Bot",
    features: [
      "Contributions, qualified disbursements, and annual interest grow 100% tax-free",
      "Full account ownership portability that carries forward across career transitions",
      "Dedicated separate secure healthcare tracking physical Visa® Debit line",
      "Automated direct deposit splitting to effortlessly build clinical safety reserves"
    ]
  }
];

export const savingsProducts = [
  {
    name: "Premier Savings",
    minDeposit: 0,
    baseApy: 0.02,
    tag: "High-yield tiered savings",
    details: "Earn premium yields on balances over $50,000. Requires $500 monthly direct deposit to checking."
  },
  {
    name: "Traditional Savings",
    minDeposit: 0.01,
    baseApy: 0.02,
    tag: "Establish membership",
    details: "Our standard savings account. Establishes your credit union membership share."
  },
  {
    name: "Mortgage Savings",
    minDeposit: 100,
    baseApy: 0.02,
    tag: "Earn lender credits",
    details: "Save for a home and earn $1 in lender credit toward closing costs for every $5 deposited (up to $1,000)."
  },
  {
    name: "Holiday Club",
    minDeposit: 0,
    baseApy: 0.02,
    tag: "Save for the holidays",
    details: "Stash money away throughout the year. Disbursed annually in October just in time for shopping."
  },
  {
    name: "College Savings",
    minDeposit: 5.00,
    baseApy: 0.02,
    tag: "Youth & Minor savings",
    details: "Start kids and teens on the path to financial literacy. Stated APY with annual anniversary bonuses."
  }
];

export const creditCards = [
  {
    name: "Aura Elite Reserve",
    tag: "Premium Travel & Lifestyle",
    bonus: "75,000 Bonus Points",
    bonusDesc: "After spending $4,000 in the first 3 months",
    earnRate: "3x Points on Travel & Dining",
    introApr: "N/A",
    regApr: "18.99% - 24.99% Variable",
    annualFee: "$0",
    balanceTransferFee: "3%",
    foreignTxFee: "None",
    bestFor: "Frequent travelers seeking uncompromised luxury",
    cardStyle: "from-slate-900 via-slate-800 to-slate-950 border-amber-500/30 text-amber-400",
    chipStyle: "bg-amber-400/20 border-amber-500/40 text-amber-300",
    accentColor: "#f59e0b",
    badgeBg: "bg-amber-500/10 border-amber-500/20 text-amber-500 dark:text-amber-400",
    botName: "Travel Rewards Bot",
    features: [
      "Complimentary global airport lounge access",
      "Annual $200 travel statement credit",
      "Primary rental car collision damage waiver",
      "24/7 elite white-glove concierge service"
    ]
  },
  {
    name: "Velocity Cash Preferred",
    tag: "Maximum Cash Back",
    bonus: "$200 Cash Bonus",
    bonusDesc: "After spending $1,000 in the first 90 days",
    earnRate: "2% Unlimited Flat Cash Back",
    introApr: "0% Intro APR for 12 Months",
    regApr: "16.24% - 22.24% Variable",
    annualFee: "$0",
    balanceTransferFee: "$0 Intro Fee",
    foreignTxFee: "1%",
    bestFor: "Everyday spending with effortless statement credits",
    cardStyle: "from-emerald-900 via-teal-900 to-cyan-950 border-emerald-500/30 text-emerald-400",
    chipStyle: "bg-emerald-400/20 border-emerald-500/40 text-emerald-300",
    accentColor: "#10b981",
    badgeBg: "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400",
    botName: "Cash Back Advisor",
    features: [
      "No rotating categories or earning caps",
      "Instant redemption directly to your checking account",
      "Purchase protection up to $1,000 per claim",
      "Extended warranty coverage on eligible items"
    ]
  },
  {
    name: "Equinox Horizon",
    tag: "Low APR & Balance Transfers",
    bonus: "0% Intro APR",
    bonusDesc: "For 18 months on balance transfers and purchases",
    earnRate: "1x Points on all purchases",
    introApr: "0% Intro APR for 18 Months",
    regApr: "13.99% - 19.99% Variable",
    annualFee: "$0",
    balanceTransferFee: "$0 Intro Fee for 60 days",
    foreignTxFee: "2%",
    bestFor: "Consolidating existing balances and financing large purchases",
    cardStyle: "from-sky-900 via-blue-950 to-slate-900 border-sky-500/30 text-sky-400",
    chipStyle: "bg-sky-400/20 border-sky-500/40 text-sky-300",
    accentColor: "#0ea5e9",
    badgeBg: "bg-sky-500/10 border-sky-500/20 text-sky-600 dark:text-sky-400",
    botName: "Balance Transfer Agent",
    features: [
      "Save on interest with our industry-leading low intro rate",
      "Customizable payment due dates to fit your schedule",
      "Free access to your live updated FICO® Score",
      "Zero liability on unauthorized transactions"
    ]
  },
  {
    name: "Vanguard Builder",
    tag: "Secured Rebuilding",
    bonus: "Instant Decision",
    bonusDesc: "No minimum credit score required to apply",
    earnRate: "1% Cash Back on Gas & Groceries",
    introApr: "N/A",
    regApr: "20.49% Variable",
    annualFee: "$0",
    balanceTransferFee: "N/A",
    foreignTxFee: "3%",
    bestFor: "Establishing or rebuilding a solid credit history safely",
    cardStyle: "from-indigo-950 via-slate-900 to-indigo-900 border-indigo-500/30 text-indigo-400",
    chipStyle: "bg-indigo-400/20 border-indigo-500/40 text-indigo-300",
    accentColor: "#6366f1",
    badgeBg: "bg-indigo-500/10 border-indigo-500/20 text-indigo-600 dark:text-indigo-400",
    botName: "Credit Support Bot",
    features: [
      "Credit limit matches your fully refundable security deposit",
      "Automatic reporting to Equifax, Experian, and TransUnion",
      "Path to unsecured upgrade review in as little as 6 months",
      "Complimentary financial literacy tools and personalized insights"
    ]
  }
];

export const mortgageRates = [
  {
    type: "30-Year Fixed Conforming",
    rate: "6.375%",
    points: "0.000",
    apr: "6.428%",
    tag: "Standard Conforming",
    notesIndex: [1, 2, 3]
  },
  {
    type: "15-Year Fixed Conforming",
    rate: "5.750%",
    points: "0.000",
    apr: "5.835%",
    tag: "Accelerated Principal",
    notesIndex: [1, 2, 3]
  },
  {
    type: "30-Year Fixed Jumbo Tier",
    rate: "6.375%",
    points: "0.000",
    apr: "6.393%",
    tag: "High-Balance Conforming",
    notesIndex: [4, 3]
  },
  {
    type: "15-Year Fixed Jumbo Tier",
    rate: "5.375%",
    points: "0.000",
    apr: "5.403%",
    tag: "Elite High-Balance",
    notesIndex: [4, 3]
  },
  {
    type: "10/6 Adjustable Rate Tier",
    rate: "5.625%",
    points: "0.000",
    apr: "5.941%",
    tag: "Extended Fixed Base",
    notesIndex: [1, 5, 3]
  },
  {
    type: "7/6 Adjustable Rate Tier",
    rate: "5.250%",
    points: "0.000",
    apr: "5.856%",
    tag: "Optimal Medium Hold",
    notesIndex: [1, 5, 3]
  },
  {
    type: "5/6 Adjustable Rate Tier",
    rate: "5.125%",
    points: "0.000",
    apr: "5.938%",
    tag: "Maximum Base Intro",
    notesIndex: [1, 5, 3]
  }
];
