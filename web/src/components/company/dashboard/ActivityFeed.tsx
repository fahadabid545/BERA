import { Card, Tag, TextLink } from "@/components/ui";
import { timeAgo } from "@/lib/timeAgo";

import { stageLabel } from "../stages";
import type { ActivityEvent } from "./types";

const project = (id: string) => `/company/projects/${id}`;

function Sentence({ event }: { event: ActivityEvent }) {
  if (event.kind === "shared") {
    return (
      <>
        A report link for{" "}
        <TextLink href={`${project(event.project_id)}/candidates`}>{event.project_title}</TextLink>{" "}
        was made and opened {event.views} times
      </>
    );
  }
  const who = (
    <TextLink href={`${project(event.project_id)}/candidates/${event.id}`}>
      {event.name || event.file_name}
    </TextLink>
  );
  const where = <TextLink href={project(event.project_id)}>{event.project_title}</TextLink>;
  return event.kind === "scored" ? (
    <>
      {who} scored {event.score} in {where}
    </>
  ) : (
    <>
      {who} moved to {stageLabel(event.to_stage ?? "")} in {where}
    </>
  );
}

/** The latest things that happened, newest first, each name a link to where it happened. */
export function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  return (
    <Card className="ui-card">
      <div className="chart-card__header">
        <h2>Live activity</h2>
        <Tag variant="live">Live</Tag>
      </div>
      {events.length === 0 ? (
        <p role="status">Nothing has happened yet.</p>
      ) : (
        <ul className="activity-feed">
          {events.map((event) => (
            <li key={`${event.kind}-${event.id}-${event.at}`} className="activity-feed__item">
              <span>
                <Sentence event={event} />
              </span>
              <time dateTime={event.at}>{timeAgo(event.at)}</time>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
