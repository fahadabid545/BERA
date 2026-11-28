"use client";

import { useEffect, useState } from "react";

import {
  Avatar,
  Button,
  Dialog,
  Menu,
  ScoreBadge,
  StageGlyph,
  TextLink,
  type StageName,
} from "@/components/ui";
import { getJson, postJson, type ApiError } from "@/lib/api";
import { startLive } from "@/lib/live";

import type { Filters, RequirementChoice } from "./CandidateFilters";
import { STAGES, stageLabel } from "./stages";

type Card = {
  id: string;
  key: string;
  file_name: string;
  name: string;
  role: string;
  score: string | null;
  grade: string | null;
};
type Column = { stage: StageName; count: number; cards: Card[] };
type BoardData = {
  refresh_seconds: number;
  filtered: boolean;
  requirements: RequirementChoice[];
  columns: Column[];
};
type Move = { card: Card; stage: StageName };

/** The candidates as cards in one column for each stage. A card moves by dragging it to another
 * column or from its own menu (the keyboard way); either asks for confirmation first. */
export function CandidateBoard({
  projectId,
  filters = {},
  onRequirements,
}: {
  projectId: string;
  filters?: Filters;
  onRequirements?: (requirements: RequirementChoice[]) => void;
}) {
  const base = `/api/company/projects/${projectId}/candidates/`;
  const filterQuery = new URLSearchParams(filters).toString();
  const [shown, setShown] = useState<BoardData | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [dragged, setDragged] = useState<Card | null>(null);
  const [move, setMove] = useState<Move | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    return startLive(
      () => getJson<BoardData>(`${base}board/${filterQuery && `?${filterQuery}`}`),
      (result) => {
        if (result.ok) {
          setShown(result.data);
          onRequirements?.(result.data.requirements ?? []);
          setError(null);
        } else setError(result.error);
      },
    );
  }, [base, filterQuery, onRequirements, version]);

  async function confirmMove() {
    if (!move) return;
    const result = await postJson(`${base}stage/`, {
      candidate_ids: [move.card.id],
      stage: move.stage,
    });
    setMove(null);
    if (result.ok) {
      setError(null);
      setVersion((current) => current + 1);
    } else setError(result.error);
  }

  if (!shown) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : (
      <p role="status">Loading</p>
    );
  }

  return (
    <>
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <div className="board">
        {shown.columns.map((column) => (
          <section
            key={column.stage}
            className="board__column"
            aria-label={stageLabel(column.stage)}
            onDragOver={(event) => dragged && event.preventDefault()}
            onDrop={() => {
              if (dragged) setMove({ card: dragged, stage: column.stage });
              setDragged(null);
            }}
          >
            <h3 className="board__heading">
              <StageGlyph stage={column.stage} /> {stageLabel(column.stage)}
              <span className="board__count">{column.count}</span>
            </h3>
            {column.cards.map((card, position) => (
              <article
                key={card.id}
                className="board__card"
                draggable
                onDragStart={() => setDragged(card)}
                onDragEnd={() => setDragged(null)}
              >
                <div className="board__card-top">
                  <span className="board__key">{card.key}</span>
                  <ScoreBadge score={card.score} grade={card.grade} />
                </div>
                <TextLink href={`/company/projects/${projectId}/candidates/${card.id}`}>
                  {card.name || card.file_name}
                </TextLink>
                {card.role && <div className="board__role">{card.role}</div>}
                <div className="board__card-bottom">
                  <Avatar name={card.name || card.file_name} position={position} />
                  <Menu
                    trigger={
                      <Button variant="secondary" aria-label={`Move ${card.key}`}>
                        Move
                      </Button>
                    }
                    items={STAGES.filter((stage) => stage.value !== column.stage).map((stage) => ({
                      label: stage.label,
                      onSelect: () => setMove({ card, stage: stage.value as StageName }),
                    }))}
                  />
                </div>
              </article>
            ))}
            {column.count > column.cards.length && (
              <p className="board__more">
                Showing {column.cards.length} of {column.count}
              </p>
            )}
          </section>
        ))}
      </div>
      <Dialog
        open={move !== null}
        onOpenChange={(open) => !open && setMove(null)}
        title="Change stage"
        description={move ? `Move ${move.card.key} to ${stageLabel(move.stage)}?` : undefined}
        confirmLabel="Change stage"
        onConfirm={() => void confirmMove()}
      />
    </>
  );
}
