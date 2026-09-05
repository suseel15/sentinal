"use client";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const supabaseConfigured = Boolean(url && key);

let cached: any = null;

export async function getSupabase() {
  if (!supabaseConfigured) return null;
  if (cached) return cached;
  const { createClient } = await import("@supabase/supabase-js");
  cached = createClient(url as string, key as string);
  return cached;
}