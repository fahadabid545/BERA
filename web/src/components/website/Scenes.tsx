/* Small illustrated scenes for the home page's step and feature cards. They are decoration:
   made-up people and numbers, drawn with markup and CSS, and hidden from assistive technology. */

import { RESULT_WORD, type RequirementResult } from "./home/demo";

function Result({ name, result }: { name: string; result: RequirementResult }) {
  return (
    <li className="scene__requirement" data-result={result}>
      <span className="scene__dot" />
      {name}
      <em>{RESULT_WORD[result]}</em>
    </li>
  );
}

function Ring({ value }: { value: number }) {
  return (
    <span className="scene__ring" style={{ "--value": value } as React.CSSProperties}>
      <svg viewBox="0 0 64 64">
        <circle className="scene__ring-track" cx="32" cy="32" r="24" />
        <circle className="scene__ring-fill" cx="32" cy="32" r="24" />
      </svg>
      <b>{value}</b>
    </span>
  );
}

function Avatar({ initials, tint }: { initials: string; tint: string }) {
  return (
    <span className="scene__avatar" data-tint={tint}>
      {initials}
    </span>
  );
}

export function UploadScene() {
  return (
    <div className="scene scene--upload">
      {["cv_amina.pdf", "cv_daniel.docx", "cv_sara.pdf"].map((file) => (
        <div key={file} className="scene__file">
          {file}
          <i />
        </div>
      ))}
    </div>
  );
}

export function ScoreScene() {
  return (
    <div className="scene scene--score">
      <Ring value={92} />
      <ul className="scene__requirements">
        <Result name="5+ years Python" result="met" />
        <Result name="PostgreSQL" result="met" />
        <Result name="Cloud" result="partly" />
      </ul>
    </div>
  );
}

export function DecideScene() {
  return (
    <div className="scene scene--decide">
      <div className="scene__person">
        <Avatar initials="AF" tint="lime" />
        <span>
          <b>Amina Fake</b>
          <small>Backend Developer</small>
        </span>
        <b className="scene__score">92</b>
      </div>
      <div className="scene__flags">
        {["New", "Shortlisted", "Interviewed", "Selected"].map((flag) => (
          <span key={flag}>{flag}</span>
        ))}
      </div>
    </div>
  );
}

export function ExplainScene() {
  return (
    <div className="scene scene--explain">
      <div className="scene__person">
        <Avatar initials="AF" tint="lime" />
        <span>
          <b>Amina Fake</b>
          <small>Backend Developer</small>
        </span>
        <span className="scene__tag">Grade A</span>
      </div>
      <div className="scene__bars">
        <div style={{ "--value": "94%" } as React.CSSProperties}>
          <span>Must-have</span>
          <i />
        </div>
        <div style={{ "--value": "78%" } as React.CSSProperties}>
          <span>Nice-to-have</span>
          <i />
        </div>
      </div>
      <ul className="scene__requirements">
        <Result name="Strong Python across three roles" result="met" />
        <Result name="No cloud role listed" result="partly" />
      </ul>
    </div>
  );
}

export function CompareScene() {
  const rows: [string, RequirementResult, RequirementResult][] = [
    ["Python", "met", "partly"],
    ["PostgreSQL", "met", "met"],
    ["Cloud", "partly", "missing"],
  ];
  return (
    <div className="scene scene--compare">
      <div className="scene__row scene__row--head">
        <span>Requirement</span>
        <span>Amina</span>
        <span>Daniel</span>
      </div>
      {rows.map(([name, first, second]) => (
        <div key={name} className="scene__row">
          <span>{name}</span>
          <span className="scene__result" data-result={first}>
            {RESULT_WORD[first]}
          </span>
          <span className="scene__result" data-result={second}>
            {RESULT_WORD[second]}
          </span>
        </div>
      ))}
    </div>
  );
}

