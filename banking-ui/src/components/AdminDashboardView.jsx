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
import { useNavigate } from 'react-router-dom';
import { FileCheck, MessageSquare, Shield, ChevronRight, LayoutDashboard } from 'lucide-react';

function AdminDashboardView() {
  const navigate = useNavigate();

  const adminModules = [
    {
      title: "Underwriting Portal",
      description: "Verify low-confidence W-2 / paystub extractions, execute structural income verification checklists, and audit borrower exceptions.",
      path: "/admin/underwriting",
      icon: FileCheck,
      color: "from-emerald-500 to-teal-600"
    },
    {
      title: "Admin Secure Messaging",
      description: "Remediate customer security threads, respond to loan officer/borrower secure messaging, and audit thread trace histories.",
      path: "/admin/messaging",
      icon: MessageSquare,
      color: "from-blue-500 to-indigo-600"
    }
  ];

  return (
    <section className="relative pt-32 pb-24 md:pt-44 md:pb-32 px-6 max-w-6xl mx-auto min-h-[calc(100vh-80px)] flex flex-col text-left">
      
      {/* Dynamic background glow */}
      <div className="absolute top-1/4 left-1/3 w-[400px] h-[400px] rounded-full bg-emerald-500/5 blur-[100px] pointer-events-none -z-10" />

      {/* Portal Header */}
      <div className="mb-12 pb-6 border-b border-slate-200 dark:border-slate-800 flex items-center gap-3">
        <div className="p-3 rounded-2xl bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 shadow-sm">
          <LayoutDashboard className="w-6 h-6" />
        </div>
        <div>
          <h1 className="text-3xl font-extrabold bg-gradient-to-r from-slate-900 via-slate-700 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
            Nova Horizon Admin Portal
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Secure, role-gated management dashboard for employee operations, underwriting, and support audits.
          </p>
        </div>
      </div>

      {/* Module Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {adminModules.map((mod) => {
          const IconComponent = mod.icon;
          return (
            <div 
              key={mod.title}
              onClick={() => navigate(mod.path)}
              className="group relative bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800/80 rounded-3xl p-6 cursor-pointer transition-all hover:-translate-y-1 hover:shadow-lg hover:border-slate-300 dark:hover:border-slate-700 flex flex-col justify-between min-h-[220px]"
            >
              <div className="space-y-4">
                {/* Top row: Icon & Title */}
                <div className="flex items-center justify-between">
                  <div className={`w-12 h-12 rounded-2xl bg-gradient-to-br ${mod.color} text-slate-950 flex items-center justify-center shadow-md group-hover:scale-105 transition-all`}>
                    <IconComponent className="w-6 h-6" />
                  </div>
                  <Shield className="w-4 h-4 text-slate-300 dark:text-slate-700" />
                </div>
                
                {/* Text Content */}
                <div className="space-y-2">
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white group-hover:text-emerald-500 dark:group-hover:text-emerald-400 transition-all">
                    {mod.title}
                  </h3>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    {mod.description}
                  </p>
                </div>
              </div>

              {/* Bottom Action link */}
              <div className="pt-4 border-t border-slate-100 dark:border-slate-850 flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-400 group-hover:text-emerald-500 transition-all">
                <span>Launch Module</span>
                <ChevronRight className="w-4 h-4 transform group-hover:translate-x-1 transition-all" />
              </div>
            </div>
          );
        })}
      </div>

    </section>
  );
}

export default AdminDashboardView;
