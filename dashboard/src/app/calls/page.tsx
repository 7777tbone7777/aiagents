'use client';

import { useState, useEffect } from 'react';
import axios from 'axios';
import { format, formatDistanceToNow } from 'date-fns';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://web-production-99709.up.railway.app';
const BUSINESS_ID = process.env.NEXT_PUBLIC_BUSINESS_ID || '78e2ea0f-f34b-4459-9d5b-6e32d946db13';

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

export default function CallsPage() {
  const [calls, setCalls] = useState<Call[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalCalls, setTotalCalls] = useState(0);
  const [page, setPage] = useState(0);
  const limit = 20;

  useEffect(() => {
    async function fetchCalls() {
      try {
        setLoading(true);
        const res = await axios.get(
          `${API_URL}/api/dashboard/calls/${BUSINESS_ID}?limit=${limit}&offset=${page * limit}`
        );

        if (res.data.success) {
          setCalls(res.data.calls);
          setTotalCalls(res.data.total);
        }
      } catch (err) {
        console.error('Error fetching calls:', err);
        setError('Failed to load calls');
      } finally {
        setLoading(false);
      }
    }

    fetchCalls();
  }, [page]);

  const totalPages = Math.ceil(totalCalls / limit);

  if (loading && calls.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-white">Call History</h1>
          <p className="text-gray-400 mt-1">{totalCalls} total calls</p>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Calls Table */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
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
                  Date/Time
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {calls.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-gray-500">
                    <div className="text-4xl mb-4">📞</div>
                    <p className="text-lg">No calls yet</p>
                    <p className="text-sm mt-2">Your AI agent is ready to receive calls!</p>
                  </td>
                </tr>
              ) : (
                calls.map((call) => (
                  <tr key={call.id} className="hover:bg-gray-700/30 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-white font-medium">{call.from_number || 'Unknown'}</div>
                      <div className="text-gray-500 text-sm">to {call.to_number}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <StatusBadge status={call.status} />
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-300">
                      {formatDuration(call.duration)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-gray-300">
                        {format(new Date(call.created_at), 'MMM d, yyyy')}
                      </div>
                      <div className="text-gray-500 text-sm">
                        {format(new Date(call.created_at), 'h:mm a')}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <a
                        href={`/calls/${call.id}`}
                        className="text-blue-400 hover:text-blue-300 text-sm font-medium mr-4"
                      >
                        View Transcript
                      </a>
                      {call.recording_url && (
                        <a
                          href={call.recording_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-green-400 hover:text-green-300 text-sm font-medium"
                        >
                          Play Recording
                        </a>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-6 py-4 border-t border-gray-700 flex items-center justify-between">
            <div className="text-sm text-gray-400">
              Showing {page * limit + 1} to {Math.min((page + 1) * limit, totalCalls)} of {totalCalls} calls
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-600 transition-colors"
              >
                Previous
              </button>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-600 transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
