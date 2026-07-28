'use client'

import { useState } from 'react'
import OverviewTab from './OverviewTab'
import UsersTab from './UsersTab'
import BacktestsTab from './BacktestsTab'
import VirtualAccountsTab from './VirtualAccountsTab'
import StrategiesTab from './StrategiesTab'
import PlansTab from './PlansTab'
import KnowledgeTab from './KnowledgeTab'
import AgentsTab from './AgentsTab'
import AuditLogsTab from './AuditLogsTab'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'users', label: 'Users' },
  { id: 'backtests', label: 'Backtests' },
  { id: 'accounts', label: 'Virtual Accounts' },
  { id: 'strategies', label: 'Strategies' },
  { id: 'plans', label: 'Plans' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'agents', label: 'Agents' },
  { id: 'audit', label: 'Audit Logs' },
] as const

type TabId = (typeof TABS)[number]['id']

export default function AdminConsole({ adminEmail }: { adminEmail: string }) {
  const [tab, setTab] = useState<TabId>('overview')

  return (
    <div
      className="min-h-screen bg-[#0f0f0f] text-white"
      style={{ paddingTop: 'var(--top-menu-bar-height, 76px)' }}
    >
      <div className="mx-auto flex w-full max-w-[1400px] gap-6 px-5 py-6 sm:px-8">
        {/* Sidebar */}
        <aside className="w-48 shrink-0">
          <h1 className="px-3 text-lg font-black tracking-tight">운영 콘솔</h1>
          <p className="mb-5 truncate px-3 text-xs font-bold text-gray-600">{adminEmail}</p>
          <nav className="flex flex-col gap-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`rounded-lg px-3 py-2 text-left text-sm font-bold transition-colors ${
                  tab === t.id
                    ? 'bg-white/10 text-white'
                    : 'text-gray-500 hover:bg-white/5 hover:text-gray-300'
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </aside>

        {/* Content — 선택된 탭만 렌더링 */}
        <main className="min-w-0 flex-1">
          {tab === 'overview' && <OverviewTab />}
          {tab === 'users' && <UsersTab />}
          {tab === 'backtests' && <BacktestsTab />}
          {tab === 'accounts' && <VirtualAccountsTab />}
          {tab === 'strategies' && <StrategiesTab />}
          {tab === 'plans' && <PlansTab />}
          {tab === 'knowledge' && <KnowledgeTab />}
          {tab === 'agents' && <AgentsTab />}
          {tab === 'audit' && <AuditLogsTab />}
        </main>
      </div>
    </div>
  )
}
