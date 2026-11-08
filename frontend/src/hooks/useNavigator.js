import { useEffect, useMemo, useRef, useState } from "react";
import { haversine, projectOnPath } from "@/lib/geo";

const ARRIVE_M = 25;
const OFF_CONFIRM = 2;

export function useNavigator(legPath, leg, fix) {
  const [state, setState] = useState(null);
  const hint = useRef(0);
  const off = useRef(0);
  const lastAlong = useRef(0);

  const stepStarts = useMemo(() => {
    if (!leg || !legPath) return [];
    const sum = leg.steps.reduce((a, s) => a + s.distance_m, 0) || 1;
    const k = legPath.total / sum;
    let acc = 0;
    return leg.steps.map((s) => {
      const v = acc;
      acc += s.distance_m * k;
      return v;
    });
  }, [leg, legPath]);

  useEffect(() => {
    hint.current = 0;
    off.current = 0;
    lastAlong.current = 0;
    setState(null);
  }, [legPath]);

  useEffect(() => {
    if (!legPath || !leg || !fix) return;
    const pr = projectOnPath(legPath, fix, hint.current);
    if (!pr) return;
    const tol = Math.max(28, Math.min(fix.accuracy || 0, 50) * 1.2);
    const onRoute = pr.offset <= tol;
    if (onRoute) {
      hint.current = pr.seg;
      off.current = 0;
      lastAlong.current = pr.along;
    } else off.current += 1;
    const along = lastAlong.current;
    const remaining = Math.max(0, legPath.total - along);
    let idx = 0;
    for (let i = 0; i < stepStarts.length; i++) if (stepStarts[i] <= along + 2) idx = i;
    const nextStep = leg.steps[idx + 1] || null;
    const distToNext = nextStep ? Math.max(0, stepStarts[idx + 1] - along) : remaining;
    const remainingS = leg.duration_s * (legPath.total ? remaining / legPath.total : 0);
    const end = legPath.points[legPath.points.length - 1];
    setState({
      display: onRoute ? pr.point : { lat: fix.lat, lng: fix.lng },
      heading: onRoute ? pr.heading : fix.heading ?? pr.heading,
      seg: onRoute ? pr.seg : hint.current,
      along,
      remaining,
      remainingS,
      progress: legPath.total ? along / legPath.total : 0,
      stepIdx: idx,
      step: leg.steps[idx],
      nextStep,
      thenStep: leg.steps[idx + 2] || null,
      distToNext,
      offRoute: off.current >= OFF_CONFIRM,
      deviating: !onRoute,
      arrived: (onRoute && remaining < ARRIVE_M) || haversine(fix, end) < ARRIVE_M,
    });
  }, [fix, legPath, leg, stepStarts]);

  return state;
}
