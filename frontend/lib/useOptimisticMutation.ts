// TODO: 将来的に全ミューテーション（PATCH/DELETE/POST）に統合予定。
// 現時点では各コンポーネントが authFetch + onRefresh() パターンで十分に機能している。
// 楽観的更新が必要になった場合（大量ノード操作でのレスポンス改善等）に統合する。
'use client';

import { useCallback, useRef } from 'react';
import { authFetch } from '@/lib/api';

interface MutationOptions<T> {
  onOptimistic?: (data: T) => void;
  onRollback?: (previous: T) => void;
  onSuccess?: (result: unknown) => void;
  onError?: (error: Error) => void;
}

/**
 * 楽観的更新の集中管理フック。
 * 全ミューテーション（PATCH/DELETE/POST）で統一パターンを使用。
 * サーバーエラー時は自動ロールバック + コールバック通知。
 */
export function useOptimisticMutation<T>() {
  const previousRef = useRef<T | null>(null);

  const mutate = useCallback(
    async (
      url: string,
      fetchOptions: RequestInit,
      currentData: T,
      optimisticData: T,
      options: MutationOptions<T> = {}
    ): Promise<boolean> => {
      // スナップショット保存
      previousRef.current = currentData;

      // 楽観的更新を即座に適用
      options.onOptimistic?.(optimisticData);

      try {
        const res = await authFetch(url, {
          ...fetchOptions,
          headers: { 'Content-Type': 'application/json', ...fetchOptions.headers },
        });

        if (!res.ok) {
          const detail = await res.text().catch(() => 'Unknown error');
          throw new Error(detail);
        }

        const result = await res.json().catch(() => ({}));
        options.onSuccess?.(result);
        previousRef.current = null;
        return true;
      } catch (err) {
        // ロールバック
        if (previousRef.current !== null) {
          options.onRollback?.(previousRef.current);
        }
        options.onError?.(err instanceof Error ? err : new Error(String(err)));
        previousRef.current = null;
        return false;
      }
    },
    []
  );

  return { mutate };
}
