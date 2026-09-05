"use client";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

export default function ShapChart({ data }: { data: { feature: string; contribution: number }[] }) {
  const sorted = [...(data || [])].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)).slice(0, 8);
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={sorted} layout="vertical" margin={{ left: 20, right: 30 }}>
          <XAxis type="number" stroke="#93a0c8" fontSize={11} />
          <YAxis type="category" dataKey="feature" stroke="#93a0c8" fontSize={11} width={170} />
          <Tooltip contentStyle={{ background: "#0e1430", border: "1px solid #1f2750", borderRadius: 8 }} />
          <Bar dataKey="contribution" radius={[0, 6, 6, 0]}>
            {sorted.map((d, i) => (
              <Cell key={i} fill={d.contribution >= 0 ? "#ff5c7c" : "#5aa8ff"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}