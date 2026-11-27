"use client";

import { useEffect, useRef, useState, type ElementType, type HTMLAttributes } from "react";

type RevealProps = HTMLAttributes<HTMLElement> & { as?: ElementType };

/**
 * Fades and lifts its content in the first time it scrolls into view. The content is fully
 * visible until the page is running and in browsers without scroll observers or with reduced
 * motion, so nothing is ever hidden for good.
 */
export function Reveal({ as: Tag = "div", className = "", ...props }: RevealProps) {
  const ref = useRef<HTMLElement>(null);
  const [state, setState] = useState<"visible" | "waiting" | "shown">("visible");

  useEffect(() => {
    const element = ref.current;
    const reduced =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!element || reduced || typeof IntersectionObserver === "undefined") return;
    setState("waiting");
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        setState("shown");
        observer.disconnect();
      },
      { threshold: 0.12 },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return <Tag ref={ref} className={`reveal ${className}`} data-reveal={state} {...props} />;
}
