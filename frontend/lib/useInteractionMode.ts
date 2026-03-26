// TODO: 将来的に IssueCausalGraph に統合予定。
// 現時点では page.tsx の selectedNodeIds state で十分に機能している。
// モード管理が複雑化した場合（エッジ作成モード、インライン編集モードの状態遷移が増えた場合）に統合する。
'use client';

import { useReducer, useCallback } from 'react';

export type InteractionMode = 'normal' | 'multi_select' | 'edge_creation' | 'inline_edit';

interface InteractionState {
  mode: InteractionMode;
  edgeSourceId: string | null; // edge_creation モードのソースノードID
  editingNodeId: string | null; // inline_edit モードの対象ノードID
  selectedNodeIds: Set<string>; // multi_select モードの選択ノード
}

type InteractionAction =
  | { type: 'START_MULTI_SELECT'; nodeId: string }
  | { type: 'TOGGLE_SELECT'; nodeId: string }
  | { type: 'SET_SELECTION'; nodeIds: string[] }
  | { type: 'CLEAR_SELECTION' }
  | { type: 'START_EDGE_CREATION'; sourceId: string }
  | { type: 'START_INLINE_EDIT'; nodeId: string }
  | { type: 'FINISH_INLINE_EDIT' }
  | { type: 'CANCEL' }
  | { type: 'RESET' };

const initialState: InteractionState = {
  mode: 'normal',
  edgeSourceId: null,
  editingNodeId: null,
  selectedNodeIds: new Set(),
};

function reducer(state: InteractionState, action: InteractionAction): InteractionState {
  switch (action.type) {
    case 'START_MULTI_SELECT': {
      const next = new Set(state.selectedNodeIds);
      next.add(action.nodeId);
      return { ...state, mode: 'multi_select', selectedNodeIds: next, edgeSourceId: null, editingNodeId: null };
    }
    case 'TOGGLE_SELECT': {
      const next = new Set(state.selectedNodeIds);
      if (next.has(action.nodeId)) {
        next.delete(action.nodeId);
      } else {
        next.add(action.nodeId);
      }
      return {
        ...state,
        mode: next.size > 0 ? 'multi_select' : 'normal',
        selectedNodeIds: next,
      };
    }
    case 'SET_SELECTION': {
      const next = new Set(action.nodeIds);
      return {
        ...state,
        mode: next.size > 0 ? 'multi_select' : 'normal',
        selectedNodeIds: next,
      };
    }
    case 'CLEAR_SELECTION':
      return { ...initialState };
    case 'START_EDGE_CREATION':
      return { ...initialState, mode: 'edge_creation', edgeSourceId: action.sourceId };
    case 'START_INLINE_EDIT':
      return { ...initialState, mode: 'inline_edit', editingNodeId: action.nodeId };
    case 'FINISH_INLINE_EDIT':
      return { ...initialState };
    case 'CANCEL':
    case 'RESET':
      return { ...initialState };
    default:
      return state;
  }
}

export function useInteractionMode() {
  const [state, dispatch] = useReducer(reducer, initialState);

  const startMultiSelect = useCallback((nodeId: string) => dispatch({ type: 'START_MULTI_SELECT', nodeId }), []);
  const toggleSelect = useCallback((nodeId: string) => dispatch({ type: 'TOGGLE_SELECT', nodeId }), []);
  const setSelection = useCallback((nodeIds: string[]) => dispatch({ type: 'SET_SELECTION', nodeIds }), []);
  const clearSelection = useCallback(() => dispatch({ type: 'CLEAR_SELECTION' }), []);
  const startEdgeCreation = useCallback((sourceId: string) => dispatch({ type: 'START_EDGE_CREATION', sourceId }), []);
  const startInlineEdit = useCallback((nodeId: string) => dispatch({ type: 'START_INLINE_EDIT', nodeId }), []);
  const finishInlineEdit = useCallback(() => dispatch({ type: 'FINISH_INLINE_EDIT' }), []);
  const cancel = useCallback(() => dispatch({ type: 'CANCEL' }), []);

  return {
    ...state,
    startMultiSelect,
    toggleSelect,
    setSelection,
    clearSelection,
    startEdgeCreation,
    startInlineEdit,
    finishInlineEdit,
    cancel,
  };
}
