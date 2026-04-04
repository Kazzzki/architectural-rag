'use client';

import { useEffect, useState } from 'react';
import { Link2, FileText, Tag, Loader2, RefreshCw } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface EntityLink {
  id: number;
  entity_type: string;
  entity_id: string;
  mention_text: string;
  confidence: number;
}

interface MeetingTag {
  id: number;
  tag_name: string;
  source: string;
}

interface Props {
  sessionId: number;
}

const TAG_COLORS: Record<string, string> = {
  '設計変更': 'bg-purple-100 text-purple-700',
  'コスト': 'bg-green-100 text-green-700',
  '工程': 'bg-blue-100 text-blue-700',
  '安全': 'bg-red-100 text-red-700',
  '品質': 'bg-amber-100 text-amber-700',
  '法規': 'bg-gray-100 text-gray-700',
  '近隣': 'bg-orange-100 text-orange-700',
  '発注者指示': 'bg-indigo-100 text-indigo-700',
  'VE': 'bg-teal-100 text-teal-700',
  'クレーム': 'bg-rose-100 text-rose-700',
};

export default function EntityLinksPanel({ sessionId }: Props) {
  const [links, setLinks] = useState<EntityLink[]>([]);
  const [tags, setTags] = useState<MeetingTag[]>([]);
  const [loading, setLoading] = useState(true);
  const [extracting, setExtracting] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [linksRes, tagsRes] = await Promise.all([
        authFetch(`/api/meetings/${sessionId}/entity-links`),
        authFetch(`/api/meetings/${sessionId}/tags`),
      ]);
      if (linksRes.ok) setLinks(await linksRes.json());
      if (tagsRes.ok) setTags(await tagsRes.json());
    } catch (e) {
      console.error('Failed to fetch entity data:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [sessionId]);

  const handleReExtract = async () => {
    setExtracting(true);
    try {
      await Promise.all([
        authFetch(`/api/meetings/${sessionId}/extract-links`, { method: 'POST' }),
        authFetch(`/api/meetings/${sessionId}/auto-tag`, { method: 'POST' }),
      ]);
      await fetchData();
    } catch (e) {
      console.error('Failed to re-extract:', e);
    } finally {
      setExtracting(false);
    }
  };

  const issueLinks = links.filter(l => l.entity_type === 'issue');
  const meetingLinks = links.filter(l => l.entity_type === 'meeting');

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <Loader2 className="w-4 h-4 animate-spin" />
          関連情報を読み込み中...
        </div>
      </div>
    );
  }

  const isEmpty = links.length === 0 && tags.length === 0;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <Link2 className="w-4 h-4 text-indigo-500" />
          関連エンティティ
        </h3>
        <button
          onClick={handleReExtract}
          disabled={extracting}
          className="text-xs px-2.5 py-1 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 disabled:opacity-50 flex items-center gap-1 transition-colors"
        >
          {extracting ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          再抽出
        </button>
      </div>

      {isEmpty ? (
        <div className="text-center py-4">
          <p className="text-sm text-gray-400">関連エンティティが見つかりませんでした</p>
          <p className="text-xs text-gray-300 mt-1">「再抽出」で再検出するか、#タグをライブメモで追加できます</p>
        </div>
      ) : (
        <>
          {/* イシューリンク */}
          {issueLinks.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-2">イシュー</p>
              <div className="space-y-1.5">
                {issueLinks.map(link => (
                  <div key={link.id} className="flex items-center gap-2 p-2 rounded-lg bg-gray-50 text-sm">
                    <Link2 className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0" />
                    <span className="font-mono text-xs text-indigo-600">[{link.entity_id}]</span>
                    <span className="text-gray-700 flex-1 truncate">{link.mention_text}</span>
                    <span className="text-xs text-gray-400">{Math.round(link.confidence * 100)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 会議リンク */}
          {meetingLinks.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-2">関連会議</p>
              <div className="space-y-1.5">
                {meetingLinks.map(link => (
                  <div key={link.id} className="flex items-center gap-2 p-2 rounded-lg bg-gray-50 text-sm">
                    <FileText className="w-3.5 h-3.5 text-blue-500 flex-shrink-0" />
                    <span className="text-gray-700 flex-1 truncate">{link.mention_text}</span>
                    <span className="text-xs text-gray-400">{Math.round(link.confidence * 100)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* タグ */}
          {tags.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-2 flex items-center gap-1">
                <Tag className="w-3 h-3" /> タグ
              </p>
              <div className="flex flex-wrap gap-1.5">
                {tags.map(tag => (
                  <span
                    key={tag.id}
                    className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      TAG_COLORS[tag.tag_name] || 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {tag.tag_name}
                    {tag.source === 'manual' && (
                      <span className="ml-1 opacity-60">手動</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
