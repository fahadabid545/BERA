"use client";

import { useEffect, useRef, useState } from "react";

import { stageLabel } from "@/components/company/stages";

import {
  DEMO_PROFILES,
  RESULT_WORD,
  STAGES_IN_ORDER,
  STAGE_DWELL_MS,
  demoGrade,
  type DemoProfile,
} from "./demo";

const RING_LENGTH = 151;
const COUNT_UP_MS = 1000;
const stageIndex = (name: (typeof STAGES_IN_ORDER)[number]) => STAGES_IN_ORDER.indexOf(name);

/** Counts up to the target once `active`; with no motion it simply shows the target. */
function useCountUp(target: number, active: boolean, animate: boolean) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!active) return setValue(0);
    if (!animate) return setValue(target);
    const start = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      const progress = Math.min(1, (now - start) / COUNT_UP_MS);
      setValue(Math.round(target * (1 - (1 - progress) ** 3)));
      if (progress < 1) frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [target, active, animate]);
  return value;
}

type CursorPoint = { left: string; top: string };
const CURSOR_IDLE: CursorPoint = { left: "74%", top: "8%" };
const CURSOR_AWAY: CursorPoint = { left: "92%", top: "55%" };

/**
 * The hero's live screening: one CV is scanned, its requirements are ticked, it is scored, and a
 * cursor moves the candidate to the next stage. Then the next candidate, from another field,
 * comes in. It is decoration, so assistive technology skips it; with reduced motion it rests on
 * one finished candidate.
 */
export function HeroScreening() {
  const [profileIndex, setProfileIndex] = useState(0);
  const [stage, setStage] = useState(0);
  const [resting, setResting] = useState(false);
  const deckRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLSpanElement>(null);
  const [buttonPoint, setButtonPoint] = useState<CursorPoint>(CURSOR_IDLE);

  useEffect(() => {
    const reduced =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setResting(true);
      setStage(stageIndex("decided"));
    }
  }, []);

  useEffect(() => {
    if (resting) return;
    const timer = setTimeout(() => {
      if (stage === STAGES_IN_ORDER.length - 1) {
        setProfileIndex((current) => (current + 1) % DEMO_PROFILES.length);
        setStage(0);
      } else {
        setStage((current) => current + 1);
      }
    }, STAGE_DWELL_MS[stage]);
    return () => clearTimeout(timer);
  }, [stage, resting]);

  const reached = (name: (typeof STAGES_IN_ORDER)[number]) => stage >= stageIndex(name);

  // The cursor aims at the button's real position, so it still lands on small screens.
  useEffect(() => {
    if (STAGES_IN_ORDER[stage] !== "cursor-moves") return;
    const deck = deckRef.current?.getBoundingClientRect();
    const button = buttonRef.current?.getBoundingClientRect();
    if (!deck || !button) return;
    setButtonPoint({
      left: `${button.left - deck.left + button.width * 0.55}px`,
      top: `${button.top - deck.top + button.height * 0.35}px`,
    });
  }, [stage]);

  const profile = DEMO_PROFILES[profileIndex];
  const scored = reached("score");
  const decided = reached("decided");
  const score = useCountUp(profile.score, scored, !resting);
  const requirementsShown = reached("requirement-3")
    ? 3
    : reached("requirement-2")
      ? 2
      : reached("requirement-1")
        ? 1
        : 0;
  const cursorAtButton = reached("cursor-moves") && !reached("cursor-leaves");
  const cursor = reached("cursor-leaves")
    ? CURSOR_AWAY
    : cursorAtButton
      ? buttonPoint
      : CURSOR_IDLE;
  const status = decided ? stageLabel(profile.stage) : stageLabel("new");
  const upcoming = [1, 2].map(
    (offset) => DEMO_PROFILES[(profileIndex + offset) % DEMO_PROFILES.length],
  );

  return (
    <div className="hero-demo" ref={deckRef} aria-hidden="true">
      <svg className="hero-demo__star" viewBox="0 0 100 100">
        <polygon points="50,2 61,35 96,35 67,56 78,90 50,69 22,90 33,56 4,35 39,35" />
      </svg>
      <svg className="hero-demo__dots" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="42" />
      </svg>
      {upcoming.map((next, position) => (
        <div key={position} className={`hero-demo__ghost hero-demo__ghost--${position + 1}`}>
          <Person profile={next} />
        </div>
      ))}
      <div
        key={profileIndex}
        className="hero-demo__card"
        data-leaving={stage === stageIndex("leave")}
      >
        <div className="hero-demo__top">
          <Person profile={profile} />
          <div className="hero-demo__ring">
            <svg viewBox="0 0 64 64">
              <circle className="hero-demo__ring-track" cx="32" cy="32" r="24" />
              <circle
                className="hero-demo__ring-fill"
                cx="32"
                cy="32"
                r="24"
                style={{ strokeDashoffset: RING_LENGTH * (1 - (scored ? profile.score : 0) / 100) }}
              />
            </svg>
            <b>{score}</b>
          </div>
        </div>
        <div className="hero-demo__sheet" data-scanning={reached("scan")}>
          <span data-highlight style={{ "--delay": "0.5s" } as React.CSSProperties} />
          <span />
          <span data-highlight style={{ "--delay": "0.9s" } as React.CSSProperties} />
          <span />
          <span data-highlight style={{ "--delay": "1.2s" } as React.CSSProperties} />
          <i className="hero-demo__scan" />
        </div>
        <ul className="hero-demo__requirements">
          {profile.requirements.map(([name, result], position) => (
            <li key={name} data-result={position < requirementsShown ? result : "pending"}>
              <span className="hero-demo__dot" />
              {name}
              <em>{position < requirementsShown ? RESULT_WORD[result] : ""}</em>
            </li>
          ))}
        </ul>
        <div className="hero-demo__foot">
          <span className="hero-demo__status" data-decided={decided}>
            {status}
          </span>
          <span
            ref={buttonRef}
            className="hero-demo__action"
            data-pressed={stage === stageIndex("click")}
          >
            {profile.action}
          </span>
        </div>
      </div>
      <span className="hero-demo__sticker" data-shown={scored}>
        Grade {demoGrade(profile.score)}
      </span>
      <span key={`status-${status}`} className="hero-demo__sticker hero-demo__sticker--status">
        {status}
      </span>
      <span className="hero-demo__cursor" style={cursor}>
        <i />
        <em>{profile.action}</em>
      </span>
    </div>
  );
}

function Person({ profile }: { profile: DemoProfile }) {
  return (
    <div className="hero-demo__person">
      <span className="hero-demo__avatar" data-tint={profile.tint}>
        {profile.initials}
      </span>
      <span>
        <b>{profile.name}</b>
        <small>{profile.role}</small>
      </span>
    </div>
  );
}
