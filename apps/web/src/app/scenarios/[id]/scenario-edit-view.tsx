"use client";

import Link from "next/link";
import { useMemo } from "react";

import { ScenarioStudio } from "@/components/scenario/studio";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingPanel } from "@/components/ui/feedback";
import { useScenario } from "@/hooks/use-scenarios";
import { safeParseScenarioDocument } from "@/lib/scenario-document";

export function ScenarioEditView({ name }: { name: string }) {
  const query = useScenario(name);
  const draft = useMemo(
    () => safeParseScenarioDocument(query.data?.document),
    [query.data?.document],
  );

  if (query.isError) {
    return (
      <div className="p-4">
        <ErrorState
          title="Scenario not found"
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      </div>
    );
  }
  if (query.isLoading) {
    return <LoadingPanel label="Loading scenario" className="p-4" />;
  }
  if (!draft) {
    return (
      <div className="p-4">
        <EmptyState
          title="This document cannot be opened in the studio"
          description="The stored YAML could not be parsed into the editor form. Open the run that used it to read the document as stored."
          action={
            <Button asChild variant="outline">
              <Link href="/scenarios">Back to the library</Link>
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <ScenarioStudio
      key={name}
      initialDraft={draft}
      editingName={query.data?.name ?? name}
      source={query.data?.source}
    />
  );
}
