'use client';

import { useState, useEffect } from 'react';
import axios from 'axios';
import { format, formatDistanceToNow } from 'date-fns';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://web-production-99709.up.railway.app';

// For demo, using hardcoded business ID - in production, this comes from auth
const BUSINESS_ID = process.env.NEXT_PUBLIC_BUSINESS_ID || '78e2ea0f-f34b-4459-9d5b-6e32d946db13';

interface Stats {
  total: number;
  completed: number;
  failed: number;
  in_progress: number;
  total_duration_seconds: number;
  avg_duration_seconds: number;
}

interface DashboardStats {
  today: Stats;
  this_week: Stats;
  this_month: Stats;
  all_time: Stats;
}

interface Call {
  id: string;
  call_sid: string;
  from_number: string;
  to_number: string;
  status: string;
  duration: number | null;
  created_at: string;
  recording_url?: string;
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '-';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs}s`;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    'completed': 'bg-green-500/20 text-green-400 border-green-500/30',
    'in-progress': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    'failed': 'bg-red-500/20 text-red-400 border-red-500/30',
    'busy': 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    'no-answer': 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  };

  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full border ${colors[status] || colors['failed']}`}>
      {status}
    </span>
  );
}

function StatCard({ title, value, subtitle, icon }: { title: string; value: string | number; subtitle?: string; icon: string }) {
  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-gray-400 text-sm font-medium">{title}</p>
          <p className="text-3xl font-bold text-white mt-1">{value}</p>
          {subtitle && <p className="text-gray-500 text-sm mt-1">{subtitle}</p>}
        </div>
        <div className="text-4xl">{icon}</div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [calls, setCalls] = useState<Call[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const [statsRes, callsRes] = await Promise.all([
          axios.get(`${API_URL}/api/dashboard/stats/${BUSINESS_ID}`),
          axios.get(`${API_URL}/api/dashboard/calls/${BUSINESS_ID}?limit=10`)
        ]);

        if (statsRes.data.success) {
          setStats(statsRes.data);
        }
        if (callsRes.data.success) {
          setCalls(callsRes.data.calls);
        }
      } catch (err) {
        console.error('Error fetching dashboard data:', err);
        setError('Failed to load dashboard data');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
    // Refresh every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-red-400">
        <h3 className="font-bold">Error</h3>
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Dashboard</h1>
        <p className="text-gray-400 mt-1">Monitor your AI phone agent performance</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Calls Today"
          value={stats?.today.total || 0}
          subtitle={`${stats?.today.completed || 0} completed`}
          icon="📞"
        />
        <StatCard
          title="This Week"
          value={stats?.this_week.total || 0}
          subtitle={`${stats?.this_week.completed || 0} completed`}
          icon="📊"
        />
        <StatCard
          title="This Month"
          value={stats?.this_month.total || 0}
          subtitle={`${stats?.this_month.completed || 0} completed`}
          icon="📈"
        />
        <StatCard
          title="Avg Duration"
          value={formatDuration(stats?.this_month.avg_duration_seconds || 0)}
          subtitle="this month"
          icon="⏱️"
        />
      </div>

      {/* Success Rate */}
      {stats && stats.this_month.total > 0 && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <h3 className="text-lg font-semibold text-white mb-4">Success Rate (This Month)</h3>
          <div className="flex items-center gap-4">
            <div className="flex-1 bg-gray-700 rounded-full h-4 overflow-hidden">
              <div
                className="bg-green-500 h-full transition-all duration-500"
                style={{
                  width: `${(stats.this_month.completed / stats.this_month.total) * 100}%`
                }}
              />
            </div>
            <span className="text-white font-bold">
              {Math.round((stats.this_month.completed / stats.this_month.total) * 100)}%
            </span>
          </div>
          <div className="flex justify-between mt-2 text-sm">
            <span className="text-green-400">{stats.this_month.completed} completed</span>
            <span className="text-red-400">{stats.this_month.failed} failed</span>
            <span className="text-yellow-400">{stats.this_month.in_progress} in progress</span>
          </div>
        </div>
      )}

      {/* Recent Calls */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-700 flex justify-between items-center">
          <h3 className="text-lg font-semibold text-white">Recent Calls</h3>
          <a href="/calls" className="text-blue-400 hover:text-blue-300 text-sm font-medium">
            View All →
          </a>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-700/50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Caller
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Duration
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Time
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {calls.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                    No calls yet. Your AI agent is ready to receive calls!
                  </td>
                </tr>
              ) : (
                calls.map((call) => (
                  <tr key={call.id} className="hover:bg-gray-700/30 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-white font-medium">{call.from_number || 'Unknown'}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <StatusBadge status={call.status} />
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-300">
                      {formatDuration(call.duration)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-400 text-sm">
                      {formatDistanceToNow(new Date(call.created_at), { addSuffix: true })}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <a
                        href={`/calls/${call.id}`}
                        className="text-blue-400 hover:text-blue-300 text-sm font-medium"
                      >
                        View Details
                      </a>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
