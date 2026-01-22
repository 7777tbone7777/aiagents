'use client';

import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://web-production-99709.up.railway.app';
const BUSINESS_ID = process.env.NEXT_PUBLIC_BUSINESS_ID || '78e2ea0f-f34b-4459-9d5b-6e32d946db13';

interface BusinessSettings {
  id: string;
  name: string;
  phone_number: string;
  timezone: string;
  system_prompt?: string;
  voice_id?: string;
  created_at: string;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<BusinessSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchSettings() {
      try {
        setLoading(true);
        const res = await axios.get(`${API_URL}/api/dashboard/business/${BUSINESS_ID}`);

        if (res.data.success) {
          setSettings(res.data.business);
        }
      } catch (err) {
        console.error('Error fetching settings:', err);
        setError('Failed to load settings');
      } finally {
        setLoading(false);
      }
    }

    fetchSettings();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Settings</h1>
        <p className="text-gray-400 mt-1">View your AI agent configuration</p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
        </div>
      )}

      {settings && (
        <>
          {/* Business Info */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h3 className="text-lg font-semibold text-white mb-4">Business Information</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Business Name
                </label>
                <div className="text-white text-lg">{settings.name}</div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Phone Number
                </label>
                <div className="text-white text-lg">{settings.phone_number}</div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Timezone
                </label>
                <div className="text-white">{settings.timezone}</div>
              </div>
            </div>
          </div>

          {/* AI Agent Config */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h3 className="text-lg font-semibold text-white mb-4">AI Agent Configuration</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Voice
                </label>
                <div className="text-white">{settings.voice_id || 'Default'}</div>
              </div>
              {settings.system_prompt && (
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1">
                    System Prompt
                  </label>
                  <div className="bg-gray-700/50 rounded-lg p-4 text-gray-200 text-sm whitespace-pre-wrap max-h-64 overflow-y-auto">
                    {settings.system_prompt}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Account Details */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h3 className="text-lg font-semibold text-white mb-4">Account Details</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Business ID
                </label>
                <div className="text-gray-300 font-mono text-sm">{settings.id}</div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Account Created
                </label>
                <div className="text-gray-300">
                  {new Date(settings.created_at).toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                  })}
                </div>
              </div>
            </div>
          </div>

          {/* Support */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h3 className="text-lg font-semibold text-white mb-4">Need Help?</h3>
            <p className="text-gray-400 mb-4">
              Contact our support team for assistance with your AI agent configuration.
            </p>
            <a
              href="mailto:support@bolt-ai.com"
              className="inline-flex items-center px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
            >
              Contact Support
            </a>
          </div>
        </>
      )}

      {!settings && !error && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 text-center">
          <div className="text-4xl mb-4">⚙️</div>
          <p className="text-gray-400">No settings available</p>
        </div>
      )}
    </div>
  );
}
