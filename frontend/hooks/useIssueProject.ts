'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/api';
import { Issue, IssueEdge, CaptureResponse, IssuesListResponse } from '@/lib/issue_types';

export function useIssueProject(projectName: string, categoryFilter: string = '') {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [edges, setEdges] = useState<IssueEdge[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchIssues = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ project_name: projectName });
      if (categoryFilter) params.set('category', categoryFilter);
      const res = await authFetch(`/api/issues?${params.toString()}`);
      if (!res.ok) return;
      const data: IssuesListResponse = await res.json();
      setIssues(data.issues);
      setEdges(data.edges);
    } finally {
      setLoading(false);
    }
  }, [projectName, categoryFilter]);

  useEffect(() => {
    fetchIssues();
  }, [fetchIssues]);

  const handleIssueAdded = useCallback((resp: CaptureResponse) => {
    if (resp.issue) {
      setIssues((prev) =>
        prev.find((iss) => iss.id === resp.issue.id) ? prev : [...prev, resp.issue]
      );
    }
    fetchIssues();
  }, [fetchIssues]);

  const handleIssueUpdated = useCallback((updated: Issue) => {
    setIssues((prev) => prev.map((iss) => (iss.id === updated.id ? updated : iss)));
  }, []);

  const handleIssueDeleted = useCallback((issueId: string) => {
    setIssues((prev) => prev.filter((iss) => iss.id !== issueId));
    fetchIssues();
  }, [fetchIssues]);

  return {
    issues,
    edges,
    loading,
    fetchIssues,
    handleIssueAdded,
    handleIssueUpdated,
    handleIssueDeleted,
  };
}
