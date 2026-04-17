import { useState, useEffect } from "react";

export function useElapsed(startIso: string | null, intervalMs = 10_000): number {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!startIso) return;
    const startMs = new Date(startIso).getTime();

    const tick = () => setElapsed(Date.now() - startMs);
    tick();
    const interval = setInterval(tick, intervalMs);
    return () => clearInterval(interval);
  }, [startIso, intervalMs]);

  return elapsed;
}
