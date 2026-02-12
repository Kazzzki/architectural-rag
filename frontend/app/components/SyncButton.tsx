"use client";

import { useState } from 'react';

interface SyncButtonProps {
    onSyncComplete?: (result: any) => void;
}

const SyncButton = ({ onSyncComplete }: SyncButtonProps) => {
    const [syncing, setSyncing] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const [status, setStatus] = useState<'success' | 'error' | null>(null);

    const handleSync = async () => {
        setSyncing(true);
        setMessage('Google Driveに同期中...');
        setStatus(null);

        try {
            const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const res = await fetch(`${API_BASE}/api/sync-drive`, {
                method: 'POST',
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Sync failed');
            }

            const data = await res.json();
            setStatus('success');
            const uploadedCount = data.uploaded_count || 0;
            setMessage(`同期完了！${uploadedCount}件のファイルをアップロードしました。`);

            if (onSyncComplete) {
                onSyncComplete(data);
            }
        } catch (error: any) {
            console.error('Sync Error:', error);
            setStatus('error');
            setMessage(`同期失敗: ${error.message}`);
        } finally {
            setSyncing(false);
        }
    };

    return (
        <div className="flex flex-col items-start gap-2">
            <button
                onClick={handleSync}
                disabled={syncing}
                className={`px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 ${syncing
                        ? 'bg-gray-400 cursor-not-allowed'
                        : 'bg-blue-600 hover:bg-blue-700 text-white'
                    }`}
            >
                {syncing && (
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                )}
                {syncing ? '同期中...' : 'Google Driveに同期'}
            </button>

            {message && (
                <div className={`text-sm px-3 py-1 rounded ${status === 'success' ? 'bg-green-100 text-green-700' :
                        status === 'error' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
                    }`}>
                    {message}
                </div>
            )}
        </div>
    );
};

export default SyncButton;
