export interface TemplateField {
  id: string;
  label: string;
  options: string[];
}

export interface IssueTemplate {
  id: string;
  label: string;
  fields: TemplateField[];
  defaultPriority: 'critical' | 'normal' | 'minor';
  defaultCategory: '工程' | 'コスト' | '品質' | '安全';
}

export const ISSUE_TEMPLATES: IssueTemplate[] = [
  {
    id: 'schedule_delay',
    label: '工程遅延',
    fields: [
      { id: 'category', label: '工種', options: ['舗装', '躯体', '設備', '土工', 'その他'] },
      { id: 'delay_days', label: '遅延日数', options: ['1〜3日', '1週間', '2週間以上'] },
      { id: 'cause', label: '原因', options: ['天候', '資材不足', '人員不足', '設計変更', 'その他'] },
    ],
    defaultPriority: 'normal',
    defaultCategory: '工程',
  },
  {
    id: 'cost_increase',
    label: 'コスト増加',
    fields: [
      { id: 'item', label: '項目', options: ['材料費', '労務費', '機械費', 'その他'] },
      { id: 'rate', label: '増加率', options: ['5%未満', '5〜15%', '15%以上'] },
      { id: 'cause', label: '原因', options: ['市況変動', '数量増加', '設計変更', 'その他'] },
    ],
    defaultPriority: 'critical',
    defaultCategory: 'コスト',
  },
  {
    id: 'quality_issue',
    label: '品質指摘',
    fields: [
      { id: 'category', label: '工種', options: ['躯体', '仕上', '設備', 'その他'] },
      { id: 'inspector', label: '指摘元', options: ['社内検査', '発注者', '第三者機関'] },
      { id: 'deadline', label: '是正期限', options: ['即日', '3日以内', '1週間以内'] },
    ],
    defaultPriority: 'normal',
    defaultCategory: '品質',
  },
  {
    id: 'safety_event',
    label: '安全事象',
    fields: [
      { id: 'type', label: '種別', options: ['ヒヤリハット', '軽微な事故', '重大事象'] },
      { id: 'severity', label: '重篤度', options: ['軽微', '中程度', '重大'] },
      { id: 'location', label: '発生場所', options: ['地上', '高所', '地下', '重機周辺', 'その他'] },
    ],
    defaultPriority: 'critical',
    defaultCategory: '安全',
  },
  {
    id: 'design_change',
    label: '設計変更',
    fields: [
      { id: 'area', label: '変更箇所', options: ['構造', '意匠', '設備', '外構', 'その他'] },
      { id: 'impact', label: '影響範囲', options: ['軽微', '工程影響あり', 'コスト影響あり', '両方'] },
      { id: 'requester', label: '起案者', options: ['発注者', '設計者', '施工者'] },
    ],
    defaultPriority: 'normal',
    defaultCategory: '工程',
  },
  {
    id: 'client_response',
    label: '発注者対応',
    fields: [
      { id: 'type', label: '対応種別', options: ['報告', '承認取得', 'クレーム対応', '協議'] },
      { id: 'deadline', label: '期限', options: ['本日中', '今週中', '来週中'] },
      { id: 'assignee', label: '担当者', options: ['自分', '上司', 'チーム'] },
    ],
    defaultPriority: 'normal',
    defaultCategory: '工程',
  },
];

/**
 * テンプレートの選択内容を自然文に変換する
 */
export function templateSelectionsToText(
  template: IssueTemplate,
  selections: Record<string, string>
): string {
  const id = template.id;
  const s = selections;

  switch (id) {
    case 'schedule_delay':
      return `${s.category ?? ''}工事が${s.cause ?? ''}の影響で${s.delay_days ?? ''}遅延している`;
    case 'cost_increase':
      return `${s.item ?? ''}が${s.cause ?? ''}により${s.rate ?? ''}増加している`;
    case 'quality_issue':
      return `${s.category ?? ''}の品質について${s.inspector ?? ''}から指摘を受けた。是正期限: ${s.deadline ?? ''}`;
    case 'safety_event':
      return `${s.location ?? ''}で${s.type ?? ''}が発生した（重篤度: ${s.severity ?? ''}）`;
    case 'design_change':
      return `${s.requester ?? ''}より${s.area ?? ''}の設計変更が発生。影響範囲: ${s.impact ?? ''}`;
    case 'client_response':
      return `発注者への${s.type ?? ''}対応が必要。期限: ${s.deadline ?? ''}、担当: ${s.assignee ?? ''}`;
    default: {
      const parts = template.fields.map((f) => `${f.label}: ${s[f.id] ?? '未選択'}`);
      return parts.join(' / ');
    }
  }
}
