"use client";
import { create } from "zustand";
import { InvestigationSummary, InvestigationState } from "@/types/investigation";

interface UIState {
  recent: InvestigationSummary[];
  setRecent: (r: InvestigationSummary[]) => void;
  addRecent: (r: InvestigationSummary) => void;

  selectedId: string | null;
  setSelectedId: (id: string | null) => void;

  cachedState: Record<string, InvestigationState>;
  setCachedState: (id: string, s: InvestigationState) => void;

  // Trigger a demo investigation when backend is unreachable so the UI is
  // always demonstrable. Backend integration always takes priority.
  demoMode: boolean;
  setDemoMode: (b: boolean) => void;
}

export const useUI = create<UIState>((set) => ({
  recent: [],
  setRecent: (r) => set({ recent: r }),
  addRecent: (r) =>
    set((s) => ({ recent: [r, ...s.recent.filter((x) => x.investigation_id !== r.investigation_id)].slice(0, 50) })),
  selectedId: null,
  setSelectedId: (id) => set({ selectedId: id }),
  cachedState: {},
  setCachedState: (id, st) => set((s) => ({ cachedState: { ...s.cachedState, [id]: st } })),
  demoMode: true,
  setDemoMode: (b) => set({ demoMode: b })
}));