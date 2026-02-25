'use client';

import { useEffect } from 'react';

const API_PASSWORD = process.env.NEXT_PUBLIC_API_PASSWORD || '';
const API_URL = process.env.NEXT_PUBLIC_API_URL || '';

/**
 * グローバルfetchにBasic認証ヘッダーを自動付与するプロバイダー。
 * APIサーバーへのリクエストにのみ認証ヘッダーを追加する。
 */
export default function AuthProvider({ children }: { children: React.ReactNode }) {
    useEffect(() => {
        if (!API_PASSWORD) return;

        const originalFetch = window.fetch;
        window.fetch = async function (input: RequestInfo | URL, init?: RequestInit) {
            const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;

            // APIサーバーへのリクエストのみ認証ヘッダーを付与
            const isApiRequest = url.includes('/api/') || (API_URL && url.startsWith(API_URL));

            if (isApiRequest) {
                console.log('AuthProvider: Injecting Auth Header', { url });
                const encoded = btoa(`user:${API_PASSWORD}`);
                const headers = new Headers(init?.headers);
                if (!headers.has('Authorization')) {
                    headers.set('Authorization', `Basic ${encoded}`);
                }
                init = { ...init, headers };
            }

            return originalFetch.call(window, input, init);
        };

        return () => {
            // クリーンアップ時に元のfetchを復元
            window.fetch = originalFetch;
        };
    }, []);

    return <>{children}</>;
}
