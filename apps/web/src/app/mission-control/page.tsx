import type { Metadata } from "next";

export const metadata: Metadata = { title: "Mission Control" };

export default function MissionControlPage() {
  return (
    <div className="p-4">
      <h1 className="panel-title">Mission Control</h1>
    </div>
  );
}
