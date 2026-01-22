'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import axios from 'axios';
import { format } from 'date-fns';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://web-production-99709.up.railway.app';

interface TranscriptEntry {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

interface CallDetail {
  id: string;
  call_sid: string;
  from_number: string;
  to_number: string;
  status: string;
  duration: number | null;
  created_at: string;
  ended_at?: string;
  recording_url?: string;
  transcript?: TranscriptEntry[];
  summary?: string;
  sentiment?: string;
  intent?: string;
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
    <span className={`px-3 py-1 text-sm font-medium rounded-full border ${colors[status] || colors['failed']}`}>
      {status}
    </span>
  );
}

function SentimentBadge({ sentiment }: { sentiment: string }) {
  const colors: Record<string, string> = {
    'positive': 'bg-green-500/20 text-green-400',
    'neutral': 'bg-gray-500/20 text-gray-400',
    'negative': 'bg-red-500/20 text-red-400',
  };

  return (
    <span className={`px-3 py-1 text-sm font-medium rounded-full ${colors[sentiment] || colors['neutral']}`}>
      {sentiment}
    </span>
  );
}

export default function CallDetailPage() {
  const params = useParams();
  const callId = params.id as string;

  const [call, setCall] = useState<CallDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchCallDetail() {
      try {
        setLoading(true);
        const res = await axios.get(`${API_URL}/api/dashboard/call/${callId}`);

        if (res.data.success) {
          setCall(res.data.call);
        } else {
          setError('Call not found');
        }
      } catch (err) {
        console.error('Error fetching call detail:', err);
        setError('Failed to load call details');
      } finally {
        setLoading(false);
      }
    }

    if (callId) {
      fetchCallDetail();
    }
  }, [callId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error || !call) {
    return (
      <div className="space-y-6">
        <a href="/calls" className="text-blue-400 hover:text-blue-300 text-sm font-medium">
          ← Back to Calls
        </a>
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-red-400">
          <h3 className="font-bold">Error</h3>
          <p>{error || 'Call not found'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back Link */}
      <a href="/calls" className="text-blue-400 hover:text-blue-300 text-sm font-medium inline-flex items-center">
        ← Back to Calls
      </a>

      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold text-white">Call Details</h1>
          <p className="text-gray-400 mt-1">
            {format(new Date(call.created_at), 'MMMM d, yyyy at h:mm a')}
          </p>
        </div>
        <StatusBadge status={call.status} />
      </div>

      {/* Call Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <p className="text-gray-400 text-sm font-medium">From</p>
          <p className="text-xl font-bold text-white mt-1">{call.from_number || 'Unknown'}</p>
        </div>
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <p className="text-gray-400 text-sm font-medium">To</p>
          <p className="text-xl font-bold text-white mt-1">{call.to_number}</p>
        </div>
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <p className="text-gray-400 text-sm font-medium">Duration</p>
          <p className="text-xl font-bold text-white mt-1">{formatDuration(call.duration)}</p>
        </div>
      </div>

      {/* Recording */}
      {call.recording_url && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <h3 className="text-lg font-semibold text-white mb-4">Recording</h3>
          <audio controls className="w-full" src={call.recording_url}>
            Your browser does not support the audio element.
          </audio>
        </div>
      )}

      {/* Summary & Sentiment */}
      {(call.summary || call.sentiment || call.intent) && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <h3 className="text-lg font-semibold text-white mb-4">Call Analysis</h3>
          <div className="space-y-4">
            {call.sentiment && (
              <div className="flex items-center gap-3">
                <span className="text-gray-400">Sentiment:</span>
                <SentimentBadge sentiment={call.sentiment} />
              </div>
            )}
            {call.intent && (
              <div>
                <span className="text-gray-400">Intent:</span>
                <span className="text-white ml-2">{call.intent}</span>
              </div>
            )}
            {call.summary && (
              <div>
                <p className="text-gray-400 mb-2">Summary:</p>
                <p className="text-gray-200 bg-gray-700/50 rounded-lg p-4">{call.summary}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Transcript */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-700">
          <h3 className="text-lg font-semibold text-white">Conversation Transcript</h3>
        </div>
        <div className="p-6">
          {call.transcript && call.transcript.length > 0 ? (
            <div className="space-y-4">
              {call.transcript.map((entry, index) => (
                <div
                  key={index}
                  className={`flex ${entry.role === 'assistant' ? 'justify-start' : 'justify-end'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                      entry.role === 'assistant'
                        ? 'bg-gray-700 text-gray-200'
                        : 'bg-blue-600 text-white'
                    }`}
                  >
                    <div className="text-xs opacity-70 mb-1">
                      {entry.role === 'assistant' ? 'AI Agent' : 'Caller'}
                      {entry.timestamp && ` • ${entry.timestamp}`}
                    </div>
                    <p>{entry.content}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center text-gray-500 py-8">
              <div className="text-4xl mb-4">💬</div>
              <p>No transcript available for this call</p>
            </div>
          )}
        </div>
      </div>

      {/* Technical Details */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h3 className="text-lg font-semibold text-white mb-4">Technical Details</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-400">Call ID:</span>
            <span className="text-gray-200 ml-2 font-mono">{call.id}</span>
          </div>
          <div>
            <span className="text-gray-400">Call SID:</span>
            <span className="text-gray-200 ml-2 font-mono text-xs">{call.call_sid}</span>
          </div>
          <div>
            <span className="text-gray-400">Started:</span>
            <span className="text-gray-200 ml-2">{format(new Date(call.created_at), 'PPpp')}</span>
          </div>
          {call.ended_at && (
            <div>
              <span className="text-gray-400">Ended:</span>
              <span className="text-gray-200 ml-2">{format(new Date(call.ended_at), 'PPpp')}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
