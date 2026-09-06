import { useEffect, useRef } from "react";

export default function Cursor() {
  const dotRef = useRef(null);
  const ringRef = useRef(null);

  useEffect(() => {
    if (window.matchMedia("(pointer: coarse)").matches) return;
    const dot = dotRef.current;
    const ring = ringRef.current;
    let rx = -100, ry = -100, tx = -100, ty = -100, scale = 1;
    const move = (e) => {
      tx = e.clientX; ty = e.clientY;
      const interactive = e.target.closest("a, button, [role='button'], input, select, textarea, [data-testid$='card']");
      scale = interactive ? 1.9 : 1;
      dot.style.transform = `translate(${tx}px, ${ty}px)`;
      ring.style.borderColor = interactive ? "hsl(var(--gold))" : "";
    };
    let raf;
    const loop = () => {
      rx += (tx - rx) * 0.16; ry += (ty - ry) * 0.16;
      ring.style.transform = `translate(${rx}px, ${ry}px) scale(${scale})`;
      raf = requestAnimationFrame(loop);
    };
    window.addEventListener("mousemove", move);
    loop();
    return () => { window.removeEventListener("mousemove", move); cancelAnimationFrame(raf); };
  }, []);

  return (
    <>
      <div ref={dotRef} className="pointer-events-none fixed top-0 left-0 z-[9999] h-1.5 w-1.5 -ml-[3px] -mt-[3px] rounded-full"
        style={{ background: "hsl(var(--gold))" }} />
      <div ref={ringRef} className="pointer-events-none fixed top-0 left-0 z-[9998] h-8 w-8 -ml-4 -mt-4 rounded-full border border-foreground/30"
        style={{ transition: "border-color 0.2s ease" }} />
    </>
  );
}