export function FilterScene() {
  return (
    <div className="scene scene--filter">
      <div className="scene__chips">
        {["AI score > 90", "ATS > 80", "Must: Yes"].map((chip) => (
          <span key={chip}>{chip}</span>
        ))}
      </div>
      {[
        ["AF", "lime", "Amina Fake", 92],
        ["DS", "lilac", "Daniel Sample", 84],
        ["SE", "peach", "Sara Example", 77],
      ].map(([initials, tint, name, score]) => (
        <div key={name} className="scene__mini">
          <Avatar initials={String(initials)} tint={String(tint)} />
          {name}
          <b>{score}</b>
        </div>
      ))}
    </div>
  );
}

export function ReportScene() {
  return (
    <div className="scene scene--report">
      <div className="scene__mini">Top 3 · Backend Developer</div>
      <div className="scene__mini">
        Amina Fake<b>92</b>
      </div>
      <div className="scene__link">
        <span className="scene__dot" />
        bera.example/r/••••••
        <span className="scene__copy">
          <span>Copy</span>
          <span>Copied</span>
        </span>
      </div>
    </div>
  );
}

export function TeamScene() {
  return (
    <div className="scene scene--team">
      <div className="scene__stack">
        {[
          ["AF", "lime"],
          ["MK", "sky"],
          ["RT", "lilac"],
          ["JP", "peach"],
        ].map(([initials, tint]) => (
          <Avatar key={initials} initials={initials} tint={tint} />
        ))}
      </div>
      <div className="scene__chips">
        {["Owner", "Member", "Member"].map((role, position) => (
          <span key={position}>{role}</span>
        ))}
      </div>
    </div>
  );
}

export function RetentionScene() {
  return (
    <div className="scene scene--retention">
      <span className="scene__pulse" />
      {["Uploaded", "Kept", "Kept", "Deleted"].map((label, position) => (
        <span key={position} className="scene__stop" data-deleted={label === "Deleted"}>
          {label}
        </span>
      ))}
    </div>
  );
}

export function ProjectScene() {
  return (
    <div className="scene scene--project">
      <div className="scene__person">
        <span className="scene__badge">Sales Manager</span>
        <span className="scene__tag">Open</span>
      </div>
      <div className="scene__group">
        <b>Must have</b>
        <div className="scene__chips">
          <span>B2B sales</span>
          <span>CRM tools</span>
        </div>
      </div>
      <div className="scene__group">
        <b>Nice to have</b>
        <div className="scene__chips">
          <span>Team leadership</span>
        </div>
      </div>
    </div>
  );
}

export function UsageScene() {
  return (
    <div className="scene scene--usage">
      <div className="scene__meter">
        <span>CVs used</span>
        <i />
      </div>
      <div className="scene__meter scene__meter--soft">
        <span>Plan limit</span>
        <i />
      </div>
    </div>
  );
}

export function ControlScene() {
  return (
    <div className="scene scene--control">
      <div className="scene__person">
        <b>Recommended: Strong match</b>
      </div>
      <div className="scene__buttons">
        <span>Reject</span>
        <span className="scene__press">Shortlist</span>
      </div>
      <i className="scene__pointer" />
    </div>
  );
}

export function HighlightScene() {
  return (
    <div className="scene scene--highlight">
      <div className="scene__sheet">
        <span />
        <span data-highlight />
        <span />
        <span data-highlight data-late />
        <span />
        <div className="scene__chips">
          <span>Python · 5 years</span>
        </div>
      </div>
    </div>
  );
}

export function ShieldScene() {
  return (
    <div className="scene scene--shield">
      <svg viewBox="0 0 76 88" fill="none">
        <path d="M38 4l30 11v26c0 20-13 35-30 43C21 76 8 61 8 41V15z" />
        <rect x="26" y="38" width="24" height="20" rx="4" />
        <path d="M30 38v-6a8 8 0 0116 0v6" />
      </svg>
      <div className="scene__chips">
        <span>Deleted automatically</span>
      </div>
    </div>
  );
}
