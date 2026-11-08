import { useEffect } from "react";
import { motion, useAnimationControls } from "framer-motion";

export const SHEET_SNAPS = { peek: 168, half: 0.55, full: 0.9 };

export function sheetHeight(snap) {
  const v = SHEET_SNAPS[snap];
  return v > 1 ? v : Math.round(window.innerHeight * v);
}

export function MobileSheet({ snap, setSnap, peek, children }) {
  const controls = useAnimationControls();
  useEffect(() => {
    controls.start({ height: sheetHeight(snap), transition: { type: "spring", damping: 30, stiffness: 280 } });
  }, [snap, controls]);

  const onDragEnd = (_, info) => {
    const order = ["peek", "half", "full"];
    const i = order.indexOf(snap);
    if (info.offset.y < -40 || info.velocity.y < -400) setSnap(order[Math.min(2, i + 1)]);
    else if (info.offset.y > 40 || info.velocity.y > 400) setSnap(order[Math.max(0, i - 1)]);
  };

  return (
    <motion.div initial={{ height: sheetHeight(snap) }} animate={controls}
      className="fixed left-0 right-0 bottom-0 z-20 rf-sheet flex flex-col" data-testid="mobile-bottom-sheet">
      <motion.div drag="y" dragConstraints={{ top: 0, bottom: 0 }} dragElastic={0.15} onDragEnd={onDragEnd}
        onClick={() => setSnap(snap === "peek" ? "half" : snap === "half" ? "full" : "peek")}
        className="pt-2.5 pb-2 cursor-grab touch-none" data-testid="sheet-handle">
        <div className="mx-auto h-1.5 w-12 rounded-full bg-white/25" />
        {peek && <div className="px-5 pt-3">{peek}</div>}
      </motion.div>
      <div className="flex-1 overflow-y-auto overscroll-contain px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">{children}</div>
    </motion.div>
  );
}
