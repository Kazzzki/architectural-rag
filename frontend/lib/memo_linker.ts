/**
 * メモ内の #issue-{short_id} と @member 記法をパースし、
 * クリッカブルなセグメントに分割する。
 */

export interface TextSegment {
  type: 'text' | 'issue_link' | 'member_link';
  content: string;
  /** issue_link の場合: UUID先頭8文字 */
  shortId?: string;
  /** member_link の場合: メンバー名 */
  memberName?: string;
}

const LINK_REGEX = /(#issue-([a-f0-9]{8}))|(@([\w\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]+))/g;

/**
 * テキストをパースしてセグメント配列を返す。
 * コードブロック内（`...`）のリンクは無視する。
 */
export function parseLinkedText(text: string): TextSegment[] {
  if (!text) return [{ type: 'text', content: '' }];

  const segments: TextSegment[] = [];
  let lastIndex = 0;

  // コードブロック内のリンクを除外するため、先にコードブロックの範囲を特定
  const codeRanges: [number, number][] = [];
  const codeRegex = /`[^`]+`/g;
  let codeMatch;
  while ((codeMatch = codeRegex.exec(text)) !== null) {
    codeRanges.push([codeMatch.index, codeMatch.index + codeMatch[0].length]);
  }

  const isInCodeBlock = (pos: number) =>
    codeRanges.some(([start, end]) => pos >= start && pos < end);

  let match;
  LINK_REGEX.lastIndex = 0;
  while ((match = LINK_REGEX.exec(text)) !== null) {
    if (isInCodeBlock(match.index)) continue;

    // マッチ前のテキスト
    if (match.index > lastIndex) {
      segments.push({ type: 'text', content: text.slice(lastIndex, match.index) });
    }

    if (match[1]) {
      // #issue-{shortId}
      segments.push({ type: 'issue_link', content: match[0], shortId: match[2] });
    } else if (match[3]) {
      // @member
      segments.push({ type: 'member_link', content: match[0], memberName: match[4] });
    }

    lastIndex = match.index + match[0].length;
  }

  // 残りのテキスト
  if (lastIndex < text.length) {
    segments.push({ type: 'text', content: text.slice(lastIndex) });
  }

  return segments.length > 0 ? segments : [{ type: 'text', content: text }];
}

/**
 * issue_id のフルUUIDから先頭8文字のshort IDを生成
 */
export function toShortId(fullId: string): string {
  return fullId.slice(0, 8);
}

/**
 * short ID からフルIDを検索
 */
export function resolveShortId(shortId: string, issues: { id: string }[]): string | null {
  const found = issues.find((iss) => iss.id.startsWith(shortId));
  return found?.id ?? null;
}
