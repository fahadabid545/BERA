"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ChartCard } from "@/components/charts/ChartCard";
import { TipLines } from "@/components/charts/ChartTip";
import { ButtonLink, Select, Tooltip } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

import { TermLabel } from "./terms";
import { displayName, type CandidateColour } from "./types";

type Point = {
  id: string;
  name: string;
  file_name: string;
  grade: string;
  stage: string;
  x: number;
  y: number;
  beaten_by: string | null;
};
type Body = {
  axes: string;
  choices: string[];
  total: number;
  left_out: number;
  frontier: string[];
  compare_limits: { min: number; max: number };
  points: Point[];
};

const AXES: Record<string, { label: string; x: string; y: string }> = {
  ai_ats: { label: "AI score and ATS score", x: "ATS score", y: "AI score" },
  must_nice: {
    label: "Must-have and nice-to-have score",
    x: "Nice-to-have score",
    y: "Must-have score",
  },
};
const PERCENT = 100;
const STEP = 10;
const MARGIN = 5;
const SCORE_TOP = 100;

function domain(values: number[]): [number, number] {
  const low = Math.max(0, Math.floor((Math.min(...values) - MARGIN) / STEP) * STEP);
  const high = Math.min(SCORE_TOP, Math.ceil((Math.max(...values) + MARGIN) / STEP) * STEP);
  return high > low ? [low, high] : [low, low + STEP];
}
const ticks = ([low, high]: [number, number]) => {
  const step = high - low > 60 ? 2 * STEP : STEP;
  return Array.from({ length: Math.floor((high - low) / step) + 1 }, (_, i) => low + i * step);
};

/** The candidates set against two scores. The ones nobody beats on both scores form the
 * frontier: they are the ones worth comparing, because everyone else has someone better on
 * both. Every dot is a link to its candidate; hovering gives both scores and who beats it.
 * Candidates in the comparison on screen keep their colour. */
export function ParetoFrontier({
  projectId,
  chosen = {},
}: {
  projectId: string;
  chosen?: Record<string, CandidateColour>;
}) {
  const [axes, setAxes] = useState<string | null>(null);
  const [body, setBody] = useState<Body | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    let current = true;
    void getJson<Body>(
      `/api/company/projects/${projectId}/frontier/${axes ? `?axes=${axes}` : ""}`,
    ).then((result) => {
      if (!current) return;
      if (result.ok) {
        setBody(result.data);
        setError(null);
      } else setError(result.error);
    });
    return () => {
      current = false;
    };
  }, [projectId, axes]);

  if (!body) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const names = AXES[body.axes] ?? AXES.ai_ats;
  const onFrontier = new Set(body.frontier);
  const byId = new Map(body.points.map((point) => [point.id, point]));
  const [xLow, xHigh] = body.points.length ? domain(body.points.map((p) => p.x)) : [0, SCORE_TOP];
  const [yLow, yHigh] = body.points.length ? domain(body.points.map((p) => p.y)) : [0, SCORE_TOP];
  const left = (x: number) => ((x - xLow) / (xHigh - xLow)) * PERCENT;
  const top = (y: number) => PERCENT - ((y - yLow) / (yHigh - yLow)) * PERCENT;
  const line = body.frontier
    .map((id) => byId.get(id))
    .filter((point): point is Point => Boolean(point))
    .map((point) => `${left(point.x)},${top(point.y)}`);
  const shown = body.frontier.slice(0, body.compare_limits.max);
  return (
    <ChartCard
      title="Pareto frontier"
      controls={
        <Select
          label="Scores"
          value={body.axes}
          onChange={(event) => setAxes(event.target.value)}
          options={body.choices.map((choice) => ({
            value: choice,
            label: AXES[choice]?.label ?? choice,
          }))}
        />
      }
    >
      {body.points.length === 0 ? (
        <p role="status">No candidates to place yet.</p>
      ) : (
        <>
          <div className="pareto">
            <ul className="pareto__scale pareto__scale--y" aria-hidden="true">
              {ticks([yLow, yHigh]).map((tick) => (
                <li key={tick} style={{ top: `${top(tick)}%` }}>
                  {tick}
                </li>
              ))}
            </ul>
            <div className="pareto__plot">
              <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                {ticks([yLow, yHigh]).map((tick) => (
                  <line
                    key={`y${tick}`}
                    className="pareto__grid"
                    x1={0}
                    x2={100}
                    y1={top(tick)}
                    y2={top(tick)}
                  />
                ))}
                {ticks([xLow, xHigh]).map((tick) => (
                  <line
                    key={`x${tick}`}
                    className="pareto__grid"
                    y1={0}
                    y2={100}
                    x1={left(tick)}
                    x2={left(tick)}
                  />
                ))}
                {line.length > 1 && (
                  <>
                    <polygon
                      className="pareto__area"
                      points={`${line[0].split(",")[0]},100 ${line.join(" ")} ${line[line.length - 1].split(",")[0]},100`}
                    />
                    <polyline className="pareto__line" points={line.join(" ")} />
                  </>
                )}
              </svg>
              {body.points.map((point) => {
                const frontier = onFrontier.has(point.id);
                const colour = chosen[point.id];
                const beater = point.beaten_by ? byId.get(point.beaten_by) : null;
                const label = displayName(point);
                return (
                  <Tooltip
                    key={point.id}
                    content={
                      <TipLines
                        title={label}
                        lines={[
                          `${names.y} ${point.y}`,
                          `${names.x} ${point.x}`,
                          frontier
                            ? "On the frontier"
                            : beater
                              ? `Beaten on both scores by ${displayName(beater)}`
                              : "Beaten on both scores",
                        ]}
                      />
                    }
                  >
                    <Link
                      href={`/company/projects/${projectId}/candidates/${point.id}`}
                      className={`pareto__point${frontier ? " pareto__point--frontier" : ""}${
                        colour ? ` pareto__point--${colour}` : ""
                      }`}
                      style={{ left: `${left(point.x)}%`, top: `${top(point.y)}%` }}
                      aria-label={`${label}, ${names.y} ${point.y}, ${names.x} ${point.x}${
                        frontier ? ", on the frontier" : ""
                      }`}
                    >
                      {(frontier || colour) && <span className="pareto__label">{label}</span>}
                    </Link>
                  </Tooltip>
                );
              })}
            </div>
            <ul className="pareto__scale pareto__scale--x" aria-hidden="true">
              {ticks([xLow, xHigh]).map((tick) => (
                <li key={tick} style={{ left: `${left(tick)}%` }}>
                  {tick}
                </li>
              ))}
            </ul>
            <p className="pareto__axis pareto__axis--y">{names.y}</p>
            <p className="pareto__axis pareto__axis--x">{names.x}</p>
          </div>
          <ul className="pareto__legend">
            <li>
              <span className="pareto__swatch pareto__swatch--frontier" />
              <TermLabel term="frontier">On the frontier</TermLabel>
            </li>
            <li>
              <span className="pareto__swatch" />
              Other candidates
            </li>
            {Object.keys(chosen).length > 0 && (
              <li>
                <span className="pareto__swatch pareto__swatch--chosen" />
                In this comparison
              </li>
            )}
          </ul>
          <p role="status">
            {body.total} candidates placed
            {body.left_out > 0 ? `, ${body.left_out} left out without both scores` : ""}
          </p>
          {shown.length >= body.compare_limits.min && (
            <ButtonLink
              variant="secondary"
              href={`/company/projects/${projectId}/compare?ids=${shown.join(",")}`}
            >
              Compare the frontier
            </ButtonLink>
          )}
        </>
      )}
    </ChartCard>
  );
}
